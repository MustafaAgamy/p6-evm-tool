"""HTTP contract tests for the AI Copilot claims routes.

/api/claims/activities · /api/claims/scenario · /api/claims/impact.
Each test gets a fresh server + temp DB (test_server fixture). No cloud/AI is
touched — Slice A is the deterministic TIA engine only.
"""
import http.client
import json


def _post(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read())


# ── /api/claims/activities ────────────────────────────────────────────────

def test_activities_lists_schedule_activities(test_server, xml_path):
    status, data = _post(test_server, '/api/claims/activities', {'xml_path': str(xml_path)})
    assert status == 200 and data['ok']
    ids = {a['id'] for a in data['activities']}
    assert {'ACT001', 'ACT002'} <= ids
    assert all('name' in a and 'wbs_path' in a for a in data['activities'])


def test_activities_missing_schedule_errors(test_server):
    _, data = _post(test_server, '/api/claims/activities', {'xml_path': 'does-not-exist.xml'})
    assert data['ok'] is False


# ── /api/claims/scenario ──────────────────────────────────────────────────

def test_scenario_writes_impacted_xml(test_server, xml_path, tmp_path):
    out = tmp_path / 'impacted.xml'
    _, data = _post(test_server, '/api/claims/scenario', {
        'xml_path': str(xml_path), 'activity_id': 'ACT002', 'delay_days': 10,
        'output_path': str(out), 'label': 'Delay: late access (10 wd)'})
    assert data['ok'], data
    assert out.exists()
    text = out.read_text(encoding='utf-8')
    assert data['delay_id'] in text
    assert 'Finish to Start' in text            # the driving link was written
    assert data['activity_name'] == 'Activity Two'


def test_scenario_requires_activity_and_positive_delay(test_server, xml_path, tmp_path):
    out = str(tmp_path / 'x.xml')
    _, d1 = _post(test_server, '/api/claims/scenario',
                  {'xml_path': str(xml_path), 'activity_id': '', 'delay_days': 5, 'output_path': out})
    assert d1['ok'] is False
    _, d2 = _post(test_server, '/api/claims/scenario',
                  {'xml_path': str(xml_path), 'activity_id': 'ACT002', 'delay_days': 0, 'output_path': out})
    assert d2['ok'] is False


def test_scenario_unknown_activity_errors(test_server, xml_path, tmp_path):
    _, data = _post(test_server, '/api/claims/scenario', {
        'xml_path': str(xml_path), 'activity_id': 'ZZZ999', 'delay_days': 5,
        'output_path': str(tmp_path / 'y.xml')})
    assert data['ok'] is False


# ── /api/claims/impact ────────────────────────────────────────────────────

def _prog(path, finish):
    path.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<APIBusinessObjects>
  <Calendar><ObjectId>CAL1</ObjectId><Name>7-day</Name></Calendar>
  <Project><ObjectId>1</ObjectId><Id>PRJ</Id><Name>P</Name>
    <DataDate>2026-01-01T00:00:00</DataDate>
    <Activity><ObjectId>OFM</ObjectId><Id>FIN</Id><Name>Complete</Name>
      <Type>Finish Milestone</Type><Status>Not Started</Status>
      <CalendarObjectId>CAL1</CalendarObjectId><PercentComplete>0</PercentComplete>
      <PlannedDuration>0</PlannedDuration>
      <PlannedStartDate>{finish}</PlannedStartDate><PlannedFinishDate>{finish}</PlannedFinishDate>
    </Activity></Project>
</APIBusinessObjects>''', encoding='utf-8')
    return str(path)


def test_impact_reads_completion_movement(test_server, tmp_path):
    base = _prog(tmp_path / 'base.xml', '2026-02-28T00:00:00')
    resched = _prog(tmp_path / 'resched.xml', '2026-03-14T00:00:00')
    _, data = _post(test_server, '/api/claims/impact',
                    {'xml_path': base, 'rescheduled_path': resched})
    assert data['ok'], data
    assert data['impact']['impact_days'] == 14
    assert data['impact']['milestone_id'] == 'FIN'


def test_impact_requires_rescheduled_file(test_server, xml_path):
    _, data = _post(test_server, '/api/claims/impact',
                    {'xml_path': str(xml_path), 'rescheduled_path': ''})
    assert data['ok'] is False
