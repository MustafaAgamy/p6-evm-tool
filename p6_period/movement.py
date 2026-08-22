"""Schedule / critical-path movement between two updates.

`finish_slip` measures each activity's forecast-finish movement in working days.
`critical_movement` is the Windows-analysis heart: the critical / near-critical
activities whose finish moved this period (or that newly entered the critical path),
with the driver classified. `buckets` counts what moved: finished / started / slipped
/ stalled / re-sequenced.
"""
from datetime import datetime
from p6_evm.calendars import signed_working_days

NEAR_CRITICAL_WD = 10          # float <= 10 working days = near-critical (repo convention)
_MILESTONES = ('StartMilestone', 'FinishMilestone')


def _deep_wbs(act):
    """Deepest WBS name for an activity (last segment of the root-first wbs_path)."""
    p = act.get('wbs_path') or ''
    return p.split(' > ')[-1].strip() if p else '(no WBS)'


def _finish(act):
    return act.get('remaining_early_finish') or act.get('planned_finish')


def _fmt(d):
    return d.strftime('%d-%b-%Y') if d else '—'


def _wd(cal, d1, d2):
    """Signed working days d1->d2 (calendar days if no calendar / on error)."""
    if not d1 or not d2:
        return None
    if cal is None:
        return (d2 - d1).days
    try:
        return signed_working_days(cal, d1, d2)
    except Exception:
        return (d2 - d1).days


def _day_hours(cals, act):
    cal = cals.get(act.get('calendar_id'))
    return getattr(cal, 'day_hours', 8.0) if cal else 8.0


def _orig_days(act, dh):
    return (act.get('planned_duration') or 0.0) / (dh or 8.0)


def finish_slip(matched):
    """code -> signed working days the forecast finish moved (prev -> current)."""
    out = {}
    cals = getattr(matched.update, 'calendars', {}) or {}
    for code in matched.matched_codes:
        b, u = matched.baseline_by_code[code], matched.update_by_code[code]
        out[code] = _wd(cals.get(u.get('calendar_id')), _finish(b), _finish(u))
    return out


def critical_movement(matched, logic_changed_codes=frozenset(), include=None):
    """{'rows': [...], 'new_critical': n} — near-critical activities (float <= 10 wd)
    whose finish slipped this period, or that newly entered the critical path.

    Row: activity_id, activity_name, wbs, prev_finish, curr_finish, slip_days, float_days,
    driver ('logic changed' | 'duration extended' | 'progress shortfall' | 'held'),
    critical_status ('new' | 'stayed'), codes. `include` (set of codes) filters to
    construction/execution activities. Sorted by slip descending."""
    slips = finish_slip(matched)
    ucals = getattr(matched.update, 'calendars', {}) or {}
    bcals = getattr(matched.baseline, 'calendars', {}) or {}
    rows, new_critical = [], 0
    for code in matched.matched_codes:
        if include is not None and code not in include:
            continue
        b, u = matched.baseline_by_code[code], matched.update_by_code[code]
        cf, pf = u.get('total_float_days'), b.get('total_float_days')
        near_now = cf is not None and cf <= NEAR_CRITICAL_WD
        if not near_now:
            continue
        was_near = pf is not None and pf <= NEAR_CRITICAL_WD
        newly = not was_near
        if newly:
            new_critical += 1
        slip = slips.get(code)
        if not (slip and slip > 0) and not newly:
            continue
        extended = _orig_days(u, _day_hours(ucals, u)) - _orig_days(b, _day_hours(bcals, b)) > 0.05
        if code in logic_changed_codes:
            driver = 'logic changed'
        elif extended:
            driver = 'duration extended'
        elif slip and slip > 0:
            driver = 'progress shortfall'
        else:
            driver = 'held'
        rows.append({
            'activity_id': code,
            'activity_name': u.get('name', ''),
            'prev_finish': _fmt(_finish(b)),
            'curr_finish': _fmt(_finish(u)),
            'slip_days': slip,
            'float_days': round(cf, 1) if cf is not None else None,
            'driver': driver,
            'critical_status': 'new' if newly else 'stayed',
            'wbs': _deep_wbs(u),
            'codes': u.get('activity_codes') or {},   # for the activity-code columns/slicer in exports
        })
    rows.sort(key=lambda r: -(r['slip_days'] or 0))
    return {'rows': rows, 'new_critical': new_critical}


def _critical_wbs_chain(data, include=None):
    """Ordered list of distinct WBS the critical path (float <= 0) runs through,
    construction/execution only, ordered by forecast start (consecutive dups collapsed)."""
    acts = []
    for a in getattr(data, 'activities', {}).values():
        code = a.get('id')
        if not code or a.get('task_type') in _MILESTONES:
            continue
        if include is not None and code not in include:
            continue
        tf = a.get('total_float_days')
        if tf is None or tf > 0:
            continue
        acts.append(a)
    acts.sort(key=lambda a: a.get('remaining_early_start') or a.get('planned_start') or datetime.max)
    chain = []
    for a in acts:
        w = _deep_wbs(a)
        if not chain or chain[-1] != w:
            chain.append(w)
    return chain


def critical_path_by_wbs(matched, include=None):
    """Previous vs current critical path, summarised to WBS level (not activities).
    {'previous': [wbs...], 'current': [wbs...]}. (Legacy zero-float view; the report now
    uses driving_path below.)"""
    return {'previous': _critical_wbs_chain(matched.baseline, include),
            'current': _critical_wbs_chain(matched.update, include)}


def _driving_chain(data, include=None, max_len=500):
    """The driving/longest chain to the project-finish milestone, walked back via driving
    predecessors — the real critical path (one route). Returns ordered activities
    (start→finish), each {id, name, wbs_path, codes}. Construction/execution only if
    `include` given; milestones dropped from the boxes. Best-effort — [] on any error."""
    try:
        from p6_audit.graph import ScheduleGraph
        from p6_compare.driving import driving_predecessors
    except Exception:
        return []
    acts = getattr(data, 'activities', {}) or {}
    if not acts:
        return []

    def fin(a):
        return a.get('remaining_early_finish') or a.get('planned_finish')

    # Finish milestone = latest-finishing FinishMilestone, else latest-finishing activity.
    end, endf = None, None
    for oid, a in acts.items():
        if a.get('task_type') == 'FinishMilestone':
            f = fin(a)
            if f and (endf is None or f > endf):
                end, endf = oid, f
    if end is None:
        for oid, a in acts.items():
            f = fin(a)
            if f and (endf is None or f > endf):
                end, endf = oid, f
    if end is None:
        return []
    try:
        graph = ScheduleGraph(data)
    except Exception:
        return []
    chain, cur, seen = [], end, set()
    for _ in range(max_len):
        if not cur or cur in seen:
            break
        seen.add(cur)
        a = acts.get(cur)
        if a:
            chain.append(a)
        try:
            cands = [dp.get('pred_oid') for dp in driving_predecessors(graph, cur)]
        except Exception:
            cands = []
        if not cands:
            # No strictly-driving link (tolerance/constraint) — fall back to ALL predecessors
            # and take the controlling (latest-finishing) one, so the longest path continues.
            try:
                cands = [lk.get('other') for lk in graph.preds_of(cur)]
            except Exception:
                cands = []
        if not cands:
            break
        best, bestf = None, None                        # the controlling (latest-finishing) predecessor
        for poid in cands:
            p = acts.get(poid)
            if not p:
                continue
            f = fin(p)
            if bestf is None or (f and f > bestf):
                best, bestf = poid, f
        cur = best
    chain.reverse()
    out = []
    for a in chain:
        code = a.get('id')
        if not code or a.get('task_type') in _MILESTONES:
            continue
        if include is not None and code not in include:
            continue
        out.append({'id': code, 'name': a.get('name', ''),
                    'wbs_path': a.get('wbs_path') or '', 'codes': a.get('activity_codes') or {},
                    # dates so the UI/PDF can draw the driving path on a real time axis
                    'start': _iso(a.get('remaining_early_start') or a.get('planned_start')),
                    'finish': _iso(a.get('remaining_early_finish') or a.get('planned_finish'))})
    return out


def driving_path(matched, include=None):
    """Previous vs current driving path (ordered construction activities) so the UI can
    group/filter by WBS level or activity code and colour the divergence.
    {'previous': [...], 'current': [...]}."""
    return {'previous': _driving_chain(matched.baseline, include),
            'current': _driving_chain(matched.update, include)}


def period_plan_counts(matched, dd_prev, dd_now, include=None):
    """How many activities the PREVIOUS update was due to finish / start in this window
    (construction only if `include` given). Feeds the 'what moved' planned-vs-actual chart.
    {'planned_finish': n, 'planned_start': n}."""
    pf = ps = 0
    if not (dd_prev and dd_now):
        return {'planned_finish': 0, 'planned_start': 0}
    for code in matched.matched_codes:
        if include is not None and code not in include:
            continue
        b = matched.baseline_by_code[code]
        if b.get('task_type') in _MILESTONES:
            continue
        pct = b.get('percent_complete') or 0.0
        if pct < 1.0:
            bf = b.get('remaining_early_finish') or b.get('planned_finish')
            if bf and dd_prev < bf <= dd_now:
                pf += 1
        if pct == 0.0:
            bs = b.get('remaining_early_start') or b.get('planned_start')
            if bs and dd_prev < bs <= dd_now:
                ps += 1
    return {'planned_finish': pf, 'planned_start': ps}


def _iso(d):
    return d.strftime('%Y-%m-%d') if d else None


def milestone_drift(matched):
    """FINISH milestones: baseline finish, previous forecast, current forecast, and how
    many working days each slipped this period (prev→curr) and vs baseline. ISO dates
    carried for the drift chart. `overall` = the project-completion milestone (latest
    current forecast) — the report table shows only this one, the chart shows them all.
    {'rows': [all finish milestones], 'overall': row|None}."""
    ucals = getattr(matched.update, 'calendars', {}) or {}
    bl = getattr(matched.update, 'baseline_by_id', {}) or {}
    rows = []
    for code in matched.milestone_codes:
        b, u = matched.baseline_by_code[code], matched.update_by_code[code]
        if u.get('task_type') != 'FinishMilestone':          # finish milestones only
            continue
        base_fin = (bl.get(code) or {}).get('planned_finish')
        prev_fc, curr_fc = _finish(b), _finish(u)
        cal = ucals.get(u.get('calendar_id'))
        rows.append({
            'activity_id': code, 'name': u.get('name', ''),
            'baseline_finish': _fmt(base_fin), 'prev_forecast': _fmt(prev_fc), 'curr_forecast': _fmt(curr_fc),
            'slip_period_days': _wd(cal, prev_fc, curr_fc),
            'slip_baseline_days': _wd(cal, base_fin, curr_fc),
            'baseline_iso': _iso(base_fin), 'prev_iso': _iso(prev_fc), 'curr_iso': _iso(curr_fc),
        })
    rows.sort(key=lambda r: -((r['slip_baseline_days'] or 0)))
    dated = [r for r in rows if r.get('curr_iso')]
    overall = max(dated, key=lambda r: r['curr_iso']) if dated else (rows[0] if rows else None)
    return {'rows': rows, 'overall': overall}


def buckets(matched, dd_now=None, logic_changed_codes=frozenset(), include=None):
    """{'counts': {...}, 'lists': {...}} — what moved this period, bucketed into
    finished / started / slipped / stalled / re_sequenced. Milestones excluded; `include`
    (set of codes) filters to construction/execution. `re_sequenced` = logic/lag changed."""
    slips = finish_slip(matched)
    counts = {'finished': 0, 'started': 0, 'slipped': 0, 'stalled': 0, 're_sequenced': 0}
    lists = {k: [] for k in counts}
    for code in matched.matched_codes:
        if include is not None and code not in include:
            continue
        b, u = matched.baseline_by_code[code], matched.update_by_code[code]
        if u.get('task_type') in _MILESTONES or b.get('task_type') in _MILESTONES:
            continue
        pp = (b.get('percent_complete') or 0.0) * 100
        cp = (u.get('percent_complete') or 0.0) * 100
        slip = slips.get(code)
        rec = {'activity_id': code, 'activity_name': u.get('name', '')}
        if cp >= 100 and pp < 100:
            counts['finished'] += 1; lists['finished'].append(rec)
        if pp == 0 and cp > 0:
            counts['started'] += 1; lists['started'].append(rec)
        if slip and slip > 0:
            counts['slipped'] += 1; lists['slipped'].append(rec)
        # Stalled: was scheduled to be underway by now but earned nothing this period.
        sched_start = b.get('remaining_early_start') or b.get('planned_start')
        if cp == pp and cp < 100 and sched_start and dd_now and sched_start <= dd_now:
            counts['stalled'] += 1; lists['stalled'].append(rec)
    for code in sorted(logic_changed_codes):
        u = matched.update_by_code.get(code, {})
        counts['re_sequenced'] += 1
        lists['re_sequenced'].append({'activity_id': code, 'activity_name': u.get('name', '')})
    return {'counts': counts, 'lists': lists}
