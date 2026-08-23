"""Excel export for the Professional Dashboard.

Mirrors the PDF composition: the letterhead, then every selected component in order
with its (user-edited) title. Built on the project's zero-dependency OOXML writer
(``p6_evm.xlsx_writer``) so the workbook always opens cleanly. Chart/trend components
are written as their underlying data tables (same numbers the on-screen chart draws),
keeping Excel == the dashboard composition.
"""

from p6_evm.xlsx_writer import _write_book, _cells_sheet, _STYLES


def _s(v):
    """Coerce to an Excel-friendly scalar (numbers stay numeric, everything else str)."""
    if v is None:
        return ''
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return v
    return str(v)


def _component_cells(cells, r, comp):
    """Write one component starting at row `r`; return the next free row."""
    title = comp.get('title') or ''
    payload = comp.get('payload') or {}
    ctype = payload.get('type') or comp.get('type')
    data = payload.get('data') or {}

    cells[(r, 0)] = (title, 1)  # bold section title
    r += 1

    if ctype == 'kpi':
        cells[(r, 0)] = ('Value', 0); cells[(r, 1)] = (_s(data.get('value')), 1); r += 1
        if data.get('note'):
            cells[(r, 0)] = (_s(data.get('note')), 0); r += 1

    elif ctype == 'score':
        cells[(r, 0)] = ('Score', 0); cells[(r, 1)] = (_s(data.get('value')), 1)
        cells[(r, 2)] = (_s(data.get('band')), 0); r += 1
        if data.get('detail'):
            cells[(r, 0)] = (_s(data.get('detail')), 0); r += 1

    elif ctype == 'status':
        cells[(r, 0)] = (_s(data.get('label')), 1); r += 1
        if data.get('note'):
            cells[(r, 0)] = (_s(data.get('note')), 0); r += 1

    elif ctype == 'summary':
        for st in (data.get('stats') or []):
            cells[(r, 0)] = (_s(st.get('label')), 0); cells[(r, 1)] = (_s(st.get('value')), 1); r += 1

    elif ctype == 'findings':
        for it in (data.get('items') or []):
            cells[(r, 0)] = (_s(it.get('severity')), 0); cells[(r, 1)] = (_s(it.get('text')), 0); r += 1

    elif ctype == 'table':
        for c, h in enumerate(data.get('headers') or []):
            cells[(r, c)] = (_s(h), 1)
        r += 1
        for row in (data.get('rows') or []):
            for c, v in enumerate(row):
                cells[(r, c)] = (_s(v), 0)
            r += 1

    elif ctype in ('chart', 'trend'):
        r = _chart_cells(cells, r, data)

    elif ctype == 'text':
        cells[(r, 0)] = (_s(data.get('text')), 0); r += 1

    elif ctype == 'image':
        cells[(r, 0)] = ('[image]', 0); r += 1

    return r + 1  # trailing blank row between components


def _chart_cells(cells, r, data):
    kind = data.get('kind')
    if kind == 'bars':
        cells[(r, 0)] = ('Label', 1); cells[(r, 1)] = ('Value', 1); r += 1
        for row in (data.get('rows') or []):
            cells[(r, 0)] = (_s(row.get('label')), 0)
            cells[(r, 1)] = (_s(row.get('value')), 0)
            r += 1
    elif kind == 'grouped':
        labels = data.get('labels') or []
        groups = data.get('groups') or []
        cells[(r, 0)] = ('', 1)
        for c, g in enumerate(groups):
            cells[(r, c + 1)] = (_s(g.get('name')), 1)
        r += 1
        for i, lab in enumerate(labels):
            cells[(r, 0)] = (_s(lab), 0)
            for c, g in enumerate(groups):
                vals = g.get('values') or []
                cells[(r, c + 1)] = (_s(vals[i] if i < len(vals) else ''), 0)
            r += 1
    elif kind == 'line':
        series = data.get('series') or []
        xlabels = data.get('x_labels') or []
        cells[(r, 0)] = ('Point', 1)
        for c, s in enumerate(series):
            cells[(r, c + 1)] = (_s(s.get('name')), 1)
        r += 1
        n = max((len(s.get('points') or []) for s in series), default=0)
        for i in range(n):
            cells[(r, 0)] = (_s(xlabels[i] if i < len(xlabels) else i + 1), 0)
            for c, s in enumerate(series):
                pts = s.get('points') or []
                cells[(r, c + 1)] = (_s(pts[i] if i < len(pts) else ''), 0)
            r += 1
    return r


def write_dashboard_xlsx(path, composition):
    """Write the dashboard composition to `path` as a single 'Dashboard' worksheet."""
    header = composition.get('header') or {}
    comps = composition.get('components') or []
    cells = {}
    r = 1
    cells[(r, 0)] = (_s(header.get('title') or 'Project Dashboard'), 1); r += 1
    if header.get('subtitle'):
        cells[(r, 0)] = (_s(header.get('subtitle')), 0); r += 1
    r += 1
    for comp in comps:
        try:
            r = _component_cells(cells, r, comp)
        except Exception:
            cells[(r, 0)] = (_s(comp.get('title') or ''), 1); r += 2
    col_widths = {0: 30, 1: 22, 2: 18, 3: 18, 4: 18, 5: 18}
    _write_book(path, [('Dashboard', _cells_sheet(cells, col_widths=col_widths))], _STYLES)
