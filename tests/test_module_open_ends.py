from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.open_ends import run_open_ends
from p6_audit.scoring import linear_score, uniform_grade

CONFIG = {'audit': {}}


def _g(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W', 'category': None}
    b.update(kw); return b


def test_isolated_activity_is_both_missing_high():
    g = _g({'a': _act('a')}, [])
    r = run_open_ends(g, CONFIG)
    f = r['findings'][0]
    assert f['issue'] == 'No predecessor + no successor'
    assert f['severity'] == 'High'
    # successor is missing -> point it at its downstream work
    assert f['recommendation'] == 'Link to its downstream work (FS)'
    assert f['finding_id']
    assert f['activity_id'] == 'a'
    assert f['activity_name'] == 'Act a'
    assert f['wbs_path'] == 'P > W'


def test_middle_activity_fully_linked_not_flagged():
    # a --FS--> b --FS--> c : b has both a predecessor and a successor
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'FS', 'lag_days': 0}])
    ids = [f['activity_id'] for f in run_open_ends(g, CONFIG)['findings']]
    assert 'b' not in ids


def test_no_successor_only_high():
    # a --FS--> b : 'a' has a successor but no predecessor;
    #              'b' has a predecessor but no successor
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    by = {f['activity_id']: f for f in run_open_ends(g, CONFIG)['findings']}
    assert by['b']['issue'] == 'No successor'
    assert by['b']['severity'] == 'High'
    assert by['b']['recommendation'] == 'Link to its downstream work (FS)'


def test_no_predecessor_only_medium():
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    by = {f['activity_id']: f for f in run_open_ends(g, CONFIG)['findings']}
    assert by['a']['issue'] == 'No predecessor'
    assert by['a']['severity'] == 'Medium'
    assert by['a']['recommendation'] == 'Link from its upstream work (FS)'


def test_start_milestone_excluded():
    g = _g({'m': _act('m', task_type='StartMilestone')}, [])
    assert run_open_ends(g, CONFIG)['findings'] == []


def test_critical_activity_bumps_severity():
    # both-missing base is High; critical -> Critical
    g = _g({'a': _act('a', is_critical=True)}, [])
    assert run_open_ends(g, CONFIG)['findings'][0]['severity'] == 'Critical'
    # no-predecessor base is Medium; critical -> High
    g2 = _g({'a': _act('a'), 'b': _act('b', is_critical=True)},
            [{'pred_id': 'b', 'succ_id': 'a', 'type': 'FS', 'lag_days': 0}])
    by = {f['activity_id']: f for f in run_open_ends(g2, CONFIG)['findings']}
    assert by['b']['issue'] == 'No predecessor'
    assert by['b']['severity'] == 'High'


def test_finding_id_stable_and_content_based():
    g = _g({'a': _act('a')}, [])
    id1 = run_open_ends(g, CONFIG)['findings'][0]['finding_id']
    id2 = run_open_ends(g, CONFIG)['findings'][0]['finding_id']
    assert id1 == id2


def test_findings_sorted_by_severity_then_id():
    # z: isolated (High, both missing); a: successor only missing? build a spread.
    # x --FS--> y : x no pred (Medium), y no succ (High). z isolated (High).
    g = _g({'x': _act('x'), 'y': _act('y'), 'z': _act('z')},
           [{'pred_id': 'x', 'succ_id': 'y', 'type': 'FS', 'lag_days': 0}])
    findings = run_open_ends(g, CONFIG)['findings']
    order = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
    keys = [(order[f['severity']], f['activity_id']) for f in findings]
    assert keys == sorted(keys)
    # High severities (y, z) come before the Medium (x)
    assert keys[-1][1] == 'x'


def test_kpis_pct_score_grade_module():
    # a --FS--> b : both a and b are open ends (a no pred, b no succ) of 2 real acts
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    r = run_open_ends(g, CONFIG)
    k = r['kpis']
    assert k['total_activities'] == 2
    assert k['open_ends'] == 2
    assert k['no_predecessor'] == 1   # a
    assert k['no_successor'] == 1     # b
    assert k['open_end_pct'] == 100.0
    assert r['pct'] == k['open_end_pct']
    assert r['score'] == linear_score(r['pct'])
    assert r['grade'] == uniform_grade(r['score'])
    assert r['module'] == 'open_ends'
    assert r['name'] == 'Open Ends'


def test_no_open_ends_pct_zero():
    # a --FS--> b --FS--> a would loop; instead make a closed pair with a milestone anchor.
    # a --FS--> b, b --FS--> a is a cycle; keep it simple: both linked both directions.
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0},
            {'pred_id': 'b', 'succ_id': 'a', 'type': 'FS', 'lag_days': 0}])
    r = run_open_ends(g, CONFIG)
    assert r['findings'] == []
    assert r['pct'] == 0.0
    assert r['kpis']['open_end_pct'] == 0.0
