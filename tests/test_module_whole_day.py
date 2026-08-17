from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.whole_day import run_whole_day
from p6_audit.scoring import linear_score, uniform_grade

CONFIG = {'audit': {}}


class _Cal:
    """Tiny calendar stub with the attributes the module reads."""
    def __init__(self, name, day_hours):
        self.name = name
        self.day_hours = day_hours


def _g(acts, rels, cals=None):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    if cals is not None:
        d.calendars = cals
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W', 'category': None,
         'planned_duration': None, 'calendar_id': None}
    b.update(kw); return b


def test_decimal_duration_flagged():
    # 80h on an 8.5 h/day calendar = 9.41 days -> decimal, flagged
    g = _g({'a': _act('a', planned_duration=80.0, calendar_id='C1')}, [],
           {'C1': _Cal('5-Day Workweek', 8.5)})
    r = run_whole_day(g, CONFIG)
    f = {x['activity_id']: x for x in r['findings']}['a']
    assert f['original_days'] == 9.41
    assert f['rounds_to'] == 9
    assert f['calendar'] == '5-Day Workweek'
    assert f['severity'] == 'Medium'
    assert f['recommendation'] == 'Round to the nearest whole day (no calendar change)'
    assert f['finding_id']


def test_whole_duration_not_flagged():
    # 80h on an 8 h/day calendar = 10.0 days -> whole, NOT flagged
    g = _g({'a': _act('a', planned_duration=80.0, calendar_id='C1')}, [],
           {'C1': _Cal('8h Day', 8.0)})
    r = run_whole_day(g, CONFIG)
    assert r['findings'] == []
    assert r['kpis']['decimal_count'] == 0


def test_kpis_score_grade_module():
    # one decimal (9.41) + one whole (10.0) of two real activities -> 50%
    g = _g({'a': _act('a', planned_duration=80.0, calendar_id='C1'),
            'b': _act('b', planned_duration=80.0, calendar_id='C2')}, [],
           {'C1': _Cal('8.5h Day', 8.5), 'C2': _Cal('8h Day', 8.0)})
    r = run_whole_day(g, CONFIG)
    k = r['kpis']
    assert k['total_activities'] == 2
    assert k['decimal_count'] == 1
    assert k['decimal_pct'] == 50.0
    assert r['pct'] == 50.0
    assert r['score'] == linear_score(50.0)
    assert r['grade'] == uniform_grade(linear_score(50.0))
    assert r['module'] == 'whole_day'
    assert r['name'] == 'Whole-day Durations'


def test_critical_activity_is_high():
    g = _g({'a': _act('a', planned_duration=80.0, calendar_id='C1', is_critical=True)}, [],
           {'C1': _Cal('8.5h Day', 8.5)})
    f = run_whole_day(g, CONFIG)['findings'][0]
    assert f['severity'] == 'High'


def test_defaults_to_eight_hours_when_no_calendar():
    # 10h with no calendar -> 10/8 = 1.25 days -> decimal, flagged; calendar falls back
    g = _g({'a': _act('a', planned_duration=10.0)}, [])
    f = run_whole_day(g, CONFIG)['findings'][0]
    assert f['original_days'] == 1.25
    assert f['rounds_to'] == 1
    assert f['calendar'] is None


def test_no_planned_duration_not_flagged():
    g = _g({'a': _act('a', planned_duration=None, calendar_id='C1'),
            'z': _act('z', planned_duration=0.0, calendar_id='C1')}, [],
           {'C1': _Cal('8.5h Day', 8.5)})
    r = run_whole_day(g, CONFIG)
    assert r['findings'] == []
    assert r['kpis']['decimal_count'] == 0


def test_milestones_excluded():
    g = _g({'m': _act('m', task_type='StartMilestone', planned_duration=5.0, calendar_id='C1')}, [],
           {'C1': _Cal('8.5h Day', 8.5)})
    r = run_whole_day(g, CONFIG)
    assert r['findings'] == []
    assert r['kpis']['total_activities'] == 0
