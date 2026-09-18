"""p6_period.outlook — schedule adherence, recovery outlook, next-period watch list."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_compare.model import MatchedSchedules
from p6_period.outlook import schedule_adherence, recovery_outlook, watch_list


def _sched(acts, dd=None, baseline=None):
    d = ScheduleData()
    d.activities = {f'o{i}': a for i, a in enumerate(acts)}
    d.project = {'name': 'T', 'data_date': dd}
    d.baseline_by_id = baseline or {}
    return d


def _a(code, pct, ts='Task', ref=None, res=None, tf=None):
    return {'id': code, 'name': code, 'task_type': ts, 'percent_complete': pct,
            'remaining_early_finish': ref, 'planned_finish': ref,
            'remaining_early_start': res, 'planned_start': res, 'total_float_days': tf}


# ── schedule adherence ───────────────────────────────────────────────────────

def test_schedule_adherence_hit_rate():
    dd_prev, dd_now = datetime(2026, 7, 1), datetime(2026, 7, 31)
    prev = _sched([_a('A1', 0.5, ref=datetime(2026, 7, 15)),   # due this window
                   _a('A2', 0.3, ref=datetime(2026, 7, 20)),   # due this window
                   _a('A3', 0.0, ref=datetime(2026, 8, 15)),   # due later → not counted
                   _a('A4', 1.0, ref=datetime(2026, 7, 10))])  # already done → not counted
    curr = _sched([_a('A1', 1.0), _a('A2', 0.6), _a('A3', 0.1), _a('A4', 1.0)])
    r = schedule_adherence(MatchedSchedules(prev, curr), dd_prev, dd_now)
    assert r == {'planned': 2, 'hit': 1, 'pct': 50.0}


# ── recovery outlook ─────────────────────────────────────────────────────────

def test_recovery_outlook_projects_and_flags_infeasible():
    dd_prev, dd_now = datetime(2026, 7, 1), datetime(2026, 7, 31)
    bl = {'M9': {'planned_start': datetime(2026, 1, 1), 'planned_finish': datetime(2027, 3, 1)}}
    prev = _sched([_a('A1', 0.34)], dd=dd_prev)
    curr = _sched([_a('A1', 0.41), _a('M9', 0.0, ts='FinishMilestone')], dd=dd_now, baseline=bl)
    summary = {'actual_now': 41.0, 'period_earned': 7.0, 'period_forecast': 9.0}
    r = recovery_outlook(prev, curr, summary)
    assert r['work_remaining'] == 59.0
    assert r['projected_finish'] is not None                    # at 7%/period it lands somewhere
    assert r['baseline_finish'] == '01-Mar-2027'
    assert r['required_rate'] is not None and r['required_rate'] > r['current_rate']
    assert r['feasible'] is False                               # 7%/period < required


def test_recovery_outlook_no_progress_guarded():
    dd_prev, dd_now = datetime(2026, 7, 1), datetime(2026, 7, 31)
    prev = _sched([_a('A1', 0.4)], dd=dd_prev)
    curr = _sched([_a('A1', 0.4)], dd=dd_now)
    r = recovery_outlook(prev, curr, {'actual_now': 40.0, 'period_earned': 0.0, 'period_forecast': 0.0})
    assert r['projected_finish'] is None and 'projected' in r['note'].lower()


# ── watch list ───────────────────────────────────────────────────────────────

def test_watch_list_near_critical_sorted_and_filtered():
    curr = _sched([
        _a('W1', 0.2, res=datetime(2026, 8, 5), tf=0.0),      # critical, in progress
        _a('W2', 0.0, res=datetime(2026, 8, 10), tf=5.0),     # near-critical
        _a('W3', 0.5, res=datetime(2026, 8, 1), tf=30.0),     # lots of float → excluded
        _a('W4', 1.0, res=datetime(2026, 8, 1), tf=0.0),      # done → excluded
        _a('M1', 0.0, ts='FinishMilestone', tf=0.0),          # milestone → excluded
    ])
    rows = watch_list(curr)['rows']
    assert [r['activity_id'] for r in rows] == ['W1', 'W2']    # tightest float first
    assert rows[0]['reason'].startswith('On the critical path')
    assert rows[1]['float_days'] == 5.0 and rows[1]['due_to_start'] == '10-Aug-2026'
