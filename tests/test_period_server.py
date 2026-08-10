"""Integration tests for the /api/period/* routes (Update vs Update) against a real
server + temp DB. No Chrome; the PDF route is exercised elsewhere."""
import http.client
import json


def _post_json(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read())


def _update_xml(data_date, acts):
    """acts: list of (oid, code, name, pct(0-1), finish_iso, dur_hr, start_iso)."""
    body = ''
    for oid, code, name, pct, finish, dur, start in acts:
        body += (f'<Activity><ObjectId>{oid}</ObjectId><Id>{code}</Id><Name>{name}</Name>'
                 f'<Type>Task Dependent</Type><WBSObjectId>100</WBSObjectId><CalendarObjectId></CalendarObjectId>'
                 f'<PercentComplete>{pct}</PercentComplete>'
                 f'<PlannedDuration>{dur}</PlannedDuration><RemainingDuration>{dur}</RemainingDuration>'
                 f'<RemainingEarlyStartDate>{start}T00:00:00</RemainingEarlyStartDate>'
                 f'<RemainingEarlyFinishDate>{finish}T00:00:00</RemainingEarlyFinishDate></Activity>\n')
    return ('<?xml version="1.0"?>\n<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">\n'
            f'  <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name><DataDate>{data_date}T00:00:00</DataDate>\n'
            '    <WBS><ObjectId>100</ObjectId><Name>Proj</Name><ParentObjectId></ParentObjectId></WBS>\n'
            f'{body}  </Project>\n</APIBusinessObjects>\n')


def _pair(tmp_path):
    prev = tmp_path / 'prev.xml'
    prev.write_text(_update_xml('2026-06-30', [
        (1, 'A050', 'Clearance', 0.5, '2026-08-18', 40, '2026-06-01'),
        (2, 'A100', 'Excavate', 0.1, '2026-09-05', 80, '2026-06-01')]), encoding='utf-8')
    curr = tmp_path / 'curr.xml'
    curr.write_text(_update_xml('2026-07-31', [
        (1, 'A050', 'Clearance', 0.6, '2026-09-01', 40, '2026-07-01'),
        (2, 'A100', 'Excavate', 0.22, '2026-09-05', 80, '2026-07-01')]), encoding='utf-8')
    return str(prev), str(curr)


def test_period_compare_end_to_end(test_server, tmp_path):
    prev, curr = _pair(tmp_path)
    _, data = _post_json(test_server, '/api/period/compare', {'prev_path': prev, 'update_path': curr})
    assert data['ok'] is True
    r = data['report']
    assert r['prev_file'] == 'prev.xml' and r['update_file'] == 'curr.xml'
    assert r['matched_activities'] == 2
    # A100 gained +12%, A050 +10% → biggest first
    assert [row['activity_id'] for row in r['progress']['rows']] == ['A100', 'A050']
    assert r['progress']['rows'][0]['variance'] == 12.0
    for key in ('summary', 'scurve', 'critical_movement', 'buckets', 'conclusion'):
        assert key in r


def test_period_compare_missing_prev(test_server):
    _, data = _post_json(test_server, '/api/period/compare',
                         {'prev_path': 'nope.xml', 'update_path': 'nope.xml'})
    assert data['ok'] is False and 'not' in data['error'].lower()


def test_period_previous_suggests_prior_snapshot(test_server, tmp_path):
    prev, curr = _pair(tmp_path)
    _, d1 = _post_json(test_server, '/api/parse', {'path': prev})
    _, d2 = _post_json(test_server, '/api/parse', {'path': curr})
    assert d1['ok'] and d2['ok']
    _, data = _post_json(test_server, '/api/period/previous', {'snapshot_id': d2['snapshot_id']})
    assert data['ok'] and data['previous'] and data['previous']['snapshot_id'] == d1['snapshot_id']


def test_period_excel_writes_file(test_server, tmp_path):
    out = tmp_path / 'progress.xlsx'
    report = {'progress': {'rows': [
        {'activity_id': 'A1', 'activity_name': 'x', 'prev_pct': 10, 'curr_pct': 20,
         'variance': 10, 'finished': False, 'started': False, 'reversal': False}]}}
    _, data = _post_json(test_server, '/api/period/excel', {'report': report, 'output_path': str(out)})
    assert data['ok'] is True and out.exists() and out.stat().st_size > 0
