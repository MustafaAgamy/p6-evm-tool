"""Phase 0 — schedule_view surfaces the data the parser already computes
(lag, activity codes, dates, float) and an ObjectId-keyed graph, without
changing the legacy code-keyed shape the v1 review depends on."""
import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.model import schedule_view


def _data(activities, relationships, wbs=('Zone A',)):
    d = types.SimpleNamespace()
    d.activities = {oid: dict(a, id=a.get('id', oid)) for oid, a in activities.items()}
    d.relationships = list(relationships)
    d.wbs = {f'W{i}': {'name': n} for i, n in enumerate(wbs)}
    d.activity_code_types = ['Type of Works', 'Zone']
    return d


def test_legacy_shape_is_unchanged():
    d = _data(
        {'O1': {'id': 'A1', 'name': 'Excavation', 'wbs_path': 'Zone A', 'task_type': 'Task'},
         'O2': {'id': 'A2', 'name': 'Handover', 'wbs_path': 'Zone A', 'task_type': 'FinishMilestone'}},
        [{'pred_id': 'O1', 'succ_id': 'O2', 'type': 'FS', 'lag_days': 2.0, 'lag_hours': 16.0}])
    v = schedule_view(d)
    assert v['activity_count'] == 2 and v['relationship_count'] == 1
    a = v['by_code']['A1']
    assert a['id'] == 'A1' and a['name'] == 'Excavation' and a['wbs_path'] == 'Zone A'
    assert v['by_code']['A2']['is_milestone'] is True
    assert v['relationships'][0]['pred'] == 'A1' and v['relationships'][0]['type'] == 'FS'


def test_lag_is_no_longer_dropped():
    d = _data(
        {'O1': {'id': 'A1', 'name': 'Pipe', 'wbs_path': '', 'task_type': 'Task'},
         'O2': {'id': 'A2', 'name': 'Test', 'wbs_path': '', 'task_type': 'Task'}},
        [{'pred_id': 'O1', 'succ_id': 'O2', 'type': 'FS', 'lag_days': 3.5, 'lag_hours': 28.0}])
    v = schedule_view(d)
    assert v['relationships'][0]['lag_days'] == 3.5
    assert v['relationships_oid'][0]['lag_days'] == 3.5 and v['relationships_oid'][0]['lag_hours'] == 28.0


def test_objectid_graph_is_dedup_safe():
    # two ObjectIds share one activity code (the real P6 duplicate-code hazard)
    d = _data(
        {'O1': {'id': 'DUP', 'name': 'Install (copy 1)', 'wbs_path': '', 'task_type': 'Task'},
         'O2': {'id': 'DUP', 'name': 'Install (copy 2)', 'wbs_path': '', 'task_type': 'Task'},
         'O3': {'id': 'A3', 'name': 'Test', 'wbs_path': '', 'task_type': 'Task'}},
        [{'pred_id': 'O1', 'succ_id': 'O3', 'type': 'FS', 'lag_days': 0, 'lag_hours': 0},
         {'pred_id': 'O2', 'succ_id': 'O3', 'type': 'FS', 'lag_days': 0, 'lag_hours': 0}])
    v = schedule_view(d)
    # ObjectId graph keeps BOTH copies distinct; the code-keyed map collapses to one
    assert len(v['activities_oid']) == 3 and len(v['by_oid']) == 3
    assert len(v['by_code']) == 2                        # DUP collapses (last-wins) in the legacy map
    assert len(v['relationships_oid']) == 2              # both real edges survive on the oid graph


def test_codes_and_fields_surfaced():
    d = _data({'O1': {'id': 'A1', 'name': 'Chiller', 'wbs_path': 'Plant',
                      'task_type': 'Task', 'status': 'Not Started', 'planned_duration': 80.0,
                      'total_float_days': 5.0, 'is_critical': False,
                      'activity_codes': {'Type of Works': 'MEP', 'Zone': 'L7'}}}, [])
    v = schedule_view(d)
    a = v['activities_oid'][0]
    assert a['object_id'] == 'O1' and a['activity_codes']['Type of Works'] == 'MEP'
    assert a['planned_duration'] == 80.0 and a['total_float_days'] == 5.0
    assert v['activity_code_types'] == ['Type of Works', 'Zone']
