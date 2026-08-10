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


def _dur_impact(float_days):
    """Whether a duration change reaches the project finish, judged by the activity's P6
    float (reliable, unlike a re-derived critical path). Direct = critical, Potential =
    near-critical (≤ 10 wd), None = float absorbs it."""
    if float_days is None:
        return 'Unknown'
    if float_days <= 0:
        return 'Direct'
    if float_days <= 10:
        return 'Potential'
    return 'None'


def diff_durations(matched, tol_days=0.05):
    """Original duration baseline vs update, and remaining vs the baseline allowance, with
    each change's impact on the project finish (from the update activity's P6 float).

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
            'impact': _dur_impact(upd.get('total_float_days')),
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


# ── Actual-relationship diff (all relationships, driving highlighted) ────────
# Reads the relationships/lags straight from the files (matched.baseline_rels /
# update_rels) rather than re-deriving "driving" from dates — so every predecessor and
# successor is always shown, never blank, even on a progressed update. "Driving" is
# kept only as a HIGHLIGHT (best-effort, date-derived; absent for completed activities).

def driving_pairs(graph):
    """Set of (pred_code, succ_code) that are driving in this schedule — for highlighting
    only, not the basis for the diff."""
    dm = driving_link_map(graph)
    pairs = set()
    for code, v in dm.items():
        for p in v['preds']:
            pairs.add((p, code))
        for s in v['succs']:
            pairs.add((code, s))
    return pairs


def _rel_index(rels, key_is_succ):
    """(pred_code, succ_code)->link  =>  code -> {other_code: link}, keyed by the successor
    (preds side) or the predecessor (succs side)."""
    out = {}
    for (p, s), v in rels.items():
        this, other = (s, p) if key_is_succ else (p, s)
        out.setdefault(this, {})[other] = v
    return out


def _diff_rel_side(base_side, upd_side, name_key):
    """Diff one side (preds or succs), each {other_code: link}. Returns
    (baseline_list, update_list, changed). Entries: {code, name, type, lag_days, status,
    driving}; changed update entries also carry change_kind ('type'|'lag')."""
    base_codes, upd_codes = set(base_side), set(upd_side)
    blist, ulist, changed = [], [], False
    for code in sorted(base_codes):
        b = base_side[code]
        status = 'same' if code in upd_codes else 'removed'
        if status == 'removed':
            changed = True
        blist.append({'code': code, 'name': b.get(name_key, ''), 'type': b.get('type', 'FS'),
                      'lag_days': b.get('lag_days', 0.0), 'status': status, 'driving': False})
    for code in sorted(upd_codes):
        u = upd_side[code]
        entry = {'code': code, 'name': u.get(name_key, ''), 'type': u.get('type', 'FS'),
                 'lag_days': u.get('lag_days', 0.0), 'status': 'same', 'driving': False}
        if code not in base_codes:
            entry['status'] = 'added'
            changed = True
        else:
            b = base_side[code]
            if b.get('type') != u.get('type'):
                entry['status'], entry['change_kind'], changed = 'changed', 'type', True
            elif abs((b.get('lag_days') or 0.0) - (u.get('lag_days') or 0.0)) > 1e-9:
                entry['status'], entry['change_kind'], changed = 'changed', 'lag', True
        ulist.append(entry)
    return blist, ulist, changed


def _rel_primary(up, us, bp, bs):
    added = any(l['status'] == 'added' for l in up + us)
    removed = any(l['status'] == 'removed' for l in bp + bs)
    if added and removed:
        return 'removed_added', 'Removed + added'
    if removed:
        return 'removed_driver', 'Link removed'
    if added:
        return 'added_driver', 'Link added'
    if any(l.get('change_kind') == 'type' for l in up + us):
        return 'type', 'Type changed'
    return 'lag', 'Lag changed'


def diff_relationships(matched, driving=frozenset()):
    """Compare ALL relationships (predecessors + successors) per activity from the files.
    Always populated (never a blank update side), driving flagged for highlight. A row
    appears if any predecessor or successor relationship/lag changed."""
    b_preds, u_preds = _rel_index(matched.baseline_rels, True), _rel_index(matched.update_rels, True)
    b_succs, u_succs = _rel_index(matched.baseline_rels, False), _rel_index(matched.update_rels, False)
    rows, by_kind = [], {}
    for code in matched.matched_codes:
        bp, up, p_ch = _diff_rel_side(b_preds.get(code, {}), u_preds.get(code, {}), 'pred_name')
        bs, us, s_ch = _diff_rel_side(b_succs.get(code, {}), u_succs.get(code, {}), 'succ_name')
        if not (p_ch or s_ch):
            continue
        for entry in bp + up:
            entry['driving'] = (entry['code'], code) in driving
        for entry in bs + us:
            entry['driving'] = (code, entry['code']) in driving
        primary, label = _rel_primary(up, us, bp, bs)
        by_kind[primary] = by_kind.get(primary, 0) + 1
        rows.append({
            'activity_id': code,
            'activity_name': (matched.update_by_code.get(code) or {}).get('name', ''),
            'primary_kind': primary, 'change_label': label,
            'baseline_preds': bp, 'update_preds': up,
            'baseline_succs': bs, 'update_succs': us,
        })
    return {'rows': rows, 'summary': {'changed_activities': len(rows), 'by_kind': by_kind}}
