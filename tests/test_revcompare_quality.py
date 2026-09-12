"""Unit tests for the Baseline Revision schedule-quality engine (p6_revcompare.quality)."""
from tests.test_revcompare_engine import _act, _sched, _pair, D

from p6_revcompare.matching import match_activities, canonicalize
from p6_compare.model import MatchedSchedules
from p6_revcompare.quality import build_quality


def _mk(rev0, rev1):
    """Build the canonicalised rev1 + MatchedSchedules the engine would pass in."""
    m = match_activities(rev0, rev1)
    rev1c = canonicalize(rev1, m['canonical'])
    return rev1c, MatchedSchedules(rev0, rev1c)


def _q(rev0, rev1):
    rev1c, matched = _mk(rev0, rev1)
    return build_quality(rev0, rev1c, matched, cal=None)


# ── keys / shape ──────────────────────────────────────────────────────────────

def test_returns_all_contract_keys():
    q = _q(*_pair())
    for key in ('open_ends', 'leads', 'total_rels', 'rels_per_act',
                'hard_constraints', 'negative_float', 'near_critical', 'float_bands'):
        assert key in q
    assert {'rev0', 'rev1', 'new_dangling'} <= set(q['open_ends'])
    assert {'rev0', 'rev1', 'new_leads'} <= set(q['leads'])
    assert {'rev0', 'rev1', 'register'} <= set(q['negative_float'])


def test_float_bands_are_the_five_ordered_bands():
    q = _q(*_pair())
    assert [b['band'] for b in q['float_bands']] == ['<0', '0–5', '6–20', '21–60', '60+']


# ── open ends / dangling ────────────────────────────────────────────────────

def test_open_ends_counts_and_new_dangling():
    q = _q(*_pair())
    oe = q['open_ends']
    # rev0 open ends: A1000 (no pred), A2050 (no pred), A2075 (no succ), A1980 (isolated)
    assert oe['rev0'] == 4
    # rev1 open ends: A1000, A2050, A2075, A4400 (isolated new activity)
    assert oe['rev1'] == 4
    new = {d['id'] for d in oe['new_dangling']}
    assert new == {'A4400'}
    assert oe['new_dangling'][0]['name'] == 'MEP Risers'


# ── leads ─────────────────────────────────────────────────────────────────────

def test_no_leads_in_pair_fixture():
    q = _q(*_pair())
    assert q['leads']['rev0'] == 0 and q['leads']['rev1'] == 0
    assert q['leads']['new_leads'] == []


def test_new_lead_detected():
    rev0 = _sched([_act('A1', 'Start', ps=D(2025, 1, 1), pf=D(2025, 1, 10)),
                   _act('A2', 'End', tf=5, ps=D(2025, 1, 11), pf=D(2025, 1, 20))],
                  [('A1', 'A2', 'FS', 0)], D(2025, 1, 1))
    rev1 = _sched([_act('A1', 'Start', ps=D(2025, 1, 1), pf=D(2025, 1, 10)),
                   _act('A2', 'End', tf=5, ps=D(2025, 1, 11), pf=D(2025, 1, 20))],
                  [('A1', 'A2', 'FS', -2)], D(2025, 1, 1))
    q = _q(rev0, rev1)
    assert q['leads']['rev0'] == 0 and q['leads']['rev1'] == 1
    assert q['leads']['new_leads'] == [{'pred_id': 'A1', 'succ_id': 'A2', 'lag': -2}]


# ── relationship density ──────────────────────────────────────────────────────

def test_total_rels_and_density():
    q = _q(*_pair())
    assert q['total_rels'] == {'rev0': 6, 'rev1': 6}
    # 6 relationships over 9 activities each side
    assert q['rels_per_act'] == {'rev0': 0.67, 'rev1': 0.67}


# ── hard constraints ──────────────────────────────────────────────────────────

def test_hard_constraints_counted():
    a = _act('A1', 'Start', tf=0, ps=D(2025, 1, 1), pf=D(2025, 1, 10))
    b = _act('A2', 'End', tf=5, ps=D(2025, 1, 11), pf=D(2025, 1, 20))
    rev0 = _sched([a, b], [('A1', 'A2', 'FS', 0)], D(2025, 1, 1))
    a1 = _act('A1', 'Start', tf=0, ps=D(2025, 1, 1), pf=D(2025, 1, 10))
    a1['constraint_type'] = 'MustFinishOn'
    b1 = _act('A2', 'End', tf=5, ps=D(2025, 1, 11), pf=D(2025, 1, 20))
    rev1 = _sched([a1, b1], [('A1', 'A2', 'FS', 0)], D(2025, 1, 1))
    q = _q(rev0, rev1)
    assert q['hard_constraints'] == {'rev0': 0, 'rev1': 1}


# ── negative float ─────────────────────────────────────────────────────────────

def test_negative_float_register_for_rev1():
    a = _act('A1', 'Start', tf=2, ps=D(2025, 1, 1), pf=D(2025, 1, 10))
    b = _act('A2', 'End', tf=5, ps=D(2025, 1, 11), pf=D(2025, 1, 20))
    rev0 = _sched([a, b], [('A1', 'A2', 'FS', 0)], D(2025, 1, 1))
    a1 = _act('A1', 'Start', tf=-3, wbs='WBS 1.2 Sub', ps=D(2025, 1, 1), pf=D(2025, 1, 10))
    b1 = _act('A2', 'End', tf=5, ps=D(2025, 1, 11), pf=D(2025, 1, 20))
    rev1 = _sched([a1, b1], [('A1', 'A2', 'FS', 0)], D(2025, 1, 1))
    q = _q(rev0, rev1)
    assert q['negative_float']['rev0'] == 0
    assert q['negative_float']['rev1'] == 1
    reg = q['negative_float']['register']
    assert reg == [{'id': 'A1', 'name': 'Start', 'tf': -3.0, 'wbs': 'WBS 1.2 Sub'}]


def test_pair_has_no_negative_float():
    q = _q(*_pair())
    assert q['negative_float']['rev0'] == 0 and q['negative_float']['rev1'] == 0
    assert q['negative_float']['register'] == []


# ── near-critical & float bands ─────────────────────────────────────────────────

def test_near_critical_and_bands_on_pair():
    q = _q(*_pair())
    # rev0 TF: 0,0,8,0,0,12,12,20,0 -> five in [0,5), four in (5,20]
    assert q['near_critical']['rev0'] == 5
    assert q['near_critical']['rev1'] == 9
    bands = {b['band']: b for b in q['float_bands']}
    assert bands['0–5']['rev0'] == 5 and bands['6–20']['rev0'] == 4
    assert bands['<0']['rev0'] == 0 and bands['21–60']['rev0'] == 0 and bands['60+']['rev0'] == 0
    assert bands['0–5']['rev1'] == 9


# ── identical revisions & guards ────────────────────────────────────────────────

def test_identical_revisions_have_no_new_items():
    rev0, _ = _pair()
    q = _q(rev0, rev0)
    assert q['open_ends']['rev0'] == q['open_ends']['rev1']
    assert q['open_ends']['new_dangling'] == []
    assert q['leads']['new_leads'] == []
    assert q['total_rels']['rev0'] == q['total_rels']['rev1']


def test_empty_schedules_do_not_crash():
    rev0 = _sched([], [], D(2025, 1, 1))
    rev1 = _sched([], [], D(2025, 1, 1))
    q = _q(rev0, rev1)
    assert q['open_ends'] == {'rev0': 0, 'rev1': 0, 'new_dangling': []}
    assert q['rels_per_act'] == {'rev0': 0.0, 'rev1': 0.0}
    assert all(b['rev0'] == 0 and b['rev1'] == 0 for b in q['float_bands'])


def test_missing_matched_falls_back_gracefully():
    rev0, rev1 = _pair()
    q = build_quality(rev0, rev1, matched=None, cal=None)
    # still returns the full shape without throwing
    assert 'open_ends' in q and 'float_bands' in q
