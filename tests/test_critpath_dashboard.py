"""Critical Path Analyzer — execution dashboard, health, and narrative."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_critpath.analysis import build_report
from p6_critpath.dashboard import build_dashboard, build_narrative


def _sched(data_date, chain, ms_finish, ms_bl, ms_tf, extra_tf):
    d = ScheduleData()
    d.project = {'name': 'T', 'data_date': data_date}
    d.wbs = {}; d.activities = {}; d.relationships = []; d.baseline_by_id = {}
    prev = None
    for i, (w, tf) in enumerate(chain):
        wid = f'W_{w}'; d.wbs[wid] = {'name': w, 'parent_object_id': None}; oid = f'A{i}'
        fin = datetime(2026, 8, 1 + i)
        d.activities[oid] = {'id': f'ACT{i}', 'name': w, 'task_type': 'Task', 'calendar_id': None,
                             'wbs_id': wid, 'percent_complete': 0.0, 'total_float_days': tf,
                             'remaining_early_start': fin, 'remaining_early_finish': fin,
                             'planned_finish': fin, 'object_id': oid}
        d.baseline_by_id[f'ACT{i}'] = {'planned_start': fin, 'planned_finish': fin}
        if prev is not None:
            d.activities[prev]['remaining_early_finish'] = fin
            d.relationships.append({'pred_id': prev, 'succ_id': oid, 'type': 'FS', 'lag_days': 0.0})
        prev = oid
    d.activities['MS'] = {'id': 'M999', 'name': 'Project Completion', 'task_type': 'FinishMilestone',
                          'calendar_id': None, 'wbs_id': None, 'total_float_days': ms_tf,
                          'remaining_early_finish': ms_finish, 'planned_finish': ms_finish}
    d.activities[prev]['remaining_early_finish'] = ms_finish
    d.relationships.append({'pred_id': prev, 'succ_id': 'MS', 'type': 'FS', 'lag_days': 0.0})
    d.baseline_by_id['M999'] = {'planned_start': data_date, 'planned_finish': ms_bl}
    for i, tf in enumerate(extra_tf):
        d.activities[f'X{i}'] = {'id': f'X{i}', 'name': f'x{i}', 'task_type': 'Task', 'calendar_id': None,
                                 'total_float_days': tf, 'object_id': f'X{i}'}
    return d


def _report():
    prev = _sched(datetime(2026, 6, 30), [('Foundations', 0.0), ('Structure', 0.0), ('Roof', 0.0)],
                  datetime(2027, 1, 5), datetime(2026, 12, 10), -5.0, [5.0, 20.0])
    curr = _sched(datetime(2026, 7, 19), [('Foundations', 0.0), ('MEP', 0.0), ('Commissioning', 0.0)],
                  datetime(2027, 1, 23), datetime(2026, 12, 10), -20.0, [-1.0, 6.0])
    return build_report({'previous': prev, 'current': curr}, 'two_updates')


def test_dashboard_shape_and_health():
    d = build_dashboard(_report())
    assert d['status'] in ('good', 'warn', 'bad')
    assert d['status'] == 'bad'                  # cpli well under 0.95
    assert len(d['kpis']) == 4
    assert d['charts']['crit_near']['roles'] == ['previous', 'current']
    assert len(d['charts']['cpli_trend']['values']) == 2
    assert isinstance(d['verdict'], str) and d['verdict']


def test_dashboard_flags_reroute():
    d = build_dashboard(_report())
    # MEP / Commissioning entered the path → reroute detected and surfaced
    assert d['reroute']
    assert any('MEP' in t or 'Commissioning' in t for t in d['reroute'])


def test_narrative_effect_and_recommendation():
    n = build_narrative(_report())
    assert 'behind' in n['effect'] or 'ahead' in n['effect']
    assert isinstance(n['recommendation'], list) and n['recommendation']
    assert isinstance(n['conclusion'], str) and n['conclusion']
