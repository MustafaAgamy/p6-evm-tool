"""wbs_excel — the Project ▸ WBS workbook: one sheet 'WBS' with the indented WBS
table, one titled block per selectable main branch (mirroring the on-screen view).
Validated by unzipping + XML-parsing the produced .xlsx (no openpyxl dependency),
matching the shape of test_calendar_xlsx / test_evm_excel."""
import zipfile
import xml.dom.minidom as minidom

from p6_evm.wbs_excel import wbs_excel
from p6_evm.xlsx_writer import write_sections_xlsx


def _report():
    """Representative WBS result the client holds: a single root 'Project' whose two
    activity-bearing children (Engineering, Construction) are the selectable mains,
    each with a leaf beneath — exactly the pre-order shape server.py emits."""
    return {
        'project_name': 'New Plant',
        'data_date': '2026-02-09',
        'wbs_main': [
            {'id': 'W-ENG', 'name': 'Engineering'},
            {'id': 'W-CON', 'name': 'Construction'},
        ],
        'wbs_summary': [
            {'id': 'W-ENG', 'parent': None, 'name': 'Engineering', 'depth': 0,
             'activities': 12, 'planned': 80.0, 'actual': 62.5,
             'start': '2025-06-01', 'finish': '2026-01-15',
             'baseline_start': '2025-06-01', 'baseline_finish': '2025-12-31', 'leaf': False},
            {'id': 'W-ENG-D', 'parent': 'W-ENG', 'name': 'Detailed Design', 'depth': 1,
             'activities': 12, 'planned': 80.0, 'actual': 62.5,
             'start': '2025-06-01', 'finish': '2026-01-15',
             'baseline_start': '2025-06-01', 'baseline_finish': '2025-12-31', 'leaf': True},
            {'id': 'W-CON', 'parent': None, 'name': 'Construction', 'depth': 0,
             'activities': 40, 'planned': 45.0, 'actual': 40.0,
             'start': '2025-09-01', 'finish': '2026-11-30',
             'baseline_start': '2025-09-01', 'baseline_finish': '2026-10-01', 'leaf': True},
        ],
    }


def _read_sheets(path):
    """Return (namelist, workbook.xml, list-of-inline-strings, open ZipFile).

    The writer uses INLINE strings (no sharedStrings.xml), so pull every
    <is><t> text run out of sheet1.xml — leading indentation is preserved via
    xml:space="preserve"."""
    z = zipfile.ZipFile(path)
    names = z.namelist()
    wb = z.read('xl/workbook.xml').decode('utf-8')
    strings = []
    dom = minidom.parseString(z.read('xl/worksheets/sheet1.xml'))
    for is_el in dom.getElementsByTagName('is'):
        strings.append(''.join(t.firstChild.data if t.firstChild else ''
                               for t in is_el.getElementsByTagName('t')))
    return names, wb, strings, z


def test_valid_xlsx_with_expected_sheet_titles_and_numeric_cell(tmp_path):
    out = tmp_path / 'wbs.xlsx'
    sheets = wbs_excel(_report())
    assert [s['name'] for s in sheets] == ['WBS']
    write_sections_xlsx(str(out), sheets)

    # 1) a real, openable .xlsx zip with the core parts
    assert zipfile.is_zipfile(str(out))
    names, wb, shared, z = _read_sheets(str(out))
    for part in ('[Content_Types].xml', 'xl/workbook.xml', 'xl/worksheets/sheet1.xml'):
        assert part in names
    with zipfile.ZipFile(str(out)) as zz:
        assert zz.testzip() is None            # no corrupt members

    # 2) the sheet is named 'WBS'
    assert '<name val="WBS"' in wb or 'name="WBS"' in wb.replace('val=', '="')
    assert 'WBS' in wb

    # 3) both main-branch block titles present (mirrors the segmented control)
    joined = '\n'.join(shared)
    assert 'WBS Summary — Engineering' in joined
    assert 'WBS Summary — Construction' in joined
    # indented child name carried its leading spaces
    assert any(s.strip() == 'Detailed Design' and s != 'Detailed Design' for s in shared)
    # headers present
    assert 'Planned %' in shared and 'Delay (days)' in shared

    # 4) a numeric percent cell (80.0) is written as a number, not text
    sheet_xml = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
    z.close()
    import re
    # numeric cells have no t="s"/t="inlineStr"; assert 80 appears as a bare <v>
    assert re.search(r'<v>80(\.0+)?</v>', sheet_xml), 'expected numeric planned % cell'
    # Delay for Construction = 2026-11-30 − 2026-10-01 = 60 days, numeric
    assert re.search(r'<v>60</v>', sheet_xml), 'expected numeric delay cell (60 days)'


def test_empty_data_returns_no_data_sheet_never_crashes(tmp_path):
    out = tmp_path / 'empty.xlsx'
    sheets = wbs_excel({'wbs_summary': [], 'wbs_main': []})
    assert [s['name'] for s in sheets] == ['WBS']
    write_sections_xlsx(str(out), sheets)
    assert zipfile.is_zipfile(str(out))
    _, _, shared, z = _read_sheets(str(out))
    z.close()
    assert any('No data' in s for s in shared)

    # None / missing keys must not raise either
    for bad in (None, {}, {'wbs_summary': None}):
        s2 = wbs_excel(bad)
        assert s2 and s2[0]['name'] == 'WBS'


def test_no_mains_falls_back_to_full_tree(tmp_path):
    out = tmp_path / 'flat.xlsx'
    rep = _report()
    rep['wbs_main'] = []                       # single flat branch, no distinct mains
    sheets = wbs_excel(rep)
    write_sections_xlsx(str(out), sheets)
    _, _, shared, z = _read_sheets(str(out))
    z.close()
    assert any(s == 'WBS Summary' for s in shared)   # one whole-tree block
