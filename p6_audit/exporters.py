"""Per-module Excel column mappings. Each module exports only its own findings."""


def _impact_str(v):
    return f'{v}×' if v is not None else '—'


def excel_columns(module_result):
    """Return (headers, rows) for the module's findings — full detail for Excel."""
    module = module_result.get('module')
    findings = module_result.get('findings', [])

    if module == 'out_of_sequence':
        cutoff = module_result.get('kpis', {}).get('data_date', '')
        headers = ['#', 'Activity ID', 'Activity Name', 'WBS Path',
                   'Current Pred. Rel.', 'Current Predecessor Activity',
                   'Current Succ. Rel.', 'Current Successor Activity', 'Cutoff Date',
                   'Suggested Predecessor', 'Suggested Successor',
                   'Root Cause', 'Planning Review Comment', 'Criticality']
        rows = [[
            i, f.get('activity_id', ''), f.get('activity_name', ''), f.get('wbs_path', ''),
            f.get('current_pred_rel', ''), f.get('current_pred_activity', ''),
            f.get('current_succ_rel', ''), f.get('current_succ_activity', ''), cutoff,
            f.get('suggested_predecessor', ''), f.get('suggested_successor', ''),
            f.get('root_cause', ''), f.get('planning_review_comment', ''), f.get('criticality', ''),
        ] for i, f in enumerate(findings, 1)]
        return headers, rows

    if module == 'lag_lead':
        def _flags(f):
            fl = []
            if f.get('is_lead'):
                fl.append('Lead')
            if f.get('is_long'):
                fl.append('Long')
            if f.get('criticality') == 'Critical':
                fl.append('Critical')
            elif f.get('criticality') == 'Near-Critical':
                fl.append('Near-Critical')
            return ', '.join(fl)
        headers = ['#', 'Activity ID', 'Activity Name', 'Pred. Relationship', 'Pred. Name',
                   'Succ. Relationship', 'Succ. Name', 'Lag (wd)', 'Flags', 'Justification']
        rows = [[
            i, f.get('activity_id', ''), f.get('activity_name', ''),
            f.get('pred_rel', ''), f.get('pred_name', ''),
            f.get('succ_rel', ''), f.get('succ_name', ''),
            f.get('lag_days', ''), _flags(f), f.get('justification', ''),
        ] for i, f in enumerate(findings, 1)]
        return headers, rows

    if module == 'dangling':
        headers = ['#', 'Activity ID', 'Activity Name', 'WBS Path', 'Severity',
                   'Logic Issue', 'Predecessor(s)', 'Successor(s)',
                   'Suggested Logic Fix', 'Suggested Logic Fix 2']
        rows = [[
            i, f.get('activity_id', ''), f.get('activity_name', ''), f.get('wbs_path', ''),
            f.get('severity', ''), f.get('logic_issue', ''), f.get('predecessors', ''),
            f.get('successors', ''), f.get('suggested_fix', ''), f.get('suggested_fix_2', ''),
        ] for i, f in enumerate(findings, 1)]
        return headers, rows

    # float
    headers = ['#', 'Activity ID', 'Activity Name', 'WBS Path', 'Total Float (d)',
               'Threshold (d)', 'Impact', 'Status', 'Severity', 'Reason', 'Engineering Recommendation']
    rows = [[
        i, f.get('activity_id', ''), f.get('activity_name', ''), f.get('wbs_path', ''),
        f.get('total_float_days', ''), f.get('threshold', ''), _impact_str(f.get('impact')),
        f.get('status', ''), f.get('severity', ''), f.get('reason', ''), f.get('recommendation', ''),
    ] for i, f in enumerate(findings, 1)]
    return headers, rows
