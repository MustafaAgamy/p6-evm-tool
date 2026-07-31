from p6_audit.findings import Finding, resolve_severity


def check_open_ends(graph, config):
    findings = []
    for oid, act in graph.activities.items():
        if not graph.is_real_activity(oid):
            continue
        is_crit = bool(act.get('is_critical'))
        cat = act.get('category')
        if not graph.preds_of(oid):
            findings.append(Finding(
                check_id='LOGIC-001', check_name='Open Ends', category=cat,
                severity=resolve_severity('Medium', cat, is_crit, config),
                activity_id=act['id'], activity_name=act['name'],
                wbs_path=graph.wbs_path(oid),
                summary='Missing predecessor — start date is not logically driven',
                basis='predecessor_count = 0',
                recommendation='Connect this activity to its true preceding work with a Finish-to-Start relationship.',
            ))
        if not graph.succs_of(oid):
            findings.append(Finding(
                check_id='LOGIC-001', check_name='Open Ends', category=cat,
                severity=resolve_severity('High', cat, is_crit, config),
                activity_id=act['id'], activity_name=act['name'],
                wbs_path=graph.wbs_path(oid),
                summary='Missing successor — nothing depends on this activity finishing',
                basis='successor_count = 0',
                recommendation='Connect this activity to its true downstream work with a Finish-to-Start relationship.',
            ))
    return findings
