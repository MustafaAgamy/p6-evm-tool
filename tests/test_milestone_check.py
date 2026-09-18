from datetime import datetime

from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.milestone_check import evaluate_milestones, _match, _norm


def _g(acts, data_date=None, calendars=None):
    d = ScheduleData()
    d.activities = acts
    d.relationships = []
    if calendars:
        d.calendars = calendars
    if data_date is not None:
        d.project = {'data_date': data_date}
    return ScheduleGraph(d)


def _act(oid, name, **kw):
    b = {'object_id': oid, 'id': oid, 'name': name, 'task_type': 'FinishMilestone',
         'is_critical': False, 'total_float_days': 0, 'planned_finish': None,
         'remaining_early_finish': None, 'calendar_id': None, 'constraint_type': None,
         'constraint_date': None, 'wbs_path': 'P'}
    b.update(kw)
    return b


def test_unmatched_invents_nothing():
    g = _g({'a': _act('a', 'Some Other Task', task_type='Task')})
    r = evaluate_milestones(g, [{'name': 'Mechanical Completion', 'date': '2027-06-30'}])[0]
    assert r['status'] == 'Unmatched'
    assert r['matched_activity_id'] is None
    assert r['scheduled_finish'] is None
    assert 'No schedule activity' in r['finding']


def test_on_track_when_finish_before_contract():
    g = _g({'m': _act('m', 'Mechanical Completion', planned_finish=datetime(2027, 6, 15), total_float_days=5)})
    r = evaluate_milestones(g, [{'name': 'Mechanical Completion', 'date': '2027-06-30'}])[0]
    assert r['matched_activity_id'] == 'm'
    assert r['status'] == 'On track'
    assert r['variance_days'] <= 0


def test_late_when_finish_after_contract_no_constraint():
    g = _g({'m': _act('m', 'Substantial Handover', planned_finish=datetime(2028, 1, 4),
                      total_float_days=-12, is_critical=True)})
    r = evaluate_milestones(g, [{'name': 'Substantial Handover', 'date': '2027-12-15'}])[0]
    assert r['status'] == 'Late'
    assert r['variance_days'] > 0
    assert r['on_driving_path'] is True
    assert r['constraint_type'] is None


def test_masked_when_finish_hard_constraint_hides_negative_float():
    g = _g({'m': _act('m', 'Mechanical Completion', planned_finish=datetime(2027, 6, 30),
                      total_float_days=-15, is_critical=True,
                      constraint_type='Finish On', constraint_date=datetime(2027, 6, 30))})
    r = evaluate_milestones(g, [{'name': 'Mechanical Completion', 'date': '2027-06-30'}])[0]
    assert r['status'] == 'Masked'
    assert r['constraint_type'] == 'Finish On'
    assert 'masking' in r['root_cause']


def test_match_prefers_milestone_and_is_case_insensitive():
    g = _g({'t': _act('t', 'mechanical completion', task_type='Task'),
            'm': _act('m', 'Mechanical Completion', task_type='FinishMilestone')})
    assert _match(g, 'MECHANICAL COMPLETION')[0] == 'm'   # milestone preferred over the task


def test_norm_strips_punctuation_and_case():
    assert _norm('  Mechanical-Completion (Contract) ') == 'mechanical completion contract'


def test_build_milestone_module_merges_and_gates():
    from p6_audit.milestone_check import build_milestone_module, NAME
    g = _g({'m': _act('m', 'Mechanical Completion', planned_finish=datetime(2027, 6, 15), total_float_days=5)})
    hard = {'module': 'hard_constraints', 'name': 'Hard Constraints', 'score': 100,
            'grade': 'Excellent', 'pct': 0, 'kpis': {}, 'findings': []}
    # no contract milestones -> gate B
    empty = build_milestone_module(hard, g, [])
    assert empty['name'] == NAME == 'Milestone Check'
    assert empty['needs_input'] is True
    assert any(b['name'] == 'Mechanical Completion' for b in empty['baseline_milestones'])
    # with a milestone -> evaluated, not gated, hard-constraint score preserved
    filled = build_milestone_module(hard, g, [{'name': 'Mechanical Completion', 'date': '2027-06-30'}])
    assert filled['needs_input'] is False
    assert filled['score'] == 100
    assert len(filled['milestones']) == 1
    assert filled['milestone_counts']['On track'] == 1
