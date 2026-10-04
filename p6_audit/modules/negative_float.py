"""Negative Float module (Schedule Health Review).

A baseline must not start with negative float: total float must be >= 0.
One row per REAL activity whose total float is negative. Score on the
Schedule Health Review model (score = 100 - defect%, uniform legend).
"""
from p6_audit.findings import content_id
from p6_audit.scoring import linear_score, uniform_grade

MODULE = 'negative_float'
NAME = 'Negative Float'

_RECOMMENDATION = ('Recover the driving path - a baseline must not start with '
                   'negative float (total float must be >= 0)')


def run_negative_float(graph, config):
    # P6's counts (comment 52): every activity type, the % over the activities not completed
    total = len(graph.p6_all())
    remaining = graph.p6_remaining()

    findings = []
    for oid, act in remaining:
        tf = act.get('total_float_days')
        if tf is None or tf >= 0:
            continue
        findings.append({
            'finding_id':       content_id('NEGFLOAT', act['id'], 'neg'),
            'activity_id':      act['id'],
            'activity_name':    act.get('name', ''),
            'wbs_path':         graph.wbs_path(oid),
            'total_float_days': round(tf, 1),
            'severity':         'Critical',
            'recommendation':   _RECOMMENDATION,
        })

    negative = len(findings)
    pct = round(100.0 * negative / len(remaining), 1) if remaining else 0.0

    findings.sort(key=lambda f: (f['total_float_days'], f['activity_id']))

    score = linear_score(pct)
    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'total_activities': total,                 # every activity, completed included
            'remaining_activities': len(remaining),    # Not Started + In Progress (the % base)
            'negative_count':   negative,
            'neg_pct':          pct,
        },
        'pct':   pct,
        'score': score,
        'grade': uniform_grade(score),
        'findings': findings,
    }
