"""Baseline Revision: a long list of logic changes reaches Word as a real table (final sweep,
comment 3 — the known limit noted under comment 2).

Up to 60 changed links Word draws each lane (Rev.00 / Rev.01 chains) as the PDF shows it.  Above
that the export cannot draw them all, and the lanes used to reach Word as thousands of loose
"■ · → ·" text lines.  Now the renderer hands the exports the same changes as one table, one
row per changed link; the screen, the PDF and the HTML file are unchanged.
"""
import zipfile
from collections import Counter

from tests.test_revcompare_engine import D, _act, _sched


def _html(n):
    from p6_revcompare import build_report_from_data
    from p6_revcompare.exporters import render_html
    a0 = [_act(f'A{i:04d}', f'Pour slab zone {i}', tf=i % 7, ps=D(2025, 3, 1), pf=D(2025, 4, 1)) for i in range(n)]
    r0 = [(f'A{i:04d}', f'A{i + 1:04d}', 'FS', 0) for i in range(n - 1)]
    r1 = [(f'A{i:04d}', f'A{i + 1:04d}', 'SS' if i % 2 else 'FS', i % 3) for i in range(n - 1)]
    rep = build_report_from_data(_sched(a0, r0, D(2025, 3, 1)), _sched(a0, r1, D(2025, 3, 1)), config={})
    return rep, render_html(rep, meta={'report_date': '02 Oct 2026'}, theme='light')


def _findings(html):
    from p6_export import html_model as HM
    from p6_export.auto_visuals import mark_visuals
    rep = HM.parse_report(mark_visuals(html))
    return [s for s in rep.sections if s.key == 'findings'][0]


def test_a_long_logic_list_becomes_one_table_in_word():
    rep, html = _html(300)
    n = len(rep['logic_register'])
    assert n > 60
    sec = _findings(html)
    kinds = Counter(b.kind for b in sec.blocks)
    tables = [b for b in sec.blocks if b.kind == 'table']
    assert len(tables) == 1 and len(tables[0].rows) == n + 1
    assert [c.text for c in tables[0].rows[0]] == ['#', 'Change', 'Rev.00 link', 'Rev.01 link', 'Predecessor',
                                                   'Successor', 'On critical path', 'WBS']
    first = [c.text for c in tables[0].rows[1]]
    assert first[0] == '1' and first[4].startswith('A0') and ' · Pour slab zone' in first[4]
    assert kinds['paragraph'] < 10, 'no loose text lines left'
    # the other designed blocks of the section are still drawn
    assert kinds['visual'] >= 1


def test_a_short_logic_list_is_still_drawn_as_the_pdf_shows_it():
    rep, html = _html(30)
    assert 0 < len(rep['logic_register']) <= 60
    assert 'data-export="table"' not in html
    assert not [b for b in _findings(html).blocks if b.kind == 'table']


def test_word_file_has_the_table(tmp_path):
    from p6_export.auto_visuals import mark_visuals
    from p6_export.to_docx import html_to_docx
    import docx
    rep, html = _html(120)
    out = tmp_path / 'rev.docx'
    html_to_docx(mark_visuals(html), str(out), app_name='Controlyx', feature='Baseline Revision',
                 use_chrome=False, sections=['findings'])
    d = docx.Document(str(out))
    t = [t for t in d.tables if t.rows[0].cells[0].text == '#' and t.rows[0].cells[2].text == 'Rev.00 link']
    assert t and len(t[0].rows) == len(rep['logic_register']) + 1
    assert '■' not in zipfile.ZipFile(out).read('word/document.xml').decode('utf-8')
