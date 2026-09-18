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
    {'planned', 'hit', 'pct'} — pct is None when nothing was due."""
    planned = hit = 0
    if not (dd_prev and dd_now):
        return {'planned': 0, 'hit': 0, 'pct': None}
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
    return {'planned': planned, 'hit': hit,
            'pct': round(100.0 * hit / planned, 1) if planned else None}


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


def recovery_outlook(prev, curr, summary):
    """Indicative recovery projection: at this period's earned rate, when does the project
    land — and what rate would it take to still hit the baseline finish?"""
    dd_prev = (getattr(prev, 'project', {}) or {}).get('data_date')
    dd_now = (getattr(curr, 'project', {}) or {}).get('data_date')
    actual_now = summary.get('actual_now') or 0.0
    work_remaining = round(100.0 - actual_now, 1)
    current_rate = summary.get('period_earned')
    period_forecast = summary.get('period_forecast')
    window_days = (dd_now - dd_prev).days if (dd_prev and dd_now and dd_now > dd_prev) else None

    out = {'work_remaining': work_remaining, 'current_rate': current_rate,
           'projected_finish': None, 'baseline_finish': None, 'required_rate': None,
           'required_achievement': None, 'feasible': None, 'note': ''}

    if current_rate and current_rate > 0 and window_days:
        windows_needed = work_remaining / current_rate
        out['projected_finish'] = _fmt(dd_now + timedelta(days=round(windows_needed * window_days)))
    elif current_rate is not None and current_rate <= 0:
        out['note'] = 'No progress earned this period — a landing date can’t be projected.'

    bl_fin = _baseline_project_finish(curr)
    out['baseline_finish'] = _fmt(bl_fin)
    if bl_fin and window_days:
        if bl_fin <= dd_now:
            out['note'] = (out['note'] + ' The baseline finish has already passed.').strip()
            out['feasible'] = False
        else:
            windows_to_bl = (bl_fin - dd_now).days / window_days
            if windows_to_bl > 0:
                out['required_rate'] = round(work_remaining / windows_to_bl, 1)
                if period_forecast and period_forecast > 0:
                    out['required_achievement'] = round(out['required_rate'] / period_forecast, 2)
                if current_rate is not None:
                    out['feasible'] = current_rate >= out['required_rate']
    return out


def watch_list(curr, threshold=10.0, limit=8):
    """Near-critical, not-yet-finished activities (float ≤ threshold wd) that will drive
    the next window — sorted tightest float first. {'rows': [...]}"""
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
                     'reason': 'On the critical path (0 float)' if fl <= 0
                               else f'Near-critical ({round(fl, 1)} wd float)',
                     'codes': act.get('activity_codes') or {},   # for export code columns
                     '_start': start})
    rows.sort(key=lambda r: (r['float_days'], r['_start'] or datetime.max))
    for r in rows:
        r.pop('_start', None)
    return {'rows': rows[:limit]}
