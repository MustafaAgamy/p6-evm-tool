"""Integration tests for the /api/update/* routes (Update Analysis) against a real
server + temp DB. No Chrome; the PDF route is exercised in preview mode only."""
import http.client
import json


def _post_json(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read())


def _sample(tmp_path):
    """A costed P6 update XML with a baseline, one Discipline code, and a finish milestone
    driven by two soil activities under Silo 1 → Soil Replacement."""
    xml = '''<?xml version="1.0"?>
<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
  <ActivityCodeType><ObjectId>901</ObjectId><Name>Discipline</Name></ActivityCodeType>
  <ActivityCode><ObjectId>902</ObjectId><CodeValue>Civil</CodeValue><CodeTypeObjectId>901</CodeTypeObjectId></ActivityCode>
  <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name><DataDate>2025-04-01T00:00:00</DataDate>
    <WBS><ObjectId>100</ObjectId><Name>Proj</Name><ParentObjectId></ParentObjectId></WBS>
    <WBS><ObjectId>200</ObjectId><Name>Silo 1</Name><ParentObjectId>100</ParentObjectId></WBS>
    <WBS><ObjectId>301</ObjectId><Name>Soil Replacement</Name><ParentObjectId>200</ParentObjectId></WBS>
    <Activity><ObjectId>20</ObjectId><Id>S1</Id><Name>Soil a</Name><Type>Task Dependent</Type>
      <WBSObjectId>301</WBSObjectId><CalendarObjectId></CalendarObjectId><PercentComplete>0.5</PercentComplete>
      <PlannedDuration>320</PlannedDuration><RemainingDuration>160</RemainingDuration>
      <RemainingEarlyStartDate>2025-03-02T00:00:00</RemainingEarlyStartDate>
      <RemainingEarlyFinishDate>2025-06-01T00:00:00</RemainingEarlyFinishDate>
      <Code><TypeObjectId>901</TypeObjectId><ValueObjectId>902</ValueObjectId></Code></Activity>
    <Activity><ObjectId>21</ObjectId><Id>S2</Id><Name>Soil b</Name><Type>Task Dependent</Type>
      <WBSObjectId>301</WBSObjectId><CalendarObjectId></CalendarObjectId><PercentComplete>0.3</PercentComplete>
      <PlannedDuration>320</PlannedDuration><RemainingDuration>224</RemainingDuration>
      <RemainingEarlyStartDate>2025-03-02T00:00:00</RemainingEarlyStartDate>
      <RemainingEarlyFinishDate>2025-06-01T00:00:00</RemainingEarlyFinishDate>
      <Code><TypeObjectId>901</TypeObjectId><ValueObjectId>902</ValueObjectId></Code></Activity>
    <Activity><ObjectId>999</ObjectId><Id>MS</Id><Name>Project completion</Name><Type>Finish Milestone</Type>
      <WBSObjectId>200</WBSObjectId><CalendarObjectId></CalendarObjectId><PercentComplete>0</PercentComplete>
      <PlannedDuration>0</PlannedDuration><RemainingDuration>0</RemainingDuration>
      <RemainingEarlyStartDate>2025-06-01T00:00:00</RemainingEarlyStartDate>
      <RemainingEarlyFinishDate>2025-06-01T00:00:00</RemainingEarlyFinishDate></Activity>
    <Relationship><PredecessorActivityObjectId>20</PredecessorActivityObjectId><SuccessorActivityObjectId>999</SuccessorActivityObjectId><Type>Finish to Start</Type><Lag>0</Lag></Relationship>
    <ResourceAssignment><ActivityObjectId>20</ActivityObjectId><PlannedCost>32000</PlannedCost></ResourceAssignment>
    <ResourceAssignment><ActivityObjectId>21</ActivityObjectId><PlannedCost>32000</PlannedCost></ResourceAssignment>
  </Project>
  <BaselineProject>
    <Activity><ObjectId>1020</ObjectId><Id>S1</Id><PlannedStartDate>2025-03-02T00:00:00</PlannedStartDate><PlannedFinishDate>2025-06-01T00:00:00</PlannedFinishDate></Activity>
    <Activity><ObjectId>1021</ObjectId><Id>S2</Id><PlannedStartDate>2025-03-02T00:00:00</PlannedStartDate><PlannedFinishDate>2025-06-01T00:00:00</PlannedFinishDate></Activity>
    <Activity><ObjectId>1999</ObjectId><Id>MS</Id><PlannedFinishDate>2025-06-01T00:00:00</PlannedFinishDate></Activity>
  </BaselineProject>
</APIBusinessObjects>
'''
    p = tmp_path / 'update.xml'
    p.write_text(xml, encoding='utf-8')
    return str(p)


def test_update_analyze_end_to_end(test_server, tmp_path):
    path = _sample(tmp_path)
    _, data = _post_json(test_server, '/api/update/analyze', {'xml_path': path})
    assert data['ok'] is True, data
    r = data['report']
    assert r['has_baseline'] is True
    ts = r['time_status']
    assert ts['actual_pct'] is not None and ts['planned_pct'] is not None
    assert 'Discipline' in r['by_code']
    cp = r['critical_path']
    assert cp['milestone']['name'] == 'Project completion'
    assert cp['charts'], 'expected a driving-path chart'


def test_update_report_preview_and_excel(test_server, tmp_path):
    path = _sample(tmp_path)
    _, data = _post_json(test_server, '/api/update/analyze', {'xml_path': path})
    report = data['report']
    _, prev = _post_json(test_server, '/api/update/report', {'report': report, 'preview': True})
    assert prev['ok'] is True
    assert '<h1>Update Analysis</h1>' in prev['html']
    out = tmp_path / 'out.xlsx'
    _, xl = _post_json(test_server, '/api/update/excel', {'report': report, 'output_path': str(out)})
    assert xl['ok'] is True
    assert out.exists() and out.stat().st_size > 0


def test_update_bycode_combined(test_server, tmp_path):
    path = _sample(tmp_path)
    _, data = _post_json(test_server, '/api/update/bycode',
                         {'xml_path': path, 'types': ['Discipline']})
    assert data['ok'] is True
    assert any(row['value'] == 'Civil' for row in data['rows'])


def test_update_analyze_missing_file(test_server):
    _, data = _post_json(test_server, '/api/update/analyze', {'xml_path': 'nope.xml'})
    assert data['ok'] is False and 'not' in data['error'].lower()
