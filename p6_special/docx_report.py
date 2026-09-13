"""Real Word (.docx) generator for Reporting Studio — a native ``python-docx``
document that matches the PDF as closely as Word allows.

Unlike :mod:`p6_special.word_export` (an Office-HTML ``.doc`` wrapper), this module
writes a *genuine* ``.docx`` package: a true double **navy** page border on every
page (``w:pgBorders``), a repeating 3-logo header, a live page-number footer, a
navy cover page, navy-header zebra tables — and, importantly, the ``bars`` /
``segbar`` payloads drawn as real horizontal BARS (shaded proportional cells), not
dumped as a value table, so a bars result looks like it does in the PDF.

The house style (A4 portrait · double navy frame · Calibri / Calibri Light · navy
``1F4E79`` headings · navy-header tables) is the Baseline-Narrative Word toolkit
(``p6_narrative/docx_template.py``): its self-contained furniture helpers are copied
in here (adapted for Reporting Studio) so this module carries no cross-package
dependency.

Entry point::

    build_docx(path, report_name, meta, rendered, letterhead=None) -> path

``rendered`` is ``registry.render(ctx, item_ids)`` output — a list of
``{id, title, feature, feature_title, ctype, payload}`` in pick order; ``payload.kind``
is the vocabulary in :mod:`p6_special.payloads`. Every section is rendered inside a
``try/except`` so a malformed/empty item is skipped, never fatal; ``rendered=[]`` still
writes a valid document (cover + empty contents).
"""
import base64
import io
from datetime import datetime
from html.parser import HTMLParser

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Inches, Pt, RGBColor

CENTER = WD_ALIGN_PARAGRAPH.CENTER
RIGHT = WD_ALIGN_PARAGRAPH.RIGHT

# ── palette ───────────────────────────────────────────────────────────────────
NAVY = RGBColor(0x1F, 0x4E, 0x79)     # heading + table-header + page-frame navy
INK = RGBColor(0x1A, 0x1D, 0x21)      # body ink
INK_SOFT = RGBColor(0x45, 0x4C, 0x57)  # softened body ink (labels / captions)
GREY = RGBColor(0x8A, 0x90, 0x99)     # muted / footer grey
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

NAVY_HEX = '1F4E79'      # navy fill (page frame, table headers, first bar series)
_ZEBRA_FILL = 'F2F6F8'   # alternating body-row background
_TRACK_HEX = 'E9EDF2'    # bar-track (the un-filled remainder) light grey

# Small palette for successive bar/segment series — navy, green, orange, then extras.
_PALETTE = ['1F4E79', '2E7D32', 'D97706', '6B7688', '8E44AD', '0F766E']
_SEV_COLOR = {'high': 'C0392B', 'medium': 'D97706', 'low': '7F8C8D', 'info': NAVY_HEX}
_STATUS_COLOR = {'good': '2E7D32', 'warn': 'D97706', 'bad': 'C0392B',
                 'accent': NAVY_HEX, 'neutral': '7F8C8D'}

_BODY_FONT = 'Calibri'
_HEAD_FONT = 'Calibri Light'
_TILE_FONT = 'Calibri'
_BODY_PT = 11
_TABLE_PT = 9.5


# ── low-level helpers (copied from the narrative toolkit) ──────────────────────
def _img_bytes(data_url):
    """Decode a 'data:image/...;base64,XXXX' URL (or bare base64) to a BytesIO, or None."""
    if not data_url:
        return None
    try:
        b64 = data_url.split(',', 1)[1] if ',' in str(data_url) else data_url
        return io.BytesIO(base64.b64decode(b64))
    except Exception:
        return None


def _set_run_font(run, name, size=None, bold=None, italic=None, color=None):
    """Set a run's font, forcing the OOXML rFonts ascii/hAnsi so themed fonts like
    'Calibri Light' actually apply in Word (the plain ``.name`` setter is not always
    honoured for the +body/+headings theme fonts)."""
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.append(rFonts)
    rFonts.set(qn('w:ascii'), name)
    rFonts.set(qn('w:hAnsi'), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = color
    return run


def _set_cell_bg(cell, hex_fill):
    """Shade a table cell (header / zebra / bar fill). Any prior shading is removed
    first so a re-colour (e.g. a findings severity cell over its zebra) is clean."""
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn('w:shd')):
        tcPr.remove(old)
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_fill)
    tcPr.append(shd)


def _page_field_run(paragraph):
    """Append a live Word PAGE field (begin + instrText ' PAGE ' + separate + '1' + end)."""
    run = paragraph.add_run()
    r = run._r
    begin = OxmlElement('w:fldChar'); begin.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve'); instr.text = ' PAGE '
    sep = OxmlElement('w:fldChar'); sep.set(qn('w:fldCharType'), 'separate')
    placeholder = OxmlElement('w:t'); placeholder.text = '1'
    end = OxmlElement('w:fldChar'); end.set(qn('w:fldCharType'), 'end')
    for el in (begin, instr, sep, placeholder, end):
        r.append(el)
    return run


def _no_table_borders(table):
    """Strip every border from a layout table (used for the bar / segment tables)."""
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn('w:tblBorders')):
        tblPr.remove(old)
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        e = OxmlElement('w:' + edge)
        e.set(qn('w:val'), 'nil')
        borders.append(e)
    tblPr.append(borders)


def _table_fixed(table):
    """Fixed layout so per-cell widths are honoured (bars must keep their proportions)."""
    table.autofit = False
    tblPr = table._tbl.tblPr
    layout = OxmlElement('w:tblLayout')
    layout.set(qn('w:type'), 'fixed')
    tblPr.append(layout)


def _zero_cell_margins(cell):
    """Remove a cell's inner margins so shading (a bar fill) reaches its edges."""
    tcPr = cell._tc.get_or_add_tcPr()
    m = OxmlElement('w:tcMar')
    for edge in ('top', 'left', 'bottom', 'right'):
        e = OxmlElement('w:' + edge)
        e.set(qn('w:w'), '0'); e.set(qn('w:type'), 'dxa')
        m.append(e)
    tcPr.append(m)


def _col_widths(table, widths):
    """Force a table's column grid + per-cell widths to ``widths`` (a list of Length).
    Both the ``w:gridCol`` grid and each row's ``w:tcW`` are set so Word keeps them."""
    grid = table._tbl.tblGrid
    cols = grid.findall(qn('w:gridCol'))
    for gc, w in zip(cols, widths):
        gc.set(qn('w:w'), str(max(0, int(int(w) / 635))))   # EMU -> twips (dxa)
        gc.set(qn('w:type'), 'dxa')
    for row in table.rows:
        for c, w in zip(row.cells, widths):
            c.width = w


# ── page geometry / frame / header / footer ───────────────────────────────────
def apply_page_geometry(section):
    """A4 portrait with a comfortable margin and 1cm header/footer distances."""
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)
    section.header_distance = Cm(1.0)
    section.footer_distance = Cm(1.0)
    return section


def add_page_border(section):
    """Draw a true DOUBLE NAVY frame on EVERY page of the section (``w:pgBorders``).

    Idempotent: any prior ``w:pgBorders`` is removed first and the new element is
    inserted immediately after ``w:pgMar`` (its correct schema position)."""
    sectPr = section._sectPr
    for existing in sectPr.findall(qn('w:pgBorders')):
        sectPr.remove(existing)
    borders = OxmlElement('w:pgBorders')
    borders.set(qn('w:offsetFrom'), 'page')
    borders.set(qn('w:display'), 'allPages')
    for edge in ('top', 'left', 'bottom', 'right'):
        el = OxmlElement('w:' + edge)
        el.set(qn('w:val'), 'double')
        el.set(qn('w:sz'), '4')
        el.set(qn('w:space'), '24')
        el.set(qn('w:color'), NAVY_HEX)
        borders.append(el)
    pgMar = sectPr.find(qn('w:pgMar'))
    if pgMar is not None:
        pgMar.addnext(borders)
    else:
        sectPr.append(borders)
    return borders


def add_header(document, meta):
    """Repeating page header — THREE logo cells (owner / consultant / contractor) over
    a thin navy rule. A missing logo leaves its cell empty rather than dropping the
    column, so the three equal cells always hold their positions."""
    meta = meta or {}
    section = document.sections[0]
    header = section.header
    header.is_linked_to_previous = False

    logos = meta.get('logos') or {}
    table = header.add_table(rows=1, cols=3, width=Inches(6.9))
    table.alignment = WD_ALIGN_PARAGRAPH.CENTER
    table.autofit = True
    for i, key in enumerate(('owner', 'consultant', 'contractor')):
        cell = table.rows[0].cells[i]
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        img = _img_bytes(logos.get(key))
        if img:
            try:
                para.add_run().add_picture(img, width=Inches(1.4))
            except Exception:
                pass   # missing / bad logo -> empty cell, column kept

    rule = header.add_paragraph()
    pPr = rule._p.get_or_add_pPr()
    pbdr = OxmlElement('w:pBdr')
    bot = OxmlElement('w:bottom')
    bot.set(qn('w:val'), 'single'); bot.set(qn('w:sz'), '6')
    bot.set(qn('w:space'), '1'); bot.set(qn('w:color'), NAVY_HEX)
    pbdr.append(bot)
    pPr.append(pbdr)
    return header


def add_footer(section):
    """Centred footer holding a live PAGE field only (no NUMPAGES), Calibri 9pt grey."""
    footer = section.footer
    footer.is_linked_to_previous = False
    para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    para.text = ''
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _page_field_run(para)
    for run in para.runs:
        _set_run_font(run, _TILE_FONT, size=9, color=GREY)
    return footer


# ── base styles / headings / tables ───────────────────────────────────────────
def apply_base_styles(document):
    """Normal = Calibri 11pt ink (dark, readable — matching the PDF body); Heading
    1/2/3 = Calibri Light bold navy at 16 / 13 / 11.5pt (rFonts ascii/hAnsi forced to
    'Calibri Light' so the theme font actually applies in Word)."""
    normal = document.styles['Normal']
    normal.font.name = _BODY_FONT
    normal.font.size = Pt(_BODY_PT)
    normal.font.color.rgb = INK

    for level, size in (('Heading 1', 16), ('Heading 2', 13), ('Heading 3', 11.5)):
        try:
            st = document.styles[level]
        except KeyError:
            continue
        st.font.name = _HEAD_FONT
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = NAVY
        rPr = st.element.get_or_add_rPr()
        rFonts = rPr.find(qn('w:rFonts'))
        if rFonts is None:
            rFonts = OxmlElement('w:rFonts')
            rPr.append(rFonts)
        rFonts.set(qn('w:ascii'), _HEAD_FONT)
        rFonts.set(qn('w:hAnsi'), _HEAD_FONT)
    return document


def format_number(parts):
    """Format a heading-number tuple: numeric levels joined by '.', trailing alpha kept,
    always suffixed with ')'.  ``(4,)`` -> '4)'; ``(3, 1)`` -> '3.1)'."""
    pieces = [str(p) for p in (parts or []) if p is not None and str(p) != '']
    return '.'.join(pieces) + ')'


def heading(document, number_label, title, level=1):
    """A Heading-styled paragraph carrying '<number_label> <title>' in Calibri Light
    bold navy. ``level`` maps to Heading 1/2/3 (sizes 16/13/11.5pt)."""
    size = {1: 16, 2: 13, 3: 11.5}.get(level, 16)
    para = document.add_heading('', level=level)
    text = ('%s %s' % (number_label or '', title or '')).strip()
    _set_run_font(para.add_run(text), _HEAD_FONT, size=size, bold=True, color=NAVY)
    return para


def subheading(document, number_label, text):
    """A Heading-2 paragraph carrying '<number_label> <text>' in Calibri Light navy."""
    return heading(document, number_label, text, level=2)


def styled_table(document, headers, rows, widths=None, bold_last_row=False):
    """A styled, editable Word table: navy header row (white bold), thin Table-Grid
    borders and zebra shading on even body rows. Returns the table."""
    headers = list(headers) or ['']
    table = document.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'

    hdr_cells = table.rows[0].cells
    for i, head in enumerate(headers):
        run = hdr_cells[i].paragraphs[0].add_run('' if head is None else str(head))
        _set_run_font(run, _BODY_FONT, size=_TABLE_PT, bold=True, color=WHITE)
        _set_cell_bg(hdr_cells[i], NAVY_HEX)

    last = len(rows) - 1
    for ri, row in enumerate(rows):
        cells = table.add_row().cells
        for ci, val in enumerate(row):
            if ci >= len(cells):
                break
            run = cells[ci].paragraphs[0].add_run('' if val is None else str(val))
            _set_run_font(run, _BODY_FONT, size=_TABLE_PT,
                          bold=bool(bold_last_row and ri == last))
        if ri % 2 == 0 and not (bold_last_row and ri == last):
            for c in cells:
                _set_cell_bg(c, _ZEBRA_FILL)

    if widths:
        table.autofit = False
        for row in table.rows:
            for i, width in enumerate(widths):
                if i < len(row.cells):
                    row.cells[i].width = width
    return table


def full_date(v):
    """Render a date as 'DD Month YYYY'; unparseable/blank input passes through."""
    if v in (None, ''):
        return ''
    if isinstance(v, datetime):
        return '%d %s %d' % (v.day, v.strftime('%B'), v.year)
    try:
        dt = datetime.strptime(str(v)[:10], '%Y-%m-%d')
        return '%d %s %d' % (dt.day, dt.strftime('%B'), dt.year)
    except (ValueError, TypeError):
        return str(v)


# ── small formatting utilities ────────────────────────────────────────────────
def _fnum(v):
    try:
        return float(v if v not in (None, '') else 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt_num(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        f = float(v)
        return str(int(f)) if f == int(f) else ('%g' % f)
    return str(v)


def _cellval(c):
    """A table cell may be a plain value or a ``[text, tone]`` / ``(text, tone)`` pair
    to colour it — take the text for the docx table."""
    if isinstance(c, (list, tuple)):
        return c[0] if c else ''
    return c


def _fmt_date(v):
    """Drop any time tail a stored data_date carries ('2026-07-19 00:00:00' -> '2026-07-19')."""
    if not v:
        return ''
    s = str(v)
    if ' ' in s:
        return s.split(' ')[0]
    if 'T' in s:
        return s.split('T')[0]
    return s


def _series_color(i, tone=None):
    return _PALETTE[i % len(_PALETTE)]


def _logo_srcs(letterhead):
    """Best-effort three logo sources from the letterhead, tolerant of shapes: ``logos``
    as a dict (owner/consultant/contractor), a list (of src strings or ``{src}`` dicts),
    or the board's ``logos_left``/``logos_right`` arrays."""
    lh = letterhead or {}
    srcs = [None, None, None]
    logos = lh.get('logos')
    if isinstance(logos, dict):
        for i, k in enumerate(('owner', 'consultant', 'contractor')):
            srcs[i] = logos.get(k)
    elif isinstance(logos, (list, tuple)):
        for i, it in enumerate(list(logos)[:3]):
            srcs[i] = it.get('src') if isinstance(it, dict) else it
    if not any(srcs):
        combined = list(lh.get('logos_left') or []) + list(lh.get('logos_right') or [])
        for i, it in enumerate(combined[:3]):
            srcs[i] = it.get('src') if isinstance(it, dict) else it
    return srcs


def _caption(document, text):
    """A small italic grey caption paragraph."""
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    _set_run_font(p.add_run(str(text or '')), _BODY_FONT, size=9, italic=True, color=GREY)
    return p


def _small_head(document, text):
    """A small bold navy label above a group of bars (a bars row label)."""
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(1)
    _set_run_font(p.add_run(str(text or '')), _BODY_FONT, size=10.5, bold=True, color=NAVY)
    return p


def _tight_spacer(document):
    """A near-zero-height paragraph inserted after each body table so two consecutive
    tables never merge into one (a Word gotcha) and bars stay tightly stacked."""
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run('')
    r.font.size = Pt(2)
    return p


def _styled(document, headers, rows, **kw):
    """``styled_table`` + a tight spacer (keeps adjacent tables from merging)."""
    t = styled_table(document, headers, rows, **kw)
    _tight_spacer(document)
    return t


def _fill_cell(cell, bg_hex, text_color=WHITE, bold=True):
    """Shade a built cell and recolour its existing run(s) (findings / status cells)."""
    _set_cell_bg(cell, bg_hex)
    for p in cell.paragraphs:
        for r in p.runs:
            r.font.color.rgb = text_color
            r.bold = bold


# ── bars / segbar drawn as REAL bars ──────────────────────────────────────────
def _bar(document, series_label, frac, fill_hex, value_disp,
         label_w=Cm(3.4), track_w=Cm(11.5), value_w=Cm(3.0)):
    """One horizontal bar as a borderless single-row table:
    ``label | [ shaded-fill | grey-remainder ] | value`` — the fill cell's width is
    ``frac`` of the track, the remainder is the light-grey track. Single-row tables so
    each bar keeps its own proportional widths (a shared multi-row grid could not)."""
    frac = max(0.0, min(1.0, _fnum(frac)))
    t = document.add_table(rows=1, cols=4)
    _table_fixed(t)
    _no_table_borders(t)
    lab, fill, rest, val = t.rows[0].cells

    fw = Emu(int(int(track_w) * frac))
    rw = Emu(max(0, int(track_w) - int(fw)))
    _col_widths(t, [label_w, fw, rw, value_w])

    # series label
    lp = lab.paragraphs[0]
    _set_run_font(lp.add_run(str(series_label or '')), _BODY_FONT, size=9, color=INK_SOFT)

    # bar fill + remainder (shaded, zero-margin, a tiny spacer run gives the bar height)
    for cell, hexc, draw in ((fill, fill_hex, frac > 0), (rest, _TRACK_HEX, True)):
        _zero_cell_margins(cell)
        if draw:
            _set_cell_bg(cell, hexc)
        sp = cell.paragraphs[0]
        sp.paragraph_format.space_before = Pt(0)
        sp.paragraph_format.space_after = Pt(0)
        _set_run_font(sp.add_run(' '), _BODY_FONT, size=7)

    # value
    vp = val.paragraphs[0]
    vp.alignment = RIGHT
    _set_run_font(vp.add_run(str(value_disp or '')), _BODY_FONT, size=9, color=INK)

    for c in (lab, fill, rest, val):
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    _tight_spacer(document)
    return t


def _render_bars(document, pl):
    rows = pl.get('rows') or []
    series = pl.get('series') or []
    variance = pl.get('style') == 'variance'
    if not rows or (not series and not variance):
        return
    axis_max = pl.get('axis_max')
    try:
        axis_max = float(axis_max) if axis_max else None
    except (TypeError, ValueError):
        axis_max = None
    if axis_max:
        block_max = axis_max
    else:
        vals = []
        for row in rows:
            for v in (row.get('values') or []):
                vals.append(abs(_fnum(v)))
            if row.get('target') is not None:
                vals.append(abs(_fnum(row.get('target'))))
        block_max = max(vals) if vals else 0

    def _frac(x):
        return (abs(_fnum(x)) / block_max) if block_max else 0.0

    if variance:
        for row in rows:
            vals = row.get('values') or []
            actual = _fnum(vals[0]) if vals else 0.0
            target = row.get('target')
            disp = row.get('display') or [None]
            shown = disp[0] if disp and disp[0] is not None else _fmt_num(actual)
            if target is not None:
                tshown = row.get('target_display') or _fmt_num(target)
                shown = '%s · plan %s' % (shown, tshown)
            _bar(document, row.get('label'), _frac(actual), _series_color(0, row.get('tone')), shown)
        note = pl.get('note')
        if note:
            _caption(document, note)
        return

    for row in rows:
        label = row.get('label')
        vals = row.get('values') or []
        disp = row.get('display') or [None] * len(vals)
        if label:
            _small_head(document, label)
        for i, s in enumerate(series):
            v = vals[i] if i < len(vals) else 0
            shown = disp[i] if (i < len(disp) and disp[i] is not None) else _fmt_num(_fnum(v))
            _bar(document, s.get('label'), _frac(v), _series_color(i, s.get('tone')), shown)
    cap = []
    if series:
        cap.append('Series: ' + ', '.join(str(s.get('label') or '') for s in series))
    if pl.get('note'):
        cap.append(str(pl.get('note')))
    if cap:
        _caption(document, ' — '.join(cap))


def _render_segbar(document, pl):
    segs = [s for s in (pl.get('segments') or []) if _fnum(s.get('value')) > 0]
    if not segs:
        return
    total = sum(_fnum(s.get('value')) for s in segs) or 1.0
    track_w = Cm(17.4)
    t = document.add_table(rows=1, cols=len(segs))
    _table_fixed(t)
    _no_table_borders(t)
    widths = [Emu(int(int(track_w) * _fnum(s.get('value')) / total)) for s in segs]
    _col_widths(t, widths)
    for i, s in enumerate(segs):
        c = t.rows[0].cells[i]
        _zero_cell_margins(c)
        _set_cell_bg(c, _series_color(i, s.get('tone')))
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = c.paragraphs[0]
        p.alignment = CENTER
        _set_run_font(p.add_run(_fmt_num(s.get('value'))), _BODY_FONT, size=8, bold=True, color=WHITE)
    _tight_spacer(document)
    cap = ' · '.join('%s %s' % (s.get('label'), _fmt_num(s.get('value'))) for s in segs)
    _caption(document, cap)
    if pl.get('note'):
        _caption(document, pl.get('note'))


# ── the other payload kinds ───────────────────────────────────────────────────
def _render_table(document, pl):
    cols = pl.get('columns') or []
    rows = pl.get('rows') or []
    if not rows:
        return
    body = [[_cellval(c) for c in (r or [])] for r in rows]
    _styled(document, cols or ['Value'], body)


def _render_kpi_group(document, pl):
    items = pl.get('items') or []
    if not items:
        return
    rows = [[it.get('label') or '', it.get('value') or '', it.get('sub') or ''] for it in items]
    _styled(document, ['Metric', 'Value', 'Detail'], rows)


def _render_keyvals(document, pl):
    pairs = pl.get('pairs') or []
    if not pairs:
        return
    _styled(document, ['Item', 'Value'], [[k, v] for k, v in pairs])


def _render_findings(document, pl):
    items = pl.get('items') or []
    if not items:
        _caption(document, pl.get('empty') or 'No findings.')
        return
    rows = [[str(f.get('severity') or 'info').title(), f.get('title') or '',
             f.get('source') or f.get('detail') or ''] for f in items]
    t = _styled(document, ['Severity', 'Finding', 'Source'], rows)
    for ri, f in enumerate(items):
        col = _SEV_COLOR.get(str(f.get('severity') or 'info').lower(), NAVY_HEX)
        try:
            _fill_cell(t.rows[ri + 1].cells[0], col)
        except IndexError:
            pass


def _render_status_header(document, pl):
    domains = pl.get('domains') or []
    v = pl.get('verdict')
    if v and v.get('label'):
        p = document.add_paragraph()
        col = _STATUS_COLOR.get(str(v.get('tone') or 'neutral').lower(), '7F8C8D')
        _set_run_font(p.add_run(str(v.get('label'))), _HEAD_FONT, size=13, bold=True,
                      color=RGBColor.from_string(col))
        if v.get('note'):
            _caption(document, v.get('note'))
    if not domains:
        return
    rows = [[d.get('domain') or '', str(d.get('tone') or 'neutral').title(), d.get('headline') or '']
            for d in domains]
    t = _styled(document, ['Area', 'Status', 'Headline'], rows)
    for ri, d in enumerate(domains):
        col = _STATUS_COLOR.get(str(d.get('tone') or 'neutral').lower(), '7F8C8D')
        try:
            _fill_cell(t.rows[ri + 1].cells[1], col)
        except IndexError:
            pass


def _render_line(document, pl):
    series = pl.get('series') or []
    x = pl.get('x') or []
    n = max((len(s.get('points') or []) for s in series), default=0)
    if not series or n < 1:
        return
    headers = ['Point'] + [(s.get('label') or ('Series %d' % (i + 1))) for i, s in enumerate(series)]
    rows = []
    for i in range(n):
        row = [str(x[i]) if i < len(x) else str(i + 1)]
        for s in series:
            pts = s.get('points') or []
            row.append('' if (i >= len(pts) or pts[i] is None) else _fmt_num(pts[i]))
        rows.append(row)
    _styled(document, headers, rows)
    cap = ['trend']
    ref = pl.get('ref')
    if ref and ref.get('value') is not None:
        cap.append('%s = %s' % (ref.get('label') or 'target', _fmt_num(ref.get('value'))))
    if pl.get('note'):
        cap.append(str(pl.get('note')))
    _caption(document, ' · '.join(cap))


def _render_text(document, pl):
    for para_text in (pl.get('paragraphs') or []):
        para = document.add_paragraph()
        _set_run_font(para.add_run(str(para_text)), _BODY_FONT, size=_BODY_PT, color=INK_SOFT)


def _render_note(document, pl):
    para = document.add_paragraph()
    _set_run_font(para.add_run(str(pl.get('message') or '')), _BODY_FONT,
                  size=_BODY_PT, italic=True, color=INK_SOFT)


def _render_group(document, pl):
    for b in (pl.get('blocks') or []):
        _render_block(document, b)


# ── html reconstruction (best-effort, never crashes) ──────────────────────────
class _HtmlExtract(HTMLParser):
    """Pull tables / headings / paragraphs out of a reused feature-report HTML section.

    Only the OUTERMOST table's rows/cells are captured (nested-table text folds into the
    enclosing cell rather than corrupting the row structure); an ``<svg>`` becomes a
    single chart-placeholder op. The result is a list of ops the caller turns into docx:
    ``('table', headers, rows)`` · ``('heading', text)`` · ``('para', text)`` · ``('chart',)``.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ops = []
        self._depth = 0        # table nesting depth
        self._rows = None      # [(row_has_th, [cell_text, ...]), ...] for the outer table
        self._row = None
        self._cell = None      # list of text fragments for the open cell
        self._row_has_th = False
        self._heading_tag = None
        self._para = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == 'table':
            self._depth += 1
            if self._depth == 1:
                self._rows = []
        elif t == 'tr' and self._depth == 1:
            self._row = []
            self._row_has_th = False
        elif t in ('td', 'th') and self._depth == 1:
            self._cell = []
            if t == 'th':
                self._row_has_th = True
        elif t in ('h1', 'h2', 'h3', 'h4') and self._depth == 0:
            self._heading_tag = t
            self._para = False
            self._buf = []
        elif t in ('p', 'li') and self._depth == 0:
            self._para = True
            self._heading_tag = None
            self._buf = []
        elif t == 'br':
            if self._cell is not None:
                self._cell.append(' ')
            elif self._para or self._heading_tag:
                self._buf.append(' ')
        elif t == 'svg':
            self.ops.append(('chart',))

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        elif self._heading_tag or self._para:
            self._buf.append(data)

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in ('td', 'th') and self._depth == 1 and self._cell is not None:
            self._row.append(' '.join(''.join(self._cell).split()))
            self._cell = None
        elif t == 'tr' and self._depth == 1 and self._row is not None:
            self._rows.append((self._row_has_th, self._row))
            self._row = None
        elif t == 'table':
            if self._depth == 1 and self._rows is not None:
                self._emit_table(self._rows)
                self._rows = None
            self._depth = max(0, self._depth - 1)
        elif t in ('h1', 'h2', 'h3', 'h4') and self._heading_tag == t:
            text = ' '.join(''.join(self._buf).split())
            if text:
                self.ops.append(('heading', text))
            self._heading_tag = None
            self._buf = []
        elif t in ('p', 'li') and self._para:
            text = ' '.join(''.join(self._buf).split())
            if text:
                self.ops.append(('para', text))
            self._para = False
            self._buf = []

    def _emit_table(self, rows):
        rows = [r for r in rows if r[1]]
        if not rows:
            return
        if rows[0][0]:
            headers = rows[0][1]
            body = [r[1] for r in rows[1:]]
        else:
            headers = None
            body = [r[1] for r in rows]
        ncol = max([len(headers or [])] + [len(b) for b in body] + [1])
        if not headers:
            headers = [''] * ncol
        self.ops.append(('table', headers, body))


def _render_html(document, pl):
    markup = pl.get('html') or ''
    ops = []
    try:
        ex = _HtmlExtract()
        ex.feed(str(markup))
        ex.close()
        ops = ex.ops
    except Exception:
        ops = []
    if not ops:
        _caption(document, 'This detailed section is available in the on-screen / PDF report.')
        return
    for op in ops:
        try:
            if op[0] == 'table':
                _styled(document, op[1] or ['Value'], op[2] or [])
            elif op[0] == 'heading':
                subheading(document, '', op[1])
            elif op[0] == 'para':
                para = document.add_paragraph()
                _set_run_font(para.add_run(op[1]), _BODY_FONT, size=_BODY_PT, color=INK_SOFT)
            elif op[0] == 'chart':
                _caption(document, '[chart shown in the PDF]')
        except Exception:
            continue


_BLOCK = {
    'table': _render_table, 'kpi_group': _render_kpi_group, 'bars': _render_bars,
    'segbar': _render_segbar, 'findings': _render_findings, 'keyvals': _render_keyvals,
    'line': _render_line, 'status_header': _render_status_header, 'text': _render_text,
    'note': _render_note, 'group': _render_group, 'html': _render_html,
}


def _render_block(document, block):
    """Dispatch one payload block to its docx renderer. no_data / unknown / empty are
    skipped; any renderer error is swallowed so one bad block never fails the report."""
    if not isinstance(block, dict):
        return
    kind = block.get('kind')
    if kind in (None, 'no_data', 'empty'):
        return
    fn = _BLOCK.get(kind)
    if fn is None:
        return
    try:
        fn(document, block)
    except Exception:
        pass


# ── cover / contents ──────────────────────────────────────────────────────────
def _cover_logo_row(document, letterhead):
    """Three centred logo slots at the top of the cover (a supplied image, else an
    empty slot). Borderless single-row table so the three columns keep their places."""
    srcs = _logo_srcs(letterhead)
    t = document.add_table(rows=1, cols=3)
    _table_fixed(t)
    _no_table_borders(t)
    third = Cm(5.8)
    _col_widths(t, [third, third, third])
    for i, src in enumerate(srcs):
        cell = t.rows[0].cells[i]
        p = cell.paragraphs[0]
        p.alignment = CENTER
        img = _img_bytes(src)
        if img:
            try:
                p.add_run().add_picture(img, width=Inches(1.6))
            except Exception:
                pass
    _tight_spacer(document)


def _center_rule(document):
    """A centred navy double rule under the cover title (matches the PDF's double rule)."""
    p = document.add_paragraph()
    p.alignment = CENTER
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement('w:pBdr')
    bot = OxmlElement('w:bottom')
    bot.set(qn('w:val'), 'double'); bot.set(qn('w:sz'), '6')
    bot.set(qn('w:space'), '4'); bot.set(qn('w:color'), NAVY_HEX)
    pbdr.append(bot)
    pPr.append(pbdr)
    return p


def add_cover(document, report_name, meta, letterhead):
    """The title page (page 1): three logos, an optional company + kicker, the report
    name large in navy sitting mid-page (empty-paragraph spacing centres it vertically),
    a navy double rule, then Project / Data date / Prepared-by — only fields supplied.
    Ends with a page break so contents starts on page 2."""
    meta = meta or {}
    lh = letterhead or {}
    _cover_logo_row(document, lh)

    company = lh.get('company')
    if company:
        cp = document.add_paragraph()
        cp.alignment = CENTER
        _set_run_font(cp.add_run(str(company)), _BODY_FONT, size=12, bold=True, color=INK)

    for _ in range(8):                       # push the title toward the vertical middle
        document.add_paragraph()

    kicker = lh.get('kicker')
    if kicker:
        kp = document.add_paragraph()
        kp.alignment = CENTER
        _set_run_font(kp.add_run(str(kicker).upper()), _TILE_FONT, size=11, bold=True, color=NAVY)

    tp = document.add_paragraph()
    tp.alignment = CENTER
    _set_run_font(tp.add_run(str(report_name or 'Special Report')),
                  _HEAD_FONT, size=28, bold=True, color=NAVY)

    _center_rule(document)

    date_s = _fmt_date(meta.get('data_date'))
    for label, value in (('Project', meta.get('project_name')),
                         ('Data date', date_s),
                         ('Prepared by', lh.get('prepared_by'))):
        if value:
            mp = document.add_paragraph()
            mp.alignment = CENTER
            _set_run_font(mp.add_run('%s:  ' % label), _TILE_FONT, size=10, bold=True, color=GREY)
            _set_run_font(mp.add_run(str(value)), _BODY_FONT, size=12, color=INK)

    document.add_page_break()


def _add_contents(document, rendered):
    """The contents page (page 2): a navy 'Contents' heading + a numbered list in pick
    order — ``N   <title>   <feature_title faint>``. Ends with a page break."""
    heading(document, '', 'Contents', level=1)
    if not rendered:
        _caption(document, 'No results selected.')
        document.add_page_break()
        return
    for i, item in enumerate(rendered, 1):
        item = item or {}
        p = document.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        _set_run_font(p.add_run('%d   ' % i), _BODY_FONT, size=11, bold=True, color=NAVY)
        _set_run_font(p.add_run(str(item.get('title') or ('Section %d' % i))),
                      _BODY_FONT, size=11, color=INK)
        src = item.get('feature_title') or item.get('feature')
        if src:
            _set_run_font(p.add_run('   %s' % src), _BODY_FONT, size=9, color=GREY)
    document.add_page_break()


# ── entry point ───────────────────────────────────────────────────────────────
def build_docx(path, report_name, meta, rendered, letterhead=None):
    """Write a real ``.docx`` report to ``path`` and return the path.

    ``report_name`` is the cover title; ``meta`` = ``{project_name, data_date}``;
    ``rendered`` = ``registry.render(...)`` output (pick order); ``letterhead`` may carry
    ``kicker`` / ``company`` / ``prepared_by`` and logo srcs (data URLs -> ``_img_bytes``;
    a missing logo -> empty slot). Structure: cover (page 1) · contents (page 2) ·
    numbered navy sections (page 3+). Every section is rendered defensively — a
    malformed/empty item is skipped, never fatal; ``rendered=[]`` still writes a valid
    document (cover + empty-contents notice)."""
    meta = meta or {}
    letterhead = letterhead or {}
    rendered = list(rendered or [])

    document = Document()
    section = document.sections[0]
    apply_page_geometry(section)
    add_page_border(section)
    # Keep the cover clean: running header/footer appear on pages 2+, not the title page.
    section.different_first_page_header_footer = True
    apply_base_styles(document)

    srcs = _logo_srcs(letterhead)
    header_meta = dict(meta)
    header_meta['logos'] = {'owner': srcs[0], 'consultant': srcs[1], 'contractor': srcs[2]}
    add_header(document, header_meta)
    add_footer(section)

    add_cover(document, report_name, meta, letterhead)
    _add_contents(document, rendered)

    for i, item in enumerate(rendered, 1):
        try:
            item = item or {}
            heading(document, str(i), item.get('title') or ('Section %d' % i), level=1)
            _render_block(document, item.get('payload') or {})
        except Exception:
            continue

    document.save(str(path))
    return str(path)
