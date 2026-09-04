"""Hard Constraints module (Schedule Health Review).

A HARD constraint overrides schedule logic: the dates are pinned regardless of
what the predecessors say, so slippage upstream cannot flow through. One row per
real activity carrying a hard constraint. Score from the hard-constraint defect %
on the uniform Schedule Health curve.

  HARD (flagged): Mandatory Start, Mandatory Finish, Start On, Finish On
  SOFT (ignored): Start On or After/Before, Finish On or After/Before,
                  As Late As Possible
"""
from p6_audit.findings import content_id
from p6_audit.scoring import linear_score, uniform_grade

MODULE = 'hard_constraints'
NAME = 'Hard Constraints'

HARD_TYPES = {'Mandatory Start', 'Mandatory Finish', 'Start On', 'Finish On'}
_MANDATORY = {'Mandatory Start', 'Mandatory Finish'}

_RECOMMENDATION = 'Replace with logic where a predecessor drives the date, or justify it'


def run_hard_constraints(graph, config):
    real = [(oid, a) for oid, a in graph.activities.items() if graph.is_real_activity(oid)]
    total = len(real)

    findings = []
    by_type = {}
    for oid, act in real:
        ctype = act.get('constraint_type')
        if ctype not in HARD_TYPES:
            continue
        by_type[ctype] = by_type.get(ctype, 0) + 1

        if act.get('is_critical'):
            severity = 'Critical'
        elif ctype in _MANDATORY:
            severity = 'High'
        else:
            severity = 'Medium'

        findings.append({
            'finding_id':      content_id('HARDCON', act['id'], ctype),
            'activity_id':     act['id'],
            'activity_name':   act.get('name', ''),
            'wbs_path':        graph.wbs_path(oid),
            'constraint_type': ctype,
            'constraint_date': act.get('constraint_date'),
            'severity':        severity,
            'recommendation':  _RECOMMENDATION,
        })

    hard_count = len(findings)
    pct = round(100.0 * hard_count / total, 1) if total else 0.0

    order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    findings.sort(key=lambda f: (order.get(f['severity'], 9), f['activity_id']))

    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'total_activities': total,
            'hard_count':       hard_count,
            'hard_pct':         pct,
            'by_type':          by_type,
        },
        'pct':   pct,
        'score': linear_score(pct),
        'grade': uniform_grade(linear_score(pct)),
        'findings': findings,
        'wbs_summary': [],
    }
