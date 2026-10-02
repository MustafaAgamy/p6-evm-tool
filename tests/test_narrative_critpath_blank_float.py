"""Owner comment 17 — the Baseline Narrative said 'no critical path' on the Saint Gobain baseline.

Cause: that XER was exported with every activity's Total Float column (total_float_hr_cnt)
BLANK, so the reader had no float for any activity and the Appendix (Critical Path) reported
"The schedule carries no total-float values". The XER reader now rebuilds a blank float from
the activity's own early / late dates, exactly as P6 computes it (and as the XML reader does),
so the Narrative finds the critical path. Checked on the real file: 223 critical activities,
19-Dec.2024 → Project Completion 30-Aug.2025.

This locks the whole chain: blank float in the XER → float rebuilt → Narrative critical path.
"""
from p6_evm.parser import parse_file
from p6_narrative import critpath
from p6_narrative.report import build_report

HEAD = ("%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_type\tstatus_code\ttask_code\ttask_name\t"
        "target_drtn_hr_cnt\tremain_drtn_hr_cnt\ttotal_float_hr_cnt\ttarget_start_date\ttarget_end_date\t"
        "restart_date\treend_date\trem_late_start_date\trem_late_end_date\n")


def _row(tid, code, name, wbs, es, ef, ls, lf, tf=''):
    return (f"%R\t{tid}\t1\t{wbs}\t10\tTT_Task\tTK_NotStart\t{code}\t{name}\t40\t40\t{tf}\t"
            f"{es}\t{ef}\t{es}\t{ef}\t{ls}\t{lf}\n")


def _xer(tmp_path, float_col=''):
    rows = (
        # the driving chain: late dates = early dates → zero float
        _row(1001, 'EX-1000', 'Excavation works', 110, '2025-03-03 08:00', '2025-03-07 17:00',
             '2025-03-03 08:00', '2025-03-07 17:00', float_col)
        + _row(1002, 'RC-1000', 'RC columns pouring', 110, '2025-03-10 08:00', '2025-03-14 17:00',
               '2025-03-10 08:00', '2025-03-14 17:00', float_col)
        + _row(1003, 'ST-1000', 'Steel structure erection', 120, '2025-03-17 08:00', '2025-03-21 17:00',
               '2025-03-17 08:00', '2025-03-21 17:00', float_col)
        # a side activity that can slip two weeks → positive float, not critical
        + _row(1004, 'FN-1000', 'Painting works', 120, '2025-03-03 08:00', '2025-03-07 17:00',
               '2025-03-17 08:00', '2025-03-21 17:00', float_col)
    )
    text = (
        "ERMHDR\t19.12\n"
        "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t1\tSG\t2025-03-01 00:00\n"
        "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\n%R\t10\t5-Day\t8\n"
        "%T\tPROJWBS\n%F\twbs_id\twbs_name\tparent_wbs_id\tproj_node_flag\n"
        "%R\t100\tSaint Gobain Baseline\t\tY\n%R\t110\tBatch House\t100\tN\n%R\t120\tMixer Building\t100\tN\n"
        "%T\tTASK\n" + HEAD + rows + "%E\n")
    p = tmp_path / 'blank_float.xer'
    p.write_text(text, encoding='cp1252')
    return str(p)


def test_blank_total_float_in_the_xer_is_rebuilt_from_the_dates(tmp_path):
    data = parse_file(_xer(tmp_path))
    tf = {a['id']: a.get('total_float_days') for a in data.activities.values()}
    assert all(v is not None for v in tf.values()), tf          # was: every one None → "no critical path"
    assert tf['EX-1000'] == 0 and tf['RC-1000'] == 0 and tf['ST-1000'] == 0
    assert tf['FN-1000'] > 0


def test_narrative_finds_the_critical_path_when_the_float_column_is_blank(tmp_path):
    path = _xer(tmp_path)
    data = parse_file(path)
    cp = critpath.critical_path(data)
    assert cp['available'] is True and cp['crit_basis'] == 'tf<=0'
    kpis = {label: value for value, label in cp['kpis']}
    assert kpis['Critical activities'] == '3'
    assert kpis['Critical path start'] == '03-Mar.2025' and kpis['Critical path finish'] == '21-Mar.2025'
    # … and the report section carries it (never the 'no total-float values' note)
    sec = next(s for s in build_report(data, path=path, setup=None).to_dict()['sections'] if s.get('kind') == 'critpath')
    assert sec['payload']['available'] is True
    assert 'no total-float' not in (sec['payload'].get('note') or '')


def test_a_float_p6_did_export_is_used_as_is(tmp_path):
    # 16 working hours on an 8 h calendar = 2 days for every activity, whatever the dates say
    data = parse_file(_xer(tmp_path, float_col='16'))
    assert {a.get('total_float_days') for a in data.activities.values()} == {2.0}
    cp = critpath.critical_path(data)                         # no activity at zero → the least-float band
    assert cp['available'] is True and cp['crit_basis'] == 'min-float'


def test_no_dates_and_no_float_still_says_so_honestly(tmp_path):
    text = (
        "ERMHDR\t19.12\n"
        "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t1\tSG\t2025-03-01 00:00\n"
        "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\n%R\t10\t5-Day\t8\n"
        "%T\tPROJWBS\n%F\twbs_id\twbs_name\tparent_wbs_id\tproj_node_flag\n%R\t100\tP\t\tY\n"
        "%T\tTASK\n"
        "%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_type\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\n"
        "%R\t1001\t1\t100\t10\tTT_Task\tA1\tTask A\t2025-03-03 08:00\t2025-03-07 17:00\n%E\n")
    p = tmp_path / 'nofloat.xer'
    p.write_text(text, encoding='cp1252')
    cp = critpath.critical_path(parse_file(str(p)))
    assert cp['available'] is False and 'no total-float values' in cp['note']
