from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.hard_constraints import run_hard_constraints

CONFIG = {'audit': {}}


def _g(acts):
    d = ScheduleData(); d.activities = acts; d.relationships = []
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W', 'category': None,
         'constraint_type': None, 'constraint_date': None}
    b.update(kw); return b


def test_mandatory_finish_flagged_high():
    g = _g({'a': _act('a', constraint_type='Mandatory Finish',
                      constraint_date='2026-09-01')})
    r = run_hard_constraints(g, CONFIG)
    f = r['findings'][0]
    assert f['activity_id'] == 'a'
    assert f['constraint_type'] == 'Mandatory Finish'
    assert f['constraint_date'] == '2026-09-01'
    assert f['severity'] == 'High'
    assert 'Replace with logic' in f['recommendation']


def test_soft_constraint_not_flagged():
    # 'Start On or After' is a SOFT constraint -> never flagged
    g = _g({'a': _act('a', constraint_type='Start On or After')})
    r = run_hard_constraints(g, CONFIG)
    assert r['findings'] == []
    assert r['kpis']['hard_count'] == 0


def test_no_constraint_not_flagged():
    g = _g({'a': _act('a', constraint_type=None)})
    assert run_hard_constraints(g, CONFIG)['findings'] == []


def test_start_on_and_finish_on_are_hard_medium():
    # 'Start On' / 'Finish On' are HARD but not Mandatory -> Medium
    g = _g({'a': _act('a', constraint_type='Start On'),
            'b': _act('b', constraint_type='Finish On')})
    by = {f['activity_id']: f for f in run_hard_constraints(g, CONFIG)['findings']}
    assert by['a']['severity'] == 'Medium'
    assert by['b']['severity'] == 'Medium'


def test_critical_bumps_to_critical():
    # Even a Mandatory constraint (base High) becomes Critical on the critical path
    g = _g({'a': _act('a', constraint_type='Mandatory Start', is_critical=True)})
    f = run_hard_constraints(g, CONFIG)['findings'][0]
    assert f['severity'] == 'Critical'


def test_finding_id_stable():
    g = _g({'a': _act('a', constraint_type='Mandatory Finish')})
    f1 = run_hard_constraints(g, CONFIG)['findings'][0]['finding_id']
    f2 = run_hard_constraints(g, CONFIG)['findings'][0]['finding_id']
    assert f1 == f2 and f1


def test_kpis_pct_score_grade_module():
    # 1 hard of 2 real activities -> 50%
    g = _g({'a': _act('a', constraint_type='Mandatory Finish'),
            'b': _act('b', constraint_type='Start On or After')})  # soft, not counted
    r = run_hard_constraints(g, CONFIG)
    k = r['kpis']
    assert k['total_activities'] == 2
    assert k['hard_count'] == 1
    assert k['hard_pct'] == 50.0
    assert k['by_type'] == {'Mandatory Finish': 1}
    assert r['pct'] == 50.0
    assert r['score'] == 50.0          # linear_score(50) = 100 - 50
    assert r['grade'] == 'Critical'    # score < 90
    assert r['module'] == 'hard_constraints'
    assert r['name'] == 'Hard Constraints'


def test_by_type_counts_each_hard_type():
    g = _g({'a': _act('a', constraint_type='Mandatory Finish'),
            'b': _act('b', constraint_type='Mandatory Finish'),
            'c': _act('c', constraint_type='Start On')})
    k = run_hard_constraints(g, CONFIG)['kpis']
    assert k['by_type'] == {'Mandatory Finish': 2, 'Start On': 1}
    assert k['hard_count'] == 3


def test_milestones_excluded():
    g = _g({'m': _act('m', task_type='StartMilestone',
                      constraint_type='Mandatory Start')})
    r = run_hard_constraints(g, CONFIG)
    assert r['findings'] == []
    assert r['kpis']['total_activities'] == 0
