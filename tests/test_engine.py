from p6_evm.parser import ScheduleData
from p6_audit import audit

CONFIG = {
    'categories': [{'name': 'Construction', 'weight': 0.95, 'wbs_match': 'Construction'}],
    'audit': {
        'default_severity': 'Medium', 'category_severity': {'Construction': 'High'},
        'float_threshold_days': 44,
        'severity_penalties': {'Critical': 25, 'High': 12, 'Medium': 5, 'Low': 2},
        'category_weights': {'Schedule Logic': 0.5, 'Float Analysis': 0.5},
    },
}


def _data():
    d = ScheduleData()
    d.wbs = {'w': {'name': 'Construction', 'parent_object_id': None}}
    d.activities = {
        'a': {'object_id': 'a', 'id': 'A1', 'name': 'Mob', 'task_type': 'Task',
              'wbs_id': 'w', 'is_critical': False, 'total_float_days': 5.0, 'free_float_days': 5.0},
        'b': {'object_id': 'b', 'id': 'A2', 'name': 'Excavate', 'task_type': 'Task',
              'wbs_id': 'w', 'is_critical': False, 'total_float_days': 5.0, 'free_float_days': 5.0},
    }
    d.relationships = [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}]
    return d


def test_audit_returns_findings_scores_counts():
    out = audit(_data(), CONFIG)
    assert 'findings' in out and 'scores' in out and 'counts' in out
    # a has no predecessor, b has no successor -> 2 open-end findings
    assert out['counts']['total'] >= 2
    assert out['scores']['overall']['categories_total'] == 2
    # findings are dicts carrying the standard keys
    assert out['findings'][0]['activity_id']
    assert out['findings'][0]['wbs_path'] == 'Construction'


def test_findings_sorted_critical_first():
    out = audit(_data(), CONFIG)
    order = ['Critical', 'High', 'Medium', 'Low']
    ranks = [order.index(f['severity']) for f in out['findings']]
    assert ranks == sorted(ranks)
