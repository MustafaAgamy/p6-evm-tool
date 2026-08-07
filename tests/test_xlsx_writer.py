import zipfile
from p6_evm.xlsx_writer import write_xlsx


def test_produces_valid_xlsx_zip(tmp_path):
    p = tmp_path / "out.xlsx"
    write_xlsx(str(p), "Findings", ["A", "B"], [["x", 1], ["y & <z>", 2.5]])
    assert p.exists()
    with zipfile.ZipFile(p) as z:
        names = set(z.namelist())
        assert '[Content_Types].xml' in names
        assert 'xl/workbook.xml' in names
        assert 'xl/worksheets/sheet1.xml' in names
        sheet = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
    assert 'y &amp; &lt;z&gt;' in sheet          # string XML-escaped
    assert '<v>2.5</v>' in sheet                  # number as numeric cell
    assert 'autoFilter' in sheet                  # filter present


def test_sheet_name_in_workbook(tmp_path):
    p = tmp_path / "o.xlsx"
    write_xlsx(str(p), "Findings", ["H"], [["v"]])
    with zipfile.ZipFile(p) as z:
        wb = z.read('xl/workbook.xml').decode('utf-8')
    assert 'Findings' in wb


def test_empty_rows_ok(tmp_path):
    p = tmp_path / "e.xlsx"
    write_xlsx(str(p), "S", ["H1", "H2"], [])
    assert p.exists()
