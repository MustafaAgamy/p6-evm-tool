"""E1 reader must handle a format DIFFERENT from Ibrahim's original file — columns
matched by meaning. Writes a small xlsx with alternative headings and reads it back."""
import openpyxl
from p6_evm.e1_log import read_e1_rows, summarize_e1


def _write(path, headers, data_rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['Some title banner'])          # noise above the header
    ws.append(headers)
    for r in data_rows:
        ws.append(r)
    wb.save(path)


def test_reads_alternative_headers(tmp_path):
    p = tmp_path / "e1_alt.xlsx"
    # None of these match Ibrahim's exact spellings — all matched by meaning
    _write(
        p,
        ['Division', 'Zone', 'Drawing Title', 'Drawing Type', 'Submission Date', 'Target Date', 'Review Status'],
        [
            ['Civil', 'Silo 1', 'Foundation plan', 'Detailed Design', '2026-01-10', '2026-01-05', 'A'],
            ['Civil', 'Silo 1', 'Rebar layout', 'Shop Drawing', '2026-02-01', '2026-01-20', 'B'],
            ['MEP', 'Silo 2', 'Duct routing', 'Shop Drawing', None, '2026-03-01', 'C'],
        ],
    )
    rows = read_e1_rows(str(p))
    assert len(rows) == 3
    assert rows[0]['trade'] == 'Civil'
    assert rows[0]['submittal_type'] == 'Detailed Design'
    assert rows[0]['action_code'] == 'A'
    # and it summarises cleanly
    summ = summarize_e1(rows)
    assert ('Civil', 'Detailed Design') in summ
    assert ('MEP', 'Shop Drawing') in summ
