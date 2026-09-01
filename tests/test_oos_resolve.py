"""Out-of-Sequence — Resolve & Correct: apply, re-validate, corrected file export."""
import textwrap

from p6_evm.parser import parse_file
from p6_audit.modules import oos_resolve as R

CONFIG = {'categories': [], 'audit': {'near_critical_days': 10}}

# A100 (in progress, no finish) → A200 started later on an FS link → A200 out of sequence.
XML = textwrap.dedent('''\
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

# Minimal XER carrying the same one out-of-sequence relationship (A100 → A200, FS).
XER = (
    "ERMHDR\t19.12\t2026-02-01\tProject\tuser\tuser\tdb\tProjectMgmt\tPMDB\n"
    "%T\tPROJECT\n"
    "%F\tproj_id\tproj_short_name\tlast_recalc_date\n"
    "%R\t100\tPJ\t2026-02-01 00:00\n"
    "%T\tCALENDAR\n"
    "%F\tclndr_id\tclndr_name\tday_hr_cnt\tclndr_data\n"
    "%R\t1\tStandard\t8\t\n"
    "%T\tPROJWBS\n"
    "%F\twbs_id\tproj_id\tparent_wbs_id\tseq_num\twbs_name\tproj_node_flag\n"
    "%R\t10\t100\t\t1\tConstruction Works\tY\n"
    "%T\tTASK\n"
    "%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_code\ttask_name\ttask_type\tstatus_code\tact_start_date\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt\n"
    "%R\t1001\t100\t10\t1\tA100\tFabricate\tTT_Task\tTK_Active\t2026-01-05 08:00\t2026-01-01 08:00\t2026-01-20 17:00\t400\n"
    "%R\t1002\t100\t10\t1\tA200\tErect\tTT_Task\tTK_Active\t2026-01-12 08:00\t2026-01-21 08:00\t2026-02-10 17:00\t400\n"
    "%T\tTASKPRED\n"
    "%F\ttask_pred_id\ttask_id\tpred_task_id\tproj_id\tpred_proj_id\tpred_type\tlag_hr_cnt\n"
    "%R\t5001\t1002\t1001\t100\t100\tPR_FS\t0\n"
    "%E\n"
)


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    return str(p)


def _finding(data, act_id='A200'):
    from p6_audit.graph import ScheduleGraph
    from p6_audit.modules.out_of_sequence import run_out_of_sequence
    res = run_out_of_sequence(ScheduleGraph(data), CONFIG)
    return next(f for f in res['findings'] if f['activity_id'] == act_id)


def _accepted_from(finding, **override):
    r = finding['resolution']
    op = {
        'finding_id': finding['finding_id'],
        'pred_id': finding['pred_id'], 'succ_id': finding['activity_id'],
        'action': r['action'], 'new_type': r['new_type'],
        'new_lag_days': r['new_lag_days'], 'new_pred_id': r['new_pred_id'],
        'reason': 'test',
    }
    op.update(override)
    return op


# ── Re-validation ────────────────────────────────────────────────────────────

def test_change_to_ss_clears_the_finding(tmp_path):
    data = parse_file(_write(tmp_path, 's.xml', XML))
    f = _finding(data)
    assert f['resolution']['action'] == 'change' and f['resolution']['new_type'] == 'SS'
    out = R.revalidate(data, CONFIG, [_accepted_from(f)])
    assert f['finding_id'] in out['resolved']
    assert all(x['activity_id'] != 'A200' for x in out['findings'])


def test_recommended_ff_repair_clears_on_revalidation(tmp_path):
    # Successor started before the predecessor but is still running → engine recommends FF (not
    # remove). Applying the recommendation must clear the finding — the repair search and the
    # re-validation use the SAME rule, so they always agree.
    ff_xml = XML.replace('2026-01-05T08:00:00', '2026-01-20T08:00:00')  # A100 (pred) starts later
    data = parse_file(_write(tmp_path, 'ff.xml', ff_xml))
    f = _finding(data)
    assert f['resolution']['action'] == 'change' and f['resolution']['new_type'] == 'FF'
    out = R.revalidate(data, CONFIG, [_accepted_from(f)])
    assert f['finding_id'] in out['resolved']


def test_remove_clears_the_finding(tmp_path):
    data = parse_file(_write(tmp_path, 's.xml', XML))
    f = _finding(data)
    out = R.revalidate(data, CONFIG, [_accepted_from(f, action='remove', new_type=None)])
    assert f['finding_id'] in out['resolved']


def test_insufficient_change_does_not_clear(tmp_path):
    # Keep it FS with 0 lag → still out of sequence → NOT resolved.
    data = parse_file(_write(tmp_path, 's.xml', XML))
    f = _finding(data)
    out = R.revalidate(data, CONFIG, [_accepted_from(f, action='change', new_type='FS', new_lag_days=0)])
    assert f['finding_id'] not in out['resolved']
    assert any(x['activity_id'] == 'A200' for x in out['findings'])


def test_data_op_is_not_applied(tmp_path):
    data = parse_file(_write(tmp_path, 's.xml', XML))
    f = _finding(data)
    out = R.revalidate(data, CONFIG, [_accepted_from(f, action='data')])
    assert f['finding_id'] not in out['resolved']


# ── Corrected file export: XML ───────────────────────────────────────────────

def test_corrected_xml_change_roundtrip(tmp_path):
    src = _write(tmp_path, 's.xml', XML)
    data = parse_file(src)
    f = _finding(data)
    out = str(tmp_path / 'corrected.xml')
    res = R.write_corrected(src, [_accepted_from(f)], out)
    assert res['applied'] >= 1
    rel = parse_file(out).relationships[0]
    assert rel['type'] == 'SS'


def test_corrected_xml_remove_roundtrip(tmp_path):
    src = _write(tmp_path, 's.xml', XML)
    data = parse_file(src)
    f = _finding(data)
    out = str(tmp_path / 'corrected.xml')
    R.write_corrected(src, [_accepted_from(f, action='remove', new_type=None)], out)
    assert parse_file(out).relationships == []


# ── Corrected file export: XER (new writer) ──────────────────────────────────

def test_corrected_xer_change_roundtrip(tmp_path):
    src = _write(tmp_path, 's.xer', XER)
    data = parse_file(src)
    f = _finding(data)
    out = str(tmp_path / 'corrected.xer')
    res = R.write_corrected(src, [_accepted_from(f)], out)
    assert res['applied'] >= 1
    rels = parse_file(out).relationships
    assert len(rels) == 1 and rels[0]['type'] == 'SS'
    assert rels[0]['lag_days'] == f['resolution']['new_lag_days']


def test_corrected_xer_remove_roundtrip(tmp_path):
    src = _write(tmp_path, 's.xer', XER)
    data = parse_file(src)
    f = _finding(data)
    out = str(tmp_path / 'corrected.xer')
    R.write_corrected(src, [_accepted_from(f, action='remove', new_type=None)], out)
    assert parse_file(out).relationships == []


def test_corrected_xer_preserves_other_tables(tmp_path):
    src = _write(tmp_path, 's.xer', XER)
    data = parse_file(src)
    f = _finding(data)
    out = str(tmp_path / 'corrected.xer')
    R.write_corrected(src, [_accepted_from(f)], out)
    reparsed = parse_file(out)
    assert len(reparsed.activities) == 2          # tasks untouched
    assert reparsed.project['id'] == 'PJ'         # project header intact


# ── Units: lag must convert on the activity's own calendar hours ─────────────

def test_lag_days_convert_on_activity_calendar_not_default_8h():
    # A 10-hour/day calendar: 3 working days of lag must be written as 30 hours, not 24.
    # A day_hours==8 fixture would let an 8h-fallback bug pass — this guards against that.
    from p6_evm.parser import ScheduleData
    from p6_evm.calendars import Calendar
    d = ScheduleData()
    d.calendars = {'c10': Calendar(object_id='c10', name='10h', day_hours=10.0)}
    d.activities = {
        'p': {'id': 'A100', 'name': 'Pred', 'calendar_id': 'c10', 'task_type': 'Task'},
        's': {'id': 'A200', 'name': 'Succ', 'calendar_id': 'c10', 'task_type': 'Task'},
    }
    d.relationships = [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS', 'lag_days': 0}]
    accepted = [{'finding_id': 'x', 'pred_id': 'A100', 'succ_id': 'A200',
                 'action': 'change', 'new_type': 'SS', 'new_lag_days': 3, 'new_pred_id': 'A100'}]
    ops = R.to_file_ops(accepted, d)
    set_op = next(o for o in ops if o['kind'] == 'set_rel')
    assert set_op['lag_hours'] == 30.0            # 3 wd × 10 h/day, NOT 24


# ── Robustness: a realistic XER shape (extra columns, CRLF) still round-trips ─

_XER_RICH = (
    "ERMHDR\t19.12\t2026-02-01\tProject\tuser\tuser\tdb\tProjectMgmt\tPMDB\n"
    "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t100\tPJ\t2026-02-01 00:00\n"
    "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\tclndr_data\n%R\t1\tStandard\t8\t\n"
    "%T\tPROJWBS\n%F\twbs_id\tproj_id\tparent_wbs_id\tseq_num\twbs_name\tproj_node_flag\n"
    "%R\t10\t100\t\t1\tConstruction Works\tY\n"
    "%T\tTASK\n%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_code\ttask_name\ttask_type\tstatus_code"
    "\tact_start_date\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt\n"
    "%R\t1001\t100\t10\t1\tA100\tFabricate\tTT_Task\tTK_Active\t2026-01-05 08:00\t2026-01-01 08:00\t2026-01-20 17:00\t400\n"
    "%R\t1002\t100\t10\t1\tA200\tErect\tTT_Task\tTK_Active\t2026-01-12 08:00\t2026-01-21 08:00\t2026-02-10 17:00\t400\n"
    # TASKPRED with MANY real-world columns around the ones we edit:
    "%T\tTASKPRED\n%F\ttask_pred_id\ttask_id\tpred_task_id\tproj_id\tpred_proj_id\tpred_type\tlag_hr_cnt\tcomments\taref\tarls\n"
    "%R\t5001\t1002\t1001\t100\t100\tPR_FS\t0\t\t\t\n"
    "%E\n"
).replace('\n', '\r\n')


def test_corrected_xer_rich_shape_change(tmp_path):
    src = _write(tmp_path, 'rich.xer', _XER_RICH)
    data = parse_file(src)
    f = _finding(data)
    out = str(tmp_path / 'rich_corrected.xer')
    R.write_corrected(src, [_accepted_from(f)], out)
    rels = parse_file(out).relationships
    assert len(rels) == 1 and rels[0]['type'] == 'SS'
    # Every other TASKPRED column must survive verbatim (comments/aref/arls headers kept).
    body = open(out, encoding='utf-8').read()
    assert 'comments\taref\tarls' in body
    assert len(parse_file(out).activities) == 2


def test_corrected_xer_rich_shape_remove(tmp_path):
    src = _write(tmp_path, 'rich.xer', _XER_RICH)
    data = parse_file(src)
    f = _finding(data)
    out = str(tmp_path / 'rich_corrected.xer')
    R.write_corrected(src, [_accepted_from(f, action='remove', new_type=None)], out)
    assert parse_file(out).relationships == []
    assert len(parse_file(out).activities) == 2   # only the relationship row dropped
