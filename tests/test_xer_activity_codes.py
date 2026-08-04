from p6_evm.xer import parse_xer

SAMPLE = (
    "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t1\tGBT\t2025-12-11 08:00\n"
    "%T\tPROJWBS\n%F\twbs_id\tproj_id\tproj_node_flag\twbs_name\tparent_wbs_id\n"
    "%R\t10\t1\tY\tGBT\t\n"
    "%T\tACTVTYPE\n%F\tactv_code_type_id\tactv_code_type\n"
    "%R\t100\tType of Works\n%R\t200\tTrade Design\n"
    "%T\tACTVCODE\n%F\tactv_code_id\tactv_code_type_id\tshort_name\tactv_code_name\n"
    "%R\t1001\t100\tPILE\tPiles Works\n%R\t1002\t100\tCOL\tColumns Works\n%R\t2001\t200\tCVL\tCivil\n"
    "%T\tTASK\n%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_type\ttask_code\ttask_name\n"
    "%R\t5001\t1\t10\t\tTT_Task\tA1000\tBore Pile\n"
    "%R\t5002\t1\t10\t\tTT_Task\tA1010\tCast Column\n"
    "%T\tTASKACTV\n%F\ttask_id\tactv_code_type_id\tactv_code_id\n"
    "%R\t5001\t100\t1001\n%R\t5001\t200\t2001\n%R\t5002\t100\t1002\n"
    "%E\n"
)


def test_activity_code_types_listed(tmp_path):
    p = tmp_path / "s.xer"
    p.write_text(SAMPLE, encoding='cp1252')
    data = parse_xer(str(p))
    assert 'Type of Works' in data.activity_code_types
    assert 'Trade Design' in data.activity_code_types


def test_activities_carry_their_codes(tmp_path):
    p = tmp_path / "s.xer"
    p.write_text(SAMPLE, encoding='cp1252')
    data = parse_xer(str(p))
    a1 = data.activities['5001']['activity_codes']
    assert a1['Type of Works'] == 'Piles Works'
    assert a1['Trade Design'] == 'Civil'
    a2 = data.activities['5002']['activity_codes']
    assert a2['Type of Works'] == 'Columns Works'
    assert 'Trade Design' not in a2      # not assigned → absent
