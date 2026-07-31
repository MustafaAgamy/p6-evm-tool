from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.checks.open_ends import check_open_ends

CONFIG = {'audit': {'default_severity': 'Medium', 'category_severity': {}}}


def _graph(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return ScheduleGraph(d)


def _act(oid, **kw):
    base = {'object_id': oid, 'id': oid, 'name': oid, 'task_type': 'Task',
            'is_critical': False, 'wbs_path': '', 'category': None}
    base.update(kw); return base


def test_missing_successor_is_high():
    g = _graph({'a': _act('a'), 'b': _act('b')},
               [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    findings = check_open_ends(g, CONFIG)
    # 'a' has no predecessor (Medium), 'b' has no successor (High)
    by_act = {f.activity_id: f for f in findings}
    assert by_act['b'].severity == 'High'
    assert 'successor' in by_act['b'].summary.lower()
    assert by_act['a'].severity == 'Medium'
    assert 'predecessor' in by_act['a'].summary.lower()


def test_start_and_finish_milestones_ignored():
    g = _graph({'m': _act('m', task_type='StartMilestone'),
                'f': _act('f', task_type='FinishMilestone')}, [])
    assert check_open_ends(g, CONFIG) == []


def test_critical_open_end_escalates():
    g = _graph({'a': _act('a', is_critical=True), 'b': _act('b')},
               [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    a = {f.activity_id: f for f in check_open_ends(g, CONFIG)}['a']
    assert a.severity == 'Critical'
