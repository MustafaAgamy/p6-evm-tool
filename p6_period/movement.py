"""Schedule / critical-path movement between two updates.

`finish_slip` measures each activity's forecast-finish movement in working days.
`critical_movement` is the Windows-analysis heart: the critical / near-critical
activities whose finish moved this period (or that newly entered the critical path),
with the driver classified. `buckets` counts what moved: finished / started / slipped
/ stalled / re-sequenced.
"""
from p6_evm.calendars import signed_working_days

NEAR_CRITICAL_WD = 10          # float <= 10 working days = near-critical (repo convention)
_MILESTONES = ('StartMilestone', 'FinishMilestone')


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


def critical_movement(matched, logic_changed_codes=frozenset()):
    """{'rows': [...], 'new_critical': n} — near-critical activities (float <= 10 wd)
    whose finish slipped this period, or that newly entered the critical path.

    Row: activity_id, activity_name, prev_finish, curr_finish, slip_days, float_days,
    driver ('logic changed' | 'duration extended' | 'progress shortfall' | 'held'),
    critical_status ('new' | 'stayed'). Sorted by slip descending."""
    slips = finish_slip(matched)
    ucals = getattr(matched.update, 'calendars', {}) or {}
    bcals = getattr(matched.baseline, 'calendars', {}) or {}
    rows, new_critical = [], 0
    for code in matched.matched_codes:
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
            'codes': u.get('activity_codes') or {},   # for the activity-code columns in exports
        })
    rows.sort(key=lambda r: -(r['slip_days'] or 0))
    return {'rows': rows, 'new_critical': new_critical}


def buckets(matched, dd_now=None, logic_changed_codes=frozenset()):
    """{'counts': {...}, 'lists': {...}} — what moved this period, bucketed into
    finished / started / slipped / stalled / re_sequenced. Milestones excluded from the
    progress buckets. `re_sequenced` = activities whose logic/lag changed vs last period."""
    slips = finish_slip(matched)
    counts = {'finished': 0, 'started': 0, 'slipped': 0, 'stalled': 0, 're_sequenced': 0}
    lists = {k: [] for k in counts}
    for code in matched.matched_codes:
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
