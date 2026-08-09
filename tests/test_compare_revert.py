"""revert_operations + write_corrected_xml — the corrected "but-for" XML.

revert_operations turns the driving-logic and duration diffs into a locatable,
selectable revert plan (baseline targets in raw hours). write_corrected_xml edits a
copy of the update XML — relationships / lags / durations back to baseline — leaving
every actual / progress field untouched, so P6 can reschedule the genuine delay.
"""
import textwrap
from p6_evm.parser import ScheduleData, parse_file
from p6_compare.model import MatchedSchedules
from p6_compare.revert import revert_operations, write_corrected_xml, write_corrected_from_paths


def _act(code, name='', planned=0.0, remaining=0.0):
    return {'id': code, 'name': name, 'task_type': 'Task', 'calendar_id': None,
            'planned_duration': planned, 'remaining_duration': remaining}


def _rel(pred_oid, succ_oid, type_='FS', lag_days=0.0, lag_hours=0.0):
    return {'pred_id': pred_oid, 'succ_id': succ_oid, 'type': type_,
            'lag_days': lag_days, 'lag_hours': lag_hours}


def _sched(acts, rels):
    d = ScheduleData()
    d.activities = acts
    d.relationships = rels
    return d


# ── revert_operations ──────────────────────────────────────────────────────

def test_revert_op_set_rel_uses_baseline_hours():
    # Baseline FS+0 (0h); update FS+10d (80h) — revert restores the baseline hours.
    base = _sched({'p': _act('A050', 'Clearance'), 's': _act('A100', 'Excavate')},
                  [_rel('p', 's', 'FS', 0.0, 0.0)])
    upd = _sched({'p': _act('A050', 'Clearance'), 's': _act('A100', 'Excavate')},
                 [_rel('p', 's', 'FS', 10.0, 80.0)])
    logic = {'rows': [{'activity_id': 'A100',
                       'update_preds': [{'code': 'A050', 'status': 'changed'}],
                       'baseline_preds': [{'code': 'A050', 'status': 'same'}]}]}
    ops = revert_operations(MatchedSchedules(base, upd), logic, {'rows': []})
    assert len(ops) == 1
    op = ops[0]
    assert op['kind'] == 'set_rel'
    assert (op['pred_code'], op['succ_code']) == ('A050', 'A100')
    assert op['type'] == 'FS' and op['lag_hours'] == 0.0


def test_revert_op_added_link_removed():
    base = _sched({'p': _act('A050'), 's': _act('A100')}, [])
    upd = _sched({'p': _act('A050'), 's': _act('A100')}, [_rel('p', 's', 'FS', 0.0, 0.0)])
    logic = {'rows': [{'activity_id': 'A100',
                       'update_preds': [{'code': 'A050', 'status': 'added'}],
                       'baseline_preds': []}]}
    ops = revert_operations(MatchedSchedules(base, upd), logic, {'rows': []})
    assert [o['kind'] for o in ops] == ['remove_rel']


def test_revert_op_removed_link_restored_with_baseline_type_lag():
    base = _sched({'p': _act('A050'), 's': _act('A100')}, [_rel('p', 's', 'SS', 2.0, 16.0)])
    upd = _sched({'p': _act('A050'), 's': _act('A100')}, [])
    logic = {'rows': [{'activity_id': 'A100', 'update_preds': [],
                       'baseline_preds': [{'code': 'A050', 'status': 'removed'}]}]}
    ops = revert_operations(MatchedSchedules(base, upd), logic, {'rows': []})
    assert ops[0]['kind'] == 'add_rel'
    assert ops[0]['type'] == 'SS' and ops[0]['lag_hours'] == 16.0


def test_revert_op_link_that_only_became_driving_is_not_touched():
    # Same relationship in both files (unchanged) but flagged 'added' in the driving
    # diff → must NOT be removed; there is nothing to revert.
    base = _sched({'p': _act('A050'), 's': _act('A100')}, [_rel('p', 's', 'FS', 0.0, 0.0)])
    upd = _sched({'p': _act('A050'), 's': _act('A100')}, [_rel('p', 's', 'FS', 0.0, 0.0)])
    logic = {'rows': [{'activity_id': 'A100',
                       'update_preds': [{'code': 'A050', 'status': 'added'}],
                       'baseline_preds': []}]}
    ops = revert_operations(MatchedSchedules(base, upd), logic, {'rows': []})
    assert ops == []


def test_revert_op_duration_baseline_minus_time_spent():
    # baseline 96h; update planned 144h, remaining 120h → spent 24h → remaining 96-24 = 72h
    base = _sched({'s': _act('A1250', planned=96.0, remaining=96.0)}, [])
    upd = _sched({'s': _act('A1250', planned=144.0, remaining=120.0)}, [])
    durations = {'rows': [{'activity_id': 'A1250', 'update_orig_days': 18.0, 'baseline_orig_days': 12.0}]}
    ops = revert_operations(MatchedSchedules(base, upd), {'rows': []}, durations)
    assert ops[0]['kind'] == 'set_duration'
    assert ops[0]['planned_hours'] == 96.0
    assert ops[0]['remaining_hours'] == 72.0


# ── write_corrected_xml (round-trip through parse_file) ─────────────────────

def _update_xml(tmp_path, lag='80', planned='144', remaining='120', with_rel=True):
    rel = textwrap.dedent(f'''\
        <Relationship>
          <ObjectId>5001</ObjectId>
          <PredecessorActivityObjectId>1001</PredecessorActivityObjectId>
          <SuccessorActivityObjectId>1002</SuccessorActivityObjectId>
          <Type>Finish to Start</Type><Lag>{lag}</Lag>
        </Relationship>''') if with_rel else ''
    content = textwrap.dedent(f'''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Project>
        <ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name>
        <Activity>
          <ObjectId>1001</ObjectId><Id>A050</Id><Name>Clearance</Name>
          <Type>Task Dependent</Type><Status>Completed</Status>
        </Activity>
        <Activity>
          <ObjectId>1002</ObjectId><Id>A100</Id><Name>Excavate</Name>
          <Type>Task Dependent</Type><Status>In Progress</Status>
          <PercentComplete>25</PercentComplete>
          <PlannedDuration>{planned}</PlannedDuration><RemainingDuration>{remaining}</RemainingDuration>
          <ActualStartDate>2026-07-20T08:00:00</ActualStartDate>
        </Activity>
    {textwrap.indent(rel, "    ")}
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / "upd.xml"
    p.write_text(content, encoding='utf-8')
    return str(p)


def test_write_reverts_lag_and_leaves_actuals(tmp_path):
    src = _update_xml(tmp_path, lag='80')
    out = str(tmp_path / "corrected.xml")
    ops = [{'kind': 'set_rel', 'pred_code': 'A050', 'succ_code': 'A100', 'type': 'FS', 'lag_hours': 0.0}]
    res = write_corrected_xml(src, ops, out, note='But-for analysis — not the official schedule')
    assert res['applied'] == 1
    data = parse_file(out)
    assert data.relationships[0]['lag_hours'] == 0.0                    # reverted
    assert data.activities['1002']['actual_start'] is not None         # actual untouched
    assert data.activities['1002']['percent_complete'] == 25.0         # progress untouched


def test_write_removes_added_link(tmp_path):
    src = _update_xml(tmp_path)
    out = str(tmp_path / "c.xml")
    write_corrected_xml(src, [{'kind': 'remove_rel', 'pred_code': 'A050', 'succ_code': 'A100'}], out)
    assert parse_file(out).relationships == []


def test_write_restores_removed_link(tmp_path):
    src = _update_xml(tmp_path, with_rel=False)   # update dropped the link
    out = str(tmp_path / "c.xml")
    ops = [{'kind': 'add_rel', 'pred_code': 'A050', 'succ_code': 'A100', 'type': 'SS', 'lag_hours': 16.0}]
    assert write_corrected_xml(src, ops, out)['applied'] == 1
    rels = parse_file(out).relationships
    assert len(rels) == 1
    assert rels[0]['pred_id'] == '1001' and rels[0]['succ_id'] == '1002'
    assert rels[0]['type'] == 'SS' and rels[0]['lag_hours'] == 16.0


def test_write_restores_link_via_clone_when_template_exists(tmp_path):
    # Realistic case: the update still has other relationships, so add_rel clones one
    # as a template and overwrites its endpoints / type / lag / ObjectId.
    src = _update_xml(tmp_path, with_rel=True)     # existing A050→A100 link = clone template
    out = str(tmp_path / "c.xml")
    ops = [{'kind': 'add_rel', 'pred_code': 'A100', 'succ_code': 'A050', 'type': 'FF', 'lag_hours': 8.0}]
    assert write_corrected_xml(src, ops, out)['applied'] == 1
    rels = {(r['pred_id'], r['succ_id']): r for r in parse_file(out).relationships}
    assert ('1001', '1002') in rels                # original relationship kept
    added = rels[('1002', '1001')]                 # restored link, endpoints resolved by code
    assert added['type'] == 'FF' and added['lag_hours'] == 8.0


def test_write_reverts_duration_leaves_progress(tmp_path):
    src = _update_xml(tmp_path, planned='144', remaining='120')
    out = str(tmp_path / "c.xml")
    ops = [{'kind': 'set_duration', 'activity_id': 'A100', 'planned_hours': 96.0, 'remaining_hours': 72.0}]
    write_corrected_xml(src, ops, out)
    a = parse_file(out).activities['1002']
    assert a['planned_duration'] == 96.0 and a['remaining_duration'] == 72.0
    assert a['percent_complete'] == 25.0                               # untouched


def test_write_missing_project_raises(tmp_path):
    p = tmp_path / "bad.xml"
    p.write_text('<?xml version="1.0"?>\n<APIBusinessObjects xmlns="http://x"/>\n', encoding='utf-8')
    import pytest
    with pytest.raises(ValueError):
        write_corrected_xml(str(p), [], str(tmp_path / "o.xml"))


# ── End-to-end: two files → the exact server path → corrected file ──────────

def _driving_xml(tmp_path, name, succ_start, lag_hours):
    """A minimal baseline/update pair where A050 → A100 (FS) is the driving link.
    Same pred finish; the successor's remaining early start moves out by `lag_hours`,
    so the link stays driving and only its lag changes."""
    content = textwrap.dedent(f'''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Project>
        <ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name>
        <Activity>
          <ObjectId>1</ObjectId><Id>A050</Id><Name>Clearance</Name><Type>Task Dependent</Type>
          <RemainingEarlyFinishDate>2026-01-10T08:00:00</RemainingEarlyFinishDate>
        </Activity>
        <Activity>
          <ObjectId>2</ObjectId><Id>A100</Id><Name>Excavate</Name><Type>Task Dependent</Type>
          <RemainingEarlyStartDate>{succ_start}T08:00:00</RemainingEarlyStartDate>
        </Activity>
        <Relationship>
          <ObjectId>9</ObjectId>
          <PredecessorActivityObjectId>1</PredecessorActivityObjectId>
          <SuccessorActivityObjectId>2</SuccessorActivityObjectId>
          <Type>Finish to Start</Type><Lag>{lag_hours}</Lag>
        </Relationship>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / name
    p.write_text(content, encoding='utf-8')
    return str(p)


def test_corrected_from_paths_reverts_driving_lag_end_to_end(tmp_path):
    # Baseline: FS+0 (start 10 Jan, gap 0). Update: FS+10d (start 20 Jan, gap 10, lag 80h).
    # The full server path (parse → driving diff → revert plan → write) must revert the lag.
    baseline = _driving_xml(tmp_path, 'baseline.xml', '2026-01-10', '0')
    update = _driving_xml(tmp_path, 'update.xml', '2026-01-20', '80')
    out = str(tmp_path / 'update_but-for.xml')
    res = write_corrected_from_paths(baseline, update, out)   # selected_ids=None → revert all
    assert res['applied'] == 1
    rel = parse_file(out).relationships[0]
    assert rel['lag_hours'] == 0.0            # driving lag reverted to baseline
    assert rel['lag_days'] == 0.0
