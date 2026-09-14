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


def _vstr(v):
    """Serialise a numeric cache value WITHOUT the 6-significant-figure rounding that
    ``'%g'`` inflicts on large numbers (e.g. 916262587.95 → '9.16263e+08', which Word
    then reads back as 916263000). Integers print as integers; non-integers keep full
    round-trip precision so a data label formatted '#,##0' can show the exact figure."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return '0'
    if f != f:                              # NaN
        return '0'
    return str(int(f)) if f == int(f) else repr(f)


def _val_ref(vals, col_letter):
    pts = ''.join(f'<c:pt idx="{i}"><c:v>{_vstr(v)}</c:v></c:pt>'
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
_WBS_LINE = '1F4E79'                        # dark navy org-chart connector (Ibrahim: the
#                                             WBS bracket lines must be clearly visible)
_LINE_EMU = 12700                           # ~1pt connector thickness. A connector MUST have
#   a non-zero extent in BOTH axes: Word silently drops any shape whose bounding box is
#   zero-width or zero-height, which is why the old zero-extent prst="line" connectors never
#   appeared (the boxes, with real extents, did) — see _wps_line.
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
        # wrap="square" lets long names flow onto 2 lines; <a:normAutofit/> shrinks the
        # text to fit the box (never clipped); tight insets give the text the whole box.
        f'<wps:bodyPr rot="0" wrap="square" anchor="ctr" lIns="9144" rIns="9144" '
        f'tIns="4572" bIns="4572"><a:normAutofit/></wps:bodyPr></wps:wsp>')


def _wps_line(counter, x, y, cx, cy, color, thick=_LINE_EMU):
    """One straight org-chart connector segment, drawn as a THIN FILLED RECTANGLE.

    ``(x, y)`` is the segment's start, ``(cx, cy)`` its signed run in EMU; for an
    axis-aligned org-chart bracket exactly one of ``cx``/``cy`` is 0.

    A ``prst="line"`` shape whose bounding box is zero-width (``cx=0``, a vertical drop)
    or zero-height (``cy=0``, a horizontal bus) is silently NOT rendered by Microsoft
    Word — which is why the old connectors vanished while the boxes (real extents on both
    axes) stayed. A thin filled ``rect`` given a small non-zero thickness on the collapsed
    axis renders reliably, looks identical to a hairline connector, and is still a native,
    click-to-edit Word shape (no picture)."""
    sid = counter[0]
    counter[0] += 1
    x0, y0, w, h = int(x), int(y), int(cx), int(cy)
    if w < 0:                               # normalise to a top-left origin
        x0 += w; w = -w
    if h < 0:
        y0 += h; h = -h
    if w == 0:                              # vertical segment → widen it, keep it centred
        w = thick; x0 -= thick // 2
    if h == 0:                              # horizontal segment → thicken it, keep centred
        h = thick; y0 -= thick // 2
    return (
        f'<wps:wsp><wps:cNvPr id="{sid}" name="Connector {sid}"/><wps:cNvSpPr/>'
        f'<wps:spPr><a:xfrm><a:off x="{x0}" y="{y0}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        f'<a:ln><a:noFill/></a:ln>'
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


def _org_vertical(document, root):
    """Vertical (indented) WBS layout — used for a big tree that would overflow the
    page horizontally (Ibrahim's note). Every node is a wide box on its own row,
    indented by depth and joined by elbow guides, so long labels read on one line."""
    ROW_H, INDENT, BOX_W, BOX_H, PAD = 33, 26, 322, 27, 16
    rowof, seq = {}, []

    def dfs(n, depth):
        rowof[id(n)] = len(seq)
        seq.append((n, depth))
        for k in (n.get('children') or []):
            dfs(k, depth + 1)

    dfs(root, 0)
    if not seq:
        return None
    max_depth = max(d for _, d in seq)
    total_w = PAD + max_depth * INDENT + BOX_W + PAD
    total_h = PAD + len(seq) * ROW_H + PAD

    def x_of(depth):
        return PAD + depth * INDENT

    def y_of(node):
        return PAD + rowof[id(node)] * ROW_H

    counter = [_next_id(document)]
    base_id = counter[0]
    counter[0] += 1
    shapes = []
    for n, depth in seq:                       # elbow guides first (boxes paint over)
        kids = n.get('children') or []
        if not kids:
            continue
        gx = x_of(depth) + INDENT / 2.0
        top = y_of(n) + BOX_H
        last_cy = y_of(kids[-1]) + BOX_H / 2.0
        shapes.append(_wps_line(counter, _emu(gx), _emu(top), 0, _emu(last_cy - top), _WBS_LINE))
        for k in kids:
            cy = y_of(k) + BOX_H / 2.0
            shapes.append(_wps_line(counter, _emu(gx), _emu(cy),
                                    _emu(x_of(depth + 1) - gx), 0, _WBS_LINE))
    for n, depth in seq:
        fill = _WBS_PALETTE_HEX[min(depth, len(_WBS_PALETTE_HEX) - 1)]
        tcol = '12303D' if depth >= len(_WBS_PALETTE_HEX) - 1 else 'FFFFFF'
        shapes.append(_wps_box(
            counter, n.get('name') or '', _emu(x_of(depth)), _emu(y_of(n)),
            _emu(BOX_W), _emu(BOX_H), fill, _WBS_ACCENT, tcol,
            n.get('name') or '', sz=11))
    return _group_drawing(document, ''.join(shapes), base_id, _emu(total_w), _emu(total_h))


def add_org_chart(document, root_node):
    """Native WBS org-chart. Small trees draw as a top-down box org-chart; a big tree
    (would overflow the page width) switches to a VERTICAL indented layout so labels
    stay readable. Per-depth blue palette (#1F4E79/#2E75B6/#4472C4/#5B9BD5/#DEEAF6) —
    the editable Word twin of ``docx_charts.wbs_smartart_svg``.

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
        BOX_W = wbs_chart.BOX_W
        BOX_H = wbs_chart.BOX_H + 18         # taller boxes (from the row whitespace) so
        #                                      wrapped names fit clearly; the row step is
        #                                      unchanged, so the chart barely grows.
        X_STEP, Y_STEP, PAD = wbs_chart.X_STEP, wbs_chart.Y_STEP, wbs_chart.PAD
        max_x = max((n['_x'] for n in nodes), default=0)
        max_d = max((n['_y'] for n in nodes), default=0)
        width_px = max_x * X_STEP + BOX_W + PAD * 2
        # Keep the top-down org-chart only for a small SHALLOW overview; anything deeper
        # or wide switches to the vertical indented layout, where each box gets a full
        # row so the labels read clearly (Ibrahim's note — big charts go vertical).
        if max_d >= 2 or width_px > 560 or len(nodes) > 8:
            return _org_vertical(document, root)
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
                                        0, _emu(mid - bottom), _WBS_LINE))
                x_l, x_r = sorted((pcx, kcx))
                shapes.append(_wps_line(counter, _emu(x_l), _emu(mid),
                                        _emu(x_r - x_l), 0, _WBS_LINE))
                shapes.append(_wps_line(counter, _emu(kcx), _emu(mid),
                                        0, _emu(by(k) - mid), _WBS_LINE))
        # boxes
        for n in nodes:
            depth = int(n['_y'])
            fill = _WBS_PALETTE_HEX[min(depth, len(_WBS_PALETTE_HEX) - 1)]
            tcol = '12303D' if depth >= len(_WBS_PALETTE_HEX) - 1 else 'FFFFFF'
            shapes.append(_wps_box(
                counter, n.get('name') or '', _emu(bx(n)), _emu(by(n)),
                _emu(BOX_W), _emu(BOX_H), fill, _WBS_ACCENT, tcol,
                n.get('name') or '', sz=11))

        return _group_drawing(document, ''.join(shapes), base_id,
                              _emu(width_px), _emu(height_px))
    except Exception:                       # pragma: no cover - never crash the export
        return None


def _process_vertical(document, steps):
    """Vertical process — used for many steps that would overflow horizontally: wide
    boxes stacked top-to-bottom with a down-arrow between, labels on their own row."""
    BOX_W, BOX_H, GAP, PAD = 322, 34, 22, 8
    n = len(steps)
    total_w = PAD + BOX_W + PAD
    total_h = PAD + n * BOX_H + (n - 1) * GAP + PAD
    counter = [_next_id(document)]
    base_id = counter[0]
    counter[0] += 1
    shapes = []
    for i, step in enumerate(steps):
        y = PAD + i * (BOX_H + GAP)
        col = _SEQ_PALETTE_HEX[i % len(_SEQ_PALETTE_HEX)]
        shapes.append(_wps_box(counter, step, _emu(PAD), _emu(y), _emu(BOX_W), _emu(BOX_H),
                               col, None, 'FFFFFF', _clip(step, 60), sz=11, prst='roundRect'))
        if i < n - 1:                          # down-arrow to the next step
            aw = 18
            ax = PAD + BOX_W / 2.0 - aw / 2.0
            shapes.append(_wps_box(counter, '', _emu(ax), _emu(y + BOX_H + 2),
                                   _emu(aw), _emu(GAP - 4), _SEQ_PALETTE_HEX[0], None,
                                   'FFFFFF', '', sz=6, prst='downArrow'))
    return _group_drawing(document, ''.join(shapes), base_id, _emu(total_w), _emu(total_h))


def add_process(document, steps):
    """Native Sequence 'Basic Process': a left-to-right row of chevrons in the blue
    palette — the editable Word twin of ``docx_charts.sequence_flow_svg``. The first
    step is a home-plate pentagon, the rest are chevrons. A long chain (would overflow
    horizontally) stacks VERTICALLY with down-arrows instead (Ibrahim's note).

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
        if width_px > 640 or n > 6:            # long chain → stack vertically
            return _process_vertical(document, clean)
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
                col, None, 'FFFFFF', _clip(step, 30), sz=10, prst=prst))

        return _group_drawing(document, ''.join(shapes), base_id,
                              _emu(width_px), _emu(height_px))
    except Exception:                       # pragma: no cover - never crash the export
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SLICE C — NATIVE charts + org-charts for the redesigned 10-section narrative.
# Ported verbatim from the approved standalone builder (build_narrative_v2.py):
#   • add_hbar          — horizontal bar chart (§6 Contract Value, §7 discipline %)
#   • add_calendar_hist — stacked green/red histogram with net-working-day labels (§8.2)
#   • add_org_flat      — horizontal root→branches org-chart WITH connectors (§9.1)
#   • add_org_cols      — horizontal per-branch org-chart, L2→L3(→L4) WITH connectors (§9.2)
# Every one is native/editable (a real c:chartSpace or a wpg:wgp shape group — never a
# picture) and None-safe: any bad input / internal error returns None, never raises.
# ══════════════════════════════════════════════════════════════════════════════
def add_hbar(document, categories, values, title, color='1F4E79', name='Series',
             num_fmt=None):
    """Native horizontal BAR chart (``barDir='bar'``) — the editable Word twin of the
    HTML horizontal-bar list. Returns the drawing element, or ``None`` on bad input.

    ``num_fmt`` (e.g. ``'#,##0'``) sets the data-label AND value-axis number format so a
    large exact amount (e.g. a 916,262,588 contract value) shows with thousands
    separators and no rounding, instead of the General/scientific default."""
    if document is None or not categories or values is None:
        return None
    cats = list(categories)
    vals = [_num(v) for v in values]
    if not cats or len(cats) != len(vals) or any(v is None for v in vals):
        return None
    col = _hex(color, '1F4E79')
    lbl_fmt = (f'<c:numFmt formatCode="{_xesc(num_fmt)}" sourceLinked="0"/>'
               if num_fmt else '')

    def build(rid):
        dpts = ''.join(
            f'<c:dPt><c:idx val="{i}"/><c:invertIfNegative val="0"/><c:bubble3D val="0"/>'
            f'<c:spPr><a:solidFill><a:srgbClr val="{col}"/></a:solidFill></c:spPr></c:dPt>'
            for i in range(len(vals)))
        ser = (f'<c:ser><c:idx val="0"/><c:order val="0"/>{_tx_ref(name, "B")}'
               f'<c:spPr><a:solidFill><a:srgbClr val="{col}"/></a:solidFill></c:spPr>'
               f'<c:dLbls>{lbl_fmt}<c:showLegendKey val="0"/><c:showVal val="1"/><c:showCatName val="0"/>'
               f'<c:showSerName val="0"/><c:showPercent val="0"/><c:showBubbleSize val="0"/></c:dLbls>'
               f'{dpts}{_cat_ref(cats)}{_val_ref(vals, "B")}</c:ser>')
        return (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<c:chartSpace {_C_NS}><c:chart>{_title_el(title)}<c:plotArea><c:layout/>'
            f'<c:barChart><c:barDir val="bar"/><c:grouping val="clustered"/>'
            f'<c:varyColors val="0"/>{ser}<c:gapWidth val="60"/>'
            f'<c:axId val="111"/><c:axId val="222"/></c:barChart>'
            f'<c:catAx><c:axId val="111"/><c:scaling><c:orientation val="maxMin"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="l"/><c:crossAx val="222"/></c:catAx>'
            f'<c:valAx><c:axId val="222"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
            f'<c:delete val="0"/><c:axPos val="b"/>{lbl_fmt}<c:crossAx val="111"/></c:valAx>'
            f'</c:plotArea><c:plotVisOnly val="1"/></c:chart>{_external_data(rid)}'
            f'</c:chartSpace>')

    return _inject(document, build, cats, [(name, vals)])


def add_calendar_hist(document, categories, working, nonworking,
                      title='Working / non-working days by month'):
    """Native STACKED histogram: net-working days (green, bottom) + non-working days
    (red, top), matching the on-screen / PDF colours (working #1F7A3D, non-working
    #B23030). A bottom two-item LEGEND names the colours ("Working days" /
    "Non-working days"), and the NET-WORKING-DAYS total is labelled ABOVE each month's
    stacked column (§8.2). Returns the drawing element, or ``None`` on bad input.

    The top-of-bar total is carried by a third, invisible zero-height series stacked on
    top: it adds no height, is hidden from the legend, and shows the working-days figure
    as a custom label at the very top of each column (the on-screen ".v" number above
    the bar). Colours mirror ``html.py`` (._cal_hist / .callegend)."""
    if document is None or not categories:
        return None
    cats = list(categories)
    wk = [_num(v) for v in (working or [])]
    nw = [_num(v) for v in (nonworking or [])]
    if (len(wk) != len(cats) or len(nw) != len(cats)
            or any(v is None for v in wk) or any(v is None for v in nw)):
        return None
    zeros = [0 for _ in cats]
    GREEN, RED, LABEL = '1F7A3D', 'B23030', '17457A'   # match html gseg / rseg / .v

    def seg(idx, nm, vals, colr, letter):
        """A plain coloured stacked segment (no data labels)."""
        dpts = ''.join(f'<c:dPt><c:idx val="{j}"/><c:invertIfNegative val="0"/>'
                       f'<c:bubble3D val="0"/><c:spPr><a:solidFill>'
                       f'<a:srgbClr val="{colr}"/></a:solidFill></c:spPr></c:dPt>'
                       for j in range(len(vals)))
        return (f'<c:ser><c:idx val="{idx}"/><c:order val="{idx}"/>{_tx_ref(nm, letter)}'
                f'<c:spPr><a:solidFill><a:srgbClr val="{colr}"/></a:solidFill></c:spPr>'
                f'{dpts}{_cat_ref(cats)}{_val_ref(vals, letter)}</c:ser>')

    def topper(idx, letter):
        """Invisible zero-height top series carrying the net-working-days number ABOVE
        each column, via a per-point custom label."""
        dlbls = ''.join(
            f'<c:dLbl><c:idx val="{j}"/>'
            f'<c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p>'
            f'<a:pPr><a:defRPr b="1" sz="800"><a:solidFill><a:srgbClr val="{LABEL}"/></a:solidFill></a:defRPr></a:pPr>'
            f'<a:r><a:rPr lang="en-US" b="1" sz="800"><a:solidFill><a:srgbClr val="{LABEL}"/></a:solidFill></a:rPr>'
            f'<a:t>{int(round(wk[j]))}</a:t></a:r></a:p></c:rich></c:tx>'
            f'<c:dLblPos val="inEnd"/>'
            f'<c:showLegendKey val="0"/><c:showVal val="0"/><c:showCatName val="0"/>'
            f'<c:showSerName val="0"/><c:showPercent val="0"/><c:showBubbleSize val="0"/></c:dLbl>'
            for j in range(len(cats)))
        dl = (f'<c:dLbls>{dlbls}<c:dLblPos val="inEnd"/>'
              f'<c:showLegendKey val="0"/><c:showVal val="0"/><c:showCatName val="0"/>'
              f'<c:showSerName val="0"/><c:showPercent val="0"/><c:showBubbleSize val="0"/></c:dLbls>')
        return (f'<c:ser><c:idx val="{idx}"/><c:order val="{idx}"/>{_tx_ref("Net working days", letter)}'
                f'<c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>'
                f'{dl}{_cat_ref(cats)}{_val_ref(zeros, letter)}</c:ser>')

    def build(rid):
        s = (seg(0, 'Working days', wk, GREEN, 'B') +
             seg(1, 'Non-working days', nw, RED, 'C') +
             topper(2, 'D'))
        # bottom legend, but hide the invisible topper series' entry (idx 2)
        legend = ('<c:legend><c:legendPos val="b"/>'
                  '<c:legendEntry><c:idx val="2"/><c:delete val="1"/></c:legendEntry>'
                  '<c:overlay val="0"/></c:legend>')
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<c:chartSpace {_C_NS}><c:chart>{_title_el(title)}'
                f'<c:plotArea><c:layout/><c:barChart><c:barDir val="col"/>'
                f'<c:grouping val="stacked"/><c:varyColors val="0"/>{s}'
                f'<c:gapWidth val="55"/><c:overlap val="100"/>'
                f'<c:axId val="111"/><c:axId val="222"/></c:barChart>'
                f'<c:catAx><c:axId val="111"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
                f'<c:delete val="0"/><c:axPos val="b"/><c:crossAx val="222"/></c:catAx>'
                f'<c:valAx><c:axId val="222"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
                f'<c:delete val="0"/><c:axPos val="l"/><c:crossAx val="111"/></c:valAx>'
                f'</c:plotArea>{legend}<c:plotVisOnly val="1"/></c:chart>'
                f'{_external_data(rid)}</c:chartSpace>')

    return _inject(document, build, cats,
                   [('Working days', wk), ('Non-working days', nw),
                    ('Net working days', zeros)])


def add_org_flat(document, root_name, branches, total_w=660):
    """Horizontal org-chart: a root header on top, then the branch boxes in a UNIFORM,
    WRAPPING grid beneath, joined by connector lines from the root (§9.1). Every branch
    box is the SAME width and height and large enough that its full name WRAPS inside
    (never clipped/truncated); rows that overflow the page width wrap to further rows,
    each centred. Native/editable shapes. ``branches`` is a list of branch names.
    Returns the drawing element, or ``None`` on bad input."""
    if document is None or not branches:
        return None
    try:
        names = [('' if b is None else str(b)) for b in branches]
        n = len(names)
        GAP, BW, BH = 12, 150, 54           # uniform branch box (width matches §9.2 boxes)
        per_row = max(1, min(n, (total_w + GAP) // (BW + GAP)))
        rows = (n + per_row - 1) // per_row
        grid_w = per_row * BW + (per_row - 1) * GAP
        RH, bus_gap, row_step = 30, 14, BH + 14
        grid_y = RH + bus_gap + 8
        total_h = grid_y + rows * row_step - (row_step - BH)

        def row_geom(r):
            k = min(per_row, n - r * per_row)
            xoff = (grid_w - (k * BW + (k - 1) * GAP)) // 2
            return k, xoff

        cnt = [_next_id(document)]
        base = cnt[0]
        cnt[0] += 1
        sh = ''
        # root header spans the grid width so a long project title reads in full
        sh += _wps_box(cnt, 'root', _emu(0), _emu(0), _emu(grid_w), _emu(RH),
                       '1F4E79', '1F4E79', 'FFFFFF', str(root_name or 'Project'), sz=11)
        busY = RH + bus_gap
        sh += _wps_line(cnt, _emu(grid_w // 2), _emu(RH), 0, _emu(busY - RH), _WBS_LINE)
        # connect the root bus to the first row of boxes
        k0, xoff0 = row_geom(0)
        ctr0 = [xoff0 + c * (BW + GAP) + BW // 2 for c in range(k0)]
        if k0 > 1:
            sh += _wps_line(cnt, _emu(ctr0[0]), _emu(busY), _emu(ctr0[-1] - ctr0[0]), 0, _WBS_LINE)
        for c in range(k0):
            sh += _wps_line(cnt, _emu(ctr0[c]), _emu(busY), 0, _emu(grid_y - busY), _WBS_LINE)
        for i, nm in enumerate(names):
            r, c = divmod(i, per_row)
            _, xoff = row_geom(r)
            x = xoff + c * (BW + GAP)
            y = grid_y + r * row_step
            sh += _wps_box(cnt, nm, _emu(x), _emu(y), _emu(BW), _emu(BH),
                           'DEEAF6', '9CBCDD', '14324F', nm, sz=9)
        return _group_drawing(document, sh, base, _emu(grid_w), _emu(total_h))
    except Exception:                       # pragma: no cover - never crash the export
        return None


def add_org_cols(document, root_name, columns, total_w=660):
    """Horizontal org-chart with depth (§9.2): a root header, then one COLUMN per Level-2
    node laid out in a UNIFORM, WRAPPING grid; under each L2 its L3 (and L4) boxes are
    stacked in that column, linked by connectors. ``columns`` =
    ``[[l2name, [[l3name, [l4name, …]], …]], …]``.

    Every box — L2, L3 and L4 alike — is the SAME width and height (differing only in
    fill so the level still reads), enlarged enough that its full text WRAPS inside and
    is never clipped/truncated. Columns that overflow the page width wrap to further
    rows (each centred). Native / editable shapes. Returns the drawing element, or
    ``None`` on bad input."""
    if document is None or not columns:
        return None
    try:
        cols = list(columns)
        n = len(cols)
        GAP, CW, BH, VGAP = 12, 150, 30, 8          # uniform box size
        RH, bus_gap, ROW_VGAP = 30, 12, 18
        # per-level fill / border / text colour (uniform SIZE, level shown by colour)
        LVL = {'l2': ('BCD3EA', '9CBCDD', '14324F'),
               'l3': ('E6EEF7', 'CDDDEF', '1F4E79'),
               'l4': ('FFFFFF', 'D3DDEA', '33414D')}

        def col_boxes(col):
            """Flatten one column to a top-to-bottom list of (level, text) boxes."""
            out = [('l2', str((col[0] if col else '') or ''))]
            for entry in (col[1] if len(col) > 1 else []) or []:
                out.append(('l3', str((entry[0] if entry else '') or '')))
                for l4 in (entry[1] if len(entry) > 1 else []) or []:
                    out.append(('l4', str(l4 or '')))
            return out

        colboxes = [col_boxes(c) for c in cols]
        per_row = max(1, min(n, (total_w + GAP) // (CW + GAP)))
        rows = (n + per_row - 1) // per_row
        grid_w = per_row * CW + (per_row - 1) * GAP
        grid_y = RH + bus_gap + 8

        def col_h(cb):
            return len(cb) * BH + (len(cb) - 1) * VGAP

        row_h = [max((col_h(cb) for cb in colboxes[r * per_row:(r + 1) * per_row]),
                     default=BH) for r in range(rows)]

        cnt = [_next_id(document)]
        base = cnt[0]
        cnt[0] += 1
        sh = ''
        sh += _wps_box(cnt, 'root', _emu(0), _emu(0), _emu(grid_w), _emu(RH),
                       '1F4E79', '1F4E79', 'FFFFFF', str(root_name or 'Project'), sz=11)
        busY = RH + bus_gap
        sh += _wps_line(cnt, _emu(grid_w // 2), _emu(RH), 0, _emu(busY - RH), _WBS_LINE)

        y0 = grid_y
        for r in range(rows):
            group = colboxes[r * per_row:(r + 1) * per_row]
            k = len(group)
            xoff = (grid_w - (k * CW + (k - 1) * GAP)) // 2
            ctr = [xoff + c * (CW + GAP) + CW // 2 for c in range(k)]
            if r == 0:                              # bus + drops from the root to row 1
                if k > 1:
                    sh += _wps_line(cnt, _emu(ctr[0]), _emu(busY),
                                    _emu(ctr[-1] - ctr[0]), 0, _WBS_LINE)
                for c in range(k):
                    sh += _wps_line(cnt, _emu(ctr[c]), _emu(busY), 0, _emu(y0 - busY), _WBS_LINE)
            for c in range(k):
                cx0 = xoff + c * (CW + GAP)
                ccx = cx0 + CW // 2
                y = y0
                for bi, (lvl, txt) in enumerate(group[c]):
                    fill, line, tcol = LVL.get(lvl, LVL['l3'])
                    if bi > 0:                      # connector down from the box above
                        sh += _wps_line(cnt, _emu(ccx), _emu(y - VGAP), 0, _emu(VGAP), _WBS_LINE)
                    sh += _wps_box(cnt, txt, _emu(cx0), _emu(y), _emu(CW), _emu(BH),
                                   fill, line, tcol, txt, sz=9)
                    y += BH + VGAP
            y0 += row_h[r] + ROW_VGAP
        total_h = y0 - ROW_VGAP
        return _group_drawing(document, sh, base, _emu(grid_w), _emu(total_h))
    except Exception:                       # pragma: no cover - never crash the export
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SLICE D — NATIVE, EDITABLE top-down INDENTED WBS box-tree (§9, approved redesign)
# ══════════════════════════════════════════════════════════════════════════════
# The approved §9 look is the classic "tree view": a top-to-bottom flow where every
# node is a box on its own row, indented one step to the RIGHT of its parent, and each
# parent joined to its children by a visible ELBOW — a single vertical line down the
# gutter plus a short horizontal stub into every child's left edge (the last child's
# stub is where the vertical line stops, so no line trails past it). Boxes are colour-
# coded by WBS level so depth reads at a glance. Drawn with the SAME reliable native
# primitives as the org-charts above — ``_wps_box`` for every node, ``_wps_line`` for
# every connector segment (thin filled rects, so zero-extent axes still render) — wrapped
# in one ``_group_drawing`` sized to the whole tree. NEVER a picture; None-safe.
#
# Per-level (fill, border, text) — matches the PDF: lv0 navy #1F4E79 + white text,
# lv1 #BCD3EA, lv2 #DEEAF6, lv3 #E6EEF7, lv4 white with a light border.
_WBS_TREE_LEVELS = [
    ('1F4E79', '1F4E79', 'FFFFFF'),         # lv0 — project root (navy, white text)
    ('BCD3EA', '9CBCDD', '14324F'),         # lv1 — major WBS branch (blue)
    ('DEEAF6', 'B8CFE8', '14324F'),         # lv2 — Level-2 (light blue)
    ('E6EEF7', 'CDDDEF', '1F4E79'),         # lv3 — Level-3
    ('FFFFFF', 'D3DDEA', '33414D'),         # lv4 — Level-4 (white, light border)
]

# tree geometry (px; converted to EMU via _emu). Uniform box width/height; each depth
# indented one INDENT; rows stepped by ROW_H (a small gap between boxes). The gutter for a
# parent's elbow sits GUTTER px right of the parent's left edge, LEFT of the child boxes
# (which start one INDENT right of the parent), so the vertical line never crosses a box.
_TREE_PAD, _TREE_INDENT, _TREE_ROW_H = 10, 28, 30
_TREE_BOX_W, _TREE_BOX_H, _TREE_GUTTER = 388, 24, 12


def add_wbs_tree(document, nodes):
    """Native TOP-DOWN INDENTED WBS box-tree with elbow connectors (§9 redesign).

    ``nodes`` is a list of ROOT node dicts, each ``{'name', 'level', 'children': [...]}``
    (nested). A depth-first walk puts each node on its own ROW in document order
    (``y = PAD + row*ROW_H``); its column is its WBS level (``x = PAD + (level-base)*INDENT``,
    so the shallowest node sits flush-left while colour still tracks the true level). Every
    parent with children gets an elbow: one vertical line down the gutter from just below the
    parent to the last child's vertical centre, plus a horizontal stub from that gutter into
    each child's left edge. Boxes are filled by level (navy root → blue → light-blue → white).

    Returns the drawing element, or ``None`` on a missing document / empty tree / any
    internal error (the caller then falls back to an editable table)."""
    if document is None or not nodes:
        return None
    try:
        seq = []                            # ordered list of node records (DFS / document order)

        def dfs(n):
            try:
                lvl = int(n.get('level'))
            except (TypeError, ValueError):
                lvl = 0
            rec = {'node': n, 'level': lvl, 'row': len(seq)}
            seq.append(rec)
            for k in (n.get('children') or []):
                dfs(k)

        for root in nodes:
            if root:
                dfs(root)
        if not seq:
            return None

        base = min(r['level'] for r in seq)
        max_depth = max(r['level'] - base for r in seq)
        rec_by_id = {id(r['node']): r for r in seq}

        def x_of(level):
            return _TREE_PAD + (level - base) * _TREE_INDENT

        def y_of(row):
            return _TREE_PAD + row * _TREE_ROW_H

        counter = [_next_id(document)]
        base_id = counter[0]
        counter[0] += 1                     # reserve base_id for the group frame's docPr

        shapes = []
        # elbow connectors FIRST so the boxes paint over them
        for rec in seq:
            kids = rec['node'].get('children') or []
            child_recs = [rec_by_id[id(k)] for k in kids if id(k) in rec_by_id]
            if not child_recs:
                continue
            gutter_x = x_of(rec['level']) + _TREE_GUTTER
            parent_bottom = y_of(rec['row']) + _TREE_BOX_H
            last_center = y_of(child_recs[-1]['row']) + _TREE_BOX_H / 2.0
            # vertical line: just below the parent → last child's vertical centre
            shapes.append(_wps_line(counter, _emu(gutter_x), _emu(parent_bottom),
                                    0, _emu(last_center - parent_bottom), _WBS_LINE))
            # horizontal stub into each child's left edge
            for cr in child_recs:
                cy = y_of(cr['row']) + _TREE_BOX_H / 2.0
                shapes.append(_wps_line(counter, _emu(gutter_x), _emu(cy),
                                        _emu(x_of(cr['level']) - gutter_x), 0, _WBS_LINE))
        # boxes (colour-coded by level)
        for rec in seq:
            lvl = rec['level']
            # colour tracks the ABSOLUTE WBS level (lv0 navy … lv4 white), clamped
            fill, border, tcol = _WBS_TREE_LEVELS[min(max(lvl, 0), len(_WBS_TREE_LEVELS) - 1)]
            nm = rec['node'].get('name') or ''
            shapes.append(_wps_box(
                counter, nm, _emu(x_of(lvl)), _emu(y_of(rec['row'])),
                _emu(_TREE_BOX_W), _emu(_TREE_BOX_H), fill, border, tcol, nm, sz=10))

        total_w = _TREE_PAD + max_depth * _TREE_INDENT + _TREE_BOX_W + _TREE_PAD
        total_h = _TREE_PAD + (len(seq) - 1) * _TREE_ROW_H + _TREE_BOX_H + _TREE_PAD
        return _group_drawing(document, ''.join(shapes), base_id,
                              _emu(total_w), _emu(total_h))
    except Exception:                       # pragma: no cover - never crash the export
        return None
