from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph


def _data():
    data = ScheduleData()
    data.activities = {
        'a': {'object_id': 'a', 'id': 'A1', 'name': 'Mob', 'task_type': 'Task',
              'is_critical': True, 'wbs_path': 'P > Enable'},
        'b': {'object_id': 'b', 'id': 'A2', 'name': 'Survey', 'task_type': 'Task',
              'is_critical': False, 'wbs_path': 'P > Enable'},
        'm': {'object_id': 'm', 'id': 'A0', 'name': 'Start', 'task_type': 'StartMilestone',
              'is_critical': True, 'wbs_path': 'P'},
    }
    data.relationships = [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0.0}]
    return data


def test_successors_and_predecessors():
    g = ScheduleGraph(_data())
    assert g.succs_of('a')[0]['other'] == 'b'
    assert g.succs_of('a')[0]['type'] == 'FS'
    assert g.preds_of('b')[0]['other'] == 'a'
    assert g.succs_of('b') == []


def test_is_real_activity_excludes_milestones():
    g = ScheduleGraph(_data())
    assert g.is_real_activity('a') is True
    assert g.is_real_activity('m') is False


def test_critical_ids():
    g = ScheduleGraph(_data())
    assert g.critical_ids() == {'a', 'm'}


def test_wbs_path_reads_from_activity():
    g = ScheduleGraph(_data())
    assert g.wbs_path('b') == 'P > Enable'


def test_unknown_relationship_endpoints_are_skipped():
    # C1: cross-project links or dangling references must not raise KeyError
    data = ScheduleData()
    data.activities = {'a': {'object_id': 'a', 'id': 'A1', 'name': 'x', 'task_type': 'Task',
                             'is_critical': False, 'wbs_path': ''}}
    data.relationships = [
        {'pred_id': 'a', 'succ_id': 'UNKNOWN', 'type': 'FS', 'lag_days': 0.0},
        {'pred_id': 'MISSING', 'succ_id': 'a', 'type': 'FS', 'lag_days': 0.0},
    ]
    g = ScheduleGraph(data)
    assert g.succs_of('a') == []
    assert g.preds_of('a') == []


def test_plan_aliases_work():
    g = ScheduleGraph(_data())
    assert g.successors('a') == g.succs_of('a')
    assert g.predecessors('b') == g.preds_of('b')
