"""Unit tests for the time-phased planned-spread engine (p6_revcompare.curves).

Baselines only — everything is PLANNED value (no actuals). Spread is linear across
each activity's planned span, bucketed by calendar month (calendar days when no
calendar is attached, as here)."""
from p6_compare.model import MatchedSchedules
from p6_revcompare.matching import match_activities, canonicalize
from p6_revcompare.curves import build_curves

from tests.test_revcompare_engine import _act, _sched, _pair, D


# ── wiring helper: mimic exactly what compare.py hands the module ──────────────

def _wire(rev0, rev1, orig_finish=None):
    match = match_activities(rev0, rev1)
    rev1c = canonicalize(rev1, match['canonical'])
    matched = MatchedSchedules(rev0, rev1c)
    return build_curves(rev0, rev1c, matched, match, None, orig_finish)


def _budget_sched(bac, ps, pf, code='A1000', codes=None):
    d = _sched([_act(code, 'Work', ps=ps, pf=pf)], [], D(2025, 1, 1))
    d.bac_by_activity = {'o0': bac}
    if codes:
        d.activities['o0']['activity_codes'] = codes
    return d


def _assign_sched(assigns, ps, pf, code='A1000'):
    """assigns: list of (resource_id, resource_name, units[, resource_type]).
    Man-hours = LABOUR only, so assignments default to resource_type 'Labour'."""
    d = _sched([_act(code, 'Work', ps=ps, pf=pf)], [], D(2025, 1, 1))
    d.assignments_by_activity = {'o0': [
        {'resource_id': a[0], 'resource_name': a[1], 'budget_units': a[2],
         'resource_type': a[3] if len(a) > 3 else 'Labour', 'budget_cost': 0.0, 'rate': None}
        for a in assigns]}
    return d


def _coded_assign_sched(assigns, ps, pf, code='A1000'):
    """assigns: list of (resource_id, resource_code, resource_name, units[, resource_type]) —
    carries the P6 code; defaults to resource_type 'Labour'."""
    d = _sched([_act(code, 'Work', ps=ps, pf=pf)], [], D(2025, 1, 1))
    d.assignments_by_activity = {'o0': [
        {'resource_id': a[0], 'resource_code': a[1], 'resource_name': a[2],
         'budget_units': a[3], 'resource_type': a[4] if len(a) > 4 else 'Labour',
         'budget_cost': 0.0, 'rate': None}
        for a in assigns]}
    return d


def test_manhours_total_exact_sum_and_same_name_not_merged():
    """P6-matching: LABOUR man-hours = the exact sum of the planned LABOUR units (no loss/double-
    count); two resources that share a NAME but have distinct P6 codes stay as separate trade rows;
    and the equipment (Crane) is excluded from man-hours entirely — it is a different unit."""
    rev0 = _coded_assign_sched([('4501', 'LAB-01', 'Steelfixers', 100.0, 'Labour'),
                                ('4507', 'LAB-07', 'Steelfixers', 40.0, 'Labour'),
                                ('9001', 'EQ-CR', 'Crane', 10.0, 'Equipment')], D(2025, 1, 1), D(2025, 1, 31))
    rev1 = _coded_assign_sched([('4501', 'LAB-01', 'Steelfixers', 120.0, 'Labour'),
                                ('4507', 'LAB-07', 'Steelfixers', 50.0, 'Labour'),
                                ('9001', 'EQ-CR', 'Crane', 10.0, 'Equipment')], D(2025, 1, 1), D(2025, 1, 31))
    c = _wire(rev0, rev1)
    # Labour only: 100+40 = 140, 120+50 = 170 — the crane's 10 units are NOT summed in.
    assert c['manhours_total']['rev0'] == 140.0 and c['manhours_total']['rev1'] == 170.0
    steel = [t for t in c['manhours_by_trade'] if t['name'] == 'Steelfixers']
    assert len(steel) == 2 and {t['resource_id'] for t in steel} == {'LAB-01', 'LAB-07'}
    assert all(t['name'] != 'Crane' for t in c['manhours_by_trade'])   # equipment not a trade
    assert c['other_resources']['equipment'] == {'rev0': 10.0, 'rev1': 10.0, 'var': 0.0, 'n0': 1, 'n1': 1}


def test_manhours_labour_only_excludes_equipment_and_material():
    """Round-15: man-hours are LABOUR units only. Equipment-hours and material quantities are
    reported in other_resources with their assignment counts, never folded into man-hours."""
    rev0 = _assign_sched([('L1', 'Carpenter', 100.0, 'Labour'),
                          ('E1', 'Excavator', 30.0, 'Equipment'),
                          ('M1', 'Concrete', 5000.0, 'Material')], D(2025, 1, 1), D(2025, 1, 31))
    rev1 = _assign_sched([('L1', 'Carpenter', 90.0, 'Labour'),
                          ('E1', 'Excavator', 30.0, 'Equipment'),
                          ('M1', 'Concrete', 4800.0, 'Material')], D(2025, 1, 1), D(2025, 1, 31))
    c = _wire(rev0, rev1)
    assert c['manhours_total'] == {'rev0': 100.0, 'rev1': 90.0, 'var': -10.0, 'pct': -10.0}
    assert [t['name'] for t in c['manhours_by_trade']] == ['Carpenter']
    assert c['other_resources']['equipment']['rev0'] == 30.0
    assert c['other_resources']['material'] == {'rev0': 5000.0, 'rev1': 4800.0, 'var': -200.0, 'n0': 1, 'n1': 1}


def test_untyped_assignment_excluded_from_manhours_and_surfaced():
    """An assignment with no resource_type (P6 export omitted it) is NEVER guessed as labour — it
    is excluded from man-hours and surfaced in other_resources['untyped']."""
    rev0 = _assign_sched([('L1', 'Carpenter', 80.0, 'Labour'),
                          ('U1', 'Mystery', 25.0, None)], D(2025, 1, 1), D(2025, 1, 31))
    rev1 = _assign_sched([('L1', 'Carpenter', 80.0, 'Labour'),
                          ('U1', 'Mystery', 25.0, None)], D(2025, 1, 1), D(2025, 1, 31))
    c = _wire(rev0, rev1)
    assert c['manhours_total']['rev0'] == 80.0
    assert c['other_resources']['untyped']['rev0'] == 25.0 and c['other_resources']['untyped']['n0'] == 1


# ── availability flags / no-data guard ─────────────────────────────────────────

def test_no_data_flags_false_and_empty():
    c = _wire(*_pair(), orig_finish=D(2026, 12, 19))
    assert c['cost_available'] is False and c['resource_available'] is False
    assert c['months'] == []
    assert c['value_monthly'] == [] and c['value_cumulative'] == []
    assert c['value_after_orig_finish'] == 0.0
    assert c['budget_by_dim'] == {} and c['manhours_by_trade'] == []
    assert c['manpower_monthly'] == []
    assert c['peak'] == {'rev0': 0.0, 'rev1': 0.0, 'rev0_month': None, 'rev1_month': None}
    assert c['manhours_total'] == {'rev0': 0.0, 'rev1': 0.0, 'var': 0.0, 'pct': None}


# ── monthly + cumulative planned value ──────────────────────────────────────────

def test_value_phasing_monthly_and_cumulative():
    # Jan (31d) + Feb (28d) = 59-day span; 590/1180 split cleanly on calendar days.
    rev0 = _budget_sched(590.0, D(2025, 1, 1), D(2025, 2, 28))
    rev1 = _budget_sched(1180.0, D(2025, 1, 1), D(2025, 2, 28))
    c = _wire(rev0, rev1)
    assert c['cost_available'] is True
    assert c['months'] == ['Jan 2025', 'Feb 2025']
    jan, feb = c['value_monthly']
    assert (jan['rev0'], jan['rev1'], jan['var']) == (310, 620, 310)
    assert (feb['rev0'], feb['rev1'], feb['var']) == (280, 560, 280)
    cj, cf = c['value_cumulative']
    assert (cj['rev0'], cj['rev1']) == (310, 620)
    assert (cf['rev0'], cf['rev1']) == (590, 1180)


def test_axis_is_contiguous_across_a_gap():
    # rev0 sits in Jan, rev1 in Apr — the axis must fill Feb/Mar in between.
    rev0 = _budget_sched(100.0, D(2025, 1, 5), D(2025, 1, 20))
    rev1 = _budget_sched(100.0, D(2025, 4, 5), D(2025, 4, 20))
    c = _wire(rev0, rev1)
    assert c['months'] == ['Jan 2025', 'Feb 2025', 'Mar 2025', 'Apr 2025']
    assert [m['rev1'] for m in c['value_monthly']] == [0, 0, 0, 100]


# ── value after the original governing finish ───────────────────────────────────

def test_value_after_orig_finish():
    rev0 = _budget_sched(590.0, D(2025, 1, 1), D(2025, 2, 28))
    rev1 = _budget_sched(1180.0, D(2025, 1, 1), D(2025, 2, 28))
    # Day granularity (not whole-month): orig finish 15 Jan → the work from 16 Jan onward is
    # "after" it — 44 of the 59 days of the 1180 activity → 880 (NOT just Feb's 560).
    c = _wire(rev0, rev1, orig_finish=D(2025, 1, 15))
    assert c['value_after_orig_finish'] == 880
    # finish on the last day of Jan → only Feb (560) falls strictly after it.
    assert _wire(rev0, rev1, orig_finish=D(2025, 1, 31))['value_after_orig_finish'] == 560


# ── budget rolled up by dimension (+ WBS branch) ────────────────────────────────

def test_budget_by_dim_and_wbs_branch():
    rev0 = _budget_sched(1000.0, D(2025, 1, 1), D(2025, 1, 31),
                         codes={'Discipline': 'Civil'})
    rev0.activity_code_types = ['Discipline']
    rev1 = _budget_sched(1500.0, D(2025, 1, 1), D(2025, 1, 31),
                         codes={'Discipline': 'Civil'})
    rev1.activity_code_types = ['Discipline']
    c = _wire(rev0, rev1)
    assert 'Discipline' in c['budget_by_dim'] and 'WBS' in c['budget_by_dim']
    disc = c['budget_by_dim']['Discipline']
    assert disc[0] == {'category': 'Civil', 'rev0': 1000, 'rev1': 1500, 'var': 500}
    wbs = c['budget_by_dim']['WBS']
    # _act default wbs_path = 'WBS 1.2 Substructure' (single branch, no ' > ')
    assert wbs[0]['category'] == 'WBS 1.2 Substructure'
    assert wbs[0]['rev0'] == 1000 and wbs[0]['rev1'] == 1500


# ── manpower phasing + peak ─────────────────────────────────────────────────────

def test_manpower_monthly_and_peak():
    rev0 = _assign_sched([('R1', 'Carpenter', 590.0)], D(2025, 1, 1), D(2025, 2, 28))
    rev1 = _assign_sched([('R1', 'Carpenter', 590.0)], D(2025, 1, 1), D(2025, 2, 28))
    c = _wire(rev0, rev1)
    assert c['resource_available'] is True
    jan, feb = c['manpower_monthly']
    assert (jan['month'], jan['rev0']) == ('Jan 2025', 310.0)
    assert feb['rev0'] == 280.0
    assert c['peak']['rev0'] == 310.0 and c['peak']['rev0_month'] == 'Jan 2025'
    assert c['peak']['rev1'] == 310.0 and c['peak']['rev1_month'] == 'Jan 2025'


# ── man-hours per trade: added / removed / changed + total ──────────────────────

def test_manhours_by_trade_and_total():
    rev0 = _assign_sched([('R1', 'Carpenter', 100.0), ('R2', 'Steel', 50.0)],
                         D(2025, 1, 1), D(2025, 1, 31))
    rev1 = _assign_sched([('R1', 'Carpenter', 120.0), ('R3', 'Electrician', 40.0)],
                         D(2025, 1, 1), D(2025, 1, 31))
    c = _wire(rev0, rev1)
    by = {r['resource_id']: r for r in c['manhours_by_trade']}
    assert by['R1']['kind'] == 'changed' and by['R1']['rev0'] == 100.0 and by['R1']['rev1'] == 120.0 and by['R1']['var'] == 20.0
    assert by['R2']['kind'] == 'removed' and by['R2']['rev0'] == 50.0 and by['R2']['rev1'] == 0.0
    assert by['R3']['kind'] == 'added' and by['R3']['rev0'] == 0.0 and by['R3']['rev1'] == 40.0
    tot = c['manhours_total']
    assert tot['rev0'] == 150.0 and tot['rev1'] == 160.0 and tot['var'] == 10.0
    assert tot['pct'] == 6.7


# ── the module never returns cost curves when only resources exist ──────────────

def test_resource_only_still_builds_axis_without_value_curves():
    rev0 = _assign_sched([('R1', 'Carpenter', 100.0)], D(2025, 1, 1), D(2025, 1, 31))
    rev1 = _assign_sched([('R1', 'Carpenter', 100.0)], D(2025, 1, 1), D(2025, 1, 31))
    c = _wire(rev0, rev1)
    assert c['cost_available'] is False
    assert c['months'] == ['Jan 2025']
    assert c['value_monthly'] == []
    assert c['manpower_monthly'] and c['manpower_monthly'][0]['rev0'] == 100.0
