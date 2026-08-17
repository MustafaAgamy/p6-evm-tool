"""Relationship Types module (Schedule Health Review).

A healthy CPM network is driven overwhelmingly by Finish-to-Start logic.
This check enumerates every relationship in the schedule, reports the mix of
FS / SS / FF / SF, and flags each relationship that is NOT Finish-to-Start.
Start-to-Finish is almost always a modelling error, so it is raised at High
severity; the other non-FS types are Medium.

Score = 100 - (share of relationships that are not FS), on the uniform
Schedule Health legend. It diagnoses and recommends — it never edits logic.
"""
from p6_audit.findings import content_id
from p6_audit.scoring import linear_score, uniform_grade

MODULE = 'relationship_types'
NAME = 'Relationship Types'

_SF_REC = 'Start-to-Finish is almost never correct - re-check this relationship'
_OTHER_REC = 'Re-type to FS if the finish drives the successor'


def run_relationship_types(graph, config):
    counts = {'FS': 0, 'SS': 0, 'FF': 0, 'SF': 0}
    findings = []

    # Enumerate ALL relationships: each activity's successor edges, so every
    # relationship (predecessor oid -> successor edge['other']) is seen once.
    for oid in graph.activities:
        pred = graph.activities.get(oid, {})
        for edge in graph.succs_of(oid):
            rel_type = edge.get('type', 'FS')
            counts[rel_type] = counts.get(rel_type, 0) + 1
            if rel_type == 'FS':
                continue
            other = edge['other']
            succ = graph.activities.get(other, {})
            findings.append({
                'finding_id':       content_id('RELTYPE', succ.get('id'), rel_type),
                'activity_id':      succ.get('id'),
                'activity_name':    succ.get('name', ''),
                'predecessor_id':   pred.get('id'),
                'predecessor_name': pred.get('name', ''),
                'rel_type':         rel_type,
                'wbs_path':         graph.wbs_path(other),
                'severity':         'High' if rel_type == 'SF' else 'Medium',
                'recommendation':   _SF_REC if rel_type == 'SF' else _OTHER_REC,
            })

    total = sum(counts.values())

    def _pct(n):
        return round(100.0 * n / total, 1) if total else 0.0

    fs_pct = _pct(counts['FS'])
    ss_pct = _pct(counts['SS'])
    ff_pct = _pct(counts['FF'])
    sf_pct = _pct(counts['SF'])
    defect_pct = round(100 - fs_pct, 1)      # share that is NOT Finish-to-Start
    non_fs = total - counts['FS']

    order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    findings.sort(key=lambda f: (order.get(f['severity'], 9), f['activity_id'] or ''))

    score = linear_score(defect_pct)
    return {
        'module': MODULE,
        'name': NAME,
        'kpis': {
            'total_relationships': total,
            'fs_pct': fs_pct,
            'ss_pct': ss_pct,
            'ff_pct': ff_pct,
            'sf_pct': sf_pct,
            'non_fs': non_fs,
        },
        'pct':   defect_pct,
        'score': score,
        'grade': uniform_grade(score),
        'findings': findings,
        'wbs_summary': [],
    }
