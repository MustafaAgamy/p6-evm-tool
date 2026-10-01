"""Reporting Studio PDF page flow (owner point 14 — findings STUDIO-PDF-4 and STUDIO-PDF-5).

STUDIO-PDF-5: the "Key indicators" group put all ten KPI cards in ONE row — the values
wrapped ("09 / Feb / 2027") and the last card was cut by the page frame. Cards now go in
balanced rows of at most five with a value font that fits the longest value on one line.

STUDIO-PDF-4: every numbered Studio item was ``page-break-inside:avoid`` as a whole, so an
item of more than a third of a page that did not fit under the previous one was pushed
WHOLE to the next page, leaving the page above it half blank (GBT: "Progress by category"
left page 4 57 % blank, "Scope Weight & Recommendation" page 61). In print an item now
flows like any other long block — kept whole only when small (the composer's measure) —
while its heading still travels with its first block. The page checker also learnt the
two blanks a Studio document has BY DESIGN: the cover page and the end of the contents
(the numbered items start on a fresh page), reported as information, not defects.
"""
import os
import re
import tempfile

import pytest

from p6_special import payloads as P
from p6_special import render_html

GBT_KPIS = [('SPI · schedule', '—'), ('Forecast finish', '09 Feb 2027'), ('Delay', '0 d'),
            ('Baseline finish', '—'), ('Overall planned', '0.00%'), ('Overall actual', '0.00%'),
            ('Planned value', '0'), ('Earned value', '0'), ('Actual cost', '0'), ('CPI · cost', '—')]


def _kpis(pairs=GBT_KPIS):
    return P.kpi_group([P.kpi(label, value) for label, value in pairs])


def _card_rows(html):
    rows = re.findall(r'<tr>(.*?)</tr>', html, flags=re.S)
    return [r.count('border-radius:8px') for r in rows if 'border-radius:8px' in r]


# ── STUDIO-PDF-5 · KPI cards in rows ─────────────────────────────────────────────
def test_ten_kpi_cards_are_laid_out_in_balanced_rows_of_at_most_five():
    html = render_html._kpi_group(_kpis(), render_html._Colors('light'))
    rows = _card_rows(html)
    assert sum(rows) == 10 and len(rows) >= 2, rows
    assert max(rows) <= 5 and max(rows) - min(rows) <= 1, rows
    labels = re.findall(r'text-transform:uppercase;[^"]*">([^<]+)<', html)
    assert labels == [render_html._esc(l) for l, _ in GBT_KPIS]            # order kept


def test_kpi_value_font_fits_the_longest_value_on_one_line():
    sizes, fs = render_html._kpi_layout([v for _, v in GBT_KPIS])
    cols = max(sizes)
    inner = (render_html._KPI_ROW_PX - render_html._KPI_GAP_PX * (cols - 1)) / cols \
        - render_html._KPI_PAD_PX
    assert fs >= render_html._KPI_FONT_PX[1]
    assert render_html._text_em('09 Feb 2027') * fs <= inner


def test_a_few_short_kpis_stay_one_row_at_full_size():
    sizes, fs = render_html._kpi_layout(['0.94', '1.02', '12 d', '61%'])
    assert sizes == [4] and fs == render_html._KPI_FONT_PX[0]
    html = render_html._kpi_group(_kpis([('SPI', '0.94'), ('CPI', '1.02')]), render_html._Colors('light'))
    assert _card_rows(html) == [2] and 'font-size:26px;font-weight:800' in html


# ── Chrome proof ─────────────────────────────────────────────────────────────────
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


def _item(iid, title, payload, ftitle='Overview'):
    return {'id': iid, 'title': title, 'feature': iid.split(':')[0], 'feature_title': ftitle,
            'ctype': 'section', 'payload': payload}


_META = {'project_name': 'Grain Bulk Terminal Detailed Schedule - Phase I REV.03',
         'data_date': '2025-12-11'}


def _doc(rendered):
    return render_html.build_document('Monthly Progress Report', _META, rendered, 'light')


def _lines(pdf):
    import pymupdf
    out = []
    with pymupdf.open(pdf) as d:
        for no, pg in enumerate(d, 1):
            for b in pg.get_text('dict')['blocks']:
                for l in b.get('lines', []):
                    t = ''.join(s['text'] for s in l['spans']).strip()
                    if t:
                        out.append((no, t, l['bbox'], pg.rect.width))
    return out


def test_chrome_key_indicators_print_every_value_whole_inside_the_frame(monkeypatch):
    chrome = _chrome()
    rendered = [_item('overview:kpis', 'Key indicators', _kpis())]
    with tempfile.TemporaryDirectory() as folder:
        after = _lines(_print(_doc(rendered), chrome, folder, 'after'))
        # the pre-fix layout: every card in one row at the full 26 px value font
        monkeypatch.setattr(render_html, '_kpi_layout', lambda vals: ([len(vals)], 26))
        before = _lines(_print(_doc(rendered), chrome, folder, 'before'))
    frame_in = 14 * 72 / 25.4 + 6                # page margin + the inner frame line

    def value_whole(lines):
        return any(t == '09 Feb 2027' for _, t, _, _ in lines)

    def inside(lines):
        cpi = [(bb, w) for _, t, bb, w in lines if t.upper().startswith('CPI')]
        return bool(cpi) and all(bb[2] <= w - frame_in for bb, w in cpi)
    assert not value_whole(before) or not inside(before)             # the defect, reproduced
    assert value_whole(after), [t for _, t, _, _ in after if '20' in t or 'Feb' in t]
    assert inside(after)


def _bars(n):
    series = [{'label': 'Planned', 'tone': 'neutral'}, {'label': 'Actual', 'tone': 'accent'}]
    rows = [{'label': f'Phase {i} Construction Works ({i * 7} activities)', 'values': [40 + i, 30 + i]}
            for i in range(1, n + 1)]
    return P.bars(rows, series)


_WORDS = ('pile caps ground beams released site planned baseline programme civil works silos '
          'area steady progress period conveyor towers quay pedestals steel structure mechanical '
          'erection insulation soil replacement elevated raft columns slab finishing handover').split()


def _para(i):
    # every line of text different (the checker sets repeated rows aside as page furniture)
    return ' '.join(_WORDS[(i * 5 + k * 3) % len(_WORDS)] for k in range(38)).capitalize() + '.'


def _paras(n, start=0):
    return [_para(start + i) for i in range(n)]


def _flow_doc():
    # long enough that the running footer sits at the page bottom on most pages (the
    # checker sets page furniture aside by its repeated place)
    return _doc([
        _item('overview:snapshot', 'Project snapshot', P.text(_paras(7))),
        _item('overview:categories', 'Progress by category', _bars(12)),
    ] + [_item(f'overview:notes{i}', f'Notes part {i}', P.text(_paras(22, 30 * i))) for i in range(1, 5)])


def _pre_fix_flow(html):
    """The same document without the print rule that lets a numbered item flow."""
    rule = render_html._SECTION_FLOW_CSS
    assert html.count(rule) == 1
    return html.replace(rule, '')


def test_chrome_mid_size_item_continues_instead_of_leaving_the_page_half_blank():
    chrome = _chrome()
    from p6_export import pagination_check as pc
    html = _flow_doc()
    with tempfile.TemporaryDirectory() as folder:
        after_pdf = _print(html, chrome, folder, 'after')
        before_pdf = _print(_pre_fix_flow(html), chrome, folder, 'before')
        after, before = pc.check_pdf(after_pdf), pc.check_pdf(before_pdf)
        a_lines, b_lines = _lines(after_pdf), _lines(before_pdf)

    def page_of(lines, text):
        return [no for no, t, _, _ in lines if t == text]
    # BEFORE: "Progress by category" was pushed whole under a half-blank page
    assert any(f['type'] == 'large_blank_then_continuation' for f in before['flags']), before
    assert page_of(b_lines, 'Progress by category') != page_of(b_lines, 'Project snapshot')
    # AFTER: it starts under the snapshot and continues; its heading keeps its first category
    head = page_of(a_lines, 'Progress by category')
    assert head and head == page_of(a_lines, 'Project snapshot')[-1:], (head, a_lines[:5])
    assert head[0] in page_of(a_lines, 'Phase 1 Construction Works (7 activities)')
    assert after['flags'] == [], after['flags']


def test_chrome_cover_and_end_of_contents_are_by_design_breaks_not_defects():
    """A Studio document with a two-page contents list: the cover page (vertically centred)
    and the last contents page end early BY DESIGN — the checker reports them as
    information; a pushed block on a body page is still a defect (previous test)."""
    chrome = _chrome()
    from p6_export import pagination_check as pc
    # distinct titles (a title repeated at the same place on many pages reads as a running
    # header to the checker)
    items = [_item(f'x:{i}', f'{_WORDS[i % len(_WORDS)].title()} {_WORDS[(i * 7) % len(_WORDS)]} '
                   f'{"review" if i % 2 else "summary"}', P.text(_paras(1, i)))
             for i in range(1, 41)]
    with tempfile.TemporaryDirectory() as folder:
        res = pc.check_pdf(_print(_doc(items), chrome, folder, 'toc'))
    assert res['flags'] == [], res['flags']
    pages = {f['page'] for f in res['info']}
    assert 1 in pages, res['info']                                     # the cover
    assert any('contents' in f['detail'] for f in res['info']), res['info']


def test_health_score_list_prints_whole_and_compact_inside_a_studio_item():
    """GBT: the reused Schedule Health summary's score list (a div grid - it cannot repeat
    its header on a new page) split 10 + 1 rows once Studio items could flow; it is kept
    whole (``rpt-keep``), and inside a Studio item its print rhythm is tighter so moving it
    whole never leaves a large blank. The standalone Health PDF keeps its own rhythm."""
    from p6_audit.report import render_summary_report
    subs = [{'name': f'Check {i}', 'status': 'Pass', 'score': 95.0, 'weight': 10, 'points': 9.5}
            for i in range(10)]
    html = render_summary_report({'score': 96.6, 'grade': 'A', 'sub_features': subs,
                                  'weight_covered': 85}, {'project_name': 'Synthetic'})
    assert '<div class="comp rpt-keep">' in html
    assert '.sr-sec .comp .crow' not in html                     # standalone rhythm unchanged
    doc = _doc([_item('overview:snapshot', 'Project snapshot', P.text(_paras(1)))])
    assert '.sr-sec .comp .crow{padding-top:4px;padding-bottom:4px;}' in doc
