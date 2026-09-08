"""Professional Dashboard Excel export — p6_evm.dashboard_excel.dashboard_excel +
write_sections_xlsx.

Validates the workbook by unzipping + XML-parsing (no openpyxl dependency), the same way
test_evm_excel / test_calendar_xlsx do. Asserts: a valid .xlsx zip, the expected sheets,
each section title present, a numeric metric cell, and the empty-read-model 'No data'
fallback (never crashes).
"""
import zipfile
import xml.dom.minidom as minidom

from p6_evm.dashboard_excel import dashboard_excel
from p6_evm.xlsx_writer import write_sections_xlsx


def _dashboard():
    """A representative dashboard read-model in the shape /api/dashboard returns."""
    return {
        'ok': True,
        'portfolio': [
            {'project_id': 1, 'name': 'Riyadh Metro', 'snapshot_id': 9,
             'data_date': '2026-02-09', 'imported_at': '2026-02-10 08:00:00',
             'activity_count': 6610, 'snapshot_count': 3,
             'spi': 0.90, 'cpi': 1.02, 'delay_days': 12,
             'overall_planned_pct': 0.50, 'overall_actual_pct': 0.45,
             'pv': 243805397, 'ev': 210000000, 'ac': 205000000},
            {'project_id': 2, 'name': 'Coastal Terminal', 'snapshot_id': 4,
             'data_date': '2026-01-31', 'imported_at': '2026-02-01 09:00:00',
             'activity_count': 1200, 'snapshot_count': 1,
             'spi': 1.05, 'cpi': 0.98, 'delay_days': -3,
             'overall_planned_pct': 0.30, 'overall_actual_pct': 0.33,
             'pv': 50000000, 'ev': 52000000, 'ac': 53000000},
        ],
        'active': {
            'project_id': 1, 'name': 'Riyadh Metro',
            'trend': [
                {'id': 5, 'data_date': '2026-01-12', 'spi': 0.97, 'cpi': 1.00,
                 'delay_days': 4, 'overall_planned_pct': 0.30, 'overall_actual_pct': 0.29},
                {'id': 7, 'data_date': '2026-01-26', 'spi': 0.94, 'cpi': 1.01,
                 'delay_days': 8, 'overall_planned_pct': 0.40, 'overall_actual_pct': 0.37},
                {'id': 9, 'data_date': '2026-02-09', 'spi': 0.90, 'cpi': 1.02,
                 'delay_days': 12, 'overall_planned_pct': 0.50, 'overall_actual_pct': 0.45},
            ],
        },
    }


def _sheet_names(z):
    wb = minidom.parseString(z.read('xl/workbook.xml'))
    return [s.getAttribute('name') for s in wb.getElementsByTagName('sheet')]


def test_dashboard_excel_writes_valid_workbook_with_sections(tmp_path):
    sheets = dashboard_excel(_dashboard())
    assert [s['name'] for s in sheets] == ['Portfolio', 'Trend']
    assert [b['title'] for b in sheets[0]['blocks']] == [
        'Portfolio Summary', 'Portfolio — latest update per project']
    assert [b['title'] for b in sheets[1]['blocks']] == ['Trend — Riyadh Metro']

    out = tmp_path / 'dashboard.xlsx'
    write_sections_xlsx(str(out), sheets)

    assert zipfile.is_zipfile(str(out))
    with zipfile.ZipFile(str(out)) as z:
        names = z.namelist()
        assert '[Content_Types].xml' in names
        assert 'xl/workbook.xml' in names
        assert 'xl/worksheets/sheet1.xml' in names
        assert 'xl/worksheets/sheet2.xml' in names          # both sheets emitted

        assert _sheet_names(z) == ['Portfolio', 'Trend']

        portfolio = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        assert 'Portfolio Summary' in portfolio
        assert 'Portfolio &#8212; latest update per project' in portfolio \
            or 'Portfolio — latest update per project' in portfolio
        assert 'Riyadh Metro' in portfolio
        assert 'On track' in portfolio and 'Behind' in portfolio
        # SPI kept as a NUMERIC cell (0.9) and delay as a numeric int (12).
        assert '<v>0.9</v>' in portfolio
        assert '<v>12</v>' in portfolio
        # Two projects → Projects count numeric.
        assert '<v>2</v>' in portfolio

        trend = z.read('xl/worksheets/sheet2.xml').decode('utf-8')
        assert 'Trend' in trend
        assert '<v>0.94</v>' in trend                        # a mid-snapshot SPI, numeric


def test_dashboard_excel_empty_yields_no_data_and_never_crashes(tmp_path):
    for empty in ({}, None, {'ok': True, 'portfolio': [], 'active': None},
                  {'portfolio': [], 'active': {'name': 'X', 'trend': []}}):
        sheets = dashboard_excel(empty)
        # No active-with-snapshots → only the Portfolio sheet.
        assert [s['name'] for s in sheets] == ['Portfolio']
        out = tmp_path / 'empty.xlsx'
        write_sections_xlsx(str(out), sheets)
        assert zipfile.is_zipfile(str(out))
        with zipfile.ZipFile(str(out)) as z:
            body = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
            assert 'No data' in body
