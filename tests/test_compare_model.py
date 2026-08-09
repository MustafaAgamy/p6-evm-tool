"""MatchedSchedules — reconciles a baseline and an update ScheduleData.

Activities and relationships are matched by Activity CODE (id), never ObjectId:
ObjectIds are assigned per-file, so the same activity has different ObjectIds in
the baseline and the update.
"""
from p6_evm.parser import ScheduleData
from p6_compare.model import MatchedSchedules


def _sched(activities, relationships):
    d = ScheduleData()
    d.activities = activities
    d.relationships = relationships
    return d


def _base():
    return _sched(
        {'b1': {'id': 'A100', 'name': 'Excavate', 'task_type': 'Task'},
         'b2': {'id': 'A200', 'name': 'Blinding', 'task_type': 'Task'},
         'bm': {'id': 'M900', 'name': 'Handover', 'task_type': 'FinishMilestone'}},
        [{'pred_id': 'b1', 'succ_id': 'b2', 'type': 'FS', 'lag_days': 0.0}])


def _upd():
    return _sched(
        {'u1': {'id': 'A100', 'name': 'Excavate', 'task_type': 'Task'},
         'u2': {'id': 'A200', 'name': 'Blinding', 'task_type': 'Task'},
         'u3': {'id': 'A300', 'name': 'Rebar', 'task_type': 'Task'},
         'um': {'id': 'M900', 'name': 'Handover', 'task_type': 'FinishMilestone'}},
        [{'pred_id': 'u1', 'succ_id': 'u2', 'type': 'FS', 'lag_days': 10.0}])


def test_matches_activities_by_code_not_objectid():
    m = MatchedSchedules(_base(), _upd())
    assert m.matched_codes == ['A100', 'A200', 'M900']
    assert m.added_activity_codes == ['A300']
    assert m.removed_activity_codes == []


def test_relationships_keyed_by_code_pair():
    m = MatchedSchedules(_base(), _upd())
    # ObjectIds differ (b1/u1) but the pair keys on codes, so both sides align
    assert ('A100', 'A200') in m.baseline_rels
    assert ('A100', 'A200') in m.update_rels
    assert m.baseline_rels[('A100', 'A200')]['lag_days'] == 0.0
    assert m.update_rels[('A100', 'A200')]['lag_days'] == 10.0
    # names carried for the table
    assert m.update_rels[('A100', 'A200')]['pred_name'] == 'Excavate'
    assert m.update_rels[('A100', 'A200')]['succ_name'] == 'Blinding'


def test_milestone_codes():
    m = MatchedSchedules(_base(), _upd())
    assert m.milestone_codes == ['M900']
