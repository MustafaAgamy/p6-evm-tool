"""Whole-day Review & Resolve, and the ONE corrected schedule the Summary downloads."""
import os

import pytest

from p6_evm.parser import parse_file
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.whole_day import run_whole_day
from p6_audit.modules.whole_day_resolve import revalidate, write_corrected
from p6_audit.corrected_file import FIXERS, fixer_keys, write_combined

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = {}

HEAD = 'ERMHDR\t19.12\t2026-01-01\tProject\tadmin\tadmin\tdbxDatabaseNoName\tProject Management\tEGP\n'
XER = (HEAD + '\n'.join([
    '%T\tCURRTYPE', '%F\tcurr_id\tcurr_symbol\tcurr_short_name', '%R\t1\t\xa3\tEGP',
    '%T\tPROJECT', '%F\tproj_id\tproj_short_name\tlast_recalc_date\tplan_start_date',
    '%R\t1\tWD\t2026-01-01 00:00\t2026-01-01 00:00',
    '%T\tCALENDAR', '%F\tclndr_id\tclndr_name\tday_hr_cnt\tweek_hr_cnt\tclndr_data',
    '%R\t10\tSix Day 10h\t10\t60\t',
    '%T\tPROJWBS', '%F\twbs_id\tproj_id\tparent_wbs_id\twbs_short_name\twbs_name\tproj_node_flag',
    '%R\t100\t1\t\tWD\tProject\tY', '%R\t101\t1\t100\tC\tConstruction\tN',
    '%T\tTASK',
    '%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_code\ttask_name\ttask_type\tstatus_code'
    '\ttarget_drtn_hr_cnt\tremain_drtn_hr_cnt\tphys_complete_pct\ttarget_start_date\ttarget_end_date'
    '\tact_start_date\tact_end_date\ttotal_float_hr_cnt',
    '%R\t1\t1\t101\t10\tA100\tExcavation\tTT_Task\tTK_NotStart\t144\t144\t0\t2026-01-01 08:00\t2026-01-17 12:00\t\t\t0',
    '%R\t2\t1\t101\t10\tA200\tBlinding\tTT_Task\tTK_NotStart\t50\t50\t0\t2026-01-18 08:00\t2026-01-22 18:00\t\t\t0',
    '%R\t3\t1\t101\t10\tA300\tRaft\tTT_Task\tTK_Active\t75\t30\t60\t2026-01-23 08:00\t2026-01-31 13:00\t2026-01-23 08:00\t\t0',
    '%T\tTASKPRED', '%F\ttask_pred_id\ttask_id\tpred_task_id\tproj_id\tpred_proj_id\tpred_type\tlag_hr_cnt',
    '%R\t1\t2\t1\t1\t1\tPR_FS\t0', '%R\t2\t3\t2\t1\t1\tPR_FS\t0',
    '%E', ''])).replace('\n', '\r\n')


@pytest.fixture
def xer(tmp_path):
    p = tmp_path / 'wd.xer'
    p.write_bytes(XER.encode('cp1252'))
    return str(p)


def _check(path):
    return run_whole_day(ScheduleGraph(parse_file(path)), CONFIG)


def _fix(m, code, days):
    f = next(x for x in m['findings'] if x['activity_id'] == code)
    return {'finding_id': f['finding_id'], 'activity_id': code, 'new_days': days}


def test_applied_fix_resolves_and_a_started_activity_is_held(xer):
    m = _check(xer)
    assert {f['activity_id'] for f in m['findings']} == {'A100', 'A300'}      # 14.4 d and 7.5 d
    out = revalidate(parse_file(xer), CONFIG, [_fix(m, 'A100', 15), _fix(m, 'A300', 8)])
    assert [f['activity_id'] for f in out['findings']] == ['A300']            # started: left open
    assert len(out['resolved']) == 1 and len(out['held']) == 1
    assert out['kpis']['decimal_count'] == 1 and out['score'] > m['score']
    labels = [t['label'] for t in out['presentation']['tiles']]
    assert labels[:3] == ['Total Activities', 'Remaining Activities', 'Task Activities Checked']


def test_typed_decimal_value_leaves_the_activity_flagged(xer):
    m = _check(xer)
    out = revalidate(parse_file(xer), CONFIG, [_fix(m, 'A100', 14.5)])
    assert 'A100' in {f['activity_id'] for f in out['findings']} and out['resolved'] == []


def test_corrected_xer_changes_only_the_durations_and_keeps_the_file_as_it_was(xer, tmp_path):
    m = _check(xer)
    out = str(tmp_path / 'out.xer')
    res = write_corrected(xer, [_fix(m, 'A100', 15), _fix(m, 'A300', 8)], out)
    assert res['applied'] == 1
    src, new = open(xer, 'rb').read(), open(out, 'rb').read()
    assert b'\xa3' in new and b'\r\n' in new                     # encoding and line ends preserved
    a, b = src.split(b'\r\n'), new.split(b'\r\n')
    assert len(a) == len(b) and sum(1 for x, y in zip(a, b) if x != y) == 1
    row = next(l for l in b if b'\tA100\t' in l).split(b'\t')
    assert row[9] == b'150' and row[10] == b'150'               # Original + Remaining, 15 d x 10 h
    assert {f['activity_id'] for f in _check(out)['findings']} == {'A300'}


def test_summary_file_carries_every_sub_features_fixes(xer, tmp_path):
    assert fixer_keys() == ['dangling', 'whole_day'] and all(callable(f['write']) for f in FIXERS)
    m = _check(xer)
    out = str(tmp_path / 'all.xer')
    dng = [{'finding_id': 'D1', 'activity_id': 'A200', 'side': 'start', 'pred_id': 'A100',
            'succ_id': 'A200', 'new_type': 'SS', 'new_lag_days': 0}]
    res = write_combined(xer, {'whole_day': [_fix(m, 'A100', 15)], 'dangling': dng}, out)
    assert res['by_feature']['whole_day'] == 1 and set(res['by_feature']) == {'dangling', 'whole_day'}
    assert res['applied'] == sum(res['by_feature'].values())
    assert {f['activity_id'] for f in _check(out)['findings']} == {'A300'}
    with pytest.raises(ValueError):
        write_combined(xer, {}, out)


def test_report_and_workbook_print_the_figures_after_the_fixes():
    import server
    cls = next(v for v in vars(server).values()
               if isinstance(v, type) and hasattr(v, '_whole_day_as_on_screen'))
    stored = {'module': 'whole_day', 'pct': 7.2, 'kpis': {'decimal_count': 62}, 'findings': [{}] * 62,
              'presentation': {'verdict': 'old'}}
    live = {'score': 98.6, 'pct': 1.4, 'kpis': {'decimal_count': 12}, 'findings': [{}] * 12,
            'presentation': {'verdict': '1.4% decimal.'}, 'applied': 50}
    out = cls._whole_day_as_on_screen(stored, {'whole_day_live': live})
    assert out['pct'] == 1.4 and len(out['findings']) == 12
    assert 'After 50 applied fixes' in out['presentation']['verdict']
    assert cls._whole_day_as_on_screen(stored, {}) is stored and stored['pct'] == 7.2


def test_ui_is_wired():
    def read(rel):
        with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
            return f.read()
    audit, api = read('ui/modules/audit.js'), read('ui/modules/api.js')
    for s in ('/api/wholeday/validate', '/api/health/corrected-file', 'Whole-day Review &amp; Resolve',
              'Download Corrected XER', 'Apply all suggested fixes in every sub-feature',
              'Activity has started', 'export function wdLiveModule'):
        assert s in audit, s
    assert 'whole_day_live' in api
    assert 'confirm(' not in audit.split('function _wdApply')[1].split('function renderWholeDay')[0]
