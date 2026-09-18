"""narrative_excel — the Baseline Narrative Excel export mirrors the on-screen / PDF
narrative: a 'Baseline Narrative' sheet with the header/figures block followed by one titled
table per narrative section, paragraphs stacked as rows. Numbers stay numeric.

Validated by unzipping + XML-parsing (no openpyxl dependency): the shared writer emits inline
strings (`t="inlineStr"><is><t>…`) and numeric cells as a bare `<v>value</v>` with no type
attribute, so any `<v>…</v>` in a worksheet is a numeric cell.
"""
import zipfile
import xml.dom.minidom as minidom

from p6_evm.narrative import build_narrative
from p6_evm.narrative_excel import narrative_excel
from p6_evm.xlsx_writer import write_sections_xlsx


def _result():
    """A representative compute() result the Baseline Narrative screen would hold."""
    return {
        'project_name': 'Marina Towers — Package 3',
        'data_date': '2026-02-09',
        'overall_planned_pct': 0.60,
        'overall_actual_pct': 0.5825,
        'spi': 0.94,
        'cpi': 1.03,
        'delay_days': 12,
        'pv': 243805397, 'ev': 229176000, 'ac': 222500000,
        'categories': {
            'Civil':        {'weight': 0.5, 'planned_pct': 0.70, 'actual_pct': 0.60},
            'MEP':          {'weight': 0.3, 'planned_pct': 0.40, 'actual_pct': 0.48},
            'Architectural': {'weight': 0.2, 'planned_pct': 0.55, 'actual_pct': 0.55},
        },
    }


def _worksheets_text(path):
    with zipfile.ZipFile(path) as z:
        return '\n'.join(z.read(n).decode() for n in z.namelist()
                         if n.startswith('xl/worksheets/'))


def _all_wellformed(path):
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.endswith('.xml'):
                minidom.parseString(z.read(n).decode())


def test_narrative_excel_mirrors_sections_and_keeps_numbers_numeric(tmp_path):
    result = _result()
    narr = build_narrative(result)
    sheets = narrative_excel({'narrative': narr, 'result': result})

    # One sheet mirroring the report; header block + one block per narrative section.
    assert len(sheets) == 1
    sheet = sheets[0]
    assert sheet['name'] == 'Baseline Narrative'
    titles = [b['title'] for b in sheet['blocks']]
    assert titles[0] == 'Baseline Narrative'                       # header/figures block
    for t in ('Executive summary', 'Schedule performance', 'Cost performance',
              'Progress by area', 'Outlook & recommendation'):
        assert t in titles                                         # every screen section mirrored

    out = tmp_path / 'narrative.xlsx'
    write_sections_xlsx(str(out), sheets)

    # A real, valid .xlsx: openable zip, every XML part well-formed.
    assert zipfile.is_zipfile(str(out))
    with zipfile.ZipFile(str(out)) as z:
        assert any(n.startswith('xl/worksheets/') for n in z.namelist())
    _all_wellformed(str(out))

    xml = _worksheets_text(str(out))
    # Section titles + prose present as inline strings.
    assert 'Executive summary' in xml
    assert 'Outlook &amp; recommendation' in xml                   # '&' escaped in inline string
    # Figures kept NUMERIC (bare <v>…</v>, no t="inlineStr"): delay 12 and SPI 0.94.
    assert '<v>12</v>' in xml                                       # Delay (days)
    assert '<v>0.94</v>' in xml                                     # SPI · Schedule
    assert '<v>58</v>' in xml                                       # Actual complete (%) 0.5825→58


def test_narrative_excel_empty_returns_no_data_sheet(tmp_path):
    """No narrative and no result → a single 'No data' sheet, never a crash."""
    sheets = narrative_excel({})
    assert len(sheets) == 1
    assert sheets[0]['name'] == 'Baseline Narrative'
    rows = sheets[0]['blocks'][0]['rows']
    assert rows[0][0] == 'No data'

    out = tmp_path / 'empty.xlsx'
    write_sections_xlsx(str(out), sheets)          # must not raise
    assert zipfile.is_zipfile(str(out))
    _all_wellformed(str(out))
