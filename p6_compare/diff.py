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


def diff_logic(base_map, upd_map):
    """Compare two driving-link maps. Returns {'rows': [...], 'summary': {...}} with
    only the activities whose driving relationship or lag changed."""
    rows = []
    by_kind = {}
    for code in sorted(set(base_map) & set(upd_map)):
        b, u = base_map[code], upd_map[code]
        bp, up, p_add, p_rem, p_chg = _diff_side(b['preds'], u['preds'])
        bs, us, s_add, s_rem, s_chg = _diff_side(b['succs'], u['succs'])
        if not (p_add or p_rem or p_chg or s_add or s_rem or s_chg):
            continue
        swap = bool((p_add and p_rem) or (s_add and s_rem))
        primary, label = _primary_kind(swap, p_add, s_add, p_rem, s_rem, p_chg + s_chg)
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
