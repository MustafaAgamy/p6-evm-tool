"""Write a v5 Baseline Narrative Report (dict) to a professional, natively-editable
Word (.docx) document.

Everything lands as native, editable Word content — paragraphs, tables and outlines,
never a flattened image of text — so a planner can change any word, number, row or
cell in Word and finish it on their letterhead. The document is styled to read like a
senior planning deliverable: a cover block, a page border on every page, a bold
numbered heading hierarchy (Word Heading styles) and page numbering in the footer.

It consumes the model produced by :func:`p6_narrative.report.build_report` → ``to_dict()``:

    {meta:{project_name, project_id, mode, logos?}, sections:[section, …]}

with five section kinds — ``overview`` · ``ms_table`` · ``wbs_tree`` · ``seq`` ·
``interfaces`` (see :mod:`p6_narrative.report` for the payload contract).
"""
import base64
import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

# ── palette (matches the on-screen / PDF renderer) ───────────────────────────
NAVY = RGBColor(0x26, 0x5F, 0x7E)
INK = RGBColor(0x1A, 0x1D, 0x21)
GREY = RGBColor(0x8A, 0x90, 0x99)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
_HEADER_FILL = '265F7E'   # table header background
_ZEBRA_FILL = 'F2F6F8'    # alternating body-row background
_BORDER_CLR = '265F7E'    # page + rule colour
_ARROW = ' → '       # " → " for sequence / macro-flow lines


# ── low-level Word helpers ───────────────────────────────────────────────────
def _img_bytes(data_url):
    """Decode a 'data:image/...;base64,XXXX' URL (or bare base64) to a BytesIO."""
    if not data_url:
        return None
    try:
        b64 = data_url.split(',', 1)[1] if ',' in data_url else data_url
        return io.BytesIO(base64.b64decode(b64))
    except Exception:
        return None


def _set_cell_bg(cell, hex_fill):
    """Shade a table cell (used for header + zebra striping)."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_fill)
    tcPr.append(shd)


def _add_field(paragraph, field_code):
    """Append a Word field (e.g. PAGE / NUMPAGES) to a paragraph as a live run."""
    run = paragraph.add_run()
    begin = OxmlElement('w:fldChar'); begin.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve'); instr.text = ' %s ' % field_code
    sep = OxmlElement('w:fldChar'); sep.set(qn('w:fldCharType'), 'separate')
    placeholder = OxmlElement('w:t'); placeholder.text = '1'
    end = OxmlElement('w:fldChar'); end.set(qn('w:fldCharType'), 'end')
    r = run._r
    for el in (begin, instr, sep, placeholder, end):
        r.append(el)
    return run


def _add_page_border(section, color=_BORDER_CLR):
    """Draw a thin border around every page of a Word section (w:pgBorders)."""
    sectPr = section._sectPr
    borders = OxmlElement('w:pgBorders')
    borders.set(qn('w:offsetFrom'), 'page')
    for edge in ('top', 'left', 'bottom', 'right'):
        el = OxmlElement('w:' + edge)
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), '18')     # eighths of a point ≈ 2.25pt
        el.set(qn('w:space'), '24')  # points inset from the page edge
        el.set(qn('w:color'), color)
        borders.append(el)
    # Schema order: pgBorders belongs right after pgMar.
    pgMar = sectPr.find(qn('w:pgMar'))
    if pgMar is not None:
        pgMar.addnext(borders)
    else:
        sectPr.append(borders)


def _add_page_number_footer(section):
    """Centered 'Page X of Y' footer, repeated on every page."""
    footer = section.footer
    para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.add_run('Page ')
    _add_field(para, 'PAGE')
    para.add_run(' of ')
    _add_field(para, 'NUMPAGES')
    for run in para.runs:
        run.font.size = Pt(9)
        run.font.color.rgb = GREY


def _para_bottom_rule(paragraph, hex_color='C9D6DE'):
    """Add a full-width bottom border to a paragraph (a light divider rule)."""
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')
    bottom.set(qn('w:space'), '2')
    bottom.set(qn('w:color'), hex_color)
    pBdr.append(bottom)
    pPr.append(pBdr)


def _add_table(document, headers, rows, widths=None, bold_last_row=False):
    """A styled, editable Word table: navy header + zebra body rows."""
    table = document.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    for i, head in enumerate(headers):
        run = hdr_cells[i].paragraphs[0].add_run(str(head))
        run.bold = True
        run.font.color.rgb = WHITE
        _set_cell_bg(hdr_cells[i], _HEADER_FILL)
    last = len(rows) - 1
    for ri, row in enumerate(rows):
        cells = table.add_row().cells
        for ci, val in enumerate(row):
            if ci >= len(cells):
                break
            run = cells[ci].paragraphs[0].add_run('' if val is None else str(val))
            if bold_last_row and ri == last:
                run.bold = True
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


def _muted(document, text):
    para = document.add_paragraph()
    run = para.add_run(str(text))
    run.italic = True
    run.font.color.rgb = GREY
    return para


def _section_heading(document, number, title):
    heading = document.add_heading('', level=1)
    run = heading.add_run('%s %s' % (number, title))
    run.bold = True
    run.font.color.rgb = NAVY
    return heading


def _subheading(document, text):
    heading = document.add_heading('', level=2)
    run = heading.add_run(str(text) or '—')
    run.bold = True
    run.font.color.rgb = NAVY
    return heading


def _add_logo_header(document, logos):
    """Put the party logos into the page header (repeats on every page)."""
    header = document.sections[0].header
    try:
        table = header.add_table(rows=1, cols=3, width=Inches(6.4))
    except Exception:
        return
    for i, key in enumerate(('owner', 'consultant', 'contractor')):
        cell = table.rows[0].cells[i]
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        img = _img_bytes(logos.get(key))
        if img:
            try:
                para.add_run().add_picture(img, width=Inches(1.4))
            except Exception:
                pass


# ── cover ────────────────────────────────────────────────────────────────────
def _add_cover(document, meta):
    for _ in range(4):
        document.add_paragraph()
    title = document.add_paragraph(); title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    trun = title.add_run(meta.get('project_name') or 'Project')
    trun.bold = True
    trun.font.size = Pt(28)
    trun.font.color.rgb = INK

    sub = document.add_paragraph(); sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    srun = sub.add_run('Baseline Schedule — Narrative Report')
    srun.font.size = Pt(15)
    srun.font.color.rgb = NAVY

    rule = document.add_paragraph(); rule.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _para_bottom_rule(rule)

    bits = []
    if meta.get('project_id'):
        bits.append('Project ID: %s' % meta['project_id'])
    if meta.get('mode'):
        bits.append('Execution model: %s' % str(meta['mode']).replace('_', ' ').title())
    if meta.get('data_date'):
        bits.append('Baseline data date: %s' % meta['data_date'])
    if bits:
        line = document.add_paragraph(); line.alignment = WD_ALIGN_PARAGRAPH.CENTER
        lrun = line.add_run('   ·   '.join(bits))
        lrun.font.size = Pt(10.5)
        lrun.font.color.rgb = GREY

    document.add_page_break()


# ── section renderers (v5 kinds) ─────────────────────────────────────────────
def _render_overview(document, p):
    for para in p.get('paragraphs', []):
        document.add_paragraph(str(para))
    breakdown = p.get('breakdown') or []
    if breakdown:
        label = document.add_paragraph()
        label.paragraph_format.space_before = Pt(6)
        lrun = label.add_run('Activity breakdown by scope')
        lrun.bold = True
        rows = [[b.get('world', ''), _count(b.get('count'))] for b in breakdown]
        total = p.get('total')
        if total is not None:
            rows.append(['Total', _count(total)])
        _add_table(document, ['Scope', 'Activities'], rows,
                   widths=(Inches(4.4), Inches(1.6)),
                   bold_last_row=total is not None)


def _render_ms_table(document, p, note):
    columns = p.get('columns') or ['Milestone', 'Date']
    rows = p.get('rows') or []
    if not rows:
        _muted(document, note or 'No finish milestones are defined in the file.')
        return
    _add_table(document, columns, rows, widths=(Inches(4.4), Inches(1.8)))


def _wbs_node(document, node, depth):
    marker = {1: '▪  ', 2: '–  ', 3: '·  '}.get(depth, '·  ')
    para = document.add_paragraph()
    para.paragraph_format.left_indent = Inches(0.28 * depth)
    para.paragraph_format.space_after = Pt(2)
    run = para.add_run(marker + (node.get('name') or '—'))
    if node.get('more'):
        run.italic = True
        run.font.color.rgb = GREY
    elif depth <= 1:
        run.bold = True
    for child in node.get('children', []):
        _wbs_node(document, child, depth + 1)


def _render_wbs_tree(document, p):
    worlds = p.get('worlds') or []
    if not worlds:
        _muted(document, 'No work breakdown structure is defined in the file.')
        return
    for w in worlds:
        root = w.get('root') or {}
        # World root as a bold Heading 2, then its children as an indented outline.
        _subheading(document, root.get('name') or w.get('name') or '—')
        for child in root.get('children', []):
            _wbs_node(document, child, 1)


def _render_seq(document, p):
    worlds = p.get('worlds') or []
    if not worlds:
        _muted(document, 'No execution fronts were detected in the file.')
        return
    for w in worlds:
        _subheading(document, w.get('world') or '—')
        fronts = w.get('fronts') or []
        if not fronts:
            _muted(document, 'No work-package sequence was detected for this scope.')
            continue
        for f in fronts:
            title_p = document.add_paragraph()
            title_p.paragraph_format.space_before = Pt(6)
            title_p.paragraph_format.space_after = Pt(1)
            title_p.add_run(f.get('title') or 'Front').bold = True

            seq = [str(s) for s in (f.get('sequence') or []) if s]
            if seq:
                sp = document.add_paragraph()
                sp.paragraph_format.left_indent = Inches(0.22)
                sp.add_run(_ARROW.join(seq))

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
                arun.font.size = Pt(9.5)
                arun.font.color.rgb = GREY


def _render_interfaces(document, p):
    macro = [str(m) for m in (p.get('macro') or []) if m]
    if macro:
        mp = document.add_paragraph()
        mrun = mp.add_run(_ARROW.join(macro))
        mrun.bold = True
        mrun.font.color.rgb = NAVY
    for note in p.get('notes') or []:
        document.add_paragraph(str(note), style='List Bullet')
    edges = [e for e in (p.get('edges') or [])
             if isinstance(e, (list, tuple)) and len(e) >= 2]
    if edges:
        label = document.add_paragraph()
        label.paragraph_format.space_before = Pt(6)
        label.add_run('Key cross-scope dependencies').bold = True
        for a, b in ((e[0], e[1]) for e in edges):
            document.add_paragraph('%s%s%s' % (a, _ARROW, b), style='List Bullet')


def _count(v):
    try:
        return '{:,}'.format(int(v))
    except (TypeError, ValueError):
        return '' if v is None else str(v)


_RENDER = {
    'overview': lambda doc, sec: _render_overview(doc, sec.get('payload') or {}),
    'ms_table': lambda doc, sec: _render_ms_table(doc, sec.get('payload') or {}, sec.get('note')),
    'wbs_tree': lambda doc, sec: _render_wbs_tree(doc, sec.get('payload') or {}),
    'seq': lambda doc, sec: _render_seq(doc, sec.get('payload') or {}),
    'interfaces': lambda doc, sec: _render_interfaces(doc, sec.get('payload') or {}),
}


def _render(document, section):
    handler = _RENDER.get(section.get('kind'))
    if handler is not None:
        handler(document, section)
        return
    # Graceful fallback for any unknown/future kind — never crash the export.
    payload = section.get('payload') or {}
    for para in payload.get('paragraphs', []) or []:
        document.add_paragraph(str(para))
    if section.get('note'):
        _muted(document, section['note'])


# ── public entry point ───────────────────────────────────────────────────────
def write_docx(doc, output_path, chrome=None):
    """Render the v5 narrative model (``doc``) to an editable .docx at ``output_path``.

    ``chrome`` is accepted for signature compatibility and ignored — this writer is
    pure ``python-docx`` and produces native, editable Word content only.
    """
    meta = (doc or {}).get('meta', {}) or {}
    document = Document()

    normal = document.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(11)

    if meta.get('logos'):
        _add_logo_header(document, meta['logos'])
    _add_page_number_footer(document.sections[0])

    _add_cover(document, meta)

    for section in (doc or {}).get('sections', []):
        _section_heading(document, section.get('number', ''), section.get('title', ''))
        _render(document, section)

    for section in document.sections:
        _add_page_border(section)

    document.save(output_path)
    return output_path
