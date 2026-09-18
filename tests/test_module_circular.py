from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.circular import run_circular, MODULE, NAME

CONFIG = {'audit': {}}


def _g(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W', 'category': None}
    b.update(kw); return b


def _rel(p, s, t='FS'):
    return {'pred_id': p, 'succ_id': s, 'type': t, 'lag_days': 0}


# ── acyclic ────────────────────────────────────────────────────────────────
def test_acyclic_chain_has_no_loops():
    # a -> b -> c is a clean FS chain: no cycle
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [_rel('a', 'b'), _rel('b', 'c')])
    r = run_circular(g, CONFIG)
    assert r['kpis']['loops'] == 0
    assert r['kpis']['activities_in_loops'] == 0
    assert r['kpis']['longest_loop'] == 0
    assert r['blocking'] is False
    assert r['pct'] == 0.0
    assert r['score'] == 100.0
    assert r['grade'] == 'Excellent'
    assert r['findings'] == []


def test_module_identity_and_blocking_key_present():
    g = _g({'a': _act('a')}, [])
    r = run_circular(g, CONFIG)
    assert r['module'] == MODULE == 'circular'
    assert r['name'] == NAME == 'Circular Logic'
    assert 'blocking' in r
    assert r['blocking'] is False


# ── one planted cycle ───────────────────────────────────────────────────────
def test_planted_cycle_detected():
    # a -> b -> c -> a  is a closed loop
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [_rel('a', 'b'), _rel('b', 'c'), _rel('c', 'a')])
    r = run_circular(g, CONFIG)
    assert r['kpis']['loops'] >= 1
    assert r['blocking'] is True
    assert r['kpis']['activities_in_loops'] == 3
    assert r['kpis']['longest_loop'] == 3
    assert len(r['findings']) >= 1


def test_cycle_finding_shape_and_closure():
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [_rel('a', 'b'), _rel('b', 'c'), _rel('c', 'a')])
    f = run_circular(g, CONFIG)['findings'][0]
    assert f['loop_index'] == 1
    assert f['activity_count'] == 3
    # chain repeats the first activity at the end to show the loop closes
    assert f['chain'][0]['id'] == f['chain'][-1]['id']
    # closure entry is an extra: three distinct + repeat = four
    assert len(f['chain']) == 4
    ids_in_loop = [c['id'] for c in f['chain'][:-1]]
    assert set(ids_in_loop) == {'a', 'b', 'c'}
    # each chain entry carries id + name
    assert all('id' in c and 'name' in c for c in f['chain'])
    assert f['recommendation'] == 'Break one link in this loop so P6 can calculate a valid schedule'
    assert f['finding_id']  # deterministic id present
    assert f['severity'] == 'Critical'  # a loop stops F9 — nothing milder applies


def test_defect_pct_and_score_for_all_in_loop():
    # every real activity sits in the loop -> 100% defect -> score 0
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [_rel('a', 'b'), _rel('b', 'c'), _rel('c', 'a')])
    r = run_circular(g, CONFIG)
    assert r['pct'] == 100.0
    assert r['score'] == 0.0
    assert r['grade'] == 'Critical'


def test_partial_loop_defect_pct():
    # loop over a,b (2 acts); c,d are clean tail -> 2 of 4 real -> 50%
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c'), 'd': _act('d')},
           [_rel('a', 'b'), _rel('b', 'a'), _rel('b', 'c'), _rel('c', 'd')])
    r = run_circular(g, CONFIG)
    assert r['kpis']['loops'] == 1
    assert r['kpis']['activities_in_loops'] == 2
    assert r['pct'] == 50.0
    assert r['blocking'] is True


# ── two independent loops ───────────────────────────────────────────────────
def test_two_distinct_loops():
    # loop 1: a<->b ; loop 2: c->d->e->c ; f is a free tail
    g = _g({k: _act(k) for k in ('a', 'b', 'c', 'd', 'e', 'f')},
           [_rel('a', 'b'), _rel('b', 'a'),
            _rel('c', 'd'), _rel('d', 'e'), _rel('e', 'c'),
            _rel('e', 'f')])
    r = run_circular(g, CONFIG)
    assert r['kpis']['loops'] == 2
    assert r['kpis']['activities_in_loops'] == 5
    assert r['kpis']['longest_loop'] == 3
    # loop_index is 1-based and unique per finding
    idx = sorted(f['loop_index'] for f in r['findings'])
    assert idx == [1, 2]


def test_findings_have_distinct_ids():
    g = _g({k: _act(k) for k in ('a', 'b', 'c', 'd')},
           [_rel('a', 'b'), _rel('b', 'a'), _rel('c', 'd'), _rel('d', 'c')])
    ids = [f['finding_id'] for f in run_circular(g, CONFIG)['findings']]
    assert len(ids) == len(set(ids)) == 2
