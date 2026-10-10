"""overview_excel — the Project Overview workbook: one sheet stacking the three
overview sections (Project Summary, Key Indicators, Progress by Category), mirroring
the on-screen Overview (ui/modules/overview.js · renderOverview). Validated by
unzipping + XML-parsing (no openpyxl dependency), matching test_calendar_xlsx."""
import zipfile
import xml.dom.minidom as minidom

from p6_evm.overview_excel import overview_excel
from p6_evm.xlsx_writer import write_sections_xlsx


def _result():
    """A representative parse result the client (state.currentResult) would hold."""
    return {
        'project_name': 'New Cairo Towers',
        'data_date': '2026-02-09',
        'activity_count': 1320,
        'calendar_count': 3,
        'spi': 0.92,
        'cpi': 1.03,
        'delay_days': 14,
        'overall_planned_pct': 0.4235,
        'overall_actual_pct': 0.3810,
        'pv': 243805397,
        'ev': 219300000.0,
        'ac': 210000000,
        'expected_finish': '2027-05-20',
        'baseline_finish': '2027-05-06',
        'categories': {
            'Engineering': {'planned_pct': 0.85, 'actual_pct': 0.80,
                            'activity_count': 120, 'overridden': False},
            'Construction': {'planned_pct': 0.40, 'actual_pct': 0.33,
                             'activity_count': 900, 'overridden': True},
        },
    }


def _report(path):
    sheets = overview_excel({'result': _result(),
                             'meta': {'source_file': 'update_wk32.xml',
                                      'report_date': '09 Feb 2026'}})
    write_sections_xlsx(str(path), sheets)
    return path


def _worksheets_text(path):
    with zipfile.ZipFile(path) as z:
        return '\n'.join(z.read(n).decode() for n in z.namelist()
                         if n.startswith('xl/worksheets/'))


def _all_wellformed(path):
    with zipfile.ZipFile(path) as z:
        assert '[Content_Types].xml' in z.namelist()
        for n in z.namelist():
            if n.endswith('.xml'):
                minidom.parseString(z.read(n).decode())  # raises if malformed


def test_overview_workbook_is_valid_zip_with_expected_sheet(tmp_path):
    """A valid .xlsx (zip of well-formed XML) whose one sheet is named 'Project Overview'."""
    p = _report(tmp_path / 'ov.xlsx')
    assert zipfile.is_zipfile(p)
    _all_wellformed(p)
    with zipfile.ZipFile(p) as z:
        workbook = z.read('xl/workbook.xml').decode()
    assert 'Project Overview' in workbook


def test_overview_mirrors_the_three_screen_sections(tmp_path):
    """The three stacked section titles + representative headers/labels are present."""
    p = _report(tmp_path / 'ov.xlsx')
    text = _worksheets_text(p)
    for title in ('Project Summary', 'Key Indicators', 'Progress by Category'):
        assert title in text
    # header chips → summary rows
    for field in ('WBS categories', 'Activities', 'Calendars'):
        assert field in text
    # KPI labels (screen order) and a category name
    for label in ('SPI · schedule', 'Planned %', 'Actual %', 'Planned value', 'Earned value'):
        assert label in text
    assert 'CPI' not in text                      # owner comment 93: no CPI on the Overview
    assert 'Construction' in text and 'manual override' in text


def test_overview_keeps_numbers_numeric(tmp_path):
    """Numbers land as numeric cells (<v>…</v>), not inline strings — SPI, activity
    count and Planned Value must be computable in Excel."""
    p = _report(tmp_path / 'ov.xlsx')
    text = _worksheets_text(p)
    assert '<v>0.92</v>' in text          # SPI kept numeric (2 dp)
    assert '<v>1320</v>' in text          # activity count numeric
    assert '<v>243805397</v>' in text     # Planned Value numeric
    assert '<v>14</v>' in text            # Delay days numeric
    assert '<v>42.35</v>' in text         # Overall planned % = 0.4235 → 42.35 numeric


def test_overview_delay_fallback_from_finishes(tmp_path):
    """When delay_days is absent, Delay = expected_finish − baseline_finish in days
    (matches renderOverview's fallback) — here 2027-05-20 − 2027-05-06 = 14."""
    r = _result()
    r.pop('delay_days')
    sheets = overview_excel({'result': r})
    p = tmp_path / 'ov2.xlsx'
    write_sections_xlsx(str(p), sheets)
    assert '<v>14</v>' in _worksheets_text(p)


def test_overview_empty_data_no_crash(tmp_path):
    """Empty/missing result → a 'No data' sheet, never an exception."""
    sheets = overview_excel({'result': {}})
    p = tmp_path / 'empty.xlsx'
    write_sections_xlsx(str(p), sheets)
    _all_wellformed(p)
    assert 'No data' in _worksheets_text(p)
    # also tolerate a completely empty payload
    write_sections_xlsx(str(tmp_path / 'none.xlsx'), overview_excel(None))
    _all_wellformed(tmp_path / 'none.xlsx')


def test_overview_uses_the_cost_loaded_figures_and_the_picked_grouping(tmp_path):
    """Owner comments 93 / 94: Planned %, Actual %, PV, EV and SPI from the cost-loaded
    activities; 'Progress by' follows the grouping picked on screen."""
    r = _result()
    r['cost_loaded'] = {'activities': 794, 'all_activities': 1503, 'bac': 1000.0, 'planned_pct': 0.6142,
                        'actual_pct': 0.4043, 'pv': 614.2, 'ev': 404.3, 'spi': 0.6583}
    r['progress_groups'] = [
        {'key': 'wbs', 'label': 'WBS', 'rows': [{'name': 'Silos', 'activities': 5, 'bac': 1000.0, 'planned_pct': 0.6142, 'actual_pct': 0.4043}]},
        {'key': 'code:Type of Works', 'label': 'Type of Works',
         'rows': [{'name': 'Civil Works', 'activities': 4, 'bac': 900.0, 'planned_pct': 0.65, 'actual_pct': 0.43}]}]
    blocks = overview_excel({'result': r, 'progress_group': 'code:Type of Works'})[0]['blocks']
    kpi = {row[0]: row[1] for row in blocks[1]['rows']}
    assert kpi['Planned %'] == 61.42 and kpi['Actual %'] == 40.43
    assert kpi['SPI · schedule'] == 0.66 and kpi['Planned value'] == 614.2
    assert '794 cost-loaded activities' in blocks[1]['note']
    assert blocks[2]['title'] == 'Progress by Type of Works' and blocks[2]['rows'][0][:4] == ['Civil Works', 4, 65.0, 43.0]
    assert overview_excel({'result': r})[0]['blocks'][2]['title'] == 'Progress by WBS'


def test_overview_hide_zero_drops_the_values_with_no_planned_and_no_actual():
    r = _result()
    r['cost_loaded'] = {'activities': 2, 'all_activities': 2, 'bac': 2.0, 'planned_pct': 0.5, 'actual_pct': 0.2, 'pv': 1.0, 'ev': 0.4, 'spi': 0.4}
    r['progress_groups'] = [{'key': 'wbs', 'label': 'WBS', 'rows': [
        {'name': 'Started', 'activities': 1, 'bac': 1.0, 'planned_pct': 1.0, 'actual_pct': 0.4},
        {'name': 'Future', 'activities': 1, 'bac': 1.0, 'planned_pct': 0.0, 'actual_pct': 0.0}]}]
    assert [x[0] for x in overview_excel({'result': r})[0]['blocks'][2]['rows']] == ['Started', 'Future']
    assert [x[0] for x in overview_excel({'result': r, 'hide_zero': True})[0]['blocks'][2]['rows']] == ['Started']
