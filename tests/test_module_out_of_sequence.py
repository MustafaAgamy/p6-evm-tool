import textwrap
from datetime import datetime

from p6_evm.parser import ScheduleData, parse_file
from p6_evm.calendars import Calendar
from p6_audit.graph import ScheduleGraph
from p6_audit.engine import audit_modules
from p6_audit.modules.out_of_sequence import run_out_of_sequence

CONFIG = {'audit': {'near_critical_days': 10}}


def _g(acts, rels, cals=None):
    d = ScheduleData()
    d.activities = acts
    d.relationships = rels
    if cals:
        d.calendars = cals
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'total_float_days': 50.0, 'wbs_path': 'P > W',
         'category': None, 'calendar_id': None, 'percent_complete': 0.0,
         'actual_start': None, 'actual_finish': None}
    b.update(kw)
    return b


def dt(s):
    return datetime.fromisoformat(s)


def _by_id(result):
    return {f['activity_id']: f for f in result['findings']}


# ── Detection ──────────────────────────────────────────────────────────────

def test_fs_break_against_incomplete_predecessor_is_flagged():
    g = _g({
        'p': _act('p', actual_start=dt('2026-01-01')),   # started, NOT finished → incomplete
        's': _act('s', actual_start=dt('2026-01-05')),   # started before p finished
    }, [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    r = run_out_of_sequence(g, CONFIG)
    f = _by_id(r)
    assert 's' in f
    assert f['s']['current_pred_rel'] == 'FS'
    assert f['s']['current_pred_activity'].startswith('p ')
    assert f['s']['root_cause'] == 'Activity started before predecessor completion.'
    assert f['s']['suggested_predecessor'].startswith('SS(')
    assert f['s']['suggested_predecessor_kind'] == 'change'
    assert f['s']['suggested_successor'] == 'No Change'
    assert r['kpis']['oos_count'] == 1


def test_completed_predecessor_is_NOT_flagged():
    # The P6-matching fix: a past overlap where BOTH activities are complete is finished
    # work, not out of sequence. Old rule flagged this; the fix must not.
    g = _g({
        'p': _act('p', actual_start=dt('2026-01-01'), actual_finish=dt('2026-01-10'),
                  percent_complete=1.0),                 # predecessor COMPLETE
        's': _act('s', actual_start=dt('2026-01-05')),   # started before p's finish (overlap)
    }, [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    r = run_out_of_sequence(g, CONFIG)
    assert r['findings'] == []
    assert r['kpis']['oos_count'] == 0


def test_milestone_predecessor_is_NOT_flagged():
    # A zero-duration milestone predecessor is not "work" — P6 doesn't count it.
    g = _g({
        'm': _act('m', task_type='StartMilestone'),      # incomplete milestone predecessor
        's': _act('s', actual_start=dt('2026-01-05')),
    }, [{'pred_id': 'm', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    assert run_out_of_sequence(g, CONFIG)['findings'] == []


def test_ss_break_flagged():
    g = _g({
        'p': _act('p', actual_start=dt('2026-01-10')),   # incomplete, starts later
        's': _act('s', actual_start=dt('2026-01-05')),   # started before p started
    }, [{'pred_id': 'p', 'succ_id': 's', 'type': 'SS', 'lag_days': 0}])
    f = _by_id(run_out_of_sequence(g, CONFIG))
    assert 's' in f and f['s']['current_pred_rel'] == 'SS'
    assert f['s']['suggested_predecessor'] == 'Planner to review'


def test_ff_break_flagged():
    g = _g({
        'p': _act('p', actual_start=dt('2026-01-01')),   # incomplete (not finished)
        's': _act('s', actual_start=dt('2026-01-02'), actual_finish=dt('2026-01-06')),
    }, [{'pred_id': 'p', 'succ_id': 's', 'type': 'FF', 'lag_days': 0}])
    assert 's' in _by_id(run_out_of_sequence(g, CONFIG))


def test_no_actuals_not_flagged():
    g = _g({'p': _act('p'), 's': _act('s')},
           [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    assert run_out_of_sequence(g, CONFIG)['findings'] == []


def test_milestone_successor_excluded():
    g = _g({'m': _act('m', task_type='StartMilestone', actual_start=dt('2026-01-05')),
            'p': _act('p', actual_start=dt('2026-01-10'))},
           [{'pred_id': 'p', 'succ_id': 'm', 'type': 'FS', 'lag_days': 0}])
    assert run_out_of_sequence(g, CONFIG)['findings'] == []


# ── Classification & KPIs ──────────────────────────────────────────────────

def test_criticality_and_impact():
    g = _g({
        'p':  _act('p', actual_start=dt('2026-01-01')),
        'sc': _act('sc', actual_start=dt('2026-01-05'), is_critical=True, total_float_days=-2.0),
        'sn': _act('sn', actual_start=dt('2026-01-05'), total_float_days=5.0),
        'sf': _act('sf', actual_start=dt('2026-01-05'), total_float_days=50.0),
    }, [
        {'pred_id': 'p', 'succ_id': 'sc', 'type': 'FS', 'lag_days': 0},
        {'pred_id': 'p', 'succ_id': 'sn', 'type': 'FS', 'lag_days': 0},
        {'pred_id': 'p', 'succ_id': 'sf', 'type': 'FS', 'lag_days': 0},
    ])
    r = run_out_of_sequence(g, CONFIG)
    f = _by_id(r)
    assert f['sc']['criticality'] == 'Critical'
    assert f['sn']['criticality'] == 'Near-Critical'
    assert f['sf']['criticality'] == ''
    assert r['kpis']['critical_oos'] == 1 and r['kpis']['near_critical_oos'] == 1
    assert r['kpis']['critical_path_impact'] == 'Yes'
    assert r['kpis']['completion_date_impact'] == 'Direct Impact'


def test_percentages_are_of_all_activities():
    # 4 real activities; 1 critical OOS → critical % = 1/4 = 25% (of ALL, not of OOS)
    g = _g({
        'p':  _act('p', actual_start=dt('2026-01-01')),
        'sc': _act('sc', actual_start=dt('2026-01-05'), is_critical=True, total_float_days=-1.0),
        'x1': _act('x1'), 'x2': _act('x2'),
    }, [{'pred_id': 'p', 'succ_id': 'sc', 'type': 'FS', 'lag_days': 0}])
    k = run_out_of_sequence(g, CONFIG)['kpis']
    assert k['total_activities'] == 4
    assert k['oos_count'] == 1
    assert k['oos_pct'] == 25.0            # 1/4
    assert k['critical_oos_pct'] == 25.0   # 1/4 of ALL, not 100% of OOS


# ── Distribution by main WBS discipline ────────────────────────────────────

def test_distribution_rolls_up_to_main_discipline():
    g = _g({
        'pc': _act('pc', wbs_path='Site > Construction Works > Foundations', actual_start=dt('2026-01-01')),
        'sc': _act('sc', wbs_path='Site > Construction Works > Foundations', actual_start=dt('2026-01-05')),
        'pd': _act('pd', wbs_path='Site > Detailed Design > Drawings', actual_start=dt('2026-01-01')),
        'sd': _act('sd', wbs_path='Site > Detailed Design > Drawings', actual_start=dt('2026-01-05')),
    }, [
        {'pred_id': 'pc', 'succ_id': 'sc', 'type': 'FS', 'lag_days': 0},
        {'pred_id': 'pd', 'succ_id': 'sd', 'type': 'FS', 'lag_days': 0},
    ])
    dist = {r['wbs']: r for r in run_out_of_sequence(g, CONFIG)['wbs_summary']}
    assert 'Construction' in dist and 'Design' in dist
    assert dist['Construction']['oos'] == 1
    assert dist['Design']['oos'] == 1


def test_conclusion_and_empty():
    g = _g({
        'p': _act('p', wbs_path='Site > Construction Works > X', actual_start=dt('2026-01-01')),
        's': _act('s', wbs_path='Site > Construction Works > X', actual_start=dt('2026-01-05'),
                  is_critical=True, total_float_days=-1.0),
    }, [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    assert 'Critical Path' in run_out_of_sequence(g, CONFIG)['kpis']['executive_conclusion']
    clean = _g({'p': _act('p'), 's': _act('s')},
               [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    assert 'No out-of-sequence' in run_out_of_sequence(clean, CONFIG)['kpis']['executive_conclusion']


# ── Advisory suggestions ───────────────────────────────────────────────────

def test_remove_relationship_when_successor_finished_before_pred_started():
    g = _g({
        'p': _act('p', actual_start=dt('2026-02-01')),
        's': _act('s', actual_start=dt('2026-01-01'), actual_finish=dt('2026-01-10')),
    }, [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    f = _by_id(run_out_of_sequence(g, CONFIG))
    assert f['s']['suggested_predecessor'] == 'Remove Relationship'
    assert f['s']['suggested_predecessor_kind'] == 'remove'


def test_inconsistent_dates_when_pred_not_started():
    g = _g({
        'p': _act('p'),                                  # no actuals → incomplete
        's': _act('s', actual_start=dt('2026-01-05')),
    }, [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    f = _by_id(run_out_of_sequence(g, CONFIG))
    assert f['s']['root_cause'] == 'Inconsistent Actual Dates.'
    assert f['s']['planning_review_comment'] == 'Validate Actual Dates.'
    assert f['s']['suggested_predecessor'] == 'Planner to review'


def test_suggested_lag_counts_working_days_not_calendar_days():
    cal = Calendar(object_id='c1', name='5-day week', nonworking_days={'Saturday', 'Sunday'})
    g = _g({
        'p': _act('p', calendar_id='c1', actual_start=dt('2026-01-05')),   # Monday
        's': _act('s', calendar_id='c1', actual_start=dt('2026-01-12')),   # next Monday
    }, [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}], cals={'c1': cal})
    f = _by_id(run_out_of_sequence(g, CONFIG))
    assert f['s']['suggested_predecessor'] == 'SS(5) - p · Act p'   # 5 working days, not 7


# ── Enrichment: split IDs / lag + structured resolution (Resolve & Correct) ──

def test_finding_carries_split_pred_succ_ids_and_lag():
    g = _g({
        'p': _act('p', actual_start=dt('2026-01-01')),
        's': _act('s', actual_start=dt('2026-01-05')),
        't': _act('t', actual_start=dt('2026-02-01')),   # a successor of s, for context
    }, [
        {'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 2},
        {'pred_id': 's', 'succ_id': 't', 'type': 'SS', 'lag_days': 1},
    ])
    f = _by_id(run_out_of_sequence(g, CONFIG))['s']
    assert f['pred_id'] == 'p' and f['pred_name'] == 'Act p'
    assert f['current_pred_lag'] == 2
    assert f['succ_id'] == 't' and f['succ_name'] == 'Act t'
    assert f['current_succ_lag'] == 1


def test_resolution_change_to_ss_for_fs_overlap():
    # Successor started AFTER predecessor started but before it finished → model as SS(lag).
    g = _g({
        'p': _act('p', actual_start=dt('2026-01-01')),
        's': _act('s', actual_start=dt('2026-01-05')),
    }, [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    r = _by_id(run_out_of_sequence(g, CONFIG))['s']['resolution']
    assert r['action'] == 'change' and r['applicable'] is True
    assert r['new_type'] == 'SS' and r['new_lag_days'] >= 0
    assert r['new_pred_id'] == 'p'
    assert 'SS' in r['action_text'] and 'p' in r['action_text']
    assert r['sug_pred_rel'] == 'SS'


def test_resolution_remove_when_successor_finished_before_pred_started():
    g = _g({
        'p': _act('p', actual_start=dt('2026-02-01')),
        's': _act('s', actual_start=dt('2026-01-01'), actual_finish=dt('2026-01-10')),
    }, [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    r = _by_id(run_out_of_sequence(g, CONFIG))['s']['resolution']
    assert r['action'] == 'remove' and r['applicable'] is True
    assert r['action_text'].lower().startswith('remove')


def test_resolution_data_when_pred_not_started_stays_open():
    # No relationship edit can fix a wrong actual date → not applicable, stays Open.
    g = _g({
        'p': _act('p'),
        's': _act('s', actual_start=dt('2026-01-05')),
    }, [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}])
    r = _by_id(run_out_of_sequence(g, CONFIG))['s']['resolution']
    assert r['action'] == 'data' and r['applicable'] is False


# ── End-to-end: real parse path → audit → module ───────────────────────────

def test_end_to_end_xml_actuals_flag_out_of_sequence(tmp_path):
    xml = textwrap.dedent('''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Project>
        <ObjectId>1</ObjectId><Id>PJ</Id><Name>P</Name>
        <DataDate>2026-02-01T00:00:00</DataDate>
        <WBS><ObjectId>10</ObjectId><Name>Construction Works</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity>
          <ObjectId>1001</ObjectId><Id>A100</Id><Name>Fabricate</Name>
          <Type>Task Dependent</Type><Status>In Progress</Status>
          <WBSObjectId>10</WBSObjectId><CalendarObjectId></CalendarObjectId>
          <PercentComplete>50</PercentComplete>
          <ActualStartDate>2026-01-05T08:00:00</ActualStartDate>
        </Activity>
        <Activity>
          <ObjectId>1002</ObjectId><Id>A200</Id><Name>Erect</Name>
          <Type>Task Dependent</Type><Status>In Progress</Status>
          <WBSObjectId>10</WBSObjectId><CalendarObjectId></CalendarObjectId>
          <PercentComplete>20</PercentComplete>
          <ActualStartDate>2026-01-12T08:00:00</ActualStartDate>
        </Activity>
        <Relationship>
          <PredecessorActivityObjectId>1001</PredecessorActivityObjectId>
          <SuccessorActivityObjectId>1002</SuccessorActivityObjectId>
          <Type>Finish to Start</Type><Lag>0</Lag>
        </Relationship>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / 's.xml'
    p.write_text(xml, encoding='utf-8')
    data = parse_file(str(p))
    out = audit_modules(data, {'categories': [], 'audit': {'near_critical_days': 10}})
    oos = out['modules']['out_of_sequence']
    assert oos['kpis']['oos_count'] == 1                # A100 is in-progress (incomplete) → A200 flagged
    f = {x['activity_id']: x for x in oos['findings']}
    assert 'A200' in f
    assert f['A200']['current_pred_rel'] == 'FS'
    assert f['A200']['current_pred_activity'].startswith('A100')
    assert f['A200']['suggested_predecessor'].startswith('SS(')
