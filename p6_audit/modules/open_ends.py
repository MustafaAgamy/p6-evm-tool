"""Open Ends module (Schedule Health Review).

An open end is a REAL activity that is not tied into the network on at least
one side: it has NO predecessor at all AND/OR NO successor at all. An activity
with no predecessor is free to start immediately; one with no successor drives
nothing downstream — either way the network logic is incomplete.

One row per open-ended activity. Score on the Schedule Health Review model:
score = 100 - Open-End %, with the uniform grade legend.
"""
from p6_audit.findings import content_id, bump_severity
from p6_audit.scoring import linear_score, uniform_grade

MODULE = 'open_ends'
NAME = 'Open Ends'


def run_open_ends(graph, config):
    findings = []
    real = [(oid, a) for oid, a in graph.activities.items() if graph.is_real_activity(oid)]
    no_pred_n = no_succ_n = 0

    for oid, act in real:
        has_pred = bool(graph.preds_of(oid))
        has_succ = bool(graph.succs_of(oid))
        if has_pred and has_succ:
            continue

        if not has_pred:
            no_pred_n += 1
        if not has_succ:
            no_succ_n += 1

        if not has_pred and not has_succ:
            issue, base = 'No predecessor + no successor', 'High'
        elif not has_succ:
            issue, base = 'No successor', 'High'
        else:
            issue, base = 'No predecessor', 'Medium'

        severity = bump_severity(base) if act.get('is_critical') else base
        recommendation = ('Link to its downstream work (FS)' if not has_succ
                          else 'Link from its upstream work (FS)')

        findings.append({
            'finding_id':     content_id('OPENEND', act['id'], issue),
            'activity_id':    act['id'],
            'activity_name':  act.get('name', ''),
            'wbs_path':       graph.wbs_path(oid),
            'severity':       severity,
            'issue':          issue,
            'recommendation': recommendation,
        })

    total = len(real)
    open_ends = len(findings)
    open_end_pct = round(100.0 * open_ends / total, 1) if total else 0.0

    order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    findings.sort(key=lambda f: (order.get(f['severity'], 9), f['activity_id']))

    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'total_activities': total,
            'open_ends':        open_ends,
            'no_predecessor':   no_pred_n,
            'no_successor':     no_succ_n,
            'open_end_pct':     open_end_pct,
        },
        'pct':   open_end_pct,
        'score': linear_score(open_end_pct),
        'grade': uniform_grade(linear_score(open_end_pct)),
        'findings': findings,
    }
