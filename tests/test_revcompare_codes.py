"""Unit tests for p6_revcompare.codes.build_codes — scope-by-code grouping."""
from tests.test_revcompare_engine import _act, _sched, _pair, D

from p6_revcompare.matching import match_activities
from p6_revcompare.codes import build_codes


def _codes(rev0, rev1):
    return build_codes(rev0, rev1, match_activities(rev0, rev1))


# ── shape / guards ────────────────────────────────────────────────────────────

def test_returns_all_keys_even_with_no_codes():
    r = _codes(*_pair())
    assert set(r) == {'dimensions', 'scope_by_code', 'added', 'removed', 'recoded'}
    # synthetic _pair activities carry no activity codes → dimensions empty,
    # but the WBS pseudo-dimension is always present.
    assert r['dimensions'] == []
    assert 'WBS' in r['scope_by_code']


def test_identical_revisions_yield_nothing():
    rev0, _ = _pair()
    r = build_codes(rev0, rev0, match_activities(rev0, rev0))
    assert r['added'] == [] and r['removed'] == []
    assert r['recoded'] == []
    assert r['scope_by_code']['WBS'] == []


def test_empty_match_is_safe():
    rev0, rev1 = _pair()
    r = build_codes(rev0, rev1, {})
    assert r['added'] == [] and r['removed'] == [] and r['recoded'] == []
    assert 'WBS' in r['scope_by_code']


# ── itemisation of added / removed ──────────────────────────────────────────────

def test_added_and_removed_itemised_with_wbs():
    r = _codes(*_pair())
    added_ids = {a['id'] for a in r['added']}
    removed_ids = {a['id'] for a in r['removed']}
    assert 'A4400' in added_ids            # MEP Risers is new scope
    assert 'A1980' in removed_ids          # Temp Dewatering dropped
    mep = next(a for a in r['added'] if a['id'] == 'A4400')
    assert mep['wbs'] == 'WBS 1.5 MEP'
    assert mep['name'] == 'MEP Risers'
    # no activity codes on the synthetic fixture → building / scope None
    assert mep['building'] is None and mep['scope'] is None


# ── scope_by_code grouping (dimensions + WBS top-branch) ─────────────────────────

def _coded_pair():
    """A pair where added/removed activities carry activity codes across dimensions."""
    rev0 = _sched([
        _act('R100', 'Old Foundation', wbs='Plant > Area 1 > Civil'),
    ], [], D(2025, 1, 1))
    rev0.activity_code_types = ['Building', 'Discipline']
    rev0.activities['o0']['activity_codes'] = {'Building': 'B1', 'Discipline': 'Civil'}

    rev1 = _sched([
        _act('N200', 'New Pump Base', wbs='Plant > Area 2 > Mechanical'),
        _act('N300', 'New Pipe Rack', wbs='Plant > Area 2 > Mechanical'),
    ], [], D(2025, 1, 1))
    rev1.activity_code_types = ['Building', 'Discipline']
    rev1.activities['o0']['activity_codes'] = {'Building': 'B2', 'Discipline': 'Mechanical'}
    rev1.activities['o1']['activity_codes'] = {'Building': 'B2', 'Discipline': 'Piping'}
    return rev0, rev1


def test_scope_by_code_dimensions_and_counts():
    rev0, rev1 = _coded_pair()
    r = build_codes(rev0, rev1, match_activities(rev0, rev1))
    assert r['dimensions'] == ['Building', 'Discipline']

    # Building dimension: B2 gained 2 added; B1 lost 1 removed.
    bmap = {row['category']: row for row in r['scope_by_code']['Building']}
    assert bmap['B2']['added'] == 2 and bmap['B2']['removed'] == 0
    assert bmap['B1']['removed'] == 1 and bmap['B1']['added'] == 0
    # biggest bucket first
    assert r['scope_by_code']['Building'][0]['category'] == 'B2'


def test_scope_by_code_wbs_top_branch():
    rev0, rev1 = _coded_pair()
    r = build_codes(rev0, rev1, match_activities(rev0, rev1))
    wmap = {row['category']: row for row in r['scope_by_code']['WBS']}
    # both revs share top branch 'Plant' → 2 added + 1 removed under 'Plant'
    assert wmap['Plant']['added'] == 2 and wmap['Plant']['removed'] == 1


def test_building_and_scope_picked_from_code_dimensions():
    rev0, rev1 = _coded_pair()
    r = build_codes(rev0, rev1, match_activities(rev0, rev1))
    pump = next(a for a in r['added'] if a['id'] == 'N200')
    assert pump['building'] == 'B2'          # dim name contains 'build'
    assert pump['scope'] == 'Mechanical'     # dim name contains 'discipline'


def test_scope_falls_back_to_any_code_when_no_hinted_dim():
    rev0 = _sched([_act('R1', 'Old')], [], D(2025, 1, 1))
    rev1 = _sched([_act('N1', 'New Widget')], [], D(2025, 1, 1))
    rev1.activity_code_types = ['Zone']
    rev1.activities['o0']['activity_codes'] = {'Zone': 'North'}
    r = build_codes(rev0, rev1, match_activities(rev0, rev1))
    widget = next(a for a in r['added'] if a['id'] == 'N1')
    # no build/discipline/scope/trade dim → both fall back to the only code value
    assert widget['building'] == 'North'
    assert widget['scope'] == 'North'


def test_uncoded_activities_grouped_under_uncoded_label():
    # rev1 declares a dimension but the added activity has no value in it
    rev0 = _sched([_act('R1', 'Old')], [], D(2025, 1, 1))
    rev1 = _sched([_act('N1', 'New Uncoded')], [], D(2025, 1, 1))
    rev1.activity_code_types = ['Building']
    r = build_codes(rev0, rev1, match_activities(rev0, rev1))
    cats = {row['category'] for row in r['scope_by_code']['Building']}
    assert '(uncoded)' in cats


# ── recoded (matched activities whose code tagging changed) ──────────────────────

def test_recoded_detects_value_change():
    # same-code matched pair whose Discipline tag changes
    a = _sched([_act('A1', 'Slab')], [], D(2025, 1, 1))
    b = _sched([_act('A1', 'Slab')], [], D(2025, 1, 1))
    a.activities['o0']['activity_codes'] = {'Discipline': 'Civil', 'Building': 'B1'}
    b.activities['o0']['activity_codes'] = {'Discipline': 'Structural', 'Building': 'B1'}
    r = build_codes(a, b, match_activities(a, b))
    disc = [x for x in r['recoded'] if x['code_type'] == 'Discipline']
    assert len(disc) == 1
    assert disc[0]['id'] == 'A1' and disc[0]['name'] == 'Slab'
    assert disc[0]['before'] == 'Civil' and disc[0]['after'] == 'Structural'
    # the unchanged Building dimension is not reported
    assert not [x for x in r['recoded'] if x['code_type'] == 'Building']


def test_recoded_detects_added_and_removed_code():
    a = _sched([_act('A1', 'Slab')], [], D(2025, 1, 1))
    b = _sched([_act('A1', 'Slab')], [], D(2025, 1, 1))
    a.activities['o0']['activity_codes'] = {'Zone': 'North'}
    b.activities['o0']['activity_codes'] = {}
    r = build_codes(a, b, match_activities(a, b))
    zone = next(x for x in r['recoded'] if x['code_type'] == 'Zone')
    assert zone['before'] == 'North' and zone['after'] is None


def test_recoded_empty_when_no_code_changes():
    a = _sched([_act('A1', 'Slab')], [], D(2025, 1, 1))
    b = _sched([_act('A1', 'Slab')], [], D(2025, 1, 1))
    a.activities['o0']['activity_codes'] = {'Discipline': 'Civil'}
    b.activities['o0']['activity_codes'] = {'Discipline': 'Civil'}
    r = build_codes(a, b, match_activities(a, b))
    assert r['recoded'] == []
