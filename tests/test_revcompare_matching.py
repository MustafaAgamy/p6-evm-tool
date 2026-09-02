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
