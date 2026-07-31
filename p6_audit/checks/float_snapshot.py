from collections import Counter
from p6_audit.findings import Finding, resolve_severity


def check_float(graph, config):
    threshold = config.get('audit', {}).get('float_threshold_days', 44)
    findings = []
    real = [(oid, a) for oid, a in graph.activities.items() if graph.is_real_activity(oid)]

    # Negative float — per activity
    for oid, act in real:
        tf = act.get('total_float_days')
        if tf is None:
            continue
        if tf < 0:
            cat = act.get('category')
            findings.append(Finding(
                check_id='FLOAT-001', check_name='Float Analysis', category=cat,
                severity=resolve_severity('High', cat, bool(act.get('is_critical')), config),
                activity_id=act['id'], activity_name=act['name'], wbs_path=graph.wbs_path(oid),
                summary='Negative float — activity is behind the schedule need date',
                basis=f'total_float = {tf:g} working days',
                recommendation='Investigate the driving logic or delay; negative float means the finish milestone is threatened.',
            ))

    # Excessive float — one summary finding
    counted = [(oid, a) for oid, a in real if a.get('total_float_days') is not None]
    total = len(counted)
    over = [(oid, a) for oid, a in counted if a['total_float_days'] > threshold]
    if over and total:
        pct = 100.0 * len(over) / total
        wbs_counts = Counter(graph.wbs_path(oid) or '(no WBS)' for oid, _ in over)
        worst_wbs, worst_n = wbs_counts.most_common(1)[0]
        findings.append(Finding(
            check_id='FLOAT-001', check_name='Float Analysis', category=None,
            severity=resolve_severity('Medium', None, False, config),
            activity_id='—', activity_name='(project-wide)', wbs_path=worst_wbs,
            summary='Excessive float — a large share of activities exceed the float threshold',
            basis=f'{len(over)} of {total} activities ({pct:.1f}%) with total float > {threshold} working days',
            recommendation=f'Review logic in "{worst_wbs}" ({worst_n} activities over threshold) — high float usually means missing successors.',
        ))
    return findings
