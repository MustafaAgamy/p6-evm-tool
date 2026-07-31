from p6_audit.findings import Finding, resolve_severity


def check_dangling(graph, config):
    findings = []
    for oid, act in graph.activities.items():
        if not graph.is_real_activity(oid):
            continue
        preds = graph.preds_of(oid)
        succs = graph.succs_of(oid)
        is_crit = bool(act.get('is_critical'))
        cat = act.get('category')

        start_controlled = any(e['type'] in ('FS', 'SS') for e in preds)
        finish_controlled = any(e['type'] in ('FS', 'FF') for e in succs)

        if preds and not start_controlled:
            findings.append(Finding(
                check_id='LOGIC-002', check_name='Dangling Logic', category=cat,
                severity=resolve_severity('High', cat, is_crit, config),
                activity_id=act['id'], activity_name=act['name'],
                wbs_path=graph.wbs_path(oid),
                summary='Start not logically controlled — no Finish-to-Start or Start-to-Start driver',
                basis='activity start has no FS/SS predecessor tie',
                recommendation='Review whether a Finish-to-Start predecessor is needed so the start is driven by real logic.',
            ))
        if succs and not finish_controlled:
            findings.append(Finding(
                check_id='LOGIC-002', check_name='Dangling Logic', category=cat,
                severity=resolve_severity('High', cat, is_crit, config),
                activity_id=act['id'], activity_name=act['name'],
                wbs_path=graph.wbs_path(oid),
                summary='Finish not logically controlled — remaining work floats free after updates',
                basis='activity finish has no FS/FF successor tie',
                recommendation='Review whether a Finish-to-Start successor is needed so completion is controlled.',
            ))
    return findings
