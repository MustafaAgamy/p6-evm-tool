"""diff_logic — compare driving links (baseline vs update) per matched activity.

Operates on driving-link maps (code -> {name, preds:{code:link}, succs:{code:link}}),
so it is a pure dict comparison. Only activities whose driving predecessor/successor
relationship or lag changed appear. driving_link_map bridges a ScheduleGraph to
this shape.
"""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_compare.model import MatchedSchedules
from p6_compare.diff import diff_logic, driving_link_map, diff_durations, diff_relationships, _dur_impact


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
    # Driving predecessor swapped: A800 removed, A905 added → one row, "Removed + added".
    base = {'A710': {'name': 'Facade', 'preds': {'A800': _L('FS', 0.0, 'Testing')}, 'succs': {}}}
    upd = {'A710': {'name': 'Facade', 'preds': {'A905': _L('FS', 0.0, 'Commissioning')}, 'succs': {}}}
    row = _row_by_id(diff_logic(base, upd), 'A710')
    assert row['primary_kind'] == 'removed_added'
    assert row['change_label'] == 'Removed + added'
    assert [s['code'] for s in row['baseline_preds'] if s['status'] == 'removed'] == ['A800']
    assert [s['code'] for s in row['update_preds'] if s['status'] == 'added'] == ['A905']


def test_successor_change_is_highlighted_on_the_row():
    # A100's driving successor A200's lag changed — its update_succs must show 'changed',
    # not plain 'same' (the row appears because its predecessor A050 also changed).
    base = {'A100': {'name': 'X', 'preds': {'A050': _L('FS', 0.0, 'P')}, 'succs': {'A200': _L('FS', 0.0, 'S')}}}
    upd = {'A100': {'name': 'X', 'preds': {'A050': _L('FS', 10.0, 'P')}, 'succs': {'A200': _L('FS', 5.0, 'S')}}}
    row = _row_by_id(diff_logic(base, upd), 'A100')
    succ = next(s for s in row['update_succs'] if s['code'] == 'A200')
    assert succ['status'] == 'changed'


# ── diff_relationships (all relationships from the files, driving highlighted) ──

def _rel_sched(rels):
    d = ScheduleData()
    d.activities = {'p': {'id': 'A050', 'name': 'Clearance'}, 's': {'id': 'A100', 'name': 'Excavate'}}
    d.relationships = rels
    return d


def test_diff_relationships_shows_all_and_never_blank():
    base = _rel_sched([{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0.0, 'lag_hours': 0.0}])
    upd = _rel_sched([{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 10.0, 'lag_hours': 80.0}])
    res = diff_relationships(MatchedSchedules(base, upd))
    # the lag change shows on BOTH ends (each activity lists its own relationships)
    assert {r['activity_id'] for r in res['rows']} == {'A050', 'A100'}
    row = next(r for r in res['rows'] if r['activity_id'] == 'A100')
    up = next(p for p in row['update_preds'] if p['code'] == 'A050')
    assert up['status'] == 'changed' and up['lag_days'] == 10.0   # populated, never blank


def test_diff_relationships_flags_driving():
    base = _rel_sched([{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0.0, 'lag_hours': 0.0}])
    upd = _rel_sched([{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 10.0, 'lag_hours': 80.0}])
    res = diff_relationships(MatchedSchedules(base, upd), driving={('A050', 'A100')})
    row = next(r for r in res['rows'] if r['activity_id'] == 'A100')
    assert next(p for p in row['update_preds'] if p['code'] == 'A050')['driving'] is True


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


def _dur_sched(entries):
    # entries: {code: (planned_hours, remaining_hours)}  — no calendar → 8h/day
    d = ScheduleData()
    d.activities = {code: {'id': code, 'name': code, 'task_type': 'Task', 'calendar_id': None,
                           'planned_duration': pl, 'remaining_duration': rem}
                    for code, (pl, rem) in entries.items()}
    return d


def test_diff_durations_flags_extended_and_not_burning():
    base = _dur_sched({'A1250': (96, 96), 'A1120': (80, 80), 'A1600': (160, 160)})
    upd = _dur_sched({'A1250': (144, 120), 'A1120': (80, 64), 'A1600': (160, 176)})
    res = diff_durations(MatchedSchedules(base, upd))
    rows = {r['activity_id']: r for r in res['rows']}
    assert set(rows) == {'A1250', 'A1600'}   # A1120 on-track (remaining < baseline) excluded
    assert rows['A1250']['status'] == 'extended'
    assert rows['A1250']['baseline_orig_days'] == 12.0
    assert rows['A1250']['update_orig_days'] == 18.0
    assert rows['A1250']['remaining_days'] == 15.0
    assert rows['A1250']['remaining_minus_baseline_days'] == 3.0
    assert rows['A1600']['status'] == 'not_burning'
    assert res['counts'] == {'extended': 1, 'not_burning': 1}
    assert 'impact' in rows['A1250']   # each duration row now carries a finish-impact


def test_dur_impact_by_float():
    assert _dur_impact(-2) == 'Direct'      # critical — the extra time pushes the finish
    assert _dur_impact(0) == 'Direct'
    assert _dur_impact(5) == 'Potential'    # near-critical
    assert _dur_impact(30) == 'None'        # float absorbs it
    assert _dur_impact(None) == 'Unknown'


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
