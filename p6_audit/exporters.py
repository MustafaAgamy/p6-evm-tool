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

    if module == 'float':
        headers = ['#', 'Activity ID', 'Activity Name', 'WBS Path', 'Total Float (d)',
                   'Threshold (d)', 'Impact', 'Status', 'Severity', 'Reason', 'Engineering Recommendation']
        rows = [[
            i, f.get('activity_id', ''), f.get('activity_name', ''), f.get('wbs_path', ''),
            f.get('total_float_days', ''), f.get('threshold', ''), _impact_str(f.get('impact')),
            f.get('status', ''), f.get('severity', ''), f.get('reason', ''), f.get('recommendation', ''),
        ] for i, f in enumerate(findings, 1)]
        return headers, rows

    # Every other check exports from the single-source presentation — the same
    # columns and cells as the screen and the PDF. WBS exports its full path (the
    # cell carries it as the title; a spreadsheet has no hover), otherwise the cell
    # text, which is already formatted once (N d, %, ISO dates).
    from p6_audit.presentation import build_presentation
    p = module_result.get('presentation') or build_presentation(module_result)
    headers = ['#'] + [c['label'] for c in p.get('columns', [])]
    rows = [[i] + [(cell.get('title') or cell.get('text', '')) for cell in row]
            for i, row in enumerate(p.get('rows', []), 1)]
    return headers, rows
