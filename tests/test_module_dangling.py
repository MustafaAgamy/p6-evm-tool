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


def test_no_pred_no_succ_is_start_and_finish_high():
    g = _g({'a': _act('a')}, [])
    r = run_dangling(g, CONFIG)
    f = r['findings'][0]
    assert f['logic_issue'] == 'Dangling Start + Dangling Finish'
    assert f['severity'] == 'High'
    assert f['predecessors'] == 'No Predecessor'
    assert f['successors'] == 'No Successor'
    # Fix 1 is the FS two-part solution (generic, no activity ids)
    assert 'Predecessor:' in f['suggested_fix'] and 'Successor:' in f['suggested_fix']
    assert 'FS' in f['suggested_fix']
    # Fix 2 uses the alternative types (SS predecessor / FF successor), and differs
    assert f['suggested_fix_2'] != f['suggested_fix']
    assert 'SS' in f['suggested_fix_2'] and 'FF' in f['suggested_fix_2']
    assert 'recommendation' not in f          # Recommendation column removed


def test_fix_is_generic_no_activity_ids():
    # a --FS--> b, b --SS--> ZZZ. b start driven (FS), finish dangling (only SS succ).
    g = _g({'a': _act('a'), 'b': _act('b'), 'ZZZ': _act('ZZZ')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0},
            {'pred_id': 'b', 'succ_id': 'ZZZ', 'type': 'SS', 'lag_days': 0}])
    b = {f['activity_id']: f for f in run_dangling(g, CONFIG)['findings']}['b']
    assert b['logic_issue'] == 'Dangling Finish'
    assert 'change relationship to FS' in b['suggested_fix']
    assert 'change relationship to FF' in b['suggested_fix_2']
    assert 'Predecessor: OK' in b['suggested_fix']       # start already driven
    # generic — the successor activity id is NOT embedded in the fix text
    assert 'ZZZ' not in b['suggested_fix'] and 'ZZZ' not in b['suggested_fix_2']


def test_no_pred_adds_predecessor_relationship():
    # a --FS--> b : 'a' has no predecessor (dangling start)
    g = _g({'a': _act('a', wbs_path='Civil > Silo 8'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    a = {f['activity_id']: f for f in run_dangling(g, CONFIG)['findings']}['a']
    assert a['logic_issue'] == 'Dangling Start'
    assert 'add relationship (FS)' in a['suggested_fix']
    assert 'Silo 8' not in a['suggested_fix']            # WBS no longer embedded
    assert 'Successor: OK' in a['suggested_fix']


def test_ss_pred_only_flags_finish_only_medium():
    # a --SS--> b, and b has no successor: b start is driven (SS), finish dangles
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'SS', 'lag_days': 0}])
    by = {f['activity_id']: f for f in run_dangling(g, CONFIG)['findings']}
    assert by['b']['logic_issue'] == 'Dangling Finish'
    assert by['b']['severity'] == 'Medium'


def test_fully_linked_not_flagged():
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'FS', 'lag_days': 0}])
    ids = [f['activity_id'] for f in run_dangling(g, CONFIG)['findings']]
    assert 'b' not in ids   # b is fully linked


def test_one_row_per_activity():
    g = _g({'a': _act('a')}, [])
    rows = [f for f in run_dangling(g, CONFIG)['findings'] if f['activity_id'] == 'a']
    assert len(rows) == 1


def test_critical_path_bumps_severity():
    g = _g({'a': _act('a', is_critical=True)}, [])  # both ends -> High, critical -> Critical
    assert run_dangling(g, CONFIG)['findings'][0]['severity'] == 'Critical'


def test_predecessor_string_lists_activity_and_type():
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    by = {f['activity_id']: f for f in run_dangling(g, CONFIG)['findings']}
    # b has a predecessor 'a' (FS) -> its start is fine; but b has no successor -> finish dangling
    assert 'a' in by['b']['predecessors'] and 'FS' in by['b']['predecessors']


def test_kpis_pct_score_grade():
    # 1 dangling of 2 real activities -> 50%
    g = _g({'a': _act('a'), 'b': _act('b')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0}])
    r = run_dangling(g, CONFIG)
    k = r['kpis']
    assert k['total_activities'] == 2
    assert k['total_dangling'] >= 1
    assert r['pct'] == round(100.0 * k['total_dangling'] / k['total_activities'], 1)
    assert r['grade'] == 'Critical'      # well over 8%
    assert r['module'] == 'dangling'


def test_milestones_excluded():
    g = _g({'m': _act('m', task_type='StartMilestone')}, [])
    assert run_dangling(g, CONFIG)['findings'] == []
