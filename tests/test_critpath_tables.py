"""Critical Path Analyzer — every-milestone table and float migration."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_critpath.tables import milestones_table, float_migration


def _mk(data_date, acts, milestones):
    """acts: (code, tf). milestones: (code, name, forecast, baseline_finish, tf)."""
    d = ScheduleData()
    d.project = {'name': 'T', 'data_date': data_date}
    d.activities = {}
    d.baseline_by_id = {}
    for code, tf in acts:
        d.activities[code] = {'id': code, 'name': code, 'task_type': 'Task', 'calendar_id': None,
                              'total_float_days': tf, 'object_id': code}
    for code, name, fc, bf, tf in milestones:
        d.activities[code] = {'id': code, 'name': name, 'task_type': 'FinishMilestone', 'calendar_id': None,
                              'total_float_days': tf, 'remaining_early_finish': fc, 'planned_finish': fc,
                              'object_id': code}
        d.baseline_by_id[code] = {'planned_start': data_date, 'planned_finish': bf}
    return d


# ── float_migration ──────────────────────────────────────────────────────────

def test_float_migration_band_transitions():
    base = _mk(datetime(2026, 6, 30), [('A', 5.0), ('B', 20.0), ('C', -1.0), ('D', -2.0)], [])
    curr = _mk(datetime(2026, 7, 19), [('A', -1.0), ('B', 6.0), ('C', 8.0), ('D', -2.0)], [])
    m = float_migration(base, curr)
    assert m['counts']['near_to_crit'] == 1      # A: 5 (near) → -1 (crit)
    assert m['counts']['safe_to_near'] == 1      # B: 20 (safe) → 6 (near)
    assert m['counts']['crit_to_recovered'] == 1  # C: -1 (crit) → 8 (near, off critical)
    assert m['counts']['held_crit'] == 1         # D: crit → crit


# ── milestones_table ─────────────────────────────────────────────────────────

def test_milestones_table_rows_and_variance():
    prev = _mk(datetime(2026, 6, 30), [('A', 0.0)],
               [('M1', 'Completion', datetime(2027, 1, 5), datetime(2026, 12, 10), -5.0),
                ('M2', 'Zone A', datetime(2026, 11, 2), datetime(2026, 11, 5), 2.0)])
    curr = _mk(datetime(2026, 7, 19), [('A', 0.0)],
               [('M1', 'Completion', datetime(2027, 1, 23), datetime(2026, 12, 10), -10.0),
                ('M2', 'Zone A', datetime(2026, 10, 28), datetime(2026, 11, 5), 4.0)])
    rows = milestones_table({'previous': prev, 'current': curr})
    m1 = next(r for r in rows if r['id'] == 'M1')
    assert m1['finishes']['current'] == '23-Jan-2027'
    assert m1['finishes']['previous'] == '05-Jan-2027'
    assert m1['var_vs_baseline_d'] is not None and m1['var_vs_baseline_d'] > 0   # behind baseline
    assert m1['var_this_period_d'] is not None and m1['var_this_period_d'] > 0   # slipped this period
    assert m1['cpli'] is not None
    # Zone A pulled EARLIER this period → negative period variance (gain)
    m2 = next(r for r in rows if r['id'] == 'M2')
    assert m2['var_this_period_d'] < 0
