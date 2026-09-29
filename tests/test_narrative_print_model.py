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
