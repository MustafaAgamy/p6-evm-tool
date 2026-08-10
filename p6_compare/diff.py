"""Diff driving links (and later durations) between a baseline and an update.

`driving_link_map` turns a ScheduleGraph into a per-code view of DRIVING
predecessors/successors; `diff_logic` compares two such maps and returns only the
activities whose driving relationship or lag changed, with each side's links
annotated for the report table.
"""
from p6_compare.driving import driving_predecessors, driving_successors


# ── Bridge: graph -> per-code driving-link map ─────────────────────────────

def driving_link_map(graph, tolerance=1.0):
    """code -> {'name', 'preds': {code: link}, 'succs': {code: link}} of driving links.

    link = {'type', 'lag_days', 'name'}. Keys are Activity codes so a baseline map and
    an update map compare directly.
    """
    acts = graph.activities
    out = {}
    for oid, act in acts.items():
        code = act.get('id')
        if not code:
            continue
        preds = {}
        for dl in driving_predecessors(graph, oid, tolerance):
            p = acts.get(dl['pred_oid'])
            if p and p.get('id'):
                preds[p['id']] = {'type': dl['type'], 'lag_days': dl['lag_days'], 'name': p.get('name', '')}
        succs = {}
        for dl in driving_successors(graph, oid, tolerance):
            s = acts.get(dl['succ_oid'])
            if s and s.get('id'):
                succs[s['id']] = {'type': dl['type'], 'lag_days': dl['lag_days'], 'name': s.get('name', '')}
        out[code] = {'name': act.get('name', ''), 'preds': preds, 'succs': succs}
    return out


# ── Per-side diff ──────────────────────────────────────────────────────────

def _diff_side(base_side, upd_side):
    """Compare one side (preds or succs). Returns (baseline_list, update_list, added, removed, changed).

    Each list entry: {code, name, type, lag_days, status}; status in same/changed/added/removed.
    `changed` items: {code, kind ('type'|'lag'), delta (lag change, else 0.0)}.
    """
    base_codes, upd_codes = set(base_side), set(upd_side)
    baseline_list, update_list = [], []
    added, removed, changed = [], [], []

    for code in sorted(base_codes):
        b = base_side[code]
        status = 'same' if code in upd_codes else 'removed'
        if status == 'removed':
            removed.append(code)
        baseline_list.append({'code': code, 'name': b['name'], 'type': b['type'],
                              'lag_days': b['lag_days'], 'status': status})

    for code in sorted(upd_codes):
        u = upd_side[code]
        if code not in base_codes:
            status = 'added'
            added.append(code)
        else:
            b = base_side[code]
            if b['type'] != u['type']:
                status = 'changed'
                changed.append({'code': code, 'kind': 'type', 'delta': 0.0})
            elif abs((b['lag_days'] or 0.0) - (u['lag_days'] or 0.0)) > 1e-9:
                status = 'changed'
                changed.append({'code': code, 'kind': 'lag',
                                'delta': (u['lag_days'] or 0.0) - (b['lag_days'] or 0.0)})
            else:
                status = 'same'
        update_list.append({'code': code, 'name': u['name'], 'type': u['type'],
                            'lag_days': u['lag_days'], 'status': status})

    return baseline_list, update_list, added, removed, changed


def _primary_kind(swap, p_add, s_add, p_rem, s_rem, changed):
    """One bucket per changed activity, most-significant first, with a display label."""
    if swap:
        return 'removed_added', 'Removed + added'
    if p_add:
        return 'added_driver', 'Driving pred added'
    if s_add:
        return 'added_driver', 'Driving succ added'
    if p_rem or s_rem:
        return 'removed_driver', 'Driving link removed'
    if any(c['kind'] == 'type' for c in changed):
        return 'type', 'Type'
    up = any(c['delta'] > 0 for c in changed if c['kind'] == 'lag')
    return 'lag', 'Lag ↑' if up else 'Lag ↓'


def _day_hours(data, act):
    cal = (getattr(data, 'calendars', {}) or {}).get(act.get('calendar_id'))
    return getattr(cal, 'day_hours', 8.0) if cal else 8.0


def diff_durations(matched, tol_days=0.05):
    """Original duration baseline vs update, and remaining vs the baseline allowance.

    Durations are stored in hours; converted to days on each side's calendar. Only
    activities that were extended, or whose remaining exceeds the baseline original,
    appear (on-track activities are omitted). Returns {'rows': [...], 'counts': {...}}.
    """
    rows = []
    counts = {}
    for code in matched.matched_codes:
        base = matched.baseline_by_code[code]
        upd = matched.update_by_code[code]
        b_dh = _day_hours(matched.baseline, base)
        u_dh = _day_hours(matched.update, upd)
        base_orig = round((base.get('planned_duration') or 0.0) / b_dh, 1)
        upd_orig = round((upd.get('planned_duration') or 0.0) / u_dh, 1)
        remaining = round((upd.get('remaining_duration') or 0.0) / u_dh, 1)
        if upd_orig - base_orig > tol_days:
            status = 'extended'
        elif remaining - base_orig > tol_days:
            status = 'not_burning'
        else:
            continue
        counts[status] = counts.get(status, 0) + 1
        rows.append({
            'activity_id': code,
            'activity_name': upd.get('name', ''),
            'baseline_orig_days': base_orig,
            'update_orig_days': upd_orig,
            'remaining_days': remaining,
            'remaining_minus_baseline_days': round(remaining - base_orig, 1),
            'over_baseline': (remaining - base_orig) > tol_days,
            'status': status,
        })
    rows.sort(key=lambda r: -r['remaining_minus_baseline_days'])
    return {'rows': rows, 'counts': counts}


def _plain(side):
    """Context list (no diff status) of an activity's driving links, sorted by code."""
    return [{'code': c, 'name': v['name'], 'type': v['type'], 'lag_days': v['lag_days'], 'status': 'same'}
            for c, v in sorted(side.items())]


def diff_logic(base_map, upd_map):
    """Compare two driving-link maps on BOTH sides.

    Each activity's driving predecessors AND successors are diffed and highlighted, so
    a changed driving successor lights up on that activity's own row — not only on the
    other end. An activity appears if any driving predecessor OR successor relationship
    or lag changed. Returns {'rows': [...], 'summary': {...}}.
    """
    rows = []
    by_kind = {}
    for code in sorted(set(base_map) & set(upd_map)):
        b, u = base_map[code], upd_map[code]
        bp, up, p_add, p_rem, p_chg = _diff_side(b['preds'], u['preds'])
        bs, us, s_add, s_rem, s_chg = _diff_side(b['succs'], u['succs'])
        # One row per relationship, keyed to the driven (predecessor-changed) activity, so a
        # link isn't listed twice. The successor columns still diff+highlight, so a changed
        # driving successor lights up on the rows that appear.
        if not (p_add or p_rem or p_chg):
            continue
        swap = bool(p_add and p_rem)
        primary, label = _primary_kind(swap, p_add, [], p_rem, [], p_chg)
        by_kind[primary] = by_kind.get(primary, 0) + 1
        rows.append({
            'activity_id': code,
            'activity_name': u.get('name') or b.get('name') or '',
            'primary_kind': primary,
            'change_label': label,
            'baseline_preds': bp, 'update_preds': up,
            'baseline_succs': bs, 'update_succs': us,
        })
    return {'rows': rows, 'summary': {'changed_activities': len(rows), 'by_kind': by_kind}}
