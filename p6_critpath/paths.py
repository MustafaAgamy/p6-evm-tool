"""Driving-path tracing and work-front boxes for the Critical Path Analyzer.

Traces P6's Longest Path (the driving predecessor chain) to a finish milestone and
rolls it up to WBS work-front boxes — the same picture as the driving-path chart in
Update Analysis §3, drawn independently here from the on-master primitives
(p6_compare.driving + p6_audit.graph) so this module needs no unmerged code.
"""
from datetime import datetime

from p6_audit.graph import ScheduleGraph
from p6_compare.driving import driving_predecessors
from p6_critpath.analysis import _forecast_finish, _ref_calendar, _wd_between, _iso, _MILESTONES


def _slip(cal, bl, exp):
    """Working-day slip between two FINISH dates, day-normalised so two dates that display
    the same (differing only by sub-day time) give exactly 0 — matching the milestones table
    (avoids the +1/-1 artifact from signed_working_days on equal calendar dates)."""
    d0 = lambda d: d.replace(hour=0, minute=0, second=0, microsecond=0) if isinstance(d, datetime) else d
    return _wd_between(cal, d0(bl), d0(exp))


def _governing_finish_ms(data):
    fin = [a for a in data.activities.values()
           if a.get('task_type') == 'FinishMilestone' and _forecast_finish(a)]
    pool = fin or [a for a in data.activities.values() if _forecast_finish(a)]
    return max(pool, key=_forecast_finish) if pool else None


def _find_milestone(data, milestone_code):
    if not milestone_code:
        return _governing_finish_ms(data)          # governing path by default
    for a in data.activities.values():
        if a.get('id') == milestone_code and a.get('task_type') == 'FinishMilestone':
            return a
    return None    # a specific milestone was asked for and this schedule doesn't have it —
                   # return no path rather than silently tracing a DIFFERENT (governing) one,
                   # which would mislabel one schedule's lane against another milestone.


def milestone_list(schedules):
    """All finish milestones across the loaded schedules, by code, with each schedule's
    forecast finish — feeds the milestone selector. Governing milestone flagged."""
    out = {}
    gov_codes = set()
    for role, data in schedules.items():
        gov = _governing_finish_ms(data)
        if gov:
            gov_codes.add(gov.get('id'))
        for a in data.activities.values():
            if a.get('task_type') != 'FinishMilestone':
                continue
            code = a.get('id')
            if not code:
                continue
            row = out.setdefault(code, {'id': code, 'name': a.get('name') or code, 'finishes': {}})
            row['finishes'][role] = _iso(_forecast_finish(a))
    rows = list(out.values())
    for r in rows:
        r['is_governing'] = r['id'] in gov_codes
    rows.sort(key=lambda r: (not r['is_governing'], r['name']))
    return rows


def trace_driving_chain(graph, start_oid, limit=500):
    """Walk backwards from the milestone along the binding predecessor at each step; return
    the chain earliest→last. Prefers the driving predecessor; falls back to the latest-
    finishing actual predecessor when the driving detector finds none (SS/FF-with-lag)."""
    chain, seen, cur = [start_oid], {start_oid}, start_oid
    while len(chain) < limit:
        cands = [pl['pred_oid'] for pl in driving_predecessors(graph, cur)]
        if not cands:
            cands = [link['other'] for link in graph.preds_of(cur)]
        best, best_f = None, None
        for poid in cands:
            if poid in seen:
                continue
            p = graph.activities.get(poid)
            if not p:
                continue
            f = _forecast_finish(p)
            if best is None or (f and (best_f is None or f > best_f)):
                best, best_f = poid, f
        if not best:
            break
        chain.append(best)
        seen.add(best)
        cur = best
    chain.reverse()
    return chain


# ── WBS rollup helpers ───────────────────────────────────────────────────────

def _wbs_ancestor_ids(wbs_id, wmap):
    ids, seen, cur = [], set(), wbs_id
    while cur and cur not in seen:
        seen.add(cur)
        ids.append(cur)
        node = wmap.get(cur)
        if not node:
            break
        cur = node.get('parent_object_id')
    return ids


def _wbs_name(wbs_id, wmap):
    return (wmap.get(wbs_id) or {}).get('name') or ''


def _crumb(wbs_id, wmap):
    ids = _wbs_ancestor_ids(wbs_id, wmap)[1:]
    names = [n for n in (_wbs_name(i, wmap) for i in ids) if n]
    return ' · '.join(list(reversed(names))[1:])   # drop project root


def _full_crumb(wbs_id, wmap):
    """The FULL WBS path of a work front, immediate-first, each level prefixed with '@' —
    e.g. '@Silo 9 @Phase C @Silos Civil Works'. The project root (top-most WBS) is dropped,
    since it just repeats the report title. So a box reads: <driving activity> @<its WBS> @…up."""
    ids = _wbs_ancestor_ids(wbs_id, wmap)          # [self, parent, …, root]
    if len(ids) > 1:
        ids = ids[:-1]                             # drop the project root
    names = [n for n in (_wbs_name(i, wmap) for i in ids) if n]
    return ' '.join('@' + n for n in names)


def _box_wbs_id(act, wmap, summary_level):
    ids = _wbs_ancestor_ids(act.get('wbs_id'), wmap)
    if not ids:
        return None
    return ids[min(summary_level, len(ids) - 1)]


def _cost_weight(data, act):
    oid = act.get('object_id')
    bl = getattr(data, 'baseline_bac_by_activity', None) or {}
    bac = getattr(data, 'bac_by_activity', None) or {}
    return bl.get(oid) or bac.get(oid) or 0.0


def _baseline_finish_of(data, act):
    bl = (getattr(data, 'baseline_by_id', None) or {}).get(act.get('id'))
    return bl.get('planned_finish') if bl else None


def _planned_pct(data, act, data_date, ref_cal):
    """The activity's PLANNED progress by the data date — the baseline schedule %: the share of
    its baseline duration (in working days) that should be done by the data date. 0 before its
    baseline start, 100 after its baseline finish. None when it has no baseline dates."""
    bl = (getattr(data, 'baseline_by_id', None) or {}).get(act.get('id'))
    if not bl or not data_date:
        return None
    bs, bf = bl.get('planned_start'), bl.get('planned_finish')
    if not (bs and bf):
        return None
    if data_date <= bs:
        return 0.0
    if data_date >= bf:
        return 1.0
    total = _wd_between(ref_cal, bs, bf)
    done = _wd_between(ref_cal, bs, data_date)
    if not total or total <= 0:
        return 1.0
    return max(0.0, min(1.0, done / total))


def _construction_ids(data):
    try:
        from p6_compare.report import _construction_codes
        return _construction_codes(data) or None
    except Exception:
        return None


def path_boxes(data, milestone_code=None, summary_level=0, construction_only=True):
    """The driving path to the chosen milestone (governing by default), as WBS work-front
    boxes in path order. Each box: WBS %-complete (cost-weighted, else simple), the WBS's
    baseline / forecast finish, and the slip between them. Construction/execution only."""
    milestone = _find_milestone(data, milestone_code)
    if not milestone:
        return {'milestone': None, 'boxes': []}

    graph = ScheduleGraph(data)
    chain = trace_driving_chain(graph, next(k for k, v in data.activities.items() if v is milestone))
    wmap = getattr(data, 'wbs', None) or {}
    ref_cal = _ref_calendar(data, milestone)
    data_date = (getattr(data, 'project', None) or {}).get('data_date')
    cons = _construction_ids(data) if construction_only else None

    # subtree index: wbs ancestor -> its activities
    subtree = {}
    for a in data.activities.values():
        for anc in _wbs_ancestor_ids(a.get('wbs_id'), wmap):
            subtree.setdefault(anc, []).append(a)

    box_order, seen_wids, box_driver, path_acts = [], set(), {}, []
    for oid in chain:
        act = graph.activities.get(oid)
        if not act or act.get('task_type') in _MILESTONES:
            continue
        if cons is not None and act.get('id') not in cons:
            continue
        path_acts.append(act)
        wid = _box_wbs_id(act, wmap, summary_level)
        if not wid or wid in seen_wids:
            continue
        seen_wids.add(wid)
        box_order.append(wid)
        box_driver[wid] = act

    boxes = []
    for wid in box_order:
        acts = subtree.get(wid, [])
        w = wa = 0.0
        pw = pp = 0.0                    # planned-% weight + weighted planned (over activities with a baseline)
        bls, exps, tfs = [], [], []
        for a in acts:
            cw = _cost_weight(data, a) or (a.get('planned_duration') or 1.0)
            w += cw
            wa += cw * (a.get('percent_complete') or 0.0)
            pl = _planned_pct(data, a, data_date, ref_cal)
            if pl is not None:
                pw += cw
                pp += cw * pl
            bf = _baseline_finish_of(data, a)
            ff = _forecast_finish(a)
            if bf:
                bls.append(bf)
            if ff:
                exps.append(ff)
            if a.get('total_float_days') is not None:
                tfs.append(a['total_float_days'])
        pct = round(wa / w * 100, 1) if w else 0.0
        planned = round(pp / pw * 100, 1) if pw else None
        bl_fin = max(bls) if bls else None
        exp_fin = max(exps) if exps else None
        driver = box_driver[wid]
        boxes.append({
            'wbs_id': wid,
            # Title = the driving activity (the specific work), then the full WBS chain in the crumb
            # → "Piles @Level +2.25" · "@Silo 9 @Phase C @Silos Civil Works" (Ibrahim's criteria).
            'name': driver.get('name') or driver.get('id') or _wbs_name(wid, wmap),
            'crumb': _full_crumb(wid, wmap),
            'pct': pct,
            'planned': planned,
            'complete': pct >= 100.0,
            'bl_finish': _iso(bl_fin),
            'exp_finish': _iso(exp_fin),
            'slip_days': _slip(ref_cal, bl_fin, exp_fin),
            'driver_tf': driver.get('total_float_days'),
        })

    ms_bl = _baseline_finish_of(data, milestone)
    ms_exp = _forecast_finish(milestone)
    return {
        'milestone': {
            'id': milestone.get('id'),
            'name': milestone.get('name') or milestone.get('id') or 'Completion',
            'baseline_finish': _iso(ms_bl),
            'expected_finish': _iso(ms_exp),
            'slip_days': _slip(ref_cal, ms_bl, ms_exp),
        },
        'boxes': boxes,
    }


def _box_key(b):
    return b.get('wbs_id') or b.get('name')


def path_diff(prev_boxes, curr_boxes):
    """Which work fronts entered / left / stayed on the critical path from prev → curr,
    keyed by WBS (falls back to name). 'entered' = new drivers (the reroute); 'left' =
    dropped off (float recovered); 'stayed' = on both."""
    prev_keys = {_box_key(b) for b in prev_boxes}
    curr_keys = {_box_key(b) for b in curr_boxes}
    entered = [b for b in curr_boxes if _box_key(b) not in prev_keys]
    left = [b for b in prev_boxes if _box_key(b) not in curr_keys]
    stayed = [b for b in curr_boxes if _box_key(b) in prev_keys]
    return {'entered': entered, 'left': left, 'stayed': stayed}
