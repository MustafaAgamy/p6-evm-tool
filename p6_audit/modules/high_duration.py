"""High Duration module (V2).

Flags real activities whose planned duration exceeds a day threshold, converted
from planned hours to working days on the activity's own calendar. Long tasks are
hard to track and mask progress — break them up or add progress steps.
Score from High Duration % (over-threshold activities / total activities) on the
Schedule Health Review curve (score = 100 − defect%).
"""
from p6_audit.findings import content_id, bump_severity
from p6_audit.scoring import linear_score, uniform_grade

MODULE = 'high_duration'
NAME = 'High Duration'

RECOMMENDATION = ('Break into shorter, trackable activities, or add progress steps '
                  'if it is genuinely one continuous quantity-driven job')


def run_high_duration(graph, config):
    threshold = config.get('audit', {}).get('duration_threshold_days', 44)
    real = [(oid, a) for oid, a in graph.activities.items() if graph.is_real_activity(oid)]
    total = len(real)

    findings = []
    over = 0
    max_days = 0.0
    for oid, act in real:
        cal = graph.calendars.get(act.get('calendar_id'))
        day_hours = cal.day_hours if (cal and getattr(cal, 'day_hours', None)) else 8.0
        duration_days = (act.get('planned_duration') or 0) / day_hours
        if duration_days > max_days:
            max_days = duration_days
        if duration_days <= threshold:
            continue

        over += 1
        severity = bump_severity('Medium') if act.get('is_critical') else 'Medium'
        findings.append({
            'finding_id':     content_id('HIGHDUR', act['id'], 'long'),
            'activity_id':    act['id'],
            'activity_name':  act.get('name', ''),
            'wbs_path':       graph.wbs_path(oid),
            'duration_days':  round(duration_days, 1),
            'severity':       severity,
            'recommendation': RECOMMENDATION,
            'is_critical':    bool(act.get('is_critical')),
        })

    defect_pct = round(100.0 * over / total, 1) if total else 0.0

    order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    findings.sort(key=lambda f: (order.get(f['severity'], 9), -f['duration_days']))

    pct = defect_pct
    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'total_activities': total,
            'over_threshold':   over,
            'high_pct':         defect_pct,
            'threshold':        threshold,
            'max_duration':     round(max_days, 1) if total else 0,
        },
        'pct':   pct,
        'score': linear_score(pct),
        'grade': uniform_grade(linear_score(pct)),
        'findings': findings,
        'wbs_summary': [],
    }
