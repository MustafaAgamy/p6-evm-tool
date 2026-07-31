from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.checks.circular import check_circular

CONFIG = {'audit': {'default_severity': 'Medium', 'category_severity': {}}}


def _g(rels, ids):
    d = ScheduleData()
    d.activities = {i: {'object_id': i, 'id': i, 'name': i, 'task_type': 'Task',
                        'is_critical': False, 'wbs_path': '', 'category': None} for i in ids}
    d.relationships = [{'pred_id': p, 'succ_id': s, 'type': 'FS', 'lag_days': 0} for p, s in rels]
    return ScheduleGraph(d)


def test_no_cycle_no_findings():
    g = _g([('a', 'b'), ('b', 'c')], ['a', 'b', 'c'])
    assert check_circular(g, CONFIG) == []


def test_three_node_loop_is_one_critical_finding():
    g = _g([('a', 'b'), ('b', 'c'), ('c', 'a')], ['a', 'b', 'c'])
    findings = check_circular(g, CONFIG)
    assert len(findings) == 1
    assert findings[0].severity == 'Critical'
    assert findings[0].check_id == 'LOGIC-003'
    # all three ids appear in the basis chain
    for i in ('a', 'b', 'c'):
        assert i in findings[0].basis


def test_two_independent_loops_two_findings():
    g = _g([('a', 'b'), ('b', 'a'), ('c', 'd'), ('d', 'c')], ['a', 'b', 'c', 'd'])
    assert len(check_circular(g, CONFIG)) == 2
