"""Per-module Excel column mappings. Each module exports only its own findings."""


def _impact_str(v):
    return f'{v}×' if v is not None else '—'


def excel_columns(module_result):
    """Return (headers, rows) for the module's findings — full detail for Excel."""
    module = module_result.get('module')
    findings = module_result.get('findings', [])

    if module == 'dangling':
        headers = ['#', 'Activity ID', 'Activity Name', 'WBS Path', 'Severity',
                   'Logic Issue', 'Predecessor(s)', 'Successor(s)', 'Suggested Logic Fix']
        rows = [[
            i, f.get('activity_id', ''), f.get('activity_name', ''), f.get('wbs_path', ''),
            f.get('severity', ''), f.get('logic_issue', ''), f.get('predecessors', ''),
            f.get('successors', ''), f.get('suggested_fix', ''),
        ] for i, f in enumerate(findings, 1)]
        return headers, rows

    # float
    headers = ['#', 'Activity ID', 'Activity Name', 'WBS Path', 'Total Float (d)',
               'Threshold (d)', 'Impact', 'Severity', 'Reason', 'Engineering Recommendation']
    rows = [[
        i, f.get('activity_id', ''), f.get('activity_name', ''), f.get('wbs_path', ''),
        f.get('total_float_days', ''), f.get('threshold', ''), _impact_str(f.get('impact')),
        f.get('severity', ''), f.get('reason', ''), f.get('recommendation', ''),
    ] for i, f in enumerate(findings, 1)]
    return headers, rows
