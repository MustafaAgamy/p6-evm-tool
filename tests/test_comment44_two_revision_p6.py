"""Comment 44 — the two-schedule features agree with Primavera P6 on the update files.

Found by reconciling every two-revision feature against P6's own exports (tests/
p6_reconcile_pairs.py on Alstom, Saint Gobain and Grain Bulk baseline → update pairs, XER and
XML) and fixed here:

* two activities may be linked TWICE in P6 (an SS and an FF): the pair kept only its last link,
  so a changed FF lag was hidden in the Consultant Review rows, counted as a 'type change' in
  Baseline Revision, and the revert plan / corrected XML / but-for finish set BOTH links to one
  type and lag;
* an XML from P6 19.x states no assignment price, so an XER baseline against an XML update
  reported hundreds of 'rate changes' P6 does not show;
* the Critical Path Analyzer measured an XER update (no baseline inside) against its own
  Planned dates although a baseline schedule was picked;
* the finish slip counted whole 24-hour spans, one day short of the dates shown.
"""
import textwrap
from datetime import datetime

from p6_evm.parser import ScheduleData, parse_file
from p6_compare.model import MatchedSchedules, link_changes, pair_links
from p6_compare.diff import diff_relationships
from p6_compare.revert import revert_operations, write_corrected_xml, relink


def _act(code, name=''):
    return {'id': code, 'name': name or code, 'task_type': 'Task', 'calendar_id': None,
            'planned_duration': 8.0, 'remaining_duration': 8.0}


def _rel(p, s, t, lag_h):
    return {'pred_id': p, 'succ_id': s, 'type': t, 'lag_hours': lag_h, 'lag_days': lag_h / 8.0}


def _sched(rels):
    d = ScheduleData()
    d.activities = {'p': _act('A1'), 's': _act('A2')}
    d.relationships = rels
    return d


BASE = [_rel('p', 's', 'SS', 96.0), _rel('p', 's', 'FF', 96.0)]
UPD = [_rel('p', 's', 'SS', 16.0), _rel('p', 's', 'FF', 40.0)]


# ── an SS + FF pair is two links ──────────────────────────────────────────────

def test_pair_keeps_every_link_by_type():
    m = MatchedSchedules(_sched(BASE), _sched(UPD))
    assert pair_links(m.baseline_rels[('A1', 'A2')]) == {'SS': (96.0, 12.0), 'FF': (96.0, 12.0)}


def test_two_lag_changes_are_two_lag_changes_not_a_type_change():
    m = MatchedSchedules(_sched(BASE), _sched(UPD))
    c = link_changes(m.baseline_rels[('A1', 'A2')], m.update_rels[('A1', 'A2')])
    assert (c['type'], c['lag'], c['added'], c['removed']) == (0, 2, 0, 0)
    from p6_revcompare.compare import _logic_stats
    assert _logic_stats(m) == {'total': 2, 'added': 0, 'removed': 0, 'type': 0, 'lag': 2}


def test_type_change_on_one_link_of_a_pair():
    m = MatchedSchedules(_sched([_rel('p', 's', 'SS', 0.0), _rel('p', 's', 'FF', 0.0)]),
                         _sched([_rel('p', 's', 'SS', 0.0), _rel('p', 's', 'FS', 0.0)]))
    c = link_changes(m.baseline_rels[('A1', 'A2')], m.update_rels[('A1', 'A2')])
    assert (c['type'], c['lag'], c['added'], c['removed']) == (1, 0, 0, 0)
    assert c['type_map'] == {'SS': 'SS', 'FS': 'FF'}


def test_consultant_rows_list_both_links_and_flag_the_ff_change():
    m = MatchedSchedules(_sched(BASE), _sched(UPD))
    row = next(r for r in diff_relationships(m)['rows'] if r['activity_id'] == 'A2')
    assert [(p['type'], p['lag_days'], p['status']) for p in row['baseline_preds']] == \
        [('FF', 12.0, 'same'), ('SS', 12.0, 'same')]
    assert [(p['type'], p['lag_days'], p['status'], p.get('change_kind')) for p in row['update_preds']] == \
        [('FF', 5.0, 'changed', 'lag'), ('SS', 2.0, 'changed', 'lag')]


def test_revert_plan_restores_each_link_to_its_own_baseline():
    m = MatchedSchedules(_sched(BASE), _sched(UPD))
    op = next(o for o in revert_operations(m, {'rows': []}, {'rows': []}) if o['kind'] == 'set_rel')
    assert op['links'] == [['FF', 96.0], ['SS', 96.0]]
    assert relink(op, ['SS', 'FF']) == ({'SS': ('SS', 96.0), 'FF': ('FF', 96.0)}, [])
    # the update turned the FF into an FS: the FS goes back to FF, nothing is lost
    assert relink(op, ['SS', 'FS']) == ({'SS': ('SS', 96.0), 'FS': ('FF', 96.0)}, [])
    # the update dropped the FF: it is restored
    assert relink(op, ['SS']) == ({'SS': ('SS', 96.0)}, [('FF', 96.0)])


def test_but_for_scheduler_keeps_the_ff_an_ff():
    from p6_compare import schedule
    upd = _sched(UPD)
    m = MatchedSchedules(_sched(BASE), upd)
    ops = revert_operations(m, {'rows': []}, {'rows': []})
    seen = {}
    orig = schedule.project_finish

    def spy(data, **kw):
        seen['rels'] = sorted((r['type'], r['lag_hours']) for r in data.relationships)
        return None
    schedule.project_finish = spy
    try:
        schedule.but_for_finish(upd, ops)
    finally:
        schedule.project_finish = orig
    assert seen['rels'] == [('FF', 96.0), ('SS', 96.0)]


def _xml(tmp_path, rels):
    body = ''.join(textwrap.dedent(f'''\
        <Relationship><ObjectId>{5000 + i}</ObjectId>
          <PredecessorActivityObjectId>1001</PredecessorActivityObjectId>
          <SuccessorActivityObjectId>1002</SuccessorActivityObjectId>
          <Type>{t}</Type><Lag>{lag}</Lag></Relationship>''') for i, (t, lag) in enumerate(rels))
    p = tmp_path / 'upd.xml'
    p.write_text(textwrap.dedent('''\
        <?xml version="1.0"?>
        <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
          <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name>
            <Activity><ObjectId>1001</ObjectId><Id>A1</Id><Name>a</Name><Type>Task Dependent</Type></Activity>
            <Activity><ObjectId>1002</ObjectId><Id>A2</Id><Name>b</Name><Type>Task Dependent</Type></Activity>
        ''') + body + '</Project></APIBusinessObjects>', encoding='utf-8')
    return str(p)


def test_corrected_xml_reverts_each_link_by_type(tmp_path):
    src = _xml(tmp_path, [('Start to Start', 16), ('Finish to Finish', 40)])
    op = {'kind': 'set_rel', 'pred_code': 'A1', 'succ_code': 'A2', 'type': 'FF', 'lag_hours': 96.0,
          'links': [['FF', 96.0], ['SS', 96.0]]}
    out = str(tmp_path / 'c.xml')
    assert write_corrected_xml(src, [op], out)['applied'] == 1
    assert sorted((r['type'], r['lag_hours']) for r in parse_file(out).relationships) == \
        [('FF', 96.0), ('SS', 96.0)]


def test_corrected_xml_restores_a_dropped_link_of_the_pair(tmp_path):
    src = _xml(tmp_path, [('Start to Start', 16)])
    op = {'kind': 'set_rel', 'pred_code': 'A1', 'succ_code': 'A2', 'type': 'FF', 'lag_hours': 96.0,
          'links': [['FF', 96.0], ['SS', 96.0]]}
    out = str(tmp_path / 'c.xml')
    write_corrected_xml(src, [op], out)
    assert sorted((r['type'], r['lag_hours']) for r in parse_file(out).relationships) == \
        [('FF', 96.0), ('SS', 96.0)]


def test_single_link_ops_still_work(tmp_path):
    src = _xml(tmp_path, [('Finish to Start', 80)])
    op = {'kind': 'set_rel', 'pred_code': 'A1', 'succ_code': 'A2', 'type': 'SS', 'lag_hours': 0.0}
    out = str(tmp_path / 'c.xml')
    write_corrected_xml(src, [op], out)
    assert [(r['type'], r['lag_hours']) for r in parse_file(out).relationships] == [('SS', 0.0)]


# ── Baseline Revision resources: a derived price is compared by cost per unit ──

def _rsched(rate, derived, cost=100.0, units=100.0):
    d = ScheduleData()
    d.activities = {'o1': {'id': 'A1', 'name': 'x', 'task_type': 'Task', 'total_float_days': 0, 'wbs_path': 'W'}}
    d.relationships = []
    d.bac_by_activity = {'o1': cost}
    d.assignments_by_activity = {'o1': [{'resource_id': 'r', 'resource_code': 'R1', 'resource_name': 'Res',
                                         'budget_units': units, 'budget_cost': cost, 'rate': rate,
                                         'resource_type': 'Nonlabor', 'rate_derived': derived}]}
    d.resources = {}
    return d


def test_xer_rate_against_derived_xml_rate_is_no_change():
    from p6_revcompare.resources import diff_resources
    r0, r1 = _rsched(0.6897, False), _rsched(1.0, True)
    assert diff_resources(r0, r1, MatchedSchedules(r0, r1))['assignment_changes'] == []


def test_derived_rate_still_reports_a_real_price_change():
    from p6_revcompare.resources import diff_resources
    r0, r1 = _rsched(1.0, False), _rsched(1.5, True, cost=150.0)
    kinds = [c['kind'] for c in diff_resources(r0, r1, MatchedSchedules(r0, r1))['assignment_changes']]
    assert kinds == ['rate']


def test_stated_rates_are_compared_as_before():
    from p6_revcompare.resources import diff_resources
    r0, r1 = _rsched(1.0, False), _rsched(2.0, False)
    kinds = [c['kind'] for c in diff_resources(r0, r1, MatchedSchedules(r0, r1))['assignment_changes']]
    assert kinds == ['rate']


# ── Critical Path Analyzer: the picked baseline measures a baseline-less update ──

def _cp_sched(source, bl_finish):
    d = ScheduleData()
    d.activities = {'m': {'id': 'M1', 'name': 'Finish', 'task_type': 'FinishMilestone',
                          'planned_start': datetime(2026, 9, 1), 'planned_finish': datetime(2026, 9, 1)}}
    d.relationships = []
    d.baseline_by_id = {'M1': {'planned_start': bl_finish, 'planned_finish': bl_finish}}
    d.baseline_source = source
    return d


def test_picked_baseline_replaces_an_update_s_own_planned_dates(tmp_path):
    from p6_evm.baseline import use_picked_baseline
    bl_file = tmp_path / 'bl.xer'
    bl_file.write_text('x')
    cur = _cp_sched('self', datetime(2026, 9, 1))
    bl = _cp_sched('self', None)
    bl.activities['m']['planned_finish'] = datetime(2026, 8, 24)
    use_picked_baseline({'current': cur, 'baseline': bl}, str(bl_file))
    assert cur.baseline_source == 'attached'
    assert cur.baseline_by_id['M1']['planned_finish'] == datetime(2026, 8, 24)


def test_picked_baseline_never_replaces_an_embedded_one(tmp_path):
    from p6_evm.baseline import use_picked_baseline
    bl_file = tmp_path / 'bl.xer'
    bl_file.write_text('x')
    cur = _cp_sched('embedded', datetime(2026, 8, 20))
    bl = _cp_sched('self', None)
    bl.activities['m']['planned_finish'] = datetime(2026, 8, 24)
    use_picked_baseline({'current': cur, 'baseline': bl}, str(bl_file))
    assert cur.baseline_by_id['M1']['planned_finish'] == datetime(2026, 8, 20)


# ── Consultant Review: the slip is counted between the finish DATES ──

def test_finish_slip_counts_dates_not_24h_spans():
    from p6_compare.report import build_report_from_data

    def s(fin):
        d = ScheduleData()
        d.activities = {'a': {'id': 'A1', 'name': 'x', 'task_type': 'Task', 'planned_finish': fin}}
        d.relationships = []
        d.project = {'scheduled_finish': fin}
        return d
    r = build_report_from_data(s(datetime(2026, 8, 24, 17, 0)), s(datetime(2026, 9, 7, 8, 0)))
    assert r['dashboard']['finish_slip_days'] == 14
