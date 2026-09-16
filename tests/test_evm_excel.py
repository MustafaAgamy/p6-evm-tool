"""Earned Value (EVM) Excel export — p6_evm.evm_excel.evm_excel + write_sections_xlsx.

Validates the workbook by unzipping + XML-parsing (no openpyxl dependency), the same way
test_calendar_xlsx does. Asserts: a valid .xlsx zip, the expected sheets, each core section
title present, numbers written as numeric cells, and the empty-report 'No data' fallback.
"""
import zipfile
import xml.dom.minidom as minidom

from p6_evm.evm_excel import evm_excel
from p6_evm.xlsx_writer import write_sections_xlsx


def _report():
    """A representative EVM report dict in the shape the client posts."""
    return {
        'result': {
            'categories': {
                'Construction': {'weight': 0.60, 'planned_pct': 0.50, 'actual_pct': 0.45},
                'Engineering': {'weight': 0.25, 'planned_pct': 0.80, 'actual_pct': 0.70},
                'Design': {'weight': 0.15, 'planned_pct': 0.90, 'actual_pct': 0.85},
                'Milestones': {'weight': 0.0, 'planned_pct': 0.0, 'actual_pct': 0.0},
            },
            'pv': 243805397, 'ev': 210000000, 'ac': 205000000,
            'spi': 0.90, 'cpi': 1.02, 'delay_days': 12,
        },
        'weights': {},               # no user override → use auto weights
        'actual_cost': None,         # → use P6 result.ac
        'meta': {
            'project_name': 'Test Project', 'data_date': '2026-02-09',
            'report_date': '09 Sep 2026', 'source_file': 'test.xml',
            'baseline_finish': '2027-06-30', 'expected_finish': '2027-07-15',
        },
        'gap': {
            'dimension': 'Discipline', 'total_gap': 33805397,
            'groups': [{'code': 'CIV', 'pv': 100000000, 'ev': 80000000,
                        'gap': 20000000, 'pct_of_gap': 59.2}],
        },
        'engineering': {
            'mode': 'E1',
            'rows': [{'trade': 'Civil', 'submittal_type': 'Shop', 'req': 10, 'planned': 8,
                      'submitted_rows': 7, 'approved_rows': 5, 'not_approved_rows': 1,
                      'under_review_rows': 1, 'planned_pct': 80, 'submitted_pct': 60,
                      'approved_pct': 50}],
            'overall': {'design': {}, 'engineering': {}},
            'by_trade': [{'trade': 'Civil', 'req': 10, 'submitted_rows': 7, 'approved_rows': 5,
                          'not_approved_rows': 1, 'submitted_pct': 60, 'approved_pct': 50}],
            'gaps': {'design': [],
                     'engineering': [{'trade': 'Civil', 'planned': 8, 'approved': 5,
                                      'gap': 3, 'pct_of_gap': 100}]},
        },
    }


def _sheet_names(z):
    wb = minidom.parseString(z.read('xl/workbook.xml'))
    return [s.getAttribute('name') for s in wb.getElementsByTagName('sheet')]


def test_evm_excel_writes_valid_workbook_with_report_sections(tmp_path):
    sheets = evm_excel(_report())
    # Core EVM sheet plus the two data-driven add-on sheets.
    assert [s['name'] for s in sheets] == ['Earned Value', 'Engineering', 'PV-EV Gap']
    core_titles = [b['title'] for b in sheets[0]['blocks']]
    assert core_titles == [
        'Project Progress — Planned vs Actual',
        'Executive Dashboard',
        'Planned Value vs Earned Value',
        'Category Weights & Overall Progress',
    ]

    out = tmp_path / 'evm.xlsx'
    write_sections_xlsx(str(out), sheets)

    assert zipfile.is_zipfile(str(out))
    with zipfile.ZipFile(str(out)) as z:
        names = z.namelist()
        assert '[Content_Types].xml' in names
        assert 'xl/workbook.xml' in names
        assert 'xl/worksheets/sheet1.xml' in names
        assert 'xl/worksheets/sheet3.xml' in names          # all three sheets emitted

        assert _sheet_names(z) == ['Earned Value', 'Engineering', 'PV-EV Gap']

        core = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        for title in core_titles:
            # minidom escapes '&' → '&amp;'; compare the escaped form.
            assert title.replace('&', '&amp;') in core
        # PV kept as a NUMERIC cell (not a formatted string) in the PV-vs-EV block.
        assert '<v>243805397</v>' in core

        gap = z.read('xl/worksheets/sheet3.xml').decode('utf-8')
        assert 'PV vs EV Gap Analysis' in gap


def test_evm_excel_empty_report_yields_no_data_and_never_crashes(tmp_path):
    for empty in ({}, None, {'result': {}}):
        sheets = evm_excel(empty)
        assert len(sheets) == 1
        assert sheets[0]['name'] == 'Earned Value'
        out = tmp_path / 'empty.xlsx'
        write_sections_xlsx(str(out), sheets)
        assert zipfile.is_zipfile(str(out))
        with zipfile.ZipFile(str(out)) as z:
            body = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
            assert 'No data' in body
