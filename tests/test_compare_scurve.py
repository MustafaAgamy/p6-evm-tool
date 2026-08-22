"""three_way_scurve — cumulative planned-% curves for baseline / before / after on a
shared monthly axis. Each activity spreads its duration-weight linearly across its
planned span; the curve is the weight-fraction scheduled complete by each boundary."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_compare.scurve import cumulative_pct, three_way_scurve


def _sched(spans):
    d = ScheduleData()
    d.activities = {
        str(i): {'id': f'A{i}', 'task_type': 'Task', 'planned_start': s, 'planned_finish': f, 'planned_duration': w}
        for i, (s, f, w) in enumerate(spans)
    }
    return d


def test_cumulative_linear_midpoint():
    d = _sched([(datetime(2026, 1, 1), datetime(2026, 1, 11), 100)])
    boundaries = [datetime(2026, 1, 1), datetime(2026, 1, 6), datetime(2026, 1, 11)]
    assert cumulative_pct(d, boundaries) == [0.0, 50.0, 100.0]


def test_cumulative_weighted_across_two_activities():
    d = _sched([(datetime(2026, 1, 1), datetime(2026, 1, 11), 100),
                (datetime(2026, 1, 1), datetime(2026, 1, 11), 300)])
    assert cumulative_pct(d, [datetime(2026, 1, 6)]) == [50.0]   # both half-done → 50% overall


def test_cumulative_clamps_before_start_and_after_finish():
    d = _sched([(datetime(2026, 2, 1), datetime(2026, 3, 1), 100)])
    assert cumulative_pct(d, [datetime(2026, 1, 1)]) == [0.0]
    assert cumulative_pct(d, [datetime(2026, 4, 1)]) == [100.0]


def test_three_way_shapes_and_before_leads_after():
    baseline = _sched([(datetime(2026, 1, 1), datetime(2026, 3, 1), 100)])
    update = _sched([(datetime(2026, 1, 1), datetime(2026, 4, 1), 100)])     # after: slipped later
    corrected = _sched([(datetime(2026, 1, 1), datetime(2026, 2, 15), 100)])  # before: earlier finish
    r = three_way_scurve(baseline, update, corrected)
    assert set(r) == {'periods', 'baseline', 'before', 'after', 'markers'}
    n = len(r['periods'])
    assert n > 0 and n == len(r['baseline']) == len(r['before']) == len(r['after'])
    assert r['baseline'][-1] == 100.0 and r['before'][-1] == 100.0 and r['after'][-1] == 100.0
    assert max(bef - aft for bef, aft in zip(r['before'], r['after'])) > 0   # before leads after


def test_scurve_excludes_non_task_activities():
    # A trailing milestone/LOE finishing later must NOT tail the curve past the task finish.
    d = _sched([(datetime(2026, 1, 1), datetime(2026, 2, 1), 100)])
    d.activities['m'] = {'id': 'M1', 'task_type': 'FinishMilestone',
                         'planned_start': datetime(2026, 1, 1), 'planned_finish': datetime(2026, 4, 1),
                         'planned_duration': 50}
    assert cumulative_pct(d, [datetime(2026, 2, 1)]) == [100.0]   # 100% at the task finish; milestone ignored


def test_scurve_anchors_to_scheduled_finish():
    # An activity planned to Apr but the schedule's finish is Feb → the curve must reach 100%
    # at Feb (the finish the dashboard shows), not tail to April.
    d = _sched([(datetime(2026, 1, 1), datetime(2026, 4, 1), 100)])
    d.project = {'scheduled_finish': datetime(2026, 2, 1)}
    assert cumulative_pct(d, [datetime(2026, 2, 1)], cap=datetime(2026, 2, 1)) == [100.0]


def test_three_way_marks_baseline_and_update_finishes():
    baseline = _sched([(datetime(2026, 1, 1), datetime(2026, 3, 1), 100)]); baseline.project = {'scheduled_finish': datetime(2026, 3, 1)}
    update = _sched([(datetime(2026, 1, 1), datetime(2026, 6, 1), 100)]); update.project = {'scheduled_finish': datetime(2026, 6, 1)}
    corrected = _sched([(datetime(2026, 1, 1), datetime(2026, 4, 1), 100)]); corrected.project = {'scheduled_finish': datetime(2026, 4, 1)}
    m = three_way_scurve(baseline, update, corrected)['markers']
    assert m['baseline_label'] == '01-Mar-2026' and m['update_label'] == '01-Jun-2026'
    assert m['update_idx'] > m['baseline_idx']            # update finishes later → its marker is to the right


def test_three_way_empty_schedules():
    e = ScheduleData()
    assert three_way_scurve(e, e, e) == {'periods': [], 'baseline': [], 'before': [], 'after': [], 'markers': {}}
