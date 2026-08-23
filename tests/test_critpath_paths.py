"""Critical Path Analyzer — driving-path boxes and path diff (the reroute)."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_critpath.paths import path_boxes, path_diff, milestone_list


def _sched(chain_wbs, ms_finish, ms_baseline):
    """A linear driving chain: Foundations → <chain_wbs[-1]> → Milestone. Each activity
    sits in its own WBS work front so the boxes are distinct. Dates make each link driving
    (FS, lag 0: succ start == pred finish)."""
    d = ScheduleData()
    d.project = {'name': 'T', 'data_date': datetime(2026, 7, 19)}
    d.wbs = {}
    d.activities = {}
    d.relationships = []
    d.baseline_by_id = {}
    prev_oid, cur_finish = None, datetime(2026, 8, 1)
    for i, wname in enumerate(chain_wbs):
        wid = f'W_{wname}'                 # stable per work front, so Roof≠MEP across schedules
        d.wbs[wid] = {'name': wname, 'parent_object_id': None}
        oid = f'A{i}'
        start = cur_finish
        finish = datetime(2026, 8, 1 + i)   # each a day later; controlling dates line up
        d.activities[oid] = {
            'id': f'ACT{i}', 'name': wname + ' work', 'task_type': 'Task', 'calendar_id': None,
            'wbs_id': wid, 'percent_complete': 0.0, 'total_float_days': 0.0,
            'remaining_early_start': start, 'remaining_early_finish': finish,
            'planned_finish': finish,
        }
        d.baseline_by_id[f'ACT{i}'] = {'planned_start': start, 'planned_finish': finish}
        if prev_oid is not None:
            # FS link: pred finish == succ start → driving
            d.activities[prev_oid]['remaining_early_finish'] = start
            d.relationships.append({'pred_id': prev_oid, 'succ_id': oid, 'type': 'FS', 'lag_days': 0.0})
        prev_oid = oid
        cur_finish = finish
    # finish milestone driven by the last activity
    d.activities['MS'] = {'id': 'M999', 'name': 'Completion', 'task_type': 'FinishMilestone',
                          'calendar_id': None, 'wbs_id': None, 'total_float_days': -5.0,
                          'remaining_early_start': ms_finish, 'remaining_early_finish': ms_finish,
                          'planned_finish': ms_finish}
    d.activities[prev_oid]['remaining_early_finish'] = ms_finish
    d.relationships.append({'pred_id': prev_oid, 'succ_id': 'MS', 'type': 'FS', 'lag_days': 0.0})
    d.baseline_by_id['M999'] = {'planned_start': ms_baseline, 'planned_finish': ms_baseline}
    return d


def test_path_boxes_returns_chain():
    d = _sched(['Foundations', 'Structure', 'MEP'], datetime(2027, 1, 23), datetime(2026, 12, 10))
    r = path_boxes(d)
    assert r['milestone']['name'] == 'Completion'
    names = [b['name'] for b in r['boxes']]
    # box title = the driving ACTIVITY name (leaf), with its full WBS chain in the crumb
    assert 'Foundations work' in names and 'MEP work' in names
    assert len(r['boxes']) == 3
    # the crumb carries the full WBS path, '@'-prefixed
    assert all(b['crumb'].startswith('@') for b in r['boxes'])


def test_path_diff_detects_reroute():
    prev = path_boxes(_sched(['Foundations', 'Structure', 'Roof'], datetime(2027, 1, 5), datetime(2026, 12, 10)))
    curr = path_boxes(_sched(['Foundations', 'Structure', 'MEP'], datetime(2027, 1, 23), datetime(2026, 12, 10)))
    diff = path_diff(prev['boxes'], curr['boxes'])
    entered = [b['name'] for b in diff['entered']]
    left = [b['name'] for b in diff['left']]
    assert 'MEP work' in entered
    assert 'Roof work' in left
    assert any(b['name'] == 'Foundations work' for b in diff['stayed'])


def test_milestone_list_across_schedules():
    a = _sched(['Foundations', 'MEP'], datetime(2027, 1, 23), datetime(2026, 12, 10))
    ms = milestone_list({'current': a})
    assert any(m['id'] == 'M999' and m['name'] == 'Completion' for m in ms)
