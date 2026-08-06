"""End-to-end: auto_categories + compute(classifier=...) buckets activities by WBS
meaning and applies the default 95/5 weights — no hand-tuned config needed."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_evm.metrics import compute
from p6_evm.classify import auto_categories, build_wbs_classifier


def _act(oid, wbs_id, pct):
    return {'object_id': oid, 'id': oid, 'name': oid, 'wbs_id': wbs_id,
            'percent_complete': pct, 'calendar_id': None, 'planned_duration': 1.0,
            'planned_start': datetime(2026, 1, 1), 'planned_finish': datetime(2026, 6, 1)}


def _data():
    d = ScheduleData()
    d.project = {'data_date': datetime(2026, 3, 1)}
    d.wbs = {
        'w1': {'name': 'Phase I Construction Works', 'parent_object_id': None},
        'w2': {'name': 'Detailed Design', 'parent_object_id': None},
    }
    d.activities = {
        'a1': _act('a1', 'w1', 0.4),
        'a2': _act('a2', 'w1', 0.5),
        'a3': _act('a3', 'w2', 0.2),
    }
    d.baseline_by_id = {
        'a1': {'planned_start': datetime(2026, 1, 1), 'planned_finish': datetime(2026, 6, 1)},
        'a2': {'planned_start': datetime(2026, 1, 1), 'planned_finish': datetime(2026, 6, 1)},
        'a3': {'planned_start': datetime(2026, 1, 1), 'planned_finish': datetime(2026, 6, 1)},
    }
    # budget: Construction WBS = 950k, Design WBS = 50k → cost-share weights 0.95 / 0.05
    d.bac_by_activity = {'a1': 900000.0, 'a2': 50000.0, 'a3': 50000.0}
    d.ac_by_activity = {}
    return d


def test_auto_categories_per_wbs_phase_and_cost_weight():
    d = _data()
    config = {'categories': auto_categories(d)}
    result = compute(d, config, classifier=build_wbs_classifier(d))
    cats = result['categories']
    # one category per top-level WBS branch (its own name), not merged
    assert set(cats) == {'Phase I Construction Works', 'Detailed Design'}
    # default weight = share of budget
    assert round(cats['Phase I Construction Works']['weight'], 4) == 0.95
    assert round(cats['Detailed Design']['weight'], 4) == 0.05
    assert cats['Phase I Construction Works']['activity_count'] == 2
    assert cats['Detailed Design']['activity_count'] == 1
