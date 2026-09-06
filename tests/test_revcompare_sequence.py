"""Sequence-change (execution-order reversal) detection (p6_revcompare.sequence)."""
from p6_evm.parser import ScheduleData
from p6_compare.model import MatchedSchedules
from p6_revcompare.sequence import detect_sequence_changes


def _sched(acts, rels):
    d = ScheduleData()
    d.activities = {f'o{i}': a for i, a in enumerate(acts)}
    code2oid = {a['id']: f'o{i}' for i, a in enumerate(acts)}
    d.relationships = [{'pred_id': code2oid[p], 'succ_id': code2oid[s], 'type': 'FS', 'lag_days': 0.0}
                       for p, s in rels]
    return d


def _a(code, name):
    return {'id': code, 'name': name, 'task_type': 'Task', 'wbs_path': 'WBS 1', 'total_float_days': 0}


def test_detects_reversal():
    # Rev0: Blinding→WP→Raft→Columns ; Rev1: Blinding→Raft→WP→Columns  (WP and Raft swap)
    rev0 = _sched([_a('B', 'Blinding'), _a('WP', 'Waterproofing'), _a('R', 'Raft'), _a('C', 'Columns')],
                  [('B', 'WP'), ('WP', 'R'), ('R', 'C')])
    rev1 = _sched([_a('B', 'Blinding'), _a('WP', 'Waterproofing'), _a('R', 'Raft'), _a('C', 'Columns')],
                  [('B', 'R'), ('R', 'WP'), ('WP', 'C')])
    seqs = detect_sequence_changes(MatchedSchedules(rev0, rev1))
    assert len(seqs) == 1
    s = seqs[0]
    assert {s['a'], s['b']} == {'WP', 'R'}
    # the reversed pair and its neighbours are recorded so the register can fold them
    assert set(s['involved']) >= {'WP', 'R'}
    assert s['chain0'] and s['chain1']


def test_no_reversal_when_order_unchanged():
    rev0 = _sched([_a('A', 'A'), _a('B', 'B')], [('A', 'B')])
    rev1 = _sched([_a('A', 'A'), _a('B', 'B')], [('A', 'B')])
    assert detect_sequence_changes(MatchedSchedules(rev0, rev1)) == []


def test_added_relationship_is_not_a_reversal():
    # A new parallel link is a logic change, not an order reversal.
    rev0 = _sched([_a('A', 'A'), _a('B', 'B'), _a('C', 'C')], [('A', 'B')])
    rev1 = _sched([_a('A', 'A'), _a('B', 'B'), _a('C', 'C')], [('A', 'B'), ('A', 'C')])
    assert detect_sequence_changes(MatchedSchedules(rev0, rev1)) == []
