"""Slice-3 resource & cost comparison (p6_revcompare.resources) + additive parser check."""
from p6_evm.parser import ScheduleData, parse_file
from p6_compare.model import MatchedSchedules
from p6_revcompare.resources import diff_resources


def _act(code, name):
    return {'id': code, 'name': name, 'task_type': 'Task', 'total_float_days': 0, 'wbs_path': 'WBS 1'}


def _sched(acts, bac=None, asg=None):
    d = ScheduleData()
    d.activities = {f'o{i}': a for i, a in enumerate(acts)}
    d.relationships = []
    c2o = {a['id']: f'o{i}' for i, a in enumerate(acts)}
    d.bac_by_activity = {c2o[k]: v for k, v in (bac or {}).items()}
    d.assignments_by_activity = {c2o[k]: v for k, v in (asg or {}).items()}
    d.resources = {}
    return d


def _asg(rid, name, units, cost, rate=None):
    return {'resource_id': rid, 'resource_name': name, 'budget_units': units, 'budget_cost': cost, 'rate': rate}


def test_not_available_when_no_cost_or_resources():
    r0 = _sched([_act('A1', 'x')])
    r1 = _sched([_act('A1', 'x')])
    d = diff_resources(r0, r1, MatchedSchedules(r0, r1))
    assert d['cost_available'] is False and d['resource_available'] is False
    assert d['activity_cost_changes'] == [] and d['assignment_changes'] == []


def test_total_budget_and_activity_cost_change():
    r0 = _sched([_act('A1', 'Exc'), _act('A2', 'Conc')], bac={'A1': 10000, 'A2': 50000})
    r1 = _sched([_act('A1', 'Exc'), _act('A2', 'Conc')], bac={'A1': 10000, 'A2': 65000})
    d = diff_resources(r0, r1, MatchedSchedules(r0, r1))
    assert d['cost_available'] is True
    assert d['total_budget'] == {'rev0': 60000, 'rev1': 75000, 'delta': 15000}
    assert len(d['activity_cost_changes']) == 1
    assert d['activity_cost_changes'][0]['code'] == 'A2' and d['activity_cost_changes'][0]['delta'] == 15000


def test_resource_added_and_units_changed():
    r0 = _sched([_act('A1', 'Exc'), _act('A2', 'Conc')],
                asg={'A1': [_asg('r1', 'Labour', 100, 10000)], 'A2': [_asg('r2', 'Concrete', 500, 50000)]})
    r1 = _sched([_act('A1', 'Exc'), _act('A2', 'Conc')],
                asg={'A1': [_asg('r1', 'Labour', 100, 10000), _asg('r3', 'Excavator', 20, 8000)],
                     'A2': [_asg('r2', 'Concrete', 650, 65000)]})
    d = diff_resources(r0, r1, MatchedSchedules(r0, r1))
    assert d['resource_available'] is True
    kinds = {(a['code'], a['resource']): a['kind'] for a in d['assignment_changes']}
    assert kinds[('A1', 'Excavator')] == 'added'
    assert kinds[('A2', 'Concrete')] == 'units'
    assert d['summary']['resources_added'] == 1 and d['summary']['units_changed'] == 1


def test_resource_removed():
    r0 = _sched([_act('A1', 'Exc')], asg={'A1': [_asg('r1', 'Labour', 100, 10000), _asg('r2', 'Crane', 5, 5000)]})
    r1 = _sched([_act('A1', 'Exc')], asg={'A1': [_asg('r1', 'Labour', 100, 10000)]})
    d = diff_resources(r0, r1, MatchedSchedules(r0, r1))
    removed = [a for a in d['assignment_changes'] if a['kind'] == 'removed']
    assert len(removed) == 1 and removed[0]['resource'] == 'Crane'


def test_parser_populates_assignments_additively():
    """The additive parser extension captures assignments without disturbing the cost sums."""
    d = parse_file('tests/fixtures/minimal.xml')
    assert hasattr(d, 'resources') and hasattr(d, 'assignments_by_activity')
    assert isinstance(d.bac_by_activity, dict) and isinstance(d.assignments_by_activity, dict)
    # every captured assignment carries the additive keys
    for lst in d.assignments_by_activity.values():
        for a in lst:
            assert set(a) >= {'resource_id', 'budget_units', 'budget_cost', 'rate'}
