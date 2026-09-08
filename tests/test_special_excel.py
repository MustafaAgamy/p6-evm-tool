"""Special Report Excel export — p6_special.excel_export.special_sheets +
write_sections_xlsx.

Validates the workbook by unzipping + XML-parsing (no openpyxl), the same way
test_evm_excel / test_calendar_xlsx do. Asserts: a valid .xlsx zip, the cover +
one sheet per selected section in order, section titles present, numbers written
as numeric cells, best-effort extraction of a reused feature-report's data table
(with the bar-chart/layout table skipped), and the empty-selection 'No data'
fallback that never crashes.
"""
import zipfile
import xml.dom.minidom as minidom

from p6_special import payloads as P
from p6_special.excel_export import special_sheets, _TableExtractor, _qualify
from p6_evm.xlsx_writer import write_sections_xlsx


# A reused feature-report fragment: one real data table + a bar-chart table built
# the way render_html._bar_track does (nested spacer table → must be skipped).
_HTML_FRAG = (
    '<div class="srf-update">'
    '<table><thead><tr><th>Activity</th><th>Planned</th><th>Actual</th></tr></thead>'
    '<tbody>'
    '<tr><td>Excavation</td><td>80</td><td>72</td></tr>'
    '<tr><td>Concrete</td><td>50</td><td>55</td></tr>'
    '</tbody></table>'
    '<table cellpadding="0"><tr>'
    '<td width="60%" bgcolor="#2563eb">&nbsp;</td>'
    '<td bgcolor="#eee">&nbsp;</td>'
    '</tr></table>'
    '</div>'
)


def _rendered():
    """A representative rendered list — the same shape registry.render returns —
    exercising every payload kind Special Report emits."""
    return [
        {'id': 'evm:pv', 'title': 'Planned Value (PV)', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'kpi',
         'payload': P.kpi_group([P.kpi('Planned Value (PV)', 'EGP 243,805,397', tone='neutral')])},
        {'id': 'evm:planned_vs_actual', 'title': 'Planned % vs Actual % — overall',
         'feature': 'evm', 'feature_title': 'EVM Report', 'ctype': 'chart',
         'payload': P.bars(
             rows=[{'label': 'Overall progress', 'values': [50.0, 42.35],
                    'display': ['50%', '42.35%']}],
             series=[{'label': 'Planned', 'tone': 'neutral'},
                     {'label': 'Actual', 'tone': 'accent'}])},
        {'id': 'evm:category_table', 'title': 'Planned % vs Actual % — by category',
         'feature': 'evm', 'feature_title': 'EVM Report', 'ctype': 'table',
         'payload': P.table(
             columns=['Category', 'Weight', 'Planned %', 'Actual %'],
             rows=[['Construction', '60%', '50%', ('45%', 'bad')],
                   ['Engineering', '25%', '80%', ('70%', 'warn')]])},
        {'id': 'audit:findings', 'title': 'Schedule Audit findings',
         'feature': 'audit', 'feature_title': 'Schedule Health', 'ctype': 'findings',
         'payload': P.findings([
             {'severity': 'high', 'title': 'Open ends', 'detail': '3 activities'},
             {'severity': 'low', 'title': 'Lags', 'detail': '2 relationships'}])},
        {'id': 'update:full', 'title': 'Update Analysis — by activity',
         'feature': 'update', 'feature_title': 'Update Analysis', 'ctype': 'section',
         'payload': {'kind': 'html', 'feature': 'update', 'css': '', 'html': _HTML_FRAG}},
        {'id': 'x:missing', 'title': 'A result with no data',
         'feature': 'x', 'feature_title': 'X', 'ctype': 'kpi',
         'payload': {'kind': 'no_data', 'error': 'nothing computed'}},
    ]


def _sheet_names(z):
    wb = minidom.parseString(z.read('xl/workbook.xml'))
    return [s.getAttribute('name') for s in wb.getElementsByTagName('sheet')]


def test_table_extractor_keeps_data_table_skips_chart():
    ex = _TableExtractor()
    ex.feed(_HTML_FRAG)
    ex.close()
    # Two <table>s captured, but the chart/spacer table has < 2 substantive cells.
    qualified = [q for q in (_qualify(t) for t in ex.tables) if q]
    assert len(qualified) == 1
    headers, data = qualified[0]
    assert headers == ['Activity', 'Planned', 'Actual']
    assert data == [['Excavation', '80', '72'], ['Concrete', '50', '55']]


def test_special_sheets_mirrors_sections_and_writes_valid_workbook(tmp_path):
    rendered = _rendered()
    sheets = special_sheets(rendered, 'Weekly Progress — March',
                            meta={'project_name': 'Test Project', 'data_date': '2026-02-09 00:00:00'})

    # Cover sheet first, then one sheet per selected section, in order.
    assert sheets[0]['name'] == 'Report'
    assert len(sheets) == 1 + len(rendered)
    assert sheets[1]['name'].startswith('1. Planned Value')
    # The html section fans its extracted data table into a titled block.
    html_sheet = sheets[5]
    assert html_sheet['name'].startswith('5. Update Analysis')

    out = tmp_path / 'special.xlsx'
    write_sections_xlsx(str(out), sheets)

    assert zipfile.is_zipfile(str(out))
    with zipfile.ZipFile(str(out)) as z:
        names = z.namelist()
        assert '[Content_Types].xml' in names
        assert 'xl/workbook.xml' in names
        # cover + 6 sections = 7 worksheets
        assert 'xl/worksheets/sheet7.xml' in names

        sn = _sheet_names(z)
        assert sn[0] == 'Report'
        assert any(n.startswith('2. Planned % vs Actual') for n in sn)

        # bars section: numeric values stay NUMERIC cells (computable, not '42.35%').
        bars = z.read('xl/worksheets/sheet3.xml').decode('utf-8')   # sheet1=cover, sheet2=PV...
        assert '<v>42.35</v>' in bars

        # cover carries the report name + a numeric section count.
        cover = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        assert 'Weekly Progress' in cover
        assert '<v>6</v>' in cover

        # reused feature-report data table extracted into the update sheet.
        upd = z.read('xl/worksheets/sheet6.xml').decode('utf-8')
        assert 'Excavation' in upd
        assert '<v>72</v>' not in upd            # HTML-extracted cells stay text, not numeric

        # no_data section renders an honest line, does not crash.
        nod = z.read('xl/worksheets/sheet7.xml').decode('utf-8')
        assert 'No data available' in nod


def test_special_sheets_empty_selection_never_crashes(tmp_path):
    for rendered in ([], None):
        sheets = special_sheets(rendered, 'Empty', meta={})
        assert len(sheets) == 1
        assert sheets[0]['name'] == 'Report'
        out = tmp_path / 'empty.xlsx'
        write_sections_xlsx(str(out), sheets)
        assert zipfile.is_zipfile(str(out))
        with zipfile.ZipFile(str(out)) as z:
            body = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
            assert 'No results selected' in body
