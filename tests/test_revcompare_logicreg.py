"""Unit tests for the logic (relationship) register — p6_revcompare.logicreg."""
from p6_compare.model import MatchedSchedules
from p6_revcompare.logicreg import build_logic_register

from tests.test_revcompare_engine import _act, _sched, _pair, D


def _matched(rev0_rels, rev1_rels, acts=None):
    """Two tiny schedules sharing the same activity codes, differing only in logic."""
    acts = acts or [
        _act('A', 'Excavation'),
        _act('B', 'Blinding'),
        _act('C', 'Raft'),
        _act('D', 'Columns'),
    ]
    rev0 = _sched([dict(a) for a in acts], rev0_rels, D(2025, 3, 1))
    rev1 = _sched([dict(a) for a in acts], rev1_rels, D(2025, 3, 1))
    return MatchedSchedules(rev0, rev1)


def test_link_added():
    m = _matched([('A', 'B', 'FS', 0)],
                 [('A', 'B', 'FS', 0), ('B', 'C', 'FS', 0)])
    rows = build_logic_register(m, set())
    added = [r for r in rows if r['change'] == 'Link added']
    assert len(added) == 1
    r = added[0]
    assert r['pred_id'] == 'B' and r['succ_id'] == 'C'
    assert r['before'] == '— no link'
    assert r['after'] == 'Finish-to-Start (FS) · +0 d'
    assert r['pred_name'] == 'Blinding' and r['succ_name'] == 'Raft'


def test_link_removed():
    m = _matched([('A', 'B', 'FS', 0), ('B', 'C', 'FS', 0)],
                 [('A', 'B', 'FS', 0)])
    rows = build_logic_register(m, set())
    removed = [r for r in rows if r['change'] == 'Link removed']
    assert len(removed) == 1
    r = removed[0]
    assert r['pred_id'] == 'B' and r['succ_id'] == 'C'
    assert r['before'] == 'Finish-to-Start (FS) · +0 d'
    assert r['after'] == '— link removed'
    assert r['is_lead'] is False


def test_type_changed_full_names():
    m = _matched([('A', 'B', 'FS', 0)],
                 [('A', 'B', 'SS', 0)])
    rows = build_logic_register(m, set())
    assert len(rows) == 1
    r = rows[0]
    assert r['change'] == 'Type changed'
    assert r['before'] == 'Finish-to-Start (FS) · +0 d'
    assert r['after'] == 'Start-to-Start (SS) · +0 d'


def test_lag_changed():
    m = _matched([('A', 'B', 'FS', 0)],
                 [('A', 'B', 'FS', 5)])
    rows = build_logic_register(m, set())
    assert len(rows) == 1
    r = rows[0]
    assert r['change'] == 'Lag changed'
    assert r['before'] == 'Finish-to-Start (FS) · +0 d'
    assert r['after'] == 'Finish-to-Start (FS) · +5 d'
    assert r['is_lead'] is False


def test_type_change_wins_over_lag_change():
    # Both type and lag differ — reported once, as a Type changed (mirrors _logic_stats).
    m = _matched([('A', 'B', 'FS', 0)],
                 [('A', 'B', 'SS', 3)])
    rows = build_logic_register(m, set())
    assert len(rows) == 1
    assert rows[0]['change'] == 'Type changed'


def test_is_lead_negative_lag_after():
    m = _matched([('A', 'B', 'FS', 0)],
                 [('A', 'B', 'FS', -3)])
    rows = build_logic_register(m, set())
    assert len(rows) == 1
    assert rows[0]['change'] == 'Lag changed'
    assert rows[0]['after'] == 'Finish-to-Start (FS) · -3 d'
    assert rows[0]['is_lead'] is True


def test_unchanged_rels_produce_no_rows():
    rels = [('A', 'B', 'FS', 0), ('B', 'C', 'FS', 2)]
    m = _matched(rels, list(rels))
    assert build_logic_register(m, set()) == []


def test_on_cp_flag_and_sort_first():
    m = _matched(
        [('A', 'B', 'FS', 0)],
        [('A', 'B', 'SS', 0),       # off critical path (change on A/B)
         ('C', 'D', 'FS', 0)],      # link added on critical path (C, D in crit1)
    )
    rows = build_logic_register(m, {'C', 'D'})
    assert len(rows) == 2
    # Critical-path row sorts first.
    assert rows[0]['on_cp'] is True
    assert (rows[0]['pred_id'], rows[0]['succ_id']) == ('C', 'D')
    assert rows[1]['on_cp'] is False


def test_on_cp_true_when_either_endpoint_critical():
    m = _matched([('A', 'B', 'FS', 0)], [('A', 'B', 'FS', 4)])
    rows = build_logic_register(m, {'B'})   # only successor is critical
    assert rows[0]['on_cp'] is True


def test_guards_none_and_empty():
    assert build_logic_register(None, set()) == []
    m = _matched([], [])
    assert build_logic_register(m, None) == []


def test_end_to_end_against_pair_fixture():
    # The engine fixture: A2050→A2075 flips FS→SS between revisions (a real type change).
    from p6_revcompare.matching import match_activities, canonicalize
    rev0, rev1 = _pair()
    match = match_activities(rev0, rev1)
    rev1c = canonicalize(rev1, match['canonical'])
    m = MatchedSchedules(rev0, rev1c)
    rows = build_logic_register(m, {'A2075', 'A2050'})
    tc = [r for r in rows if r['pred_id'] == 'A2050' and r['succ_id'] == 'A2075']
    assert len(tc) == 1
    assert tc[0]['change'] == 'Type changed'
    assert tc[0]['before'].startswith('Finish-to-Start')
    assert tc[0]['after'].startswith('Start-to-Start')
    assert tc[0]['on_cp'] is True
