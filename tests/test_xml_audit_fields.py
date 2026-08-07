import textwrap
from datetime import datetime
from p6_evm.parser import parse_file


def _xml(tmp_path):
    content = textwrap.dedent('''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Project>
        <ObjectId>1</ObjectId><Id>T33</Id><Name>Tower 33</Name>
        <DataDate>2026-07-24T00:00:00</DataDate>
        <WBS><ObjectId>10</ObjectId><Name>Structure</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity>
          <ObjectId>1001</ObjectId><Id>A230</Id><Name>Roof Steel</Name>
          <Type>Task Dependent</Type><Status>In Progress</Status>
          <WBSObjectId>10</WBSObjectId><CalendarObjectId></CalendarObjectId>
          <PercentComplete>40</PercentComplete>
          <ActualStartDate>2026-07-20T08:00:00</ActualStartDate>
        </Activity>
        <Activity>
          <ObjectId>1002</ObjectId><Id>A240</Id><Name>Roof Cladding</Name>
          <Type>Task Dependent</Type><Status>Not Started</Status>
          <WBSObjectId>10</WBSObjectId><CalendarObjectId></CalendarObjectId>
          <PercentComplete>0</PercentComplete>
        </Activity>
        <Relationship>
          <PredecessorActivityObjectId>1001</PredecessorActivityObjectId>
          <SuccessorActivityObjectId>1002</SuccessorActivityObjectId>
          <Type>Finish to Start</Type><Lag>0</Lag>
        </Relationship>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / "s.xml"; p.write_text(content, encoding='utf-8')
    return str(p)


def test_xml_relationships_and_type(tmp_path):
    data = parse_file(_xml(tmp_path))
    assert data.relationships == [
        {'pred_id': '1001', 'succ_id': '1002', 'type': 'FS', 'lag_days': 0.0}
    ]
    assert data.activities['1001']['task_type'] == 'Task'
    assert data.activities['1002']['wbs_path'] == 'Structure'


def test_xml_actual_dates_parsed(tmp_path):
    data = parse_file(_xml(tmp_path))
    # 1001 has an ActualStartDate and no ActualFinishDate; 1002 has neither
    assert data.activities['1001']['actual_start'] == datetime(2026, 7, 20, 8, 0, 0)
    assert data.activities['1001']['actual_finish'] is None
    assert data.activities['1002']['actual_start'] is None
