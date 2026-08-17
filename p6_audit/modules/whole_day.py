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
        findings.append({
            'finding_id':     content_id('WHOLEDAY', act['id'], 'decimal'),
            'activity_id':    act['id'],
            'activity_name':  act.get('name', ''),
            'wbs_path':       graph.wbs_path(oid),
            'original_days':  round(duration_days, 2),
            'rounds_to':      int(round(duration_days)),
            'calendar':       getattr(cal, 'name', act.get('calendar_id')),
            'severity':       'High' if act.get('is_critical') else 'Medium',
            'recommendation': 'Round to the nearest whole day (no calendar change)',
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
