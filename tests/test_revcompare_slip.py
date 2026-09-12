"""Unit tests for p6_revcompare.slip — the finish-slip attribution bridge.

build_slip attributes the governing-finish working-day delta to neutral causes on the
Rev.01 driving chain. The load-bearing guarantees:
  * sum(contribution wd) == total_wd  ALWAYS (the bridge closes via 'Other / interaction')
  * 'Added CP scope' and 'Longer durations' carry concrete working-day quantities
  * structural causes (re-sequence / new link / constraint) are flagged with wd == 0
  * every path is guarded — missing/degenerate data returns an again-safe structure
"""
from tests.test_revcompare_engine import _act, _sched, _pair, D

from p6_compare.model import MatchedSchedules
from p6_revcompare.matching import match_activities, canonicalize
from p6_revcompare.compare import _ref_cal, _governing_finish
from p6_revcompare.slip import build_slip


def _prep(rev0, rev1):
    """Mirror what compare.py wires in: match, canonicalise rev1, MatchedSchedules, cal, govs."""
    match = match_activities(rev0, rev1)
    rev1c = canonicalize(rev1, match['canonical'])
    matched = MatchedSchedules(rev0, rev1c)
    cal = _ref_cal(rev1c)
    gov0, gov1 = _governing_finish(rev0), _governing_finish(rev1c)
    return match, rev1c, matched, cal, gov0, gov1


def _causes(slip):
    return {c['cause']: c['wd'] for c in slip['contributions']}


# ── 1) Added scope + longer durations on the driving chain, reconciled ──────────

def _added_and_longer_pair():
    """Rev.01 grows an existing CP activity (+10 d) and inserts a new CP activity (10 d)."""
    rev0 = _sched([
        _act('A', 'Excavation', tf=0, ps=D(2025, 3, 1), pf=D(2025, 3, 14), dur=80),      # 10 d
        _act('B', 'Foundation', tf=0, ps=D(2025, 3, 15), pf=D(2025, 3, 28), dur=80),     # 10 d
        _act('MS', 'Completion', 'FinishMilestone', tf=0, ps=D(2025, 3, 28), pf=D(2025, 3, 28)),
    ], [('A', 'B', 'FS', 0), ('B', 'MS', 'FS', 0)], D(2025, 3, 1))
    rev1 = _sched([
        _act('A', 'Excavation', tf=0, ps=D(2025, 3, 1), pf=D(2025, 3, 14), dur=80),      # 10 d
        _act('C', 'Piling', tf=0, ps=D(2025, 3, 15), pf=D(2025, 3, 28), dur=80),         # 10 d  (ADDED, on CP)
        _act('B', 'Foundation', tf=0, ps=D(2025, 3, 29), pf=D(2025, 4, 25), dur=160),    # 20 d  (+10 d)
        _act('MS', 'Completion', 'FinishMilestone', tf=0, ps=D(2025, 4, 25), pf=D(2025, 4, 25)),
    ], [('A', 'C', 'FS', 0), ('C', 'B', 'FS', 0), ('B', 'MS', 'FS', 0)], D(2025, 3, 1))
    return rev0, rev1


def test_added_and_longer_quantified():
    rev0, rev1 = _added_and_longer_pair()
    match, rev1c, matched, cal, gov0, gov1 = _prep(rev0, rev1)
    # Hand-built driving chain (build_slip only reads cp['rev1'][*]['code']).
    cp = {'rev1': [{'code': 'A'}, {'code': 'C'}, {'code': 'B'}, {'code': 'MS'}]}
    slip = build_slip(rev0, rev1c, matched, match, cp, cal, gov0, gov1)

    causes = _causes(slip)
    assert causes['Added CP scope'] == 10      # C, 80h / 8 = 10 working days
    assert causes['Longer durations'] == 10    # B grew 10 d → 20 d
    assert 'Other / interaction' in causes


def test_bridge_always_reconciles_to_total():
    rev0, rev1 = _added_and_longer_pair()
    match, rev1c, matched, cal, gov0, gov1 = _prep(rev0, rev1)
    cp = {'rev1': [{'code': 'A'}, {'code': 'C'}, {'code': 'B'}, {'code': 'MS'}]}
    slip = build_slip(rev0, rev1c, matched, match, cp, cal, gov0, gov1)
    assert sum(c['wd'] for c in slip['contributions']) == slip['total_wd']


def test_finish_strings_present():
    rev0, rev1 = _added_and_longer_pair()
    match, rev1c, matched, cal, gov0, gov1 = _prep(rev0, rev1)
    cp = {'rev1': [{'code': 'B'}, {'code': 'MS'}]}
    slip = build_slip(rev0, rev1c, matched, match, cp, cal, gov0, gov1)
    assert slip['rev0_finish'] == '28 Mar 2025'
    assert slip['rev1_finish'] == '25 Apr 2025'
    assert isinstance(slip['total_wd'], int) and slip['total_wd'] > 0


# ── 2) Off-chain changes are NOT attributed to scope/duration bars ──────────────

def test_only_driving_chain_activities_counted():
    rev0, rev1 = _added_and_longer_pair()
    match, rev1c, matched, cal, gov0, gov1 = _prep(rev0, rev1)
    # A CP that excludes C and B → their growth must NOT show as Added/Longer.
    cp = {'rev1': [{'code': 'A'}, {'code': 'MS'}]}
    slip = build_slip(rev0, rev1c, matched, match, cp, cal, gov0, gov1)
    causes = _causes(slip)
    assert 'Added CP scope' not in causes
    assert 'Longer durations' not in causes
    # The whole move then lands in the reconciling bucket, still summing to total.
    assert sum(c['wd'] for c in slip['contributions']) == slip['total_wd']
    assert causes.get('Other / interaction') == slip['total_wd']


# ── 3) Structural causes flagged with wd == 0 (re-sequence + new link) ──────────

def test_resequence_and_new_link_flagged_zero_wd():
    # Order reversal X<->Y plus the link swap that implements it, both on the CP.
    rev0 = _sched([
        _act('X', 'Pour slab', tf=0, ps=D(2025, 3, 1), pf=D(2025, 3, 14), dur=80),
        _act('Y', 'Strike forms', tf=0, ps=D(2025, 3, 15), pf=D(2025, 3, 28), dur=80),
        _act('MS', 'Completion', 'FinishMilestone', tf=0, ps=D(2025, 3, 28), pf=D(2025, 3, 28)),
    ], [('X', 'Y', 'FS', 0), ('Y', 'MS', 'FS', 0)], D(2025, 3, 1))
    rev1 = _sched([
        _act('X', 'Pour slab', tf=0, ps=D(2025, 3, 15), pf=D(2025, 3, 28), dur=80),
        _act('Y', 'Strike forms', tf=0, ps=D(2025, 3, 1), pf=D(2025, 3, 14), dur=80),
        _act('MS', 'Completion', 'FinishMilestone', tf=0, ps=D(2025, 3, 28), pf=D(2025, 3, 28)),
    ], [('Y', 'X', 'FS', 0), ('X', 'MS', 'FS', 0)], D(2025, 3, 1))
    match, rev1c, matched, cal, gov0, gov1 = _prep(rev0, rev1)
    cp = {'rev1': [{'code': 'Y'}, {'code': 'X'}, {'code': 'MS'}]}
    slip = build_slip(rev0, rev1c, matched, match, cp, cal, gov0, gov1)
    causes = _causes(slip)
    assert causes.get('Re-sequence') == 0
    assert causes.get('New driving link') == 0
    # No duration/scope quantities here → bridge is entirely structural + reconcile bucket.
    assert sum(c['wd'] for c in slip['contributions']) == slip['total_wd']


# ── 4) Guards — degenerate / missing inputs never throw ─────────────────────────

def test_missing_governing_finish_is_safe():
    rev0, rev1 = _added_and_longer_pair()
    match, rev1c, matched, cal, gov0, gov1 = _prep(rev0, rev1)
    cp = {'rev1': [{'code': 'B'}]}
    slip = build_slip(rev0, rev1c, matched, match, cp, cal, None, None)
    assert slip['total_wd'] == 0
    assert slip['rev0_finish'] is None and slip['rev1_finish'] is None
    assert sum(c['wd'] for c in slip['contributions']) == 0


def test_empty_cp_and_no_match_is_safe():
    rev0, rev1 = _added_and_longer_pair()
    match, rev1c, matched, cal, gov0, gov1 = _prep(rev0, rev1)
    slip = build_slip(rev0, rev1c, matched, {}, {}, cal, gov0, gov1)
    # Nothing on the (empty) chain → the whole move sits in the reconcile bucket.
    assert sum(c['wd'] for c in slip['contributions']) == slip['total_wd']


def test_no_change_returns_empty_bridge():
    rev0, _ = _added_and_longer_pair()
    match, rev1c, matched, cal, gov0, gov1 = _prep(rev0, rev0)
    cp = {'rev1': [{'code': 'A'}, {'code': 'B'}, {'code': 'MS'}]}
    slip = build_slip(rev0, rev1c, matched, match, cp, cal, gov0, gov1)
    assert slip['total_wd'] == 0
    assert slip['contributions'] == []


# ── 5) Runs on the shared engine fixture without throwing ───────────────────────

def test_runs_on_engine_fixture():
    rev0, rev1 = _pair()
    match, rev1c, matched, cal, gov0, gov1 = _prep(rev0, rev1)
    from p6_revcompare.compare import _cp_chain, _critical_codes
    crit1 = _critical_codes(rev1c)
    cp = {'rev1': _cp_chain(rev1c, crit1, set(), set())}
    slip = build_slip(rev0, rev1c, matched, match, cp, cal, gov0, gov1)
    assert sum(c['wd'] for c in slip['contributions']) == slip['total_wd']
    assert isinstance(slip['rev1_finish'], str)
