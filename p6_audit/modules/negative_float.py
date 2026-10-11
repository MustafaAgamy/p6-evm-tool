"""Negative Float module (Schedule Health Review).

A baseline must not start with negative float: total float must be >= 0.
One row per REAL activity whose total float is negative. Score on the
Schedule Health Review model (score = 100 - defect%, uniform legend).
"""
from p6_audit.findings import content_id
from p6_audit.scoring import linear_score, uniform_grade

MODULE = 'negative_float'
NAME = 'Negative Float'

FRACTION_DAYS = 0.5   # a negative float within half a day is a part-day rounding, not a delay

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
            # as P6 holds it (comment 83): a float of a few hours stays -0.05, never 0
            'total_float_days': round(tf, 2) or round(tf, 4),
            'severity':         'Critical',
            'recommendation':   _RECOMMENDATION,
        })

    negative = len(findings)
    # review comment 9: negative by less than half a day = a decimal (part-day) duration in the
    # baseline, not a delay - counted so the report can say so
    floats = [act['total_float_days'] for _oid, act in remaining
              if act.get('total_float_days') is not None and act['total_float_days'] < 0]
    fraction = sum(1 for tf in floats if tf >= -FRACTION_DAYS)
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
            'hours_basis':      dict(graph.hours_basis),   # how hours become days
            'fraction_count':   fraction,              # negative by no more than half a day
            'fraction_days':    FRACTION_DAYS,
            'most_negative':    (round(min(floats), 2) or round(min(floats), 4)) if floats else None,
        },
        'pct':   pct,
        'score': score,
        'grade': uniform_grade(score),
        'findings': findings,
    }
