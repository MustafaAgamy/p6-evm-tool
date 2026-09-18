"""Cost loading + cash-flow curve for the Baseline Narrative — pure, no I/O."""
from datetime import datetime

from p6_narrative.costflow import cash_flow, cost_by_wbs

WBS = {
    'w_civ': {'name': 'Civil', 'parent_object_id': None},
    'w_pile': {'name': 'Pile', 'parent_object_id': 'w_civ'},
    'w_mep': {'name': 'MEP', 'parent_object_id': None},
}


def _a(oid, wbs_id, start, finish):
    return {'object_id': oid, 'wbs_id': wbs_id,
            'planned_start': start, 'planned_finish': finish}


def test_cost_by_wbs_rolls_to_top_branch_and_sums_to_total():
    acts = [_a('1', 'w_pile', datetime(2026, 1, 1), datetime(2026, 1, 10)),
            _a('2', 'w_mep', datetime(2026, 1, 1), datetime(2026, 1, 5))]
    bac = {'1': 900.0, '2': 100.0}
    r = cost_by_wbs(acts, bac, WBS)
    assert r['total'] == 1000.0
    assert r['rows'][0] == {'name': 'Civil', 'cost': 900.0, 'pct': 90.0}
    assert r['rows'][1] == {'name': 'MEP', 'cost': 100.0, 'pct': 10.0}


def test_cost_by_wbs_ignores_zero_cost():
    acts = [_a('1', 'w_pile', datetime(2026, 1, 1), datetime(2026, 1, 2))]
    assert cost_by_wbs(acts, {}, WBS) == {'total': 0.0, 'rows': []}


def test_cash_flow_monotonic_and_ends_at_100pct():
    acts = [_a('1', 'w_pile', datetime(2026, 1, 1), datetime(2026, 1, 10)),
            _a('2', 'w_mep', datetime(2026, 1, 11), datetime(2026, 1, 20))]
    bac = {'1': 500.0, '2': 500.0}
    cf = cash_flow(acts, bac, n_points=10)
    assert cf['total'] == 1000.0
    vals = [p['cumulative'] for p in cf['points']]
    assert vals == sorted(vals)            # non-decreasing
    assert cf['points'][-1]['pct'] == 100.0
    assert cf['points'][0]['cumulative'] >= 0.0


def test_cash_flow_empty_when_no_cost():
    acts = [_a('1', 'w_pile', datetime(2026, 1, 1), datetime(2026, 1, 2))]
    assert cash_flow(acts, {}, n_points=5) == {'total': 0.0, 'points': []}
