"""Excel (.xlsx) export for Reporting Studio.

Mirrors the Document / Dashboard report as DATA: a leading **Contents** sheet
listing the picked sections in pick order, then **one sheet per result** holding
that result's numbers — the table rows, the KPI values, the bar/line series, the
findings, and so on. This is the data behind the report, so a planner can open the
workbook and work with the figures directly in Excel.

No third-party dependency: everything is composed from the shared pure-Python OOXML
writer in :mod:`p6_evm.xlsx_writer` — :func:`_write_book` (multi-sheet workbook),
:func:`_sheet` (one flat table with a bold frozen header + autofilter),
:func:`_stacked_sheet` (several titled tables on one sheet — used for a ``group``),
:func:`_cells_sheet` (free-placed cells — used for the Contents title block) and the
sheet-name helpers :func:`_safe_sheet_name` / :func:`_uniq`. The whole workbook shares
one style sheet — the calendar styles, whose palette carries the title (xf 9) and
navy header (xf 2) cell styles the stacked / contents sheets reference.

Payload vocabulary is :mod:`p6_special.payloads`; the input ``rendered`` is the list
returned by ``registry.render(ctx, item_ids)`` — one ``{id, title, feature,
feature_title, ctype, payload}`` per picked result, in the user's pick order.
"""
from p6_evm.xlsx_writer import (
    _CAL_STYLES, _write_book, _sheet, _stacked_sheet, _cells_sheet,
    _safe_sheet_name, _uniq,
)

# What an opaque reused feature-report section (kind 'html') gets — honest, we do
# not try to parse the feature's own report markup back into a table.
_HTML_NOTICE = 'This section is a detailed report section — see the PDF / Word report.'

# A friendly heading per payload kind, used for the sub-heading of each block when a
# ``group`` payload is flattened onto one stacked sheet.
_KIND_LABEL = {
    'table': 'Table', 'kpi_group': 'Key figures', 'bars': 'Comparison',
    'segbar': 'Breakdown', 'findings': 'Findings', 'keyvals': 'Details',
    'line': 'Trend', 'status_header': 'Status', 'text': 'Notes',
    'note': 'Note', 'html': 'Detailed section',
}


def _cellval(c):
    """A ``table`` cell may be a plain value or a ``[text, tone]`` / ``(text, tone)``
    pair to colour it — take the text for the spreadsheet."""
    if isinstance(c, (list, tuple)):
        return c[0] if c else ''
    return c


def _val(v):
    """None -> '' (blank cell); everything else passes through unchanged so numbers
    stay numeric cells and strings stay text."""
    return '' if v is None else v


def _date_str(v):
    """A clean date for the Contents subtitle — drop any time tail."""
    if not v:
        return ''
    s = str(v)
    for sep in (' ', 'T'):
        if sep in s:
            return s.split(sep)[0]
    return s


def _kind_to_table(pl):
    """A payload -> ``(headers, rows)`` for one flat sheet, or ``None`` to skip.

    ``group`` and ``no_data`` (and any unknown kind) return ``None`` — the caller
    handles ``group`` specially and skips the rest.
    """
    if not isinstance(pl, dict):
        return None
    kind = pl.get('kind')

    if kind == 'table':
        cols = list(pl.get('columns') or [])
        rows = [[_cellval(c) for c in (r or [])] for r in (pl.get('rows') or [])]
        return (cols or ['Value'], rows)

    if kind == 'kpi_group':
        rows = [[it.get('label'), it.get('value'), it.get('sub')]
                for it in (pl.get('items') or [])]
        return (['Metric', 'Value', 'Detail'], rows)

    if kind == 'bars':
        series = pl.get('series') or []
        headers = ['Category'] + [s.get('label') for s in series]
        rows = []
        for row in (pl.get('rows') or []):
            vals = row.get('values') or []
            rows.append([row.get('label')] +
                        [_val(vals[i]) if i < len(vals) else '' for i in range(len(series))])
        return (headers, rows)

    if kind == 'segbar':
        rows = [[s.get('label'), _val(s.get('value'))] for s in (pl.get('segments') or [])]
        return (['Segment', 'Value'], rows)

    if kind == 'findings':
        rows = [[str(f.get('severity') or 'info').title(), f.get('title'),
                 f.get('source') or f.get('detail') or '']
                for f in (pl.get('items') or [])]
        return (['Severity', 'Finding', 'Source'], rows)

    if kind == 'keyvals':
        rows = [[k, v] for k, v in (pl.get('pairs') or [])]
        return (['Item', 'Value'], rows)

    if kind == 'line':
        series = pl.get('series') or []
        x = pl.get('x') or []
        n = max((len(s.get('points') or []) for s in series), default=0)
        headers = ['Point'] + [s.get('label') for s in series]
        rows = []
        for i in range(n):
            cells = [x[i] if i < len(x) else (i + 1)]
            for s in series:
                pts = s.get('points') or []
                cells.append(_val(pts[i]) if i < len(pts) else '')
            rows.append(cells)
        return (headers, rows)

    if kind == 'status_header':
        rows = [[d.get('domain'), str(d.get('tone') or '').title(), d.get('headline')]
                for d in (pl.get('domains') or [])]
        return (['Area', 'Status', 'Headline'], rows)

    if kind == 'text':
        return (['Text'], [[p] for p in (pl.get('paragraphs') or [])])

    if kind == 'note':
        return (['Note'], [[pl.get('message')]])

    if kind == 'html':
        return (['Detailed report section'], [[_HTML_NOTICE]])

    return None


def _group_blocks(pl):
    """Flatten a ``group`` payload into stacked-sheet blocks
    ``[{title, headers, rows}, ...]`` — recursing nested groups, skipping no_data."""
    blocks = []
    for b in (pl.get('blocks') or []):
        if not isinstance(b, dict):
            continue
        if b.get('kind') == 'group':
            blocks.extend(_group_blocks(b))
            continue
        t = _kind_to_table(b)
        if not t:
            continue
        headers, rows = t
        blocks.append({'title': _KIND_LABEL.get(b.get('kind'), 'Section'),
                       'headers': headers, 'rows': rows})
    return blocks


def _result_sheet_xml(pl):
    """The worksheet XML for one result payload, or ``None`` to skip it (no_data /
    unknown / an empty group)."""
    if not isinstance(pl, dict):
        return None
    kind = pl.get('kind')
    if kind == 'group':
        blocks = _group_blocks(pl)
        if not blocks:
            return None
        return _stacked_sheet(blocks, col_widths={0: 30, 1: 22, 2: 22, 3: 18})
    if kind in (None, 'no_data'):
        return None
    t = _kind_to_table(pl)
    if not t:
        return None
    headers, rows = t
    return _sheet(headers, rows)


def _contents_sheet_xml(report_name, meta, rendered):
    """The leading Contents sheet: a title block (report name + project · data date)
    then a numbered '#/Section/Source' list of every picked section, in pick order."""
    meta = meta or {}
    cells = {(1, 0): (report_name or 'Special Report', 9)}          # xf 9 = title
    proj = meta.get('project_name')
    dd = _date_str(meta.get('data_date'))
    bits = [b for b in (proj, (f'Data date {dd}' if dd else None)) if b]
    if bits:
        cells[(2, 0)] = (' · '.join(str(b) for b in bits), 0)
    hr = 4
    for c, h in enumerate(('#', 'Section', 'Source')):
        cells[(hr, c)] = (h, 2)                                     # xf 2 = navy header
    r = hr + 1
    for i, item in enumerate(rendered, 1):
        item = item or {}
        cells[(r, 0)] = (i, 0)
        cells[(r, 1)] = (item.get('title') or 'Section', 0)
        cells[(r, 2)] = (item.get('feature_title') or item.get('feature') or '', 0)
        r += 1
    return _cells_sheet(cells, col_widths={0: 6, 1: 46, 2: 28})


def build_excel(path, report_name, meta, rendered):
    """Write the Reporting Studio workbook to ``path``.

    ``rendered`` is ``registry.render(...)`` output (a list of ``{id, title, feature,
    feature_title, ctype, payload}`` in pick order). Emits a Contents sheet plus one
    data sheet per result (no_data / unknown / empty-group results are skipped, never
    an empty sheet). Never raises on a malformed / empty item — such an item is
    skipped. Returns ``path``.
    """
    rendered = list(rendered or [])
    used = set()
    sheets = [(_uniq(_safe_sheet_name('Contents'), used),
               _contents_sheet_xml(report_name, meta, rendered))]
    for item in rendered:
        try:
            pl = (item or {}).get('payload') or {}
            sheet_xml = _result_sheet_xml(pl)
            if sheet_xml is None:
                continue
            name = _uniq(_safe_sheet_name((item or {}).get('title') or 'Section'), used)
            sheets.append((name, sheet_xml))
        except Exception:
            continue
    _write_book(path, sheets, _CAL_STYLES)
    return path
