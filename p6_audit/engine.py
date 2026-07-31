from p6_evm.parser import full_wbs_path
from p6_evm.metrics import classify_activity
from p6_audit.graph import ScheduleGraph
from p6_audit.findings import SEVERITY_ORDER
from p6_audit.checks.open_ends import check_open_ends
from p6_audit.checks.dangling import check_dangling
from p6_audit.checks.circular import check_circular
from p6_audit.checks.float_snapshot import check_float
from p6_audit.scoring import score_categories, overall_score

CHECKS = [check_open_ends, check_dangling, check_circular, check_float]


def _enrich(data, config):
    """Ensure each activity has 'category' and 'wbs_path' for the checks."""
    categories = config.get('categories', [])
    wbs_map = getattr(data, 'wbs', {}) or {}
    for act in data.activities.values():
        if 'wbs_path' not in act:
            act['wbs_path'] = full_wbs_path(act.get('wbs_id'), wbs_map)
        if 'category' not in act:
            act['category'] = classify_activity(act, wbs_map, categories)


def audit(data, config):
    _enrich(data, config)
    graph = ScheduleGraph(data)
    findings = []
    for check in CHECKS:
        findings.extend(check(graph, config))

    cats = score_categories(findings, config)
    overall = overall_score(cats)

    rank = {s: i for i, s in enumerate(reversed(SEVERITY_ORDER))}  # Critical -> 0
    findings.sort(key=lambda f: rank.get(f.severity, 99))

    by_sev = {}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1

    return {
        'findings': [f.as_dict() for f in findings],
        'scores': {'categories': cats, 'overall': overall},
        'counts': {'total': len(findings), 'by_severity': by_sev},
    }
