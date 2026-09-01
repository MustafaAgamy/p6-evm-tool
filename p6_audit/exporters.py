"""Per-module Excel column mappings. Each module exports only its own findings."""


def _impact_str(v):
    return f'{v}×' if v is not None else '—'


def excel_columns(module_result):
    """Return (headers, rows) for the module's findings — full detail for Excel."""
    module = module_result.get('module')
    findings = module_result.get('findings', [])

    if module == 'out_of_sequence':
        cutoff = module_result.get('kpis', {}).get('data_date', '')
        # LOG format: Baseline (Predecessor · Rel · Successor · Rel) vs After Modification.
        headers = ['#', 'Activity ID', 'Activity Name',
                   'Baseline Predecessor', 'Baseline Pred. Rel.',
                   'Baseline Successor', 'Baseline Succ. Rel.', 'Data Date',
                   'After Predecessor', 'After Pred. Rel.',
                   'After Successor', 'After Succ. Rel.', 'Severity']
        rows = [[
            i, f.get('activity_id', ''), f.get('activity_name', ''),
            f.get('pred_name', ''), f.get('pred_baseline_label', ''),
            (f.get('succ_name', '') or ('No successor' if not f.get('succ_id') else '')),
            f.get('succ_baseline_label', ''), cutoff,
            f.get('pred_name', ''), f.get('pred_after_label', ''),
            (f.get('succ_name', '') if f.get('succ_id') else ''), f.get('succ_after_label', ''),
            f.get('severity', 'Medium'),
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
