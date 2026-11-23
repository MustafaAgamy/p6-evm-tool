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
    <CurrentBaselineProjectObjectId>7</CurrentBaselineProjectObjectId>
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


def test_update_counts(test_server, tmp_path):
    path = _sample(tmp_path)
    _, data = _post_json(test_server, '/api/update/counts', {'xml_path': path})
    assert data['ok'] is True
    c = data['counts']
    assert c['total'] >= 1
    assert c['actual_completed'] + c['actual_in_progress'] + c['actual_not_started'] == c['total']
    # filter narrows to the Discipline=Civil subset
    _, f = _post_json(test_server, '/api/update/counts',
                      {'xml_path': path, 'code_filter': {'type': 'Discipline', 'value': 'Civil'}})
    assert f['ok'] is True and f['counts']['total'] >= 1


def test_update_scope(test_server, tmp_path):
    path = _sample(tmp_path)
    _, data = _post_json(test_server, '/api/update/scope', {'xml_path': path, 'types': ['Discipline']})
    assert data['ok'] is True, data
    scope = data['scope']
    assert scope['code_type'] == 'Discipline'
    rows = scope['rows']
    assert rows, data
    assert all('weight_pct' in r for r in rows)
    # the fixture's costed Civil activities are the whole cost-loaded scope
    assert any(r['value'] == 'Civil' for r in rows)


def test_update_analyze_missing_file(test_server):
    _, data = _post_json(test_server, '/api/update/analyze', {'xml_path': 'nope.xml'})
    assert data['ok'] is False and 'not' in data['error'].lower()


def test_update_analyze_no_baseline_advice_matches_help(test_server, tmp_path):
    """An XML exported WITHOUT its baseline project (and nothing attached) stops with code
    no_baseline — it is never measured against its own Planned dates. The advice must be what
    the tool truly accepts (SHELL-1): this route reads the baseline attached for the update
    (p6_evm.baseline), so the planner is told to attach the baseline (XER or XML), or re-export
    the XML with it — the same words Help shows (UPDATE_NO_BASELINE_ADVICE)."""
    src = open(_sample(tmp_path), encoding='utf-8').read()
    start, end = src.index('<BaselineProject>'), src.index('</BaselineProject>') + len('</BaselineProject>')
    p = tmp_path / 'update_no_baseline.xml'
    p.write_text(src[:start] + src[end:], encoding='utf-8')
    _, data = _post_json(test_server, '/api/update/analyze', {'xml_path': str(p)})
    assert data['ok'] is False and data['code'] == 'no_baseline', data
    assert data['report']['baseline_source'] == 'self'
    err = data['error']
    assert 'Attach the baseline (XER or XML)' in err and 'every feature' in err
    assert 'XML' in err and 'baseline' in err
    assert 'import the update as an XER' not in err


# ── Section 6 · Progress S-curve with earlier imported updates (2026-11-23) ──────────

def _update_xml(tmp_path, name, data_date, pct_a, pct_b):
    """The same job (same baseline 'BL R1' taken 01-Mar-2025) at another data date."""
    xml = (tmp_path / 'update.xml').read_text(encoding='utf-8') if (tmp_path / 'update.xml').exists() else None
    if xml is None:
        _sample(tmp_path)
        xml = (tmp_path / 'update.xml').read_text(encoding='utf-8')
    xml = (xml.replace('<DataDate>2025-04-01T00:00:00</DataDate>', f'<DataDate>{data_date}T00:00:00</DataDate>')
              .replace('<Id>S1</Id><Name>Soil a</Name>',
                       '<Id>S1</Id><Name>Soil a</Name><ActualStartDate>2025-03-02T00:00:00</ActualStartDate>')
              .replace('<PercentComplete>0.5</PercentComplete>', f'<PercentComplete>{pct_a}</PercentComplete>')
              .replace('<PercentComplete>0.3</PercentComplete>', f'<PercentComplete>{pct_b}</PercentComplete>')
              .replace('<BaselineProject>', '<BaselineProject><Name>BL R1</Name><DataDate>2025-03-01T00:00:00</DataDate>'))
    p = tmp_path / name
    p.write_text(xml, encoding='utf-8')
    return str(p)


def test_update_report_has_summary_and_scurve(test_server, tmp_path):
    path = _sample(tmp_path)
    _, data = _post_json(test_server, '/api/update/analyze', {'xml_path': path})
    r = data['report']
    assert [k['key'] for k in r['summary']['kpis']] == ['elapsed', 'planned', 'earned', 'spi', 'finish', 'delay']
    dd = [p for p in r['scurve']['points'] if p['kind'] == 'data_date'][0]
    assert dd['planned'] == r['time_status']['planned_pct'] and dd['earned'] == r['time_status']['actual_pct']


def test_scurve_puts_the_earlier_update_of_the_same_baseline_on_the_curve(test_server, tmp_path):
    early = _update_xml(tmp_path, 'up_march.xml', '2025-03-20', 0.2, 0.1)
    late = _update_xml(tmp_path, 'up_april.xml', '2025-04-01', 0.5, 0.3)
    _, a = _post_json(test_server, '/api/parse', {'path': early})
    _, b = _post_json(test_server, '/api/parse', {'path': late})
    assert a['ok'] and b['ok'], (a, b)
    sid = b['snapshot_id']
    _, d = _post_json(test_server, '/api/update/analyze', {'xml_path': late, 'snapshot_id': sid})
    sc = d['report']['scurve']
    ear = [e for e in sc['earlier'] if e['data_date'] == '2025-03-20']
    assert ear and ear[0]['auto'] and ear[0]['on'], sc['earlier']
    assert ear[0]['earned'] == 15.0                       # (0.2 + 0.1) / 2, equal budgets
    upd = [p for p in sc['points'] if p['kind'] == 'update']
    assert [(p['date'], p['earned']) for p in upd] == [('2025-03-20', 15.0)]

    # the planner unticks it: the point goes, the choice is kept for this update
    _, t = _post_json(test_server, '/api/update/scurve_earlier',
                      {'snapshot_id': sid, 'scurve': sc, 'pick': ear[0]['snapshot_id'], 'on': False})
    assert t['ok'], t
    assert not [p for p in t['scurve']['points'] if p['kind'] == 'update']
    assert t['picks']['remove'] == [ear[0]['snapshot_id']]
    _, d2 = _post_json(test_server, '/api/update/analyze', {'xml_path': late, 'snapshot_id': sid})
    assert not [p for p in d2['report']['scurve']['points'] if p['kind'] == 'update']
