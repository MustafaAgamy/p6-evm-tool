from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.float_analysis import run_float

CONFIG = {'audit': {'float_threshold_days': 44}}


def _g(acts):
    d = ScheduleData(); d.activities = acts; d.relationships = []
    return ScheduleGraph(d)


def _act(oid, tf, wbs='Civil > Silo 8', **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': wbs, 'category': None,
         'total_float_days': tf, 'free_float_days': tf}
    b.update(kw); return b


def test_over_threshold_medium_with_impact():
    g = _g({'a': _act('a', 88.0)})               # 88/44 = 2.0x
    f = run_float(g, CONFIG)['findings'][0]
    assert f['severity'] == 'Medium'
    assert f['status'] == 'Excessive Float'
    assert f['impact'] == 2.0
    assert f['total_float_days'] == 88.0
    assert f['threshold'] == 44


def test_severely_excessive_is_high():
    g = _g({'a': _act('a', 200.0)})              # >3x threshold
    f = run_float(g, CONFIG)['findings'][0]
    assert f['severity'] == 'High'
    assert f['impact'] > 3


def test_negative_float_is_critical():
    g = _g({'a': _act('a', -6.0)})
    f = run_float(g, CONFIG)['findings'][0]
    assert f['severity'] == 'Critical'
    assert f['status'] == 'Negative Float'
    assert f['impact'] is None


def test_normal_float_not_flagged():
    g = _g({'a': _act('a', 10.0)})
    assert run_float(g, CONFIG)['findings'] == []


def test_none_float_ignored_and_not_in_total_denominator():
    g = _g({'a': _act('a', None), 'b': _act('b', 60.0)})
    r = run_float(g, CONFIG)
    # only 'b' has assessable float; over threshold count 1
    assert r['kpis']['above_threshold'] == 1


def test_kpis():
    acts = {f'x{i}': _act(f'x{i}', 60.0) for i in range(3)}
    acts['ok'] = _act('ok', 10.0)
    r = run_float(_g(acts), CONFIG)
    k = r['kpis']
    assert k['above_threshold'] == 3
    assert k['max_float'] == 60.0
    assert k['float_pct'] == round(100.0 * 3 / k['total_activities'], 1)


def test_wbs_summary_sorted_worst_first():
    acts = {}
    for i in range(5):
        acts[f'm{i}'] = _act(f'm{i}', 60.0, wbs='MEP > L12')
    for i in range(2):
        acts[f'c{i}'] = _act(f'c{i}', 60.0, wbs='Civil > Ext')
    r = run_float(_g(acts), CONFIG)
    ws = r['wbs_summary']
    assert ws[0]['wbs'] == 'MEP > L12'
    assert ws[0]['high'] == 5
    assert ws[0]['high'] >= ws[1]['high']


def test_score_and_grade():
    acts = {f'x{i}': _act(f'x{i}', 60.0) for i in range(40)}  # 40/40 = 100% over
    r = run_float(_g(acts), CONFIG)
    assert r['grade'] == 'Critical'
    assert r['score'] == 0
    assert r['module'] == 'float'
