"""Dangling — Resolve & Correct: apply a type-change fix, re-validate with the SAME dangling
test, and export a corrected schedule (XER / XML). Reuses the engine-agnostic op application
and file writers from ``oos_resolve``; only the re-validation engine (run_dangling) differs.
"""
import textwrap

from p6_evm.parser import parse_file, ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.dangling import run_dangling
from p6_audit.modules import dangling_resolve as R

CONFIG = {'audit': {}}

# A100 --FF--> A200 --FS--> A300 : A200 start is dangling (only an FF predecessor); its finish is
# driven (FS successor). Changing A100→A200 from FF to FS clears A200.
XML = textwrap.dedent('''\
<?xml version="1.0"?>
<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
  <Project>
    <ObjectId>1</ObjectId><Id>PJ</Id><Name>P</Name>
    <DataDate>2026-02-01T00:00:00</DataDate>
    <WBS><ObjectId>10</ObjectId><Name>Works</Name><ParentObjectId></ParentObjectId></WBS>
    <Activity><ObjectId>1001</ObjectId><Id>A100</Id><Name>Alpha</Name>
      <Type>Task Dependent</Type><Status>Not Started</Status>
      <WBSObjectId>10</WBSObjectId><CalendarObjectId></CalendarObjectId></Activity>
    <Activity><ObjectId>1002</ObjectId><Id>A200</Id><Name>Bravo</Name>
      <Type>Task Dependent</Type><Status>Not Started</Status>
      <WBSObjectId>10</WBSObjectId><CalendarObjectId></CalendarObjectId></Activity>
    <Activity><ObjectId>1003</ObjectId><Id>A300</Id><Name>Charlie</Name>
      <Type>Task Dependent</Type><Status>Not Started</Status>
      <WBSObjectId>10</WBSObjectId><CalendarObjectId></CalendarObjectId></Activity>
    <Relationship><PredecessorActivityObjectId>1001</PredecessorActivityObjectId>
      <SuccessorActivityObjectId>1002</SuccessorActivityObjectId>
      <Type>Finish to Finish</Type><Lag>0</Lag></Relationship>
    <Relationship><PredecessorActivityObjectId>1002</PredecessorActivityObjectId>
      <SuccessorActivityObjectId>1003</SuccessorActivityObjectId>
      <Type>Finish to Start</Type><Lag>0</Lag></Relationship>
  </Project>
</APIBusinessObjects>
''')

# Same one FF relationship in XER form (A100 --FF--> A200), plus A200 --FS--> A300.
XER = (
    "ERMHDR\t19.12\t2026-02-01\tProject\tuser\tuser\tdb\tProjectMgmt\tPMDB\n"
    "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t100\tPJ\t2026-02-01 00:00\n"
    "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\tclndr_data\n%R\t1\tStandard\t8\t\n"
    "%T\tPROJWBS\n%F\twbs_id\tproj_id\tparent_wbs_id\tseq_num\twbs_name\tproj_node_flag\n"
    "%R\t10\t100\t\t1\tWorks\tY\n"
    "%T\tTASK\n%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_code\ttask_name\ttask_type\tstatus_code"
    "\tact_start_date\ttarget_start_date\ttarget_end_date\ttotal_float_hr_cnt\n"
    "%R\t1001\t100\t10\t1\tA100\tAlpha\tTT_Task\tTK_NotStart\t\t2026-01-01 08:00\t2026-01-10 17:00\t400\n"
    "%R\t1002\t100\t10\t1\tA200\tBravo\tTT_Task\tTK_NotStart\t\t2026-01-11 08:00\t2026-01-20 17:00\t400\n"
    "%R\t1003\t100\t10\t1\tA300\tCharlie\tTT_Task\tTK_NotStart\t\t2026-01-21 08:00\t2026-01-30 17:00\t400\n"
    "%T\tTASKPRED\n%F\ttask_pred_id\ttask_id\tpred_task_id\tproj_id\tpred_proj_id\tpred_type\tlag_hr_cnt\n"
    "%R\t5001\t1002\t1001\t100\t100\tPR_FF\t0\n"
    "%R\t5002\t1003\t1002\t100\t100\tPR_FS\t0\n"
    "%E\n"
)


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    return str(p)


def _find(data, act_id):
    return next(f for f in run_dangling(ScheduleGraph(data), CONFIG)['findings']
                if f['activity_id'] == act_id)


def _accepted_start(f, new_type='FS'):
    fx = f['start_fix']
    return {'finding_id': f['finding_id'], 'activity_id': f['activity_id'], 'side': 'start',
            'action': 'change', 'pred_id': fx['target_id'], 'succ_id': f['activity_id'],
            'new_type': new_type, 'new_lag_days': fx['current_lag_days']}


def _accepted_finish(f, new_type='FS'):
    fx = f['finish_fix']
    return {'finding_id': f['finding_id'], 'activity_id': f['activity_id'], 'side': 'finish',
            'action': 'change', 'pred_id': f['activity_id'], 'succ_id': fx['target_id'],
            'new_type': new_type, 'new_lag_days': fx['current_lag_days']}


# ── in-memory graph helpers (both-sided cases) ───────────────────────────────

def _mk(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W', 'category': None}
    b.update(kw); return b


def _data(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return d


# ── Re-validation ────────────────────────────────────────────────────────────

def test_change_pred_type_clears_start_dangling(tmp_path):
    data = parse_file(_write(tmp_path, 's.xml', XML))
    f = _find(data, 'A200')
    assert f['start_dangling'] and f['start_fix']['kind'] == 'change'
    assert f['start_fix']['target_id'] == 'A100'
    out = R.revalidate(data, CONFIG, [_accepted_start(f)])
    assert f['finding_id'] in out['resolved']
    assert all(x['activity_id'] != 'A200' for x in out['findings'])


def test_partial_fix_of_both_sided_activity_stays_open():
    # B: FF predecessor (start dangling) AND SS successor (finish dangling). Fixing ONLY the start
    # must NOT mark the finding resolved — the activity is still dangling (honest accounting even
    # though B's finding_id changes from 'Start + Finish' to 'Finish').
    data = _data({'A': _mk('A'), 'B': _mk('B'), 'C': _mk('C')},
                 [{'pred_id': 'A', 'succ_id': 'B', 'type': 'FF', 'lag_days': 0},
                  {'pred_id': 'B', 'succ_id': 'C', 'type': 'SS', 'lag_days': 0}])
    f = _find(data, 'B')
    assert f['start_dangling'] and f['finish_dangling']
    out = R.revalidate(data, CONFIG, [_accepted_start(f)])
    assert f['finding_id'] not in out['resolved']
    assert any(x['activity_id'] == 'B' for x in out['findings'])


def test_fixing_both_sides_clears_the_activity():
    data = _data({'A': _mk('A'), 'B': _mk('B'), 'C': _mk('C')},
                 [{'pred_id': 'A', 'succ_id': 'B', 'type': 'FF', 'lag_days': 0},
                  {'pred_id': 'B', 'succ_id': 'C', 'type': 'SS', 'lag_days': 0}])
    f = _find(data, 'B')
    out = R.revalidate(data, CONFIG, [_accepted_start(f), _accepted_finish(f)])
    assert f['finding_id'] in out['resolved']
    assert all(x['activity_id'] != 'B' for x in out['findings'])


def test_applying_one_activity_does_not_resolve_another():
    data = _data({'A': _mk('A'), 'B': _mk('B'), 'C': _mk('C')},
                 [{'pred_id': 'A', 'succ_id': 'B', 'type': 'FF', 'lag_days': 0},
                  {'pred_id': 'B', 'succ_id': 'C', 'type': 'FS', 'lag_days': 0}])
    fb = _find(data, 'B')       # B start dangling (FF pred)
    out = R.revalidate(data, CONFIG, [_accepted_start(fb)])
    # A (no predecessor) and C (no successor) are still dangling — not falsely resolved.
    still = {x['activity_id'] for x in out['findings']}
    assert 'A' in still and 'C' in still
    assert out['resolved'] == [fb['finding_id']]


# ── Corrected-file export ─────────────────────────────────────────────────────

def _assert_corrected_clears_a200(out_path):
    reparsed = parse_file(out_path)
    assert all(r['type'] != 'FF' for r in reparsed.relationships)   # the FF tie was re-typed
    ids = [x['activity_id'] for x in run_dangling(ScheduleGraph(reparsed), CONFIG)['findings']]
    assert 'A200' not in ids                                        # genuinely no longer dangling


def test_corrected_xml_roundtrip(tmp_path):
    src = _write(tmp_path, 's.xml', XML)
    data = parse_file(src)
    f = _find(data, 'A200')
    out = str(tmp_path / 'c.xml')
    res = R.write_corrected(src, [_accepted_start(f)], out)
    assert res['applied'] >= 1
    _assert_corrected_clears_a200(out)


def test_corrected_xer_roundtrip(tmp_path):
    src = _write(tmp_path, 's.xer', XER)
    data = parse_file(src)
    f = _find(data, 'A200')
    out = str(tmp_path / 'c.xer')
    res = R.write_corrected(src, [_accepted_start(f)], out)
    assert res['applied'] >= 1
    _assert_corrected_clears_a200(out)
    assert len(parse_file(out).activities) == 3    # tasks untouched


def test_no_accepted_ops_changes_nothing(tmp_path):
    data = parse_file(_write(tmp_path, 's.xml', XML))
    out = R.revalidate(data, CONFIG, [])
    assert out['resolved'] == []
    # every originally-dangling activity is still present
    before = {x['activity_id'] for x in run_dangling(ScheduleGraph(data), CONFIG)['findings']}
    after = {x['activity_id'] for x in out['findings']}
    assert before == after


# ── Contract-milestone guard (offline forward-pass estimate) ─────────────────
# P --FF--> D --FS--> COMP(Practical Completion) ; R --FF--> Q --FS--> S. Data date 1-Jan-2026.
# Baseline COMP finishes 16-Jan (FF from P doesn't drive D's start). Fixing P→D to FS delays D's
# start to P's finish, pushing COMP to 21-Jan — past the 20-Jan contract → that fix is blocked.
# Fixing R→Q (FF→FS) reshuffles Q/S but never touches COMP → allowed.
from datetime import datetime as _dt


def _mkd(oid, dur_h=0, task='Task', **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': task,
         'is_critical': False, 'wbs_path': 'P > W', 'category': None,
         'remaining_duration': dur_h, 'calendar_id': None,
         'actual_start': None, 'actual_finish': None}
    b.update(kw); return b


def _proj():
    acts = {
        'P':    _mkd('P', 120),                                   # 15 calendar days
        'D':    _mkd('D', 40),                                    # 5 days
        'COMP': _mkd('COMP', 0, task='FinishMilestone', name='Practical Completion'),
        'R':    _mkd('R', 64),                                    # 8 days
        'Q':    _mkd('Q', 40),                                    # 5 days
        'S':    _mkd('S', 24),                                    # 3 days
    }
    rels = [
        {'pred_id': 'P', 'succ_id': 'D', 'type': 'FF', 'lag_days': 0},
        {'pred_id': 'D', 'succ_id': 'COMP', 'type': 'FS', 'lag_days': 0},
        {'pred_id': 'R', 'succ_id': 'Q', 'type': 'FF', 'lag_days': 0},
        {'pred_id': 'Q', 'succ_id': 'S', 'type': 'FS', 'lag_days': 0},
    ]
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    d.project = {'data_date': _dt(2026, 1, 1)}
    return d


_COMPLETION = {'activity_id': 'COMP', 'contract_date': '2026-01-20'}


def test_fix_that_pushes_completion_past_contract_is_blocked():
    data = _proj()
    fD = _find(data, 'D')
    out = R.revalidate(data, CONFIG, [_accepted_start(fD)], completion=_COMPLETION)
    assert fD['finding_id'] in out['blocked']            # held back
    assert fD['finding_id'] not in out['resolved']       # never counted resolved
    assert any(x['activity_id'] == 'D' for x in out['findings'])  # stays open (fix not applied)


def test_fix_that_does_not_touch_completion_is_allowed():
    data = _proj()
    fQ = _find(data, 'Q')
    out = R.revalidate(data, CONFIG, [_accepted_start(fQ)], completion=_COMPLETION)
    assert fQ['finding_id'] not in out['blocked']
    assert fQ['finding_id'] in out['resolved']           # Q's only dangling side fixed → resolved


def test_no_completion_means_no_guard():
    data = _proj()
    fD = _find(data, 'D')
    out = R.revalidate(data, CONFIG, [_accepted_start(fD)])   # no completion passed
    assert out['blocked'] == []
    assert fD['finding_id'] in out['resolved']           # applies normally without the guard


def test_milestone_blocked_helper_directly():
    data = _proj()
    fD = _find(data, 'D')
    fQ = _find(data, 'Q')
    blocked = R.milestone_blocked(data, [_accepted_start(fD), _accepted_start(fQ)], _COMPLETION)
    assert fD['finding_id'] in blocked and fQ['finding_id'] not in blocked


# ── Live execution-dashboard update: revalidate returns the recomputed score/tiles ───────────

def test_revalidate_returns_updated_score_and_presentation(tmp_path):
    data = parse_file(_write(tmp_path, 's.xml', XML))
    base = run_dangling(ScheduleGraph(data), CONFIG)
    f = _find(data, 'A200')
    out = R.revalidate(data, CONFIG, [_accepted_start(f)])
    # the fresh score/grade/pct + presentation are returned so the screen dashboard can repaint
    assert out['score'] is not None and out['grade'] and out['pct'] is not None
    assert isinstance(out['presentation'], dict) and out['presentation'].get('tiles')
    # resolving a finding removes it → fewer dangling → the score goes UP (never down)
    assert out['kpis']['total_dangling'] < base['kpis']['total_dangling']
    assert out['score'] >= base['score']
