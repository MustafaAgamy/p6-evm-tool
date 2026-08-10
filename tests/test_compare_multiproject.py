"""Multi-project: the Consultant Review comparison reads ALL projects so a successor
that lives in another project of a program export isn't dropped (which showed up as
predecessors present but successors blank). Default parse still reads one project."""
import textwrap
from p6_evm.parser import parse_file
from p6_evm.xer import parse_xer


_XER = (
    "ERMHDR\t19.12\n"
    "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n"
    "%R\t1\tP1\t2026-01-01 00:00\n%R\t2\tP2\t2026-01-01 00:00\n"
    "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\n%R\t10\t5-Day\t8\n"
    "%T\tPROJWBS\n%F\twbs_id\twbs_name\tparent_wbs_id\tproj_node_flag\tproj_id\n"
    "%R\t100\tProj1\t\tY\t1\n%R\t200\tProj2\t\tY\t2\n"
    "%T\tTASK\n%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_type\ttask_code\ttask_name\n"
    "%R\t1001\t1\t100\t10\tTT_Task\tA1\tActA1\n%R\t2001\t2\t200\t10\tTT_Task\tA2\tActA2\n"
    "%T\tTASKPRED\n%F\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt\n%R\t2001\t1001\tPR_FS\t0\n"
    "%E\n"
)


def test_xer_all_projects_keeps_cross_project_link(tmp_path):
    p = tmp_path / "prog.xer"
    p.write_text(_XER, encoding='cp1252')
    d1 = parse_xer(str(p))                        # default: first project only
    assert {a['id'] for a in d1.activities.values()} == {'A1'}
    assert d1.relationships == []                 # cross-project link dropped
    d2 = parse_xer(str(p), all_projects=True)     # all projects
    assert {a['id'] for a in d2.activities.values()} == {'A1', 'A2'}
    assert [(r['pred_id'], r['succ_id']) for r in d2.relationships] == [('1001', '2001')]


_XML = textwrap.dedent('''\
<?xml version="1.0"?>
<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
  <Project>
    <ObjectId>1</ObjectId><Id>P1</Id><Name>Proj1</Name><DataDate>2026-01-01T00:00:00</DataDate>
    <Activity><ObjectId>1001</ObjectId><Id>A1</Id><Name>ActA1</Name><Type>Task Dependent</Type></Activity>
  </Project>
  <Project>
    <ObjectId>2</ObjectId><Id>P2</Id><Name>Proj2</Name><DataDate>2026-01-01T00:00:00</DataDate>
    <Activity><ObjectId>2001</ObjectId><Id>A2</Id><Name>ActA2</Name><Type>Task Dependent</Type></Activity>
    <Relationship>
      <PredecessorActivityObjectId>1001</PredecessorActivityObjectId>
      <SuccessorActivityObjectId>2001</SuccessorActivityObjectId>
      <Type>Finish to Start</Type><Lag>0</Lag>
    </Relationship>
  </Project>
</APIBusinessObjects>
''')


def test_xml_all_projects_keeps_cross_project_link(tmp_path):
    p = tmp_path / "prog.xml"
    p.write_text(_XML, encoding='utf-8')
    d1 = parse_file(str(p))                        # default: first project only
    assert {a['id'] for a in d1.activities.values()} == {'A1'}
    assert d1.relationships == []
    d2 = parse_file(str(p), all_projects=True)     # all projects
    assert {a['id'] for a in d2.activities.values()} == {'A1', 'A2'}
    assert [(r['pred_id'], r['succ_id']) for r in d2.relationships] == [('1001', '2001')]
