"""Write the redesigned Baseline Narrative Report (10 sections) to a professional,
natively-editable Word (.docx) document.

This writer draws STRAIGHT FROM THE SECTION PAYLOADS emitted by
:func:`p6_narrative.report.build_report` → ``to_dict()`` — no re-derivation. It is the
Word twin of the approved on-screen / PDF look (``mockups/narrative_full.html``) and
reproduces the approved ``.docx`` builders (``scratchpad/build_narrative_v2.py``):
composition / dashboard / hours TILES, the navy total BANNER, native HORIZONTAL bar
charts (§6 / §7), the stacked green/red calendar histograms with net-working-day
labels (§8.2), the horizontal WBS org-charts with connectors (§9) and the two-per-row
Activity-Code tables (§10).

Page furniture (A4 portrait, the double page border, the 3-logo header, the centred
page-number footer, the cover and Table-of-Contents, base styles) is laid down by
:mod:`p6_narrative.docx_template`; every chart / diagram is a NATIVE, editable Word
object built by :mod:`p6_narrative.docx_native` (a real ``c:chartSpace`` chart part or a
grouped-shape ``wpg:wgp`` drawing — never a rasterised picture). Section 8 (Project
Calendars & Holidays) is delegated to :mod:`p6_narrative.docx_calendar`.

Body font is Times New Roman 12; section headings are navy (#1F4E79) Calibri Light.
Only the page frame follows the template — the body DATA equals the PDF body DATA.

Section kinds handled (renumbered 1..10 by the producer):

    overview · image · keyvals · ms_table · value_bars · scope · table(calendars) ·
    wbs_tree · codes

Every renderer is guarded: a missing / empty payload renders a short muted line and
never raises, so the export is always produced.
"""
from docx import Document
from docx.enum.table import (WD_ALIGN_VERTICAL, WD_ROW_HEIGHT_RULE,
                             WD_TABLE_ALIGNMENT)
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from p6_narrative import docx_calendar, docx_native, docx_template

# ── palette / fonts (mirror the approved builder) ─────────────────────────────
NAVY = RGBColor(0x1F, 0x4E, 0x79)
INK = RGBColor(0x1A, 0x1D, 0x21)
GREY = RGBColor(0x8A, 0x90, 0x99)
DKNAVY = RGBColor(0x14, 0x32, 0x4F)
GREEN = RGBColor(0x1F, 0x7A, 0x3D)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SUBNAVY = RGBColor(0x17, 0x45, 0x7A)
BODYNAVY = RGBColor(0x4A, 0x55, 0x60)

TNR = 'Times New Roman'
CAL = 'Calibri'
FILL_TILE = 'DEEAF6'
FILL_LABEL = 'EEF3F9'
NAVY_HEX = '1F4E79'
ZEBRA = 'F7F9FB'


# ── short leads shown under each section heading (generic; not project-specific) ──
_LEADS = {
    'Project Brief': 'The key contractual and programme data for the project, as '
                     'recorded in the baseline schedule.',
    'Major Milestones': 'The major milestones defined in the baseline schedule '
                        '(Start and Finish), in chronological order.',
    'Key Dates': 'All Start and Finish milestones defined in the baseline schedule, '
                 'in chronological order.',
    'Contract Value': 'The contract value and its distribution by type of work '
                      '(discipline activity code), from cost loading.',
    'Scope of Work': 'The scope is summarised by discipline (share of contract value), '
                     'then set out per building and element, read from the activity codes.',
    'Work Breakdown Structure': 'The project WBS is presented as an organisation chart, '
                                'then each major branch is expanded — to Level 4 where a '
                                'branch’s Level-4 nodes are 4 or fewer, otherwise to Level 3.',
    'Activity Codes': 'The baseline uses the following activity-code structures. Each '
                      'code and its values is listed below.',
}


# ── formatting helpers ────────────────────────────────────────────────────────
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


def _font(run_, font, size, bold, italic, color, underline=False):
    run_.font.name = font
    run_.font.size = Pt(size)
    run_.font.bold = bold
    run_.font.italic = italic
    run_.font.underline = underline
    if color is not None:
        run_.font.color.rgb = color
    rp = run_._element.get_or_add_rPr()
    rfn = OxmlElement('w:rFonts')
    rfn.set(qn('w:ascii'), font)
    rfn.set(qn('w:hAnsi'), font)
    rp.append(rfn)
    return run_


def run(p, text, font=TNR, size=12, bold=False, italic=False, color=None, underline=False):
    r = p.add_run('' if text is None else str(text))
    return _font(r, font, size, bold, italic, color, underline)


def para(document, text='', size=12, bold=False, italic=False, color=None,
         before=0, after=6, align=None, font=TNR):
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    if align is not None:
        p.alignment = align
    if text:
        run(p, text, font=font, size=size, bold=bold, italic=italic, color=color)
    return p


def _shade(cell, hex6):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:fill'), hex6)
    tcPr.append(shd)


def _no_space(cell):
    for p in cell.paragraphs:
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)


def _cell_borders(cell, color='B9C6D3', sz='4'):
    tcPr = cell._tc.get_or_add_tcPr()
    tb = OxmlElement('w:tcBorders')
    for edge in ('top', 'left', 'bottom', 'right'):
        e = OxmlElement('w:' + edge)
        e.set(qn('w:val'), 'single'); e.set(qn('w:sz'), sz)
        e.set(qn('w:space'), '0'); e.set(qn('w:color'), color)
        tb.append(e)
    tcPr.append(tb)


def _set_w(cell, inches):
    cell.width = Inches(inches)
    tcPr = cell._tc.get_or_add_tcPr()
    tcW = OxmlElement('w:tcW')
    tcW.set(qn('w:w'), str(int(inches * 1440)))
    tcW.set(qn('w:type'), 'dxa')
    tcPr.append(tcW)


def _row_h(rw, pts, exact=True):
    rw.height = Pt(pts)
    rw.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY if exact else WD_ROW_HEIGHT_RULE.AT_LEAST


def _subhead(document, num, title, size=12):
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(7)
    run(p, ('%s  %s' % (num, title)).strip().upper(), font=CAL, size=size,
        bold=True, color=SUBNAVY)
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement('w:pBdr'); bot = OxmlElement('w:bottom')
    bot.set(qn('w:val'), 'single'); bot.set(qn('w:sz'), '6')
    bot.set(qn('w:space'), '2'); bot.set(qn('w:color'), 'DBE1E8')
    pbdr.append(bot); pPr.append(pbdr)
    return p


def _muted(document, text):
    return para(document, text, size=11, italic=True, color=GREY, after=4)


# ── composite builders (ported from build_narrative_v2.py) ────────────────────
def tiles(document, items, per_row=None, big_size=17, label_size=8.5, fill=FILL_TILE,
          border='B9D1EA', numcolor=NAVY, height=44):
    """A row (or grid) of KPI / composition tiles: big value over a small label."""
    items = list(items or [])
    if not items:
        return None
    per_row = per_row or len(items)
    n = len(items)
    rows = (n + per_row - 1) // per_row
    outer = document.add_table(rows=rows, cols=per_row)
    outer.autofit = False
    outer.alignment = WD_TABLE_ALIGNMENT.CENTER
    idx = 0
    total_w = 6.9
    for r in range(rows):
        _row_h(outer.rows[r], height, exact=False)
        for c in range(per_row):
            cell = outer.rows[r].cells[c]
            _set_w(cell, total_w / per_row)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            if idx < n:
                lbl, val = items[idx]
                _shade(cell, fill); _cell_borders(cell, border)
                p1 = cell.paragraphs[0]
                p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p1.paragraph_format.space_before = Pt(2)
                p1.paragraph_format.space_after = Pt(0)
                run(p1, val, font=CAL, size=big_size, bold=True, color=numcolor)
                p2 = cell.add_paragraph()
                p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p2.paragraph_format.space_before = Pt(0)
                p2.paragraph_format.space_after = Pt(2)
                run(p2, lbl, font=CAL, size=label_size, color=BODYNAVY)
            idx += 1
    return outer


def kv_table(document, rows, label_w=2.5, val_w=4.4, h=21):
    """Key/value table — navy shaded label column, uniform row heights."""
    rows = list(rows or [])
    if not rows:
        return None
    t = document.add_table(rows=len(rows), cols=2)
    t.style = 'Table Grid'
    t.autofit = False
    for i, (k, v) in enumerate(rows):
        rw = t.rows[i]
        _row_h(rw, h)
        lc, vc = rw.cells
        _set_w(lc, label_w); _set_w(vc, val_w)
        lc.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        vc.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _shade(lc, FILL_LABEL); _no_space(lc); _no_space(vc)
        run(lc.paragraphs[0], k, size=11.5, bold=True, color=NAVY)
        run(vc.paragraphs[0], v, size=11.5)
    return t


def data_table(document, headers, rows, widths=None, h=21, aligns=None):
    """Navy-header data table with uniform row heights + zebra striping."""
    t = document.add_table(rows=1, cols=len(headers))
    t.style = 'Table Grid'
    t.autofit = False
    hr = t.rows[0]
    _row_h(hr, h)
    for i, hd in enumerate(headers):
        c = hr.cells[i]
        _shade(c, '26517D'); _no_space(c)
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        if widths:
            _set_w(c, widths[i])
        p = c.paragraphs[0]
        if aligns and aligns[i] == 'r':
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run(p, hd, font=CAL, size=10, bold=True, color=WHITE)
    for ri, row_vals in enumerate(rows or []):
        rr = t.add_row()
        _row_h(rr, h)
        for ci, val in enumerate(row_vals):
            if ci >= len(rr.cells):
                break
            c = rr.cells[ci]
            _no_space(c); c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            if widths:
                _set_w(c, widths[ci])
            if ri % 2 == 1:
                _shade(c, ZEBRA)
            p = c.paragraphs[0]
            if aligns and aligns[ci] == 'r':
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run(p, val, size=11)
    return t


def banner(document, left_text, right_text):
    """Navy total banner — a 2-cell full-width bar (label left, value right)."""
    ban = document.add_table(rows=1, cols=2)
    ban.autofit = False
    _row_h(ban.rows[0], 30, exact=False)
    lc, rc = ban.rows[0].cells
    _set_w(lc, 3.4); _set_w(rc, 3.5)
    _shade(lc, NAVY_HEX); _shade(rc, NAVY_HEX)
    lc.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    rc.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    _no_space(lc); _no_space(rc)
    run(lc.paragraphs[0], '  ' + left_text, font=CAL, size=11, bold=True, color=WHITE)
    pr = rc.paragraphs[0]
    pr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run(pr, right_text + '  ', font=CAL, size=15, bold=True, color=WHITE)
    return ban


def _arrow(document, text):
    p = document.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    run(p, '➢ ', size=12, bold=True, color=NAVY)
    run(p, text, size=12, bold=True)
    return p


def _check(document, text, indent=0.5):
    p = document.add_paragraph()
    p.paragraph_format.left_indent = Inches(indent)
    p.paragraph_format.space_after = Pt(1)
    run(p, '✓ ', size=12, color=GREEN)
    run(p, text, size=12)
    return p


def _code_table(cell, title, rows):
    """One small 'Code Value | Description' table inside ``cell``."""
    run(cell.paragraphs[0], title, size=12, bold=True)
    t = cell.add_table(rows=1, cols=2)
    t.style = 'Table Grid'
    t.autofit = False
    hr = t.rows[0]
    _row_h(hr, 18)
    for i, h in enumerate(['Code Value', 'Description']):
        hc = hr.cells[i]
        _shade(hc, 'DBE5F1'); _no_space(hc)
        _set_w(hc, 1.2 if i == 0 else 2.1)
        pp = hc.paragraphs[0]
        pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run(pp, h, font=CAL, size=9.5, bold=True, color=DKNAVY)
    for cv, desc in rows:
        rr = t.add_row()
        _row_h(rr, 18)
        c0, c1 = rr.cells
        _no_space(c0); _no_space(c1); _set_w(c0, 1.2); _set_w(c1, 2.1)
        c0.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        c1.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p0 = c0.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run(p0, cv, size=10.5, bold=True)
        run(c1.paragraphs[0], desc, size=10.5)
    return t


# ── §1 Project Overview ───────────────────────────────────────────────────────
def _render_overview(document, p, number, note):
    for txt in p.get('paragraphs') or []:
        para(document, txt)
    breakdown = p.get('breakdown') or []
    if breakdown:
        para(document, 'Baseline composition', size=11, bold=True, color=NAVY,
             before=6, after=6, font=CAL)
        items = [(str(b.get('world', '')), _count(b.get('count'))) for b in breakdown]
        tiles(document, items, per_row=min(len(items), 4), big_size=20, height=50)
        total = p.get('total')
        if total is not None:
            para(document, 'Total: %s baseline activities across %d major scopes.'
                 % (_count(total), len(breakdown)), size=11.5, before=8, after=0)


# ── §2 Project Layout ─────────────────────────────────────────────────────────
def _render_image(document, p, number, note):
    img = docx_template._img_bytes(p.get('image'))
    if not img:
        _muted(document, 'No layout image provided.')
        return
    try:
        document.add_picture(img, width=Inches(6.6))
        document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception:
        _muted(document, '[project layout image]')
        return
    para(document, 'Figure 1 — %s' % (p.get('caption') or 'Project general layout'),
         size=10, italic=True, color=GREY, align=WD_ALIGN_PARAGRAPH.CENTER, before=4)


# ── §3 Project Brief ──────────────────────────────────────────────────────────
def _render_keyvals(document, p, number, note):
    rows = [(r.get('k'), r.get('v')) for r in (p.get('rows') or [])]
    if not rows:
        _muted(document, 'No project brief fields are available.')
        return
    kv_table(document, rows)


# ── §4 / §5 milestone + key-date tables ───────────────────────────────────────
def _render_ms_table(document, p, number, note):
    cols = p.get('columns') or ['Milestone', 'Date']
    rows = p.get('rows') or []
    if not rows:
        _muted(document, note or 'No Start/Finish milestones are defined in the file.')
        return
    data_table(document, cols, rows, widths=[4.6, 2.3])


# ── §6 Contract Value ─────────────────────────────────────────────────────────
def _render_value_bars(document, p, number, note):
    total = p.get('total')
    unit = p.get('unit')
    right = _money(total)
    if unit:
        right = '%s %s' % (right, unit)
    banner(document, 'TOTAL CONTRACT VALUE', right)
    para(document, '', after=4)
    rows = p.get('rows') or []
    if not rows:
        _muted(document, 'No cost-loading information is available in the file.')
        return
    cats = [str(r.get('name', '')) for r in rows]
    vals = [r.get('amount') for r in rows]
    title = 'Contract value by type of work' + (' (%s)' % unit if unit else '')
    if docx_native.add_hbar(document, cats, vals, title, color='1F4E79',
                            name=unit or 'Value') is None:
        # native chart unavailable → an editable value table as a graceful fallback
        data_table(document, ['Type of work', 'Amount', 'Share %'],
                   [[r.get('name'), _money(r.get('amount')), '%s%%' % r.get('pct')]
                    for r in rows], widths=[3.7, 2.0, 1.2], aligns=[None, 'r', 'r'])


# ── §7 Scope of Work ──────────────────────────────────────────────────────────
def _render_scope(document, p, number, note):
    disciplines = p.get('disciplines') or []
    if disciplines:
        para(document, 'Scope by discipline — share of contract value', size=10.5,
             bold=True, color=NAVY, before=2, after=6, font=CAL)
        cats = [str(d.get('name', '')) for d in disciplines]
        vals = [d.get('pct') for d in disciplines]
        if docx_native.add_hbar(document, cats, vals, 'Share of contract value (%)',
                                color='2E75B6', name='% of value') is None:
            data_table(document, ['Discipline', 'Share %'],
                       [[d.get('name'), '%s%%' % d.get('pct')] for d in disciplines],
                       widths=[4.6, 2.3], aligns=[None, 'r'])
    sections = p.get('sections') or []
    for i, sec in enumerate(sections, 1):
        disc = sec.get('discipline') or 'Discipline'
        hp = document.add_paragraph()
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        hp.paragraph_format.space_before = Pt(10)
        run(hp, '%s.%d  Detailed %s Scope of Work includes:—' % (number, i, disc),
            size=13, bold=True, color=DKNAVY, underline=True)
        for b in sec.get('buildings') or []:
            _arrow(document, b.get('name') or '—')
            for el in b.get('elements') or []:
                _check(document, el)


# ── §8 Project Calendars & Holidays (delegated) ───────────────────────────────
def _render_table(document, p, number, note):
    if p.get('view') == 'calendars':
        docx_calendar.render_calendar(document, p, None, number)
        return
    cols = p.get('columns') or ['—']
    rows = p.get('rows') or []
    if not rows:
        _muted(document, note or 'No rows are available for this table.')
        return
    data_table(document, cols, rows)


# ── §9 Work Breakdown Structure ───────────────────────────────────────────────
def _render_wbs_tree(document, p, number, note):
    overview = p.get('overview') or {}
    branches = p.get('branches') or []
    if not (overview or branches):
        _muted(document, 'No work breakdown structure is defined in the file.')
        return
    if overview:
        _subhead(document, '%s.1' % number, 'WBS Overview')
        names = [c.get('name') for c in (overview.get('children') or [])]
        if names:
            docx_native.add_org_flat(document, overview.get('name'), names)
    for i, br in enumerate(branches):
        _subhead(document, '%s.%d' % (number, i + 2),
                 '%s — breakdown' % (br.get('name') or '—'))
        docx_native.add_org_cols(document, br.get('name'), br.get('columns') or [])


# ── §10 Activity Codes ────────────────────────────────────────────────────────
def _render_codes(document, p, number, note):
    tables = p.get('tables') or []
    if not tables:
        _muted(document, 'No activity codes are defined in the file.')
        return
    # two small Code Value | Description tables per row, equal row heights
    for i in range(0, len(tables), 2):
        pair = tables[i:i + 2]
        container = document.add_table(rows=1, cols=2)
        container.autofit = False
        cells = container.rows[0].cells
        _set_w(cells[0], 3.45); _set_w(cells[1], 3.45)
        for j, tbl in enumerate(pair):
            dim = tbl.get('dimension') or 'Codes'
            rows = [(r.get('code'), r.get('description')) for r in (tbl.get('rows') or [])]
            _code_table(cells[j], '%d · %s' % (i + j + 1, dim), rows)
        para(document, '', after=6)


_RENDER = {
    'overview': _render_overview,
    'image': _render_image,
    'keyvals': _render_keyvals,
    'ms_table': _render_ms_table,
    'value_bars': _render_value_bars,
    'scope': _render_scope,
    'table': _render_table,
    'wbs_tree': _render_wbs_tree,
    'codes': _render_codes,
}


def _render(document, section, number):
    kind = section.get('kind')
    payload = section.get('payload') or {}
    note = section.get('note')
    lead = _LEADS.get(section.get('title'))
    if lead and kind not in ('overview', 'image'):
        para(document, lead, size=11, italic=True, color=GREY, after=8)
    handler = _RENDER.get(kind)
    if handler is not None:
        handler(document, payload, number, note)
        return
    # graceful fallback for any unknown / future kind — never crash the export
    for txt in payload.get('paragraphs') or []:
        para(document, txt)
    if note:
        _muted(document, note)


# ── public entry point ────────────────────────────────────────────────────────
def write_docx(doc, output_path, chrome=None):
    """Render the narrative model (``doc``) to an editable .docx at ``output_path``.

    ``chrome`` is accepted for signature compatibility with the caller (``server.py``);
    the redesigned Word export needs no browser — every chart is a native Word object —
    so it is ignored.
    """
    doc = doc or {}
    meta = doc.get('meta', {}) or {}
    document = Document()

    docx_template.apply_base_styles(document)
    section0 = document.sections[0]
    docx_template.apply_page_geometry(section0)
    docx_template.add_page_border(section0)
    docx_template.add_footer(section0)
    docx_template.add_header(document, meta)
    docx_template.add_cover(document, meta)
    docx_template.add_toc(document)

    sections = [s for s in (doc.get('sections') or []) if s]
    for idx, section in enumerate(sections, 1):
        try:
            number = int(section.get('number'))
        except (TypeError, ValueError):
            number = idx
        docx_template.heading(document, docx_template.format_number((number,)),
                              section.get('title', ''))
        _render(document, section, number)
        if idx < len(sections):
            document.add_page_break()

    document.save(output_path)
    return output_path
