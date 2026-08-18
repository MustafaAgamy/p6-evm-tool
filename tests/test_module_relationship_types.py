from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.relationship_types import run_relationship_types, MODULE, NAME

CONFIG = {'audit': {}}


def _g(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W'}
    b.update(kw); return b


def _rel(p, s, t='FS', lag=0):
    return {'pred_id': p, 'succ_id': s, 'type': t, 'lag_days': lag}


def test_all_fs_is_clean():
    # a --FS--> b --FS--> c : every relationship is Finish-to-Start
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [_rel('a', 'b', 'FS'), _rel('b', 'c', 'FS')])
    r = run_relationship_types(g, CONFIG)
    k = r['kpis']
    assert k['total_relationships'] == 2
    assert k['fs_pct'] == 100.0
    assert k['ss_pct'] == 0.0
    assert k['ff_pct'] == 0.0
    assert k['sf_pct'] == 0.0
    assert k['non_fs'] == 0
    assert r['findings'] == []
    assert r['pct'] == 0.0
    assert r['score'] == 100


def test_mix_ss_and_sf_gives_two_findings():
    # a --FS--> b (clean), b --SS--> c (defect), c --SF--> d (defect, high)
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c'), 'd': _act('d')},
           [_rel('a', 'b', 'FS'), _rel('b', 'c', 'SS'), _rel('c', 'd', 'SF')])
    r = run_relationship_types(g, CONFIG)
    k = r['kpis']
    assert k['total_relationships'] == 3
    assert k['fs_pct'] == 33.3
    assert k['ss_pct'] == 33.3
    assert k['ff_pct'] == 0.0
    assert k['sf_pct'] == 33.3
    assert k['non_fs'] == 2
    assert r['pct'] == round(100 - 33.3, 1)   # 66.7 — share that is NOT FS

    findings = r['findings']
    assert len(findings) == 2
    by_type = {f['rel_type']: f for f in findings}

    # SF is the worst offender — raised to High
    sf = by_type['SF']
    assert sf['severity'] == 'High'
    assert sf['activity_id'] == 'd'          # successor
    assert sf['activity_name'] == 'Act d'
    assert sf['predecessor_id'] == 'c'       # predecessor (the iterated oid)
    assert sf['predecessor_name'] == 'Act c'
    assert sf['wbs_path'] == 'P > W'          # successor's WBS
    assert 'almost never correct' in sf['recommendation']

    # SS off the critical path — Low (impact-based; Medium only on the critical path)
    ss = by_type['SS']
    assert ss['severity'] == 'Low'
    assert ss['on_critical'] is False
    assert ss['activity_id'] == 'c'          # successor
    assert ss['predecessor_id'] == 'b'
    assert 'Re-type to FS' in ss['recommendation']


def test_severity_is_impact_based_on_the_critical_path():
    # same SS/SF defects, but the endpoints are now critical → severity is raised
    g = _g({'a': _act('a'), 'b': _act('b', is_critical=True),
            'c': _act('c', is_critical=True), 'd': _act('d', is_critical=True)},
           [_rel('a', 'b', 'FS'), _rel('b', 'c', 'SS'), _rel('c', 'd', 'SF')])
    by_type = {f['rel_type']: f for f in run_relationship_types(g, CONFIG)['findings']}
    assert by_type['SS']['severity'] == 'Medium'    # SS on the critical path
    assert by_type['SF']['severity'] == 'Critical'  # SF on the critical path
    assert by_type['SS']['on_critical'] is True


def test_module_identity():
    g = _g({'a': _act('a'), 'b': _act('b')}, [_rel('a', 'b', 'FS')])
    r = run_relationship_types(g, CONFIG)
    assert MODULE == 'relationship_types'
    assert NAME == 'Relationship Types'
    assert r['module'] == 'relationship_types'
    assert r['name'] == 'Relationship Types'
