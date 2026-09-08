"""Write a Baseline Narrative Report (dict) to a professional, natively-editable
Word (.docx) document.

This writer is an ORCHESTRATOR: the professional "shell" of the deliverable — page
geometry, the page-border frame, the repeating logo/title header, the page-number
footer, the cover, the Table of Contents, base styles and the shared numbered
heading / styled-table helpers — all live in :mod:`p6_narrative.docx_template`
(SLICE B). The charts are drawn as self-contained SVGs and rasterised to PNG by
:mod:`p6_narrative.docx_charts` (SLICE C, via headless Chrome), and Section 5
(Project Calendars & Holidays) is delegated to :mod:`p6_narrative.docx_calendar`
(SLICE D). This module wires those together and keeps the native, editable
renderers for the text-shaped section kinds.

The furniture intentionally follows the Roots template (NOT the PDF look). Only the
DATA and the charts mirror the screen / PDF export, so a planner can change any word,
number, row or cell in Word and finish it on their letterhead.

It consumes the model produced by :func:`p6_narrative.report.build_report` →
``to_dict()``::

    {meta:{project_name, project_id, mode, data_date?, location?, revision?, logos?},
     sections:[{number, title, kind, payload, note, editable}, …]}

and renders every section kind the producer can emit::

    overview · keyvals · ms_table · timeline · value · scope · table · wbs_tree ·
    codes · idanatomy · seq · interfaces · prose · costbars · cashflow · image

Chart kinds (wbs_tree · seq · value · costbars · timeline · cashflow) embed a real
graph image when Chrome is available and fall back to a native table / outline when
it is not — the export never crashes on a missing chrome.
"""
import base64
import io
from datetime import datetime

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Inches, Pt

from p6_narrative import chart_png, docx_calendar, docx_charts, docx_template

# ── palette / font (native renderers reuse the template's palette) ────────────
NAVY = docx_template.NAVY
INK = docx_template.INK
GREY = docx_template.GREY
_FONT = 'Calibri'
_BODY_PT = 11
_ARROW = ' → '     # " → " for sequence / macro-flow fallback lines
_IMG_W = Cm(16)         # cap every embedded image so it never spills past the page frame


# ── low-level helpers still used by the native renderers ──────────────────────
def _img_bytes(data_url):
    """Decode a 'data:image/...;base64,XXXX' URL (or bare base64) to a BytesIO, or None."""
    if not data_url:
        return None
    try:
        b64 = data_url.split(',', 1)[1] if ',' in str(data_url) else data_url
        return io.BytesIO(base64.b64decode(b64))
    except Exception:
        return None


def _money(v):
    try:
        return '{:,.0f}'.format(float(v))
    except (TypeError, ValueError):
        return '' if v is None else str(v)


def _count(v):
    try:
        return '{:,}'.format(int(v))
    except (TypeError, ValueError):
        return '' if v is None else str(v)


def _fmt_iso(v):
    """Render an ISO date (or any date-ish value) as 'DD Mon YYYY'; else pass through."""
    if not v:
        return ''
    if isinstance(v, datetime):
        return '%d %s %d' % (v.day, v.strftime('%b'), v.year)
    try:
        dt = datetime.strptime(str(v)[:10], '%Y-%m-%d')
        return '%d %s %d' % (dt.day, dt.strftime('%b'), dt.year)
    except (ValueError, TypeError):
        return str(v)


def _para(document, text, size=None, italic=False, bold=False, color=None, style=None):
    para = document.add_paragraph(style=style) if style else document.add_paragraph()
    run = para.add_run('' if text is None else str(text))
    run.font.name = _FONT
    run.font.size = Pt(size or _BODY_PT)
    run.italic = italic
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    return para


def _muted(document, text):
    return _para(document, text, italic=True, color=GREY)


def _lead(document, text):
    """A grey lead / caption line under a heading (matches the HTML '.lead')."""
    return _para(document, text, size=9.5, italic=True, color=GREY)


class _Sub:
    """Numbered sub-heading emitter for one section: yields ``<number>.1``,
    ``<number>.2`` … through :func:`docx_template.subheading`, so every sub-heading
    follows the ACTUAL parent section number."""

    def __init__(self, document, number):
        self.document = document
        self.number = number
        self._i = 0

    def heading(self, text):
        self._i += 1
        return docx_template.subheading(
            self.document, docx_template.format_number((self.number, self._i)),
            text or '—')


def _add_chart_image(document, kind, data, chrome):
    """Rasterise ``kind`` from ``data`` (docx_charts) and embed it centred, capped at
    the text-column width. Returns True when an image was placed, False otherwise
    (unknown kind / empty data / Chrome missing / add_picture failure) so the caller
    can fall back to a native table or outline."""
    png = docx_charts.chart_png(kind, data, chrome)
    if not png:
        return False
    try:
        document.add_picture(docx_charts.stream(png), width=_IMG_W)
        document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        return True
    except Exception:
        return False


# ── v5 renderers ──────────────────────────────────────────────────────────────
def _render_overview(document, p, sub, chrome, note):
    for para in p.get('paragraphs', []) or []:
        _para(document, para)
    breakdown = p.get('breakdown') or []
    if breakdown:
        sub.heading('Baseline composition')
        rows = [[b.get('world', ''), _count(b.get('count'))] for b in breakdown]
        total = p.get('total')
        if total is not None:
            rows.append(['Total', _count(total)])
        docx_template.styled_table(document, ['Scope', 'Activities'], rows,
                                   widths=(Inches(4.6), Inches(1.6)),
                                   bold_last_row=total is not None)


def _render_ms_table(document, p, sub, chrome, note):
    columns = p.get('columns') or ['Milestone', 'Date']
    rows = p.get('rows') or []
    if not rows:
        _muted(document, note or 'No finish milestones are defined in the file.')
        return
    docx_template.styled_table(document, columns, rows, widths=(Inches(4.6), Inches(1.9)))


def _wbs_node(document, node, depth):
    """One editable outline paragraph per WBS node — indent grows with depth (full P6
    depth), level-1 bold, a '+N more' breadth marker italic-grey."""
    marker = {1: '▪  ', 2: '–  ', 3: '·  '}.get(depth, '·  ')
    para = document.add_paragraph()
    para.paragraph_format.left_indent = Inches(0.26 * depth)
    para.paragraph_format.space_after = Pt(2)
    run = para.add_run(marker + (node.get('name') or '—'))
    run.font.name = _FONT
    run.font.size = Pt(_BODY_PT)
    if node.get('more'):
        run.italic = True
        run.font.color.rgb = GREY
    elif depth <= 1:
        run.bold = True
    for child in node.get('children', []):
        _wbs_node(document, child, depth + 1)


def _render_wbs_tree(document, p, sub, chrome, note):
    worlds = p.get('worlds') or []
    if not worlds:
        _muted(document, 'No work breakdown structure is defined in the file.')
        return
    _lead(document, 'The actual P6 breakdown, one org-chart per major branch, at full '
                    'hierarchy depth. Structure only — the execution order is in the '
                    'Sequence of Work section. When the chart engine is unavailable the '
                    'same WBS renders as an editable indented outline.')
    for w in worlds:
        root = w.get('root') or {}
        sub.heading(root.get('name') or w.get('name') or '—')
        if not _add_chart_image(document, 'wbs_smartart', root, chrome):
            for child in root.get('children', []):
                _wbs_node(document, child, 1)


def _render_seq(document, p, sub, chrome, note):
    worlds = p.get('worlds') or []
    if not worlds:
        _muted(document, 'No execution fronts were detected in the file.')
        return
    for w in worlds:
        sub.heading(w.get('world') or '—')
        fronts = w.get('fronts') or []
        if not fronts:
            _muted(document, 'No work-package sequence was detected for this scope.')
            continue
        for f in fronts:
            title_p = document.add_paragraph()
            title_p.paragraph_format.space_before = Pt(6)
            title_p.paragraph_format.space_after = Pt(1)
            trun = title_p.add_run(f.get('title') or 'Front')
            trun.bold = True
            trun.font.name = _FONT
            trun.font.size = Pt(_BODY_PT)

            # flow: a chevron image when Chrome is available, else an arrow line
            seq = [str(s) for s in (f.get('sequence') or []) if s]
            if not _add_chart_image(document, 'sequence_flow', f, chrome) and seq:
                sp = document.add_paragraph()
                sp.paragraph_format.left_indent = Inches(0.22)
                srun = sp.add_run(_ARROW.join(seq))
                srun.font.name = _FONT
                srun.font.size = Pt(_BODY_PT)

            meta_bits = []
            instances = [str(i) for i in (f.get('instances') or []) if i]
            if instances:
                shown = ', '.join(instances[:8])
                if len(instances) > 8:
                    shown += ', +%d more' % (len(instances) - 8)
                meta_bits.append('Applies to: ' + shown)
            acts = f.get('activities') or []
            if acts:
                meta_bits.append('%d activities' % len(acts))
            if meta_bits:
                ap = document.add_paragraph()
                ap.paragraph_format.left_indent = Inches(0.22)
                arun = ap.add_run('   ·   '.join(meta_bits))
                arun.italic = True
                arun.font.name = _FONT
                arun.font.size = Pt(9.5)
                arun.font.color.rgb = GREY

            # drill-down P6 activities table beneath the flow (kept either way)
            if acts:
                rows = [[a.get('id'), a.get('name'), a.get('wbs')] for a in acts]
                docx_template.styled_table(
                    document, ['ID', 'Activity', 'WBS'], rows,
                    widths=(Inches(1.4), Inches(3.4), Inches(1.9)))


def _render_interfaces(document, p, sub, chrome, note):
    macro = [str(m) for m in (p.get('macro') or []) if m]
    if macro:
        sub.heading('Macro execution flow')
        mp = document.add_paragraph()
        mrun = mp.add_run(_ARROW.join(macro))
        mrun.bold = True
        mrun.font.name = _FONT
        mrun.font.size = Pt(_BODY_PT)
        mrun.font.color.rgb = NAVY
    for n in p.get('notes') or []:
        _para(document, n, style='List Bullet')
    edges = [e for e in (p.get('edges') or [])
             if isinstance(e, (list, tuple)) and len(e) >= 2]
    if edges:
        sub.heading('Key building / front dependencies')
        for a, b in ((e[0], e[1]) for e in edges):
            _para(document, '%s%s%s' % (a, _ARROW, b), style='List Bullet')


# ── recovered content-breadth renderers ──────────────────────────────────────
def _render_prose(document, p, sub, chrome, note):
    for para in p.get('paragraphs', []) or []:
        _para(document, para)
    for bullet in p.get('bullets', []) or []:
        _para(document, bullet, style='List Bullet')


def _render_keyvals(document, p, sub, chrome, note):
    rows = [[r.get('k'), r.get('v')] for r in p.get('rows', []) or []]
    if not rows:
        _muted(document, 'No project brief fields are available.')
        return
    docx_template.styled_table(document, ['Field', 'Value'], rows,
                               widths=(Inches(2.4), Inches(4.2)))


def _render_image(document, p, sub, chrome, note):
    img = _img_bytes(p.get('image'))
    if not img:
        _muted(document, 'No layout image provided.')
        return
    try:
        document.add_picture(img, width=_IMG_W)
        document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception:
        _muted(document, '[project layout image]')


def _render_timeline(document, p, sub, chrome, note):
    items = p.get('items', []) or []
    if not items:
        _muted(document, 'No key dates are available in the file.')
        return
    if _add_chart_image(document, 'timeline', p, chrome):
        return
    rows = [[_fmt_iso(it.get('date')), it.get('label')] for it in items]
    docx_template.styled_table(document, ['Date', 'Key date / milestone'], rows,
                               widths=(Inches(1.9), Inches(4.7)))


def _cost_table(document, p, name_header):
    rows = [[r.get('name'), _money(r.get('cost')),
             '%s%%' % r.get('pct')] for r in p.get('rows', []) or []]
    if not rows:
        _muted(document, 'No cost-loading information is available in the file.')
        return
    total = p.get('total')
    if total is not None:
        rows.append(['Total', _money(total), '100%'])
    docx_template.styled_table(document, [name_header, 'Cost', 'Share %'], rows,
                               widths=(Inches(3.8), Inches(1.6), Inches(1.2)),
                               bold_last_row=total is not None)


def _render_value(document, p, sub, chrome, note):
    # PDF shows BOTH a donut and the cost table — mirror that: image (when chrome)
    # plus the editable cost table always.
    if not p.get('rows'):
        _muted(document, 'No cost-loading information is available in the file.')
        return
    _add_chart_image(document, 'donut', p, chrome)
    _cost_table(document, p, 'Branch')


def _render_costbars(document, p, sub, chrome, note):
    if _add_chart_image(document, 'costbars', p, chrome):
        return
    _cost_table(document, p, 'WBS branch')


def _render_scope(document, p, sub, chrome, note):
    stats = p.get('stats') or []
    if stats:
        labels = [s.get('l', '') for s in stats]
        values = [s.get('v', '') for s in stats]
        docx_template.styled_table(document, labels, [values], bold_last_row=True)
    if p.get('intro'):
        _para(document, p['intro'])
    for b in p.get('blocks', []) or []:
        sub.heading(b.get('discipline', '') or '—')
        if b.get('paragraph'):
            _para(document, b['paragraph'])
        for pkg in b.get('packages', []) or []:
            para = document.add_paragraph(style='List Bullet')
            run = para.add_run(str(pkg))
            run.bold = True
            run.font.name = _FONT
            run.font.size = Pt(_BODY_PT)


def _render_table(document, p, sub, chrome, note):
    if p.get('view') == 'calendars':
        # Section 5 — delegated; sub-blocks follow the ACTUAL section number.
        docx_calendar.render_calendar(document, p, chrome, sub.number)
        return
    columns = p.get('columns') or ['—']
    rows = p.get('rows') or []
    if not rows:
        _muted(document, note or 'No rows are available for this table.')
        return
    docx_template.styled_table(document, columns, rows)


def _render_codes(document, p, sub, chrome, note):
    tables = p.get('tables', []) or []
    if not tables:
        _muted(document, 'No activity codes are defined in the file.')
        return
    for tbl in tables:
        sub.heading(tbl.get('dimension', '') or '—')
        rows = [[r.get('code'), r.get('description')] for r in tbl.get('rows', []) or []]
        if rows:
            docx_template.styled_table(document, ['Code', 'Description'], rows,
                                       widths=(Inches(1.8), Inches(4.8)))
        else:
            _muted(document, 'No values defined for this dimension.')


def _render_idanatomy(document, p, sub, chrome, note):
    aid = p.get('id', '') or ''
    lead = document.add_paragraph()
    lrun = lead.add_run('Example activity ID: ')
    lrun.font.name = _FONT
    lrun.font.size = Pt(_BODY_PT)
    idrun = lead.add_run(aid)
    idrun.bold = True
    idrun.font.name = 'Consolas'
    idrun.font.size = Pt(_BODY_PT)
    segs = [[s.get('label'), s.get('value')] for s in p.get('segments', []) or []]
    if segs:
        docx_template.styled_table(document, ['Part', 'Value'], segs,
                                   widths=(Inches(2.4), Inches(4.2)))


def _render_cashflow(document, p, sub, chrome, note):
    points = p.get('points', []) or []
    if not points:
        _muted(document, 'Time-phased cost information is not available in the file.')
        return
    _lead(document, 'Cumulative planned cost (cost-loaded S-curve) sampled across the '
                    'baseline — illustrative of the plan.')
    # chart image via the shared cashflow SVG + Chrome rasteriser; table fallback.
    placed = False
    if chrome:
        try:
            svg = chart_png.cashflow_svg(points)
            png = chart_png.render_svg_png(svg, 760, 320, chrome) if svg else None
            if png:
                document.add_picture(docx_charts.stream(png), width=_IMG_W)
                document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                placed = True
        except Exception:
            placed = False
    if not placed:
        rows = [[_fmt_iso(pt.get('date')), _money(pt.get('cumulative')),
                 '%s%%' % pt.get('pct')] for pt in points]
        docx_template.styled_table(document, ['Date', 'Cumulative cost', '% complete'],
                                   rows, widths=(Inches(1.9), Inches(2.6), Inches(1.6)))


_RENDER = {
    'overview': _render_overview,
    'ms_table': _render_ms_table,
    'wbs_tree': _render_wbs_tree,
    'seq': _render_seq,
    'interfaces': _render_interfaces,
    'prose': _render_prose,
    'keyvals': _render_keyvals,
    'image': _render_image,
    'timeline': _render_timeline,
    'value': _render_value,
    'scope': _render_scope,
    'table': _render_table,
    'codes': _render_codes,
    'idanatomy': _render_idanatomy,
    'costbars': _render_costbars,
    'cashflow': _render_cashflow,
}


def _render(document, section, sub, chrome):
    handler = _RENDER.get(section.get('kind'))
    payload = section.get('payload') or {}
    note = section.get('note')
    if handler is not None:
        handler(document, payload, sub, chrome, note)
        return
    # Graceful fallback for any unknown / future kind — never crash the export.
    for para in payload.get('paragraphs', []) or []:
        _para(document, para)
    if note:
        _muted(document, note)


# ── public entry point ───────────────────────────────────────────────────────
def write_docx(doc, output_path, chrome=None):
    """Render the narrative model (``doc``) to an editable .docx at ``output_path``.

    ``chrome`` is a path to a headless-Chrome binary (server.py passes ``_find_chrome()``):
    when present the chart kinds embed real graph images; when None every chart falls
    back to a native, editable table / outline so the export is always produced.
    """
    doc = doc or {}
    meta = doc.get('meta', {}) or {}
    document = Document()

    # Furniture (SLICE B): base styles, then geometry / border / footer on the
    # single section, the repeating header, the cover and the Table of Contents.
    docx_template.apply_base_styles(document)
    section0 = document.sections[0]
    docx_template.apply_page_geometry(section0)
    docx_template.add_page_border(section0)
    docx_template.add_footer(section0)
    docx_template.add_header(document, meta)
    docx_template.add_cover(document, meta)
    docx_template.add_toc(document)

    for idx, section in enumerate(doc.get('sections', []) or [], 1):
        try:
            number = int(section.get('number'))
        except (TypeError, ValueError):
            number = idx
        docx_template.heading(document, docx_template.format_number((number,)),
                              section.get('title', ''))
        _render(document, section, _Sub(document, number), chrome)

    document.save(output_path)
    return output_path
