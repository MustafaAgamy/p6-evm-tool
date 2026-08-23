"""Excel export for the Professional Dashboard.

Reproduces the on-screen dashboard as a **visual grid of panels** — a letterhead, a
row of KPI tiles, then a two-column grid of bordered panels with pale-blue title bars,
with **native Excel charts** drawn inside the chart panels. Hand-rolled OOXML, zero
third-party dependencies.

Robustness: if anything in the styled build fails, it falls back to a plain data-only
workbook via the shared writer, so the file always opens.
"""

import zipfile
from xml.sax.saxutils import escape

from p6_evm.xlsx_writer import _cell, _col, _cells_sheet, _STYLES, _write_book

# Visual grid: 8 content columns (A–H). Left band 0–3, right band 4–7; wide = 0–7.
NCOL = 8
LEFT = (0, 3)
RIGHT = (4, 7)
WIDE = (0, 7)
DATA_COL = 20            # off-grid column where chart source data lives

# style indices in _DSTYLES (below)
S_BOLD, S_TITLE, S_HEAD, S_SUB, S_BIG, S_NOTE, S_THEAD, S_CELL, S_BODY = 1, 2, 3, 4, 5, 6, 7, 8, 9


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _s(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return v
    return str(v)


def _merge(a_col, b_col, row):
    return f'{_col(a_col)}{row}:{_col(b_col)}{row}'


class _Build:
    def __init__(self):
        self.cells = {}
        self.merges = []
        self.charts = []
        self.data_row = 1        # cursor in the off-grid chart-data region

    def put(self, r, c, v, s=None):
        self.cells[(r, c)] = (v, s)

    def bar(self, band, row, text, style=S_TITLE):
        """A merged title/head bar across a band at `row`."""
        self.put(row, band[0], text, style)
        for c in range(band[0] + 1, band[1] + 1):
            self.put(row, c, '', style)
        self.merges.append(_merge(band[0], band[1], row))


# ── panel bodies (return rows used, excluding the title bar) ─────────────────

def _panel(B, band, top, comp):
    """Render one component's title bar + body into band starting at row `top`
    (1-based). Returns the total rows used (title + body)."""
    title = comp.get('title') or ''
    payload = comp.get('payload') or {}
    ctype = payload.get('type') or comp.get('type')
    data = payload.get('data') or {}
    B.bar(band, top, title, S_TITLE)
    r = top + 1
    c0, c1 = band

    if ctype in ('kpi', 'score', 'status'):
        val = data.get('value') if ctype != 'status' else data.get('label')
        B.bar(band, r, _s(val), S_BIG); r += 1
        note = data.get('note') or data.get('band') or data.get('detail')
        if note:
            B.bar(band, r, _s(note), S_NOTE); r += 1

    elif ctype == 'summary':
        for st in (data.get('stats') or []):
            B.put(r, c0, _s(st.get('label')), S_CELL)
            for c in range(c0 + 1, c1): B.put(r, c, '', S_CELL)
            B.put(r, c1, _s(st.get('value')), S_CELL)
            r += 1

    elif ctype == 'findings':
        for it in (data.get('items') or []):
            B.put(r, c0, _s(it.get('severity')), S_CELL)
            B.bar(band, r, _s(it.get('text')), S_CELL)   # note: bar re-merges c0..c1
            # (severity overwritten by merge start; keep it simple — text spans the row)
            r += 1

    elif ctype == 'table':
        heads = data.get('headers') or []
        for i, h in enumerate(heads[:c1 - c0 + 1]):
            B.put(r, c0 + i, _s(h), S_THEAD)
        r += 1
        for row in (data.get('rows') or []):
            for i, v in enumerate(row[:c1 - c0 + 1]):
                B.put(r, c0 + i, _s(v), S_CELL)
            r += 1

    elif ctype in ('chart', 'trend'):
        _chart_panel(B, band, r, data)
        r += 11          # reserve rows for the embedded chart

    elif ctype == 'text':
        B.bar(band, r, _s(data.get('text')), S_CELL); r += 3

    elif ctype == 'image':
        B.bar(band, r, '[image]', S_CELL); r += 1

    else:
        B.bar(band, r, '—', S_CELL); r += 1

    return r - top


def _chart_panel(B, band, row, data):
    """Write chart source data off-grid and register a native chart anchored in the
    panel band starting at `row` (1-based)."""
    kind = data.get('kind')
    dc = DATA_COL
    dr = B.data_row
    cats, series = [], []      # series: (name, col0based, first, last)

    if kind == 'bars':
        rows = data.get('rows') or []
        B.put(dr, dc, 'Label'); B.put(dr, dc + 1, 'Value'); dr += 1
        first = dr
        for row_ in rows:
            B.put(dr, dc, _s(row_.get('label'))); B.put(dr, dc + 1, _num(row_.get('value'))); dr += 1
        cats = [_s(x.get('label')) for x in rows]
        if rows:
            series = [('Value', dc + 1, first, dr - 1)]
    elif kind == 'grouped':
        labels = data.get('labels') or []; groups = data.get('groups') or []
        B.put(dr, dc, '')
        for i, g in enumerate(groups): B.put(dr, dc + 1 + i, _s(g.get('name')))
        dr += 1
        first = dr
        for i, lab in enumerate(labels):
            B.put(dr, dc, _s(lab))
            for gi, g in enumerate(groups):
                vals = g.get('values') or []
                B.put(dr, dc + 1 + gi, _num(vals[i]) if i < len(vals) else 0)
            dr += 1
        cats = [_s(x) for x in labels]
        series = [(g.get('name') or f'S{gi+1}', dc + 1 + gi, first, dr - 1) for gi, g in enumerate(groups)]
    elif kind == 'line':
        ser = data.get('series') or []; xl = data.get('x_labels') or []
        B.put(dr, dc, 'Point')
        for i, s in enumerate(ser): B.put(dr, dc + 1 + i, _s(s.get('name')))
        dr += 1
        first = dr
        n = max((len(s.get('points') or []) for s in ser), default=0)
        for i in range(n):
            B.put(dr, dc, _s(xl[i]) if i < len(xl) else i + 1)
            for si, s in enumerate(ser):
                pts = s.get('points') or []
                B.put(dr, dc + 1 + si, _num(pts[i]) if i < len(pts) else 0)
            dr += 1
        cats = [str(xl[i]) if i < len(xl) else str(i + 1) for i in range(n)]
        series = [(s.get('name') or f'S{si+1}', dc + 1 + si, first, dr - 1) for si, s in enumerate(ser)]

    B.data_row = dr + 1
    if series:
        B.charts.append({
            'kind': 'line' if kind == 'line' else 'bar',
            'cats_col': dc, 'cats': cats, 'series': series,
            'from_col': band[0], 'from_row': row - 1, 'to_col': band[1] + 1, 'to_row': row - 1 + 10,
        })


# ── OOXML chart / drawing generation ────────────────────────────────────────

_CNS = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
_ANS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_RNS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_XNS = 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'


def _rng(col0, r0, r1):
    col = _col(col0)
    return f'Dashboard!${col}${r0}:${col}${r1}'


def _str_cache(vals):
    return f'<c:ptCount val="{len(vals)}"/>' + ''.join(
        f'<c:pt idx="{i}"><c:v>{escape(str(v))}</c:v></c:pt>' for i, v in enumerate(vals))


def _num_cache(B, col, first, last):
    vals = [_num(B.cells.get((rr, col), (0,))[0]) for rr in range(first, last + 1)]
    pts = ''.join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(vals))
    return f'<c:formatCode>General</c:formatCode><c:ptCount val="{len(vals)}"/>{pts}'


def _chart_xml(B, spec):
    sers = []
    for i, (name, col, first, last) in enumerate(spec['series']):
        sers.append(
            f'<c:ser><c:idx val="{i}"/><c:order val="{i}"/>'
            f'<c:tx><c:v>{escape(str(name))}</c:v></c:tx>'
            f'<c:cat><c:strRef><c:f>{escape(_rng(spec["cats_col"], first, last))}</c:f>'
            f'<c:strCache>{_str_cache(spec["cats"])}</c:strCache></c:strRef></c:cat>'
            f'<c:val><c:numRef><c:f>{escape(_rng(col, first, last))}</c:f>'
            f'<c:numCache>{_num_cache(B, col, first, last)}</c:numCache></c:numRef></c:val></c:ser>')
    body = ''.join(sers)
    a1, a2 = 111111111, 222222222
    if spec['kind'] == 'line':
        plot = (f'<c:lineChart><c:grouping val="standard"/><c:varyColors val="0"/>{body}'
                f'<c:marker val="1"/><c:axId val="{a1}"/><c:axId val="{a2}"/></c:lineChart>')
    else:
        plot = (f'<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/><c:varyColors val="0"/>'
                f'{body}<c:axId val="{a1}"/><c:axId val="{a2}"/></c:barChart>')
    axes = (f'<c:catAx><c:axId val="{a1}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="b"/><c:crossAx val="{a2}"/></c:catAx>'
            f'<c:valAx><c:axId val="{a2}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="l"/><c:crossAx val="{a1}"/></c:valAx>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<c:chartSpace xmlns:c="{_CNS}" xmlns:a="{_ANS}" xmlns:r="{_RNS}"><c:chart>'
            f'<c:autoTitleDeleted val="1"/><c:plotArea><c:layout/>{plot}{axes}</c:plotArea>'
            f'<c:plotVisOnly val="1"/></c:chart></c:chartSpace>')


def _anchor(spec, rid):
    def frm(col, row):
        return f'<xdr:col>{col}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{row}</xdr:row><xdr:rowOff>0</xdr:rowOff>'
    return (f'<xdr:twoCellAnchor><xdr:from>{frm(spec["from_col"], spec["from_row"])}</xdr:from>'
            f'<xdr:to>{frm(spec["to_col"], spec["to_row"])}</xdr:to>'
            f'<xdr:graphicFrame macro=""><xdr:nvGraphicFramePr>'
            f'<xdr:cNvPr id="{rid + 1}" name="Chart {rid}"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr>'
            f'<xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm>'
            f'<a:graphic><a:graphicData uri="{_CNS}">'
            f'<c:chart xmlns:c="{_CNS}" xmlns:r="{_RNS}" r:id="rId{rid}"/></a:graphicData></a:graphic>'
            f'</xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>')


def _drawing_xml(charts):
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><xdr:wsDr xmlns:xdr="{_XNS}" '
            f'xmlns:a="{_ANS}">' + ''.join(_anchor(s, i + 1) for i, s in enumerate(charts)) + '</xdr:wsDr>')


def _drawing_rels(charts):
    rels = ''.join(
        f'<Relationship Id="rId{i+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" '
        f'Target="../charts/chart{i+1}.xml"/>' for i in range(len(charts)))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
            f'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')


# ── worksheet + workbook packaging ──────────────────────────────────────────

def _sheet_xml(B, col_widths, has_charts):
    cols = ('<cols>' + ''.join(
        f'<col min="{c+1}" max="{c+1}" width="{w}" customWidth="1"/>'
        for c, w in sorted(col_widths.items())) + '</cols>') if col_widths else ''
    by_row = {}
    for (r, c), (v, s) in B.cells.items():
        by_row.setdefault(r, {})[c] = (v, s)
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
           ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
           cols, '<sheetData>']
    for r in sorted(by_row):
        out.append(f'<row r="{r}">')
        for c in sorted(by_row[r]):
            v, s = by_row[r][c]
            out.append(_cell(c, r, v, style=s))
        out.append('</row>')
    out.append('</sheetData>')
    if B.merges:
        out.append(f'<mergeCells count="{len(B.merges)}">'
                   + ''.join(f'<mergeCell ref="{m}"/>' for m in B.merges) + '</mergeCells>')
    if has_charts:
        out.append('<drawing r:id="rId1"/>')
    out.append('</worksheet>')
    return ''.join(out)


def _write(path, sheet_xml, charts, chart_xmls):
    n = len(charts)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>']
    if n:
        ct.append('<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>')
        for i in range(1, n + 1):
            ct.append(f'<Override PartName="/xl/charts/chart{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>')
    ct.append('</Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
          ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          '<sheets><sheet name="Dashboard" sheetId="1" r:id="rId1"/></sheets></workbook>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
               '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    sheet_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ''.join(ct))
        z.writestr('_rels/.rels', root_rels)
        z.writestr('xl/workbook.xml', wb)
        z.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        z.writestr('xl/styles.xml', _DSTYLES)
        z.writestr('xl/worksheets/sheet1.xml', sheet_xml)
        if n:
            z.writestr('xl/worksheets/_rels/sheet1.xml.rels', sheet_rels)
            z.writestr('xl/drawings/drawing1.xml', _drawing_xml(charts))
            z.writestr('xl/drawings/_rels/drawing1.xml.rels', _drawing_rels(charts))
            for i, cx in enumerate(chart_xmls, 1):
                z.writestr(f'xl/charts/chart{i}.xml', cx)


# ── public entry ────────────────────────────────────────────────────────────

def write_dashboard_xlsx(path, composition):
    try:
        _write_grid(path, composition)
    except Exception:
        _write_fallback(path, composition)


def _write_grid(path, composition):
    header = composition.get('header') or {}
    comps = composition.get('components') or []
    B = _Build()

    # letterhead
    row = 1
    B.bar(WIDE, row, _s(header.get('title') or 'Project Dashboard'), S_HEAD); row += 1
    if header.get('subtitle'):
        B.bar(WIDE, row, _s(header.get('subtitle')), S_SUB); row += 1
    row += 1

    kpis = [c for c in comps if ((c.get('payload') or {}).get('type') or c.get('type')) == 'kpi']
    panels = [c for c in comps if c not in kpis]

    # KPI tiles — 4 per row, each 2 columns wide
    col = 0
    for c in kpis:
        band = (col, col + 1)
        d = (c.get('payload') or {}).get('data') or {}
        B.bar(band, row, _s(c.get('title')), S_TITLE)
        B.bar(band, row + 1, _s(d.get('value')), S_BIG)
        B.bar(band, row + 2, _s(d.get('note')), S_NOTE)
        col += 2
        if col >= NCOL:
            col = 0; row += 3
    if col != 0:
        row += 3
    row += 1

    # panels — two-column grid, paired left/right; wide panels take a full row
    i = 0
    while i < len(panels):
        p = panels[i]
        if (p.get('size') == 2):
            h = _panel(B, WIDE, row, p)
            row += h + 1; i += 1
        else:
            hL = _panel(B, LEFT, row, p)
            hR = 0
            if i + 1 < len(panels) and panels[i + 1].get('size') != 2:
                hR = _panel(B, RIGHT, row, panels[i + 1]); i += 2
            else:
                i += 1
            row += max(hL, hR) + 1

    col_widths = {c: 15 for c in range(NCOL)}
    for c in range(DATA_COL, DATA_COL + 8):
        col_widths[c] = 11
    sheet_xml = _sheet_xml(B, col_widths, bool(B.charts))
    chart_xmls = [_chart_xml(B, s) for s in B.charts]
    _write(path, sheet_xml, B.charts, chart_xmls)


def _write_fallback(path, composition):
    """A plain, always-valid data workbook if the styled grid ever fails."""
    comps = composition.get('components') or []
    header = composition.get('header') or {}
    cells = {}
    r = 1
    cells[(r, 0)] = (_s(header.get('title') or 'Project Dashboard'), 1); r += 2
    for comp in comps:
        cells[(r, 0)] = (_s(comp.get('title') or ''), 1); r += 1
        d = (comp.get('payload') or {}).get('data') or {}
        v = d.get('value') or d.get('label')
        if v is not None:
            cells[(r, 0)] = (_s(v), 0); r += 1
        r += 1
    _write_book(path, [('Dashboard', _cells_sheet(cells, col_widths={0: 30, 1: 20}))], _STYLES)


# ── styles ──────────────────────────────────────────────────────────────────
_DSTYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="6">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FF1F3C66"/><name val="Calibri"/></font>
<font><b/><sz val="16"/><color rgb="FF1F3C66"/><name val="Calibri"/></font>
<font><b/><sz val="18"/><name val="Calibri"/></font>
<font><sz val="9"/><color rgb="FF5D6B80"/><name val="Calibri"/></font>
</fonts>
<fills count="4">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFD6E2F2"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEEF2F7"/></patternFill></fill>
</fills>
<borders count="2">
<border/>
<border><left style="thin"><color rgb="FFB7C5D8"/></left><right style="thin"><color rgb="FFB7C5D8"/></right><top style="thin"><color rgb="FFB7C5D8"/></top><bottom style="thin"><color rgb="FFB7C5D8"/></bottom></border>
</borders>
<cellStyleXfs count="1"><xf/></cellStyleXfs>
<cellXfs count="10">
<xf/>
<xf fontId="1" applyFont="1"/>
<xf fontId="2" fillId="2" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf fontId="3" applyFont="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf fontId="5" applyFont="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf fontId="4" borderId="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf fontId="5" borderId="1" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf fontId="1" fillId="3" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf borderId="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="top" wrapText="1"/></xf>
<xf borderId="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="top" wrapText="1"/></xf>
</cellXfs>
</styleSheet>'''
