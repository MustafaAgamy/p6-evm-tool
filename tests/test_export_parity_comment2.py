"""Owner comment 2 — "Screen = PDF = Word = HTML = Excel — same data, same format and style."

The PDF and the HTML file are the previewed report itself.  Word and Excel are built from its
blocks, and a chart or a row of tiles made of styled ``<div>``s used to reach Word as loose lines
of text.  ``p6_export.auto_visuals.mark_visuals`` now marks every such block as a picture for
Word (drawn by Chrome — the same picture the PDF shows) and attaches its numbers for Excel; the
generic Word / Excel routes run it, so every report can offer all the outputs.
"""
import json
import re
import zipfile

from p6_export import html_model as HM
from p6_export.auto_visuals import mark_visuals
from tests.test_server import _post_json

TABLE = '<table><thead><tr><th>Activity ID</th><th>Float</th></tr></thead><tbody><tr><td>A1</td><td>3</td></tr></tbody></table>'
BARS = ('<div class="bars">'
        + ''.join(f'<div class="wrow"><div class="wname">Phase {c}</div><div class="wtrack"><div class="wfill" '
                  f'style="width:{p}%"></div></div><div class="wpct">{p}%</div></div>' for c, p in (('A', 95), ('B', 68)))
        + '</div>')
TILES = ('<div class="kpis"><div class="kpi"><div class="k">SPI</div><div class="v">0.66</div></div>'
         '<div class="kpi"><div class="k">Delay</div><div class="v">60 d</div></div></div>')


def _doc(body):
    return f'<html><head><style>.wfill{{background:#00f;height:8px}}</style></head><body>{body}</body></html>'


def _marks(html):
    """(tag, class) of every element marked as a picture, whatever the attribute order."""
    out = []
    for tag, attrs in re.findall(r"""<(\w+)((?:\s+[\w-]+(?:=(?:"[^"]*"|'[^']*'))?)*)\s*>""", html):
        if 'data-export="image"' in attrs:
            m = re.search(r'class="([^"]*)"', attrs)
            out.append((tag, m.group(1) if m else ''))
    return out


def test_designed_blocks_become_pictures_tables_and_text_stay():
    html = _doc(f'<div data-sec="scope"><h2>Scope</h2><p class="note">Share of the cost-loaded scope.</p>'
                f'{BARS}{TILES}{TABLE}<div class="concl">The plan is behind.</div></div>')
    out = mark_visuals(html)
    assert _marks(out) == [('div', 'bars'), ('div', 'kpis')]
    # nothing else changed: stripping the added attributes gives the report back
    plain = re.sub(r" data-export=\"image\" data-auto-visual=\"1\"(?: data-chart-headers='[^']*' data-chart-data='[^']*')?", '', out)
    assert plain == html
    for untouched in ('<table>', '<h2>Scope</h2>', '<p class="note">', '<div class="concl">'):
        assert untouched in out


def test_the_numbers_of_a_chart_travel_with_it_for_excel():
    out = mark_visuals(_doc(f'<div data-sec="scope"><h2>Scope</h2>{BARS}{TILES}</div>'))
    rep = HM.parse_report(out)
    visuals = [b for sec in rep.sections for b in sec.blocks if type(b).__name__ == 'Visual']
    assert len(visuals) == 2
    bars, tiles = visuals
    assert bars.data_headers == ['Item', 'Value'] and bars.data_rows == [['Phase A', '95%'], ['Phase B', '68%']]
    assert tiles.data_headers == ['Item', 'Value'] and tiles.data_rows == [['SPI', '0.66'], ['Delay', '60 d']]


def test_a_block_holding_a_table_is_opened_not_pictured():
    html = _doc(f'<div data-sec="s"><h2>S</h2><div class="card">{BARS}{TABLE}</div></div>')
    out = mark_visuals(html)
    assert _marks(out) == [('div', 'bars')]                 # the chart inside the card, never the table


def test_a_whole_card_section_is_one_picture_and_reaches_the_model_as_one_visual():
    html = _doc('<div class="top3"><div class="card3 gauge" data-sec="overview" data-parts="none">'
                '<div class="score-num">85.9</div><div class="verdict-badge" style="background:#0a0">Acceptable</div>'
                '</div></div>')
    out = mark_visuals(html)
    assert 'data-sec="overview" data-parts="none"' in out and out.count('data-export="image"') == 1
    rep = HM.parse_report(out)
    assert [s.key for s in rep.sections] == ['overview']
    assert [type(b).__name__ for b in rep.sections[0].blocks] == ['Visual']


def test_renderers_that_mark_their_own_exports_are_left_alone_and_it_never_raises():
    own = _doc(f'<div data-sec="a"><h2>A</h2><div class="chart" data-export="image">{BARS}</div>{TILES}</div>')
    assert mark_visuals(own) == own
    wrapped = _doc(f'<div data-sec="a"><h2>A</h2><div data-part="a.a1" style="display:contents"><h3>T</h3>{BARS}</div></div>')
    assert _marks(mark_visuals(wrapped)) == [('div', 'bars')]            # the block inside, not the wrapper
    for junk in (None, '', 5, '<div data-sec="x"><div class="chart"', 'no sections here'):
        assert mark_visuals(junk) == junk
    again = mark_visuals(_doc(f'<div data-sec="a"><h2>A</h2>{BARS}</div>'))
    assert mark_visuals(again) == again


def test_word_gets_a_picture_and_excel_gets_the_numbers_through_the_routes(test_server, tmp_path):
    html = _doc('<div class="head"><div class="title">Update Analysis</div></div>'
                f'<div data-sec="scope"><h2>Scope weight</h2>{BARS}{TABLE}</div>')
    docx, xlsx = tmp_path / 'r.docx', tmp_path / 'r.xlsx'
    meta = {'feature': 'Update Analysis', 'project': 'P'}
    _, d = _post_json(test_server, '/api/export/docx', {'html': html, 'output_path': str(docx), 'meta': meta})
    assert d['ok'], d
    with zipfile.ZipFile(docx) as z:
        media = [n for n in z.namelist() if n.startswith('word/media/')]
        body = z.read('word/document.xml').decode('utf-8')
    assert len(media) >= 1, 'the bar chart is a picture in Word'
    assert body.count('<w:tbl>') >= 1 and 'Activity ID' in body          # the table is a real Word table
    assert 'Phase A' not in re.sub(r'<w:tbl>.*?</w:tbl>', '', body, flags=re.S), 'chart labels are not loose text'

    _, d = _post_json(test_server, '/api/export/xlsx', {'html': html, 'output_path': str(xlsx), 'meta': meta})
    assert d['ok'], d
    with zipfile.ZipFile(xlsx) as z:
        text = ''.join(z.read(n).decode('utf-8') for n in z.namelist() if n.endswith('.xml'))
    for needle in ('Phase A', 'Phase B', 'Activity ID', 'A1'):          # (95% is stored as a number)
        assert needle in text, needle


def test_the_pdf_and_html_routes_do_not_touch_the_report(test_server, tmp_path):
    html = _doc(f'<div data-sec="scope"><h2>Scope weight</h2>{BARS}</div>')
    out = tmp_path / 'r.html'
    _, d = _post_json(test_server, '/api/export/html', {'html': html, 'output_path': str(out), 'title': 'T'})
    assert d['ok'], d
    saved = out.read_text(encoding='utf-8')
    assert 'data-auto-visual' not in saved and 'class="wfill"' in saved


def test_update_analysis_count_chart_is_one_block():
    from tests.test_report_parts_comment1 import _parts
    from tests.test_update_analysis import _parse_and_compute, _xml, build_report_from_data
    from p6_update.exporters import render_html
    from p6_export.auto_parts import annotate
    wbs = [(100, 'Proj', ''), (200, 'Silo 1', 100), (301, 'Soil Replacement', 200)]
    acts = [(20, 'S1', 'Soil a', 0.5, '2025-03-02', '2025-06-01', 320, 301, {'Discipline': 'Civil'}),
            (21, 'S2', 'Soil b', 0.3, '2025-03-02', '2025-06-01', 320, 301, {'Discipline': 'Civil'})]
    data, metrics = _parse_and_compute(_xml('2025-04-01', acts, [(20, 999)], wbs,
                                            [(999, 'MS', 'Project completion', '2025-06-01', 200)]))
    html = annotate(render_html(build_report_from_data(data, metrics)))
    assert '<section data-sec="counts" data-parts="none">' in html
    assert not [pid for pid, _lab in _parts(html) if pid.startswith('counts.')]
    assert json.dumps([pid for pid, _l in _parts(html)])               # the other sections keep their parts


def test_a_long_list_of_rows_stays_text_never_thousands_of_pictures():
    from p6_export import auto_visuals as AV
    rows = ''.join(f'<div class="chg"><span style="width:40%">A{i}</span><span style="width:60%">FS to SS</span></div>'
                   for i in range(AV.MAX_ITEMS + 40))
    html = _doc(f'<div data-sec="findings"><h2>Findings</h2><div class="list">{rows}</div>{BARS}</div>')
    out = mark_visuals(html)
    assert _marks(out) == [('div', 'bars')]                 # the chart is a picture; the long list is not
    big = _doc('<div data-sec="s"><h2>S</h2><div class="chart" style="width:100%">'
               + '<i style="width:1%"></i>' * (AV.MAX_HTML // 20) + '</div></div>')
    assert _marks(mark_visuals(big)) == []                  # an oversize block is never one giant picture


def test_screen_view_capture_document_overrides_the_app_print_rules():
    import inspect
    from p6_export import svg_raster
    src = inspect.getsource(svg_raster.chrome_raster)
    assert 'body>.__xcap{display:block!important}' in src
    assert 'height:auto!important' in src and 'overflow:visible!important' in src
