"""Critical Path Analyzer engine — census counts, CPLI, and the report shape."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_critpath.analysis import cpli, schedule_census


# ── CPLI pure function ───────────────────────────────────────────────────────

def test_cpli_formula():
    # (remaining length + total float) / remaining length
    assert cpli(120, -15) == 0.88          # (120-15)/120 = 0.875 → 0.88
    assert cpli(100, 0) == 1.0             # on the required finish
    assert cpli(120, 12) == 1.10           # ahead of the finish


def test_cpli_guards():
    assert cpli(0, -5) is None             # no length → undefined
    assert cpli(None, -5) is None
    assert cpli(120, None) is None         # no float reference → undefined


# ── schedule_census ──────────────────────────────────────────────────────────

def _schedule(data_date, gov_forecast, gov_baseline, gov_tf, acts_tf):
    """A tiny schedule: one governing finish milestone + N task activities carrying
    the given total floats. calendar_id None → working-day helper falls back to
    calendar days, so the numbers are deterministic in the test."""
    d = ScheduleData()
    d.project = {'name': 'Test', 'data_date': data_date}
    d.activities = {
        'MS': {'id': 'M999', 'name': 'Project Completion', 'task_type': 'FinishMilestone',
               'calendar_id': None, 'total_float_days': gov_tf,
               'remaining_early_finish': gov_forecast, 'planned_finish': gov_forecast},
    }
    for i, tf in enumerate(acts_tf):
        oid = f'A{i}'
        d.activities[oid] = {'id': f'ACT{i}', 'name': f'Act {i}', 'task_type': 'Task',
                             'calendar_id': None, 'total_float_days': tf,
                             'remaining_early_finish': gov_forecast}
    d.baseline_by_id = {'M999': {'planned_start': data_date, 'planned_finish': gov_baseline}}
    return d


def test_census_counts_and_percentages():
    # 4 task activities: floats 15 (safe), 5 (near), 0 (critical), -3 (critical)
    d = _schedule(datetime(2026, 7, 19), datetime(2027, 1, 23), datetime(2026, 12, 10),
                  gov_tf=-10.0, acts_tf=[15.0, 5.0, 0.0, -3.0])
    c = schedule_census(d)
    assert c['total_activities'] == 4
    assert c['critical'] == 2              # tf 0 and -3
    assert c['near'] == 1                  # tf 5 (0 < tf < 10)
    assert c['critical_pct'] == 50.0
    assert c['near_pct'] == 25.0


def test_census_cpli_ties_to_formula():
    d = _schedule(datetime(2026, 7, 19), datetime(2027, 1, 23), datetime(2026, 12, 10),
                  gov_tf=-10.0, acts_tf=[15.0, 5.0, 0.0, -3.0])
    c = schedule_census(d)
    assert c['path_length_wd'] is not None and c['path_length_wd'] > 0
    assert c['total_float_wd'] == -10.0
    assert c['cpli'] == cpli(c['path_length_wd'], c['total_float_wd'])
    assert c['gov_name'] == 'Project Completion'


def test_census_near_threshold_is_strict_under_10():
    # tf exactly 10 is NOT near-critical (strictly < 10)
    d = _schedule(datetime(2026, 7, 19), datetime(2027, 1, 23), datetime(2026, 12, 10),
                  gov_tf=0.0, acts_tf=[10.0, 9.99])
    c = schedule_census(d)
    assert c['near'] == 1                  # only 9.99


# ── build_report: lanes + milestone list ─────────────────────────────────────

def test_build_report_has_lanes_and_census_per_role():
    from p6_critpath.analysis import build_report
    a = _schedule(datetime(2026, 6, 30), datetime(2027, 1, 5), datetime(2026, 12, 10),
                  gov_tf=-5.0, acts_tf=[5.0, 0.0])
    b = _schedule(datetime(2026, 7, 19), datetime(2027, 1, 23), datetime(2026, 12, 10),
                  gov_tf=-10.0, acts_tf=[0.0, -3.0])
    rep = build_report({'previous': a, 'current': b}, 'two_updates')
    assert set(rep['roles']) == {'previous', 'current'}
    assert 'previous' in rep['census'] and 'current' in rep['census']
    # a lane per role, and the current lane carries box 'state' flags
    lane_roles = {ln['role'] for ln in rep['lanes']}
    assert lane_roles == {'previous', 'current'}
    cur = next(ln for ln in rep['lanes'] if ln['role'] == 'current')
    assert all('state' in bx for bx in cur['boxes'])
