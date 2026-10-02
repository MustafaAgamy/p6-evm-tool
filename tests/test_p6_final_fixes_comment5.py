"""Two differences against Primavera P6 found by the final P6 test (comment 5), each fixed:

* Schedule Health left every RESOURCE DEPENDENT activity out of all its checks (only Task
  Dependent counted).  P6 and DCMA count both as tasks — Grain Bulk showed 1,466 where P6
  has 1,467.
* The Lag Report dropped a part-day lag (Saint Gobain: 0.12 h, which P6 shows as 0.01 d)
  because it rounds to 0 whole days — 182 lags where P6 holds 183.
"""
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.lag_lead import run_lag_lead
from p6_audit.modules.high_duration import run_high_duration


def _act(oid, tt='Task', **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': tt, 'is_critical': False,
         'total_float_days': 50.0, 'wbs_path': 'P > A', 'calendar_id': None, 'percent_complete': 0.0,
         'actual_start': None, 'actual_finish': None, 'planned_duration': 8.0 * 50}
    b.update(kw)
    return b


def _g(acts, rels=()):
    d = ScheduleData()
    d.activities = acts
    d.relationships = list(rels)
    return ScheduleGraph(d)


def test_resource_dependent_work_is_checked_like_any_task():
    g = _g({'t': _act('t'), 'r': _act('r', 'ResourceDependent'), 'm': _act('m', 'FinishMilestone'),
            'l': _act('l', 'LOE')})
    assert g.is_real_activity('t') and g.is_real_activity('r')
    assert not g.is_real_activity('m') and not g.is_real_activity('l')
    k = run_high_duration(g, {})['kpis']
    assert k['total_activities'] == 2 and k['over_threshold'] == 2


def test_a_part_day_lag_is_still_a_lag():
    g = _g({'p': _act('p'), 's': _act('s'), 'q': _act('q')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0.12 / 11},
            {'pred_id': 'q', 'succ_id': 's', 'type': 'SS', 'lag_days': 0.0}])
    r = run_lag_lead(g, {'audit': {'near_critical_days': 10, 'long_lag_days': 14}})
    assert r['kpis']['lagged_count'] == 1 and r['kpis']['positive_count'] == 1
    row = r['findings'][0]
    assert row['lag_days'] == 0.01 and row['pred_rel'] == 'FS+0.01'
    assert row['is_lead'] is False and row['is_long'] is False


def test_a_whole_day_lag_reads_as_before():
    g = _g({'p': _act('p'), 's': _act('s')}, [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 7.2}])
    row = run_lag_lead(g, {'audit': {}})['findings'][0]
    assert row['lag_days'] == 7 and row['pred_rel'] == 'FS+7'


def test_the_update_verdict_names_the_spi_change_not_a_zero_spi():
    import inspect
    from p6_period import report, exporters
    assert "SPI change {" in inspect.getsource(report) and "f'SPI {" not in inspect.getsource(report)
    assert "SPI change {_spi_var_disp(spv)}" in inspect.getsource(exporters)
