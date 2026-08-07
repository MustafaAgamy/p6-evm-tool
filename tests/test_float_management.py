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


def test_wbs_distribution_groups_by_discipline_category():
    acts = {}
    # construction activities across different WBS branches → one 'Construction' row
    for i in range(3):
        acts[f'a{i}'] = _act(f'a{i}', 88, wbs='Project > Phase I Construction Works > Foundations')
    for i in range(2):
        acts[f'b{i}'] = _act(f'b{i}', 88, wbs='Project > MEP Works > Level 8')          # mep → Construction
    for i in range(4):
        acts[f'e{i}'] = _act(f'e{i}', 88 if i == 0 else 10, wbs='Project > Phase I Engineering > Shop')
    acts['d0'] = _act('d0', 88, wbs='Project > Phase II Design > IFC')
    m = float_management(_g(acts), CONFIG)
    names = {r['wbs']: r for r in m['wbs']}
    assert set(names) <= {'Construction', 'Engineering', 'Design', 'Procurement'}
    assert names['Construction']['activities'] == 5          # 3 + 2 merged into one discipline row
    assert names['Construction']['is_construction'] is True
    assert names['Engineering']['is_construction'] is False
    assert m['wbs'][0]['pct'] >= m['wbs'][1]['pct']          # worst concentration first


def test_highest_float_names_its_discipline():
    acts = {'a': _act('a', 60, wbs='Site > Concrete'),
            'b': _act('b', 210, wbs='Steel > Structural Steel')}
    m = float_management(_g(acts), CONFIG)
    assert m['indicators']['highest_float'] == 210.0
    assert m['indicators']['highest_float_wbs'] == 'Construction'   # discipline of the biggest float


def test_completed_activities_excluded_from_float():
    acts = {
        'done': _act('done', 88, status='Completed'),     # completed → out of the float population
        'live': _act('live', 88, status='In Progress'),   # in progress → counted
    }
    m = float_management(_g(acts), CONFIG)
    assert m['stats']['total'] == 1                        # only the live one
    assert m['indicators']['constr_over'] == 1


def test_baseline_shows_total_update_shows_remaining():
    base = {f'x{i}': _act(f'x{i}', 60, status='Not Started') for i in range(3)}
    mb = float_management(_g(base), CONFIG)
    assert mb['stats']['is_update'] is False
    assert mb['stats']['total_label'] == 'Total Activities'
    assert mb['stats']['total'] == 3

    upd = dict(base)
    upd['p'] = _act('p', 60, status='In Progress')
    mu = float_management(_g(upd), CONFIG)
    assert mu['stats']['is_update'] is True
    assert mu['stats']['total_label'] == 'Remaining Total Activities'


def test_conclusion_is_prose_about_construction_scope():
    acts = {f's{i}': _act(f's{i}', 120, wbs='Steel > Structural Steel') for i in range(5)}
    m = float_management(_g(acts), CONFIG)
    c = m['conclusion']
    assert isinstance(c, str) and c.strip()
    assert 'construction' in c.lower()


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


# ── end-to-end: a real P6 file parsed through the engine yields a well-formed mgmt ──
def test_end_to_end_real_xml_through_engine_produces_valid_mgmt():
    import os
    from p6_evm.parser import parse_file
    from p6_audit.engine import audit_modules
    data = parse_file(os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml'))
    fm = audit_modules(data, CONFIG)['modules']['float']['mgmt']
    # structure is present and internally consistent (no crash on real parsed data)
    assert 0 <= fm['float_health'] <= 100
    assert fm['fh_color'] in ('green', 'amber', 'red')
    for key in ('stats', 'indicators', 'high', 'neg', 'wbs', 'conclusion'):
        assert key in fm
    assert isinstance(fm['wbs'], list)
    assert isinstance(fm['conclusion'], str) and fm['conclusion'].strip()
    # wbs distribution stays sorted worst-concentration-first
    pcts = [r['pct'] for r in fm['wbs']]
    assert pcts == sorted(pcts, reverse=True)
