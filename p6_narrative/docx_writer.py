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
from docx.enum.text import (WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT,
                             WD_TAB_LEADER)
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
    'Scope of Work': 'The scope is analysed from the activity codes, weighted by cost '
                     'loading.',
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
def _placeholder_box(document, text):
    """A clean, framed single-cell box holding centred muted placeholder text — used when no
    layout drawing was attached, so §2 shows a tidy prompt instead of a broken figure."""
    t = document.add_table(rows=1, cols=1)
    t.autofit = False
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _row_h(t.rows[0], 84, exact=False)
    c = t.rows[0].cells[0]
    _set_w(c, 6.6)
    _shade(c, 'F4F7FB')
    _cell_borders(c, color='C9D6E4', sz='6')
    c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    pp = c.paragraphs[0]
    pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pp.paragraph_format.space_before = Pt(2)
    pp.paragraph_format.space_after = Pt(2)
    run(pp, text, size=11, italic=True, color=GREY)
    return t


def _render_image(document, p, number, note):
    img = docx_template._img_bytes(p.get('image'))
    if not img:
        # C01a — no drawing attached: show the payload placeholder text in a clean framed box
        # (never a broken figure). TOC still lists §2 because the section always renders.
        placeholder = (p.get('placeholder')
                       or 'No project layout drawing was attached. Add one in the report '
                          'setup (Project Layout) to show the general arrangement here.')
        _placeholder_box(document, placeholder)
        return
    try:
        document.add_picture(img, width=Inches(6.6))
        document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception:
        # a bad/undecodable image → the framed placeholder box, never a broken figure
        _placeholder_box(document, p.get('placeholder')
                         or 'The attached project layout drawing could not be displayed.')
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
def _value_legend(document, rows, colors, unit):
    """C02 — the clean value legend/table beside the doughnut: a colour SWATCH (matching the
    slice), the type of work, its amount (#,##0) and its share %. Reuses ``docx_native``'s
    distinct-ramp colours so swatch == slice. Doubles as the graceful fallback (name + amount +
    share) when the native doughnut can't be drawn."""
    hdr = ['', 'Type of work', 'Amount' + (' (%s)' % unit if unit else ''), 'Share %']
    widths = [0.32, 3.5, 2.05, 1.03]
    t = document.add_table(rows=1, cols=4)
    t.style = 'Table Grid'
    t.autofit = False
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hr = t.rows[0]
    _row_h(hr, 20)
    for i, h in enumerate(hdr):
        c = hr.cells[i]
        _shade(c, '26517D'); _no_space(c)
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _set_w(c, widths[i])
        pp = c.paragraphs[0]
        if i >= 2:
            pp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run(pp, h, font=CAL, size=10, bold=True, color=WHITE)
    for i, r in enumerate(rows):
        rr = t.add_row()
        _row_h(rr, 19)
        sw, nm, am, sh = rr.cells
        for cc in rr.cells:
            _no_space(cc)
            cc.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _set_w(sw, widths[0]); _set_w(nm, widths[1])
        _set_w(am, widths[2]); _set_w(sh, widths[3])
        _shade(sw, colors[i] if i < len(colors) else NAVY_HEX)   # colour swatch == slice
        run(nm.paragraphs[0], r.get('name'), size=11)
        pa = am.paragraphs[0]; pa.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run(pa, _money(r.get('amount')), size=11)
        ps = sh.paragraphs[0]; ps.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        pct = r.get('pct')
        run(ps, ('%s%%' % pct) if pct is not None else '', size=11)
    return t


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
    # §6 — a DOUGHNUT of the value distribution by type of work (distinct-ramp slices, NO
    # crowded on-slice amount labels). Below it a clean value legend/table (C02): swatch +
    # type + amount (#,##0) + share%. The legend also stands in as the editable fallback if
    # the native chart can't be drawn, so the amounts are never lost.
    docx_native.add_doughnut(document, cats, vals, num_fmt='#,##0')
    para(document, '', after=2)
    _value_legend(document, rows, docx_native.ramp_colors(cats), unit)


# ── §6 Scope of Work ──────────────────────────────────────────────────────────
def _scope_composition(document, items, unit):
    """§6.1 — a single 100 %-stacked horizontal COMPOSITION BAR split into one ramp-coloured
    segment per discipline (segment size = that discipline's share of value), with a legend
    of discipline names and a percentage label line beneath ("Civil 93.9% · …"). Falls back
    to an editable cost/share table if the native chart can't be built."""
    items = [it for it in (items or []) if it]
    if not items:
        _muted(document, 'No cost-loaded items are available for this breakdown.')
        return
    names = [str(it.get('name') or '—') for it in items]
    costs = [it.get('cost') for it in items]
    if docx_native.add_composition_bar(document, names, costs) is None:
        data_table(document, ['Discipline', 'Amount' + (' (%s)' % unit if unit else ''),
                              'Share %'],
                   [[it.get('name'), _money(it.get('cost')),
                     ('%s%%' % it.get('pct')) if it.get('pct') is not None else '']
                    for it in items],
                   widths=[3.7, 2.0, 1.2], aligns=[None, 'r', 'r'])
        return
    # percentage label line beneath the composed bar (the approved "Civil 93.9% · …")
    parts = ['%s %s%%' % (it.get('name') or '—', it.get('pct'))
             for it in items if it.get('pct') is not None]
    if parts:
        para(document, '  ·  '.join(parts), size=10, color=BODYNAVY,
             align=WD_ALIGN_PARAGRAPH.CENTER, before=4, after=2)


def _render_scope(document, p, number, note):
    unit = p.get('unit')

    def _cur(v):
        """Money with the currency prefix — 'EGP 794,684,896' (matches the narrative)."""
        m = _money(v)
        return ('%s %s' % (unit, m)) if (unit and m) else m

    # intro — the scope is derived by cross-filtering the picked activity codes
    para(document,
         'The scope is analysed by cross-filtering the picked activity codes '
         '(Type of Work, Building / Area, and work type).',
         align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=8)

    # {number}.1 — scope overview by discipline (a single 100%-stacked COMPOSITION BAR:
    # one ramp-coloured segment per discipline, sized to its % share of value)
    disciplines = p.get('disciplines') or []
    _subhead(document, '%s.1' % number, 'Scope overview — by discipline')
    if disciplines:
        _scope_composition(document, disciplines, unit)
    else:
        _muted(document, 'No cost-loaded activity codes are available to analyse the scope.')

    # editable, justified narrative prose (the auto-summary callout)
    narrative = p.get('narrative')
    if narrative:
        para(document, narrative, align=WD_ALIGN_PARAGRAPH.JUSTIFY, before=8, after=8)

    # {number}.2 — scope by area / structure: one described block per area, no charts
    _subhead(document, '%s.2' % number, 'Scope by area / structure')
    areas = [a for a in (p.get('areas') or []) if a]
    if not areas:
        _muted(document, 'No building- or area-level breakdown is available for this scope.')
        return
    for a in areas:
        label = a.get('label') or '—'
        count = a.get('count') or 1
        each = bool(a.get('each'))
        pct = a.get('pct')
        # quantity suffix: 'each' when priced per unit, '· N areas' when several are grouped
        if each:
            qty = ' each'
        elif count and int(count) > 1:
            qty = ' · %s areas' % _count(count)
        else:
            qty = ''
        pct_txt = (' (%s%%)' % pct) if pct is not None else ''
        # ➢ heading line — bold navy, carries label + cost + quantity + share
        ph = para(document, before=9, after=2)
        run(ph, '➢ %s — %s%s%s' % (label, _cur(a.get('cost')), qty, pct_txt),
            bold=True, color=NAVY)
        # per-discipline: bold discipline NAME on its own line, then each work type on its OWN
        # line with a • bullet (C03c — a vertical bullet list, not the old inline "· ✓ …" run)
        for disc in (a.get('disciplines') or []):
            if not disc:
                continue
            name = disc.get('name') or 'Works'
            wts = [w for w in (disc.get('worktypes') or []) if w]
            dp = para(document, before=3, after=1)
            dp.paragraph_format.left_indent = Inches(0.28)
            run(dp, name, bold=True, color=DKNAVY)
            for wt in wts:
                wp = para(document, before=0, after=1)
                wp.paragraph_format.left_indent = Inches(0.54)
                run(wp, '•  ', bold=True, color=GREEN)
                run(wp, wt)


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
def _wbs_overview_nodes(overview):
    """x.1 node tree: lv0 project root → lv1 major-WBS children (for add_wbs_tree)."""
    return {'name': overview.get('name'), 'level': 0,
            'children': [{'name': c.get('name'), 'level': 1, 'children': []}
                         for c in (overview.get('children') or [])]}


def _wbs_branch_nodes(br):
    """x.n node tree: lv1 branch root → lv2 columns → lv3 → lv4 (from the payload columns).

    Payload column shape: ``[l2name, [[l3name, [l4name, …]], …]]``."""
    def l3_node(entry):
        l3name = entry[0] if entry else ''
        l4names = entry[1] if len(entry) > 1 else []
        return {'name': l3name, 'level': 3,
                'children': [{'name': x, 'level': 4, 'children': []}
                             for x in (l4names or [])]}

    def col_node(col):
        l2name = col[0] if col else ''
        l3list = col[1] if len(col) > 1 else []
        return {'name': l2name, 'level': 2,
                'children': [l3_node(e) for e in (l3list or [])]}

    return {'name': br.get('name'), 'level': 1,
            'children': [col_node(c) for c in (br.get('columns') or [])]}


def _wbs_fallback_table(document, root):
    """Graceful editable fallback when the native tree can't be built: the same WBS as an
    indented, level-shaded single-column table (still fully editable in Word)."""
    flat = []

    def walk(n):
        try:
            lvl = int(n.get('level'))
        except (TypeError, ValueError):
            lvl = 0
        flat.append((lvl, n.get('name') or ''))
        for k in (n.get('children') or []):
            walk(k)

    walk(root)
    if not flat:
        _muted(document, 'No work breakdown structure is defined in the file.')
        return
    base = min(l for l, _ in flat)
    fills = {0: NAVY_HEX, 1: 'BCD3EA', 2: 'DEEAF6', 3: 'E6EEF7', 4: 'FFFFFF'}
    t = document.add_table(rows=0, cols=1)
    t.style = 'Table Grid'
    t.autofit = False
    for lvl, name in flat:
        rr = t.add_row()
        _row_h(rr, 18, exact=False)
        c = rr.cells[0]
        _set_w(c, 6.9); _no_space(c)
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _shade(c, fills.get(min(max(lvl, 0), 4), 'FFFFFF'))
        pp = c.paragraphs[0]
        pp.paragraph_format.left_indent = Inches(0.22 * max(lvl - base, 0))
        run(pp, name, size=11, bold=(lvl <= 1),
            color=(WHITE if lvl == 0 else DKNAVY))
    return t


def _render_wbs_tree(document, p, number, note):
    overview = p.get('overview') or {}
    branches = p.get('branches') or []
    if not (overview or branches):
        _muted(document, 'No work breakdown structure is defined in the file.')
        return
    if overview and (overview.get('name') or overview.get('children')):
        _subhead(document, '%s.1' % number, 'WBS Overview')
        root = _wbs_overview_nodes(overview)
        if docx_native.add_wbs_tree(document, [root]) is None:
            _wbs_fallback_table(document, root)
    for i, br in enumerate(branches):
        _subhead(document, '%s.%d' % (number, i + 2),
                 '%s — breakdown' % (br.get('name') or '—'))
        root = _wbs_branch_nodes(br)
        if docx_native.add_wbs_tree(document, [root]) is None:
            _wbs_fallback_table(document, root)


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


# ── drawing-id de-duplication (guards against Word's "repair" on open) ─────────
def _dedupe_drawing_ids(document):
    """Give every drawing object a globally-unique id across the WHOLE package.

    Every inline drawing carries a ``<wp:docPr id>`` and every picture / grouped
    shape a ``<pic:cNvPr id>`` / ``<wps:cNvPr id>`` (and the group frame a
    ``<wp:docPr id>``). Word treats two drawing objects that share an id as
    corruption and, on open, offers to *repair* the file — dropping all content
    after the clash (the reader sees only the first few pages, blank).

    The ids were previously allocated per *story*: the header logos (built by
    :func:`docx_template.add_header`) numbered 1, 2, 3 while the body's native
    charts / calendar histograms / WBS org-charts (and the §2 layout image) also
    restarted at 1 — because :func:`docx_native._next_id` scans only the document
    body and python-docx's ``add_picture`` scans only the header story. On a rich
    P6 file (many body drawings) those ranges overlap and Word repairs the file;
    on a sparse file the body has no native drawings so nothing collides — which is
    exactly why the bug only showed up with rich data.

    This final pass walks every story part (document body + all headers/footers)
    and renumbers every ``docPr`` / ``cNvPr`` id from a single monotonic counter,
    so no two drawing objects anywhere in the package can share an id regardless of
    how many charts, calendars or WBS branches the report contains. These ids are
    non-visual labels referenced by nothing else, so renumbering them is safe.
    """
    counter = 0
    try:
        parts = list(document.part.package.iter_parts())
    except Exception:                       # pragma: no cover - defensive
        return
    for part in parts:
        el = getattr(part, 'element', None)
        if el is None or not hasattr(el, 'iter'):
            continue
        for node in el.iter():
            tag = node.tag
            if not isinstance(tag, str):     # comments / processing instructions
                continue
            if tag.rsplit('}', 1)[-1] in ('docPr', 'cNvPr') and node.get('id') is not None:
                counter += 1
                node.set('id', str(counter))


# ── static Table of Contents (mirrors html.py _toc / _TOC_GROUPS) ─────────────
# Same grouping and order the PDF/screen TOC uses. Any section whose title is not in a
# named group is listed last under "OTHER" (defensive — every current section is grouped).
_TOC_GROUPS = [
    ('PROJECT DEFINITION', ('Project Overview', 'Project Layout', 'Project Brief')),
    ('BASELINE TARGETS', ('Major Milestones', 'Key Dates', 'Contract Value')),
    ('SCOPE & STRUCTURE', ('Scope of Work', 'Project Calendars & Holidays',
                           'Work Breakdown Structure', 'Activity Codes')),
]


def _toc_group_header(document, label):
    """A navy, small-caps group header with a hairline underneath (the PDF look)."""
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    r = run(p, label.upper(), font=CAL, size=10.5, bold=True, color=NAVY)
    r.font.small_caps = True
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement('w:pBdr'); bot = OxmlElement('w:bottom')
    bot.set(qn('w:val'), 'single'); bot.set(qn('w:sz'), '6')
    bot.set(qn('w:space'), '3'); bot.set(qn('w:color'), 'DBE1E8')
    pbdr.append(bot); pPr.append(pbdr)
    return p


def _bookmark_para(para, name, bid):
    """Anchor a bookmark at a heading paragraph so a TOC PAGEREF can resolve its REAL page."""
    p = para._p
    start = OxmlElement('w:bookmarkStart')
    start.set(qn('w:id'), str(bid)); start.set(qn('w:name'), name)
    end = OxmlElement('w:bookmarkEnd'); end.set(qn('w:id'), str(bid))
    pPr = p.find(qn('w:pPr'))
    if pPr is not None:
        pPr.addnext(start)
    else:
        p.insert(0, start)
    p.append(end)


def _toc_pageref(p, bookmark, fallback):
    """A right-aligned PAGEREF field to ``bookmark`` — shows the section's REAL page once Word
    refreshes fields on open (enable_update_fields), with ``fallback`` (the ordinal) cached
    so the row is never blank before that refresh."""
    def _fld(t):
        rr = p.add_run(); fc = OxmlElement('w:fldChar'); fc.set(qn('w:fldCharType'), t)
        rr._r.append(fc)
    _fld('begin')
    rr = p.add_run(); it = OxmlElement('w:instrText'); it.set(qn('xml:space'), 'preserve')
    it.text = ' PAGEREF %s \\h ' % bookmark; rr._r.append(it)
    _fld('separate')
    run(p, str(fallback), size=12, color=NAVY)
    _fld('end')


def _toc_row(document, number, title, page):
    """One TOC line: 'N)  Title' … <dotted leader> … REAL page (PAGEREF field, ordinal fallback)."""
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.tab_stops.add_tab_stop(Inches(7.0), WD_TAB_ALIGNMENT.RIGHT,
                                              WD_TAB_LEADER.DOTS)
    run(p, '%s)  ' % number, size=12, bold=True, color=NAVY)
    run(p, '' if title is None else str(title), size=12)
    run(p, '\t', size=12)
    _toc_pageref(p, '_sec_%s' % number, page)
    return p


def _static_toc(document, sections):
    """A STATIC, already-populated Table of Contents on its own page — the Word twin of
    ``html.py._toc``. No live Word field (which shows only 'Right-click to update field'
    until manually refreshed): the rows are written out, grouped and numbered exactly as
    the PDF/screen TOC. ``sections`` is the ordered list of section dicts."""
    # centred navy title + underline bar (mirrors html _toc)
    tp = document.add_paragraph()
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tp.paragraph_format.space_after = Pt(2)
    run(tp, 'Table of Contents', font=CAL, size=22, bold=True, color=NAVY)
    bar = document.add_paragraph()
    bar.alignment = WD_ALIGN_PARAGRAPH.CENTER
    bar.paragraph_format.space_after = Pt(8)
    br = run(bar, ' ' * 8, font=CAL, size=2, color=NAVY)  # short centred rule
    rPr = br._element.get_or_add_rPr()
    bdr = OxmlElement('w:bdr')
    bdr.set(qn('w:val'), 'single'); bdr.set(qn('w:sz'), '18')
    bdr.set(qn('w:space'), '0'); bdr.set(qn('w:color'), '1F4E79')
    rPr.append(bdr)

    # ordinal (page) per section — the same value the PDF uses: enumerate(sections, 1)
    paged = list(enumerate([s for s in sections if s], 1))
    by_title = {}
    for pg, s in paged:
        by_title.setdefault(s.get('title'), (s, pg))
    used = set()
    for label, titles in _TOC_GROUPS:
        rowspecs = [(by_title[t][0], by_title[t][1]) for t in titles if t in by_title]
        if not rowspecs:
            continue
        _toc_group_header(document, label)
        for s, pg in rowspecs:
            used.add(s.get('title'))
            _toc_row(document, s.get('number'), s.get('title'), pg)
    extra = [(s, pg) for pg, s in paged if s.get('title') not in used]
    if extra:
        _toc_group_header(document, 'OTHER')
        for s, pg in extra:
            _toc_row(document, s.get('number'), s.get('title'), pg)
    document.add_page_break()


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

    sections = [s for s in (doc.get('sections') or []) if s]
    # A STATIC, already-populated TOC (not a live Word field) on its own page.
    _static_toc(document, sections)

    for idx, section in enumerate(sections, 1):
        try:
            number = int(section.get('number'))
        except (TypeError, ValueError):
            number = idx
        hp = docx_template.heading(document, docx_template.format_number((number,)),
                                   section.get('title', ''))
        _bookmark_para(hp, '_sec_%s' % number, 900 + number)   # PAGEREF target for the TOC
        _render(document, section, number)
        if idx < len(sections):
            document.add_page_break()

    # Real TOC page numbers: refresh all fields (the TOC PAGEREFs) with the true page on open.
    docx_template.enable_update_fields(document)
    # Final safety pass: guarantee every drawing object has a document-wide unique id
    # (header logos vs. body charts/org-charts) so Word never "repairs" the file on open.
    _dedupe_drawing_ids(document)

    document.save(output_path)
    return output_path
