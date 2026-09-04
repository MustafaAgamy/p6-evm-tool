"""Whole-day Durations module (V2 Schedule Health Review).

Flags real activities whose planned duration is not a whole number of working
days on the activity's own calendar (e.g. 9.41 days). A decimal duration usually
means a duration typed in hours, or a calendar whose hours-per-day differs from
the one used to size the work — either way the plan reads cleaner when durations
land on whole days. The fix is a round to the nearest whole day; the calendar is
left untouched.

Score from the decimal % on the uniform Schedule Health curve
(score = 100 − defect%, uniform grade legend).
"""
from p6_audit.findings import content_id
from p6_audit.scoring import linear_score, uniform_grade

MODULE = 'whole_day'
NAME = 'Whole-day Durations'


def _num(v):
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else f'{f:g}'
    except (TypeError, ValueError):
        return str(v)


def _classify(pd, cal, day_hours, duration_days):
    """Evidence-graded cause of the decimal duration — WHERE it comes from and WHY.
    Returns (cause_key, cause_label, evidence, root_cause, recommendation). The
    calendar is only blamed when the numbers support it; otherwise it is a typed
    part-hours value, or the cause cannot be determined from the file."""
    rounds = int(round(duration_days))
    if cal is None:
        return ('nd', 'Not determinable',
                'No calendar could be resolved for this activity, so its Hours/Day is unknown.',
                'Cause not determinable from available schedule data.',
                'Confirm the activity’s assigned calendar in P6, then re-run this check.')
    dh = _num(day_hours)
    pd_whole_hours = abs(pd - round(pd)) <= 0.01
    at8 = pd / 8.0
    whole_at_8 = abs(at8 - round(at8)) <= 0.01
    dd = _num(round(duration_days, 2))
    if abs(day_hours - 8.0) > 0.01 and pd_whole_hours and whole_at_8:
        return ('cal', 'Calendar hrs/day',
                f'Planned {_num(pd)} h ÷ this calendar’s {dh} h/day = {dd} d; {_num(pd)} h is a clean '
                f'{round(at8)} days at 8 h/day.',
                f'Sized for 8-hour days but assigned a {dh} h/day calendar, so P6 stores a decimal.',
                f'Reassign to the 8 h/day project calendar (→ {round(at8)} d), or confirm {dh} h/day and round to {rounds} d.')
    if not pd_whole_hours:
        return ('entry', 'Part-hours entry',
                f'Planned {_num(pd)} h ÷ {dh} h/day = {dd} d — {_num(pd)} h is not a whole number of hours.',
                'The duration was typed in part-hours — a data-entry value, not a calendar effect.',
                f'Round to {rounds} whole days ({rounds * (day_hours or 8):g} h). No calendar change needed.')
    return ('entry', 'Part-hours entry',
            f'Planned {_num(pd)} h ÷ {dh} h/day = {dd} d — whole hours, but not a whole number of days on this calendar.',
            'Whole hours but not whole days — likely typed in hours rather than days.',
            f'Round to the nearest whole day ({rounds} d).')


def run_whole_day(graph, config):
    findings = []
    real = [(oid, a) for oid, a in graph.activities.items() if graph.is_real_activity(oid)]
    total = len(real)
    decimal_count = 0

    for oid, act in real:
        pd = act.get('planned_duration')
        if not pd:                       # no (or zero) planned duration → nothing to round
            continue
        cal = graph.calendars.get(act.get('calendar_id'))
        day_hours = cal.day_hours if (cal and getattr(cal, 'day_hours', None)) else 8.0
        duration_days = pd / day_hours
        if abs(duration_days - round(duration_days)) <= 0.01:
            continue                     # already a whole day → clean
        decimal_count += 1
        cause, cause_label, evidence, root_cause, recommendation = _classify(pd, cal, day_hours, duration_days)
        findings.append({
            'finding_id':     content_id('WHOLEDAY', act['id'], 'decimal'),
            'activity_id':    act['id'],
            'activity_name':  act.get('name', ''),
            'wbs_path':       graph.wbs_path(oid),
            'original_days':  round(duration_days, 2),
            'rounds_to':      int(round(duration_days)),
            'calendar_id':    act.get('calendar_id'),
            'calendar':       getattr(cal, 'name', None) or act.get('calendar_id') or '(unresolved)',
            'day_hours':      round(day_hours, 2) if cal else None,
            'planned_hours':  round(pd, 2),
            'cause':          cause,          # 'cal' | 'entry' | 'nd'
            'cause_label':    cause_label,
            'evidence':       evidence,
            'root_cause':     root_cause,
            'impact':         'A fractional day that shifts this activity’s finish and rolls up through the WBS date math.',
            'severity':       'High' if act.get('is_critical') else 'Medium',
            'recommendation': recommendation,
        })

    defect_pct = round(100.0 * decimal_count / total, 1) if total else 0.0
    score = linear_score(defect_pct)

    order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    findings.sort(key=lambda f: (order.get(f['severity'], 9), f['activity_id']))

    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'total_activities': total,
            'decimal_count':    decimal_count,
            'decimal_pct':      defect_pct,
        },
        'pct':   defect_pct,
        'score': score,
        'grade': uniform_grade(score),
        'findings': findings,
        'wbs_summary': [],
    }
