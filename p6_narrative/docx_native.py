"""SLICE A — NATIVE, EDITABLE Word charts.

The rest of the Word export (``docx_charts.py``) rasterises SVGs to PNG and
embeds them as *pictures* — pixels Word cannot edit. This module instead injects
REAL Word chart objects: a ``c:chartSpace`` OOXML part wired into the package
with the correct content-type override and relationship, referenced by an inline
``<w:drawing><c:chart r:id=.../>`` in the document body. Word opens them as
native, fully editable charts (right-click ▸ Edit Data, restyle, re-colour),
while they keep the current report's visual style and palette.

The injection pattern is the one proven by ``scratchpad/probe_native_chart.py``:
build the chart XML string, wrap it in a :class:`docx.opc.part.Part` with the
chart content-type, ``document.part.relate_to`` it (python-docx then registers
the ``[Content_Types].xml`` override and the ``document.xml.rels`` entry
automatically), and append the ``<w:drawing>`` to a fresh run.

For full "Edit Data" support each chart also gets an embedded ``.xlsx`` workbook
(built with openpyxl) referenced from the chart part via ``<c:externalData>``.
Workbook embedding is best-effort: if anything about it fails the chart still
ships as a native ``numCache``-backed chart object (editable styling, static
data) rather than crashing the export.

Every public function is **None-safe** and **project-agnostic**: a missing
document, empty data, mismatched lengths or non-numeric values return ``None``
and never raise, so a single bad chart can never take down the report.
"""
import io
import re

from docx.oxml import parse_xml
from docx.opc.part import Part
from docx.opc.packuri import PackURI
from docx.shared import Emu

from p6_narrative import wbs_chart

try:                                        # openpyxl is optional (Edit-Data nicety)
    from openpyxl import Workbook
except Exception:                           # pragma: no cover - env without openpyxl
    Workbook = None


# ── OOXML constants ───────────────────────────────────────────────────────────
CT_CHART = 'application/vnd.openxmlformats-officedocument.drawingml.chart+xml'
RT_CHART = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart'
CT_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
RT_PACKAGE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/package'

# default extent ≈ 16 cm wide (Cm(16) == 5760720 EMU), 9 cm tall — one report column
_CX = 5760720
_CY = 3240000

# doughnut palette (matches docx_charts._DONUT_PALETTE, sans the leading '#')
_PIE_PALETTE = ['1F5FA8', 'C98A2B', '7A5AA6', '4B9D6E', 'A35D5D', '5A8FB0']

_C_NS = ('xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
         'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
         'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


# ── small helpers ─────────────────────────────────────────────────────────────
def _xesc(x):
    """Minimal XML-text escaping; None → ''."""
    s = '' if x is None else str(x)
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
             .replace('"', '&quot;'))


def _num(v):
    """Coerce to float or None (never raises)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:                              # NaN
        return None
    return f


def _hex(color, fallback):
    """Normalise a colour to a 6-hex string (strip a leading '#'); fallback on junk."""
    try:
        c = str(color).lstrip('#').strip()
    except Exception:
        return fallback
    if len(c) == 6 and all(ch in '0123456789abcdefABCDEF' for ch in c):
        return c.upper()
    return fallback


def _title_el(title):
    if not title:
        return '<c:autoTitleDeleted val="1"/>'
    return (f'<c:title><c:tx><c:rich><a:bodyPr/><a:p><a:r>'
            f'<a:t>{_xesc(title)}</a:t></a:r></a:p></c:rich></c:tx>'
            f'<c:overlay val="0"/></c:title><c:autoTitleDeleted val="0"/>')


def _cat_ref(cats):
    pts = ''.join(f'<c:pt idx="{i}"><c:v>{_xesc(c)}</c:v></c:pt>'
                  for i, c in enumerate(cats))
    return (f'<c:cat><c:strRef><c:f>Sheet1!$A$2:$A${len(cats) + 1}</c:f>'
            f'<c:strCache><c:ptCount val="{len(cats)}"/>{pts}</c:strCache>'
            f'</c:strRef></c:cat>')


def _val_ref(vals, col_letter):
    pts = ''.join(f'<c:pt idx="{i}"><c:v>{v:g}</c:v></c:pt>'
                  for i, v in enumerate(vals))
    return (f'<c:val><c:numRef>'
            f'<c:f>Sheet1!${col_letter}$2:${col_letter}${len(vals) + 1}</c:f>'
            f'<c:numCache><c:formatCode>General</c:formatCode>'
            f'<c:ptCount val="{len(vals)}"/>{pts}</c:numCache></c:numRef></c:val>')


def _tx_ref(name, col_letter):
    return (f'<c:tx><c:strRef><c:f>Sheet1!${col_letter}$1</c:f>'
            f'<c:strCache><c:ptCount val="1"/><c:pt idx="0"><c:v>{_xesc(name)}</c:v>'
            f'</c:pt></c:strCache></c:strRef></c:tx>')


def _next_chart_index(package):
    n = 1
    existing = {p.partname for p in package.iter_parts()}
    while PackURI(f'/word/charts/chart{n}.xml') in existing:
        n += 1
    return n


def _col_letter(i):
    """0→B, 1→C, … (value columns start at B; A holds categories)."""
    return chr(ord('B') + i)


# ── native workbook embed (best-effort "Edit Data") ───────────────────────────
def _build_xlsx_bytes(cats, series):
    """A minimal workbook: A2.. categories, B1/C1.. series names, B2.. values.
    ``series`` is a list of (name, values). Returns bytes or None."""
    if Workbook is None:
        return None
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = 'Sheet1'
        ws['A1'] = ''
        for r, c in enumerate(cats):
            ws.cell(row=r + 2, column=1, value=c)
        for s, (name, values) in enumerate(series):
            ws.cell(row=1, column=2 + s, value=name)
            for r, v in enumerate(values):
                ws.cell(row=r + 2, column=2 + s, value=v)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
    except Exception:                       # pragma: no cover - defensive
        return None


def _try_embed(chart_part, package, cats, series):
    """Add an embedded xlsx to ``chart_part`` and return its rId, or None.

    Best-effort: any failure returns None and the chart falls back to the
    numCache-only form (still a native, editable chart object)."""
    blob = _build_xlsx_bytes(cats, series)
    if not blob:
        return None
    try:
        n = 1
        existing = {p.partname for p in package.iter_parts()}
        while PackURI(f'/word/embeddings/Microsoft_Excel_Worksheet{n}.xlsx') in existing:
            n += 1
        partname = PackURI(f'/word/embeddings/Microsoft_Excel_Worksheet{n}.xlsx')
        embed = Part(partname, CT_XLSX, blob, package)
        return chart_part.relate_to(embed, RT_PACKAGE)
    except Exception:                       # pragma: no cover - defensive
        return None


def _external_data(rid):
    if not rid:
        return ''
    return f'<c:externalData r:id="{rid}"><c:autoUpdate val="0"/></c:externalData>'


# ── the one place that wires a chartSpace XML string into the package ─────────
def _inject(document, chart_xml_fn, cats, series):
    """Create the chart part, (try to) embed its workbook, append the inline
    drawing. ``chart_xml_fn(rid)`` builds the chartSpace XML given the embedded
    workbook rId (may be ''). Returns the drawing element, or None on any error."""
    if document is None:
        return None
    try:
        package = document.part.package
        idx = _next_chart_index(package)
        partname = PackURI(f'/word/charts/chart{idx}.xml')
        # Build once WITHOUT externalData so the part exists to relate the workbook to.
        chart_part = Part(partname, CT_CHART, chart_xml_fn('').encode('utf-8'), package)
        rid_chart = document.part.relate_to(chart_part, RT_CHART)
        # Best-effort embed → patch the blob to reference it (keeps one part, one rel).
        rid_embed = _try_embed(chart_part, package, cats, series)
        if rid_embed:
            chart_part._blob = chart_xml_fn(rid_embed).encode('utf-8')

        # wp:docPr id must be DOCUMENT-unique (not the chart-part index) — otherwise a
        # chart's frame id can collide with a diagram/shape id and trip Word's repair
        # prompt. Allocate from the same shared counter the diagrams use.
        did = _next_id(document)
        drawing = parse_xml(
            '<w:drawing xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{_CX}" cy="{_CY}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{did}" name="Chart {did}"/>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
            f'<c:chart r:id="{rid_chart}"/></a:graphicData></a:graphic>'
            '</wp:inline></w:drawing>')
        run = document.add_paragraph().add_run()
        run._r.append(drawing)
        return drawing
    except Exception:                       # pragma: no cover - never crash the export
        return None


# ── public API ────────────────────────────────────────────────────────────────
def add_bar_chart(document, categories, values, title, color='2E75B6', series_name=None):
    """Native clustered COLUMN chart (cash flow, cost bars, calendar histogram).

    Returns the drawing element on success, ``None`` on any bad input."""
    if document is None or not categories or not values:
        return None
    cats = list(categories)
    vals = [_num(v) for v in values]
    if len(cats) != len(vals) or any(v is None for v in vals):
        return None
    col = _hex(color, '2E75B6')
    name = series_name or (title or 'Series 1')

    def build(rid):
        dpts = ''.join(
            f'<c:dPt><c:idx val="{i}"/><c:invertIfNegative val="0"/><c:bubble3D val="0"/>'
            f'<c:spPr><a:solidFill><a:srgbClr val="{col}"/></a:solidFill></c:spPr></c:dPt>'
            for i in range(len(vals)))
        ser = (f'<c:ser><c:idx val="0"/><c:order val="0"/>{_tx_ref(name, "B")}'
               f'<c:spPr><a:solidFill><a:srgbClr val="{col}"/></a:solidFill></c:spPr>'
               f'{dpts}{_cat_ref(cats)}{_val_ref(vals, "B")}</c:ser>')
        return (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<c:chartSpace {_C_NS}><c:chart>{_title_el(title)}<c:plotArea><c:layout/>'
            f'<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/>'
            f'<c:varyColors val="0"/>{ser}<c:gapWidth val="60"/>'
            f'<c:axId val="111"/><c:axId val="222"/></c:barChart>'
            f'<c:catAx><c:axId val="111"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="b"/><c:crossAx val="222"/></c:catAx>'
            f'<c:valAx><c:axId val="222"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="l"/><c:crossAx val="111"/></c:valAx>'
            f'</c:plotArea><c:plotVisOnly val="1"/></c:chart>{_external_data(rid)}'
            f'</c:chartSpace>')

    return _inject(document, build, cats, [(name, vals)])


def add_bar_chart_stacked(document, categories, series, title):
    """Native STACKED COLUMN chart (calendar net-working vs non-working).

    ``series`` is a list of dicts ``{'name', 'values', 'color'}`` — e.g. green
    working (#22C55E) + red non-working (#EF4444). Returns the drawing element or
    ``None`` on bad input."""
    if document is None or not categories or not series:
        return None
    cats = list(categories)
    clean = []
    for i, s in enumerate(series):
        s = s or {}
        vals = s.get('values')
        if not vals:
            return None
        vals = [_num(v) for v in vals]
        if len(vals) != len(cats) or any(v is None for v in vals):
            return None
        default = '22C55E' if i == 0 else ('EF4444' if i == 1 else '2E75B6')
        clean.append({'name': s.get('name') or f'Series {i + 1}',
                      'values': vals,
                      'color': _hex(s.get('color'), default)})

    def build(rid):
        sers = ''
        for i, s in enumerate(clean):
            col = s['color']
            letter = _col_letter(i)
            dpts = ''.join(
                f'<c:dPt><c:idx val="{j}"/><c:invertIfNegative val="0"/><c:bubble3D val="0"/>'
                f'<c:spPr><a:solidFill><a:srgbClr val="{col}"/></a:solidFill></c:spPr></c:dPt>'
                for j in range(len(s['values'])))
            sers += (f'<c:ser><c:idx val="{i}"/><c:order val="{i}"/>'
                     f'{_tx_ref(s["name"], letter)}'
                     f'<c:spPr><a:solidFill><a:srgbClr val="{col}"/></a:solidFill></c:spPr>'
                     f'{dpts}{_cat_ref(cats)}{_val_ref(s["values"], letter)}</c:ser>')
        return (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<c:chartSpace {_C_NS}><c:chart>{_title_el(title)}<c:plotArea><c:layout/>'
            f'<c:barChart><c:barDir val="col"/><c:grouping val="stacked"/>'
            f'<c:varyColors val="0"/>{sers}<c:gapWidth val="60"/><c:overlap val="100"/>'
            f'<c:axId val="111"/><c:axId val="222"/></c:barChart>'
            f'<c:catAx><c:axId val="111"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="b"/><c:crossAx val="222"/></c:catAx>'
            f'<c:valAx><c:axId val="222"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="l"/><c:crossAx val="111"/></c:valAx>'
            f'</c:plotArea><c:plotVisOnly val="1"/></c:chart>{_external_data(rid)}'
            f'</c:chartSpace>')

    return _inject(document, build,
                   cats, [(s['name'], s['values']) for s in clean])


def add_pie_chart(document, labels, values, title, colors=None):
    """Native DOUGHNUT chart (contract-value donut).

    Each slice keeps its palette colour via a per-point ``<c:dPt>`` solidFill.
    Returns the drawing element or ``None`` on bad input."""
    if document is None or not labels or not values:
        return None
    labs = list(labels)
    vals = [_num(v) for v in values]
    if len(labs) != len(vals) or any(v is None for v in vals):
        return None
    palette = [_hex(c, _PIE_PALETTE[i % len(_PIE_PALETTE)])
               for i, c in enumerate(colors)] if colors else list(_PIE_PALETTE)

    def build(rid):
        dpts = ''.join(
            f'<c:dPt><c:idx val="{i}"/><c:bubble3D val="0"/>'
            f'<c:spPr><a:solidFill>'
            f'<a:srgbClr val="{palette[i % len(palette)]}"/></a:solidFill></c:spPr></c:dPt>'
            for i in range(len(vals)))
        ser = (f'<c:ser><c:idx val="0"/><c:order val="0"/>{_tx_ref(title or "Series 1", "B")}'
               f'{dpts}{_cat_ref(labs)}{_val_ref(vals, "B")}</c:ser>')
        return (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<c:chartSpace {_C_NS}><c:chart>{_title_el(title)}<c:plotArea><c:layout/>'
            f'<c:doughnutChart><c:varyColors val="1"/>{ser}'
            f'<c:firstSliceAng val="0"/><c:holeSize val="50"/></c:doughnutChart>'
            f'</c:plotArea><c:plotVisOnly val="1"/></c:chart>{_external_data(rid)}'
            f'</c:chartSpace>')

    return _inject(document, build, labs, [(title or 'Series 1', vals)])


# ══════════════════════════════════════════════════════════════════════════════
# SLICE B — NATIVE, EDITABLE WBS org-chart + Sequence process (grouped shapes)
# ══════════════════════════════════════════════════════════════════════════════
# Word charts (above) cover data plots, but a WBS hierarchy and a process flow are
# *diagrams*, not plots — Word draws those as SmartArt or grouped shapes. Real
# SmartArt needs four schema-strict ``dgm`` parts (data/layout/colours/quickStyle)
# plus a drawing fallback; the smallest structural slip makes Word offer to
# "repair" the file. So these two builders emit the reliable, equally-editable
# alternative: a single inline ``<w:drawing>`` holding a ``wpg:wgp`` group of
# ``wps:wsp`` shapes — rounded-rectangle text boxes (the WBS boxes / the chevrons)
# and thin ``line`` shapes (the elbow connectors). The user can click any box,
# drag it, restyle it, or edit its text, exactly like SmartArt, and NOTHING is
# rasterised — no picture part is ever added. Colours and box/chevron geometry
# mirror ``docx_charts.wbs_smartart_svg`` / ``sequence_flow_svg`` so the Word file
# keeps today's look.
#
# Both functions are None-safe and project-agnostic: an empty tree / empty step
# list (or any internal error) returns ``None`` and never raises.

_EMU_PER_PX = 9525                          # 96-dpi pixel → EMU

# per-depth WBS palette + chevron palette — match docx_charts (sans the leading '#')
_WBS_PALETTE_HEX = ['1F4E79', '2E75B6', '4472C4', '5B9BD5', 'DEEAF6']
_WBS_ACCENT = '2E75B6'
_SEQ_PALETTE_HEX = ['1F4E79', '2E75B6', '4472C4', '5B9BD5', '41719C', '8FAADC']

# namespaces the grouped-shape drawing needs (declared on the <w:drawing> root)
_WPG_URI = 'http://schemas.microsoft.com/office/word/2010/wordprocessingGroup'
_DRAW_NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"')


def _emu(px):
    """Pixels (report geometry) → EMU (Word drawing units)."""
    try:
        return int(round(float(px) * _EMU_PER_PX))
    except (TypeError, ValueError):
        return 0


def _clip(name, n=20):
    """Trim a label to ``n`` chars with an ellipsis (mirrors docx_charts._clip)."""
    name = '' if name is None else str(name)
    return name if len(name) <= n else name[:n - 1] + '…'


def _next_id(document):
    """Smallest id above every drawing/shape id already in the document, so new
    frames and shapes never clash (Word rejects duplicate ``wp:docPr`` ids)."""
    try:
        xml = document.element.xml
        ids = [int(m) for m in re.findall(
            r'<(?:wp:docPr|wps:cNvPr|pic:cNvPr|a:cNvPr|wpg:cNvPr) id="(\d+)"', xml)]
        return (max(ids) + 1) if ids else 1
    except Exception:                       # pragma: no cover - defensive
        return 1


def _wps_box(counter, name, x, y, w, h, fill, line, tcol, text, sz=17, prst='roundRect'):
    """One filled text-box shape (a WBS node or a chevron). ``counter`` is a
    one-item list used as a mutable shape-id allocator."""
    sid = counter[0]
    counter[0] += 1
    ln = (f'<a:ln w="9525"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>'
          if line else '<a:ln><a:noFill/></a:ln>')
    return (
        f'<wps:wsp><wps:cNvPr id="{sid}" name="{_xesc(name) or ("Shape %d" % sid)}"/>'
        f'<wps:cNvSpPr/>'
        f'<wps:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="{prst}"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>{ln}</wps:spPr>'
        f'<wps:txbx><w:txbxContent><w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
        f'<w:r><w:rPr><w:b/><w:color w:val="{tcol}"/><w:sz w:val="{sz * 2}"/>'
        f'<w:szCs w:val="{sz * 2}"/></w:rPr>'
        f'<w:t xml:space="preserve">{_xesc(text)}</w:t></w:r></w:p></w:txbxContent></wps:txbx>'
        f'<wps:bodyPr rot="0" anchor="ctr" lIns="36000" rIns="36000" '
        f'tIns="18000" bIns="18000"/></wps:wsp>')


def _wps_line(counter, x, y, cx, cy, color):
    """One straight line-connector shape (an elbow segment)."""
    sid = counter[0]
    counter[0] += 1
    return (
        f'<wps:wsp><wps:cNvPr id="{sid}" name="Connector {sid}"/><wps:cNvSpPr/>'
        f'<wps:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
        f'<a:ln w="9525"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln>'
        f'</wps:spPr><wps:bodyPr/></wps:wsp>')


def _group_drawing(document, shapes_xml, base_id, w_emu, h_emu):
    """Wrap the shape XML in a ``wpg:wgp`` group inside an inline ``<w:drawing>``,
    append it to a fresh run, and return the drawing element."""
    drawing = parse_xml(
        f'<w:drawing {_DRAW_NS}>'
        f'<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{w_emu}" cy="{h_emu}"/>'
        f'<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="{base_id}" name="Diagram {base_id}"/>'
        f'<wp:cNvGraphicFramePr/>'
        f'<a:graphic><a:graphicData uri="{_WPG_URI}">'
        f'<wpg:wgp><wpg:cNvGrpSpPr/>'
        f'<wpg:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{w_emu}" cy="{h_emu}"/>'
        f'<a:chOff x="0" y="0"/><a:chExt cx="{w_emu}" cy="{h_emu}"/></a:xfrm></wpg:grpSpPr>'
        f'{shapes_xml}</wpg:wgp></a:graphicData></a:graphic>'
        f'</wp:inline></w:drawing>')
    run = document.add_paragraph().add_run()
    run._r.append(drawing)
    return drawing


def add_org_chart(document, root_node):
    """Native WBS org-chart: a top box over its child boxes joined by elbow line
    connectors, with the per-depth blue palette (#1F4E79/#2E75B6/#4472C4/#5B9BD5/
    #DEEAF6) — the editable Word twin of ``docx_charts.wbs_smartart_svg``.

    ``root_node`` = ``{'name', 'children': [...]}``. Returns the drawing element,
    or ``None`` on a missing document / empty tree / any internal error."""
    if document is None or not root_node:
        return None
    if not root_node.get('name') and not root_node.get('children'):
        return None
    try:
        root = wbs_chart._copy(root_node)   # never mutate the caller's tree
        wbs_chart._layout(root, 0, [0])
        nodes = []
        wbs_chart._collect(root, nodes)
        if not nodes:
            return None
        BOX_W, BOX_H = wbs_chart.BOX_W, wbs_chart.BOX_H
        X_STEP, Y_STEP, PAD = wbs_chart.X_STEP, wbs_chart.Y_STEP, wbs_chart.PAD
        max_x = max((n['_x'] for n in nodes), default=0)
        max_d = max((n['_y'] for n in nodes), default=0)
        width_px = max_x * X_STEP + BOX_W + PAD * 2
        height_px = max_d * Y_STEP + BOX_H + PAD * 2

        def bx(n):
            return PAD + n['_x'] * X_STEP

        def by(n):
            return PAD + n['_y'] * Y_STEP

        counter = [_next_id(document)]
        base_id = counter[0]
        counter[0] += 1                     # reserve base_id for the frame's docPr

        shapes = []
        # connectors first so the boxes paint over them
        for n in nodes:
            pcx = bx(n) + BOX_W / 2.0
            for k in n.get('children') or []:
                kcx = bx(k) + BOX_W / 2.0
                mid = by(n) + BOX_H + (Y_STEP - BOX_H) / 2.0
                bottom = by(n) + BOX_H
                shapes.append(_wps_line(counter, _emu(pcx), _emu(bottom),
                                        0, _emu(mid - bottom), _WBS_ACCENT))
                x_l, x_r = sorted((pcx, kcx))
                shapes.append(_wps_line(counter, _emu(x_l), _emu(mid),
                                        _emu(x_r - x_l), 0, _WBS_ACCENT))
                shapes.append(_wps_line(counter, _emu(kcx), _emu(mid),
                                        0, _emu(by(k) - mid), _WBS_ACCENT))
        # boxes
        for n in nodes:
            depth = int(n['_y'])
            fill = _WBS_PALETTE_HEX[min(depth, len(_WBS_PALETTE_HEX) - 1)]
            tcol = '12303D' if depth >= len(_WBS_PALETTE_HEX) - 1 else 'FFFFFF'
            shapes.append(_wps_box(
                counter, n.get('name') or '', _emu(bx(n)), _emu(by(n)),
                _emu(BOX_W), _emu(BOX_H), fill, _WBS_ACCENT, tcol,
                _clip(n.get('name'))))

        return _group_drawing(document, ''.join(shapes), base_id,
                              _emu(width_px), _emu(height_px))
    except Exception:                       # pragma: no cover - never crash the export
        return None


def add_process(document, steps):
    """Native Sequence 'Basic Process': a left-to-right row of chevrons in the blue
    palette — the editable Word twin of ``docx_charts.sequence_flow_svg``. The first
    step is a home-plate pentagon, the rest are chevrons.

    ``steps`` = ``[str, ...]``. Returns the drawing element, or ``None`` on a missing
    document / empty step list / any internal error."""
    if document is None or not steps:
        return None
    clean = [str(s) for s in steps if s is not None and str(s).strip() != '']
    if not clean:
        return None
    try:
        BW, BH, GAP = 150, 56, 6
        top = 8
        n = len(clean)
        width_px = n * (BW + GAP) - GAP + 4
        height_px = top + BH + 8

        counter = [_next_id(document)]
        base_id = counter[0]
        counter[0] += 1

        shapes = []
        for i, step in enumerate(clean):
            x = i * (BW + GAP)
            col = _SEQ_PALETTE_HEX[i % len(_SEQ_PALETTE_HEX)]
            prst = 'homePlate' if i == 0 else 'chevron'
            shapes.append(_wps_box(
                counter, step, _emu(x), _emu(top), _emu(BW), _emu(BH),
                col, None, 'FFFFFF', _clip(step, 18), sz=10, prst=prst))

        return _group_drawing(document, ''.join(shapes), base_id,
                              _emu(width_px), _emu(height_px))
    except Exception:                       # pragma: no cover - never crash the export
        return None
