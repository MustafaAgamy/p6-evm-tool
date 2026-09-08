"""Schedule (Gantt) Excel export — p6_evm.schedule_excel.schedule_excel + write_sections_xlsx.

Validates the workbook by unzipping + XML-parsing (no openpyxl dependency), the same way
test_evm_excel does. Asserts: a valid .xlsx zip, the expected 'Schedule' sheet, the summary
+ per-WBS-group section titles present, group ordering by earliest start, % Complete written
as a numeric cell, and the empty-result 'No data' fallback that never crashes.
"""
import zipfile
import xml.dom.minidom as minidom

from p6_evm.schedule_excel import schedule_excel
from p6_evm.xlsx_writer import write_sections_xlsx


def _result():
    """A representative parse result in the shape the client posts — mirrors the slim
    `activities` list _handle_parse() attaches. 'Construction' starts before 'Engineering'."""
    return {
        'project_name': 'Test Project',
        'data_date': '2026-02-09',
        'activity_count': 4,
        'activities': [
            {'id': 'ENG-010', 'name': 'IFC Drawings', 'wbs': 'Project > Engineering',
             'wbs_top': 'Engineering', 'start': '2026-03-01', 'finish': '2026-05-30',
             'pct': 40, 'critical': False, 'milestone': False},
            {'id': 'CON-010', 'name': 'Excavation', 'wbs': 'Project > Construction',
             'wbs_top': 'Construction', 'start': '2026-01-05', 'finish': '2026-02-20',
             'pct': 75, 'critical': True, 'milestone': False},
            {'id': 'CON-020', 'name': 'Foundations', 'wbs': 'Project > Construction',
             'wbs_top': 'Construction', 'start': '2026-02-21', 'finish': '2026-04-10',
             'pct': 10, 'critical': True, 'milestone': False},
            {'id': 'MS-100', 'name': 'Substantial Completion', 'wbs': 'Project > Construction',
             'wbs_top': 'Construction', 'start': '2026-06-30', 'finish': '2026-06-30',
             'pct': 0, 'critical': True, 'milestone': True},
        ],
    }


def _sheet_names(z):
    wb = minidom.parseString(z.read('xl/workbook.xml'))
    return [s.getAttribute('name') for s in wb.getElementsByTagName('sheet')]


def test_schedule_excel_writes_valid_workbook_mirroring_wbs_groups(tmp_path):
    sheets = schedule_excel(_result())
    assert [s['name'] for s in sheets] == ['Schedule']

    titles = [b['title'] for b in sheets[0]['blocks']]
    # Summary first, then WBS groups ordered by earliest start (Construction 05-Jan
    # before Engineering 01-Mar).
    assert titles == ['Schedule (Gantt)', 'Construction', 'Engineering']

    out = tmp_path / 'schedule.xlsx'
    write_sections_xlsx(str(out), sheets)

    assert zipfile.is_zipfile(str(out))
    with zipfile.ZipFile(str(out)) as z:
        names = z.namelist()
        assert '[Content_Types].xml' in names
        assert 'xl/workbook.xml' in names
        assert 'xl/worksheets/sheet1.xml' in names
        assert _sheet_names(z) == ['Schedule']

        body = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        for title in titles:
            assert title in body
        assert 'Activity ID' in body and 'Substantial Completion' in body
        # % Complete kept NUMERIC (not a formatted string).
        assert '<v>75</v>' in body
        # Activity count numeric in the summary block.
        assert '<v>4</v>' in body


def test_schedule_excel_empty_result_yields_no_data_and_never_crashes(tmp_path):
    for empty in ({}, None, {'activities': []}, {'activity_count': 12, 'activities': []}):
        sheets = schedule_excel(empty)
        assert len(sheets) == 1
        assert sheets[0]['name'] == 'Schedule'
        out = tmp_path / 'empty.xlsx'
        write_sections_xlsx(str(out), sheets)
        assert zipfile.is_zipfile(str(out))
        with zipfile.ZipFile(str(out)) as z:
            body = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
            assert 'No data' in body
