from p6_evm.parser import ScheduleData
from p6_audit.engine import audit_modules

CONFIG = {
    'categories': [],
    'audit': {'float_threshold_days': 44},
}


def _data():
    d = ScheduleData()
    d.wbs = {'w': {'name': 'Civil', 'parent_object_id': None}}
    d.activities = {
        'a': {'object_id': 'a', 'id': 'A1', 'name': 'Mob', 'task_type': 'Task',
              'wbs_id': 'w', 'is_critical': False, 'total_float_days': 5.0},
        'b': {'object_id': 'b', 'id': 'A2', 'name': 'Excavate', 'task_type': 'Task',
              'wbs_id': 'w', 'is_critical': False, 'total_float_days': 90.0},
    }
    d.relationships = [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}]
    return d


def test_returns_isolated_modules():
    out = audit_modules(_data(), CONFIG)
    assert set(out['modules'].keys()) == {
        'dangling', 'float', 'out_of_sequence', 'lag_lead',
        'open_ends', 'relationship_types', 'hard_constraints', 'high_duration',
        'leads', 'negative_float', 'whole_day', 'circular', 'cpli'}
    assert out['module_order'] == [
        'dangling', 'float', 'out_of_sequence', 'lag_lead',
        'open_ends', 'relationship_types', 'hard_constraints', 'high_duration',
        'leads', 'negative_float', 'whole_day', 'circular', 'cpli']
    # each module carries its own score/grade/findings/kpis — nothing shared
    for key in ('dangling', 'float', 'out_of_sequence'):
        m = out['modules'][key]
        assert 'score' in m and 'grade' in m and 'kpis' in m and 'findings' in m
    # float found the 90-day activity
    assert out['modules']['float']['kpis']['above_threshold'] == 1
    # dangling found the open ends (a has no pred, b has no succ)
    assert out['modules']['dangling']['kpis']['total_dangling'] >= 1


def test_no_overall_score_key():
    out = audit_modules(_data(), CONFIG)
    assert 'overall' not in out           # overall Health Score is deferred
    assert 'scores' not in out
