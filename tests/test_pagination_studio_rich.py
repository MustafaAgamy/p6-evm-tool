"""[pagination:STUDIO] Reporting Studio Document PDF + Word with a RICH multi-feature
selection (GBT: overview, EVM, every Schedule Health module, Calendar Audit, Update
Analysis, Baseline Revision Comparison, Baseline Narrative - ~60 results).

Findings fixed in this step (each test fails without its fix):

* STUDIO-RICH-1 - a big selection could not be exported: every Chrome print of the Studio
  had a flat 180 s allowance (90 s for a Word section picture); the GBT document with the
  Baseline Revision 'Key Findings' is 6.4 MB / ~1 800 pages and prints in ~210 s a pass,
  so the PDF export stopped with 'did not finish within 180 s' while Chrome was still
  printing normally. The allowance now grows a minute per MB of markup.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ── STUDIO-RICH-1: the print allowance grows with the document ─────────────────────────
def test_print_timeout_grows_with_the_document():
    from p6_special.pdf_render import print_timeout
    assert print_timeout('', 180) == 180                    # a small document: the base
    assert print_timeout('x' * 1000, 180) == 180
    big = 'x' * 6_400_000                                   # the GBT rich selection
    assert print_timeout(big, 180) >= 180 + 6 * 60          # > the ~210 s a pass it needs
    assert print_timeout(big, 90) >= 90 + 6 * 60            # Word section pictures too
    assert print_timeout(None, 180) == 180


def test_chrome_pdf_passes_the_scaled_allowance(monkeypatch, tmp_path):
    import p6_export.pdf as P
    from p6_special import pdf_render
    seen = {}

    def fake_run_chrome(chrome, args, timeout=180):
        seen['timeout'] = timeout
    monkeypatch.setattr(P, 'run_chrome', fake_run_chrome)
    html = '<html><body>' + ('<div>row</div>' * 400_000) + '</body></html>'   # ~5.6 MB
    pdf_render.chrome_pdf(html, 'chrome.exe', str(tmp_path / 'out.pdf'))
    assert seen['timeout'] > 180 + 5 * 60, seen     # was a flat 180 s


def test_word_section_picture_gets_the_scaled_allowance(monkeypatch):
    import p6_export.pdf as P
    from p6_special import docx_report
    seen = {}

    def fake_run_chrome(chrome, args, timeout=180):
        seen['timeout'] = timeout
        raise RuntimeError('stop here')              # the slicer falls back quietly
    monkeypatch.setattr(P, 'run_chrome', fake_run_chrome)
    frag = '<div class="lanes">' + ('<div class="lane">#1 link</div>' * 120_000) + '</div>'
    assert docx_report._slice_section(frag, '', 'light', 'chrome.exe', 700.0, 600.0) is None
    assert seen['timeout'] > 90 + 3 * 60, seen      # was a flat 90 s


# ── STUDIO-RICH-2: checker - a cell's line is not a heading ───────────────────────────
pymupdf = None
try:
    import pymupdf
except ImportError:                                  # pragma: no cover
    pass

A4 = (595, 842)
_REC = 'Predecessor link Insulation Works -> Insulation Works: change SS to FS if the finish drives the successor'


def _pdf(path, pages):
    doc = pymupdf.open()
    for ops in pages:
        pg = doc.new_page(width=A4[0], height=A4[1])
        for _, x, y, text, size, bold in ops:
            pg.insert_text((x, y), text, fontsize=size, fontname='hebo' if bold else 'helv')
    doc.save(path)
    doc.close()
    return path


def _running(no, n):
    return [('t', 40, 30, 'PROJECT REPORT  Grain Bulk Terminal', 8, False),
            ('t', 280, 825, f'Page {no} of {n}', 8, False)]


def _tall_rows(y, n, first):
    """A Relationship-Types style register: ID + name centred in a tall row whose
    Recommendation cell (x 350) wraps over 4 lines - its FIRST line 'Predecessor link' sits
    above the centred cells (and is the start of a hinted heading text elsewhere)."""
    ops = [('t', 40, y, '#  Activity ID', 9, True), ('t', 150, y, 'Activity Name', 9, True),
           ('t', 350, y, 'Recommendation', 9, True)]
    y += 22
    for i in range(n):
        k = first + i
        ops += [('t', 350, y, 'Predecessor link', 9, False),
                ('t', 40, y + 16, f'{k}  CONS.PL.S{k}.1010', 9, False),
                ('t', 150, y + 16, f'RFT Works For Bored Piles {k}', 9, False),
                ('t', 350, y + 11, 'Insulation Works -> Insulation', 9, False),
                ('t', 350, y + 22, 'Works: change SS to FS if the', 9, False),
                ('t', 350, y + 33, 'finish drives the successor', 9, False)]
        y += 50
    return ops


def _register_pdf(path):
    n = 3
    pages = [
        _running(1, n) + [('t', 40, 70, 'Detailed findings', 14, True)] + _tall_rows(95, 14, 1),
        _running(2, n) + _tall_rows(70, 14, 15),
        _running(3, n) + [('t', 40, 70, 'Next section', 14, True)]
        + [('t', 40, y, f'Narrative line {y} of the next section, plain words.', 10, False)
           for y in range(95, 400, 14)],
    ]
    return _pdf(path, pages)


def test_checker_reads_a_tall_row_register_as_one_table(tmp_path):
    import pytest
    if pymupdf is None:
        pytest.skip('PyMuPDF missing')
    from p6_export import pagination_check as pc
    res = pc.check_pdf(_register_pdf(str(tmp_path / 'reg.pdf')), headings=[_REC])
    assert res['flags'] == [], res['flags']


def test_checker_pre_fix_broke_the_register_into_few_row_tables(tmp_path, monkeypatch):
    import pytest
    if pymupdf is None:
        pytest.skip('PyMuPDF missing')
    from p6_export import pagination_check as pc
    monkeypatch.setattr(pc, '_cell_line', lambda reg, b: False)        # the old reading
    res = pc.check_pdf(_register_pdf(str(tmp_path / 'reg.pdf')), headings=[_REC])
    assert 'table_split_few_rows' in {f['type'] for f in res['flags']}, res['flags']


def test_checker_still_flags_a_real_heading_under_a_table(tmp_path):
    """Control: a heading at the content's LEFT edge right under the table, ending the page,
    is still an orphaned heading (it is not inside a column)."""
    import pytest
    if pymupdf is None:
        pytest.skip('PyMuPDF missing')
    from p6_export import pagination_check as pc
    n = 3
    pages = [
        _running(1, n) + [('t', 40, 70, 'Detailed findings', 14, True)] + _tall_rows(95, 13, 1)
        + [('t', 40, 790, 'Predecessor link summary', 13, True)],
        _running(2, n) + [('t', 40, y, f'Summary line {y}: the links to review, plain words.', 10, False)
                          for y in range(70, 700, 14)],
        _running(3, n) + [('t', 40, 70, 'Next section', 14, True)]
        + [('t', 40, y, f'Narrative line {y} of the next section.', 10, False) for y in range(95, 790, 14)],
    ]
    res = pc.check_pdf(_pdf(str(tmp_path / 'ctl.pdf'), pages), headings=[_REC])
    assert ('orphaned_heading', 1) in {(f['type'], f['page']) for f in res['flags']}, res['flags']


# ── STUDIO-RICH-9: a Word page slice that ends INSIDE a card is not a cut picture ─────────
# The Studio .docx prints a long reused section (a Baseline Revision register / WBS tree in a
# card) as one picture per Word page. Every slice but the last ends inside the card: only the
# card's side borders (or the bottom line of a box closing right at the slice edge) reach the
# picture's bottom edge, and the NEXT picture goes on with the same section. The checker read
# each of those as 'picture_truncated' - 206 of 206 flags on the GBT rich Studio .docx, the
# pages verified as PNG: nothing missing. A slice cut through a text line, or the LAST slice
# of a section ending open, is still flagged.
def _card_slice(h_px, edge='sides', w_px=900, lines=10):
    """A page-sized slice of a card: top border, side borders running past the bottom edge,
    ``lines`` text rows; ``edge``: 'sides' (only the side borders reach the edge), 'box' (a
    band's bottom line on the last pixel row - the band closes there) or 'text' (a text line
    cut by the edge)."""
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=w_px, height=h_px)
    grey = (0.75, 0.78, 0.82)
    page.draw_line((20, 8), (w_px - 20, 8), color=grey, width=1.5)
    for x in (20, w_px - 20):
        page.draw_line((x, 8), (x, h_px + 6), color=grey, width=1.5)
    y = 34
    for i in range(lines):
        page.insert_text((36, y), 'CONS.TR28.32.SS.%04d   Install steel beams   Added   Tower %d' % (1100 + i, i),
                         fontsize=15)
        y += 22
    if edge == 'box':                      # a tree band in the right column closes at the edge
        band = pymupdf.Rect(470, h_px - 40, w_px - 40, h_px - 0.75)
        page.draw_rect(band, color=(0.3, 0.3, 0.3), width=1.5)
        page.insert_text((486, h_px - 16), 'Tower 33 - Machine Tower', fontsize=13)
    elif edge == 'text':
        page.insert_text((36, h_px + 7), 'CONS.TR28.32.SS.1170   Phase D > Delivery Bins > Chain', fontsize=15)
    return page.get_pixmap(alpha=False).tobytes('png')


def _docx_sections(sections, path):
    """A .docx with one Heading 1 per section and its pictures (png list) under it."""
    import io
    from docx import Document
    from docx.shared import Inches
    d = Document()
    for i, pics in enumerate(sections, 1):
        d.add_heading('%d Section' % i, level=1)
        for png in pics:
            d.add_picture(io.BytesIO(png), width=Inches(6.3))
    d.save(path)
    return path


def _truncated(path):
    from p6_export import pagination_check as pc
    return sorted(f['detail'].split(':')[0] for f in pc.docx_picture_flags(path)
                  if f['type'] == 'picture_truncated')


def test_word_slice_ending_inside_a_card_that_the_next_slice_continues_is_not_cut(tmp_path):
    path = _docx_sections([
        [_card_slice(300, 'sides'), _card_slice(330, 'box', lines=6), _card_slice_closed()],  # continues
        [_card_slice(300, 'sides')],                                   # the last slice ends open
        [_card_slice(300, 'text', lines=8), _card_slice_closed()],     # a text line cut by the edge
    ], str(tmp_path / 'slices.docx'))
    assert _truncated(path) == ["picture 4 under '2 Section'", "picture 5 under '3 Section'"]


def _card_slice_closed(h_px=300, w_px=900, lines=6):
    """The last slice of a card: the box closes with white below it (a clean end)."""
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=w_px, height=h_px)
    grey = (0.75, 0.78, 0.82)
    bottom = 34 + lines * 22
    page.draw_rect(pymupdf.Rect(20, -4, w_px - 20, bottom), color=grey, width=1.5)
    y = 20
    for i in range(lines):
        page.insert_text((36, y), 'CONS.TR33.SS.%04d   Machine tower   Moved' % (1200 + i), fontsize=15)
        y += 22
    return page.get_pixmap(alpha=False).tobytes('png')


def test_word_slice_rule_pre_fix_flagged_every_continued_slice(tmp_path, monkeypatch):
    """Without the rule (STUDIO-RICH-9 reverted) the continued slices are 'cut' as well."""
    from p6_export import pagination_check as pc
    path = _docx_sections([[_card_slice(300, 'sides'), _card_slice(330, 'box', lines=6),
                            _card_slice_closed()]], str(tmp_path / 'pre.docx'))
    assert _truncated(path) == []
    monkeypatch.setattr(pc, '_frame_sides_only', lambda *a, **k: False)
    assert _truncated(path) == ["picture 1 under '1 Section'", "picture 2 under '1 Section'"]


# ── a Word layout that times out stops the Word IT started, never another Word ────────────
def test_word_layout_timeout_stops_only_its_own_word(tmp_path, monkeypatch):
    import subprocess
    from p6_export import pagination_check as pc
    calls = []

    def fake_run(cmd, **kw):
        if '--word-layout' in cmd:
            with open(cmd[-1], 'w', encoding='ascii') as fh:    # the child records its Word
                fh.write('4242')
            raise subprocess.TimeoutExpired(cmd, kw.get('timeout'))
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(pc.subprocess, 'run', fake_run)
    monkeypatch.setattr(pc.os, 'name', 'nt')
    import pytest
    with pytest.raises(subprocess.TimeoutExpired):
        pc._word_layout_subprocess(str(tmp_path / 'x.docx'), 1)
    assert calls == [['taskkill', '/PID', '4242', '/F']]
    # no pid recorded (Word never started) -> nothing is stopped
    calls.clear()
    assert pc._stop_pid_in(str(tmp_path / 'missing.pid')) is False and calls == []


# ── STUDIO-RICH-10: a small card split by the page break is flagged (block_split) ─────────
# GBT rich Studio PDF: the Update Analysis driving path's 'Completion Milestone' card printed
# its flag line at the foot of p109 and its title + dates at the top of p110; the Float Health
# 'how the score is calculated' legend left its colour key alone on p17. Chrome paints each
# fragment as its own box, and the checker's graphic_cut rule leaves TEXT boxes alone (text at
# the break is how a long panel or a table row reads) - zero flags were reported.
def _split_box_pdf(path, kind='card'):
    """4 pages of text; at the foot of p2 a box opens (ending on the page-area bottom) and it
    goes on at the top of p3. ``kind``: 'card' (a 100 pt card: flag line on p2, title + dates
    on p3), 'rows' (two whole table rows meeting at the break - text close to both edges) or
    'panel' (a long panel: 330 pt on p2 + 120 pt on p3)."""
    doc = pymupdf.open()
    for no in range(1, 5):
        pg = doc.new_page(width=A4[0], height=A4[1])
        pg.insert_text((40, 30), 'PROJECT REPORT  Grain Bulk Terminal', fontsize=8)
        pg.insert_text((280, 825), f'Page {no} of 4', fontsize=8)
    # the page area (top 100, bottom 780): p1 / p4 hold a framed panel of text lines filling it
    top, bottom = 100.0, 780.0
    for no in (0, 3):
        doc[no].draw_rect(pymupdf.Rect(40, top, 555, bottom), color=(0.8, 0.8, 0.8), width=1)
        for y in range(120, 772, 14):
            doc[no].insert_text((50, y), f'Narrative line {y}: the schedule is reviewed in plain words.', fontsize=10)
    a_top = {'card': bottom - 30, 'rows': bottom - 24, 'panel': bottom - 330}[kind]
    b_h = {'card': 70, 'rows': 24, 'panel': 120}[kind]
    p2, p3 = doc[1], doc[2]
    for y in range(120, int(a_top) - 20, 14):
        p2.insert_text((40, y), f'Narrative line {y} before the card, plain words.', fontsize=10)
    edge, fill = (0.15, 0.39, 0.92), (0.86, 0.9, 1.0)
    p2.draw_rect(pymupdf.Rect(57, a_top, 198, bottom), color=edge, fill=fill, width=1.5)
    p3.draw_rect(pymupdf.Rect(57, top, 198, top + b_h), color=edge, fill=fill, width=1.5)
    if kind == 'card':
        p2.insert_text((66, a_top + 13), 'COMPLETION MILESTONE', fontsize=7)
        p3.insert_text((66, top + 12), 'Phase I Scope Completion', fontsize=9)
        p3.insert_text((66, top + 28), 'Baseline Finish   09-Feb.2027', fontsize=8)
        p3.insert_text((66, top + 42), 'Expected Finish   09-Feb.2027', fontsize=8)
    elif kind == 'rows':
        p2.insert_text((66, bottom - 6), 'CONS.PL.S01.1000   14 wd', fontsize=9)
        p3.insert_text((66, top + 12), 'CONS.PL.S01.1010   12 wd', fontsize=9)
    else:
        for y in range(int(a_top) + 14, int(bottom) - 4, 14):
            p2.insert_text((66, y), f'panel line {y}', fontsize=9)
        for y in range(int(top) + 12, int(top + b_h) - 4, 14):
            p3.insert_text((66, y), f'panel line {y}', fontsize=9)
    for y in range(int(top + b_h) + 30, 772, 14):
        p3.insert_text((40, y), f'Narrative line {y} after the card, plain words.', fontsize=10)
    doc.save(path)
    doc.close()
    return path


def test_checker_flags_a_small_card_split_by_the_break(tmp_path):
    import pytest
    if pymupdf is None:
        pytest.skip('PyMuPDF missing')
    from p6_export import pagination_check as pc
    res = pc.check_pdf(_split_box_pdf(str(tmp_path / 'card.pdf')))
    got = [(f['type'], f['page']) for f in res['flags']]
    assert got == [('block_split', 2)], res['flags']
    assert 'COMPLETION MILESTONE' in res['flags'][0]['detail']
    assert 'block_split' in pc.DEFECT_TYPES


def test_checker_leaves_whole_rows_and_a_long_panel_at_the_break_alone(tmp_path):
    import pytest
    if pymupdf is None:
        pytest.skip('PyMuPDF missing')
    from p6_export import pagination_check as pc
    for kind in ('rows', 'panel'):
        res = pc.check_pdf(_split_box_pdf(str(tmp_path / f'{kind}.pdf'), kind))
        assert 'block_split' not in {f['type'] for f in res['flags']}, (kind, res['flags'])


# ── the narrative's letterhead table is running furniture, not a table header ─────────────
# Since centred columns match by their centre (STUDIO-RICH-6), the Baseline Narrative's
# letterhead 'OWNER  CONSULTANT  CONTRACTOR' over 'logo logo logo' (both centred in the same
# three cells, on every page) read as a table header repeated over its first row - kept as
# content, it made every page start with a 'table' (GBT narrative PDF: 0 -> 27 flags, 15 of
# them 'large blank ... page N+1 starts with table OWNER CONSULTANT CONTRACTOR').
_AREAS = ('Silo', 'Tower', 'Jetty', 'Conveyor', 'Workshop', 'Substation', 'Gatehouse',
          'Warehouse', 'Pump house', 'MCC room', 'Weighbridge')
_WORKS = ('piling', 'raft', 'columns', 'slab', 'steel erection', 'cladding', 'roofing',
          'cabling', 'testing', 'handover')


def _letterhead_pdf(path, n=5):
    doc = pymupdf.open()
    k = 0
    for no in range(1, n + 1):
        pg = doc.new_page(width=A4[0], height=A4[1])
        for cx, word in ((150, 'OWNER'), (300, 'CONSULTANT'), (450, 'CONTRACTOR')):
            w = pymupdf.get_text_length(word, fontsize=7)
            pg.insert_text((cx - w / 2, 72), word, fontsize=7)
            w = pymupdf.get_text_length('logo', fontsize=7)
            pg.insert_text((cx - w / 2, 81), 'logo', fontsize=7)
        if no == 1:
            pg.insert_text((40, 120), '1) Project Overview', fontsize=16, fontname='hebo')
        y = 150 if no == 1 else 115
        pg.insert_text((40, y), 'Milestone', fontsize=9, fontname='hebo')
        pg.insert_text((300, y), 'Area', fontsize=9, fontname='hebo')
        pg.insert_text((420, y), 'Date', fontsize=9, fontname='hebo')
        y += 16
        while y < 780:
            k += 1
            area, work = _AREAS[k % len(_AREAS)], _WORKS[(k // len(_AREAS)) % len(_WORKS)]
            pg.insert_text((40, y), f'{area} {work} completed', fontsize=9)
            pg.insert_text((300, y), area, fontsize=9)
            pg.insert_text((420, y), f'{k % 28 + 1:02d}-Feb-2027', fontsize=9)
            y += 16
        pg.insert_text((280, 825), f'Page {no} of {n}', fontsize=8)
    doc.save(path)
    doc.close()
    return path


def test_checker_strips_a_letterhead_table_that_repeats_on_every_page(tmp_path):
    import pytest
    if pymupdf is None:
        pytest.skip('PyMuPDF missing')
    from p6_export import pagination_check as pc
    path = _letterhead_pdf(str(tmp_path / 'narr.pdf'))
    pages = pc._read_pdf(path)
    pc._strip_running(pages)
    assert not any(l.t.strip() in ('OWNER', 'CONSULTANT', 'CONTRACTOR', 'logo')
                   for P in pages for l in P.lines)
    assert pc.check_pdf(path)['flags'] == []


# ── a title inside a card that closes on the page is the card's label, not a heading ──────
# GBT rich Studio, Float Analysis: once the Float Health card (score + 'High Float > 44 WD -
# construction' driver label + bar + note) is kept whole, the 'how the score is calculated'
# legend starts the next page - the checker read the bold driver label as a heading whose
# block (the legend) started the next page (heading_separated_from_block).
def _card_label_pdf(path, boxed=True):
    doc = pymupdf.open()
    for no in range(1, 4):
        pg = doc.new_page(width=A4[0], height=A4[1])
        pg.insert_text((40, 30), 'PROJECT REPORT  Grain Bulk Terminal', fontsize=8)
        pg.insert_text((280, 825), f'Page {no} of 3', fontsize=8)
    p1, p2, p3 = doc
    p1.insert_text((40, 110), '17 Float Analysis', fontsize=16, fontname='hebo')
    for y in range(140, 540, 14):
        p1.insert_text((40, y), f'Narrative line {y}: the float profile of the schedule in plain words.', fontsize=9)
    if boxed:
        p1.draw_rect(pymupdf.Rect(40, 560, 555, 660), color=(0.8, 0.84, 0.9), fill=(0.97, 0.98, 1.0), width=1)
    p1.insert_text((200, 590), 'High Float > 44 WD - construction', fontsize=12, fontname='hebo')
    p1.insert_text((200, 604), 'the score driver - 100 minus this %', fontsize=8)
    p1.insert_text((200, 630), 'Score = 100 - the construction High-Float defect above.', fontsize=8)
    y = 110
    p2.insert_text((40, y), 'Activity ID', fontsize=9, fontname='hebo')
    p2.insert_text((200, y), 'Activity Name', fontsize=9, fontname='hebo')
    p2.insert_text((450, y), 'Total Float', fontsize=9, fontname='hebo')
    for i in range(40):
        y += 16
        p2.insert_text((40, y), f'CONS.PL.S{i:02d}.1010', fontsize=9)
        p2.insert_text((200, y), f'{_AREAS[i % len(_AREAS)]} {_WORKS[i % len(_WORKS)]}', fontsize=9)
        p2.insert_text((450, y), f'{45 + i} wd', fontsize=9)
    for y in range(110, 780, 14):
        p3.insert_text((40, y), f'Closing narrative line {y}, plain words.', fontsize=9)
    doc.save(path)
    doc.close()
    return path


def test_checker_a_label_inside_a_closed_card_is_not_a_heading_ending_the_page(tmp_path, monkeypatch):
    import pytest
    if pymupdf is None:
        pytest.skip('PyMuPDF missing')
    from p6_export import pagination_check as pc
    path = _card_label_pdf(str(tmp_path / 'card.pdf'))
    assert pc.check_pdf(path)['flags'] == []
    monkeypatch.setattr(pc, '_in_closed_box', lambda *a, **k: False)     # the pre-fix reading
    assert 'heading_separated_from_block' in {f['type'] for f in pc.check_pdf(path)['flags']}
    # control: the same label with no card around it is still a heading ending the page
    monkeypatch.undo()
    loose = _card_label_pdf(str(tmp_path / 'loose.pdf'), boxed=False)
    assert 'heading_separated_from_block' in {f['type'] for f in pc.check_pdf(loose)['flags']}


# ── Chrome proof: driving-path cards and score cards are never parted by a page break ──────
_NEW_KEEP = ('.chain > .box', '.chain > .msbox', '.fh', '.scorelegend')
_CHAIN_CSS = (
    'body{font-family:Calibri,Arial,sans-serif;font-size:12px;margin:0;color:#1f2937}'
    'h2{font-size:16px;margin:14px 0 8px}'
    '.chain{display:flex;align-items:stretch;flex-wrap:wrap;gap:5px;margin-bottom:8px}'
    '.arw{display:flex;align-items:center;color:#64748b;font-weight:900;font-size:15px}'
    '.box{flex:none;width:184px;border:1px solid #d9dee6;border-radius:10px;padding:9px 11px}'
    '.box .bt{font-size:12px;font-weight:700;line-height:1.2}.box .bc{font-size:9.5px;color:#64748b;margin:3px 0 8px}'
    '.b4{display:grid;grid-template-columns:1fr 1fr;gap:6px 8px}.b4 .k{font-size:9px;color:#64748b}'
    '.b4 .v{font-size:12px;font-weight:700}.b4 .full{grid-column:1/-1;border-top:1px dashed #d9dee6;padding-top:4px}'
    '.msbox{flex:none;width:188px;border:2px solid #2563eb;border-radius:10px;padding:10px 11px;background:#dbeafe}'
    '.msbox .msflag{font-size:9px;text-transform:uppercase;color:#2563eb;margin-bottom:6px}'
    '.msbox .mst{font-size:12px;font-weight:800;color:#2563eb;margin-bottom:6px}'
    '.msbox .r{display:flex;justify-content:space-between;font-size:11px;margin:2px 0}'
    '.lanehdr{display:flex;gap:9px;align-items:center;margin:10px 0 6px;font-size:11px}'
    '.lanetag{font-size:10px;font-weight:800;text-transform:uppercase;padding:3px 9px;'
    'border-radius:6px;background:#dbeafe;color:#1e40af}')


def _chain_doc(lanes=12, intro=True):
    """Driving-path lanes of activity cards ending on a milestone card. ``intro``: a lane
    title row (Critical Path Analyzer '.lanehdr') of varying length above each lane, else lanes
    of 4-6 cards; card heights vary by lane
    (the cards do not sit at the same place on every page - identical drawings / text at the
    same place on most pages are page furniture to the checker)."""
    out = []
    for n in range(lanes):
        parts = []
        for i in range(5 if intro else 4 + n % 3):
            parts.append(
                f'<div class="box"><div class="bt">{_AREAS[(n + i) % len(_AREAS)]} '
                f'{_WORKS[(n * 3 + i) % len(_WORKS)]}</div><div class="bc">Phase {n % 4 + 1} · '
                f'{_AREAS[i % len(_AREAS)]} works' + ' · Silos Civil Works · Elevated Raft' * (n % 3)
                + '</div><div class="b4"><div><div class="k">Planned</div>'
                f'<div class="v">0.0%</div></div><div><div class="k">Actual</div><div class="v">0.0%</div></div>'
                f'<div><div class="k">Baseline finish</div><div class="v">1{i}-Oct.2026</div></div>'
                f'<div><div class="k">Expected finish</div><div class="v">1{i}-Oct.2026</div></div>'
                f'<div class="full"><div class="k">Delay</div><div class="v">0 d</div></div></div></div>'
                '<div class="arw">&#9656;</div>')
        parts.append(f'<div class="msbox"><div class="msflag">&#9670; Completion Milestone</div>'
                     f'<div class="mst">Phase {n + 1} Scope Completion</div>'
                     f'<div class="r"><span>Baseline Finish</span><b>09-Feb.2027</b></div>'
                     f'<div class="r"><span>Expected Finish</span><b>09-Feb.2027</b></div>'
                     f'<div class="r"><span>Delay</span><b>0 d</b></div></div>')
        lead = (f'<div class="lanehdr"><span class="lanetag">Path {n + 1}</span><span>'
                + 'activities on the longest path to the milestone. ' * (n % 3 + 1)
                + '</span></div>') if intro else ''
        out.append(f'{lead}<div class="chain">{"".join(parts)}</div>')
    return ('<!doctype html><html><head><meta charset="utf-8"><style>@page{size:A4;margin:18mm}'
            f'{_CHAIN_CSS}</style></head><body><h2>Driving Path Analyzer</h2>{"".join(out)}</body></html>')


def test_chrome_keeps_driving_path_cards_whole(tmp_path, monkeypatch):
    import pytest
    if pymupdf is None:
        pytest.skip('PyMuPDF missing')
    from p6_export.pdf import chrome_candidates, run_chrome
    from p6_export import pagination_check as pc
    import report_theme as rt
    found = chrome_candidates(None)
    if not found:
        pytest.skip('no Chromium installed')

    def printed(name, intro):
        src = tmp_path / f'{name}.html'
        src.write_text(rt.with_pagination(_chain_doc(intro=intro)), encoding='utf-8')
        out = str(tmp_path / f'{name}.pdf')
        run_chrome(found[0], [f'--print-to-pdf={out}', '--no-pdf-header-footer',
                              'file:///' + str(src).replace(os.sep, '/')], timeout=120)
        return pc.check_pdf(out)

    assert all(s in rt.KEEP_WHOLE_SELECTORS for s in _NEW_KEEP)
    after = [printed('after', True), printed('after_plain', False)]
    # BEFORE - the shared layer without the STUDIO-RICH-10 selectors: a card is split across
    # the break (title on one page, dates on the next)
    monkeypatch.setattr(rt, 'KEEP_WHOLE_SELECTORS', tuple(s for s in rt.KEEP_WHOLE_SELECTORS if s not in _NEW_KEEP))
    monkeypatch.setattr(rt, 'MEASURED_SELECTORS', tuple(s for s in rt.MEASURED_SELECTORS if s not in _NEW_KEEP))
    before = printed('before_plain', False)
    assert all(a['pages'] >= 3 for a in after)
    assert 'block_split' in {f['type'] for f in before['flags']}, before['flags']
    # AFTER - every card whole, and a lane's title row stays with its first cards
    assert [a['flags'] for a in after] == [[], []], after


def _small_card_split(h_px=600, w_px=900):
    """Two slices parting a SMALL card: 60 px of it (top border + its flag line) end slice 1,
    50 px (title + bottom border) open slice 2."""
    import pymupdf
    grey = (0.6, 0.64, 0.7)
    out = []
    for part in (1, 2):
        doc = pymupdf.open()
        page = doc.new_page(width=w_px, height=h_px)
        if part == 1:
            for i, y in enumerate(range(30, 500, 22)):
                page.insert_text((36, y), 'Row %02d   CONS.TR28.32.SS.%04d   Install steel beams' % (i, 1100 + i), fontsize=15)
            page.draw_line((300, 540), (560, 540), color=grey, width=1.5)
            for x in (300, 560):
                page.draw_line((x, 540), (x, h_px + 6), color=grey, width=1.5)
            page.insert_text((314, 562), 'COMPLETION MILESTONE', fontsize=11)
        else:
            for x in (300, 560):
                page.draw_line((x, -6), (x, 50), color=grey, width=1.5)
            page.draw_line((300, 50), (560, 50), color=grey, width=1.5)
            page.insert_text((314, 30), 'Phase I Scope Completion', fontsize=15)
            for i, y in enumerate(range(90, 400, 22)):
                page.insert_text((36, y), 'Row %02d   Baseline finish 09-Feb.2027' % i, fontsize=15)
        out.append(page.get_pixmap(alpha=False).tobytes('png'))
    return out


def test_word_slices_parting_a_small_card_stay_flagged(tmp_path):
    """The long-card rule does not excuse a SMALL card whose title ends one picture and whose
    body opens the next (the Word twin of the PDF's block_split)."""
    from p6_export import pagination_check as pc
    path = _docx_sections([_small_card_split()], str(tmp_path / 'small.docx'))
    flags = [f for f in pc.docx_picture_flags(path) if f['type'] == 'picture_truncated']
    assert len(flags) == 1 and 'small card' in flags[0]['detail'], flags
