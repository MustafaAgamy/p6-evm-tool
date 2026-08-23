"""Excel export for the Professional Dashboard.

Mirrors the PDF composition: the letterhead, then every selected component in order
with its (user-edited) title. Chart/trend/grouped components get a data table AND a
**native in-cell Excel chart** (bar / line / clustered bar), written as hand-rolled
OOXML so the bundle keeps zero third-party dependencies.

Robustness: chart building is wrapped so a single bad chart degrades to just its data
table, and if the whole chart-packaging path fails the workbook is re-written data-only
via the plain writer — the file always opens.
"""

import zipfile
from xml.sax.saxutils import escape

from p6_evm.xlsx_writer import _cells_sheet, _STYLES, _col, _write_book


def _s(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return v
    return str(v)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ── cell layout (also collects chart specs) ─────────────────────────────────

def _component_cells(cells, r, comp, charts):
    title = comp.get('title') or ''
    payload = comp.get('payload') or {}
    ctype = payload.get('type') or comp.get('type')
    data = payload.get('data') or {}

    cells[(r, 0)] = (title, 1)
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
        r = _chart_cells(cells, r, data, title, charts)
    elif ctype == 'text':
        cells[(r, 0)] = (_s(data.get('text')), 0); r += 1
    elif ctype == 'image':
        cells[(r, 0)] = ('[image]', 0); r += 1

    return r + 1


def _chart_cells(cells, r, data, title, charts):
    """Write a chart component's data table and register a native-chart spec."""
    kind = data.get('kind')
    header_row = r  # 1-based row of the data header

    if kind == 'bars':
        rows = data.get('rows') or []
        cells[(r, 0)] = ('Label', 1); cells[(r, 1)] = ('Value', 1); r += 1
        first = r
        for row in rows:
            cells[(r, 0)] = (_s(row.get('label')), 0)
            cells[(r, 1)] = (_num(row.get('value')), 0)
            r += 1
        if rows:
            _register_chart(charts, 'bar', title, header_row, first, r - 1,
                            cats_col=0, series=[('Value', 1)], cats=[_s(x.get('label')) for x in rows])
        return r

    if kind == 'grouped':
        labels = data.get('labels') or []
        groups = data.get('groups') or []
        cells[(r, 0)] = ('', 1)
        for c, g in enumerate(groups):
            cells[(r, c + 1)] = (_s(g.get('name')), 1)
        r += 1
        first = r
        for i, lab in enumerate(labels):
            cells[(r, 0)] = (_s(lab), 0)
            for c, g in enumerate(groups):
                vals = g.get('values') or []
                cells[(r, c + 1)] = (_num(vals[i]) if i < len(vals) else 0, 0)
            r += 1
        if labels and groups:
            _register_chart(charts, 'bar', title, header_row, first, r - 1,
                            cats_col=0, series=[(g.get('name') or f'Series {c+1}', c + 1)
                                                for c, g in enumerate(groups)],
                            cats=[_s(x) for x in labels])
        return r

    if kind == 'line':
        series = data.get('series') or []
        xlabels = data.get('x_labels') or []
        cells[(r, 0)] = ('Point', 1)
        for c, sname in enumerate(series):
            cells[(r, c + 1)] = (_s(sname.get('name')), 1)
        r += 1
        first = r
        n = max((len(s.get('points') or []) for s in series), default=0)
        cats = []
        for i in range(n):
            lab = _s(xlabels[i]) if i < len(xlabels) else (i + 1)
            cells[(r, 0)] = (lab, 0)
            cats.append(str(lab))
            for c, s in enumerate(series):
                pts = s.get('points') or []
                cells[(r, c + 1)] = (_num(pts[i]) if i < len(pts) else 0, 0)
            r += 1
        if n and series:
            _register_chart(charts, 'line', title, header_row, first, r - 1,
                            cats_col=0, series=[(s.get('name') or f'Series {c+1}', c + 1)
                                                for c, s in enumerate(series)],
                            cats=cats)
        return r

    return r


def _register_chart(charts, kind, title, header_row, first_row, last_row, cats_col, series, cats):
    """Record enough to emit chartN.xml. Rows are 1-based; cols 0-based."""
    charts.append({
        'kind': kind, 'title': title,
        'cats_col': cats_col, 'first': first_row, 'last': last_row, 'cats': cats,
        'series': series,                      # [(name, col_index_0based)]
        'anchor_top': header_row - 1,          # 0-based drawing row
    })


# ── OOXML chart / drawing generation ────────────────────────────────────────

_CNS = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
_ANS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_RNS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_XNS = 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'


def _ref(col0, r0, r1):
    col = _col(col0)
    return f'Dashboard!${col}${r0}:${col}${r1}'


def _str_cache(vals):
    pts = ''.join(f'<c:pt idx="{i}"><c:v>{escape(str(v))}</c:v></c:pt>' for i, v in enumerate(vals))
    return f'<c:ptCount val="{len(vals)}"/>{pts}'


def _num_cache(vals):
    pts = ''.join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(vals))
    return f'<c:formatCode>General</c:formatCode><c:ptCount val="{len(vals)}"/>{pts}'


def _ser_xml(idx, name, cats_col, val_col, first, last, cats, vals):
    cat_ref = _ref(cats_col, first, last)
    val_ref = _ref(val_col, first, last)
    return (
        f'<c:ser><c:idx val="{idx}"/><c:order val="{idx}"/>'
        f'<c:tx><c:v>{escape(str(name))}</c:v></c:tx>'
        f'<c:cat><c:strRef><c:f>{escape(cat_ref)}</c:f><c:strCache>{_str_cache(cats)}</c:strCache></c:strRef></c:cat>'
        f'<c:val><c:numRef><c:f>{escape(val_ref)}</c:f><c:numCache>{_num_cache(vals)}</c:numCache></c:numRef></c:val>'
        f'</c:ser>')


def _chart_xml(spec, cell_lookup):
    """cell_lookup(row, col) -> numeric value stored for a series column."""
    cats = spec['cats']
    first, last = spec['first'], spec['last']
    sers = []
    for i, (name, col) in enumerate(spec['series']):
        vals = [_num(cell_lookup(rr, col)) for rr in range(first, last + 1)]
        sers.append(_ser_xml(i, name, spec['cats_col'], col, first, last, cats, vals))
    body = ''.join(sers)
    ax1, ax2 = 111111111, 222222222
    title = (f'<c:title><c:tx><c:rich><a:bodyPr/><a:p><a:r><a:t>{escape(spec["title"])}</a:t>'
             f'</a:r></a:p></c:rich></c:tx><c:overlay val="0"/></c:title><c:autoTitleDeleted val="0"/>')
    if spec['kind'] == 'line':
        plot = (f'<c:lineChart><c:grouping val="standard"/><c:varyColors val="0"/>{body}'
                f'<c:marker val="1"/><c:axId val="{ax1}"/><c:axId val="{ax2}"/></c:lineChart>')
    else:
        plot = (f'<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/><c:varyColors val="0"/>'
                f'{body}<c:axId val="{ax1}"/><c:axId val="{ax2}"/></c:barChart>')
    axes = (f'<c:catAx><c:axId val="{ax1}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="b"/><c:crossAx val="{ax2}"/></c:catAx>'
            f'<c:valAx><c:axId val="{ax2}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="l"/><c:crossAx val="{ax1}"/></c:valAx>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<c:chartSpace xmlns:c="{_CNS}" xmlns:a="{_ANS}" xmlns:r="{_RNS}">'
            f'<c:chart>{title}<c:plotArea><c:layout/>{plot}{axes}</c:plotArea>'
            f'<c:plotVisOnly val="1"/></c:chart></c:chartSpace>')


def _anchor(spec, chart_rid):
    top = max(0, spec['anchor_top'])
    frm = f'<xdr:from><xdr:col>7</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{top}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>'
    to = f'<xdr:to><xdr:col>15</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{top + 15}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>'
    gid = chart_rid  # unique small int
    return (f'<xdr:twoCellAnchor>{frm}{to}'
            f'<xdr:graphicFrame macro=""><xdr:nvGraphicFramePr>'
            f'<xdr:cNvPr id="{gid + 1}" name="Chart {gid}"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr>'
            f'<xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm>'
            f'<a:graphic><a:graphicData uri="{_CNS}">'
            f'<c:chart xmlns:c="{_CNS}" xmlns:r="{_RNS}" r:id="rId{gid}"/></a:graphicData></a:graphic>'
            f'</xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>')


def _drawing_xml(charts):
    anchors = ''.join(_anchor(spec, i + 1) for i, spec in enumerate(charts))
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<xdr:wsDr xmlns:xdr="{_XNS}" xmlns:a="{_ANS}">{anchors}</xdr:wsDr>')


def _drawing_rels(charts):
    rels = ''.join(
        f'<Relationship Id="rId{i + 1}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" '
        f'Target="../charts/chart{i + 1}.xml"/>' for i in range(len(charts)))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{rels}</Relationships>')


def _write_workbook_with_charts(path, sheet_xml, charts, chart_xmls):
    n = len(charts)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>',
          '<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>']
    for i in range(1, n + 1):
        ct.append(f'<Override PartName="/xl/charts/chart{i}.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>')
    ct.append('</Types>')

    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                 '</Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
          ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          '<sheets><sheet name="Dashboard" sheetId="1" r:id="rId1"/></sheets></workbook>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
               '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
               '</Relationships>')
    sheet_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>'
                  '</Relationships>')

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ''.join(ct))
        z.writestr('_rels/.rels', root_rels)
        z.writestr('xl/workbook.xml', wb)
        z.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        z.writestr('xl/styles.xml', _STYLES)
        z.writestr('xl/worksheets/sheet1.xml', sheet_xml)
        z.writestr('xl/worksheets/_rels/sheet1.xml.rels', sheet_rels)
        z.writestr('xl/drawings/drawing1.xml', _drawing_xml(charts))
        z.writestr('xl/drawings/_rels/drawing1.xml.rels', _drawing_rels(charts))
        for i, cx in enumerate(chart_xmls, 1):
            z.writestr(f'xl/charts/chart{i}.xml', cx)


# ── public entry ────────────────────────────────────────────────────────────

def write_dashboard_xlsx(path, composition):
    """Write the composition to `path`. Native charts for chart/trend/grouped
    components; falls back to a data-only workbook if chart packaging fails."""
    header = composition.get('header') or {}
    comps = composition.get('components') or []
    cells = {}
    charts = []
    r = 1
    cells[(r, 0)] = (_s(header.get('title') or 'Project Dashboard'), 1); r += 1
    if header.get('subtitle'):
        cells[(r, 0)] = (_s(header.get('subtitle')), 0); r += 1
    r += 1
    for comp in comps:
        try:
            r = _component_cells(cells, r, comp, charts)
        except Exception:
            cells[(r, 0)] = (_s(comp.get('title') or ''), 1); r += 2

    col_widths = {0: 30, 1: 22, 2: 18, 3: 18, 4: 18, 5: 18}
    sheet_body = _cells_sheet(cells, col_widths=col_widths)

    if not charts:
        _write_book(path, [('Dashboard', sheet_body)], _STYLES)
        return

    def _lookup(row, col):
        v = cells.get((row, col))
        return v[0] if v else 0

    try:
        chart_xmls = []
        good = []
        for spec in charts:
            try:
                chart_xmls.append(_chart_xml(spec, _lookup))
                good.append(spec)
            except Exception:
                continue          # skip this chart; its data table is already in the sheet
        if not good:
            _write_book(path, [('Dashboard', sheet_body)], _STYLES)
            return
        sheet_with_drawing = sheet_body.replace(
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        ).replace('</worksheet>', '<drawing r:id="rId1"/></worksheet>')
        _write_workbook_with_charts(path, sheet_with_drawing, good, chart_xmls)
    except Exception:
        # ultimate safety net — a valid data-only workbook always opens
        _write_book(path, [('Dashboard', sheet_body)], _STYLES)
