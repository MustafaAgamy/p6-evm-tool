"""Sequence-chart logic for the Baseline Narrative — pure, no I/O.

Rules under test (all set with Ibrahim):
  * group per Type-of-Works / discipline code; fall back to the top WBS when absent;
  * roll activities up to their WBS work-package (Drilling + RFT both under "Pile");
  * order packages + steps by the scheduled (planned-start) order;
  * split into charts of <= max_steps, continuation labelled, nothing dropped;
  * milestones / LOE / summary rows are not steps.
"""
from datetime import datetime

from p6_narrative.sequence import build_sequences, pick_discipline_dim


def _act(oid, name, wbs_id, disc=None, start=None, tt='Task'):
    return {
        'object_id': oid, 'id': oid, 'name': name, 'wbs_id': wbs_id, 'task_type': tt,
        'activity_codes': ({'Type of Works': disc} if disc else {}),
        'planned_start': start,
    }


WBS = {
    'w_pile': {'name': 'Pile', 'parent_object_id': 'w_silo'},
    'w_col': {'name': 'Columns', 'parent_object_id': 'w_silo'},
    'w_silo': {'name': 'Silo 1', 'parent_object_id': None},
}


def test_pick_discipline_dim_matches_type_of_works():
    assert pick_discipline_dim(['WBS', 'Type of Works', 'Phase']) == 'Type of Works'
    assert pick_discipline_dim(['Trade Design', 'Phase']) == 'Trade Design'
    assert pick_discipline_dim(['Phase', 'Area']) is None


def test_groups_by_discipline_and_rolls_up_to_wbs_package():
    acts = [
        _act('1', 'Drilling Piles', 'w_pile', 'Civil', datetime(2026, 1, 1)),
        _act('2', 'RFT Piles', 'w_pile', 'Civil', datetime(2026, 1, 3)),
        _act('3', 'Concrete Pour Piles', 'w_pile', 'Civil', datetime(2026, 1, 5)),
        _act('4', 'RFT Columns', 'w_col', 'Civil', datetime(2026, 1, 10)),
    ]
    charts = build_sequences(acts, WBS, code_types=['Type of Works'])
    assert len(charts) == 1
    c = charts[0]
    assert c['discipline'] == 'Civil'
    # Drilling + RFT roll up under the same "Pile" package — not two groups
    assert [p['name'] for p in c['packages']] == ['Pile', 'Columns']
    assert [s['name'] for s in c['packages'][0]['steps']] == [
        'Drilling Piles', 'RFT Piles', 'Concrete Pour Piles']


def test_separate_disciplines_make_separate_charts():
    acts = [
        _act('1', 'Drilling', 'w_pile', 'Civil', datetime(2026, 1, 1)),
        _act('2', 'Erect steel', 'w_col', 'Steel', datetime(2026, 2, 1)),
    ]
    charts = build_sequences(acts, WBS, code_types=['Type of Works'])
    assert {c['discipline'] for c in charts} == {'Civil', 'Steel'}


def test_caps_at_max_steps_and_continues_without_dropping():
    acts = [_act(str(i), f'Step {i}', 'w_pile', 'Civil', datetime(2026, 1, (i % 27) + 1))
            for i in range(1, 19)]  # 18 steps in one package
    charts = build_sequences(acts, WBS, code_types=['Type of Works'], max_steps=15)
    assert len(charts) == 2
    assert (charts[0]['chart_index'], charts[0]['chart_count']) == (1, 2)
    assert (charts[1]['chart_index'], charts[1]['chart_count']) == (2, 2)
    total = sum(len(p['steps']) for c in charts for p in c['packages'])
    assert total == 18  # nothing dropped
    assert charts[0]['steps_total'] == 18


def test_falls_back_to_wbs_when_no_discipline_code():
    acts = [_act('1', 'A', 'w_pile', None, datetime(2026, 1, 1))]
    charts = build_sequences(acts, WBS, code_types=[])
    assert len(charts) == 1
    assert charts[0]['discipline'] == 'Silo 1'  # top-level WBS name


def test_skips_milestones_and_summary_rows():
    acts = [
        _act('1', 'Start MS', 'w_pile', 'Civil', datetime(2026, 1, 1), tt='StartMilestone'),
        _act('2', 'Summary', 'w_silo', 'Civil', datetime(2026, 1, 1), tt='WBSSummary'),
    ]
    assert build_sequences(acts, WBS, code_types=['Type of Works']) == []
