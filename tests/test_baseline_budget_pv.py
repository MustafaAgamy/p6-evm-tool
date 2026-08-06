"""P6 anchors Planned Value and the WBS %-rollup to the BASELINE budget, not the current
update's cost loading. When a schedule carries baseline costs, compute() weights by them;
without them (e.g. a bare XER) it falls back to the current BAC. Verified against real files:
SNT_GBN XML PV 243.8M and Construction actual 26.04% match P6 only with baseline weighting."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_evm.metrics import compute

CONFIG = {'categories': [{'name': 'Construction', 'weight': 1.0, 'wbs_match': 'Construction'}]}


def _schedule():
    d = ScheduleData()
    d.project = {'data_date': datetime(2026, 3, 1)}
    d.wbs = {'w1': {'name': 'Construction', 'parent_object_id': None}}

    def act(oid, pct):
        return {'object_id': oid, 'id': oid, 'name': oid, 'wbs_id': 'w1',
                'percent_complete': pct, 'calendar_id': None, 'planned_duration': 1.0,
                'planned_start': datetime(2026, 1, 1), 'planned_finish': datetime(2026, 2, 1)}

    d.activities = {'A': act('A', 1.0), 'B': act('B', 0.0)}   # A complete, B not started
    # both past their baseline finish by the data date → planned% = 100%
    bl = {'planned_start': datetime(2026, 1, 1), 'planned_finish': datetime(2026, 2, 1)}
    d.baseline_by_id = {'A': dict(bl), 'B': dict(bl)}
    d.bac_by_activity = {'A': 100.0, 'B': 100.0}              # current update budget (total 200)
    d.ac_by_activity = {}
    return d


def test_pv_and_rollup_use_baseline_budget_when_present():
    d = _schedule()
    d.baseline_bac_by_activity = {'A': 100.0, 'B': 150.0}     # B's baseline budget was higher (total 250)
    r = compute(d, CONFIG)
    # PV = baseline-weighted planned (both 100% planned) = 100 + 150 = 250, NOT the current 200
    assert round(r['pv'], 2) == 250.0
    # EV = baseline-weighted actual = 100*1 + 150*0 = 100
    assert round(r['ev'], 2) == 100.0
    # Construction actual% weighted by baseline budget = (100*1 + 150*0) / 250 = 40%
    assert round(r['categories']['Construction']['actual_pct'], 4) == 0.40


def test_falls_back_to_current_bac_without_baseline_costs():
    d = _schedule()
    d.baseline_bac_by_activity = {}                           # e.g. bare XER — no embedded baseline cost
    r = compute(d, CONFIG)
    assert round(r['pv'], 2) == 200.0                         # current budget 100 + 100
    # current-weighted actual% = (100*1 + 100*0) / 200 = 50%
    assert round(r['categories']['Construction']['actual_pct'], 4) == 0.50
