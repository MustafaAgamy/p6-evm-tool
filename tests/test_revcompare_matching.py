"""Fuzzy activity matching across two baseline revisions (p6_revcompare.matching)."""
from datetime import datetime

from p6_evm.parser import ScheduleData
from p6_revcompare.matching import (
    name_ratio, evidence_score, match_activities, canonicalize,
)


def _act(code, name, wbs='WBS 1', dur=80.0, ps=None, codes=None, tt='Task', tf=None):
    return {'id': code, 'name': name, 'wbs_path': wbs, 'wbs_id': 'w', 'planned_duration': dur,
            'planned_start': ps, 'planned_finish': ps, 'activity_codes': codes or {},
            'task_type': tt, 'total_float_days': tf, 'calendar_id': 'c'}


def _sched(acts):
    d = ScheduleData()
    d.activities = {f'o{i}': a for i, a in enumerate(acts)}
    d.relationships = []
    return d


def test_name_ratio_normalises():
    assert name_ratio('Raft Slab — Zone B', 'raft slab zone b') > 0.95
    assert name_ratio('Excavation', 'Demolition') < 0.6


def test_evidence_score_same_work_scores_high():
    a = _act('A1', 'Waterproofing to Raft — Zone B', dur=112, ps=datetime(2025, 4, 12))
    b = _act('A2', 'Raft Waterproofing — Zone B', dur=112, ps=datetime(2025, 5, 2))
    assert evidence_score(a, b) >= 0.62


def test_exact_and_added_and_removed():
    rev0 = _sched([_act('A100', 'Excavate'), _act('A200', 'Blinding'), _act('A900', 'Old')])
    rev1 = _sched([_act('A100', 'Excavate'), _act('A200', 'Blinding'), _act('A300', 'Rebar wall')])
    m = match_activities(rev0, rev1)
    exact = {p['code0'] for p in m['pairs'] if p['match'] == 'exact'}
    assert exact == {'A100', 'A200'}
    assert [a['id'] for a in m['added']] == ['A300']
    assert [a['id'] for a in m['removed']] == ['A900']
    assert m['id_changes'] == []


def test_id_change_detected_not_added_removed():
    rev0 = _sched([_act('A1220', 'Waterproofing to Raft — Zone B', dur=112, ps=datetime(2025, 4, 12))])
    rev1 = _sched([_act('A1362', 'Raft Waterproofing — Zone B', dur=112, ps=datetime(2025, 5, 2))])
    m = match_activities(rev0, rev1)
    assert len(m['id_changes']) == 1
    p = m['id_changes'][0]
    assert (p['code0'], p['code1']) == ('A1220', 'A1362')
    assert p['canonical'] == 'A1220'
    assert m['added'] == [] and m['removed'] == []


def test_true_added_removed_not_false_matched():
    # Two genuinely different activities must NOT be fuzzy-matched.
    rev0 = _sched([_act('A1', 'Site mobilisation')])
    rev1 = _sched([_act('B9', 'Final commissioning and handover')])
    m = match_activities(rev0, rev1)
    assert m['id_changes'] == []
    assert len(m['added']) == 1 and len(m['removed']) == 1


def test_renamed_same_code():
    rev0 = _sched([_act('A100', 'Excavate to formation')])
    rev1 = _sched([_act('A100', 'Bulk earthworks and cart away')])
    m = match_activities(rev0, rev1)
    assert len(m['renamed']) == 1
    assert m['renamed'][0]['code0'] == 'A100'


def test_moved_wbs():
    rev0 = _sched([_act('A100', 'Ducting', wbs='WBS 1 > MEP')])
    rev1 = _sched([_act('A100', 'Ducting', wbs='WBS 2 > Services')])
    m = match_activities(rev0, rev1)
    assert len(m['moved_wbs']) == 1


def test_canonicalize_remaps_id_and_preserves_orig():
    rev1 = _sched([_act('A1362', 'Raft Waterproofing — Zone B')])
    clone = canonicalize(rev1, {'A1362': 'A1220'})
    act = list(clone.activities.values())[0]
    assert act['id'] == 'A1220'
    assert act['orig_id'] == 'A1362'
    # original untouched
    assert list(rev1.activities.values())[0]['id'] == 'A1362'


# ── Speed without a different answer (owner comment 36: no long wait on Run) ───────────
# The leftover pairs are no longer all run through difflib: a pair is skipped only when
# even its most generous name similarity cannot reach the accept score. The candidates
# (pairs AND scores) must be exactly what scoring every pair gives.

def _brute_candidates(by0, by1, left0, left1, accept):
    out = []
    for c0 in left0:
        for c1 in left1:
            s = evidence_score(by0[c0], by1[c1])
            if s >= accept:
                out.append((s, c0, c1))
    return out


def test_fuzzy_candidates_identical_to_scoring_every_pair():
    import random
    from p6_revcompare.matching import _fuzzy_candidates, ACCEPT_SCORE
    rnd = random.Random(20260930)
    words = ['Raft', 'Slab', 'Zone', 'B', 'Waterproofing', 'Excavation', 'Rebar', 'Wall', 'Pour',
             'Formwork', 'Column', 'C1', 'Level 2', '—', '(Phase 1)', 'Backfill', 'MEP', 'First-fix']
    wbs = ['WBS 1', 'WBS 1 / Civil', 'WBS 2', None, '']
    codes = [{}, {'AREA': 'A'}, {'AREA': 'B'}, {'AREA': 'A', 'TRADE': 'CIV'}, {'TRADE': 'CIV'}]

    def rand_act(code):
        n = ' '.join(rnd.choice(words) for _ in range(rnd.randint(0, 5)))
        ps = rnd.choice([None, datetime(2025, 1, 1 + rnd.randint(0, 27)), datetime(2025, rnd.randint(1, 12), 3)])
        return _act(code, rnd.choice([n, n.upper(), '', None]), wbs=rnd.choice(wbs),
                    dur=rnd.choice([0.0, 5.0, 10.0, 80.0, rnd.uniform(0, 120)]), ps=ps, codes=rnd.choice(codes))

    by0 = {f'O{i}': rand_act(f'O{i}') for i in range(90)}
    by1 = {f'N{i}': rand_act(f'N{i}') for i in range(90)}
    # near-copies so plenty of pairs sit right at (and around) the accept score
    for i in range(30):
        a = dict(by0[f'O{i}']); a['id'] = f'N{i}'
        a['name'] = (a['name'] or '') + rnd.choice(['', ' x', 's', ' Zone C'])
        by1[f'N{i}'] = a
    left0, left1 = sorted(by0), sorted(by1)
    for accept in (ACCEPT_SCORE, 0.5, 0.7, 0.3):
        fast = sorted(_fuzzy_candidates(by0, by1, left0, left1, accept))
        slow = sorted(_brute_candidates(by0, by1, left0, left1, accept))
        assert fast == slow
    assert len(slow) > 0


def test_fuzzy_candidates_keeps_a_pair_exactly_at_the_accept_score():
    from p6_revcompare.matching import _fuzzy_candidates
    a = _act('A1', 'Waterproofing to Raft — Zone B', dur=112, ps=datetime(2025, 4, 12))
    b = _act('A2', 'Raft Waterproofing — Zone B', dur=112, ps=datetime(2025, 5, 2))
    s = evidence_score(a, b)
    assert _fuzzy_candidates({'A1': a}, {'A2': b}, ['A1'], ['A2'], s) == [(s, 'A1', 'A2')]
    assert _fuzzy_candidates({'A1': a}, {'A2': b}, ['A1'], ['A2'], round(s + 0.0001, 4)) == []
