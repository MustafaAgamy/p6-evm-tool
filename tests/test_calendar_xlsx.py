"""write_calendar_xlsx — the Calendar Audit Excel export: a coloured timeline
grid (sheet 1) + the Monthly Statistics table (sheet 2). Validated by unzipping
and XML-parsing (no openpyxl dependency)."""
import zipfile
import xml.dom.minidom as minidom
from p6_evm.xlsx_writer import write_calendar_xlsx, write_xlsx


def _months():
    return [
        {'label': 'Feb 2025', 'first_weekday': 5, 'working_days': 18, 'holidays': 1,
         'exceptions': 1, 'working_hours': 144.0,
         'days': [{'d': d, 'status': ('holiday' if d == 20 else 'work')} for d in range(19, 29)]},
        {'label': 'Mar 2025', 'first_weekday': 5, 'working_days': 21, 'holidays': 0,
         'exceptions': 0, 'working_hours': 168.0,
         'days': [{'d': d, 'status': 'work'} for d in range(1, 32)]},
    ]


def test_calendar_xlsx_has_two_sheets_and_colours(tmp_path):
    p = tmp_path / 'cal.xlsx'
    write_calendar_xlsx(str(p), _months(), '5 Days/Week', 'from data date 19 Feb 2025')
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        assert 'xl/worksheets/sheet1.xml' in names   # Timeline
        assert 'xl/worksheets/sheet2.xml' in names   # Monthly Stats
        styles = z.read('xl/styles.xml').decode()
        assert 'FFDCFCE7' in styles and 'FFFEE2E2' in styles   # work + holiday fills
        s1 = z.read('xl/worksheets/sheet1.xml').decode()
        assert '5 Days/Week' in s1                    # title
        assert 'from data date 19 Feb 2025' in s1     # subtitle
        s2 = z.read('xl/worksheets/sheet2.xml').decode()
        assert 'Working Days' in s2                   # stats header
        # every part must be well-formed XML
        for part in ('xl/workbook.xml', 'xl/worksheets/sheet1.xml',
                     'xl/worksheets/sheet2.xml', 'xl/styles.xml', '[Content_Types].xml'):
            minidom.parseString(z.read(part).decode())


def test_calendar_xlsx_day_cells_coloured(tmp_path):
    p = tmp_path / 'cal.xlsx'
    write_calendar_xlsx(str(p), _months(), 'Cal', '')
    with zipfile.ZipFile(p) as z:
        s1 = z.read('xl/worksheets/sheet1.xml').decode()
    # holiday day 20 → style 5 ; a normal working day → style 3
    assert 's="5"' in s1     # holiday-styled cell present
    assert 's="3"' in s1     # work-styled cell present


def test_write_xlsx_still_works(tmp_path):
    """The flat-table export used elsewhere must keep working after the refactor."""
    p = tmp_path / 'flat.xlsx'
    write_xlsx(str(p), 'Sheet', ['A', 'B'], [['x', 1], ['y', 2]])
    with zipfile.ZipFile(p) as z:
        assert 'xl/worksheets/sheet1.xml' in z.namelist()
        s = z.read('xl/worksheets/sheet1.xml').decode()
        assert 'autoFilter' in s          # flat table keeps its filter
        minidom.parseString(s)
