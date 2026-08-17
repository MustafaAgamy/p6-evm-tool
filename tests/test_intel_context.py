"""Slice-1 Schedule Intelligence — context indexing.

Uses the real minimal.xml fixture for the parse-reconciliation checks and a small
synthetic ScheduleData (milestones, LOE/summary, multi-level WBS, a dangling
relationship) for the cases the minimal fixture can't exercise.
"""
from datetime import datetime
from pathlib import Path

from p6_evm.parser import ScheduleData, parse_file
from p6_evm.calendars import Calendar
from p6_narrative.intel import build_context

FIXTURE = Path(__file__).parent / 'fixtures' / 'minimal.xml'


# ── synthetic schedule builder ──────────────────────────────────────────────
def _act(oid, name, wbs_id, tt='Task', dur_hours=0.0, codes=None,
         actual_start=None, is_critical=False):
    return {
        'object_id': oid, 'id': oid, 'name': name, 'wbs_id': wbs_id,
        'task_type': tt, 'calendar_id': 'C1', 'planned_duration': dur_hours,
        'planned_start': None, 'activity_codes': codes or {},
        'actual_start': actual_start, 'is_critical': is_critical,
    }


def _synthetic(with_codes=True, dangling=False):
    d = ScheduleData()
    d.calendars = {'C1': Calendar(object_id='C1', name='Cal', day_hours=10.0)}
    d.project = {'data_date': None}
    d.wbs = {
        'PRJ':  {'name': 'Project', 'parent_object_id': None},
        'CIV':  {'name': 'Civil', 'parent_object_id': 'PRJ'},
        'MEC':  {'name': 'Mechanical', 'parent_object_id': 'PRJ'},
        'PILE': {'name': 'Pile', 'parent_object_id': 'CIV'},
        'CONV': {'name': 'Conveyor', 'parent_object_id': 'MEC'},
    }
    code = (lambda v: {'Type of Works': v}) if with_codes else (lambda v: {})
    d.activities = {
        'a1':   _act('a1', 'Drilling Piles', 'PILE', dur_hours=100.0,
                     codes=code('Civil'), actual_start=datetime(2026, 1, 1)),
        'a2':   _act('a2', 'RFT Piles', 'PILE', dur_hours=50.0, codes=code('Civil')),
        'a3':   _act('a3', 'Erect Conveyor 2', 'CONV', dur_hours=80.0,
                     codes=code('Mechanical'), is_critical=True),
        'ms1':  _act('ms1', 'Start MS', 'PILE', tt='StartMilestone'),
        'ms2':  _act('ms2', 'Finish MS', 'CONV', tt='FinishMilestone'),
        'loe1': _act('loe1', 'Supervision', 'CIV', tt='LOE'),
        'sum1': _act('sum1', 'Summary', 'MEC', tt='WBSSummary'),
    }
    d.activity_code_types = ['Type of Works'] if with_codes else []
    d.relationships = [
        {'pred_id': 'a1', 'succ_id': 'a2', 'type': 'FS', 'lag_days': 0.0},
        {'pred_id': 'a2', 'succ_id': 'a3', 'type': 'SS', 'lag_days': 0.0},
    ]
    if dangling:
        d.relationships.append({'pred_id': 'ghost', 'succ_id': 'a1',
                                'type': 'FS', 'lag_days': 0.0})
    d.bac_by_activity = {'a1': 1000.0}
    d.ac_by_activity = {'a1': 500.0}
    return d


# ── tests ───────────────────────────────────────────────────────────────────
def test_filters_milestones_out_of_steps_and_keeps_them_as_anchors():
    ctx = build_context(_synthetic())
    # steps = Task-type only; LOE + WBSSummary + milestones excluded
    assert set(ctx.steps) == {'a1', 'a2', 'a3'}
    # milestones kept aside as anchors
    assert set(ctx.milestones) == {'ms1', 'ms2'}
    # LOE/summary are neither steps nor anchors
    assert 'loe1' not in ctx.steps and 'loe1' not in ctx.milestones
    assert 'sum1' not in ctx.steps and 'sum1' not in ctx.milestones


def test_durations_are_in_working_days():
    # minimal.xml: 8h/day calendar; 180h -> 22.5 wd, 184h -> 23.0 wd
    ctx = build_context(parse_file(str(FIXTURE)))
    assert ctx.durations_days == {'OBJ001': 22.5, 'OBJ002': 23.0}
    # synthetic: 10h/day calendar; 100h -> 10.0 wd
    sctx = build_context(_synthetic())
    assert sctx.durations_days['a1'] == 10.0
    assert sctx.durations_days['a2'] == 5.0


def test_tokens_are_produced_once_per_activity():
    ctx = build_context(parse_file(str(FIXTURE)))
    assert ctx.tokens['OBJ001'] == ['Activity', 'One']
    assert ctx.tokens['OBJ002'] == ['Activity', 'Two']
    # numbers tokenized separately from words
    sctx = build_context(_synthetic())
    assert sctx.tokens['a3'] == ['Erect', 'Conveyor', '2']


def test_wbs_indices_children_acts_and_ancestors():
    ctx = build_context(_synthetic())
    assert ctx.children_of_wbs['PRJ'] == ['CIV', 'MEC']
    assert ctx.children_of_wbs['CIV'] == ['PILE']
    # acts_by_wbs holds only STEP activities under each leaf
    assert ctx.acts_by_wbs['PILE'] == ['a1', 'a2']
    assert ctx.acts_by_wbs['CONV'] == ['a3']
    assert 'CIV' not in ctx.acts_by_wbs  # LOE isn't a step
    # ancestor-at-level lookup, root-first
    assert ctx.wbs_ancestors['PILE'] == ('PRJ', 'CIV', 'PILE')
    assert ctx.ancestor_at_level('PILE', 0) == 'PRJ'
    assert ctx.ancestor_at_level('PILE', 1) == 'CIV'
    assert ctx.ancestor_at_level('PILE', 2) == 'PILE'
    assert ctx.ancestor_at_level('PILE', 3) is None  # out of range
    assert ctx.wbs_depth_of('PILE') == 3
    assert ctx.wbs_depth_of('PRJ') == 1


def test_adjacency_wraps_graph_and_drops_dangling():
    ctx = build_context(_synthetic(dangling=True))
    assert ctx.forward['a1'] == ['a2']
    assert ctx.forward['a2'] == ['a3']
    assert ctx.back['a2'] == ['a1']
    assert ctx.back['a3'] == ['a2']
    # dangling predecessor 'ghost' (not an activity) is dropped by the graph
    assert ctx.back['a1'] == []
    assert ctx.succ_ids('a1') == ['a2'] and ctx.pred_ids('a2') == ['a1']


def test_everything_keyed_on_object_id():
    d = _synthetic()
    ctx = build_context(d)
    # every step/milestone key is an object_id present in the raw parse
    for oid in list(ctx.steps) + list(ctx.milestones):
        assert oid in d.activities
    # data is the same object — nothing re-parsed/mutated
    assert ctx.data is d
