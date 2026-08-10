"""The AI skeleton — the ONLY thing that leaves the machine.

Privacy contract (Decision 003 + Ibrahim's rule): activity names, durations,
links and WBS may go out; costs and the client/project name must not.
Relationships are keyed by activity *code*, never per-file ObjectIds.
"""
import json

from p6_evm.parser import ScheduleData
from p6_ai.skeleton import build_skeleton


def _data():
    d = ScheduleData()
    d.project = {'name': 'SECRET CLIENT TOWER', 'id': 'PRJ-1'}
    d.wbs = {
        'w1': {'name': 'Civil', 'parent_object_id': None},
        'w2': {'name': 'Testing & Commissioning', 'parent_object_id': None},
    }
    d.activities = {
        'o1': {'object_id': 'o1', 'id': 'A100', 'name': 'Excavate', 'wbs_id': 'w1',
               'wbs_path': 'Civil', 'task_type': 'Task', 'planned_duration': 80, 'calendar_id': None},
        'o2': {'object_id': 'o2', 'id': 'A200', 'name': 'Pour Foundation', 'wbs_id': 'w1',
               'wbs_path': 'Civil', 'task_type': 'Task', 'planned_duration': 40, 'calendar_id': None},
        'o3': {'object_id': 'o3', 'id': 'M1', 'name': 'Project Start', 'wbs_id': 'w1',
               'wbs_path': 'Civil', 'task_type': 'StartMilestone', 'planned_duration': 0, 'calendar_id': None},
    }
    d.relationships = [
        {'pred_id': 'o1', 'succ_id': 'o2', 'type': 'FS', 'lag_days': 0.0},
        {'pred_id': 'o2', 'succ_id': 'oX', 'type': 'FS', 'lag_days': 2.0},  # dangling → dropped
    ]
    d.calendars = {}
    return d


def test_costs_never_in_skeleton():
    d = _data()
    d.bac_by_activity = {'o1': 100000.0}
    d.ac_by_activity = {'o1': 50000.0}
    blob = json.dumps(build_skeleton(d))
    assert '100000' not in blob and '50000' not in blob
    assert 'cost' not in blob.lower() and 'bac' not in blob.lower()


def test_client_name_stripped():
    blob = json.dumps(build_skeleton(_data()))
    assert 'SECRET CLIENT TOWER' not in blob
    assert 'PRJ-1' not in blob


def test_relationships_use_activity_codes_not_oids():
    sk = build_skeleton(_data())
    simple = [{k: r[k] for k in ('pred', 'succ', 'type', 'lag_days')} for r in sk['relationships']]
    assert {'pred': 'A100', 'succ': 'A200', 'type': 'FS', 'lag_days': 0.0} in simple
    # relationship to an unknown ObjectId is dropped, never emitted as a raw oid
    assert all(r['succ'] != 'oX' for r in sk['relationships'])
    assert sk['relationship_count'] == 1


def test_milestone_flagged_and_counts():
    sk = build_skeleton(_data())
    assert sk['activity_count'] == 3
    milestones = [a for a in sk['activities'] if a['is_milestone']]
    assert len(milestones) == 1 and milestones[0]['id'] == 'M1'
    a100 = next(a for a in sk['activities'] if a['id'] == 'A100')
    assert a100['wbs_path'] == 'Civil'
    assert a100['duration_days'] == 10.0  # 80h / 8h-day


def test_wbs_scope_included():
    sk = build_skeleton(_data())
    names = {w['name'] for w in sk['wbs']}
    assert 'Civil' in names and 'Testing & Commissioning' in names


def test_activity_without_code_skipped():
    d = _data()
    d.activities['o4'] = {'object_id': 'o4', 'id': None, 'name': 'orphan',
                          'wbs_id': 'w1', 'wbs_path': 'Civil', 'task_type': 'Task',
                          'planned_duration': 0, 'calendar_id': None}
    sk = build_skeleton(d)
    assert sk['activity_count'] == 3  # orphan without a code is excluded
