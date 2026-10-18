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


def test_float_migration_p6_bands_comment91():
    """Comment 91/92: the bands are P6's filters - completed / LOE never critical, milestones
    counted, near = TF 1-10 d inclusive, safe -> critical is its own move, totals on each side."""
    from types import SimpleNamespace as NS
    from p6_critpath.tables import float_migration
    from p6_critpath.exporters import critpath_excel_sections, render_html

    def sched(acts):
        return NS(activities={i: a for i, a in enumerate(acts)}, project={})
    base = sched([
        {'id': 'A', 'total_float_days': 5, 'status': 'Not Started'},            # near
        {'id': 'B', 'total_float_days': 30, 'status': 'Not Started'},           # safe
        {'id': 'M', 'task_type': 'FinishMilestone', 'total_float_days': 0, 'status': 'Not Started'},
        {'id': 'L', 'task_type': 'LOE', 'total_float_days': -5, 'status': 'In Progress'},
        {'id': 'D', 'total_float_days': -2, 'status': 'Completed'},             # in no band
        {'id': 'N', 'total_float_days': 10, 'status': 'Not Started'},           # 10 d = near
    ])
    curr = sched([
        {'id': 'A', 'total_float_days': 0, 'status': 'In Progress'},
        {'id': 'B', 'total_float_days': -1, 'status': 'Not Started'},
        {'id': 'M', 'task_type': 'FinishMilestone', 'total_float_days': 0, 'status': 'Not Started'},
        {'id': 'L', 'task_type': 'LOE', 'total_float_days': -5, 'status': 'In Progress'},
        {'id': 'D', 'total_float_days': -2, 'status': 'Completed'},
        {'id': 'N', 'total_float_days': 10, 'status': 'Not Started'},
    ])
    m = float_migration(base, curr)
    c = m['counts']
    assert (c['near_to_crit'], c['safe_to_crit'], c['held_crit'], c['turned_crit']) == (1, 1, 1, 2)
    assert m['totals'] == {'base': {'critical': 1, 'near': 2}, 'current': {'critical': 3, 'near': 1}}
    rep = {'float_migration': m, 'float_migration_base': 'previous'}
    html = render_html(rep, sections=['float_migration'])
    assert 'activities turned critical' in html and 'Where every open activity moved' in html
    assert m['matrix'] == {'near>crit': 1, 'safe>crit': 1, 'crit>crit': 1, 'near>near': 1}
    sh = [s for s in critpath_excel_sections(rep) if s['name'] == 'Float migration'][0]
    assert any(r[0] == 'Safe → CRITICAL' for r in sh['blocks'][0]['rows'])


def test_migration_advice_building_by_trade_round3():
    """Round 3: the recommendation crosses the activities that turned critical by a location and
    a trade code (auto-picked by name), names the worst cells with a mitigation, and the PDF /
    Excel follow the codes picked on screen."""
    from p6_critpath.migration_advice import advice, pick_codes
    from p6_critpath.exporters import render_html, critpath_excel_sections
    rows = ([{'kind': 'safe_to_crit', 'to': 'crit', 'base_tf': 20, 'curr_tf': -2, 'codes': {'Building': 'Tower A', 'Trade': 'Civil Works'}}] * 3
            + [{'kind': 'near_to_crit', 'to': 'crit', 'base_tf': 5, 'curr_tf': 0, 'codes': {'Building': 'Tower B', 'Trade': 'Steel Works'}}]
            + [{'kind': 'held_crit', 'to': 'crit', 'base_tf': 0, 'curr_tf': -9, 'codes': {'Building': 'Tower B', 'Trade': 'Civil Works'}}])
    assert pick_codes(rows) == {'location': 'Building', 'trade': 'Trade'}
    a = advice({'rows': rows}, 'Building', 'Trade')
    assert a['items'][0]['location'] == 'Tower A' and a['items'][0]['turned_crit'] == 3 and a['items'][0]['avg_lost'] == 22
    assert 'civil crew' in a['items'][0]['mitigation']
    assert a['worst'][0] == {'location': 'Tower B', 'trade': 'Civil Works', 'activities': 1, 'min_tf': -9}
    mig = {'rows': rows, 'counts': {'near_to_crit': 1, 'safe_to_crit': 3, 'turned_crit': 4}, 'matrix': {},
           'code_types': [{'type': 'Building', 'covered': 4}], 'advice_codes': {'location': 'Building', 'trade': 'Trade'}}
    rep = {'float_migration': mig, 'float_migration_base': 'baseline', 'mig_front_code': {'type': 'Building', 'value': 'Tower A'}}
    html = render_html(rep, sections=['float_migration'])
    assert 'Tower A — Civil Works' in html and 'Mitigation' in html
    sh = [s for s in critpath_excel_sections(rep) if s['name'] == 'Float migration'][0]
    assert any(b['title'].startswith('Recommendation') for b in sh['blocks'])


def test_governing_tie_takes_the_project_finish():
    from types import SimpleNamespace as NS
    from datetime import datetime
    from p6_critpath.analysis import _governing_milestone
    d = datetime(2027, 5, 2, 16)
    acts = {1: {'id': 'KD', 'name': 'Cable Erection Completion', 'task_type': 'FinishMilestone', 'remaining_early_finish': d, 'total_float_days': -60},
            2: {'id': 'CM', 'name': 'Phase I Scope Completion', 'task_type': 'FinishMilestone', 'remaining_early_finish': d, 'total_float_days': -60}}
    data = NS(activities=acts, relationships=[{'pred_id': 1, 'succ_id': 2}], project={})
    assert _governing_milestone(data)['id'] == 'CM'
