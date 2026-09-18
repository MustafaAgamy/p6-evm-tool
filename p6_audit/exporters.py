"""Per-module Excel column mappings. Each module exports only its own findings."""

from p6_evm.xlsx_writer import RichText


def excel_highlight_cols(headers):
    """No column-level fill highlight is used any more. The driving predecessor is highlighted
    IN-cell — a bold amber run inside the Baseline Predecessors cell (see excel_columns), the
    closest Excel can do to the on-screen highlighted row — so no whole column is filled. Kept
    (returning []) because server.py still passes its result to write_xlsx(highlight_cols=...)."""
    return []


def excel_severity_meta(module_result, headers):
    """(severity_col_index, legend) for the colour-coded Severity column + its legend — for the
    Out-of-Sequence export; (None, None) for other modules so their exports are unchanged. The
    near-critical band reflects the configured ``near_critical_days`` (not a hardcoded 10)."""
    if module_result.get('module') != 'out_of_sequence' or 'Severity' not in headers:
        return None, None
    near = ((module_result.get('kpis') or {}).get('near_critical_days')) or 10
    legend = [
        ('Critical', 'On the critical path (total float <= 0)'),
        ('High', f'Near-critical (0 < total float <= {near} working days)'),
        ('Medium', 'Has float - not near-critical'),
    ]
    return headers.index('Severity'), legend


def _impact_str(v):
    return f'{v}×' if v is not None else '—'


def filter_lag_findings(module_result, visible_keys):
    """Narrow a module's findings to those whose `rel_key` is in `visible_keys`,
    preserving order — the on-screen filter's request to the exporters. `visible_keys`
    is None when the user has no active filter, in which case `module_result` is
    returned unchanged (identity, no copy).

    Only `findings` narrows: `kpis` / `wbs_summary` are left untouched so charts and
    KPI tiles stay whole-schedule even when the register/Excel rows are filtered.
    Generic (keys off `rel_key`, not module-specific) but only used for lag_lead
    today. Never mutates the input dict."""
    if visible_keys is None:
        return module_result
    keys = set(visible_keys)
    out = dict(module_result)
    out['findings'] = [f for f in module_result.get('findings', []) if f.get('rel_key') in keys]
    return out


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
        def _rel_items(items, single_id, single_name, single_label):
            # ALL ties (driving one flagged), or a single one synthesised from the flat fields.
            return items if items else ([{'id': single_id, 'name': single_name,
                                          'label': single_label, 'affected': True}] if single_id else [])

        def _rel_line(p):
            return (f"{p.get('id','')}  {p.get('label','')}"
                    f"{'  [Driving]' if p.get('affected') else ''}  —  {p.get('name','')}")

        def _rel_lines(items, single_id, single_name, single_label, fallback):
            # Plain multi-line text (successors): the affected tie carries a " [Driving]" tag.
            lst = _rel_items(items, single_id, single_name, single_label)
            if not lst:
                return fallback
            return '\n'.join(_rel_line(p) for p in lst)

        def _pred_rich(f):
            # Baseline Predecessors as a RichText cell: the driving predecessor line is bold +
            # amber-brown (FF92400E), the rest plain — the closest Excel can do to the on-screen
            # highlighted row. Lines are joined by a newline (the cell wraps).
            lst = _rel_items(f.get('all_predecessors'), f.get('pred_id'),
                             f.get('pred_name'), f.get('pred_baseline_label'))
            if not lst:
                return 'No predecessor'
            runs = []
            for k, p in enumerate(lst):
                text = ('\n' if k else '') + _rel_line(p)
                if p.get('affected'):
                    runs.append({'t': text, 'b': True, 'color': 'FF92400E'})
                else:
                    runs.append({'t': text, 'b': False, 'color': None})
            return RichText(runs)

        def _after_pred(f):
            # Mirror the on-screen After-Predecessor cell, incl. the "Remaining predecessors: N"
            # sub-note shown there for an auto-remove.
            lbl = f.get('pred_after_label', '')
            if (f.get('pred_resolution') or {}).get('action') == 'remove' \
                    and f.get('remaining_preds') is not None:
                lbl = f"{lbl}  (remaining predecessors: {f['remaining_preds']})"
            return lbl

        # The on-screen columns EXACTLY (minus the last two — Resolution and the plain Severity),
        # then a colour-coded Severity (with a legend). The driving predecessor is no longer a
        # separate column — it is highlighted in-cell inside Baseline Predecessors (bold amber).
        headers = ['#', 'Activity ID', 'Activity Name',
                   'Baseline Predecessors', 'Baseline Successors', 'Data Date',
                   'After Predecessor Tie', 'After Successor Tie', 'Severity']
        rows = [[
            i, f.get('activity_id', ''), f.get('activity_name', ''),
            _pred_rich(f),
            _rel_lines(f.get('all_successors'), f.get('succ_id'), f.get('succ_name'),
                       f.get('succ_baseline_label'), 'No successor'),
            cutoff,
            _after_pred(f), f.get('succ_after_label', ''),
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
