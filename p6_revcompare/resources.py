"""Slice-3 resource & cost comparison across two revisions.

Cost comparison works from the per-activity budget the parser has always summed
(``bac_by_activity``) — no parser change needed. Resource-level comparison uses the
additive ``assignments_by_activity`` / ``resources`` the parser now captures (only
populated when the export carries resource loading). The whole comparison is
**conditional on the data being available**: with no cost and no assignments it
reports nothing and the UI/report omit the section.

Pure functions over parsed ScheduleData + a MatchedSchedules; unit-tested.
"""

_COST_TOL = 0.5   # currency units; ignore sub-unit rounding
_MS = ('StartMilestone', 'FinishMilestone')


def _cost_by_code(data):
    out = {}
    for oid, act in data.activities.items():
        code = act.get('id')
        if code:
            out[code] = out.get(code, 0.0) + (data.bac_by_activity.get(oid) or 0.0)
    return out


def _assign_by_code(data):
    """activity code -> {resource key -> {'units', 'cost', 'rate', 'name'}} aggregated."""
    out = {}
    amap = getattr(data, 'assignments_by_activity', None) or {}
    for oid, act in data.activities.items():
        code = act.get('id')
        if not code:
            continue
        for a in amap.get(oid, []):
            # Key by the P6 resource CODE (rsrc_short_name / XML Id) — stable across revisions AND
            # unique, so two resources that merely share a name are NOT merged, and the same resource
            # matches across Rev.00/Rev.01. Fall back to name then the internal id only when no code.
            key = a.get('resource_code') or a.get('resource_name') or a.get('resource_id')
            if not key:
                continue
            disp_id = a.get('resource_code') or a.get('resource_id')
            slot = out.setdefault(code, {}).setdefault(key, {
                'units': 0.0, 'cost': 0.0, 'rate': a.get('rate'),
                'name': a.get('resource_name') or a.get('resource_code') or key,
                'id': disp_id, 'type': a.get('resource_type')})
            slot['units'] += a.get('budget_units') or 0.0
            slot['cost'] += a.get('budget_cost') or 0.0
            if slot['rate'] is None:
                slot['rate'] = a.get('rate')
            if not slot.get('id'):
                slot['id'] = disp_id
            if not slot.get('type'):
                slot['type'] = a.get('resource_type')
    return out


def _resource_totals(a0, a1):
    """Per-resource before/after roll-up (units summed across all activities, activity count,
    type, and a neutral change kind) — drives the #6 before/after 'resource comparison' bars,
    summary chips and enhanced table. `a0`/`a1` are the `_assign_by_code` maps for each rev."""
    def roll(amap):
        agg = {}
        for code, res in amap.items():
            for key, slot in res.items():
                g = agg.setdefault(key, {'units': 0.0, 'acts': set(), 'name': slot.get('name'),
                                         'id': slot.get('id'), 'type': slot.get('type')})
                g['units'] += slot.get('units') or 0.0
                g['acts'].add(code)
                for f in ('id', 'name', 'type'):
                    if not g.get(f):
                        g[f] = slot.get(f)
        return agg
    g0, g1 = roll(a0), roll(a1)
    rows = []
    for key in sorted(set(g0) | set(g1)):
        s0, s1 = g0.get(key), g1.get(key)
        u0 = round(s0['units'], 1) if s0 else 0.0
        u1 = round(s1['units'], 1) if s1 else 0.0
        acts = len((s1 or s0)['acts'])
        if u0 and not u1:
            kind = 'removed'
        elif u1 and not u0:
            kind = 'added'
        elif abs(u1 - u0) > 0.5:
            kind = 'increased' if u1 > u0 else 'decreased'
        else:
            kind = 'unchanged'
        meta = s1 or s0
        rows.append({
            'id': meta.get('id') or '', 'name': meta.get('name') or str(key), 'type': meta.get('type') or '',
            'rev0': u0, 'rev1': u1, 'var': round(u1 - u0, 1),
            'activities': acts, 'kind': kind,
        })
    # Biggest movers first; unchanged rows sink to the bottom.
    rows.sort(key=lambda r: (r['kind'] == 'unchanged', -abs(r['var']), -max(r['rev0'], r['rev1'])))
    return rows


def _fmt_money(v):
    return f'{round(v):,}' if v else '0'


def diff_resources(rev0, rev1, matched):
    c0, c1 = _cost_by_code(rev0), _cost_by_code(rev1)
    total0, total1 = sum(c0.values()), sum(c1.values())
    cost_available = bool(total0 or total1)

    activity_cost_changes = []
    if cost_available:
        for code in matched.matched_codes:
            v0, v1 = c0.get(code, 0.0), c1.get(code, 0.0)
            if abs(v1 - v0) > _COST_TOL:
                a1 = matched.update_by_code.get(code) or matched.baseline_by_code.get(code) or {}
                codes = dict(a1.get('activity_codes') or {})
                wp = a1.get('wbs_path')
                if wp:
                    codes['WBS'] = wp.split(' > ', 1)[0].strip() or wp
                activity_cost_changes.append({
                    'code': code, 'name': a1.get('name') or code,
                    'rev0': _fmt_money(v0), 'rev1': _fmt_money(v1),
                    'rev0_num': round(v0), 'rev1_num': round(v1),
                    'delta': round(v1 - v0), 'codes': codes,
                })
        activity_cost_changes.sort(key=lambda r: -abs(r['delta']))

    # Cost reconciliation (comment: show where the rest of the budget sits — the changed-activity
    # total is less than the whole budget). Partition every coded activity into disjoint buckets
    # that sum back to the total budget: Changed (matched, cost moved) uses the SAME figures as the
    # itemised table above; the remainder splits into Unchanged (both, same cost), New scope (Rev.01
    # only) and Removed scope (Rev.00 only).
    cost_reconciliation = []
    if cost_available:
        # Every bucket AND the total are summed from the SAME per-activity ROUNDED values, and the
        # total row is the sum of the buckets (not a separately-rounded whole) — so the parts always
        # tie to the whole even when per-activity costs are fractional (rate × units). "Changed" uses
        # the same rounded figures as the itemised table / pie, so all three agree.
        changed_codes = {r['code'] for r in activity_cost_changes}
        ch0 = sum(r['rev0_num'] for r in activity_cost_changes)
        ch1 = sum(r['rev1_num'] for r in activity_cost_changes)
        un0 = un1 = add1 = rem0 = 0
        for code in set(c0) | set(c1):
            if code in changed_codes:
                continue
            v0, v1 = round(c0.get(code, 0.0)), round(c1.get(code, 0.0))
            if code in c0 and code not in c1:
                rem0 += v0
            elif code in c1 and code not in c0:
                add1 += v1
            else:
                un0 += v0
                un1 += v1
        tot0, tot1 = ch0 + un0 + rem0, ch1 + un1 + add1
        cost_reconciliation = [
            {'bucket': 'changed', 'label': 'Changed activities', 'note': 'matched, cost moved',
             'rev0': ch0, 'rev1': ch1, 'delta': ch1 - ch0},
            {'bucket': 'unchanged', 'label': 'Unchanged activities', 'note': 'matched, same cost',
             'rev0': un0, 'rev1': un1, 'delta': un1 - un0},
            {'bucket': 'added', 'label': 'New scope', 'note': 'added in Rev.01',
             'rev0': 0, 'rev1': add1, 'delta': add1},
            {'bucket': 'removed', 'label': 'Removed scope', 'note': 'only in Rev.00',
             'rev0': rem0, 'rev1': 0, 'delta': -rem0},
            {'bucket': 'total', 'label': 'Budget total', 'note': 'whole project',
             'rev0': tot0, 'rev1': tot1, 'delta': tot1 - tot0},
        ]

    a0, a1 = _assign_by_code(rev0), _assign_by_code(rev1)
    resource_available = bool(a0 or a1)
    assignment_changes = []
    res_added = res_removed = units_changed = 0
    if resource_available:
        for code in matched.matched_codes:
            r0, r1 = a0.get(code, {}), a1.get(code, {})
            for key in sorted(set(r0) | set(r1)):
                s0, s1 = r0.get(key), r1.get(key)
                name = matched.update_by_code.get(code, {}).get('name') or code
                meta = s1 or s0
                rname = meta.get('name') or key           # resource display NAME
                rid = meta.get('id') or ''                 # P6 human Resource Id (code)
                if s1 and not s0:
                    res_added += 1
                    assignment_changes.append(_arow(code, name, 'added', rname, '—', _units(s1), rid))
                elif s0 and not s1:
                    res_removed += 1
                    assignment_changes.append(_arow(code, name, 'removed', rname, _units(s0), '—', rid))
                else:
                    if abs((s0['units'] or 0) - (s1['units'] or 0)) > 0.5:
                        units_changed += 1
                        assignment_changes.append(_arow(code, name, 'units', rname, _units(s0), _units(s1), rid))
                    elif _rate(s0) != _rate(s1) and (s0.get('rate') is not None or s1.get('rate') is not None):
                        assignment_changes.append(_arow(code, name, 'rate', rname, _rate(s0), _rate(s1), rid))

    resource_totals = _resource_totals(a0, a1) if resource_available else []
    tot_added = sum(1 for r in resource_totals if r['kind'] == 'added')
    tot_removed = sum(1 for r in resource_totals if r['kind'] == 'removed')
    tot_resized = sum(1 for r in resource_totals if r['kind'] in ('increased', 'decreased'))

    return {
        'cost_available': cost_available,
        'resource_available': resource_available,
        'total_budget': {'rev0': round(total0), 'rev1': round(total1), 'delta': round(total1 - total0)},
        'activity_cost_changes': activity_cost_changes,
        'cost_reconciliation': cost_reconciliation,
        'assignment_changes': assignment_changes,
        'resource_totals': resource_totals,
        'summary': {
            'cost_activities': len(activity_cost_changes),
            'resources_added': res_added, 'resources_removed': res_removed,
            'units_changed': units_changed, 'total_delta': round(total1 - total0),
            'res_added': tot_added, 'res_removed': tot_removed, 'res_resized': tot_resized,
        },
    }


def _units(slot):
    return f"{round(slot['units'], 1)} u"


def _rate(slot):
    r = slot.get('rate')
    return f'{round(r, 2)}/u' if r is not None else '—'


def _arow(code, name, kind, resource, rev0, rev1, resource_id=''):
    return {'code': code, 'name': name, 'kind': kind, 'resource': resource,
            'resource_id': resource_id, 'rev0': rev0, 'rev1': rev1}
