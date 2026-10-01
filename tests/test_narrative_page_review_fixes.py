"""Baseline Narrative — defects from the page-by-page PNG review of GBT / SG (NARRFIX).

1. §15 production table: the 'Working-days' header broke mid-word ('Workin / g-days', PDF +
   Word) and the Total quantity broke inside the number ('243,805,3 / 97'). The header is
   'Working days' (wraps at its space), the columns are widened, the PDF figures never wrap.
2. §15 Word: every data row was one EXACT 40 pt height, so SG's 4-line crew cell lost its
   last line ('+15 more'). The one shared height is raised to the tallest wrapped cell and is
   AT LEAST (never clips); the checker now flags text clipped by an EXACT row (text_cut).
3. §13: the untitled 5-row equipment totals table opened SG PDF p22 alone. Each §13
   sub-section is one print group kept whole up to 45 % of a page, and each totals table
   carries its title as a repeating header row (PDF + Word). The checker's --html heading
   hints honour 'p.rescap' (a lead-in) vs the 'div.rescap' chart caption.
4. §16 S-curve: sliver columns carry no value label (the line struck '0M' '1M'); the Word
   end-point label moves left off the right-hand axis.

Pure tests need python-docx only; the Word / Chrome proofs are skipped without Word / Chrome.
"""
import os
import re
import tempfile

import pytest
from docx import Document
from docx.oxml.ns import qn

from p6_export import pagination_check as pc
from p6_narrative import docx_native, docx_template as T, docx_writer as W, prodrate as PR
from p6_narrative.html import page_html, _volwork_svg
from p6_narrative.util import bar_label_shown, restable_title

_META = {'project_name': 'Synthetic Terminal', 'data_date': '11 Dec 2025'}
CREW4 = 'Steel Fixer ~1.1/day; Carpenter ~0.9/day; Carpenter Helper ~0.5/day; +15 more'
PAD = 2 * W.CELL_PAD_PT


def _prod_payload(headers=None, widths=None, rows=None):
    return {'available': True, 'intro': 'Production rates.', 'method_intro': 'How.',
            'method': [['Rate per day', 'Total quantity / Total working days']],
            'breakdown': [], 'headers': list(headers or PR.HEADERS),
            'widths': list(widths or PR.WIDTHS),
            'rows': rows or [['EX-resource', '', '243,805,397', '4787', '', '', CREW4],
                             ['Piles - QTY- m3', 'm3', '36,401', '464', '78.5 m3/day',
                              '11.9 – 168.4 m3/day', 'Piles Works Subcontractor MNP ~1/day']],
            'no_unit_note': 'The rate columns are blank for the unit-less row.'}


OLD_HEADERS = ['Quantities resource', 'Unit', 'Total quantity', 'Working-days',
               'Rate/day', 'Range (min–max)', 'Crew assigned (per day)']
OLD_WIDTHS = [1.65, 0.52, 0.72, 0.58, 0.78, 0.87, 1.78]


# ── 1 · headers and figures fit their columns ──────────────────────────────────
def test_prodrate_header_words_and_figures_fit_their_columns():
    assert 'Working days' in PR.HEADERS and 'Working days' in PR.BREAKDOWN_HEADERS
    assert abs(sum(PR.WIDTHS) - 6.9) < 1e-6
    for h, w in zip(PR.HEADERS, PR.WIDTHS):
        assert '-' not in h, h                          # a header wraps at spaces only
        for word in h.split():                          # bold 9.5 pt: every word on one line
            assert W._tnr_width_pt(word, 9.5) * 1.1 <= w * 72 - PAD, (h, word, w)
    assert W._wrapped_lines('243,805,397', PR.WIDTHS[2] * 72 - PAD, 10) == 1
    assert W._wrapped_lines('11.9 – 168.4', PR.WIDTHS[5] * 72 - PAD, 10) == 1
    # the pre-fix header / widths fail the same rule
    assert W._tnr_width_pt('Working-days', 9.5) * 1.1 > OLD_WIDTHS[3] * 72 - PAD
    assert W._wrapped_lines('243,805,397', OLD_WIDTHS[2] * 72 - PAD, 10) == 2


def test_wrap_estimate_counts_lines_and_breaks_a_too_long_word():
    assert W._wrapped_lines('', 100, 10) == 1
    assert W._wrapped_lines(CREW4, PR.WIDTHS[6] * 72 - PAD, 10) == 4
    assert W._wrapped_lines('x' * 60, 50, 10) >= 3        # a word wider than the cell


# ── 2 · Word rows: one shared height, raised to the tallest cell, never EXACT ────
def _prod_docx(path=None, payload=None, exact_pt=None):
    d = Document()
    T.apply_base_styles(d)
    T.apply_page_geometry(d.sections[0])
    W._render_prodrate(d, payload or _prod_payload(), 15, None)
    tbl = d.tables[-1]
    if exact_pt:                                         # the pre-fix writer: EXACT rows
        for rw in list(tbl.rows)[1:]:
            W._row_h(rw, exact_pt, exact=True)
    if path:
        d.save(path)
    return d, tbl


def _tr_height(rw):
    h = rw._tr.find(qn('w:trPr')).find(qn('w:trHeight'))
    return int(h.get(qn('w:val'))) / 20.0, h.get(qn('w:hRule'))


def test_word_production_rows_share_one_height_that_fits_the_tallest_cell():
    _, tbl = _prod_docx()
    data = [_tr_height(rw) for rw in list(tbl.rows)[1:]]
    assert len({h for h, _ in data}) == 1                # every data row the same height
    assert all(rule == 'atLeast' for _, rule in data)    # AT LEAST: never clips
    assert data[0][0] >= 4 * 10 * W.LINE_PITCH            # the 4-line crew cell fits
    # a table of short rows keeps the 40 pt floor
    _, small = _prod_docx(payload=_prod_payload(rows=[['A', 'm3', '1', '2', '3', '4', 'Crew']]))
    assert _tr_height(small.rows[1]) == (40.0, 'atLeast')


def _com_cells(path, cells):
    """(first-y, last-y, text) of each (row, col) of table 1 and whether any word is split."""
    import pythoncom
    import win32com.client as wc
    pythoncom.CoInitialize()
    w = wc.DispatchEx('Word.Application')
    out = {}
    try:
        w.Visible = False
        w.DisplayAlerts = 0
        d = w.Documents.Open(os.path.abspath(path), False, True, False)
        try:
            d.Repaginate()
            tb = d.Tables(1)
            for r, c in cells:
                rng = tb.Cell(r, c).Range
                split = []
                for k in range(1, rng.Words.Count + 1):
                    wd = rng.Words(k)
                    t = wd.Text.strip()
                    if len(t) < 2 or t in ('\r\x07',):
                        continue
                    e = wd.Start + len(wd.Text.rstrip()) - 1
                    if d.Range(wd.Start, wd.Start).Information(6) != d.Range(e, e).Information(6):
                        split.append(t)
                out[(r, c)] = split
        finally:
            d.Close(False)
    finally:
        w.Quit()
        pythoncom.CoUninitialize()
    return out


def test_word_proof_no_clipped_crew_no_split_header_or_figure(tmp_path):
    """Word lays the table out: the fixed table has no text_cut and no word split across
    lines in the header ('Working days') or the Total quantity figure; the pre-fix EXACT
    40 pt rows are flagged text_cut and the pre-fix header splits 'Working-days'."""
    if not pc.word_available():
        pytest.skip('Microsoft Word (COM) is not available')
    new, old = str(tmp_path / 'new.docx'), str(tmp_path / 'old.docx')
    _prod_docx(new)
    _prod_docx(old, payload=_prod_payload(OLD_HEADERS, OLD_WIDTHS), exact_pt=40)
    flags_new, _, _ = pc.analyze_word_layout(pc.word_layout(new))
    flags_old, _, _ = pc.analyze_word_layout(pc.word_layout(old))
    assert not [f for f in flags_new if f['type'] == 'text_cut'], flags_new
    assert [f for f in flags_old if f['type'] == 'text_cut'], flags_old
    cells = [(1, 3), (1, 4), (2, 3)]
    split_new, split_old = _com_cells(new, cells), _com_cells(old, cells)
    assert all(not v for v in split_new.values()), split_new
    assert any(split_old.values()), split_old


# ── Chrome helpers ──────────────────────────────────────────────────────────────
def _chrome():
    from p6_export.pdf import chrome_candidates
    found = chrome_candidates(None)
    if not found:
        pytest.skip('no Chromium installed')
    return found[0]


def _print(html, chrome, folder, name):
    from p6_export.pdf import run_chrome
    src = os.path.join(folder, name + '.html')
    with open(src, 'w', encoding='utf-8') as fh:
        fh.write(html)
    out = os.path.join(folder, name + '.pdf')
    run_chrome(chrome, [f'--print-to-pdf={out}', '--no-pdf-header-footer',
                        'file:///' + src.replace(os.sep, '/')], timeout=120)
    return out


def _words(pdf):
    import pymupdf
    with pymupdf.open(pdf) as d:
        return [[w[4] for w in pg.get_text('words')] for pg in d]


def test_chrome_proof_production_header_and_figure_stay_whole():
    chrome = _chrome()
    doc = {'meta': dict(_META), 'sections': [
        {'number': 15, 'title': 'Productivity Rates & Resources Assigned', 'kind': 'prodrate',
         'payload': _prod_payload()}]}
    html = page_html(doc)
    assert 'dt prodtbl' in html and 'class="nw"' in html
    old_doc = {'meta': dict(_META), 'sections': [dict(doc['sections'][0], payload=_prod_payload(
        OLD_HEADERS, OLD_WIDTHS))]}
    old = page_html(old_doc).replace('dt prodtbl', 'dt').replace(' class="nw"', '')
    with tempfile.TemporaryDirectory() as folder:
        new_w = sum(_words(_print(html, chrome, folder, 'new')), [])
        old_w = sum(_words(_print(old, chrome, folder, 'old')), [])
    assert 'Working' in new_w and 'days' in new_w and 'Workin' not in new_w
    assert '243,805,397' in new_w
    assert 'Workin' in old_w or '243,805,397' not in old_w      # the pre-fix breaks a word


# ── 3 · §13: titled totals tables; a sub-section moves whole ──────────────────────
MONTHS = ['%s-25' % m for m in ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug')]


def _resload_payload():
    def grp(title, n, heads, color):
        return {'title': title, 'basis_note': 'Read from the %s resource assignments.' % title,
                'total_label': '16,071', 'total_unit': 'hours', 'window': 'Jan 2025 – Aug 2025',
                'row_headers': heads,
                'rows': [['%s resource %d' % (title, i)] + ['{:,}'.format(5000 - 300 * i)] * (len(heads) - 1)
                         for i in range(n)],
                'charts': [{'chart_title': '%s — number per month' % title, 'color': color,
                            'span': MONTHS, 'values': [6, 7, 4, 1, 16, 32, 12, 9],
                            'peak_val': 32, 'peak_label': 'May 2025', 'peak_unit': ''}]}
    return {'available': True, 'intro': 'The manpower and equipment loading.',
            'groups': [grp('Manpower', 11, ['Resource', 'Total man-hours'], '1F4E79'),
                       grp('Equipment', 5, ['Resource', 'Total equipment-hours', 'Peak no. on site'],
                           '2E9E5B')]}


def _resload_doc(filler_words):
    return {'meta': dict(_META), 'sections': [
        {'number': 13, 'title': 'Resource Loading', 'kind': 'resload',
         'payload': dict(_resload_payload(), intro=' '.join(['loading'] * filler_words))}]}


def test_totals_tables_carry_their_title_as_a_repeating_header_row():
    assert restable_title(13, 2, {'title': 'Equipment'}) == '13.2 · Equipment — totals by resource'
    html = page_html(_resload_doc(5))
    for i, t in ((1, 'Manpower'), (2, 'Equipment')):
        assert re.search(r'<thead><tr><th class="tcap" colspan="\d">%s</th></tr>'
                         % re.escape(restable_title(13, i, {'title': t})), html)
    assert html.count('<div class="resgrp rpt-group">') == 2
    d = Document()
    T.apply_base_styles(d)
    W._render_resload(d, _resload_payload(), 13, None)
    tables = [t for t in d.tables if t.rows[0].cells[0].text.endswith('totals by resource')]
    assert [t.rows[0].cells[0].text for t in tables] == [
        restable_title(13, 1, {'title': 'Manpower'}), restable_title(13, 2, {'title': 'Equipment'})]
    for t in tables:
        for rw in t.rows[:2]:                             # title + header repeat together
            tp = rw._tr.find(qn('w:trPr'))
            assert tp.find(qn('w:tblHeader')) is not None and tp.find(qn('w:cantSplit')) is not None
        assert len(t.rows[0].cells) == len(t.rows[1].cells)   # the title spans the table
        assert t.rows[0].cells[0]._tc is t.rows[0].cells[-1]._tc


def test_rpt_group_is_measured_and_kept_whole_up_to_the_keep_limit():
    import report_theme as RT
    assert '.rpt-group' in RT.MEASURED_SELECTORS
    js = RT.pagination_script()
    assert "else if(hg<=H*KT&&el.classList.contains('rpt-group'))todo.push([el,'rpt-fit']);" in js


def test_html_headings_honour_the_tag_of_a_selector():
    hs = pc.html_headings('<div class="sub">13.2 · Equipment</div><p class="rescap">Lead in</p>'
                          '<div class="calfig"><div class="rescap">Peak 32 in May 2025.</div></div>')
    assert '13.2 · Equipment' in hs and 'Lead in' in hs
    assert 'Peak 32 in May 2025.' not in hs


def _pages_of(words, token):
    return [i for i, ws in enumerate(words) if token in ws]


def test_chrome_proof_a_totals_table_never_opens_a_page_without_its_sub_section():
    """At several page fills the §13.2 group (heading, chart, caption, 5-row table) moves
    whole: the first equipment row is on the page of '13.2 · EQUIPMENT'. Without the group
    (the pre-fix markup) at least one fill leaves the table alone on the next page."""
    chrome = _chrome()
    after, before = [], []
    with tempfile.TemporaryDirectory() as folder:
        for k, words in enumerate((420, 470, 520, 570, 620)):
            html = page_html(_resload_doc(words))
            old = html.replace(' rpt-group', '')
            for src, into, tag in ((html, after, 'a'), (old, before, 'b')):
                pdf = _print(src, chrome, folder, '%s%d' % (tag, k))
                ws = _words(pdf)
                sub = _pages_of(ws, 'EQUIPMENT')           # the 13.2 sub-heading (upper case)
                first_row = [i for i, p in enumerate(ws) if ' '.join(p).find('Equipment resource 0') >= 0]
                into.append((k, sub[:1], first_row[:1]))
                if src is html:
                    flags = pc.check_pdf(pdf, headings=pc.html_headings(html))['flags']
                    assert not [f for f in flags if f['type'] in ('orphaned_heading',
                                                                    'heading_separated_from_block')], flags
    assert all(s == r for _, s, r in after), after
    assert any(s != r for _, s, r in before), before


# ── 4 · §16 S-curve labels ──────────────────────────────────────────────────────
VALS = [12e6, 0, 1e6, 2e6, 138e6, 18e6]
CUM = [12e6, 12e6, 13e6, 15e6, 153e6, 171e6]


def test_sliver_columns_carry_no_label_in_pdf_and_word():
    assert [bar_label_shown(v, VALS) for v in VALS] == [True, False, False, False, True, True]
    svg = _volwork_svg(['M%d' % i for i in range(6)], VALS, CUM, '1F4E79', 'E8A33D', '')
    labels = re.findall(r'rotate\(-90[^)]*\)">([^<]+)</text>', svg)
    assert labels == ['12M', '138M', '18M']
    d = Document()
    assert docx_native.add_cashflow_combo(d, ['M%d' % i for i in range(6)], VALS, CUM, '',
                                          num_fmt='#,##0,,"M"') is not None
    xml = [p.blob.decode('utf-8') for p in d.part.package.parts
           if p.partname.endswith('.xml') and '/charts/' in p.partname][0]
    bar = xml.split('<c:barChart>')[1].split('</c:barChart>')[0]
    deleted = re.findall(r'<c:dLbl><c:idx val="(\d+)"/><c:delete val="1"/></c:dLbl>', bar)
    assert deleted == ['1', '2', '3']
    line = xml.split('<c:lineChart>')[1].split('</c:lineChart>')[0]
    last = re.search(r'<c:dLbl><c:idx val="5"/><c:layout><c:manualLayout><c:x val="(-[\d.]+)"/>', line)
    assert last and float(last.group(1)) < 0          # the end label moves left of the axis
