"""run_review assembles the report from a (mocked) AI response: counts, the two
percentages, the 45/45/10 score, and defensive unique suggested-ids."""
import copy

from p6_evm.parser import ScheduleData
from p6_ai.review import run_review


def _data():
    d = ScheduleData()
    d.wbs = {'w1': {'name': 'Civil', 'parent_object_id': None}}
    d.activities = {
        'o1': {'object_id': 'o1', 'id': 'A100', 'name': 'Excavate', 'wbs_id': 'w1',
               'wbs_path': 'Civil', 'task_type': 'Task', 'planned_duration': 40, 'calendar_id': None},
        'o2': {'object_id': 'o2', 'id': 'A200', 'name': 'Foundation', 'wbs_id': 'w1',
               'wbs_path': 'Civil', 'task_type': 'Task', 'planned_duration': 40, 'calendar_id': None},
    }
    d.relationships = [{'pred_id': 'o1', 'succ_id': 'o2', 'type': 'FS', 'lag_days': 0.0}]
    d.calendars = {}
    return d


_AI = {
    'project_type': 'Infrastructure — test',
    'understood': {'summary': 's', 'phases': [{'name': 'Civil', 'present': True}]},
    'illogical': [{
        'activity_id': 'A200', 'activity_name': 'Foundation', 'wbs_path': 'Civil',
        'current_preds': [{'id': 'A100', 'name': 'Excavate', 'rel': 'SS'}], 'current_succs': [],
        'why': 'w', 'suggested_preds': [{'id': 'A100', 'name': 'Excavate', 'rel': 'FS', 'kind': 'change'}],
        'suggested_succs': [], 'impact': 'Critical'}],
    'missing': [{
        'suggested_id': 'A100', 'name': 'Survey', 'wbs': 'Civil', 'new_wbs': False,
        'preds': [], 'succs': [{'id': 'A100', 'name': 'Excavate', 'rel': 'FS'}],
        'why': 'w', 'basis': 'AI knowledge'}],
    'missing_wbs': [{'name': 'Testing & Commissioning', 'why': 'w'}],
    'wbs_review': [{'name': 'Civil', 'status': 'ok', 'note': 'n'}],
    'conclusion': 'c',
}


def test_report_shape_counts_and_percentages():
    captured = {}

    def fake_call(request, api_key):
        captured['request'] = request
        captured['key'] = api_key
        return copy.deepcopy(_AI)

    rep = run_review(_data(), 'sk-x', cfg={'model': 'claude-opus-5'}, _call=fake_call)

    assert captured['key'] == 'sk-x'
    assert captured['request']['model'] == 'claude-opus-5'

    d = rep['dashboard']
    assert d['illogical_count'] == 1 and d['total_relationships'] == 1
    assert d['illogical_pct'] == 100.0           # 1 of 1 relationship
    assert d['missing_count'] == 1 and d['total_activities'] == 2
    assert d['missing_pct'] == 50.0              # 1 of 2 activities
    assert d['missing_wbs'] == 1
    assert d['critical_affected'] is True
    assert rep['mode'] == 'engineering'
    assert 'overall' in rep['score'] and 'band_label' in rep['score']


def test_suggested_id_collision_is_renamed():
    def fake_call(request, api_key):
        return copy.deepcopy(_AI)
    rep = run_review(_data(), 'sk-x', _call=fake_call)
    # A100 already exists in the schedule → the suggested new-activity id must differ
    assert rep['missing'][0]['suggested_id'] != 'A100'


def test_reference_mode_is_flagged_and_sent():
    def fake_call(request, api_key):
        # Mode 2 → the request instructs the AI that the reference outranks knowledge
        assert 'outrank' in request['system'].lower()
        return copy.deepcopy(_AI)
    rep = run_review(_data(), 'sk-x', reference_data=_data(), _call=fake_call)
    assert rep['mode'] == 'reference'
