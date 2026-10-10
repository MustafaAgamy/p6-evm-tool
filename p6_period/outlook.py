"""Planning-manager outlook: schedule adherence, recovery outlook, next-period watch list.

These are *indicative planning projections*, not a P6 CPM result — the tool never
schedules. They read the current update's own dates/float and the period rate to
answer a manager's questions: are we executing to plan, can we still recover, and
what drives the next window. Every figure is None-guarded.
"""
from datetime import datetime, timedelta

from p6_period.progress import _fmt

_MILESTONES = ('StartMilestone', 'FinishMilestone')


def schedule_adherence(matched, dd_prev, dd_now):
    """Baseline-execution / hit-rate: of the activities the PREVIOUS update forecast to
    finish in this window (and weren't already done), how many actually finished.
    {'planned', 'hit', 'pct', 'missed'} — pct is None when nothing was due; `missed` lists
    the due activities that are still open ({id, name, due, finish_now}, earliest due first)."""
    planned = hit = 0
    missed = []
    if not (dd_prev and dd_now):
        return {'planned': 0, 'hit': 0, 'pct': None, 'missed': []}
    for code in matched.matched_codes:
        b = matched.baseline_by_code.get(code, {})
        u = matched.update_by_code.get(code, {})
        if b.get('task_type') in _MILESTONES:
            continue
        if (b.get('percent_complete') or 0.0) >= 1.0:          # already finished last period
            continue
        bf = b.get('remaining_early_finish') or b.get('planned_finish')
        if not bf or not (dd_prev < bf <= dd_now):             # not forecast to finish this window
            continue
        planned += 1
        if (u.get('percent_complete') or 0.0) >= 1.0:
            hit += 1
        else:
            uf = u.get('remaining_early_finish') or u.get('planned_finish')
            missed.append((bf, {'id': u.get('id') or b.get('id') or code,
                                'name': u.get('name') or b.get('name') or '',
                                'due': _fmt(bf), 'finish_now': _fmt(uf) if uf else '',
                                'pct': round(100.0 * (u.get('percent_complete') or 0.0), 1)}))
    missed.sort(key=lambda x: (x[0], str(x[1]['id'])))
    return {'planned': planned, 'hit': hit,
            'pct': round(100.0 * hit / planned, 1) if planned else None,
            'missed': [m for _d, m in missed]}


def _baseline_project_finish(data):
    """Baseline finish of the project — the finish-milestone's baseline finish, else the
    latest baseline finish across activities. From the update's embedded baseline."""
    bl = getattr(data, 'baseline_by_id', {}) or {}
    fins, fm_fins = [], []
    for act in getattr(data, 'activities', {}).values():
        bf = (bl.get(act.get('id')) or {}).get('planned_finish')
        if bf:
            fins.append(bf)
            if act.get('task_type') == 'FinishMilestone':
                fm_fins.append(bf)
    if fm_fins:
        return max(fm_fins)
    return max(fins) if fins else None


_WEEK = {'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'}


def rate_calendar(data):
    """The calendar the rate of progress is counted on: the one most activities run on (the
    project default when none is assigned). None when the file carries no usable calendar —
    the rate then falls back to calendar days."""
    cals = getattr(data, 'calendars', None) or {}
    usable = lambda c: c is not None and not (set(getattr(c, 'nonworking_days', None) or ()) >= _WEEK)
    count = {}
    for a in (getattr(data, 'activities', None) or {}).values():
        cid = a.get('calendar_id')
        if cid in cals and usable(cals[cid]):
            count[cid] = count.get(cid, 0) + 1
    if count:
        return cals[max(count, key=count.get)]
    cal = cals.get((getattr(data, 'project', None) or {}).get('default_calendar_id'))
    return cal if usable(cal) else None


def _date(d):
    return d.date() if isinstance(d, datetime) else d


def work_days(cal, start, end):
    """Working days after `start` up to and including `end` (calendar days when cal is None)."""
    start, end = _date(start), _date(end)
    if cal is None:
        return (end - start).days
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if cal.is_working_day(d):
            n += 1
    return n


def shift_work_days(cal, start, n):
    """The day reached n working days after `start` (n calendar days when cal is None)."""
    if cal is None:
        return start + timedelta(days=n)
    d, done, guard = start, 0, 0
    while done < n and guard < 40000:
        d += timedelta(days=1)
        guard += 1
        if cal.is_working_day(_date(d)):
            done += 1
    return d


def recovery_outlook(prev, curr, summary):
    """Indicative recovery projection: at this period's earned rate, when does the project
    land — and what rate would it take to still hit the baseline finish?

    The rate is counted on WORKING days (rate_calendar): what was earned ÷ the working days
    between the two data dates, then carried forward over working days only — non-working
    days and holidays earn nothing and are skipped."""
    dd_prev = (getattr(prev, 'project', {}) or {}).get('data_date')
    dd_now = (getattr(curr, 'project', {}) or {}).get('data_date')
    actual_now = summary.get('actual_now') or 0.0
    work_remaining = round(100.0 - actual_now, 1)
    current_rate = summary.get('period_earned')
    period_forecast = summary.get('period_forecast')
    window_days = (dd_now - dd_prev).days if (dd_prev and dd_now and dd_now > dd_prev) else None

    cal = rate_calendar(curr) if window_days else None
    wd = work_days(cal, dd_prev, dd_now) if window_days else None
    if cal is not None and not wd:          # no working day in the period on that calendar
        cal, wd = None, window_days

    out = {'work_days': wd, 'calendar_days': window_days, 'calendar_name': getattr(cal, 'name', None) if cal else None,
           'work_remaining': work_remaining, 'current_rate': current_rate,
           'projected_finish': None, 'baseline_finish': None, 'required_rate': None,
           'required_achievement': None, 'feasible': None, 'note': ''}

    if current_rate and current_rate > 0 and window_days:
        windows_needed = work_remaining / current_rate
        ev_var, bac, ev_now = summary.get('ev_variance'), summary.get('bac'), summary.get('ev_now')
        if summary.get('pct_basis') == 'cost' and (ev_var or 0) > 0 and bac and ev_now is not None:
            windows_needed = max(0.0, bac - ev_now) / ev_var        # the money itself, not the rounded %
        out['days_needed'] = round(windows_needed * wd)
        out['projected_finish'] = _fmt(shift_work_days(cal, dd_now, out['days_needed']))
    elif current_rate is not None and current_rate <= 0:
        out['note'] = 'No progress earned this period — a landing date can’t be projected.'

    bl_fin = _baseline_project_finish(curr)
    out['baseline_finish'] = _fmt(bl_fin)
    if bl_fin and window_days:
        if bl_fin <= dd_now:
            out['note'] = (out['note'] + ' The baseline finish has already passed.').strip()
            out['feasible'] = False
        else:
            out['work_days_to_baseline'] = work_days(cal, dd_now, bl_fin)
            windows_to_bl = out['work_days_to_baseline'] / wd
            if windows_to_bl > 0:
                out['required_rate'] = round(work_remaining / windows_to_bl, 1)
                if period_forecast and period_forecast > 0:
                    out['required_achievement'] = round(out['required_rate'] / period_forecast, 2)
                if current_rate is not None:
                    out['feasible'] = current_rate >= out['required_rate']
    return out


def _slipped_predecessors(matched, curr):
    """Activity IDs that follow an activity whose finish slipped this period. Best-effort —
    an empty set when there is no previous update to compare or the logic cannot be read."""
    if matched is None:
        return set()
    try:
        from p6_audit.graph import ScheduleGraph
        from p6_period.movement import finish_slip
        slipped = {c for c, v in finish_slip(matched).items() if v and v > 0}
        acts = getattr(curr, 'activities', {}) or {}
        graph = ScheduleGraph(curr)
        out = set()
        for oid, a in acts.items():
            for lk in graph.preds_of(oid):
                p = acts.get(lk.get('other'))
                if p and p.get('id') in slipped:
                    out.add(a.get('id'))
                    break
        return out
    except Exception:
        return set()


def _watch_reason(code, fl, threshold, prev_by_code, after_slip):
    if fl <= 0:
        return 'On the critical path' + ('' if fl == 0 else f' (Total Float {round(fl, 1)} wd)')
    pf = (prev_by_code.get(code) or {}).get('total_float_days')
    if pf is not None and pf > threshold:
        return f'Float dropped to {round(fl, 1)} wd this period (was {round(pf, 1)})'
    if code in after_slip:
        return f'Follows an activity that slipped this period ({round(fl, 1)} wd float)'
    return f'Near-critical ({round(fl, 1)} wd float)'


def watch_list(curr, threshold=10.0, limit=8, matched=None):
    """Near-critical, not-yet-finished activities (float ≤ threshold wd) that will drive
    the next window — sorted tightest float first. {'rows': [...]}

    `reason` says why each one is listed: on the critical path, its float dropped to the
    threshold or less in this period, or it follows an activity that slipped this period
    (the last two need `matched` — the previous update)."""
    after_slip = _slipped_predecessors(matched, curr)
    prev_by_code = getattr(matched, 'baseline_by_code', None) or {}
    try:
        from p6_compare.report import _construction_codes
        cons = _construction_codes(curr) or None    # empty detection → don't filter everything out
    except Exception:
        cons = None
    rows = []
    for act in getattr(curr, 'activities', {}).values():
        code = act.get('id')
        if not code or act.get('task_type') in _MILESTONES:
            continue
        if cons is not None and code not in cons:
            continue
        if (act.get('percent_complete') or 0.0) >= 1.0:
            continue
        fl = act.get('total_float_days')
        if fl is None or fl > threshold:
            continue
        start = act.get('remaining_early_start') or act.get('planned_start')
        rows.append({'activity_id': code, 'activity_name': act.get('name', ''),
                     'float_days': round(fl, 1), 'due_to_start': _fmt(start),
                     'reason': _watch_reason(code, fl, threshold, prev_by_code, after_slip),
                     'codes': act.get('activity_codes') or {},   # for export code columns
                     'wbs': (act.get('wbs_path') or '').split(' > ')[-1].strip() or '(no WBS)',
                     '_start': start})
    rows.sort(key=lambda r: (r['float_days'], r['_start'] or datetime.max))
    for r in rows:
        r.pop('_start', None)
    return {'rows': rows[:limit]}
