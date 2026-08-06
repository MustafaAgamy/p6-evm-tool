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


def _data_with_noncost_phase():
    """Construction is cost-loaded; Engineering carries no cost (its progress isn't in the
    schedule $); a Milestones row is a structural summary. Engineering should still get the
    5% default, Milestones should get 0 — so nothing important starts at 0%."""
    d = ScheduleData()
    d.project = {'data_date': datetime(2026, 3, 1)}
    d.wbs = {
        'w1': {'name': 'Phase I Construction Works', 'parent_object_id': None},
        'w2': {'name': 'Phase I Engineering', 'parent_object_id': None},
        'w3': {'name': 'Milestones', 'parent_object_id': None},
    }
    d.activities = {
        'a1': _act('a1', 'w1', 0.5),
        'a2': _act('a2', 'w2', 0.3),
        'a3': _act('a3', 'w3', 0.0),
    }
    d.baseline_by_id = {
        oid: {'planned_start': datetime(2026, 1, 1), 'planned_finish': datetime(2026, 6, 1)}
        for oid in ('a1', 'a2', 'a3')
    }
    # only Construction carries budget; Engineering + Milestones are zero-cost
    d.bac_by_activity = {'a1': 950000.0, 'a2': 0.0, 'a3': 0.0}
    d.ac_by_activity = {}
    return d


def test_noncost_discipline_gets_5pct_structural_gets_zero():
    d = _data_with_noncost_phase()
    config = {'categories': auto_categories(d)}
    result = compute(d, config, classifier=build_wbs_classifier(d))
    cats = result['categories']
    assert round(cats['Phase I Construction Works']['weight'], 6) == 0.95
    assert round(cats['Phase I Engineering']['weight'], 6) == 0.05   # discipline, no cost → 5%
    assert cats['Milestones']['weight'] == 0.0                        # structural → 0
    # the three weights still add to exactly 1.0
    assert round(sum(c['weight'] for c in cats.values()), 6) == 1.0


def test_saved_weights_override_the_defaults():
    d = _data_with_noncost_phase()
    # user drags Engineering up to 10%, Construction down to 90%
    saved = {'Phase I Construction Works': 0.90, 'Phase I Engineering': 0.10}
    config = {'categories': auto_categories(d, saved_weights=saved)}
    result = compute(d, config, classifier=build_wbs_classifier(d))
    cats = result['categories']
    assert round(cats['Phase I Construction Works']['weight'], 6) == 0.90
    assert round(cats['Phase I Engineering']['weight'], 6) == 0.10
