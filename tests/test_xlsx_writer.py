import zipfile
import xml.etree.ElementTree as ET
from p6_evm.xlsx_writer import write_xlsx, RichText


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


def test_highlight_cols_apply_amber_style(tmp_path):
    # A highlighted column's DATA cells carry the amber highlight style (xf s="2"); other cells and
    # the header do not. This is how the driving relationship is highlighted on export.
    p = tmp_path / "h.xlsx"
    write_xlsx(str(p), "S", ["Plain", "Driving"], [["a", "D1"], ["b", "D2"]], highlight_cols=[1])
    with zipfile.ZipFile(p) as z:
        sheet = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        styles = z.read('xl/styles.xml').decode('utf-8')
    assert 'FFFEF3C7' in styles                      # amber fill defined
    # the driving-column data cells (B2, B3) are styled s="2"; the plain-column cells are not
    assert '<c r="B2" s="2"' in sheet and '<c r="B3" s="2"' in sheet
    assert '<c r="A2" s="2"' not in sheet


def test_severity_colours_and_legend(tmp_path):
    # The severity column is colour-coded by value (Critical=3, High=4, Medium=5) and a legend is
    # rendered below the table.
    p = tmp_path / "s.xlsx"
    write_xlsx(str(p), "S", ["Activity", "Severity"],
               [["A", "Critical"], ["B", "High"], ["C", "Medium"]],
               severity_col=1,
               legend=[("Critical", "On the critical path"), ("High", "Near-critical"), ("Medium", "Has float")])
    with zipfile.ZipFile(p) as z:
        sheet = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        styles = z.read('xl/styles.xml').decode('utf-8')
    assert 'FFFADDDD' in styles and 'FFFBECCF' in styles and 'FFEEF1F6' in styles   # sev fills defined
    assert '<c r="B2" s="3"' in sheet          # Critical → red
    assert '<c r="B3" s="4"' in sheet          # High → amber
    assert '<c r="B4" s="5"' in sheet          # Medium → grey
    assert 'Severity legend' in sheet          # legend rendered below the table
    assert 'On the critical path' in sheet


def test_richtext_cell_emits_runs_with_bold_colour(tmp_path):
    # A RichText cell becomes an inline string of multiple <r> runs; the driving run carries
    # a bold + amber-brown (FF92400E) rPr, a plain run carries no rPr. This is how the driving
    # predecessor line is highlighted INSIDE the Baseline Predecessors cell.
    rich = RichText([
        {'t': 'SS-1410  FS  [Driving]  —  Fabricate Steel', 'b': True, 'color': 'FF92400E'},
        {'t': '\nSS-1400  SS  —  Site Handover', 'b': False, 'color': None},
    ])
    p = tmp_path / "rich.xlsx"
    write_xlsx(str(p), "Findings", ["Baseline Predecessors"], [[rich]])
    assert p.exists()
    with zipfile.ZipFile(p) as z:
        sheet = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
        styles = z.read('xl/styles.xml').decode('utf-8')
        # valid zip whose styles.xml + sheet1.xml both parse as XML
        ET.fromstring(sheet)
        ET.fromstring(styles)
    assert sheet.count('<r>') == 2                    # two runs in one cell
    assert '<b/>' in sheet                            # the driving run is bold …
    assert '<color rgb="FF92400E"/>' in sheet         # … and amber-brown
    assert '[Driving]' in sheet and 'Fabricate Steel' in sheet
    assert 'Site Handover' in sheet                   # the plain run text present too
    # the rich cell wraps (multi-line): it carries the wrap-top style, not a fill
    assert '<c r="A2" s="6"' in sheet
