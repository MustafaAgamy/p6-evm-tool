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
            key = a.get('resource_name') or a.get('resource_id')
            if not key:
                continue
            slot = out.setdefault(code, {}).setdefault(key, {'units': 0.0, 'cost': 0.0, 'rate': a.get('rate'), 'name': key})
            slot['units'] += a.get('budget_units') or 0.0
            slot['cost'] += a.get('budget_cost') or 0.0
            if slot['rate'] is None:
                slot['rate'] = a.get('rate')
    return out


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
                a1 = matched.update_by_code.get(code) or {}
                activity_cost_changes.append({
                    'code': code, 'name': a1.get('name') or code,
                    'rev0': _fmt_money(v0), 'rev1': _fmt_money(v1),
                    'delta': round(v1 - v0),
                })
        activity_cost_changes.sort(key=lambda r: -abs(r['delta']))

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
                if s1 and not s0:
                    res_added += 1
                    assignment_changes.append(_arow(code, name, 'added', key, '—', _units(s1)))
                elif s0 and not s1:
                    res_removed += 1
                    assignment_changes.append(_arow(code, name, 'removed', key, _units(s0), '—'))
                else:
                    if abs((s0['units'] or 0) - (s1['units'] or 0)) > 0.5:
                        units_changed += 1
                        assignment_changes.append(_arow(code, name, 'units', key, _units(s0), _units(s1)))
                    elif _rate(s0) != _rate(s1) and (s0.get('rate') is not None or s1.get('rate') is not None):
                        assignment_changes.append(_arow(code, name, 'rate', key, _rate(s0), _rate(s1)))

    return {
        'cost_available': cost_available,
        'resource_available': resource_available,
        'total_budget': {'rev0': round(total0), 'rev1': round(total1), 'delta': round(total1 - total0)},
        'activity_cost_changes': activity_cost_changes,
        'assignment_changes': assignment_changes,
        'summary': {
            'cost_activities': len(activity_cost_changes),
            'resources_added': res_added, 'resources_removed': res_removed,
            'units_changed': units_changed, 'total_delta': round(total1 - total0),
        },
    }


def _units(slot):
    return f"{round(slot['units'], 1)} u"


def _rate(slot):
    r = slot.get('rate')
    return f'{round(r, 2)}/u' if r is not None else '—'


def _arow(code, name, kind, resource, rev0, rev1):
    return {'code': code, 'name': name, 'kind': kind, 'resource': resource, 'rev0': rev0, 'rev1': rev1}
