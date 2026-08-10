"""p6_period.progress — activity % complete variance and the Option-B period summary.

Progress is measured against LAST PERIOD'S FORECAST: forecast_at_now = actual_prev +
the previous update's scheduled increment across the window. All percentages are
0-100 (percent_complete is a 0-1 fraction internally, scaled up here)."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_period.progress import activity_progress, period_summary
from p6_compare.model import MatchedSchedules


def _act(code, name, pct, ts=None, tf=None, s=None, f=None):
    return {'id': code, 'name': name, 'percent_complete': pct, 'task_type': ts or 'Task',
            'planned_start': s, 'planned_finish': f, 'remaining_early_start': s,
            'remaining_early_finish': f, 'planned_duration': 8.0, 'total_float_days': tf}


def _sched(acts, dd=None):
    d = ScheduleData()
    d.activities = {f'o{i}': a for i, a in enumerate(acts)}
    d.project = {'name': 'Grain Terminal', 'data_date': dd}
    return d


# ── activity_progress ────────────────────────────────────────────────────────

def test_progress_lists_only_changed_activities_biggest_first():
    prev = _sched([_act('A1', 'Dredging', 0.82), _act('A2', 'Quay wall', 0.55),
                   _act('A3', 'Idle', 0.20)])
    curr = _sched([_act('A1', 'Dredging', 1.00), _act('A2', 'Quay wall', 0.68),
                   _act('A3', 'Idle', 0.20)])
    out = activity_progress(MatchedSchedules(prev, curr))
    ids = [r['activity_id'] for r in out['rows']]
    assert ids == ['A1', 'A2']                      # A3 unchanged omitted; sorted by variance desc
    assert out['rows'][0]['variance'] == 18.0        # 100 - 82, on the 0-100 scale
    assert out['rows'][0]['prev_pct'] == 82.0 and out['rows'][0]['curr_pct'] == 100.0
    assert out['rows'][0]['finished'] is True
    assert out['rows'][1]['variance'] == 13.0


def test_progress_flags_started_and_reversal():
    prev = _sched([_act('S1', 'New start', 0.0), _act('R1', 'Reversed', 0.40)])
    curr = _sched([_act('S1', 'New start', 0.15), _act('R1', 'Reversed', 0.35)])
    out = activity_progress(MatchedSchedules(prev, curr))
    by = {r['activity_id']: r for r in out['rows']}
    assert by['S1']['started'] is True and by['S1']['variance'] == 15.0
    assert by['R1']['reversal'] is True and by['R1']['variance'] == -5.0
    # reversals sink below gains
    assert out['rows'][-1]['activity_id'] == 'R1'
    assert out['counts']['reversed'] == 1 and out['counts']['started'] == 1


def test_progress_excludes_milestones():
    prev = _sched([_act('M1', 'Handover', 0.0, ts='FinishMilestone')])
    curr = _sched([_act('M1', 'Handover', 1.0, ts='FinishMilestone')])
    out = activity_progress(MatchedSchedules(prev, curr))
    assert out['rows'] == []


# ── period_summary (Option B) ────────────────────────────────────────────────

def test_period_summary_option_b_achievement_and_shortfall():
    dd_prev, dd_now = datetime(2026, 6, 30), datetime(2026, 7, 31)
    # one activity spanning Jun->Sep so ~ the window carries scheduled work
    prev = _sched([_act('A1', 'Work', 0.34, s=datetime(2026, 6, 1), f=datetime(2026, 9, 1))], dd=dd_prev)
    curr = _sched([_act('A1', 'Work', 0.41, s=datetime(2026, 6, 1), f=datetime(2026, 9, 1))], dd=dd_now)
    pm = {'overall_actual_pct': 0.34, 'delay_days': 22}
    cm = {'overall_actual_pct': 0.41, 'delay_days': 30}
    s = period_summary(prev, curr, pm, cm)
    assert s['actual_prev'] == 34.0 and s['actual_now'] == 41.0
    assert s['period_earned'] == 7.0
    assert s['period_forecast'] > 0                       # prev scheduled progress across the window
    assert s['forecast_at_now'] == round(34.0 + s['period_forecast'], 1)
    assert s['shortfall_pct'] == round(s['forecast_at_now'] - 41.0, 1)
    # achievement = earned / forecast
    assert s['forecast_achievement'] == round(7.0 / s['period_forecast'], 2)
    assert s['delay_change'] == 8


def test_period_summary_guards_zero_forecast():
    dd = datetime(2026, 7, 31)
    prev = _sched([_act('A1', 'Done', 1.0)], dd=datetime(2026, 6, 30))
    curr = _sched([_act('A1', 'Done', 1.0)], dd=dd)
    s = period_summary(prev, curr, {'overall_actual_pct': 1.0, 'delay_days': None},
                       {'overall_actual_pct': 1.0, 'delay_days': None})
    assert s['forecast_achievement'] is None            # no scheduled work -> no divide by zero
    assert s['delay_change'] is None
