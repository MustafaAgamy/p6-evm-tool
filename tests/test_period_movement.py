"""p6_period.movement — finish slip, critical-path movement, buckets, milestone drift."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_period.movement import finish_slip, critical_movement, buckets, milestone_drift
from p6_compare.model import MatchedSchedules


def _act(code, name, pct=0.0, finish=None, tf=None, ts='Task', start=None, dur=80.0):
    return {'id': code, 'name': name, 'percent_complete': pct, 'task_type': ts,
            'planned_finish': finish, 'remaining_early_finish': finish,
            'planned_start': start, 'remaining_early_start': start,
            'total_float_days': tf, 'planned_duration': dur, 'calendar_id': None}


def _sched(acts):
    d = ScheduleData()
    d.activities = {f'o{i}': a for i, a in enumerate(acts)}
    d.calendars = {}
    d.project = {}
    return d


def test_finish_slip_signed_calendar_days_without_calendar():
    prev = _sched([_act('A1', 'x', finish=datetime(2026, 8, 18))])
    curr = _sched([_act('A1', 'x', finish=datetime(2026, 9, 1))])
    slips = finish_slip(MatchedSchedules(prev, curr))
    assert slips['A1'] == 14


def test_critical_movement_flags_slipped_and_newly_critical():
    # CV1: stayed critical (float 0 both), finish slipped 10 d
    # CV2: newly critical (float was 40, now 4), finish held
    # CV3: comfortable float, ignored
    prev = _sched([_act('CV1', 'Quay', finish=datetime(2026, 8, 18), tf=0),
                   _act('CV2', 'Loader', finish=datetime(2026, 9, 5), tf=40),
                   _act('CV3', 'Fence', finish=datetime(2026, 9, 5), tf=30)])
    curr = _sched([_act('CV1', 'Quay', finish=datetime(2026, 9, 1), tf=0),
                   _act('CV2', 'Loader', finish=datetime(2026, 9, 5), tf=4),
                   _act('CV3', 'Fence', finish=datetime(2026, 9, 5), tf=30)])
    out = critical_movement(MatchedSchedules(prev, curr), logic_changed_codes={'CV2'})
    ids = [r['activity_id'] for r in out['rows']]
    assert set(ids) == {'CV1', 'CV2'} and 'CV3' not in ids
    assert out['new_critical'] == 1                       # CV2 entered the critical path
    by = {r['activity_id']: r for r in out['rows']}
    assert by['CV1']['slip_days'] == 14 and by['CV1']['critical_status'] == 'stayed'
    assert by['CV1']['driver'] == 'progress shortfall'
    assert by['CV2']['critical_status'] == 'new' and by['CV2']['driver'] == 'logic changed'


def test_buckets_counts_finished_started_slipped_and_resequenced():
    prev = _sched([_act('F1', 'Done soon', pct=0.80, finish=datetime(2026, 7, 1)),
                   _act('S1', 'Fresh', pct=0.0, finish=datetime(2026, 8, 1)),
                   _act('L1', 'Late', pct=0.30, finish=datetime(2026, 8, 1))])
    curr = _sched([_act('F1', 'Done soon', pct=1.0, finish=datetime(2026, 7, 1)),
                   _act('S1', 'Fresh', pct=0.10, finish=datetime(2026, 8, 1)),
                   _act('L1', 'Late', pct=0.30, finish=datetime(2026, 8, 20))])
    out = buckets(MatchedSchedules(prev, curr), dd_now=datetime(2026, 7, 31),
                  logic_changed_codes={'L1'})
    c = out['counts']
    assert c['finished'] == 1 and c['started'] == 1
    assert c['slipped'] == 1                              # L1 finish moved later
    assert c['re_sequenced'] == 1                         # L1 logic changed vs last period
    assert {r['activity_id'] for r in out['lists']['finished']} == {'F1'}


def _sched_bl(acts, baseline):
    d = _sched(acts)
    d.baseline_by_id = baseline
    return d


def test_milestone_drift_finish_only_and_overall_is_latest():
    prev = _sched_bl([
        _act('S1', 'Start', ts='StartMilestone', finish=datetime(2026, 1, 1)),
        _act('M1', 'Section handover', ts='FinishMilestone', finish=datetime(2026, 11, 1)),
        _act('M9', 'Project completion', ts='FinishMilestone', finish=datetime(2027, 2, 9)),
    ], {})
    curr = _sched_bl([
        _act('S1', 'Start', ts='StartMilestone', finish=datetime(2026, 1, 1)),
        _act('M1', 'Section handover', ts='FinishMilestone', finish=datetime(2026, 11, 8)),
        _act('M9', 'Project completion', ts='FinishMilestone', finish=datetime(2027, 3, 1)),
    ], {'M1': {'planned_finish': datetime(2026, 11, 1)}, 'M9': {'planned_finish': datetime(2027, 2, 9)}})
    md = milestone_drift(MatchedSchedules(prev, curr))
    ids = {r['activity_id'] for r in md['rows']}
    assert ids == {'M1', 'M9'}                       # finish milestones only (start excluded)
    assert md['overall']['activity_id'] == 'M9'      # latest current forecast = project completion
    assert md['overall']['slip_baseline_days'] is not None
