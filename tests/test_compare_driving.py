"""Driving-link derivation.

A predecessor link is "driving" when the date it imposes on the successor equals
(within tolerance) the successor's remaining early start/finish — i.e. the working
days between the predecessor's controlling date and the successor's anchor equal
the link's lag. Co-driving links (ties) are all returned. P6 doesn't export a
driving flag, so we derive it from the remaining early dates + lag.
"""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_compare.driving import driving_predecessors, driving_successors


def _d(m, day):
    return datetime(2026, m, day)


def _graph(activities, relationships):
    d = ScheduleData()
    d.activities = activities
    d.relationships = relationships
    return ScheduleGraph(d)


def test_only_the_binding_predecessor_drives():
    g = _graph(
        {'P': {'id': 'P', 'name': 'P', 'task_type': 'Task', 'remaining_early_finish': _d(1, 10)},
         'Q': {'id': 'Q', 'name': 'Q', 'task_type': 'Task', 'remaining_early_finish': _d(1, 5)},
         'S': {'id': 'S', 'name': 'S', 'task_type': 'Task', 'remaining_early_start': _d(1, 10)}},
        [{'pred_id': 'P', 'succ_id': 'S', 'type': 'FS', 'lag_days': 0.0},
         {'pred_id': 'Q', 'succ_id': 'S', 'type': 'FS', 'lag_days': 0.0}])
    drv = driving_predecessors(g, 'S')
    assert [x['pred_oid'] for x in drv] == ['P']


def test_co_driving_predecessors_both_returned():
    g = _graph(
        {'P': {'id': 'P', 'name': 'P', 'task_type': 'Task', 'remaining_early_finish': _d(1, 10)},
         'R': {'id': 'R', 'name': 'R', 'task_type': 'Task', 'remaining_early_finish': _d(1, 10)},
         'S': {'id': 'S', 'name': 'S', 'task_type': 'Task', 'remaining_early_start': _d(1, 10)}},
        [{'pred_id': 'P', 'succ_id': 'S', 'type': 'FS', 'lag_days': 0.0},
         {'pred_id': 'R', 'succ_id': 'S', 'type': 'FS', 'lag_days': 0.0}])
    drv = sorted(x['pred_oid'] for x in driving_predecessors(g, 'S'))
    assert drv == ['P', 'R']


def test_lag_accounted_for():
    # pred finish 5 Jan, FS+3, successor start 8 Jan → 3 working days == lag → driving
    g = _graph(
        {'P': {'id': 'P', 'name': 'P', 'task_type': 'Task', 'remaining_early_finish': _d(1, 5)},
         'S': {'id': 'S', 'name': 'S', 'task_type': 'Task', 'remaining_early_start': _d(1, 8)}},
        [{'pred_id': 'P', 'succ_id': 'S', 'type': 'FS', 'lag_days': 3.0}])
    assert [x['pred_oid'] for x in driving_predecessors(g, 'S')] == ['P']


def test_driving_successors_symmetric():
    g = _graph(
        {'A': {'id': 'A', 'name': 'A', 'task_type': 'Task', 'remaining_early_finish': _d(1, 10)},
         'B': {'id': 'B', 'name': 'B', 'task_type': 'Task', 'remaining_early_start': _d(1, 10)}},
        [{'pred_id': 'A', 'succ_id': 'B', 'type': 'FS', 'lag_days': 0.0}])
    drv = driving_successors(g, 'A')
    assert [x['succ_oid'] for x in drv] == ['B']
