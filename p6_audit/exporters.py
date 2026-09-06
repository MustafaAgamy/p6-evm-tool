"""Per-module Excel column mappings. Each module exports only its own findings."""

# The Excel column that carries the driving-activity highlight (amber fill) — so the driving
# relationship stands out on export exactly as its [DRIVING] highlight does on screen.
DRIVING_HEADER = 'Driving Activity'

# Severity colour key (matches the on-screen badges + the OOS criticality rule).
OOS_SEVERITY_LEGEND = [
    ('Critical', 'On the critical path (total float <= 0)'),
    ('High', 'Near-critical (0 < total float <= 10 working days)'),
    ('Medium', 'Has float - not near-critical'),
]


def excel_highlight_cols(headers):
    """0-based indices of columns to render with the driving-activity highlight."""
    return [i for i, h in enumerate(headers) if h == DRIVING_HEADER]


def excel_severity_meta(module_result, headers):
    """(severity_col_index, legend) for the colour-coded Severity column + its legend — for the
    Out-of-Sequence export; (None, None) for other modules so their exports are unchanged."""
    if module_result.get('module') != 'out_of_sequence' or 'Severity' not in headers:
        return None, None
    return headers.index('Severity'), OOS_SEVERITY_LEGEND


def _impact_str(v):
    return f'{v}×' if v is not None else '—'


def excel_columns(module_result):
    """Return (headers, rows) for the module's findings — full detail for Excel."""
    module = module_result.get('module')
    findings = module_result.get('findings', [])

    if module == 'out_of_sequence':
        cutoff = module_result.get('kpis', {}).get('data_date', '')
        # LOG format: Baseline lists ALL predecessor/successor ties (driving one marked) vs After
        # Modification (the before→after transition per affected tie). Each Baseline cell is a
        # multi-line list so a multi-predecessor / multi-successor activity shows the full context and
        # exactly WHICH tie was modified.
        def _rel_lines(items, single_id, single_name, single_label, fallback):
            lst = items if items else ([{'id': single_id, 'name': single_name,
                                         'label': single_label, 'affected': True}] if single_id else [])
            if not lst:
                return fallback
            return '\n'.join(
                f"{p.get('id','')}  {p.get('label','')}{'  [Driving]' if p.get('affected') else ''}  —  {p.get('name','')}"
                for p in lst)

        def _driving(f):
            # The driving activity (the OOS cause) — its own amber-highlighted column, so it stands
            # out on export exactly as the [DRIVING] highlight does on screen.
            pid, pname = f.get('pred_id', ''), f.get('pred_name', '')
            if not pid:
                return ''
            return f"{pid} - {pname} · {f.get('pred_after_label', '')}"

        def _after_pred(f):
            # Mirror the on-screen After-Predecessor cell, incl. the "Remaining predecessors: N"
            # sub-note shown there for an auto-remove.
            lbl = f.get('pred_after_label', '')
            if (f.get('pred_resolution') or {}).get('action') == 'remove' \
                    and f.get('remaining_preds') is not None:
                lbl = f"{lbl}  (remaining predecessors: {f['remaining_preds']})"
            return lbl

        # The on-screen columns EXACTLY (minus the last two — Resolution and the plain Severity),
        # then a highlighted Driving Activity column, then a colour-coded Severity (with a legend).
        headers = ['#', 'Activity ID', 'Activity Name',
                   'Baseline Predecessors', 'Baseline Successors', 'Data Date',
                   'After Predecessor Tie', 'After Successor Tie', DRIVING_HEADER, 'Severity']
        rows = [[
            i, f.get('activity_id', ''), f.get('activity_name', ''),
            _rel_lines(f.get('all_predecessors'), f.get('pred_id'), f.get('pred_name'),
                       f.get('pred_baseline_label'), 'No predecessor'),
            _rel_lines(f.get('all_successors'), f.get('succ_id'), f.get('succ_name'),
                       f.get('succ_baseline_label'), 'No successor'),
            cutoff,
            _after_pred(f), f.get('succ_after_label', ''),
            _driving(f), f.get('severity', 'Medium'),
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
