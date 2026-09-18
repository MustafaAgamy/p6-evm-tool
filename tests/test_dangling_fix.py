"""Dangling Resolve & Correct — engine enrichment.

Each dangling finding gains structured, applyable fix data (additive; detection unchanged):
per-side ties, a concrete type-change fix when a wrong-type link exists, or a 'review' marker
when there is no link at all on that side.
"""
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.dangling import run_dangling

CONFIG = {'audit': {}}


def _g(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W', 'category': None}
    b.update(kw); return b


def _by(g):
    return {f['activity_id']: f for f in run_dangling(g, CONFIG)['findings']}


def test_start_dangling_wrong_type_pred_gives_change_fix():
    # a --FF--> b --FS--> c : b start not driven (FF only), b finish driven (FS). Start is fixable.
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FF', 'lag_days': 2.0},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'FS', 'lag_days': 0}])
    b = _by(g)['b']
    assert b['start_dangling'] is True and b['finish_dangling'] is False
    fx = b['start_fix']
    assert fx['kind'] == 'change'
    assert fx['target_id'] == 'a'
    assert fx['current_type'] == 'FF'
    assert fx['current_lag_days'] == 2.0
    assert fx['recommended_type'] == 'FS'
    assert fx['alt_type'] == 'SS'
    assert any(c['id'] == 'a' for c in fx['candidates'])
    # finish side is fine → no finish_fix (or a benign absence)
    assert b.get('finish_fix') in (None, {}) or b['finish_fix'].get('kind') != 'change'


def test_finish_dangling_wrong_type_succ_gives_change_fix():
    # a --FS--> b --SS--> c : b start driven (FS), b finish not driven (SS only). Finish is fixable.
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'SS', 'lag_days': 1.5}])
    b = _by(g)['b']
    assert b['finish_dangling'] is True and b['start_dangling'] is False
    fx = b['finish_fix']
    assert fx['kind'] == 'change'
    assert fx['target_id'] == 'c'
    assert fx['current_type'] == 'SS'
    assert fx['current_lag_days'] == 1.5
    assert fx['recommended_type'] == 'FS'
    assert fx['alt_type'] == 'FF'


def test_no_pred_gives_review_start_fix():
    # a --FS--> b : 'a' has no predecessor → start review; a finish is driven (FS succ) so no finish issue.
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    a = _by(g)['a']
    assert a['start_dangling'] is True
    assert a['start_fix']['kind'] == 'review'
    assert not a['start_fix'].get('candidates')


def test_isolated_activity_both_sides_review():
    g = _g({'x': _act('x')}, [])
    x = _by(g)['x']
    assert x['start_dangling'] and x['finish_dangling']
    assert x['start_fix']['kind'] == 'review'
    assert x['finish_fix']['kind'] == 'review'


def test_ties_carry_codes_types_lags():
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FF', 'lag_days': 2.0},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'SS', 'lag_days': 0}])
    b = _by(g)['b']
    pred = next(t for t in b['pred_ties'] if t['id'] == 'a')
    assert pred['type'] == 'FF' and pred['lag_days'] == 2.0 and pred['name'] == 'Act a'
    succ = next(t for t in b['succ_ties'] if t['id'] == 'c')
    assert succ['type'] == 'SS'


def test_existing_fields_preserved():
    # The enrichment must not change or drop the legacy display/report fields.
    g = _g({'x': _act('x')}, [])
    x = _by(g)['x']
    assert 'Predecessor:' in x['suggested_fix'] and 'Successor:' in x['suggested_fix']
    assert x['suggested_fix_2'] != x['suggested_fix']
    assert x['predecessors'] == 'No Predecessor' and x['successors'] == 'No Successor'
    assert 'recommendation' not in x
