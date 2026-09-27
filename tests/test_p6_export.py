"""p6_export — one-document exports (html_model · to_docx · to_xlsx · to_html · svg_raster).

Fixtures are REAL report HTML produced by the feature renderers (EVM + P6 Calendar Audit)
on synthetic data / tests/fixtures/minimal.xml — never client files.
"""
import io
import re
import zipfile
from datetime import datetime

import docx
import openpyxl
import pytest

from p6_calendar import calendar_audit
from p6_calendar.report import render_calendar_report
from p6_evm.evm_report import render_evm_report
from p6_evm.parser import parse_file
from p6_export import html_model as HM
from p6_export import svg_raster, to_docx, to_html, to_xlsx

RESULT = {
    'pv': 412.6e6, 'ev': 388.9e6, 'ac': 388.9e6, 'spi': 0.94, 'cpi': 1.11, 'delay_days': 18,
    'data_date': datetime(2025, 12, 11),
    'categories': {
        'Construction': {'weight': 0.95, 'planned_pct': 0.345, 'actual_pct': 0.324},
        'Design — Phase I': {'weight': 0.05, 'planned_pct': 0.80, 'actual_pct': 0.72},
    },
}
META = {'project_name': 'Grain Bulk Terminal', 'data_date': '11-Dec-2025',
        'report_date': '04-Aug-2026', 'source_file': 'gbt.xml'}
ENG = {'mode': 'P6', 'rows': [
    {'trade': 'Civil', 'submittal_type': 'Shop', 'req': 40, 'planned_sub': 30, 'actual_sub': 20,
     'planned_appr': 25, 'actual_appr': 12, 'actual_sub_pct': 50, 'actual_appr_pct': 30}]}
GAP = {'dimension': 'Area', 'total_gap': 23.7e6, 'groups': [
    {'code': 'Silo A', 'pv': 100e6, 'ev': 80e6, 'gap': 20e6, 'pct_of_gap': 84.4}]}


def evm_html(theme='light', **kw):
    return render_evm_report(RESULT, META, gap=kw.get('gap', GAP), engineering=kw.get('eng', ENG),
                             theme=theme)


@pytest.fixture(scope='module')
def cal_html(xml_path):
    ca = calendar_audit(parse_file(str(xml_path)), {}, {})
    return render_calendar_report(ca, {'project_name': 'Calendar Test', 'data_date': '2025-02-01',
                                       'report_date': '27 Sep 2026', 'source_file': 'minimal.xml'})


def _prune(html, part):
    """What the picker does client-side (report_parts.pruneHtml) for one unticked part."""
    m = re.search(r'<div data-part="%s"' % re.escape(part), html)
    assert m, part
    depth, i = 0, m.start()
    for t in re.finditer(r'<(/?)div\b[^>]*>', html[m.start():]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return html[:i] + html[m.start() + t.end():]
    raise AssertionError('unbalanced')


# ── html_model ──────────────────────────────────────────────────────────────
def test_model_sections_parts_and_meta_from_the_evm_report():
    rep = HM.parse_report(evm_html())
    assert [s.key for s in rep.sections] == ['progress', 'dashboard', 'value', 'category',
                                             'engineering', 'gap']
    assert rep.sections[0].title.startswith('Project Progress')
    assert rep.meta['project'] == 'Grain Bulk Terminal'
    assert rep.meta['data_date'] == '11-Dec-2025'
    assert rep.part_labels['category.table'] == 'Category weights table'
    kinds = {b.part: b.kind for s in rep.sections for b in s.blocks if b.part}
    assert kinds['progress.kpis'] == 'kpis'
    assert kinds['value.chart'] == 'visual'                 # data-export="image"
    assert kinds['category.table'] == 'table'
    vis = next(b for b in rep.all_blocks() if b.kind == 'visual' and b.part == 'value.chart')
    assert vis.data_headers == ['Measure', 'Value (EGP)']
    assert vis.data_rows[0] == ['Planned Value (PV)', 412600000.0]


def test_model_resolves_theme_tokens_to_concrete_colours_in_dark_mode():
    rep = HM.parse_report(evm_html('dark'))
    assert rep.bg == '131922'
    tbl = next(b for b in rep.all_blocks() if b.kind == 'table' and b.part == 'category.table')
    hdr = tbl.rows[0][0]
    assert hdr.header and re.fullmatch(r'[0-9A-F]{6}', hdr.bg)
    for b in rep.all_blocks():
        for r in getattr(b, 'runs', []) or []:
            assert r.color is None or re.fullmatch(r'[0-9A-F]{6}', r.color)


def test_headings_are_kept_with_their_content():
    rep = HM.parse_report(evm_html())
    for s in rep.sections:
        for b in s.blocks:
            if b.kind == 'heading':
                assert b.keep_with_next


# ── svg_raster ──────────────────────────────────────────────────────────────
SVG_REPORT = '''<html><head><style>
:root{--rpt-series-1:#1f77b4;--ink:#222}
.bar{fill:var(--rpt-series-1)} .lbl{fill:currentColor;font-size:12px} svg{color:#aa0000}
</style></head><body><div data-sec="s"><h2>Chart</h2>
<div data-part="s.chart" data-part-label="Bars"><svg viewBox="0 0 200 100" width="200" height="100">
<rect class="bar" x="10" y="10" width="80" height="60"/><text class="lbl" x="100" y="50">Label 42</text>
<linearGradient id="g"><stop offset="0" stop-color="var(--rpt-series-1)"/></linearGradient>
</svg></div></div></body></html>'''


def test_resolve_svg_makes_every_paint_concrete_and_restores_svg_case():
    rep = HM.parse_report(SVG_REPORT)
    v = next(b for b in rep.all_blocks() if b.kind == 'visual')
    assert v.svg and 'var(' not in v.svg and 'class=' not in v.svg
    assert 'viewBox="0 0 200 100"' in v.svg and '<linearGradient' in v.svg
    assert 'fill:#1f77b4' in v.svg                                # .bar via var()
    assert 'fill:#aa0000' in v.svg                                # currentColor
    assert v.title == 'Bars'


def test_svg_to_png_draws_the_resolved_colours():
    import pymupdf
    rep = HM.parse_report(SVG_REPORT)
    v = next(b for b in rep.all_blocks() if b.kind == 'visual')
    png = svg_raster.svg_to_png(v.svg, 200, scale=1.0)
    assert png and png[:8] == b'\x89PNG\r\n\x1a\n'
    pix = pymupdf.Pixmap(png)
    r, g, b = pix.pixel(40, 40)[:3]
    assert (abs(r - 0x1f) < 12 and abs(g - 0x77) < 12 and abs(b - 0xb4) < 12), (r, g, b)


def test_rasterize_without_chrome_leaves_css_charts_for_the_data_fallback():
    rep = HM.parse_report(evm_html())
    svg_raster.rasterize(rep, use_chrome=False)
    vis = [b for b in rep.all_blocks() if b.kind == 'visual']
    assert vis and all(v.png is None for v in vis)                # CSS charts need Chrome


# ── Word ────────────────────────────────────────────────────────────────────
def _docx(html, tmp_path, name='r.docx', **kw):
    out = tmp_path / name
    to_docx.html_to_docx(html, str(out), app_name='Controlyx', feature='Earned Value',
                         use_chrome=False, **kw)
    return out


def _xml(path, part='word/document.xml'):
    with zipfile.ZipFile(path) as z:
        return z.read(part).decode('utf-8')


def test_docx_carries_every_table_cell_and_heading(tmp_path):
    out = _docx(evm_html(), tmp_path)
    d = docx.Document(str(out))
    text = '\n'.join(p.text for p in d.paragraphs)
    cells = '\n'.join(c.text for t in d.tables for row in t.rows for c in row.cells)
    for h in ('Project Progress — Planned vs Actual', 'Executive Dashboard',
              'Category Weights & Overall Progress', 'PV vs EV Gap Analysis — by Area'):
        assert h in text
    for v in ('Construction', '95.0%', '34.5%', '32.77%', 'Overall', 'Silo A', 'Civil', '94%',
              'SPI · SCHEDULE'):
        assert v in cells, v
    # CSS chart without Chrome → the numbers behind it, as a table
    assert 'Planned Value (PV)' in cells and '412600000.0' in cells


def test_docx_is_word_ready_headers_colours_no_css_vars(tmp_path):
    out = _docx(evm_html('dark'), tmp_path)
    doc_xml = _xml(out)
    assert 'var(' not in doc_xml
    assert '<w:background w:color="131922"' in doc_xml             # dark page kept
    assert '<w:tblHeader' in doc_xml                               # header row repeats
    assert 'w:keepNext' in _xml(out, 'word/styles.xml') or 'w:keepNext' in doc_xml
    assert re.search(r'w:fill="[0-9A-F]{6}"', doc_xml)             # concrete cell shading
    headers = ''.join(_xml(out, n) for n in zipfile.ZipFile(out).namelist() if 'header' in n)
    footers = ''.join(_xml(out, n) for n in zipfile.ZipFile(out).namelist() if 'footer' in n)
    assert 'Controlyx — Earned Value · Grain Bulk Terminal' in headers
    assert 'PAGE' in footers and 'NUMPAGES' in footers
    assert 'displayBackgroundShape' in _xml(out, 'word/settings.xml')


def test_docx_page_follows_the_report_at_page(tmp_path):
    html = ('<html><head><style>@page{size:A4 landscape;margin:10mm}</style></head><body>'
            '<h1>Wide</h1><table><tr><th>A</th></tr><tr><td>1</td></tr></table></body></html>')
    d = docx.Document(str(_docx(html, tmp_path)))
    sec = d.sections[0]
    assert sec.page_width > sec.page_height


def test_docx_embeds_svg_charts_as_pictures(tmp_path):
    out = _docx(SVG_REPORT, tmp_path, name='svg.docx')
    names = zipfile.ZipFile(out).namelist()
    assert any(n.startswith('word/media/') and n.endswith('.png') for n in names)


def test_docx_unticked_part_is_absent(tmp_path):
    html = _prune(evm_html(), 'category.table')
    d = docx.Document(str(_docx(html, tmp_path)))
    cells = '\n'.join(c.text for t in d.tables for row in t.rows for c in row.cells)
    assert 'Construction' not in cells and 'WBS Category' not in cells
    assert 'Silo A' in cells


# ── Excel ───────────────────────────────────────────────────────────────────
def _xlsx(html, tmp_path, name='r.xlsx'):
    out = tmp_path / name
    to_xlsx.html_to_xlsx(html, str(out), app_name='Controlyx', feature='Earned Value')
    return openpyxl.load_workbook(str(out))


def _rows(ws):
    return [tuple(v for v in r if v is not None) for r in ws.iter_rows(values_only=True)
            if any(v is not None for v in r)]


def test_xlsx_one_sheet_per_section_with_header_block(tmp_path):
    wb = _xlsx(evm_html(), tmp_path)
    assert wb.sheetnames == ['Project Progress', 'Executive Dashboard',
                             'Planned Value vs Earned', 'Category Weights & Overall',
                             'Engineering Progress', 'PV vs EV Gap Analysis']
    assert all(len(n) <= 31 for n in wb.sheetnames)
    first = _rows(wb.worksheets[0])
    assert first[0] == ('Controlyx — Earned Value',)
    assert 'Project: Grain Bulk Terminal' in first[1][0] and 'Data date: 11-Dec-2025' in first[1][0]


def test_xlsx_tables_keep_numbers_numeric_with_the_same_look(tmp_path):
    wb = _xlsx(evm_html(), tmp_path)
    ws = wb['Category Weights & Overall']
    rows = _rows(ws)
    hdr = rows.index(('WBS Category', 'Weight %', 'Planned %', 'Actual %', 'Planned Weight %',
                      'Weighted Actual %'))
    con = rows[hdr + 1]
    assert con[0] == 'Construction' and con[1] == pytest.approx(0.95)
    cell = next(c for c in ws['B'] if c.value == pytest.approx(0.95))
    assert cell.number_format == '0.0%'
    tot = next(r for r in rows if r and r[0] == 'Overall')
    assert tot[-1] == pytest.approx(0.3438)


def test_xlsx_kpis_become_measure_value_blocks_and_charts_their_data(tmp_path):
    wb = _xlsx(evm_html(), tmp_path)
    dash = _rows(wb['Executive Dashboard'])
    assert ('Measure', 'Value', 'Note') in dash
    spi = next(r for r in dash if r[0] == 'SPI · Schedule')
    assert spi[1] == pytest.approx(0.94) and spi[2] == 'Behind Schedule'
    chart = _rows(wb['Planned Value vs Earned'])
    assert chart[0] == ('Planned Value vs Earned Value — bar chart',)
    assert ('Planned Value (PV)', 412600000) in chart


def test_xlsx_unticked_part_is_absent(tmp_path):
    wb = _xlsx(_prune(evm_html(), 'progress.chart'), tmp_path)
    flat = [v for ws in wb for r in _rows(ws) for v in r]
    assert 'Planned vs Actual — bar chart' not in flat
    assert 'Planned %' in flat                                     # the tiles part stays


def test_xlsx_typed_values():
    assert to_xlsx.typed('1,234').value == 1234
    assert to_xlsx.typed('−2.40%').value == pytest.approx(-0.024)
    assert to_xlsx.typed('11-Dec-2025').value == 46002
    assert to_xlsx.typed('007') == '007'
    assert to_xlsx.typed('412.6M') == '412.6M'
    assert to_xlsx.typed('18') == 18


def test_xlsx_calendar_sheets_and_month_data(tmp_path, cal_html):
    wb = _xlsx(cal_html, tmp_path, 'cal.xlsx')
    assert wb.sheetnames[:2] == ['Execution Dashboard', 'Calendar Timeline']
    tl = _rows(wb['Calendar Timeline'])
    assert ('Month', 'Net working days', 'Non-working days', 'Working hours') in tl
    assert any(r and r[0] == 'Month-by-month calendars' for r in tl)


# ── HTML ────────────────────────────────────────────────────────────────────
def test_standalone_html_is_self_contained_and_utf8(tmp_path):
    html = ('<html><head><link rel="stylesheet" href="https://x/y.css"><script>alert(1)</script>'
            '</head><body onload="x()"><h1>Delay — 18 days</h1><img src="https://x/a.png"></body></html>')
    out = tmp_path / 'r.html'
    to_html.write_html(html, str(out), title='EVM — report')
    txt = out.read_text(encoding='utf-8')
    assert txt.startswith('<!DOCTYPE html>')
    assert '<meta charset="utf-8">' in txt and '<title>EVM — report</title>' in txt
    assert '<script' not in txt and '<link' not in txt and 'https://x' not in txt and 'onload' not in txt
    assert 'Delay — 18 days' in txt


def test_standalone_html_keeps_the_report_unchanged(tmp_path):
    src = evm_html('sepia')
    out = to_html.standalone_html(src, 'EVM')
    assert out.count('<meta charset="utf-8">') == 1
    assert 'data-part="category.table"' in out and 'rpt-theme' in out
