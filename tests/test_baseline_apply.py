"""Attaching a baseline must feed the update BOTH the baseline planned dates AND the baseline
budget, matched by Activity Id — exactly like the XML's embedded <BaselineProject> linkage.
Copying only the dates (the old behaviour) left PV/EV/%-rollup on the update's own cost, so a
XER never matched the XML. apply_baseline() closes that gap; metrics.py is untouched.
"""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_evm.metrics import compute
from p6_evm.baseline import apply_baseline

CONFIG = {'categories': [{'name': 'Construction', 'weight': 1.0, 'wbs_match': 'Construction'}]}


def _update():
    d = ScheduleData()
    d.project = {'data_date': datetime(2026, 3, 1)}
    d.wbs = {'w1': {'name': 'Construction', 'parent_object_id': None}}

    def act(oid, aid, pct):
        return {'object_id': oid, 'id': aid, 'name': aid, 'wbs_id': 'w1',
                'percent_complete': pct, 'calendar_id': None, 'planned_duration': 1.0,
                'planned_start': datetime(2026, 1, 5), 'planned_finish': datetime(2026, 2, 5)}

    # A complete, B not started, C is new work not in the baseline
    d.activities = {'a1': act('a1', 'A', 1.0), 'b1': act('b1', 'B', 0.0), 'c1': act('c1', 'C', 0.0)}
    d.bac_by_activity = {'a1': 100.0, 'b1': 100.0, 'c1': 100.0}   # current update budget
    d.ac_by_activity = {}
    return d


def _baseline():
    d = ScheduleData()

    def act(oid, aid):
        return {'object_id': oid, 'id': aid, 'name': aid,
                'planned_start': datetime(2026, 1, 1), 'planned_finish': datetime(2026, 2, 1)}

    d.activities = {'ba': act('ba', 'A'), 'bb': act('bb', 'B')}   # only A and B are baselined
    d.bac_by_activity = {'ba': 100.0, 'bb': 150.0}                # B's baseline budget was higher
    return d


def test_apply_baseline_sets_dates_and_budget():
    up, bl = _update(), _baseline()
    report = apply_baseline(up, bl)
    # dates keyed by Activity Id, from the baseline
    assert up.baseline_by_id['A']['planned_finish'] == datetime(2026, 2, 1)
    assert set(up.baseline_by_id) == {'A', 'B'}
    # budget keyed by the UPDATE's object id, valued from the baseline; C has no baseline cost
    assert up.baseline_bac_by_activity == {'a1': 100.0, 'b1': 150.0}
    assert report['matched'] == 2 and report['total'] == 3


def test_pv_uses_baseline_budget_after_apply():
    up, bl = _update(), _baseline()
    apply_baseline(up, bl)
    r = compute(up, CONFIG)
    # both A and B are past their baseline finish by the data date → planned% = 100%
    # PV weights by the BASELINE budget: 100*1 + 150*1 = 250 (NOT the update's 200)
    assert round(r['pv'], 2) == 250.0
    # EV = baseline-weighted actual = 100*1 + 150*0 = 100
    assert round(r['ev'], 2) == 100.0


def test_matched_count_ignores_unbaselined_activities():
    up, bl = _update(), _baseline()
    report = apply_baseline(up, bl)
    # C (new work) is counted in total but not matched
    assert report['matched'] == 2
    assert 'c1' not in up.baseline_bac_by_activity
