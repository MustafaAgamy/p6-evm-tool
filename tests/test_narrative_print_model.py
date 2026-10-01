"""Baseline Narrative PDF page model (owner point 14 — findings NARR-PDF-1 / NARR-PDF-2).

The narrative is designed as fixed A4 sheets (double frame, 3-logo header band, page number
inside the frame). A section longer than one sheet used to spill onto frameless,
header-less, zero-margin continuation pages, and the 36-row milestone tables were pushed
whole to a new page with 2 rows stranded on a third. The PDF now paints the furniture per
PHYSICAL page; these tests prove it on a synthetic long narrative printed by Chrome.
"""
import os
import re
import tempfile

import pytest

from p6_narrative.html import page_html, render_narrative_html

_META = {'project_name': 'Synthetic Terminal', 'data_date': '11 Dec 2025'}
_LONG_P = ('This paragraph stands for a long narrative passage of the Project Overview: it '
           'describes the scope, the methodology, the phasing and the contractual framework '
           'in enough words to be a real body paragraph of the report. ')


def _doc(ms_rows=60, paras=45):
    rows = [['Milestone number %02d of the synthetic baseline' % i, '%02d-Jan-2027' % (i % 28 + 1)]
            for i in range(1, ms_rows + 1)]
    return {'meta': dict(_META), 'sections': [
        {'number': 1, 'title': 'Project Overview', 'kind': 'overview',
         'payload': {'paragraphs': [_LONG_P * 3] * paras, 'breakdown': [], 'total': 0}},
        {'number': 2, 'title': 'Major Milestones', 'kind': 'ms_table',
         'payload': {'columns': ['Milestone', 'Date'], 'rows': rows}},
        {'number': 3, 'title': 'Key Dates', 'kind': 'ms_table',
         'payload': {'columns': ['Milestone', 'Date'], 'rows': rows[:36]}},
    ]}


# ── unit: the print model is in the PDF source, the screen view is untouched ───────
def test_pdf_source_carries_the_per_page_furniture_once():
    html = page_html(_doc(5, 2))
    assert html.count('class="pfx"') == 1 and html.count('id="narr-print"') == 1
    css = re.search(r'<style id="narr-print">(.*?)</style>', html, re.S).group(1)
    assert 'counter(page)' in css and '@page front' in css
    assert 'box-decoration-break: clone' in css and 'position: fixed' in css
    assert '--rpt-page-reserve' in css
    # cover + table of contents are the unnumbered front matter
    assert html.count('<div class="page front">') == 2
    # the on-screen renderer carries none of it (the Studio / screen reuse it)
    screen = render_narrative_html(_doc(5, 2))
    assert 'narr-print' not in screen and 'class="pfx"' not in screen


def test_milestone_table_has_a_repeating_header_row():
    html = render_narrative_html(_doc(40, 1))
    m = re.search(r'<table class="dt"><thead><tr><th[^>]*>Milestone</th>.*?</thead><tbody>(.*?)</tbody>',
                  html, re.S)
    assert m, 'the milestone header row must live in <thead>'
    assert m.group(1).count('<tr>') == 40 and '<th' not in m.group(1)


# ── Chrome proof ────────────────────────────────────────────────────────────────
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


def _pages(pdf):
    import pymupdf
    out = []
    with pymupdf.open(pdf) as d:
        for pg in d:
            h = pg.rect.height
            words = pg.get_text('words')
            frames = [r for r in (x['rect'] for x in pg.get_drawings())
                      if r.width > pg.rect.width * 0.8 and r.height > h * 0.8]
            body = [w for w in words if w[4] not in ('OWNER', 'CONSULTANT', 'CONTRACTOR', 'logo')]
            out.append({
                'h': h, 'frames': len(frames),
                'header': sum(1 for w in words if w[4] in ('OWNER', 'CONSULTANT', 'CONTRACTOR')),
                'top': min((w[1] for w in body), default=None),
                'foot': [w[4] for w in words if w[1] > h - 26],
                'text': ' '.join(w[4] for w in words),
                'ms_rows': sum(1 for w in words if w[4] == 'number' and w[0] < 300),
            })
    return out


def test_chrome_every_page_is_framed_headed_and_numbered_and_tables_continue_cleanly():
    chrome = _chrome()
    doc = _doc()
    with tempfile.TemporaryDirectory() as folder:
        after_pdf = _print(page_html(doc), chrome, folder, 'after')
        after = _pages(after_pdf)
        # the pre-fix model: the same report without the per-page print layer
        old = re.sub(r'<style id="narr-print">.*?</style>', '', page_html(doc), flags=re.S)
        before = _pages(_print(old, chrome, folder, 'before'))
        from p6_export import pagination_check as pc
        flags = pc.check_pdf(after_pdf)['flags']

    # BEFORE: continuation pages have no frame, no logo band, text at the paper edge
    assert any(p['frames'] < 2 or p['header'] < 3 for p in before), before
    assert any(p['top'] is not None and p['top'] < 20 for p in before), [p['top'] for p in before]

    # AFTER: every physical page carries the double frame and the 3-logo band …
    assert len(after) >= 6
    for i, p in enumerate(after, 1):
        assert p['frames'] >= 2, (i, p)
        assert p['header'] == 3, (i, p)
        # … the text starts below the logo band on every page (never at the paper edge)
        if p['top'] is not None:
            assert p['top'] > 95, (i, p['top'])
    # front matter unnumbered; body pages numbered with their physical page number
    assert after[0]['foot'] == [] and after[1]['foot'] == []
    for i, p in enumerate(after[2:], 3):
        assert p['foot'] == [str(i)], (i, p['foot'])

    # the long milestone tables: header row on every page they run onto, >= 3 rows a page
    for name in ('Major Milestones', 'Key Dates'):
        start = next(i for i, p in enumerate(after) if name in p['text'] and i > 1)
        # heading, intro and the first rows start together on the section's first page
        assert after[start]['ms_rows'] >= 3, (name, after[start]['ms_rows'])
        span = [p for p in after[start:] if p['ms_rows']]
        span = span[:next((k for k, p in enumerate(span[1:], 1)
                          if 'Major Milestones' in p['text'] or 'Key Dates' in p['text']), len(span))]
        for p in span:
            assert 'Milestone Date' in p['text'], (name, p['text'][:120])
            assert p['ms_rows'] >= 3, (name, p['ms_rows'])

    # and the shared page checker finds nothing to flag
    assert flags == [], flags


# ── NARR-PDF-3 / NARR-PDF-4: activity-code pairs and "fits a page" tables ────────────
def _codes_doc(sizes):
    tables = [{'dimension': 'Code structure %d' % k,
               'rows': [{'code': 'C%d-%02d' % (k, i), 'description': 'Value %d of structure %d' % (i, k)}
                        for i in range(1, n + 1)]}
              for k, n in enumerate(sizes, 1)]
    return {'meta': dict(_META), 'sections': [
        {'number': 10, 'title': 'Activity Codes', 'kind': 'codes', 'payload': {'tables': tables}}]}


_FLOW_JS = "if(hg>fit&&hg<=flow&&!inCell(el))"


def _blank_flags(pdf):
    from p6_export import pagination_check as pc
    return [f for f in pc.check_pdf(pdf)['flags'] if f['type'] == 'large_blank_then_continuation']


def test_chrome_small_code_tables_never_chain_into_one_pushed_block():
    """NARR-PDF-3 — the old table rules put break-after:avoid on the LAST row of a 1-3 row
    table; Chrome carries it out of the table and its flex pair, so pairs of small code
    tables chained into one block pushed to the next page (page before it ~60 % blank)."""
    chrome = _chrome()
    doc = _codes_doc([10, 3, 4, 2, 6, 2, 14, 4, 8, 8])     # the GBT §10 head, all small
    html = page_html(doc)
    assert ':not(:last-child)' in html and ':not(:first-child)' in html
    # the markup of that time: each code's title a div.ct ABOVE its table (the title now rides
    # in the table's <thead> - NARRFIX); the fixed rules must hold for that markup as well
    div_titles = re.sub(r'<table class="codetbl"><thead><tr><th class="ct" colspan="2">(.*?)</th></tr>'
                        r'(.*?)</thead><tbody>(.*?)</tbody></table>',
                        r'<div class="ct">\g<1></div><table class="codetbl">\g<2>\g<3></table>', html)
    assert div_titles.count('<div class="ct">') == 10
    old = div_titles.replace(':not(:last-child)', '').replace(':not(:first-child)', '')
    with tempfile.TemporaryDirectory() as folder:
        after = _blank_flags(_print(html, chrome, folder, 'after'))
        after_div = _blank_flags(_print(div_titles, chrome, folder, 'after_div'))
        before = _blank_flags(_print(old, chrome, folder, 'before'))
    assert before, 'the pre-fix rules should leave a large blank before a pushed code pair'
    assert after == [] and after_div == [], (after, after_div)


def test_chrome_table_taller_than_a_third_continues_instead_of_leaving_a_blank():
    """NARR-PDF-4 — a code table of ~60 % of a page after a half-full page used to be pushed
    whole (the renderer keeps .codetbl whole), leaving the page above it half blank. It now
    continues with its header row repeated and >= 3 rows on each page."""
    chrome = _chrome()
    doc = _codes_doc([14, 14, 34, 3, 8, 8])
    html = page_html(doc)
    assert _FLOW_JS in html
    old = html.replace(_FLOW_JS, 'if(0)')
    with tempfile.TemporaryDirectory() as folder:
        after_pdf = _print(html, chrome, folder, 'after')
        after = _blank_flags(after_pdf)
        before = _blank_flags(_print(old, chrome, folder, 'before'))
        from p6_export import pagination_check as pc
        flags = pc.check_pdf(after_pdf)['flags']
        pages = _pages(after_pdf)
    assert before, 'the pre-fix composer should push the 34-row table whole'
    assert after == [] and flags == [], flags
    # the long table really continues: its rows are on two pages, header on both
    on = [p for p in pages if 'C3-' in p['text']]
    assert len(on) == 2 and all('Code Value Description' in p['text'] for p in on), [p['text'][:80] for p in on]
    # … and its TITLE repeats too, so the continued rows are never of an unnamed code (NARRFIX:
    # GBT PDF p22 opened with 14 rows of '7 · Silos Area Name' under only the header row)
    assert all('3 · Code structure 3' in p['text'] for p in on), [p['text'][:80] for p in on]


def test_code_table_title_is_the_first_row_of_its_repeating_head():
    """NARRFIX — the code's title rides in the table's <thead> (repeated on every page the
    table runs onto, like the Word export) instead of a div above the table."""
    html = page_html(_codes_doc([4, 30]))
    for k, n in ((1, 4), (2, 30)):
        title = '%d &middot; Code structure %d' % (k, k)
        i = html.index(title)
        head = html[html.rindex('<table class="codetbl">', 0, i):html.index('</thead>', i)]
        assert '<thead><tr><th class="ct" colspan="2">' in head and head.count('<tr>') == 2
        assert html.count(title) == 1                     # no separate title div any more
    assert '.codetbl th.ct {' in html                      # styled like the old title line


# ── NARR-PDF-4: a WBS tree over a third of a page continues between its branches ────────
def _tree_doc(a_leaves=3, b_subs=3, b_leaves=6):
    branches = [
        {'name': 'Branch A with a deliberately long label',
         'columns': ['Leaf A-%02d with a long descriptive label' % i for i in range(1, a_leaves + 1)]},
        {'name': 'Branch B with a deliberately long label',
         'columns': [['Sub-branch B%d with a long label' % k,
                      ['Leaf B%d-%02d with a long descriptive label' % (k, i) for i in range(1, b_leaves + 1)]]
                     for k in range(1, b_subs + 1)]},
    ]
    overview = {'name': 'Synthetic Terminal WBS root',
                'children': [{'name': b['name']} for b in branches]}
    return {'meta': dict(_META), 'sections': [
        {'number': 9, 'title': 'Work Breakdown Structure', 'kind': 'wbs_tree',
         'payload': {'overview': overview, 'branches': branches}}]}


_LIST_JS = ("if((el.tagName==='UL'||el.tagName==='OL')&&hg>fit",
            "if(el.tagName==='LI'&&hg>fit&&hg<=flow)")


def test_chrome_wbs_tree_taller_than_a_third_continues_between_branches():
    """NARR-PDF-4 — the renderer keeps a WBS tree (.wt) whole, so a branch of ~70 % of a
    page after a half-full page was pushed to the next page, leaving the page above it
    half blank (GBT §9.4 / §9.7). It now continues between its sub-branches: each small
    sub-branch stays whole and a sub-branch label never ends a page without its first leaf."""
    chrome = _chrome()
    html = page_html(_tree_doc())
    old = html
    for js in _LIST_JS:
        assert html.count(js) == 1, js
        old = old.replace(js, 'if(0&&' + js[3:])
    with tempfile.TemporaryDirectory() as folder:
        after_pdf = _print(html, chrome, folder, 'after')
        before = _blank_flags(_print(old, chrome, folder, 'before'))
        from p6_export import pagination_check as pc
        flags = pc.check_pdf(after_pdf)['flags']
        pages = _pages(after_pdf)
    assert before, 'the pre-fix composer should push the Branch B tree whole'
    assert flags == [], flags
    on = [i for i, p in enumerate(pages) if 'Leaf B' in p['text']]
    assert len(on) == 2, on                    # the tree really continues on the next page
    for k in range(1, 4):                      # every sub-branch label sits with its first leaf
        label = next(i for i, p in enumerate(pages) if 'Sub-branch B%d' % k in p['text'])
        assert 'Leaf B%d-01' % k in pages[label]['text'], (k, label)


def _materials_doc(n_charts, intro_words):
    months = ['%s-26' % m for m in ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
                                    'Sep', 'Oct', 'Nov', 'Dec')]
    charts = [{'name': 'Material %02d - QTY' % k, 'unit': 'm3', 'total': 1000 + k,
               'span': months, 'values': [((k * 7 + i * 13) % 90) + 5 for i in range(12)],
               'color': 'E8A33D', 'peak_val': 95, 'peak_label': 'June 2026'}
              for k in range(1, n_charts + 1)]
    return {'meta': dict(_META), 'sections': [
        {'number': 14, 'title': 'Material Resources', 'kind': 'materials',
         'payload': {'available': True, 'intro': ' '.join(['quantity'] * intro_words),
                     'total_n': n_charts, 'charted_n': n_charts, 'charts': charts,
                     'table_rows': [['Material %02d - QTY' % k, 'm3', '1,000']
                                    for k in range(1, n_charts + 1)]}}]}


def test_chrome_a_run_of_material_charts_never_cuts_a_chart_across_pages():
    """NARR-PDF-5 — the 'Peak ...' caption UNDER each §14 chart (<div class="rescap">, the
    last child of the .calfig) was treated as a heading: its break-after:avoid propagated
    to the figure, so every break between a run of charts was forbidden and Chrome cut the
    next chart itself across the page (GBT p34->p35: title + 2 bars on one page, the rest
    of the columns scattered at the top of the next). Only the lead-in <p class="rescap">
    keeps with its chart group now; every chart moves whole."""
    chrome = _chrome()
    from p6_export import pagination_check as pc
    before, after = [], []
    with tempfile.TemporaryDirectory() as folder:
        for k, words in enumerate((10, 60, 120)):
            html = page_html(_materials_doc(14, words))
            assert 'p.rescap,' in html
            old = html.replace('p.rescap,', '.rescap,')
            for pdf, into in ((_print(html, chrome, folder, 'after%d' % k), after),
                              (_print(old, chrome, folder, 'before%d' % k), before)):
                into.extend(f for f in pc.check_pdf(pdf)['flags']
                            if f['type'] in ('graphic_cut', 'orphaned_heading'))
    assert before, 'the pre-fix heading list should cut a material chart across a page'
    assert after == [], after
