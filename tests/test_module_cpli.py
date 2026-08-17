from datetime import datetime, timedelta

from p6_evm.parser import ScheduleData
from p6_evm.calendars import Calendar
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.cpli import run_cpli, compute_cpli, MODULE

CONFIG = {'audit': {}}


def _g(acts, data_date=None, calendars=None):
    d = ScheduleData()
    d.activities = acts
    d.relationships = []
    if calendars:
        d.calendars = calendars
    if data_date is not None:
        d.project = {'data_date': data_date}
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W', 'total_float_days': None,
         'planned_finish': None, 'remaining_early_finish': None, 'calendar_id': None}
    b.update(kw)
    return b


# ── the pure ratio helper ──────────────────────────────────────────────────
def test_compute_cpli_ratio():
    assert compute_cpli(380, -22) == __import__('pytest').approx(0.9421, abs=1e-3)


def test_compute_cpli_guards_zero_none_and_backwards_cpl():
    assert compute_cpli(0, 5) is None
    assert compute_cpli(None, 5) is None
    assert compute_cpli(380, None) is None
    # a finish on/before the data date would invert the ratio into a healthy-looking
    # number (here (-10 + -5) / -10 = 1.5) — refuse it instead
    assert compute_cpli(-10, -5) is None


# ── on-plan schedule: TF = 0, computable CPL → CPLI ≈ 1.0, perfect score ────
def test_finish_milestone_tf_zero_scores_100():
    data_date = datetime(2026, 1, 1)
    cal = Calendar(object_id='C1', name='5-day',
                   nonworking_days={'Saturday', 'Sunday'}, day_hours=8.0)
    acts = {
        'm': _act('m', task_type='FinishMilestone', calendar_id='C1',
                  planned_finish=datetime(2026, 2, 2), total_float_days=0.0),
    }
    g = _g(acts, data_date=data_date, calendars={'C1': cal})
    r = run_cpli(g, CONFIG)

    assert r['kpis']['cpli'] == 1.0
    assert r['kpis']['computable'] is True
    assert r['kpis']['critical_path_length_days'] is not None
    assert r['kpis']['critical_path_length_days'] > 0
    assert r['score'] == 100.0
    assert r['pct'] == 0.0
    assert r['grade'] == 'Excellent'
    assert r['baseline_rule_met'] is True
    assert r['kpis']['finish_milestone_id'] == 'm'
    assert r['kpis']['target'] == 0.95


# ── behind plan: TF = -22 via the calendar-days fallback → score < 95 ───────
def test_negative_float_fails_baseline_rule():
    data_date = datetime(2026, 1, 1)
    finish = data_date + timedelta(days=380)   # no calendar → (finish-dd).days = 380
    acts = {
        'm': _act('m', task_type='FinishMilestone', calendar_id=None,
                  planned_finish=finish, total_float_days=-22.0),
    }
    g = _g(acts, data_date=data_date)   # no calendars → fallback path
    r = run_cpli(g, CONFIG)

    assert r['kpis']['critical_path_length_days'] == 380
    assert r['kpis']['cpli'] == 0.94
    assert r['score'] < 95                              # below the DCMA acceptance score
    assert r['kpis']['cpli'] < r['kpis']['target']     # 0.94 < 0.95 target -> fails DCMA
    assert r['baseline_rule_met'] is False


# ── no finish / float data anywhere → safe defaults, no crash ───────────────
def test_no_data_scores_100_and_cpli_none():
    acts = {'a': _act('a'), 'b': _act('b')}   # no finish dates, no float
    g = _g(acts)
    r = run_cpli(g, CONFIG)

    assert r['kpis']['cpli'] is None
    assert r['kpis']['critical_path_length_days'] is None
    assert r['kpis']['project_total_float_days'] is None
    assert r['kpis']['finish_milestone_id'] is None
    assert r['score'] == 100.0
    assert r['grade'] == 'Excellent'
    assert r['baseline_rule_met'] is False


# ── driving path findings: one row per critical activity, sorted by id ──────
def test_findings_are_the_driving_path():
    acts = {
        'z': _act('z', is_critical=True, total_float_days=0.0,
                  planned_finish=datetime(2026, 3, 1)),
        'a': _act('a', is_critical=True, total_float_days=-1.0,
                  planned_finish=datetime(2026, 2, 1)),
        'n': _act('n', is_critical=False, total_float_days=10.0),
    }
    g = _g(acts, data_date=datetime(2026, 1, 1))
    r = run_cpli(g, CONFIG)

    ids = [f['activity_id'] for f in r['findings']]
    assert ids == ['a', 'z']                     # only critical, sorted by id
    f0 = r['findings'][0]
    assert f0['note'] == 'On the driving/critical path'
    assert f0['activity_name'] == 'Act a'
    assert f0['wbs_path'] == 'P > W'
    assert f0['total_float_days'] == -1.0


# ── module identity + required extra key ───────────────────────────────────
def test_module_id_and_baseline_key_present():
    g = _g({'a': _act('a')})
    r = run_cpli(g, CONFIG)
    assert r['module'] == MODULE == 'cpli'
    assert r['name'] == 'Critical Path / CPLI'
    assert 'baseline_rule_met' in r
    assert set(['module', 'name', 'kpis', 'pct', 'score', 'grade', 'findings']) <= set(r)


# ── defensive cases: the file must never be made to look healthier than it is ──
def test_finish_before_data_date_is_not_computable():
    """A finish on/before the data date gives a backwards CPL — report it as not
    computable rather than letting the inverted ratio read as on-plan."""
    acts = {'m': _act('m', task_type='FinishMilestone',
                      planned_finish=datetime(2026, 1, 1), total_float_days=-5.0)}
    r = run_cpli(_g(acts, data_date=datetime(2026, 6, 1)), CONFIG)

    assert r['kpis']['critical_path_length_days'] < 0
    assert r['kpis']['cpli'] is None
    assert r['kpis']['computable'] is False
    assert r['score'] == 100.0            # no penalty for missing data ...
    assert r['baseline_rule_met'] is False  # ... but the negative float still shows


def test_deep_negative_float_clamps_score_to_zero():
    """CPLI can go negative; the score feeds the weighted roll-up and must not."""
    data_date = datetime(2026, 1, 1)
    acts = {'m': _act('m', task_type='FinishMilestone',
                      planned_finish=data_date + timedelta(days=100),
                      total_float_days=-260.0)}
    r = run_cpli(_g(acts, data_date=data_date), CONFIG)

    assert r['kpis']['cpli'] == -1.6      # (100 - 260) / 100
    assert r['score'] == 0.0              # clamped, never negative
    assert r['pct'] == 100.0
    assert r['grade'] == 'Critical'


def test_summary_spans_are_not_finish_candidates():
    """LOE and WBS Summary run to the project end by construction and carry no
    meaningful float — they must not be mistaken for the completion milestone."""
    acts = {
        'loe':  _act('loe', task_type='LOE', planned_finish=datetime(2027, 1, 1),
                     total_float_days=99.0),
        'sum':  _act('sum', task_type='WBSSummary', planned_finish=datetime(2027, 6, 1),
                     total_float_days=99.0),
        'last': _act('last', planned_finish=datetime(2026, 12, 1), total_float_days=0.0),
    }
    r = run_cpli(_g(acts, data_date=datetime(2026, 1, 1)), CONFIG)

    assert r['kpis']['finish_milestone_id'] == 'last'
    assert r['kpis']['project_total_float_days'] == 0.0


def test_cpl_basis_reports_working_vs_calendar_days():
    """Float is measured in working days; when no calendar is available the CPL
    falls back to calendar days, and the KPI has to say so."""
    data_date, fin = datetime(2026, 1, 1), datetime(2026, 3, 2)
    cal = Calendar(object_id='C1', name='5-day',
                   nonworking_days={'Saturday', 'Sunday'}, day_hours=8.0)
    with_cal = run_cpli(_g({'m': _act('m', task_type='FinishMilestone', calendar_id='C1',
                                      planned_finish=fin, total_float_days=0.0)},
                           data_date=data_date, calendars={'C1': cal}), CONFIG)
    no_cal = run_cpli(_g({'m': _act('m', task_type='FinishMilestone',
                                    planned_finish=fin, total_float_days=0.0)},
                         data_date=data_date), CONFIG)

    assert with_cal['kpis']['cpl_basis'] == 'working'
    assert no_cal['kpis']['cpl_basis'] == 'calendar'
    # weekends stripped -> the working-day span is the shorter of the two
    assert (with_cal['kpis']['critical_path_length_days']
            < no_cal['kpis']['critical_path_length_days'])
