"""Critical Path Analyzer — PDF (HTML) and Excel exporters."""
from datetime import datetime
import report_theme
from p6_evm.parser import ScheduleData
from p6_critpath.analysis import build_report
from p6_critpath.exporters import render_html, to_excel, critpath_excel_sections


def _sched(data_date, chain, ms_finish, ms_bl, ms_tf, extra):
    d = ScheduleData()
    d.project = {'name': 'T', 'data_date': data_date}
    d.wbs = {}; d.activities = {}; d.relationships = []; d.baseline_by_id = {}
    prev = None
    for i, (w, tf) in enumerate(chain):
        wid = f'W_{w}'; d.wbs[wid] = {'name': w, 'parent_object_id': None}; oid = f'A{i}'
        fin = datetime(2026, 8, 1 + i)
        d.activities[oid] = {'id': f'ACT{i}', 'name': w, 'task_type': 'Task', 'calendar_id': None,
                             'wbs_id': wid, 'percent_complete': 0.0, 'total_float_days': tf,
                             'remaining_early_finish': fin, 'planned_finish': fin, 'object_id': oid}
        d.baseline_by_id[f'ACT{i}'] = {'planned_start': fin, 'planned_finish': fin}
        if prev is not None:
            d.activities[prev]['remaining_early_finish'] = fin
            d.relationships.append({'pred_id': prev, 'succ_id': oid, 'type': 'FS', 'lag_days': 0.0})
        prev = oid
    d.activities['MS'] = {'id': 'M999', 'name': 'Project Completion', 'task_type': 'FinishMilestone',
                          'calendar_id': None, 'wbs_id': None, 'total_float_days': ms_tf,
                          'remaining_early_finish': ms_finish, 'planned_finish': ms_finish}
    d.activities[prev]['remaining_early_finish'] = ms_finish
    d.relationships.append({'pred_id': prev, 'succ_id': 'MS', 'type': 'FS', 'lag_days': 0.0})
    d.baseline_by_id['M999'] = {'planned_start': data_date, 'planned_finish': ms_bl}
    for i, tf in enumerate(extra):
        d.activities[f'X{i}'] = {'id': f'X{i}', 'name': f'x{i}', 'task_type': 'Task', 'calendar_id': None,
                                 'total_float_days': tf, 'object_id': f'X{i}'}
    return d


def _report():
    prev = _sched(datetime(2026, 6, 30), [('Foundations', 0.0), ('Structure', 0.0), ('Roof', 0.0)],
                  datetime(2027, 1, 5), datetime(2026, 12, 10), -5.0, [5.0, 20.0])
    curr = _sched(datetime(2026, 7, 19), [('Foundations', 0.0), ('MEP', 0.0), ('Commissioning', 0.0)],
                  datetime(2027, 1, 23), datetime(2026, 12, 10), -20.0, [-1.0, 6.0])
    r = build_report({'previous': prev, 'current': curr}, 'two_updates')
    r['files'] = {'previous': 'prev.xml', 'current': 'curr.xml'}
    return r


def test_render_html_has_all_sections():
    html = render_html(_report())
    for key in ('verdict', 'dashboard', 'driving_path', 'census', 'milestones', 'float_migration', 'recommendation'):
        assert f'data-sec="{key}"' in html
    assert 'NEW ON PATH' in html            # the reroute highlight survives into the PDF
    assert 'Critical Path Analyzer' in html


def test_render_html_section_filter():
    html = render_html(_report(), sections=['census'])
    assert 'data-sec="census"' in html
    assert 'data-sec="dashboard"' not in html


def test_render_html_theme_dark():
    html = render_html(_report(), theme='dark')
    assert 'data-rpt-theme="dark"' in html
    assert report_theme.THEMES['dark']['rpt-accent'] in html  # '#5b9bff'


def test_render_html_theme_default_is_light():
    html = render_html(_report())
    assert html.startswith('<!doctype html>') and html.rstrip().endswith('</html>')
    assert 'data-rpt-theme="light"' in html


def test_to_excel_writes_expected_sheets(tmp_path):
    from openpyxl import load_workbook
    out = tmp_path / 'cpa.xlsx'
    to_excel(_report(), str(out))
    assert out.exists() and out.stat().st_size > 0     # a real, non-empty .xlsx
    wb = load_workbook(out)
    assert set(wb.sheetnames) >= {'Census', 'Milestones', 'Driving path (current)', 'Float migration'}
    # The workbook now mirrors the report sections via the shared writer: each sheet opens
    # with its section title, then the (self-explaining) header row.
    assert wb['Census']['A1'].value == 'Critical & near-critical census'
    census_vals = [c.value for col in wb['Census'].iter_cols() for c in col]
    assert 'Measure' in census_vals                    # the neutral header row is present
    assert any(str(v or '').startswith('Total activities') for v in census_vals)
    assert any(str(v or '').startswith('CPLI') for v in census_vals)


def test_critpath_excel_sections_structure():
    r = _report()
    sheets = critpath_excel_sections(r)
    names = [s['name'] for s in sheets]
    assert names[:3] == ['Census', 'Milestones', 'Driving path (current)']
    assert 'Float migration' in names                  # base schedule loaded → section present

    # Census mirrors the on-screen numbers exactly (roles = previous, current).
    census = next(s for s in sheets if s['name'] == 'Census')
    blk = census['blocks'][0]
    hdr = blk['headers']
    assert hdr == ['Measure', 'Previous update', 'Current update']
    ci, pi = hdr.index('Current update'), hdr.index('Previous update')
    crit = next(row for row in blk['rows'] if row[0].startswith('Critical activities — count'))
    assert crit[ci] == r['census']['current']['critical']
    assert crit[pi] == r['census']['previous']['critical']

    # Driving path colour-codes criticality via a severity column + a sheet legend.
    dp = next(s for s in sheets if s['name'] == 'Driving path (current)')
    dblk = dp['blocks'][0]
    assert dblk['severity_col'] == dblk['headers'].index('Criticality')
    assert dp.get('legend') and dp['legend'][0][0] == 'Critical'
    # every criticality cell is a valid severity word (or blank) so it colour-matches
    sc = dblk['severity_col']
    assert all(row[sc] in ('Critical', 'High', 'Low', '') for row in dblk['rows'])


def test_critpath_excel_sections_write_roundtrip(tmp_path):
    """The sections structure writes a valid workbook through the shared writer."""
    from openpyxl import load_workbook
    from p6_evm.xlsx_writer import write_sections_xlsx
    out = tmp_path / 'cpa_sections.xlsx'
    write_sections_xlsx(str(out), critpath_excel_sections(_report()))
    wb = load_workbook(out)
    assert {'Census', 'Milestones', 'Driving path (current)', 'Float migration'} <= set(wb.sheetnames)
