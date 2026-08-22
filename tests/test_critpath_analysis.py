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


def test_census_floatless_schedule_counts_critical_from_path():
    # A baseline export with NO per-activity float: critical must still be counted (from the
    # critical/longest path), near-critical reported as unknown.
    d = _chain_schedule(datetime(2026, 1, 1), [('Foundations', None), ('Structure', None)],
                        datetime(2026, 12, 10), datetime(2026, 12, 10))
    for a in d.activities.values():
        if a.get('task_type') == 'Task':
            a['total_float_days'] = None            # strip float → float-less schedule
    c = schedule_census(d)
    assert c['critical_source'] == 'path'
    assert c['total_activities'] == 2               # both task activities counted
    assert c['critical'] >= 1                        # the path activities are critical
    assert c['near'] is None                         # can't judge near without float


def test_census_floatless_counts_only_governing_path():
    # Float-less schedule with TWO independent finish milestones: a governing one (latest
    # finish, 3-activity chain) and an earlier Zone milestone (2-activity chain). The critical
    # count must be the GOVERNING path only (3), NOT the union of both chains (5) — a floated
    # schedule would give the Zone chain positive float, so it is not critical.
    d = ScheduleData()
    d.project = {'name': 'T', 'data_date': datetime(2026, 1, 1)}
    d.wbs = {}; d.activities = {}; d.relationships = []; d.baseline_by_id = {}

    def add_chain(prefix, acts, ms_code, ms_name, ms_finish):
        prev = None
        for i in range(acts):
            oid = f'{prefix}{i}'
            d.activities[oid] = {'id': oid, 'name': oid, 'task_type': 'Task', 'calendar_id': None,
                                 'wbs_id': None, 'total_float_days': None,
                                 'remaining_early_finish': ms_finish, 'planned_finish': ms_finish, 'object_id': oid}
            if prev is not None:
                d.relationships.append({'pred_id': prev, 'succ_id': oid, 'type': 'FS', 'lag_days': 0.0})
            prev = oid
        d.activities[ms_code] = {'id': ms_code, 'name': ms_name, 'task_type': 'FinishMilestone',
                                 'calendar_id': None, 'total_float_days': None,
                                 'remaining_early_finish': ms_finish, 'planned_finish': ms_finish}
        d.relationships.append({'pred_id': prev, 'succ_id': ms_code, 'type': 'FS', 'lag_days': 0.0})

    add_chain('G', 3, 'MSG', 'Project Completion', datetime(2027, 6, 1))   # governing (latest)
    add_chain('Z', 2, 'MSZ', 'Zone A Completion', datetime(2026, 9, 1))    # earlier, independent
    c = schedule_census(d)
    assert c['critical_source'] == 'path'
    assert c['total_activities'] == 5                     # all 5 task activities counted
    assert c['critical'] == 3                             # ONLY the governing chain, not 5


def test_census_near_threshold_is_strict_under_10():
    # tf exactly 10 is NOT near-critical (strictly < 10)
    d = _schedule(datetime(2026, 7, 19), datetime(2027, 1, 23), datetime(2026, 12, 10),
                  gov_tf=0.0, acts_tf=[10.0, 9.99])
    c = schedule_census(d)
    assert c['near'] == 1                  # only 9.99


# ── build_report: lanes + milestone list ─────────────────────────────────────

def _chain_schedule(data_date, chain, ms_finish, ms_bl):
    """A schedule whose activities form a driving chain to the finish milestone (so the
    Critical Path Analyzer view has a path). chain = [(wbs_name, tf)]."""
    d = ScheduleData()
    d.project = {'name': 'T', 'data_date': data_date}
    d.wbs = {}; d.activities = {}; d.relationships = []; d.baseline_by_id = {}
    prev = None
    for i, (w, tf) in enumerate(chain):
        wid = f'W_{w}'; d.wbs[wid] = {'name': w, 'parent_object_id': None}; oid = f'A{i}'
        fin = datetime(2026, 8, 1 + i)
        d.activities[oid] = {'id': f'ACT{i}', 'name': w, 'task_type': 'Task', 'calendar_id': None,
                             'wbs_id': wid, 'percent_complete': 0.0, 'total_float_days': tf,
                             'remaining_early_finish': fin, 'planned_finish': fin, 'object_id': oid}
        d.baseline_by_id[f'ACT{i}'] = {'planned_start': fin, 'planned_finish': fin}
        if prev is not None:
            d.activities[prev]['remaining_early_finish'] = fin
            d.relationships.append({'pred_id': prev, 'succ_id': oid, 'type': 'FS', 'lag_days': 0.0})
        prev = oid
    d.activities['MS'] = {'id': 'M999', 'name': 'Completion', 'task_type': 'FinishMilestone',
                          'calendar_id': None, 'wbs_id': None, 'total_float_days': -5.0,
                          'remaining_early_finish': ms_finish, 'planned_finish': ms_finish}
    d.activities[prev]['remaining_early_finish'] = ms_finish
    d.relationships.append({'pred_id': prev, 'succ_id': 'MS', 'type': 'FS', 'lag_days': 0.0})
    d.baseline_by_id['M999'] = {'planned_start': data_date, 'planned_finish': ms_bl}
    return d


def test_build_report_has_milestone_paths_and_census_per_role():
    from p6_critpath.analysis import build_report
    a = _chain_schedule(datetime(2026, 6, 30), [('Foundations', 0.0), ('Roof', 0.0)],
                        datetime(2027, 1, 5), datetime(2026, 12, 10))
    b = _chain_schedule(datetime(2026, 7, 19), [('Foundations', 0.0), ('MEP', 0.0)],
                        datetime(2027, 1, 23), datetime(2026, 12, 10))
    rep = build_report({'previous': a, 'current': b}, 'two_updates')
    assert set(rep['roles']) == {'previous', 'current'}
    assert 'previous' in rep['census'] and 'current' in rep['census']
    # one path block per finish milestone; the governing one carries lanes with box states
    assert rep['milestone_paths'], 'should have at least the governing milestone path'
    gov = next(m for m in rep['milestone_paths'] if m['is_governing'])
    cur = next(ln for ln in gov['lanes'] if ln['role'] == 'current')
    assert all('state' in bx for bx in cur['boxes'])
    # the governing lanes are also surfaced at report['lanes'] for the dashboard
    assert {ln['role'] for ln in rep['lanes']} == {'previous', 'current'}
