from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.leads import run_leads
from p6_audit.scoring import linear_score, uniform_grade

CONFIG = {'audit': {}}


def _g(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W', 'category': None}
    b.update(kw); return b


def test_negative_lag_fs_flagged_high():
    # a --FS(-5)--> b : negative lag = a lead, flagged on the successor (b)
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': -5}])
    r = run_leads(g, CONFIG)
    assert len(r['findings']) == 1
    f = r['findings'][0]
    assert f['activity_id'] == 'b'            # successor
    assert f['activity_name'] == 'Act b'
    assert f['predecessor_id'] == 'a'
    assert f['predecessor_name'] == 'Act a'
    assert f['rel_type'] == 'FS'
    assert f['lag_days'] == -5
    assert f['wbs_path'] == 'P > W'           # successor's WBS
    assert f['severity'] == 'High'
    assert f['recommendation'] == 'Remove the lead, or model the real overlap as its own activity'


def test_positive_lag_not_flagged():
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 10}])
    r = run_leads(g, CONFIG)
    assert r['findings'] == []
    assert r['kpis']['leads'] == 0


def test_zero_lag_not_flagged():
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    assert run_leads(g, CONFIG)['findings'] == []


def test_critical_successor_is_critical():
    g = _g({'a': _act('a'), 'b': _act('b', is_critical=True)},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'SS', 'lag_days': -3}])
    f = run_leads(g, CONFIG)['findings'][0]
    assert f['severity'] == 'Critical'
    assert f['rel_type'] == 'SS'


def test_finding_id_uses_content_id():
    from p6_audit.findings import content_id
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': -5}])
    f = run_leads(g, CONFIG)['findings'][0]
    assert f['finding_id'] == content_id('LEAD', 'b', str(-5))


def test_kpis_pct_score_grade_and_module():
    # 1 lead of 2 relationships -> 50%
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': -5},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'FS', 'lag_days': 0}])
    r = run_leads(g, CONFIG)
    k = r['kpis']
    assert k['total_relationships'] == 2
    assert k['leads'] == 1
    assert k['lead_pct'] == 50.0
    assert k['target'] == 0
    assert r['pct'] == 50.0
    assert r['score'] == linear_score(50.0)
    assert r['grade'] == uniform_grade(r['score'])
    assert r['module'] == 'leads'
    assert r['name'] == 'Leads'


def test_no_relationships_zero_pct():
    g = _g({'a': _act('a')}, [])
    r = run_leads(g, CONFIG)
    assert r['kpis']['total_relationships'] == 0
    assert r['kpis']['leads'] == 0
    assert r['pct'] == 0.0
    assert r['score'] == 100.0
