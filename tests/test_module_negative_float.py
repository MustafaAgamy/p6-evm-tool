from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.negative_float import run_negative_float
from p6_audit.scoring import linear_score, uniform_grade

CONFIG = {'audit': {}}


def _g(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W', 'category': None}
    b.update(kw); return b


def test_negative_float_flagged_critical():
    g = _g({'a': _act('a', total_float_days=-8)}, [])
    r = run_negative_float(g, CONFIG)
    f = {x['activity_id']: x for x in r['findings']}['a']
    assert f['severity'] == 'Critical'
    assert f['total_float_days'] == -8.0
    assert f['activity_name'] == 'Act a'
    assert f['wbs_path'] == 'P > W'
    assert 'total float must be >= 0' in f['recommendation']


def test_positive_float_not_flagged():
    g = _g({'a': _act('a', total_float_days=5)}, [])
    ids = [f['activity_id'] for f in run_negative_float(g, CONFIG)['findings']]
    assert 'a' not in ids


def test_none_float_ignored():
    g = _g({'a': _act('a', total_float_days=None)}, [])
    ids = [f['activity_id'] for f in run_negative_float(g, CONFIG)['findings']]
    assert 'a' not in ids


def test_zero_float_not_flagged():
    g = _g({'a': _act('a', total_float_days=0)}, [])
    ids = [f['activity_id'] for f in run_negative_float(g, CONFIG)['findings']]
    assert 'a' not in ids


def test_milestone_excluded():
    g = _g({'m': _act('m', task_type='StartMilestone', total_float_days=-8)}, [])
    assert run_negative_float(g, CONFIG)['findings'] == []


def test_total_float_rounded():
    g = _g({'a': _act('a', total_float_days=-8.26)}, [])
    f = run_negative_float(g, CONFIG)['findings'][0]
    assert f['total_float_days'] == -8.3


def test_kpis_pct_score_grade_module():
    # 1 negative of 2 real activities -> 50%
    g = _g({'a': _act('a', total_float_days=-8), 'b': _act('b', total_float_days=5)}, [])
    r = run_negative_float(g, CONFIG)
    k = r['kpis']
    assert k['total_activities'] == 2
    assert k['negative_count'] == 1
    assert k['neg_pct'] == 50.0
    assert r['pct'] == 50.0
    assert r['score'] == linear_score(50.0)
    assert r['grade'] == uniform_grade(r['score'])
    assert r['module'] == 'negative_float'
    assert r['name'] == 'Negative Float'


def test_finding_id_stable():
    from p6_audit.findings import content_id
    g = _g({'a': _act('a', total_float_days=-8)}, [])
    f = run_negative_float(g, CONFIG)['findings'][0]
    assert f['finding_id'] == content_id('NEGFLOAT', 'a', 'neg')


def test_empty_schedule_pct_zero():
    g = _g({}, [])
    r = run_negative_float(g, CONFIG)
    assert r['pct'] == 0.0
    assert r['kpis']['total_activities'] == 0
    assert r['findings'] == []
