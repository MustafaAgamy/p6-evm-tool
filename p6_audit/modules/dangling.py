"""Dangling Activities module (V2).

Primavera dangling definition, absorbing the old Open Ends check:
  * Dangling Start  = the start is not driven by an FS or SS predecessor
                      (includes activities with no predecessor at all).
  * Dangling Finish = the finish does not drive an FS or FF successor
                      (includes activities with no successor at all).
One merged row per activity. Score from Dangling % on the agreed curve.
"""
from p6_audit.findings import content_id, bump_severity
from p6_audit.scoring import module_score, grade_for_pct

MODULE = 'dangling'
NAME = 'Dangling Activities'

_FIX = {
    'Dangling Start':          'Add an FS predecessor.',
    'Dangling Finish':         'Assign an FS successor.',
    'Dangling Start + Finish': 'Add FS predecessor & successor.',
}


def _edge_str(graph, edges, empty):
    if not edges:
        return empty
    parts = []
    for e in edges:
        other = graph.activities.get(e['other'], {})
        parts.append(f"{other.get('id', '?')} - {other.get('name', '')} ({e.get('type', 'FS')})")
    return '; '.join(parts)


def run_dangling(graph, config):
    findings = []
    real = [(oid, a) for oid, a in graph.activities.items() if graph.is_real_activity(oid)]
    start_n = finish_n = both_n = 0

    for oid, act in real:
        preds = graph.preds_of(oid)
        succs = graph.succs_of(oid)
        start_dangling = not any(e['type'] in ('FS', 'SS') for e in preds)
        finish_dangling = not any(e['type'] in ('FS', 'FF') for e in succs)
        if not (start_dangling or finish_dangling):
            continue

        if start_dangling and finish_dangling:
            issue, base = 'Dangling Start + Finish', 'High'
            both_n += 1
        elif start_dangling:
            issue, base = 'Dangling Start', 'Medium'
            start_n += 1
        else:
            issue, base = 'Dangling Finish', 'Medium'
            finish_n += 1

        severity = bump_severity(base) if act.get('is_critical') else base
        findings.append({
            'finding_id':    content_id('DANGLING', act['id'], issue),
            'activity_id':   act['id'],
            'activity_name': act.get('name', ''),
            'wbs_path':      graph.wbs_path(oid),
            'severity':      severity,
            'logic_issue':   issue,
            'predecessors':  _edge_str(graph, preds, 'No Predecessor'),
            'successors':    _edge_str(graph, succs, 'No Successor'),
            'suggested_fix': _FIX[issue],
            'is_critical':   bool(act.get('is_critical')),
        })

    total = len(real)
    dangling = len(findings)
    pct = round(100.0 * dangling / total, 1) if total else 0.0

    order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    findings.sort(key=lambda f: (order.get(f['severity'], 9), f['activity_id']))

    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'total_activities': total,
            'total_dangling':   dangling,
            'start_dangling':   start_n,
            'finish_dangling':  finish_n,
            'both_dangling':    both_n,
            'dangling_pct':     pct,
        },
        'pct':   pct,
        'score': module_score(pct),
        'grade': grade_for_pct(pct),
        'findings': findings,
        'wbs_summary': [],
    }
