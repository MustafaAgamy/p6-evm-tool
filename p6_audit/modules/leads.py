"""Leads module (Schedule Health Review).

A lead is a relationship with a NEGATIVE lag (lag_days < 0): the successor is
allowed to start (or finish) before its predecessor, overlapping work that the
network does not otherwise model. DCMA flags leads as a schedule-integrity
defect — they distort the critical path and hide real durations.

One finding per lead edge, keyed on the successor. Defect % = leads / all
relationships; score = 100 - defect% on the uniform Schedule Health curve.
"""
from p6_audit.findings import content_id
from p6_audit.scoring import linear_score, uniform_grade

MODULE = 'leads'
NAME = 'Leads'

RECOMMENDATION = 'Remove the lead, or model the real overlap as its own activity'


def run_leads(graph, config):
    findings = []
    total_rels = 0

    # Enumerate every relationship once: each successor edge is one
    # predecessor(oid) -> successor(edge['other']) link.
    for oid, act in graph.activities.items():
        for edge in graph.succs_of(oid):
            total_rels += 1
            lag = edge.get('lag_days', 0.0)
            if lag >= 0:
                continue  # not a lead

            succ_id = edge['other']
            succ = graph.activities.get(succ_id, {})
            severity = 'Critical' if succ.get('is_critical') else 'High'
            findings.append({
                'finding_id':      content_id('LEAD', succ.get('id', succ_id), str(lag)),
                'activity_id':     succ.get('id', succ_id),
                'activity_name':   succ.get('name', ''),
                'predecessor_id':  act.get('id', oid),
                'predecessor_name': act.get('name', ''),
                'rel_type':        edge.get('type', 'FS'),
                'lag_days':        lag,
                'wbs_path':        graph.wbs_path(succ_id),
                'severity':        severity,
                'recommendation':  RECOMMENDATION,
            })

    leads = len(findings)
    pct = round(100.0 * leads / total_rels, 1) if total_rels else 0.0

    order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    findings.sort(key=lambda f: (order.get(f['severity'], 9), f['activity_id']))

    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'total_relationships': total_rels,
            'leads':               leads,
            'lead_pct':            pct,
            'target':              0,
        },
        'pct':   pct,
        'score': linear_score(pct),
        'grade': uniform_grade(linear_score(pct)),
        'findings': findings,
    }
