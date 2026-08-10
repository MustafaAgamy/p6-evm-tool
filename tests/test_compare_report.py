"""build_report_from_data assembles the Consultant Review report dict from a
baseline + update ScheduleData: header, dashboard, logic changes, duration
changes, change summary, and milestone finishes."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_compare.report import build_report_from_data


def _d(m, day):
    return datetime(2026 if m <= 12 else 2027, m if m <= 12 else m - 12, day)


def _baseline():
    d = ScheduleData()
    d.project = {'name': 'Riyadh Metro', 'data_date': datetime(2026, 2, 9),
                 'scheduled_finish': datetime(2027, 2, 9)}
    d.activities = {
        'bp': {'id': 'A050', 'name': 'Clearance', 'task_type': 'Task', 'calendar_id': None,
               'remaining_early_finish': datetime(2026, 1, 10)},
        'bs': {'id': 'A100', 'name': 'Excavate', 'task_type': 'Task', 'calendar_id': None,
               'remaining_early_start': datetime(2026, 1, 10),
               'planned_duration': 80, 'remaining_duration': 80},
        'bd': {'id': 'A200', 'name': 'Rebar', 'task_type': 'Task', 'calendar_id': None,
               'planned_duration': 96, 'remaining_duration': 96},
        'bm': {'id': 'M900', 'name': 'Handover', 'task_type': 'FinishMilestone', 'calendar_id': None,
               'planned_finish': datetime(2027, 2, 9)},
    }
    d.relationships = [{'pred_id': 'bp', 'succ_id': 'bs', 'type': 'FS', 'lag_days': 0.0}]
    return d


def _update():
    d = ScheduleData()
    d.project = {'name': 'Riyadh Metro', 'data_date': datetime(2026, 2, 9),
                 'scheduled_finish': datetime(2027, 2, 22)}
    d.activities = {
        'up': {'id': 'A050', 'name': 'Clearance', 'task_type': 'Task', 'calendar_id': None,
               'remaining_early_finish': datetime(2026, 1, 10)},
        'us': {'id': 'A100', 'name': 'Excavate', 'task_type': 'Task', 'calendar_id': None,
               'remaining_early_start': datetime(2026, 1, 20),
               'planned_duration': 80, 'remaining_duration': 80},
        'ud': {'id': 'A200', 'name': 'Rebar', 'task_type': 'Task', 'calendar_id': None,
               'planned_duration': 144, 'remaining_duration': 120},
        'um': {'id': 'M900', 'name': 'Handover', 'task_type': 'FinishMilestone', 'calendar_id': None,
               'planned_finish': datetime(2027, 2, 22)},
    }
    d.relationships = [{'pred_id': 'up', 'succ_id': 'us', 'type': 'FS', 'lag_days': 10.0}]
    return d


def test_report_shape_and_wiring():
    r = build_report_from_data(_baseline(), _update())
    assert r['project_name'] == 'Riyadh Metro'
    assert r['data_date'] == '09-Feb-2026'
    assert r['matched_activities'] == 4   # A050, A100, A200, M900 line up by code
    # logic: only A100 (lag change)
    assert r['logic']['summary']['changed_activities'] == 1
    assert [row['activity_id'] for row in r['logic']['rows']] == ['A100']
    # durations: A200 extended
    assert [row['activity_id'] for row in r['durations']['rows']] == ['A200']
    # dashboard counts distinct activities across logic + duration
    assert r['dashboard']['changed_activities'] == 2
    # change summary carries both a lag item and an extended item
    labels = {it['kind']: it['count'] for it in r['change_summary']['items']}
    assert labels.get('lag') == 1 and labels.get('extended') == 1
    # milestones compare baseline vs update finish
    m = next(x for x in r['milestones'] if x['activity_id'] == 'M900')
    assert m['baseline_finish'] == '09-Feb-2027' and m['update_finish'] == '22-Feb-2027'


def test_baseline_finish_falls_back_to_latest_activity_finish():
    # XER-style baseline: no project scheduled_finish → use the latest activity finish.
    b, u = ScheduleData(), ScheduleData()
    b.project = {'name': 'P', 'data_date': datetime(2026, 2, 9)}
    u.project = {'name': 'P', 'data_date': datetime(2026, 2, 9)}
    b.activities = {'1': {'id': 'A1', 'name': 'x', 'task_type': 'Task', 'calendar_id': None,
                          'planned_finish': datetime(2027, 1, 5)}}
    u.activities = {'1': {'id': 'A1', 'name': 'x', 'task_type': 'Task', 'calendar_id': None,
                          'planned_finish': datetime(2027, 3, 9)}}
    r = build_report_from_data(b, u)
    assert r['baseline_finish'] == '05-Jan-2027'
    assert r['update_finish'] == '09-Mar-2027'


def test_construction_codes_keep_construction_drop_engineering_and_milestones():
    from p6_compare.report import _construction_codes
    d = ScheduleData()
    d.wbs = {'w1': {'name': 'Construction Works', 'parent_object_id': None},
             'w2': {'name': 'Shop Drawings', 'parent_object_id': None}}
    d.activities = {
        '1': {'id': 'C1', 'task_type': 'Task', 'wbs_id': 'w1'},            # construction → kept
        '2': {'id': 'E1', 'task_type': 'Task', 'wbs_id': 'w2'},            # engineering (shop) → dropped
        '3': {'id': 'M1', 'task_type': 'FinishMilestone', 'wbs_id': 'w1'},  # milestone → dropped
        '4': {'id': 'X1', 'task_type': 'Task', 'wbs_id': None},            # unclassified → kept
    }
    assert _construction_codes(d) == {'C1', 'X1'}
