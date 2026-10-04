"""Comments 48-52 — Schedule Health counts activities the way Primavera P6 does.

P6's Activities window and its Critical / float filters count EVERY activity type (tasks,
milestones, Level of Effort, WBS summaries); the tool counted task-dependent activities only, so
Alstom UP-006 showed 483 critical where P6 shows 497 (483 tasks + 8 finish milestones + 6 LOE),
2,450 activities where P6 has 2,502. Ibrahim's rule: counts as P6; every % over the activities
not completed (Not Started + In Progress) — all activities when nothing is completed.
"""
from p6_evm.calendars import p6_is_critical, critical_path_type
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.cpli import run_cpli
from p6_audit.modules.negative_float import run_negative_float
from p6_audit.modules.float_management import float_management

CONFIG = {'audit': {}}


def test_p6_critical_follows_the_files_float_limit():
    proj = {'critical_path_type': 'float', 'critical_float_limit_hours': 0.0}
    assert p6_is_critical(0.0, 8, 'Not Started', proj)
    assert not p6_is_critical(0.5, 8, 'Not Started', proj)          # 4 h of float > 0 h limit
    assert p6_is_critical(0.5, 8, 'Not Started', dict(proj, critical_float_limit_hours=8.0))


def test_p6_critical_longest_path_and_completed():
    proj = {'critical_path_type': 'longest', 'critical_float_limit_hours': 0.0}
    assert p6_is_critical(5.0, 8, 'In Progress', proj, longest_path=True)
    assert not p6_is_critical(-3.0, 8, 'In Progress', proj, longest_path=False)
    assert not p6_is_critical(-3.0, 8, 'Completed', {'critical_path_type': 'float'})   # no live float
    assert critical_path_type('CT_DrivPath') == 'longest' and critical_path_type('Critical Float') == 'float'


def _graph(acts):
    d = ScheduleData()
    d.activities = {a['id']: dict({'name': a['id'], 'wbs_path': 'P > W'}, **a) for a in acts}
    d.relationships = []
    return ScheduleGraph(d)


ACTS = [
    {'id': 'T1', 'task_type': 'Task', 'status': 'Not Started', 'total_float_days': -2.0, 'is_critical': True},
    {'id': 'T2', 'task_type': 'Task', 'status': 'In Progress', 'total_float_days': 5.0, 'is_critical': False},
    {'id': 'T3', 'task_type': 'Task', 'status': 'Completed', 'total_float_days': None, 'is_critical': False},
    {'id': 'M1', 'task_type': 'FinishMilestone', 'status': 'Not Started', 'total_float_days': -2.0, 'is_critical': True},
    {'id': 'L1', 'task_type': 'LOE', 'status': 'Not Started', 'total_float_days': 0.0, 'is_critical': True},
]


def test_every_activity_type_counts_and_pct_is_over_the_remaining():
    g = _graph(ACTS)
    k = run_cpli(g, CONFIG)['kpis']
    assert (k['total_activities'], k['remaining_activities'], k['critical_count']) == (5, 4, 3)
    assert k['critical_pct'] == 75.0                                   # 3 of the 4 not completed
    n = run_negative_float(g, CONFIG)['kpis']
    assert (n['negative_count'], n['remaining_activities'], n['neg_pct']) == (2, 4, 50.0)
    s = float_management(g, CONFIG)['stats']
    assert (s['total_all'], s['total'], s['critical'], s['near_critical']) == (5, 4, 3, 1)


def test_with_nothing_completed_the_base_is_every_activity():
    g = _graph([a for a in ACTS if a['status'] != 'Completed'])
    k = run_cpli(g, CONFIG)['kpis']
    assert k['remaining_activities'] == k['total_activities'] == 4
    assert k['critical_pct'] == 75.0
