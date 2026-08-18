from p6_evm.parser import full_wbs_path
from p6_evm.metrics import classify_activity
from p6_audit.graph import ScheduleGraph
from p6_audit.findings import SEVERITY_ORDER
from p6_audit.checks.open_ends import check_open_ends
from p6_audit.checks.dangling import check_dangling
from p6_audit.checks.circular import check_circular
from p6_audit.checks.float_snapshot import check_float
from p6_audit.scoring import score_categories, overall_score
from p6_audit.health import schedule_health
from p6_audit.presentation import build_presentation
from p6_audit.modules.dangling import run_dangling
from p6_audit.modules.float_analysis import run_float
from p6_audit.modules.out_of_sequence import run_out_of_sequence
from p6_audit.modules.lag_lead import run_lag_lead
from p6_audit.modules.open_ends import run_open_ends
from p6_audit.modules.relationship_types import run_relationship_types
from p6_audit.modules.hard_constraints import run_hard_constraints
from p6_audit.modules.high_duration import run_high_duration
from p6_audit.modules.leads import run_leads
from p6_audit.modules.negative_float import run_negative_float
from p6_audit.modules.whole_day import run_whole_day
from p6_audit.modules.circular import run_circular
from p6_audit.modules.cpli import run_cpli

CHECKS = [check_open_ends, check_dangling, check_circular, check_float]

# V2: isolated modules, ordered. Each is fully self-contained (own KPIs, score,
# grade, findings). Overall Schedule Health Score is deferred until all modules
# exist and is then computed from module scores × weights, never from findings.
MODULE_RUNNERS = [
    run_dangling,
    run_float,
    run_out_of_sequence,
    run_lag_lead,
    run_open_ends,
    run_relationship_types,
    run_hard_constraints,
    run_high_duration,
    run_leads,
    run_negative_float,
    run_whole_day,
    run_circular,
    run_cpli,
]


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


def audit_modules(data, config):
    """V2 entry point — isolated per-module results plus the Schedule Health roll-up.

    Returns {'modules': {name: module_result}, 'module_order': [...], 'health': {...}}.
    Every module still scores itself in isolation and can be read on its own exactly
    as before; `health` only combines them (Decision 006).
    """
    _enrich(data, config)
    graph = ScheduleGraph(data)
    modules = {}
    order = []
    for runner in MODULE_RUNNERS:
        result = runner(graph, config)
        # The normalized presentation the screen, PDF and Excel all render from —
        # derived from this result, so it is identical on import and on DB read.
        result['presentation'] = build_presentation(result)
        modules[result['module']] = result
        order.append(result['module'])
    return {'modules': modules, 'module_order': order,
            'health': schedule_health(modules)}
