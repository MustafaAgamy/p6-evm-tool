from p6_evm.xer import parse_xer
from p6_evm.parser import parse_file

SAMPLE = (
    "ERMHDR\t19.12\n"
    "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t1\tTOWER33\t2026-07-24 00:00\n"
    "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\n%R\t10\t5-Day\t8\n"
    "%T\tPROJWBS\n%F\twbs_id\twbs_name\tparent_wbs_id\tproj_node_flag\n"
    "%R\t100\tTower 33\t\tY\n%R\t101\tStructure\t100\tN\n"
    "%T\tTASK\n"
    "%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_type\ttask_code\ttask_name\ttotal_float_hr_cnt\tfree_float_hr_cnt\tcstr_type\tcstr_date\n"
    "%R\t1001\t1\t101\t10\tTT_Task\tA230\tRoof Steel\t0\t0\t\t\n"
    "%R\t1002\t1\t101\t10\tTT_Task\tA240\tRoof Cladding\t320\t80\tCS_MSO\t2026-08-01 00:00\n"
    "%T\tTASKPRED\n%F\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt\n%R\t1002\t1001\tPR_FS\t0\n"
    "%E\n"
)


def test_parse_xer_builds_model(tmp_path):
    p = tmp_path / "s.xer"; p.write_text(SAMPLE, encoding='cp1252')
    data = parse_xer(str(p))
    assert data.project['name'] == 'TOWER33'
    a = data.activities['1002']
    assert a['id'] == 'A240'
    assert a['task_type'] == 'Task'
    assert a['total_float_days'] == 40.0      # 320 / 8
    assert a['free_float_days'] == 10.0
    assert a['is_critical'] is False
    assert a['constraint_type'] == 'CS_MSO'
    assert a['wbs_path'] == 'Tower 33 > Structure'
    crit = data.activities['1001']
    assert crit['is_critical'] is True         # 0 float
    rel = data.relationships[0]
    assert rel['pred_id'] == '1001' and rel['succ_id'] == '1002' and rel['type'] == 'FS'


def test_parse_file_dispatches_on_extension(tmp_path):
    p = tmp_path / "s.xer"; p.write_text(SAMPLE, encoding='cp1252')
    data = parse_file(str(p))
    assert '1001' in data.activities
