from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.checks.float_snapshot import check_float

CONFIG = {'audit': {'default_severity': 'Medium', 'category_severity': {}, 'float_threshold_days': 44}}


def _g(acts):
    d = ScheduleData(); d.activities = acts; d.relationships = []
    return ScheduleGraph(d)


def _act(oid, tf, wbs='WBS-X', **kw):
    b = {'object_id': oid, 'id': oid, 'name': oid, 'task_type': 'Task',
         'is_critical': False, 'wbs_path': wbs, 'category': None,
         'total_float_days': tf, 'free_float_days': tf}
    b.update(kw); return b


def test_negative_float_flagged_high():
    g = _g({'a': _act('a', -3.0)})
    findings = check_float(g, CONFIG)
    neg = [f for f in findings if 'negative' in f.summary.lower()]
    assert len(neg) == 1
    assert neg[0].severity == 'High'


def test_excessive_float_single_summary_with_percentage():
    acts = {f'x{i}': _act(f'x{i}', 60.0) for i in range(3)}
    acts['ok'] = _act('ok', 10.0)
    g = _g(acts)
    summary = [f for f in check_float(g, CONFIG) if 'excessive' in f.summary.lower()]
    assert len(summary) == 1
    assert '3' in summary[0].basis and '4' in summary[0].basis  # 3 of 4


def test_none_float_ignored():
    g = _g({'a': _act('a', None)})
    assert check_float(g, CONFIG) == []
