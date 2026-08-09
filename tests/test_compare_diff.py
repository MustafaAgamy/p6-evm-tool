"""diff_logic — compare driving links (baseline vs update) per matched activity.

Operates on driving-link maps (code -> {name, preds:{code:link}, succs:{code:link}}),
so it is a pure dict comparison. Only activities whose driving predecessor/successor
relationship or lag changed appear. driving_link_map bridges a ScheduleGraph to
this shape.
"""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_compare.diff import diff_logic, driving_link_map


def _L(type_, lag, name):
    return {'type': type_, 'lag_days': lag, 'name': name}


def _row_by_id(res, aid):
    return next(r for r in res['rows'] if r['activity_id'] == aid)


def test_lag_change_flagged():
    base = {'A100': {'name': 'Excavate', 'preds': {'A050': _L('FS', 0.0, 'Clearance')}, 'succs': {}}}
    upd = {'A100': {'name': 'Excavate', 'preds': {'A050': _L('FS', 10.0, 'Clearance')}, 'succs': {}}}
    res = diff_logic(base, upd)
    row = _row_by_id(res, 'A100')
    assert row['primary_kind'] == 'lag'
    assert row['change_label'] == 'Lag ↑'
    cell = next(p for p in row['update_preds'] if p['code'] == 'A050')
    assert cell['status'] == 'changed'


def test_type_change_flagged():
    base = {'A200': {'name': 'Rebar', 'preds': {'A230': _L('FS', 0.0, 'Formwork')}, 'succs': {}}}
    upd = {'A200': {'name': 'Rebar', 'preds': {'A230': _L('SS', 2.0, 'Formwork')}, 'succs': {}}}
    res = diff_logic(base, upd)
    assert _row_by_id(res, 'A200')['primary_kind'] == 'type'


def test_added_driving_predecessor():
    base = {'A600': {'name': 'MEP', 'preds': {'A450': _L('FS', 0.0, 'Slab')}, 'succs': {}}}
    upd = {'A600': {'name': 'MEP', 'preds': {'A450': _L('FS', 0.0, 'Slab'),
                                             'A520': _L('FS', 5.0, 'Blockwork')}, 'succs': {}}}
    row = _row_by_id(diff_logic(base, upd), 'A600')
    assert row['primary_kind'] == 'added_driver'
    statuses = {p['code']: p['status'] for p in row['update_preds']}
    assert statuses == {'A450': 'same', 'A520': 'added'}


def test_removed_and_added_is_a_swap():
    base = {'A710': {'name': 'Facade', 'preds': {}, 'succs': {'A800': _L('FS', 0.0, 'Testing')}}}
    upd = {'A710': {'name': 'Facade', 'preds': {}, 'succs': {'A905': _L('FS', 0.0, 'Commissioning')}}}
    row = _row_by_id(diff_logic(base, upd), 'A710')
    assert row['primary_kind'] == 'removed_added'
    assert row['change_label'] == 'Removed + added'
    assert [s['code'] for s in row['baseline_succs'] if s['status'] == 'removed'] == ['A800']
    assert [s['code'] for s in row['update_succs'] if s['status'] == 'added'] == ['A905']


def test_unchanged_activity_excluded_and_summary_counts():
    base = {
        'A100': {'name': 'Excavate', 'preds': {'A050': _L('FS', 0.0, 'C')}, 'succs': {}},
        'A900': {'name': 'Steady', 'preds': {'A800': _L('FS', 0.0, 'X')}, 'succs': {}},
    }
    upd = {
        'A100': {'name': 'Excavate', 'preds': {'A050': _L('FS', 5.0, 'C')}, 'succs': {}},
        'A900': {'name': 'Steady', 'preds': {'A800': _L('FS', 0.0, 'X')}, 'succs': {}},
    }
    res = diff_logic(base, upd)
    assert [r['activity_id'] for r in res['rows']] == ['A100']   # A900 unchanged, excluded
    assert res['summary']['changed_activities'] == 1
    assert res['summary']['by_kind'] == {'lag': 1}


def test_driving_link_map_from_graph():
    d = ScheduleData()
    d.activities = {
        'P': {'id': 'A050', 'name': 'Clearance', 'task_type': 'Task',
              'remaining_early_finish': datetime(2026, 1, 10)},
        'S': {'id': 'A100', 'name': 'Excavate', 'task_type': 'Task',
              'remaining_early_start': datetime(2026, 1, 10)},
    }
    d.relationships = [{'pred_id': 'P', 'succ_id': 'S', 'type': 'FS', 'lag_days': 0.0}]
    m = driving_link_map(ScheduleGraph(d))
    assert m['A100']['preds'] == {'A050': {'type': 'FS', 'lag_days': 0.0, 'name': 'Clearance'}}
    assert m['A100']['name'] == 'Excavate'
