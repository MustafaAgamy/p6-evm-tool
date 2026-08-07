from p6_evm.xer import read_xer_tables

SAMPLE = (
    "ERMHDR\t19.12\t2026-07-24\tProject\tadmin\n"
    "%T\tPROJECT\n"
    "%F\tproj_id\tproj_short_name\n"
    "%R\t123\tTOWER33\n"
    "%T\tTASK\n"
    "%F\ttask_id\ttask_code\ttask_name\ttotal_float_hr_cnt\n"
    "%R\t1001\tA230\tRoof Steel\t0\n"
    "%R\t1002\tA240\tRoof Cladding\t40\n"
    "%E\n"
)


def test_reads_tables_and_rows(tmp_path):
    p = tmp_path / "s.xer"
    p.write_text(SAMPLE, encoding='cp1252')
    tables = read_xer_tables(str(p))
    assert set(tables) == {'PROJECT', 'TASK'}
    assert tables['PROJECT'][0]['proj_short_name'] == 'TOWER33'
    assert tables['TASK'][1]['task_code'] == 'A240'
    assert tables['TASK'][0]['total_float_hr_cnt'] == '0'
