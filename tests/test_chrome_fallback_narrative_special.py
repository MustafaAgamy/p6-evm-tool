"""Audit TOOLING-1 (owner point 14 — pagination checker step).

The Baseline Narrative and Reporting Studio PDF / Word pipelines launched the ONE browser
``server._find_chrome()`` returned, with no fallback. That is the Playwright Chromium when
Playwright is importable — and a broken one (e.g. ``WinError 14001``: its side-by-side
manifest fails to load) then failed the whole export although a working Chrome / Edge was
installed. Only ``p6_export.pdf.run_chrome`` walked the other candidates.

These tests hand every narrative / Studio Chrome launcher a "browser" that cannot start and
prove the export still comes out (the next working Chromium prints it). Without the fix each
one raises / returns nothing.

The second half pins the checker's other tooling lessons from the same audit note: a module
report's page frame and Chrome's thousands of off-page drawing paths are not content, and a
table split is found from the row bands (not from PyMuPDF ``find_tables``, which reads the
page frame as one big table).
"""
import json
import os
import urllib.request

import pytest

pymupdf = pytest.importorskip('pymupdf')

_HTML = ('<!doctype html><html><head><meta charset="utf-8"><style>@page{size:A4;margin:12mm}'
         '</style></head><body><h2>Fallback proof</h2><p>The next working browser printed this '
         'page.</p></body></html>')


def _need_chromium():
    from p6_export.pdf import chrome_candidates
    if not chrome_candidates(None):
        pytest.skip('no Chromium installed')


@pytest.fixture
def broken_chrome(tmp_path):
    """A 'chrome.exe' that the OS refuses to start (OSError), like a broken Playwright build."""
    _need_chromium()
    p = tmp_path / 'broken-chromium' / 'chrome.exe'
    p.parent.mkdir()
    p.write_bytes(b'this is not a program')
    return str(p)


def _pdf_text(path):
    with pymupdf.open(path) as d:
        return ' '.join(pg.get_text() for pg in d)


# ── Reporting Studio ────────────────────────────────────────────────────────────
def test_studio_pdf_print_falls_back_past_a_browser_that_cannot_start(broken_chrome, tmp_path):
    from p6_special.pdf_render import chrome_pdf, render_document_pdf
    out = str(tmp_path / 'studio.pdf')
    chrome_pdf(_HTML, broken_chrome, out)
    assert 'Fallback proof' in _pdf_text(out)
    out2 = str(tmp_path / 'studio2.pdf')
    render_document_pdf(out2, lambda pages: _HTML, broken_chrome)
    assert 'Fallback proof' in _pdf_text(out2)


def test_studio_pdf_exact_word_print_falls_back(broken_chrome, tmp_path):
    from p6_special.docx_pdf import _html_to_pdf
    out = str(tmp_path / 'word-src.pdf')
    _html_to_pdf(_HTML, broken_chrome, out)
    assert 'Fallback proof' in _pdf_text(out)


def test_studio_word_section_pictures_fall_back(broken_chrome):
    from p6_special import docx_report as dr
    frag = '<div class="sec"><h3>Reused section</h3><p>' + 'Body text of the section. ' * 40 + '</p></div>'
    slices = dr._slice_section(frag, '', 'light', broken_chrome, 700.0, 700.0)
    assert slices, 'the Word section pictures must still be printed by the next Chromium'
    # comment 41: a slice is the page's own drawing (native Word shapes); a PNG only as fallback
    assert all(h > 0 and (vec or png[:8] == b'\x89PNG\r\n\x1a\n') for png, h, vec in slices)
    png = dr._rasterize_section(frag, '', 'light', broken_chrome)
    assert png and png[:8] == b'\x89PNG\r\n\x1a\n'


# ── Baseline Narrative ──────────────────────────────────────────────────────────
def test_narrative_word_chart_picture_falls_back(broken_chrome):
    from p6_narrative.chart_png import render_svg_png
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="120">'
           '<rect x="10" y="10" width="200" height="60" fill="#1F4E79"/></svg>')
    png = render_svg_png(svg, 300, 120, chrome=broken_chrome)
    assert png and png[:8] == b'\x89PNG\r\n\x1a\n', 'the chart must not fall back to a table'


def _doc():
    return {'meta': {'project_name': 'Synthetic Terminal', 'data_date': '11 Dec 2025'},
            'sections': [
                {'number': 1, 'title': 'Project Overview', 'kind': 'overview',
                 'payload': {'paragraphs': ['Fallback proof paragraph of the overview.'] * 3,
                             'breakdown': [], 'total': 0}},
                {'number': 2, 'title': 'Major Milestones', 'kind': 'ms_table',
                 'payload': {'columns': ['Milestone', 'Date'],
                             'rows': [['Milestone %02d' % i, '0%d-Jan-2027' % i] for i in range(1, 6)]}},
            ]}


def test_narrative_pdf_route_falls_back_past_a_browser_that_cannot_start(test_server, tmp_path,
                                                                         broken_chrome, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv, '_find_chrome', lambda: broken_chrome)
    out = str(tmp_path / 'narrative.pdf')
    req = urllib.request.Request(
        f'http://127.0.0.1:{test_server}/api/narrative/pdf',
        data=json.dumps({'doc': _doc(), 'output_path': out}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=300) as r:
        res = json.loads(r.read().decode('utf-8'))
    assert res.get('ok'), res
    txt = _pdf_text(out)
    assert 'Project Overview' in txt and 'Major Milestones' in txt


# ── checker tooling lessons (PyMuPDF on Chrome output) ──────────────────────────
def _framed_page(doc, rows, header=True):
    """A module-report sheet: a stroked page frame (find_tables reads it as ONE table),
    a title, a table of ``rows`` body rows, and 2 000 off-page drawing paths like Chrome
    emits (y down to -30 000)."""
    from p6_export import pagination_check  # noqa: F401  (import check)
    pg = doc.new_page(width=595, height=842)
    pg.draw_rect(pymupdf.Rect(20, 20, 575, 822), color=(0.12, 0.3, 0.47), width=1.2)
    sh = pg.new_shape()
    for i in range(2000):
        y = -30000 + i * 14
        sh.draw_rect(pymupdf.Rect(40, y, 300, y + 8))
    sh.finish(color=(0.2, 0.2, 0.2), fill=(0.8, 0.8, 0.8))
    sh.commit()
    return pg


def test_page_frame_and_off_page_paths_are_not_content(tmp_path):
    from p6_export import pagination_check as pc
    path = str(tmp_path / 'framed.pdf')
    doc = pymupdf.open()
    pg = _framed_page(doc, 0)
    pg.insert_text((40, 60), 'Schedule Health', fontsize=16, fontname='hebo')
    for k, y in enumerate(range(90, 780, 14)):
        pg.insert_text((40, y), f'Line {k} of the section body text, plain words only.', fontsize=10)
    doc.save(path)
    doc.close()
    pages = pc._read_pdf(path)
    assert len(pages) == 1
    assert not pages[0].draws, 'the frame and the off-page paths must be filtered out'
    res = pc.check_pdf(path)
    assert res['status'] == 'ok' and res['flags'] == []


def test_table_split_found_from_row_bands_inside_a_page_frame(tmp_path):
    """The split table is found although the whole sheet sits inside one stroked frame."""
    from p6_export import pagination_check as pc
    path = str(tmp_path / 'split.pdf')
    doc = pymupdf.open()
    cols = (40, 200, 400)

    def row(pg, y, a, b, c, bold=False):
        f = 'hebo' if bold else 'helv'
        for x, t in zip(cols, (a, b, c)):
            pg.insert_text((x, y), t, fontsize=10, fontname=f)
    p1 = _framed_page(doc, 0)
    p1.insert_text((40, 60), 'Delay register', fontsize=16, fontname='hebo')
    for k, y in enumerate(range(90, 720, 14)):
        p1.insert_text((40, y), f'Line {k} of the narrative before the table, plain words.', fontsize=10)
    p1.insert_text((40, 748), 'Activities behind plan', fontsize=13, fontname='hebo')
    row(p1, 770, 'Activity ID', 'Activity name', 'Duration', bold=True)
    for i in range(2):
        row(p1, 788 + i * 18, f'A-{i + 1}', f'Activity {i + 1}', f'{i + 3} d')
    p2 = _framed_page(doc, 0)
    row(p2, 60, 'Activity ID', 'Activity name', 'Duration', bold=True)
    for i in range(2, 14):
        row(p2, 78 + (i - 2) * 18, f'A-{i + 1}', f'Activity {i + 1}', f'{i + 3} d')
    doc.save(path)
    doc.close()
    res = pc.check_pdf(path)
    kinds = {f['type'] for f in res['flags']}
    assert 'table_split_few_rows' in kinds, res['flags']
