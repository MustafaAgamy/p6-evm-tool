"""Owner comment 26 — Schedule (Gantt).

  1. The Gantt (and the WBS view) is still there after a project is re-opened from Recent
     Projects: its rows are stored with the snapshot; an older snapshot is rebuilt once.
  2. Bars use the CURRENT dates, as P6's Start / Finish columns do (actual where started /
     finished, remaining early otherwise), not the Planned dates.
  3. Grouping is by the TRUE top-level WBS, keyed by its id (the old code grouped by the
     activity's own lowest WBS name and merged unrelated WBS that shared a name).
  4. The view prints: File ▸ Print opens the Report Contents preview with PDF / Word / HTML.
"""
import os
from datetime import datetime
from types import SimpleNamespace

import db
from p6_evm import schedule_view as sv
from p6_evm.schedule_excel import schedule_excel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = datetime


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding='utf-8').read()


WBS = {
    'P':  {'name': 'Project', 'parent_object_id': None},
    'E':  {'name': 'Engineering', 'parent_object_id': 'P'},
    'C':  {'name': 'Construction', 'parent_object_id': 'P'},
    'EC': {'name': 'Civil', 'parent_object_id': 'E'},
    'CC': {'name': 'Civil', 'parent_object_id': 'C'},        # same NAME, different WBS
}


def _act(i, wbs, ps, pf, **kw):
    a = {'id': i, 'name': 'Act ' + i, 'wbs_id': wbs, 'planned_start': ps, 'planned_finish': pf,
         'percent_complete': 0.0, 'task_type': 'TaskDependent', 'planned_duration': 5}
    a.update(kw)
    return a


def _records():
    return [
        # finished: drawn on its ACTUAL dates, never critical
        {'activity': _act('A1', 'EC', D(2025, 1, 1), D(2025, 1, 10), actual_start=D(2025, 2, 3),
                          actual_finish=D(2025, 2, 14), percent_complete=1.0),
         'total_float': 0, 'bac': 0, 'planned_pct': 1.0, 'actual_pct': 1.0},
        # in progress: actual start → remaining early finish
        {'activity': _act('A2', 'CC', D(2025, 2, 1), D(2025, 2, 20), actual_start=D(2025, 3, 1),
                          remaining_early_start=D(2025, 3, 10), remaining_early_finish=D(2025, 4, 2),
                          percent_complete=0.4),
         'total_float': -12.34, 'bac': 0, 'planned_pct': 1.0, 'actual_pct': 0.4},
        # not started: remaining early dates
        {'activity': _act('A3', 'CC', D(2025, 3, 1), D(2025, 3, 20),
                          remaining_early_start=D(2025, 5, 1), remaining_early_finish=D(2025, 5, 20)),
         'total_float': 8.0, 'bac': 0, 'planned_pct': 0.5, 'actual_pct': 0.0},
        # a critical finish milestone with only Planned dates
        {'activity': _act('M1', 'C', D(2025, 6, 1), D(2025, 6, 1), task_type='FinishMilestone'),
         'total_float': 0, 'bac': 0, 'planned_pct': 0.0, 'actual_pct': 0.0},
        # no dates at all → not on the chart
        {'activity': _act('X', 'C', None, None), 'total_float': None, 'bac': 0,
         'planned_pct': None, 'actual_pct': 0.0},
    ]


def test_bars_use_current_dates_not_planned():
    rows = {r['id']: r for r in sv.gantt_activities(_records(), WBS)}
    assert 'X' not in rows
    a1, a2, a3, m1 = rows['A1'], rows['A2'], rows['A3'], rows['M1']
    assert (a1['start'][:10], a1['finish'][:10], a1['status']) == ('2025-02-03', '2025-02-14', 'Completed')
    assert (a1['planned_start'][:10], a1['planned_finish'][:10]) == ('2025-01-01', '2025-01-10')   # kept for reference
    assert (a2['start'][:10], a2['finish'][:10], a2['status']) == ('2025-03-01', '2025-04-02', 'In Progress')
    assert (a3['start'][:10], a3['finish'][:10], a3['status']) == ('2025-05-01', '2025-05-20', 'Not Started')
    assert (m1['start'][:10], m1['finish'][:10]) == ('2025-06-01', '2025-06-01')     # Planned only as the fallback
    # critical = float of zero or less AND not finished; milestones included
    assert a1['critical'] is False and a2['critical'] is True and a3['critical'] is False
    assert m1['critical'] is True and m1['milestone'] is True
    assert a2['tf'] == -12.3 and a3['tf'] == 8.0


def test_grouping_is_the_true_top_level_wbs_keyed_by_id():
    rows = {r['id']: r for r in sv.gantt_activities(_records(), WBS)}
    # everything hangs under the single 'Project' node → grouped one level down
    assert rows['A1']['wbs_top'] == 'Engineering' and rows['A2']['wbs_top'] == 'Construction'
    assert rows['A1']['wbs_top_id'] == 'E' and rows['A2']['wbs_top_id'] == 'C' == rows['M1']['wbs_top_id']
    # the path reads top → own WBS (P6 order), not backwards
    assert rows['A1']['wbs'] == 'Project > Engineering > Civil'
    assert rows['A2']['wbs'] == 'Project > Construction > Civil'
    # two real top levels: no step down
    two = dict(WBS, E={'name': 'Engineering', 'parent_object_id': None}, C={'name': 'Construction', 'parent_object_id': None})
    rows = {r['id']: r for r in sv.gantt_activities(_records(), two)}
    assert rows['A1']['wbs_top_id'] == 'E' and rows['A1']['wbs'] == 'Engineering > Civil'


def test_excel_follows_the_same_groups_and_dates():
    # owner comment 65: the sheet lists the CRITICAL activities only (A2 and the milestone M1)
    acts = sv.gantt_activities(_records(), WBS)
    blocks = schedule_excel({'activities': acts, 'data_date': '2025-03-15', 'project_name': 'T'})[0]['blocks']
    assert [b['title'] for b in blocks] == ['Schedule Gantt (Critical activities)', 'Construction']
    head = blocks[1]['headers']
    assert head[:9] == ['Activity ID', 'Activity Name', 'WBS', 'Status', 'Expected Start', 'Expected Finish', 'Delay (d)', 'Planned Start', 'Planned Finish']
    con = {r[0]: r for r in blocks[1]['rows']}
    assert set(con) == {'A2', 'M1'}
    assert con['M1'][head.index('Critical')] == 'Yes' and con['M1'][head.index('Type')] == 'Milestone'
    assert con['A2'][head.index('Total Float (d)')] == -12.3 and con['A2'][4] == '01-Mar.2025'
    assert 'actual where the work has started' in blocks[0]['note']
    assert ['Activities in the schedule', 4] in blocks[0]['rows']
    # two WBS with the SAME name under different parents stay two groups
    acts2 = [dict(a, critical=True) for a in acts]
    for a in acts2:
        a['wbs_top'] = 'Civil'
    titles = [b['title'] for b in schedule_excel({'activities': acts2})[0]['blocks']]
    assert titles == ['Schedule Gantt (Critical activities)', 'Civil', 'Civil']
    # a schedule with nothing critical says so instead of listing every activity
    none = schedule_excel({'activities': [dict(a, critical=False) for a in acts]})[0]['blocks']
    assert len(none) == 1 and none[0]['rows'][0][0] == 'No critical activities'
    # an old stored result (no status / float / planned dates) still exports
    old = [{'id': 'O1', 'name': 'Old', 'wbs': 'A', 'wbs_top': 'A', 'start': '2025-01-01', 'finish': '2025-01-02',
            'pct': 10, 'critical': True, 'milestone': False}]
    row = schedule_excel({'activities': old})[0]['blocks'][1]['rows'][0]
    assert row[3] == '' and row[6] == '' and row[7] == '' and row[10] == ''


def test_wbs_view_dates_are_current_dates_too():
    data = SimpleNamespace(wbs=WBS, baseline_by_id={})
    summary, main = sv.wbs_views(_records(), data)
    by = {n['id']: n for n in summary}
    assert by['EC']['start'] == '2025-02-03' and by['EC']['finish'] == '2025-02-14'
    assert by['C']['finish'] == '2025-06-01'
    assert [m['name'] for m in main] == ['Engineering', 'Construction']      # the file's own (P6) order
    views = sv.build_views(_records(), data)
    assert set(views) == {'activities', 'wbs_summary', 'wbs_main', 'wbs_critical', 'cost_loaded', 'progress_groups'} and len(views['activities']) == 4


def test_views_are_stored_with_the_snapshot_and_removed_with_the_project(temp_db):
    pid = db.upsert_project('G26', 'Gantt 26')
    sid = db.insert_snapshot(pid, '2025-03-15', 'x.xml', 'x.xml', 'h', 4, 1)
    assert db.get_snapshot_views(sid) is None
    views = {'activities': [{'id': 'A1'}], 'wbs_summary': [{'id': 'E'}], 'wbs_main': []}
    db.save_snapshot_views(sid, views)
    assert db.get_snapshot_views(sid) == views
    db.save_snapshot_views(sid, dict(views, activities=[]))          # replaced, not duplicated
    assert db.get_snapshot_views(sid)['activities'] == []
    db.delete_project(pid)
    assert db.get_snapshot_views(sid) is None


def test_reopen_reads_the_stored_views_and_rebuilds_an_old_snapshot_once():
    srv = _read('server.py')
    load = srv[srv.index('    def _handle_project_load(self, body):'):]
    load = load[:load.index('\n    def ', 10)]
    assert 'result.update(self._snapshot_views(snapshot_id))' in load
    helper = srv[srv.index('    def _snapshot_views(self, snapshot_id):'):srv.index('    def _handle_project_load(self, body):')]
    assert 'db.get_snapshot_views(snapshot_id)' in helper and "if views is None or 'cost_loaded' not in views or views.get('v') != 4:" in helper
    assert 'build_views(' in helper and 'db.save_snapshot_views(snapshot_id, views)' in helper
    # the import stores them, from the one shared builder
    pipe = srv[srv.index('    def _parse_pipeline(self, body):'):srv.index('    def _snapshot_views(self, snapshot_id):')]
    assert 'gantt_activities(result[\'records\'], data.wbs, data)' in pipe and 'wbs_views(result[\'records\'], data)' in pipe
    assert 'db.save_snapshot_views(sid,' in pipe
    assert "a.get('planned_start'), a.get('planned_finish')" not in pipe      # no Planned-date bars left behind


def test_the_gantt_prints_with_pdf_word_and_html():
    app = _read('ui', 'app.js')
    assert "schedule:  { module: 'schedule',   title: 'Schedule (Gantt)',       get: schedulePrint, exports: ['pdf', 'docx', 'html', 'xlsx']" in app      # + its own Excel (comment 2 follow-up)
    assert "import { renderSchedule, schedulePrint }" in app
    assert "if (e.target.closest('#sched-print-btn')) runReport('pdf');" in app
    pv = _read('ui', 'modules', 'printview.js')
    assert 'export async function printView({ module, title, subtitle, sections, exports, exportName, meta, onExcel, landscape })' in pv
    assert 'html, body { height:auto !important; overflow:visible !important; }' in pv    # a report longer than one page
    g = _read('ui', 'modules', 'gantt.js')
    assert 'data-part="gantt.' in g and 'data-part="summary.counts"' in g
    assert 'data-export="bar"' in g                       # Word draws the bar column; Excel gets the dates (test_gantt_word_bars)
    assert 'id="sched-print-btn"' in g and g.count('id="sched-excel-btn"') == 2   # Excel button also in the empty state
    assert 'Re-import this schedule to build the Gantt' not in g
    css = _read('ui', 'style.css')
    assert '.g-wrap { --g-lblw: 560px; overflow: auto; max-height:' in css and 'var(--g-cols,' in css       # header + activity column stay in view
    assert 'position: sticky; left: 0;' in css and '.g-ms.crit { background: var(--danger); }' in css


# ── owner comments 63 / 65 / 93 / 94 — cost-loaded figures, critical-only Gantt ──────────────
def _cost_records():
    def rec(i, wbs, bac, pl, ac, codes=None, **kw):
        a = _act(i, wbs, D(2025, 1, 1), D(2025, 1, 10), activity_codes=codes or {}, **kw)
        return {'activity': a, 'total_float': 5, 'bac': bac, 'planned_pct': pl, 'actual_pct': ac}
    return [
        rec('E1', 'EC', 0, 1.0, 1.0),                                   # engineering: no cost
        rec('C1', 'CC', 300.0, 1.0, 0.5, {'Type of Works': 'Civil'}),
        rec('C2', 'CC', 100.0, 0.2, 0.0, {'Type of Works': 'Steel'}),
        rec('C3', 'C', 0, 0.6, 0.6),                                    # construction, no cost
    ]


class _Data:
    wbs = WBS
    baseline_by_id = {}
    activity_code_types = ['Type of Works', 'Unused code']


def test_overview_figures_come_from_cost_loaded_activities_only():
    ov = sv.cost_loaded_overview(_cost_records())
    assert ov['activities'] == 2 and ov['all_activities'] == 4 and ov['bac'] == 400.0
    assert ov['pv'] == 320.0 and ov['ev'] == 150.0                     # 300*1.0+100*0.2 / 300*0.5
    assert ov['planned_pct'] == 0.8 and ov['actual_pct'] == 0.375
    assert abs(ov['spi'] - 0.46875) < 1e-9                              # = actual % / planned %
    assert sv.cost_loaded_overview(_records()) is None                  # a schedule with no cost


def test_progress_groups_by_wbs_and_by_each_used_activity_code():
    groups = sv.progress_groups(_cost_records(), _Data())
    assert [g['key'] for g in groups] == ['wbs', 'code:Type of Works']      # the unused code is not offered
    by = {r['name']: r for r in groups[1]['rows']}
    assert by['Civil']['planned_pct'] == 1.0 and by['Civil']['actual_pct'] == 0.5 and by['Civil']['activities'] == 1
    assert by['Steel']['planned_pct'] == 0.2 and by['Steel']['bac'] == 100.0
    assert sum(r['activities'] for r in groups[0]['rows']) == 2             # cost-loaded only
    assert sv.progress_groups(_records(), _Data()) == []


def test_wbs_without_cost_carries_no_percentages():
    summary, _ = sv.wbs_views(_cost_records(), _Data())
    by = {n['id']: n for n in summary}
    assert by['EC']['cost_loaded'] == 0 and by['EC']['planned'] is None and by['EC']['actual'] is None
    assert by['CC']['cost_loaded'] == 2 and by['CC']['planned'] == 80.0 and by['CC']['actual'] == 37.5
    from p6_evm.wbs_excel import wbs_excel
    rows = [r for b in wbs_excel({'wbs_summary': summary, 'wbs_main': []})[0]['blocks'] for r in b['rows']]
    eng = next(r for r in rows if r[0].strip() == 'Engineering')
    assert eng[5] == 'no cost' and eng[6] == 'no cost'


def test_critical_follows_the_p6_flag_when_the_file_carries_it():
    recs = _records()
    recs[2]['activity']['is_critical'] = True          # P6 flags it (longest path) although float is 8
    recs[1]['activity']['is_critical'] = False
    rows = {r['id']: r for r in sv.gantt_activities(recs, WBS)}
    assert rows['A3']['critical'] is True and rows['A2']['critical'] is False
    assert rows['A1']['critical'] is False             # finished work is never critical


def test_screens_show_cost_loaded_overview_critical_gantt_and_fitted_wbs():
    ov, gantt = _read('ui', 'modules', 'overview.js'), _read('ui', 'modules', 'gantt.js')
    assert 'CPI' not in ov[ov.index('export function renderOverview'):ov.index('// ── Project ▸ WBS summary timeline')]
    assert 'result.cost_loaded' in ov and 'id="ov-group"' in ov
    assert 'all.filter((a) => a.critical && a.construction !== false)' in gantt
    assert 'Schedule Gantt (Critical activities)' in gantt and '<i>Expected Start</i><i>Expected Finish</i><i>Delay</i>' in gantt
    assert 'id="g-code"' in gantt and 'ovh-col p' in ov and 'id="ov-hide0"' in ov and 'cost-loaded\' : \'\'}' not in ov
    assert 'Cut-off date' in ov and "if ('delay' in n) return n.delay;" in ov
    assert 'wbst-fit' in ov and 'totalDays * 3' not in ov        # the timeline fits the screen: no sideways scroll
    assert 'wbsHasPct' in ov


def test_wbs_follows_p6_order_and_delay_is_the_update_total_float():
    """WBS siblings in P6's own order (Sequence Number), not alphabetical. Delay = the update's
    Total Float read as days late: per activity -(total float); per WBS its latest Late Finish
    against its latest Early Finish on the project's default calendar."""
    wbs = {
        'P': {'name': 'Project', 'parent_object_id': None, 'seq': '0'},
        'S': {'name': 'Submittal', 'parent_object_id': 'P', 'seq': '10'},
        'A': {'name': 'Approval', 'parent_object_id': 'P', 'seq': '20'},
        'Z': {'name': 'Done', 'parent_object_id': 'P', 'seq': '30'},
    }
    recs = [
        {'activity': _act('X1', 'A', D(2025, 1, 1), D(2025, 1, 10), remaining_early_start=D(2025, 1, 6, 8),
                          remaining_early_finish=D(2025, 1, 20, 17), remaining_late_finish=D(2025, 1, 13, 17), calendar_id='c'),
         'total_float': -5.0, 'bac': 0, 'planned_pct': 0.0, 'actual_pct': 0.0},
        {'activity': _act('X2', 'S', D(2025, 1, 1), D(2025, 1, 10), remaining_early_start=D(2025, 1, 6, 8),
                          remaining_early_finish=D(2025, 1, 13, 17), remaining_late_finish=D(2025, 1, 15, 17), calendar_id='c'),
         'total_float': 2.0, 'bac': 0, 'planned_pct': 0.0, 'actual_pct': 0.0},
        {'activity': _act('X3', 'Z', D(2025, 1, 1), D(2025, 1, 3), actual_start=D(2025, 1, 1, 8), actual_finish=D(2025, 1, 3, 17),
                          percent_complete=1.0, calendar_id='c'),
         'total_float': None, 'bac': 0, 'planned_pct': 1.0, 'actual_pct': 1.0},
    ]

    class Cal:                                           # Monday-Friday
        def is_working_day(self, d):
            return d.weekday() < 5
    data = SimpleNamespace(wbs=wbs, calendars={'c': Cal()}, project={'default_calendar_id': 'c'}, baseline_by_id={})
    summary, main = sv.wbs_views(recs, data)
    assert [m['name'] for m in main] == ['Submittal', 'Approval', 'Done']   # P6 order, not A-Z
    by = {n['name']: n for n in summary}
    assert by['Approval']['delay'] == 5 and by['Approval']['total_float'] == -5     # late finish 13-Jan, early finish 20-Jan
    assert by['Submittal']['delay'] == -2 and by['Done']['delay'] is None           # 2 d of float; finished work has none
    rows = {r['id']: r for r in sv.gantt_activities(recs, wbs, data)}
    assert rows['X1']['delay'] == 5 and rows['X2']['delay'] == -2 and rows['X3']['delay'] is None


def test_gantt_keeps_construction_rows_only_and_offers_a_code_column():
    recs = _cost_records()
    for r in recs:
        r['activity']['is_critical'] = True
    rows = {r['id']: r for r in sv.gantt_activities(recs, WBS, None)}
    assert rows['C1']['construction'] and rows['C3']['construction'] and rows['E1']['construction'] is False
    assert rows['C1']['codes'] == {'Type of Works': 'Civil'}
    blocks = schedule_excel({'activities': list(rows.values()), 'code_column': 'Type of Works'})[0]['blocks']
    assert [b['title'] for b in blocks] == ['Schedule Gantt (Critical activities)', 'Construction']
    assert blocks[1]['headers'][:3] == ['Activity ID', 'Type of Works', 'Activity Name']
    assert {r[0]: r[1] for r in blocks[1]['rows']} == {'C1': 'Civil', 'C2': 'Steel', 'C3': ''}


def test_critical_wbs_summary_is_p6s_band_under_the_critical_filter():
    """Round 4 (owner's P6 example sheet): each WBS summarised over its CRITICAL activities only -
    earliest Start, latest Finish, Activity Count, Budget / PV / EV, Schedule % and Performance %,
    Original Duration from Planned Start to Planned Finish, Total Float from the summarised dates."""
    wbs = {'P': {'name': 'Project', 'parent_object_id': None, 'seq': '0'},
           'B': {'name': 'Phase B', 'parent_object_id': 'P', 'seq': '10'}}

    def rec(i, tf, bac, pl, ac, es, ef, lf, **kw):
        a = _act(i, 'B', D(2025, 1, 6, 8), D(2025, 1, 17, 17), remaining_early_start=es, remaining_early_finish=ef,
                 remaining_late_finish=lf, calendar_id='c', is_critical=tf <= 0, **kw)
        return {'activity': a, 'total_float': tf, 'bac': bac, 'planned_pct': pl, 'actual_pct': ac}
    recs = [
        rec('K1', -5.0, 100.0, 1.0, 0.5, D(2025, 1, 13, 8), D(2025, 1, 24, 17), D(2025, 1, 17, 17)),
        rec('K2', -3.0, 300.0, 0.5, 0.0, D(2025, 1, 20, 8), D(2025, 1, 31, 17), D(2025, 1, 28, 17)),
        rec('N1', 9.0, 600.0, 1.0, 1.0, D(2025, 1, 6, 8), D(2025, 2, 28, 17), D(2025, 3, 13, 17)),     # not critical
    ]

    class Cal:
        def is_working_day(self, d):
            return d.weekday() < 5
    data = SimpleNamespace(wbs=wbs, calendars={'c': Cal()}, project={'default_calendar_id': 'c'}, baseline_by_id={})
    crit = sv.critical_records(recs)
    assert [r['activity']['id'] for r in crit] == ['K1', 'K2']
    b = {n['name']: n for n in sv.wbs_views(crit, data)[0]}['Phase B']
    assert b['count'] == 2 and b['start'] == '2025-01-13' and b['finish'] == '2025-01-31'
    assert b['bac'] == 400.0 and b['pv'] == 250.0 and b['ev'] == 50.0
    assert b['planned'] == 62.5 and b['actual'] == 12.5                     # PV / budget, EV / budget
    assert b['total_float'] == -3 and b['delay'] == 3                       # late finish 28-Jan against early finish 31-Jan
    assert b['orig_dur'] == 10                                              # Planned Start 06-Jan to Planned Finish 17-Jan
    views = sv.build_views(recs, data)
    assert [n['name'] for n in views['wbs_critical']] == ['Project', 'Phase B'] and views['wbs_summary'][1]['count'] == 3
    rows = {r['id']: r for r in views['activities']}
    assert rows['K1']['wbs_id'] == 'B'
    gantt, ov = _read('ui', 'modules', 'gantt.js'), _read('ui', 'modules', 'overview.js')
    assert 'result.wbs_critical' in gantt and 'g-band' in gantt
    assert "data-mode=\"critical\"" in ov
    assert 'Original Duration' not in ov and 'Budgeted Total Cost' not in ov      # only the agreed columns are shown
