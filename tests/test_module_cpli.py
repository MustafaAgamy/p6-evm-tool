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


def test_compute_cpli_guards_zero_and_none():
    assert compute_cpli(0, 5) is None
    assert compute_cpli(None, 5) is None


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
