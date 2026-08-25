from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.high_duration import run_high_duration

CONFIG = {'audit': {}}


class _Cal:
    """Tiny calendar stub — only .day_hours is needed by the module."""
    def __init__(self, day_hours):
        self.day_hours = day_hours


def _g(acts, cals=None):
    d = ScheduleData(); d.activities = acts; d.relationships = []
    d.calendars = cals or {}
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W', 'category': None,
         'calendar_id': 'C1', 'planned_duration': None}
    b.update(kw); return b


def test_80h_on_8h_calendar_is_10_days_not_flagged():
    # 80h / 8 = 10 days, threshold 44 -> NOT flagged
    g = _g({'a': _act('a', planned_duration=80.0)}, {'C1': _Cal(8.0)})
    r = run_high_duration(g, CONFIG)
    assert r['findings'] == []
    assert r['kpis']['over_threshold'] == 0


def test_400h_on_8h_calendar_is_50_days_flagged():
    # 400h / 8 = 50 days, threshold 44 -> flagged
    g = _g({'a': _act('a', planned_duration=400.0)}, {'C1': _Cal(8.0)})
    r = run_high_duration(g, CONFIG)
    ids = [f['activity_id'] for f in r['findings']]
    assert 'a' in ids
    f = r['findings'][0]
    assert f['duration_days'] == 50.0
    assert f['severity'] == 'Medium'
    assert 'Break into shorter' in f['recommendation']


def test_kpis_pct_score_grade_module():
    # 1 flagged of 2 real activities -> 50%
    g = _g({'a': _act('a', planned_duration=80.0),   # 10 days -> not flagged
            'b': _act('b', planned_duration=400.0)},  # 50 days -> flagged
           {'C1': _Cal(8.0)})
    r = run_high_duration(g, CONFIG)
    k = r['kpis']
    assert k['total_activities'] == 2
    assert k['over_threshold'] == 1
    assert k['high_pct'] == 50.0
    assert k['threshold'] == 44
    assert k['max_duration'] == 50.0
    assert r['pct'] == 50.0
    assert r['score'] == 50.0          # linear_score(50) = 100 - 50
    assert r['grade'] == 'Critical'    # score < 90
    assert r['module'] == 'high_duration'
    assert r['name'] == 'High Duration'


def test_critical_activity_bumps_severity():
    g = _g({'a': _act('a', planned_duration=400.0, is_critical=True)}, {'C1': _Cal(8.0)})
    f = run_high_duration(g, CONFIG)['findings'][0]
    assert f['severity'] == 'High'     # Medium bumped to High on the critical path


def test_missing_calendar_defaults_to_8h():
    # No calendar registered -> day_hours falls back to 8.0; 400h = 50 days -> flagged
    g = _g({'a': _act('a', planned_duration=400.0, calendar_id='NOPE')}, {})
    r = run_high_duration(g, CONFIG)
    assert r['findings'][0]['duration_days'] == 50.0


def test_custom_threshold_from_config():
    # 10-day activity is flagged when threshold is 5
    g = _g({'a': _act('a', planned_duration=80.0)}, {'C1': _Cal(8.0)})
    r = run_high_duration(g, {'audit': {'duration_threshold_days': 5}})
    assert r['kpis']['threshold'] == 5
    assert r['findings'][0]['activity_id'] == 'a'


def test_ten_hour_calendar_shortens_duration():
    # 400h / 10 = 40 days, threshold 44 -> NOT flagged
    g = _g({'a': _act('a', planned_duration=400.0)}, {'C1': _Cal(10.0)})
    r = run_high_duration(g, CONFIG)
    assert r['findings'] == []
    assert r['kpis']['max_duration'] == 40.0


def test_milestones_excluded():
    g = _g({'m': _act('m', task_type='StartMilestone', planned_duration=4000.0)},
           {'C1': _Cal(8.0)})
    r = run_high_duration(g, CONFIG)
    assert r['findings'] == []
    assert r['kpis']['total_activities'] == 0
    assert r['kpis']['max_duration'] == 0
