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
import math
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

# DISTINCT discipline colour ramp — MIRRORS ``html.py`` (``_RAMP`` / ``_GREY``) EXACTLY so a
# discipline reads as the SAME colour across the §6 Contract-Value doughnut (add_doughnut) and
# the §7.1 scope composition bar (add_composition_bar), matching the on-screen / PDF report.
# Any discipline literally named "Unclassified" / "Other" is forced to grey regardless of its
# position in the list. ``ramp_colors(names)`` is the single source both charts (and the Word
# legend table in ``docx_writer``) draw from, so swatch == slice == segment colour.
_DISCIPLINE_RAMP = ['1F4E79', '2E9E5B', 'E8A33D', '7A5AA6', 'C0504D', '4BACC6', 'B07AA1']
_DISCIPLINE_GREY = '9AA4B0'


def ramp_color(name, i):
    """The distinct ramp colour for a discipline at position ``i`` — grey when it is
    literally named "Unclassified" / "Other" (mirrors ``html.py._disc_color``)."""
    if str(name or '').strip().lower() in ('unclassified', 'other'):
        return _DISCIPLINE_GREY
    return _DISCIPLINE_RAMP[i % len(_DISCIPLINE_RAMP)]


def ramp_colors(names):
    """The per-name distinct-ramp colour list (grey for Unclassified/Other). The Word legend
    table reuses this so its swatches match the doughnut slices exactly."""
    return [ramp_color(n, i) for i, n in enumerate(names or [])]

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


def _contrast(hex6):
    """A readable label colour ('FFFFFF' on dark fills, '1A1D21' on light fills) for text
    drawn ON a coloured segment/box — perceptual-luminance threshold."""
    c = _hex(hex6, '1F4E79')
    try:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return 'FFFFFF'
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return '1A1D21' if lum > 150 else 'FFFFFF'


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
def add_bar_chart(document, categories, values, title, color='2E75B6', series_name=None,
                  data_labels=False, num_fmt=None):
    """Native clustered COLUMN chart (cash flow, cost bars, calendar histogram).

    ``data_labels`` draws each bar's value just above its top (``dLblPos='outEnd'``) — used by
    the §13/§14 resource histograms so every bar carries its number. ``num_fmt`` (e.g.
    ``'#,##0'``) sets that label's number format. Returns the drawing element on success,
    ``None`` on any bad input."""
    if document is None or not categories or not values:
        return None
    cats = list(categories)
    vals = [_num(v) for v in values]
    if len(cats) != len(vals) or any(v is None for v in vals):
        return None
    col = _hex(color, '2E75B6')
    name = series_name or (title or 'Series 1')
    lbl_fmt = (f'<c:numFmt formatCode="{_xesc(num_fmt)}" sourceLinked="0"/>'
               if num_fmt else '')
    dlbls = (f'<c:dLbls>{lbl_fmt}<c:dLblPos val="outEnd"/>'
             f'<c:showLegendKey val="0"/><c:showVal val="1"/><c:showCatName val="0"/>'
             f'<c:showSerName val="0"/><c:showPercent val="0"/><c:showBubbleSize val="0"/></c:dLbls>'
             if data_labels else '')

    def build(rid):
        dpts = ''.join(
            f'<c:dPt><c:idx val="{i}"/><c:invertIfNegative val="0"/><c:bubble3D val="0"/>'
            f'<c:spPr><a:solidFill><a:srgbClr val="{col}"/></a:solidFill></c:spPr></c:dPt>'
            for i in range(len(vals)))
        ser = (f'<c:ser><c:idx val="0"/><c:order val="0"/>{_tx_ref(name, "B")}'
               f'<c:spPr><a:solidFill><a:srgbClr val="{col}"/></a:solidFill></c:spPr>'
               f'{dpts}{dlbls}{_cat_ref(cats)}{_val_ref(vals, "B")}</c:ser>')
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


# Max on-page width for a grouped drawing (18.4 cm — fits the report's 18.6 cm text column;
# 1 cm = 360000 EMU). A group wider than this is scaled DOWN uniformly (outer ``ext`` < child
# ``chExt``) so the whole drawing — shapes AND their text — shrinks to fit, keeping the exact
# proportions of the approved SVG instead of overflowing the page like a fixed-size drawing.
_MAX_GROUP_W_EMU = 6624000


def _group_drawing(document, shapes_xml, base_id, w_emu, h_emu,
                   disp_w_emu=None, disp_h_emu=None):
    """Wrap the shape XML in a ``wpg:wgp`` group inside an inline ``<w:drawing>``, append it to
    a fresh run, and return the drawing element.

    ``w_emu`` / ``h_emu`` are the child coordinate extent (the space the shape coordinates live
    in). ``disp_w_emu`` / ``disp_h_emu`` (optional) are the group's size on the page; when they
    differ from the child extent Word scales every child — geometry and text alike — by
    ext/chExt, so the drawing shrinks to fit while keeping its proportions. Default (None) =
    render 1:1."""
    dw = int(disp_w_emu) if disp_w_emu else int(w_emu)
    dh = int(disp_h_emu) if disp_h_emu else int(h_emu)
    drawing = parse_xml(
        f'<w:drawing {_DRAW_NS}>'
        f'<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{dw}" cy="{dh}"/>'
        f'<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="{base_id}" name="Diagram {base_id}"/>'
        f'<wp:cNvGraphicFramePr/>'
        f'<a:graphic><a:graphicData uri="{_WPG_URI}">'
        f'<wpg:wgp><wpg:cNvGrpSpPr/>'
        f'<wpg:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{dw}" cy="{dh}"/>'
        f'<a:chOff x="0" y="0"/><a:chExt cx="{int(w_emu)}" cy="{int(h_emu)}"/></a:xfrm>'
        f'</wpg:grpSpPr>'
        f'{shapes_xml}</wpg:wgp></a:graphicData></a:graphic>'
        f'</wp:inline></w:drawing>')
    run = document.add_paragraph().add_run()
    run._r.append(drawing)
    return drawing


def _fit_display(w_emu, h_emu):
    """(disp_w, disp_h) EMU scaled uniformly so the group is at most ``_MAX_GROUP_W_EMU`` wide
    (keeps the SVG aspect ratio; never enlarges)."""
    if w_emu <= _MAX_GROUP_W_EMU:
        return w_emu, h_emu
    scale = _MAX_GROUP_W_EMU / float(w_emu)
    return int(round(w_emu * scale)), int(round(h_emu * scale))


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


def add_chevron_flow(document, labels, palette=None):
    """Native HORIZONTAL chevron flow for §11 Sequence of Work — a home-plate first step
    then chevrons, in the blue sequence palette, white centred labels.

    Layout comes from the SHARED :func:`p6_narrative.util.chevron_layout`, the very same helper
    ``html._chevrons`` uses — so the Word flow and the SVG/PDF flow are identical: same labels,
    same rows, same order, FULL text in both. Each shape is sized to its own wrapped text and
    the whole flow wraps onto MULTIPLE ROWS when a row would exceed the text column, so a long
    label is never truncated and a wide sequence never crushes every chevron into one page-wide
    row. Reuses the same ``_wps_box`` home-plate / chevron shapes (``wrap="square"`` +
    ``normAutofit``), so it is a real editable Word drawing — never a picture. Returns the
    drawing element, or ``None`` on a missing document / empty labels / any internal error."""
    if document is None or not labels:
        return None
    clean = [str(x) for x in labels if x is not None and str(x).strip() != '']
    if not clean:
        return None
    try:
        from p6_narrative.util import chevron_layout
        pal = palette or _SEQ_PALETTE_HEX
        lay = chevron_layout(clean)
        rows = lay['rows']
        if not rows:
            return None
        counter = [_next_id(document)]
        base_id = counter[0]
        counter[0] += 1
        shapes = []
        for row in rows:
            for it in row:
                col = pal[it['i'] % len(pal)]
                prst = 'homePlate' if it['kind'] == 'home' else 'chevron'
                # FULL label (never _clip'd) — the box wraps + normAutofit-fits it; sz is the
                # layout's per-shape font converted px→pt (font_px·0.75), so the shrink the
                # layout already chose is honoured 1:1 with the SVG.
                sz = max(int(round(it['font_px'] * 0.75)), 1)
                shapes.append(_wps_box(
                    counter, it['label'], _emu(it['x']), _emu(it['y']),
                    _emu(it['w']), _emu(it['h']), col, None, 'FFFFFF',
                    it['label'], sz=sz, prst=prst))
        w_emu, h_emu = _emu(lay['width']), _emu(lay['height'])
        # The layout already fits max_width_px; _fit_display is a no-op unless the group still
        # exceeds the page (safety), so multiple rows keep their real size rather than crushing.
        dw, dh = _fit_display(w_emu, h_emu)
        return _group_drawing(document, ''.join(shapes), base_id, w_emu, h_emu, dw, dh)
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


# ══════════════════════════════════════════════════════════════════════════════
# SLICE E — NATIVE, EDITABLE §6 doughnut + §7.1 composition bar as GROUPED SHAPES
# ══════════════════════════════════════════════════════════════════════════════
# The §6 Contract-Value doughnut and the §7.1 scope composition bar are the two charts
# whose APPROVED look lives in ``html.py`` (``_doughnut`` / ``_compbar``) as hand-built
# SVGs. To keep "all formats match Word/PDF/HTML", their Word twins below REPLICATE that
# SVG geometry EXACTLY — pixel-for-pixel, converted px→EMU — drawn as a ``wpg:wgp`` group
# of real ``wps:wsp`` shapes (annular ``a:custGeom`` sectors, ``a:custGeom`` leader
# polylines, ``prstGeom`` ellipses / roundRects, and transparent text boxes). NEVER a
# ``c:chart`` object and NEVER a rasterised picture — the reader can click, drag, restyle,
# recolour and edit the text of every slice, segment and label. Both are None-safe: any
# bad / empty / mismatched / zero-total input returns ``None`` and the writer falls back to
# its editable table / legend.
#
# Angle convention (annular sectors): ``html._polar`` measures degrees CLOCKWISE from 12
# o'clock; DrawingML measures CLOCKWISE from +x (3 o'clock, because y points down) in
# 60000ths of a degree, so DrawingML angle = (svg_angle − 90). ``a:arcTo`` derives the arc
# centre as currentPoint − (wR·cos stAng, hR·sin stAng); we therefore move the pen to the
# arc's exact start point first and set stAng to that point's angle, so the centre lands on
# (cx, cy). A single 100 % slice would be a degenerate 360° arc, so it is drawn instead as a
# full disc ellipse (the white centre hole then makes it read as a ring). Each custGeom /
# text shape spans the WHOLE canvas coordinate frame (off 0,0; ext W×H; path space = W×H
# EMU), so path/point coordinates are absolute canvas EMU and need no per-shape bbox maths.

def _pt(cx, cy, r, deg):
    """Point on a circle, angle in degrees CLOCKWISE from 12 o'clock (mirrors html._polar)."""
    t = math.radians(deg - 90.0)
    return (cx + r * math.cos(t), cy + r * math.sin(t))


def _hp(px):
    """SVG px font-size → Word half-points (px · 0.75 pt/px · 2)."""
    return int(round(px * 1.5))


def _pct_str(p):
    """Percent text with no trailing '.0' on whole numbers (mirrors html._fmt_pct)."""
    try:
        f = float(p)
    except (TypeError, ValueError):
        return ''
    return ('%d' % f) if f == int(f) else ('%.1f' % f)


def _est_w(text, fs_px):
    """A generous one-line width estimate (px) so a centred text box never wraps to 2 lines."""
    return len(str(text)) * fs_px * 0.62 + 10.0


def _roundadj(radius_px, dim_px):
    """roundRect corner-radius adjustment guide (radius as a fraction of the box's side)."""
    try:
        val = int(round(min(max(radius_px / float(dim_px), 0.0), 0.5) * 100000))
    except (TypeError, ValueError, ZeroDivisionError):
        val = 0
    return '<a:gd name="adj" fmla="val %d"/>' % val


def _custgeom_shape(sid, name, path_inner, w_emu, h_emu, fill_hex=None,
                    fill_mode='norm', line_hex=None, line_emu=0):
    """One wps:wsp custom-geometry shape spanning the whole canvas (off 0,0; ext w×h; path
    coord space = w×h EMU, so path coordinates are absolute canvas EMU). Filled sector
    (``fill_hex`` set, ``fill_mode='norm'``) or stroked-only polyline (``fill_hex`` None,
    ``fill_mode='none'``)."""
    fill = (f'<a:solidFill><a:srgbClr val="{fill_hex}"/></a:solidFill>'
            if fill_hex else '<a:noFill/>')
    if line_hex:
        ln = (f'<a:ln w="{int(line_emu)}"><a:solidFill><a:srgbClr val="{line_hex}"/>'
              f'</a:solidFill></a:ln>')
    else:
        ln = '<a:ln><a:noFill/></a:ln>'
    return (
        f'<wps:wsp><wps:cNvPr id="{sid}" name="{_xesc(name) or ("S%d" % sid)}"/>'
        f'<wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{int(w_emu)}" cy="{int(h_emu)}"/></a:xfrm>'
        f'<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/>'
        f'<a:rect l="0" t="0" r="{int(w_emu)}" b="{int(h_emu)}"/>'
        f'<a:pathLst><a:path w="{int(w_emu)}" h="{int(h_emu)}" fill="{fill_mode}">'
        f'{path_inner}</a:path></a:pathLst></a:custGeom>'
        f'{fill}{ln}</wps:spPr><wps:bodyPr/></wps:wsp>')


def _prst_shape(sid, name, x, y, w, h, prst, fill_hex, line_hex=None,
                line_emu=9525, adj=''):
    """One wps:wsp preset-geometry shape (ellipse / rect / roundRect) at an absolute EMU
    bounding box — the doughnut centre hole, small dots and swatches, the composition-bar
    track and segments."""
    fill = (f'<a:solidFill><a:srgbClr val="{fill_hex}"/></a:solidFill>'
            if fill_hex else '<a:noFill/>')
    ln = (f'<a:ln w="{int(line_emu)}"><a:solidFill><a:srgbClr val="{line_hex}"/>'
          f'</a:solidFill></a:ln>' if line_hex else '<a:ln><a:noFill/></a:ln>')
    return (
        f'<wps:wsp><wps:cNvPr id="{sid}" name="{_xesc(name) or ("S%d" % sid)}"/>'
        f'<wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="{int(x)}" y="{int(y)}"/>'
        f'<a:ext cx="{int(w)}" cy="{int(h)}"/></a:xfrm>'
        f'<a:prstGeom prst="{prst}"><a:avLst>{adj}</a:avLst></a:prstGeom>'
        f'{fill}{ln}</wps:spPr><wps:bodyPr/></wps:wsp>')


def _text_shape(sid, name, x, y, w, h, runs, jc='center', anchor='ctr', wrap='square'):
    """One transparent, borderless text box (no fill, no line) holding a single paragraph of
    runs, vertically centred (``anchor='ctr'``). ``runs`` = [(text, sz_halfpt, bold, hex), …].
    Calibri, to match the SVG labels."""
    rtxt = ''
    for text, szhp, bold, col in runs:
        b = '<w:b/>' if bold else ''
        rtxt += (f'<w:r><w:rPr>{b}<w:color w:val="{col}"/>'
                 f'<w:sz w:val="{szhp}"/><w:szCs w:val="{szhp}"/>'
                 f'<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/></w:rPr>'
                 f'<w:t xml:space="preserve">{_xesc(text)}</w:t></w:r>')
    return (
        f'<wps:wsp><wps:cNvPr id="{sid}" name="{_xesc(name) or ("T%d" % sid)}"/>'
        f'<wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="{int(x)}" y="{int(y)}"/>'
        f'<a:ext cx="{int(w)}" cy="{int(h)}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:noFill/><a:ln><a:noFill/></a:ln></wps:spPr>'
        f'<wps:txbx><w:txbxContent><w:p><w:pPr>'
        f'<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
        f'<w:jc w:val="{jc}"/></w:pPr>{rtxt}</w:p></w:txbxContent></wps:txbx>'
        f'<wps:bodyPr rot="0" wrap="{wrap}" anchor="{anchor}" '
        f'lIns="0" tIns="0" rIns="0" bIns="0"><a:noAutofit/></wps:bodyPr></wps:wsp>')


def _center_text(sid, name, cxp, cyp, wp, hp, runs, jc='center'):
    """A text box CENTRED on report point (cxp, cyp) px — for on-ring / in-bar / centre-hole
    labels; (cxp, cyp) is the SVG text's visual centre."""
    return _text_shape(sid, name, _emu(cxp - wp / 2.0), _emu(cyp - hp / 2.0),
                       _emu(wp), _emu(hp), runs, jc=jc)


def _left_text(sid, name, lxp, cyp, wp, hp, runs):
    """A left-aligned text box whose LEFT edge is at lxp and whose text is vertically centred
    on cyp (px) — for the doughnut external leader labels."""
    return _text_shape(sid, name, _emu(lxp), _emu(cyp - hp / 2.0),
                       _emu(wp), _emu(hp), runs, jc='left', wrap='none')


def _annular_sector(sid, name, cx, cy, R, ri, a0, a1, w_emu, h_emu, fill_hex):
    """One doughnut slice as an annular custGeom sector (outer arc a0→a1, line in, inner arc
    a1→a0, close). Angles are SVG degrees (clockwise from 12 o'clock). A full 100 % slice is
    drawn as a disc ellipse (the centre hole rings it) to avoid a degenerate 360° arc."""
    sweep = a1 - a0
    if sweep >= 359.999:
        return _prst_shape(sid, name, _emu(cx - R), _emu(cy - R), _emu(2 * R), _emu(2 * R),
                           'ellipse', fill_hex, line_hex='FFFFFF', line_emu=_emu(2))
    ox0, oy0 = _pt(cx, cy, R, a0)
    ix1, iy1 = _pt(cx, cy, ri, a1)
    st_out = int(round((a0 - 90.0) * 60000))
    sw = int(round(sweep * 60000))
    st_in = int(round((a1 - 90.0) * 60000))
    path = (f'<a:moveTo><a:pt x="{_emu(ox0)}" y="{_emu(oy0)}"/></a:moveTo>'
            f'<a:arcTo wR="{_emu(R)}" hR="{_emu(R)}" stAng="{st_out}" swAng="{sw}"/>'
            f'<a:lnTo><a:pt x="{_emu(ix1)}" y="{_emu(iy1)}"/></a:lnTo>'
            f'<a:arcTo wR="{_emu(ri)}" hR="{_emu(ri)}" stAng="{st_in}" swAng="{-sw}"/>'
            f'<a:close/>')
    return _custgeom_shape(sid, name, path, w_emu, h_emu, fill_hex=fill_hex,
                           fill_mode='norm', line_hex='FFFFFF', line_emu=_emu(2))


def _polyline(sid, name, pts, w_emu, h_emu, color_hex, width_emu):
    """A multi-segment leader (moveTo + lnTo per point) as a stroked, no-fill custGeom.
    ``pts`` = [(x, y), …] in report px on the whole-canvas coordinate frame."""
    d = f'<a:moveTo><a:pt x="{_emu(pts[0][0])}" y="{_emu(pts[0][1])}"/></a:moveTo>'
    for (x, y) in pts[1:]:
        d += f'<a:lnTo><a:pt x="{_emu(x)}" y="{_emu(y)}"/></a:lnTo>'
    return _custgeom_shape(sid, name, d, w_emu, h_emu, fill_hex=None,
                           fill_mode='none', line_hex=color_hex, line_emu=width_emu)


def add_doughnut(document, categories, values, title=None, num_fmt='#,##0', unit='',
                 pcts=None, total=None):
    """Native, EDITABLE §6 Contract-Value DOUGHNUT — a ``wpg:wgp`` group of real Word shapes
    (annular custGeom sectors + text boxes + leader polylines + a centre-hole ellipse), the
    pixel twin of ``html._doughnut``. NOT a ``c:chart`` and never a picture.

    Geometry mirrors ``html._doughnut`` EXACTLY (W=760, H=330, cx=205, cy=165, R=124, ri=73):
    the dominant slice (share ≥ 15 %) is labelled ON the ring (name over pct, white, at the
    centroid radius); each small slice gets an external right-hand ladder (a coloured dot at
    the ring outer point, a #9aa4ad leader, an 8×8 swatch and a "Name pct%" label); the grouped
    total sits in the white centre hole under a "TOTAL (unit)" cap. Slice colours come from
    ``ramp_colors`` (grey for Unclassified / Other), so a discipline reads the SAME colour here,
    on the §7.1 composition bar and in the PDF / screen. The amount legend/table is drawn
    SEPARATELY by ``docx_writer`` (its swatches reuse ``ramp_colors``). ``unit`` is the currency
    code for the centre cap; ``num_fmt`` is kept for signature compatibility (unused).

    None-safe: a missing document, empty / mismatched / non-numeric / zero-total data returns
    ``None`` and never raises. Returns the drawing element on success."""
    if document is None or not categories or not values:
        return None
    cats = list(categories)
    vals = [_num(v) for v in values]
    if len(cats) != len(vals) or any(v is None for v in vals):
        return None
    val_total = sum(vals)
    if val_total <= 0:
        return None
    # Mirror html._doughnut EXACTLY: drive the slice angles, labels and the dominant/external
    # split from the payload's per-row pct (already rounded), and put the payload TOTAL in the
    # centre — so Word == PDF == HTML (and the centre never disagrees with the §6 banner). Fall
    # back to deriving both from the amounts only when the caller supplies neither.
    pf = [_num(pp) for pp in (pcts or [])]
    share = (pf if (len(pf) == len(cats) and all(p is not None for p in pf) and sum(pf) > 0)
             else [v / val_total * 100.0 for v in vals])
    total_share = sum(share) or 100.0
    ctotal = _num(total)
    if ctotal is None:
        ctotal = val_total
    try:
        W, H, cx, cy, R, ri = 760.0, 330.0, 205.0, 165.0, 124.0, 73.0
        w_emu, h_emu = _emu(W), _emu(H)
        palette = ramp_colors(cats)
        counter = [_next_id(document)]
        base_id = counter[0]
        counter[0] += 1

        def nid():
            v = counter[0]
            counter[0] += 1
            return v

        sectors, ring_labels, smalls = [], [], []
        acc = 0.0
        for i, p in enumerate(share):
            col = palette[i]
            a0 = acc / total_share * 360.0
            a1 = (acc + p) / total_share * 360.0
            acc += p
            mid = (a0 + a1) / 2.0
            sectors.append(_annular_sector(nid(), cats[i], cx, cy, R, ri, a0, a1,
                                           w_emu, h_emu, col))
            if p >= 15.0:                        # dominant slice → label ON the ring
                lx, ly = _pt(cx, cy, (R + ri) / 2.0, mid)
                nm = _clip(cats[i], 18)
                ring_labels.append(_center_text(
                    nid(), 'ring-name', lx, ly - 5 - 15 * 0.34,
                    _est_w(nm, 15), 15 * 1.8, [(nm, _hp(15), True, 'FFFFFF')]))
                ptxt = '%s%%' % _pct_str(p)
                ring_labels.append(_center_text(
                    nid(), 'ring-pct', lx, ly + 15 - 17 * 0.34,
                    _est_w(ptxt, 17), 17 * 1.8, [(ptxt, _hp(17), True, 'FFFFFF')]))
            else:
                smalls.append((i, col, mid, p))

        # centre hole (white disc) + "TOTAL (unit)" cap + grouped total (painted over the ring)
        hole = _prst_shape(nid(), 'hole', _emu(cx - (ri - 1)), _emu(cy - (ri - 1)),
                           _emu(2 * (ri - 1)), _emu(2 * (ri - 1)), 'ellipse', 'FFFFFF')
        u = (unit or '').strip()
        cap = ('TOTAL (%s)' % u) if u else 'TOTAL'
        centre_cap = _center_text(nid(), 'cap', cx, cy - 9 - 10.5 * 0.34,
                                  _est_w(cap, 10.5), 10.5 * 1.8,
                                  [(cap, _hp(10.5), True, '8A93A0')])
        big = '{:,.0f}'.format(ctotal)
        centre_total = _center_text(nid(), 'total', cx, cy + 14 - 16 * 0.34,
                                    _est_w(big, 16), 16 * 1.8,
                                    [(big, _hp(16), True, '1F4E79')])

        # external right-hand ladder for the small slices (leader + dot + swatch + label)
        ladder = []
        if smalls:
            chan_x = W - 236.0                   # 524
            txt_x = chan_x + 14.0                # 538
            top = 46.0
            gap = min(50.0, (H - top - 14.0) / max(len(smalls) - 1, 1))
            for j, (i, col, mid, p) in enumerate(smalls):
                ly = top + j * gap
                px, py = _pt(cx, cy, R, mid)
                sx, sy = _pt(cx, cy, R + 14.0, mid)
                ladder.append(_polyline(nid(), 'leader',
                              [(px, py), (sx, sy), (chan_x, ly), (txt_x - 4.0, ly)],
                              w_emu, h_emu, '9AA4AD', _emu(1.3)))
                ladder.append(_prst_shape(nid(), 'dot', _emu(px - 2.6), _emu(py - 2.6),
                              _emu(5.2), _emu(5.2), 'ellipse', col))
                ladder.append(_prst_shape(nid(), 'swatch', _emu(txt_x - 4.0), _emu(ly - 10.0),
                              _emu(8), _emu(8), 'roundRect', col, adj=_roundadj(2, 8)))
                nm = _clip(cats[i], 16)
                ptxt = '%s%%' % _pct_str(p)
                runs = [(nm + ' ', _hp(13), True, '1A1D21'), (ptxt, _hp(13), True, col)]
                ladder.append(_left_text(nid(), 'leader-label', txt_x + 9.0, ly,
                              _est_w(nm + '  ' + ptxt, 13), 13 * 1.8, runs))

        shapes = ''.join(sectors + ring_labels
                         + [hole, centre_cap, centre_total] + ladder)
        disp_w, disp_h = _fit_display(w_emu, h_emu)
        return _group_drawing(document, shapes, base_id, w_emu, h_emu, disp_w, disp_h)
    except Exception:                            # pragma: no cover - never crash the export
        return None


def add_composition_bar(document, labels, values, title=None, pcts=None):
    """Native, EDITABLE §7.1 scope COMPOSITION BAR — a ``wpg:wgp`` group of real Word shapes
    (a rounded track + one rounded / plain segment per discipline + in-bar white labels +
    external leader polylines with % labels), the pixel twin of ``html._compbar``. NOT a
    ``c:chart`` and never a picture.

    Geometry mirrors ``html._compbar`` EXACTLY (W=760, H=104, x0=8, y0=60, bh=40, bw=744):
    each segment's width is its share of the total value; a wide segment (≥ 150 px) carries
    "Name pct%" inside (white), a medium one (≥ 34 px) carries "pct%" inside (white), and a
    thin one gets its % spread across the top with an angled leader down to the segment (so
    small shares never collide). Segment colours come from ``ramp_colors`` (grey for
    Unclassified / Other), so they match the §6 doughnut, the swatch legend ``docx_writer``
    draws beneath, and the PDF / screen.

    None-safe: a missing document, empty / mismatched / non-numeric / zero-total data returns
    ``None`` (the writer then falls back to its editable cost / share table). Returns the
    drawing element on success."""
    if document is None or not labels or not values:
        return None
    labs = [('' if l is None else str(l)) for l in labels]
    vals = [_num(v) for v in values]
    if len(labs) != len(vals) or any(v is None for v in vals):
        return None
    val_total = sum(vals)
    if val_total <= 0:
        return None
    # Mirror html._compbar: segment widths, labels and the in/out thresholds all run off the
    # payload's rounded pct, so the bar matches the SVG and the swatch legend beneath it exactly
    # (no "75.0%" vs "75%" drift). Derive from amounts only when the caller supplies no pcts.
    pf = [_num(pp) for pp in (pcts or [])]
    share = (pf if (len(pf) == len(labs) and all(p is not None for p in pf) and sum(pf) > 0)
             else [v / val_total * 100.0 for v in vals])
    total_share = sum(share) or 100.0
    try:
        W, H, x0, y0, bh = 760.0, 104.0, 8.0, 60.0, 40.0
        bw = W - 2 * x0                          # 744
        n = len(labs)
        w_emu, h_emu = _emu(W), _emu(H)
        palette = ramp_colors(labs)
        counter = [_next_id(document)]
        base_id = counter[0]
        counter[0] += 1

        def nid():
            v = counter[0]
            counter[0] += 1
            return v

        # rounded background track (paints first; segments paint over it)
        shapes = [_prst_shape(nid(), 'track', _emu(x0), _emu(y0), _emu(bw), _emu(bh),
                              'roundRect', 'EEF1F5', adj=_roundadj(6, bh))]
        inside, smalls = [], []
        cy_lab = y0 + bh / 2.0 + 1.0             # 81 (SVG dominant-baseline middle → centre)
        acc = 0.0
        for i, p in enumerate(share):
            col = palette[i]
            w = p / total_share * bw
            x = x0 + acc / total_share * bw
            acc += p
            rounded = (i == 0 or i == n - 1)     # first / last segment carry rx=6 corners
            shapes.append(_prst_shape(
                nid(), labs[i], _emu(x), _emu(y0), _emu(max(w, 0.8)), _emu(bh),
                'roundRect' if rounded else 'rect', col, line_hex='FFFFFF',
                line_emu=_emu(1), adj=(_roundadj(6, bh) if rounded else '')))
            if w >= 150.0:                        # wide → name + pct inside (white)
                txt = '%s %s%%' % (_clip(labs[i], 22), _pct_str(p))
                inside.append(_center_text(nid(), 'seg-label', x + w / 2.0, cy_lab,
                              _est_w(txt, 15), 15 * 1.8, [(txt, _hp(15), True, 'FFFFFF')]))
            elif w >= 34.0:                       # medium → pct only inside (white)
                txt = '%s%%' % _pct_str(p)
                inside.append(_center_text(nid(), 'seg-pct', x + w / 2.0, cy_lab,
                              _est_w(txt, 12), 12 * 1.8, [(txt, _hp(12), True, 'FFFFFF')]))
            else:                                 # thin → external spread % + leader
                smalls.append((col, x + w / 2.0, p))

        leaders = []
        if smalls:
            sx0 = x0 + bw * 0.34                  # 260.96
            sx1 = W - 30.0                        # 730
            lab_y = 18.0
            m = len(smalls)
            for j, (col, seg_cx, p) in enumerate(smalls):
                lx = (sx0 + (sx1 - sx0) * j / (m - 1)) if m > 1 else (sx0 + sx1) / 2.0
                leaders.append(_polyline(nid(), 'leader',
                               [(lx, lab_y + 6.0), (lx, lab_y + 16.0), (seg_cx, y0 - 2.0)],
                               w_emu, h_emu, col, _emu(1.2)))
                txt = '%s%%' % _pct_str(p)
                leaders.append(_center_text(nid(), 'spread-pct', lx, lab_y,
                               _est_w(txt, 12), 12 * 1.8, [(txt, _hp(12), True, col)]))

        disp_w, disp_h = _fit_display(w_emu, h_emu)
        return _group_drawing(document, ''.join(shapes + inside + leaders),
                              base_id, w_emu, h_emu, disp_w, disp_h)
    except Exception:                            # pragma: no cover - never crash the export
        return None


def add_calendar_hist(document, categories, working, nonworking,
                      title='Working / non-working days by month'):
    """Native STACKED histogram: net-working days (green, bottom) + non-working days
    (red, top), matching the on-screen / PDF colours (working #1F7A3D, non-working
    #B23030). A bottom two-item LEGEND names the colours ("Working days" /
    "Non-working days"), and the NET-WORKING-DAYS total is labelled CLEARLY ABOVE each
    month's stacked column, in the white space over the bar (§8.2). Returns the drawing
    element, or ``None`` on bad input.

    The top-of-bar total is carried by a third, invisible (``noFill``) series stacked on
    top of the two coloured ones. It is given a small, uniform HEIGHT (``head_h`` ≈ 22 %
    of the tallest column) so it reserves a band of empty space above every coloured
    stack; the value axis is then capped just above that band (an explicit ``c:max`` ≈
    1.22× the tallest total) so the headroom is guaranteed for every column regardless of
    auto-scaling. The net-working-days figure is shown as a custom, centred label of that
    invisible band (``dLblPos="ctr"``) — so it floats in the white space above the bar,
    never overlapping the green/red segments. The band is hidden from the legend. Colours
    mirror ``html.py`` (._cal_hist / .callegend)."""
    if document is None or not categories:
        return None
    cats = list(categories)
    wk = [_num(v) for v in (working or [])]
    nw = [_num(v) for v in (nonworking or [])]
    if (len(wk) != len(cats) or len(nw) != len(cats)
            or any(v is None for v in wk) or any(v is None for v in nw)):
        return None
    # Headroom band: an invisible top segment (uniform height) that opens white space
    # ABOVE every coloured stack for the label to sit in, plus an explicit value-axis max
    # so that space is always present. head_h ≈ 22 % of the tallest total (min 1); the
    # centred label then floats ~11 % of the tallest total above each column's top.
    totals = [wk[j] + nw[j] for j in range(len(cats))]
    max_total = max(totals) if totals else 0
    head_h = max(1, int(round(max_total * 0.22)))
    head = [head_h for _ in cats]              # invisible top-band series values
    axis_max = max_total + head_h              # value-axis cap → guaranteed headroom
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
        """Invisible top band (uniform ``head`` height, ``noFill``) carrying the
        net-working-days number in the white space ABOVE each column. The label is
        CENTRED in the band (``dLblPos="ctr"``) so it floats clearly over the coloured
        stack — never inside/overlapping the green/red segments."""
        dlbls = ''.join(
            f'<c:dLbl><c:idx val="{j}"/>'
            f'<c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p>'
            f'<a:pPr><a:defRPr b="1" sz="800"><a:solidFill><a:srgbClr val="{LABEL}"/></a:solidFill></a:defRPr></a:pPr>'
            f'<a:r><a:rPr lang="en-US" b="1" sz="800"><a:solidFill><a:srgbClr val="{LABEL}"/></a:solidFill></a:rPr>'
            f'<a:t>{int(round(wk[j]))}</a:t></a:r></a:p></c:rich></c:tx>'
            f'<c:dLblPos val="ctr"/>'
            f'<c:showLegendKey val="0"/><c:showVal val="0"/><c:showCatName val="0"/>'
            f'<c:showSerName val="0"/><c:showPercent val="0"/><c:showBubbleSize val="0"/></c:dLbl>'
            for j in range(len(cats)))
        dl = (f'<c:dLbls>{dlbls}<c:dLblPos val="ctr"/>'
              f'<c:showLegendKey val="0"/><c:showVal val="0"/><c:showCatName val="0"/>'
              f'<c:showSerName val="0"/><c:showPercent val="0"/><c:showBubbleSize val="0"/></c:dLbls>')
        return (f'<c:ser><c:idx val="{idx}"/><c:order val="{idx}"/>{_tx_ref("Net working days", letter)}'
                f'<c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>'
                f'{dl}{_cat_ref(cats)}{_val_ref(head, letter)}</c:ser>')

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
                f'<c:valAx><c:axId val="222"/>'
                f'<c:scaling><c:orientation val="minMax"/>'
                f'<c:max val="{_vstr(axis_max)}"/><c:min val="0"/></c:scaling>'
                f'<c:delete val="0"/><c:axPos val="l"/><c:crossAx val="111"/></c:valAx>'
                f'</c:plotArea>{legend}<c:plotVisOnly val="1"/></c:chart>'
                f'{_external_data(rid)}</c:chartSpace>')

    return _inject(document, build, cats,
                   [('Working days', wk), ('Non-working days', nw),
                    ('Net working days', head)])


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

# VERTICAL (indented) tree geometry (px; converted to EMU via _emu). Uniform box width/height;
# each depth indented one INDENT; rows stepped by ROW_H (a small gap between boxes). The gutter
# for a parent's elbow sits GUTTER px right of the parent's left edge, LEFT of the child boxes
# (which start one INDENT right of the parent), so the vertical line never crosses a box.
_TREE_PAD, _TREE_INDENT, _TREE_ROW_H = 10, 28, 30
_TREE_BOX_W, _TREE_BOX_H, _TREE_GUTTER = 388, 24, 12

# HORIZONTAL (left→right) branch geometry — a small, short-labelled branch lays its children in
# a COLUMN to the RIGHT of the parent: one depth per COL_W, one leaf per ROW_H, uniform box.
_HTREE_PAD, _HTREE_COL_W, _HTREE_ROW_H = 10, 170, 40
_HTREE_BOX_W, _HTREE_BOX_H = 140, 32

# adaptive-orientation thresholds — a single-root tree draws HORIZONTAL only when it is small
# AND short-labelled AND shallow; otherwise (many children / long labels / deeper) it draws as
# the VERTICAL indented tree so no label is clipped (Ibrahim's approved rule).
_H_MAX_NODES, _H_MAX_LABEL, _H_MAX_DEPTH = 10, 24, 3


def _wbs_vertical(document, seq, base, max_depth):
    """VERTICAL indented WBS tree (the approved overview / big-branch layout): every node on its
    own ROW, indented by ``level - base``, joined to its children by one gutter ELBOW (a single
    vertical line down the gutter plus a horizontal stub into each child's left edge). ``seq`` is
    the DFS record list (``{'node','level','row'}``). Returns the drawing element or ``None``."""
    rec_by_id = {id(r['node']): r for r in seq}

    def x_of(level):
        return _TREE_PAD + (level - base) * _TREE_INDENT

    def y_of(row):
        return _TREE_PAD + row * _TREE_ROW_H

    counter = [_next_id(document)]
    base_id = counter[0]
    counter[0] += 1                     # reserve base_id for the group frame's docPr

    shapes = []
    # elbow connectors FIRST so the boxes paint over them — one per real parent→children link
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
    # boxes (colour-coded by ABSOLUTE WBS level: lv0 navy … lv4 white, clamped)
    for rec in seq:
        lvl = rec['level']
        fill, border, tcol = _WBS_TREE_LEVELS[min(max(lvl, 0), len(_WBS_TREE_LEVELS) - 1)]
        nm = rec['node'].get('name') or ''
        shapes.append(_wps_box(
            counter, nm, _emu(x_of(lvl)), _emu(y_of(rec['row'])),
            _emu(_TREE_BOX_W), _emu(_TREE_BOX_H), fill, border, tcol, nm, sz=10))

    total_w = _TREE_PAD + max_depth * _TREE_INDENT + _TREE_BOX_W + _TREE_PAD
    total_h = _TREE_PAD + (len(seq) - 1) * _TREE_ROW_H + _TREE_BOX_H + _TREE_PAD
    return _group_drawing(document, ''.join(shapes), base_id, _emu(total_w), _emu(total_h))


def _wbs_horizontal(document, root):
    """HORIZONTAL (left→right) WBS tree for a small, short-labelled branch: the parent sits on
    the LEFT and its children are stacked in a COLUMN to the RIGHT; each child expands the same
    way further right. Tidy-tree layout — ``x = PAD + depth*COL_W``; a leaf takes the next
    ROW_H slot, a parent centres on the Y span of its children.

    One clean orthogonal ELBOW per parent (no diagonal / duplicate / decorative lines): a short
    horizontal from the parent's right edge to a vertical BUS that spans the children's centres,
    then a horizontal STUB from the bus into each child's left edge. The canvas grows to fit
    every box so nothing overlaps or truncates. Returns the drawing element or ``None``."""
    pad, colw, rowh = _HTREE_PAD, _HTREE_COL_W, _HTREE_ROW_H
    bw, bh = _HTREE_BOX_W, _HTREE_BOX_H
    pos = {}                                    # id(node) -> (x, y_top)
    order = []                                  # [(node, depth, level), …] in DFS order
    leaf_y = [pad]                              # next free leaf Y slot (mutable)

    def layout(n, depth):
        try:
            lvl = int(n.get('level'))
        except (TypeError, ValueError):
            lvl = depth
        order.append((n, depth, lvl))
        x = pad + depth * colw
        kids = [k for k in (n.get('children') or []) if k]
        if not kids:
            y = leaf_y[0]
            leaf_y[0] += rowh
        else:
            for k in kids:
                layout(k, depth + 1)
            ys = [pos[id(k)][1] for k in kids]
            y = (min(ys) + max(ys)) / 2.0       # parent centres on its children's Y span
        pos[id(n)] = (x, y)

    layout(root, 0)
    if not order:
        return None
    max_x = max(x for x, _ in pos.values())
    max_y = max(y for _, y in pos.values())
    total_w = max_x + bw + pad
    total_h = max_y + bh + pad

    counter = [_next_id(document)]
    base_id = counter[0]
    counter[0] += 1
    shapes = []
    # elbow connectors FIRST (boxes paint over them) — one set per real parent→children link
    for n, depth, lvl in order:
        kids = [k for k in (n.get('children') or []) if k and id(k) in pos]
        if not kids:
            continue
        px, py = pos[id(n)]
        parent_right = px + bw
        child_left = pos[id(kids[0])][0]        # = pad + (depth+1)*colw
        bus_x = parent_right + (child_left - parent_right) / 2.0
        parent_cy = py + bh / 2.0
        cys = [pos[id(k)][1] + bh / 2.0 for k in kids]
        # 1) short horizontal from the parent's right edge to the bus (lands on the bus centre)
        shapes.append(_wps_line(counter, _emu(parent_right), _emu(parent_cy),
                                _emu(bus_x - parent_right), 0, _WBS_LINE))
        # 2) vertical bus across the children's centres (omitted for a single child)
        if len(kids) >= 2:
            shapes.append(_wps_line(counter, _emu(bus_x), _emu(min(cys)),
                                    0, _emu(max(cys) - min(cys)), _WBS_LINE))
        # 3) a horizontal stub from the bus into each child's left edge
        for k in kids:
            kx, _ky = pos[id(k)]
            cy = _ky + bh / 2.0
            shapes.append(_wps_line(counter, _emu(bus_x), _emu(cy),
                                    _emu(kx - bus_x), 0, _WBS_LINE))
    # boxes (colour-coded by ABSOLUTE WBS level: lv0 navy … lv4 white, clamped)
    for n, depth, lvl in order:
        x, y = pos[id(n)]
        fill, border, tcol = _WBS_TREE_LEVELS[min(max(lvl, 0), len(_WBS_TREE_LEVELS) - 1)]
        nm = n.get('name') or ''
        shapes.append(_wps_box(counter, nm, _emu(x), _emu(y), _emu(bw), _emu(bh),
                               fill, border, tcol, nm, sz=9))
    return _group_drawing(document, ''.join(shapes), base_id, _emu(total_w), _emu(total_h))


def add_wbs_tree(document, nodes):
    """Native, editable WBS box-tree with clean orthogonal ELBOW connectors (§9 redesign),
    ADAPTIVE per branch:

      • a SMALL, SHORT-LABELLED, SHALLOW single-root branch draws HORIZONTAL (left→right) — the
        parent on the left, its children stacked in a column to the right (``_wbs_horizontal``);
      • anything with MANY children, LONG labels or more DEPTH draws as the VERTICAL indented
        tree so no label is clipped (``_wbs_vertical``). The §9.1 overview (root → 10 long-named
        majors) therefore stays vertical; a compact branch (e.g. "Phase I Design") goes
        horizontal. The choice is DYNAMIC — computed from node count / label length / depth,
        never hard-coded.

    ``nodes`` is a list of ROOT node dicts, each ``{'name', 'level', 'children': [...]}``.
    Every connector is one real parent→child elbow (no diagonal, duplicate or decorative
    lines); boxes are colour-coded by WBS level (navy → blue → light-blue → white); the group is
    sized to fit every box so nothing overlaps or truncates. Native shapes only (``_wps_box`` +
    ``_wps_line`` — never a picture). Returns the drawing element, or ``None`` on a missing
    document / empty tree / any internal error (the caller falls back to an editable table)."""
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
                if k:
                    dfs(k)

        roots = [r for r in nodes if r]
        for root in roots:
            dfs(root)
        if not seq:
            return None

        base = min(r['level'] for r in seq)
        max_depth = max(r['level'] - base for r in seq)

        # Adaptive orientation (single-root trees only — the writer passes one root per call).
        # Horizontal iff small AND short-labelled AND shallow; else the vertical indented tree.
        if len(roots) == 1:
            node_count = len(seq)
            max_label = max((len(r['node'].get('name') or '') for r in seq), default=0)
            if (node_count <= _H_MAX_NODES and max_label <= _H_MAX_LABEL
                    and max_depth <= _H_MAX_DEPTH):
                try:
                    drawing = _wbs_horizontal(document, roots[0])
                except Exception:           # pragma: no cover - fall back to vertical
                    drawing = None
                if drawing is not None:
                    return drawing

        return _wbs_vertical(document, seq, base, max_depth)
    except Exception:                       # pragma: no cover - never crash the export
        return None
