"""Float Analysis management-dashboard layer (V2 redesign).

Covers the NEW derived numbers only — the float calculation engine (run_float
threshold/findings) is unchanged and tested in test_module_float.py.
"""
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.float_analysis import run_float
from p6_audit.modules.float_management import (
    activity_category, float_health, fh_color, float_management,
)

CONFIG = {'audit': {'float_threshold_days': 44, 'near_critical_days': 10}}


def _g(acts, rels=None):
    d = ScheduleData()
    d.activities = acts
    d.relationships = rels or []
    return ScheduleGraph(d)


def _act(oid, tf, wbs='Site > Construction > Concrete', critical=False, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': critical, 'wbs_path': wbs, 'category': None,
         'total_float_days': tf, 'free_float_days': tf}
    b.update(kw)
    return b


# ── activity_category — meaning-based Construction detection ──────────────────
def test_category_construction():
    assert activity_category('Root > Steel Structure > Structural Steel') == 'Construction'


def test_category_engineering():
    assert activity_category('Root > Engineering > Shop Drawings') == 'Engineering'


def test_category_procurement():
    assert activity_category('Root > Procurement > Long Lead') == 'Procurement'


def test_category_empty_falls_back_to_construction():
    assert activity_category('') == 'Construction'


# ── float_health — DCMA-anchored composite score ─────────────────────────────
def test_fh_perfect_meets_both_dcma_targets():
    assert float_health(3, 0, {}) == (100, 0, 0)


def test_fh_slightly_over_high_float():
    assert float_health(8, 0, {}) == (88, 12, 0)


def test_fh_composite_mockup_numbers():
    # 21.6% high float (penalty caps at 60) + 1.2% negative (~10) -> 30
    assert float_health(21.6, 1.2, {}) == (30, 60, 10)


def test_fh_passes_high_but_negative_float_still_hurts():
    # 4% high float passes DCMA (<5%) but 6% negative float -> 60, not 100
    assert float_health(4, 6, {}) == (60, 0, 40)


def test_fh_floors_at_zero():
    assert float_health(50, 20, {})[0] == 0


def test_fh_color_bands():
    assert fh_color(100) == 'green'
    assert fh_color(85) == 'green'
    assert fh_color(84) == 'amber'
    assert fh_color(60) == 'amber'
    assert fh_color(59) == 'red'


# ── float_management aggregations ────────────────────────────────────────────
def test_stats_critical_and_near_critical():
    acts = {
        'c1': _act('c1', -2, critical=True),   # critical
        'c2': _act('c2', 0, critical=True),    # critical (tf 0)
        'n1': _act('n1', 5),                   # near-critical (0 < tf <= 10)
        'n2': _act('n2', 10),                  # near-critical boundary
        'x1': _act('x1', 30),                  # neither
        'h1': _act('h1', 88),                  # high float
    }
    m = float_management(_g(acts), CONFIG)
    assert m['stats']['total'] == 6
    assert m['stats']['critical'] == 2
    assert m['stats']['near_critical'] == 2
    assert m['stats']['near_band'] == 10


def test_construction_only_over_threshold():
    acts = {
        'con': _act('con', 88, wbs='Site > Construction > Concrete'),      # construction, >44
        'eng': _act('eng', 88, wbs='Root > Engineering > Shop Drawings'),  # excluded from KPI
        'low': _act('low', 10, wbs='Site > Construction > Concrete'),      # construction, not over
    }
    m = float_management(_g(acts), CONFIG)
    assert m['indicators']['constr_total'] == 2      # con + low (eng excluded)
    assert m['indicators']['constr_over'] == 1       # only con
    assert m['indicators']['constr_over_pct'] == 50.0


def test_wbs_distribution_sorted_worst_first_and_tagged():
    acts = {}
    for i in range(4):
        acts[f'm{i}'] = _act(f'm{i}', 88, wbs='Bldg > MEP')                      # 4/4 over -> 100%
    for i in range(4):
        acts[f'c{i}'] = _act(f'c{i}', 88 if i == 0 else 10, wbs='Sub > Concrete')  # 1/4 over -> 25%
    m = float_management(_g(acts), CONFIG)
    w = m['wbs']
    assert w[0]['wbs'] == 'Bldg > MEP'
    assert w[0]['pct'] == 100.0
    assert w[0]['pct'] >= w[1]['pct']
    assert all('is_construction' in r for r in w)
    assert all(r['is_construction'] for r in w)  # MEP + Concrete both construction


def test_highest_float_names_its_wbs():
    acts = {'a': _act('a', 60, wbs='Site > Concrete'),
            'b': _act('b', 210, wbs='Steel > Structural Steel')}
    m = float_management(_g(acts), CONFIG)
    assert m['indicators']['highest_float'] == 210.0
    assert 'Structural Steel' in m['indicators']['highest_float_wbs']


def test_conclusion_is_prose_naming_top_construction_package():
    acts = {f's{i}': _act(f's{i}', 120, wbs='Steel > Structural Steel') for i in range(5)}
    m = float_management(_g(acts), CONFIG)
    assert isinstance(m['conclusion'], str) and m['conclusion'].strip()
    assert 'Structural Steel' in m['conclusion']


def test_per_wbs_avg_and_max_float():
    acts = {'a': _act('a', 20, wbs='Site > Concrete'),
            'b': _act('b', 80, wbs='Site > Concrete')}
    m = float_management(_g(acts), CONFIG)
    row = m['wbs'][0]
    assert row['avg_float'] == 50.0
    assert row['max_float'] == 80.0


# ── backward compatibility — run_float keeps its contract, only adds mgmt ─────
def test_run_float_attaches_mgmt_without_breaking_existing_contract():
    acts = {'a': _act('a', 88)}
    r = run_float(_g(acts), CONFIG)
    assert 'mgmt' in r and 'float_health' in r['mgmt']
    # existing contract intact
    assert r['module'] == 'float'
    assert r['kpis']['above_threshold'] == 1
    assert 'score' in r and 'grade' in r and 'findings' in r
