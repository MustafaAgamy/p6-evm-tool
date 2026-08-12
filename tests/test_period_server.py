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
    """A P6 update XML with a BaselineProject (like a real export), so metrics.compute
    yields a real planned/actual %. acts: (oid, code, name, pct(0-1), finish, dur_hr, start)."""
    body, baseline, ras = '', '', ''
    for oid, code, name, pct, finish, dur, start in acts:
        body += (f'<Activity><ObjectId>{oid}</ObjectId><Id>{code}</Id><Name>{name}</Name>'
                 f'<Type>Task Dependent</Type><WBSObjectId>100</WBSObjectId><CalendarObjectId></CalendarObjectId>'
                 f'<PercentComplete>{pct}</PercentComplete>'
                 f'<PlannedDuration>{dur}</PlannedDuration><RemainingDuration>{dur}</RemainingDuration>'
                 f'<RemainingEarlyStartDate>{start}T00:00:00</RemainingEarlyStartDate>'
                 f'<RemainingEarlyFinishDate>{finish}T00:00:00</RemainingEarlyFinishDate></Activity>\n')
        # baseline carries each activity's planned dates so planned_pct (and thus actual %) exists
        baseline += (f'<Activity><ObjectId>{oid + 100}</ObjectId><Id>{code}</Id>'
                     f'<PlannedStartDate>{start}T00:00:00</PlannedStartDate>'
                     f'<PlannedFinishDate>{finish}T00:00:00</PlannedFinishDate></Activity>\n')
        # cost-load the activity so its phase carries weight (a real schedule is cost-loaded;
        # an uncosted lone WBS gets weight 0 → overall % 0, which would hide the actual-% path)
        ras += (f'<ResourceAssignment><ActivityObjectId>{oid}</ActivityObjectId>'
                f'<PlannedCost>{dur * 100}</PlannedCost></ResourceAssignment>\n')
    return ('<?xml version="1.0"?>\n<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">\n'
            f'  <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name><DataDate>{data_date}T00:00:00</DataDate>\n'
            '    <WBS><ObjectId>100</ObjectId><Name>Proj</Name><ParentObjectId></ParentObjectId></WBS>\n'
            f'{body}{ras}  </Project>\n'
            f'  <BaselineProject>\n{baseline}  </BaselineProject>\n</APIBusinessObjects>\n')


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
    # Option-B numbers are sane on real parse+compute (not just "it ran"):
    s = r['summary']
    assert s['actual_now'] > s['actual_prev'] > 0            # progress moved forward, 0-100 scale
    assert s['period_earned'] == round(s['actual_now'] - s['actual_prev'], 1)
    assert s['period_forecast'] > 0                          # previous update scheduled work this window
    assert s['forecast_achievement'] is not None             # earned / forecast, finite
    assert 0 <= s['actual_now'] <= 100 and 0 <= s['forecast_at_now'] <= 100
    # SPI trend flows end-to-end (both cutoffs have planned work), variance = curr − prev
    assert s['prev_spi'] is not None and s['curr_spi'] is not None
    assert s['spi_variance'] == round(s['curr_spi'] - s['prev_spi'], 2)
    # Critical-path timeline (Option A): the driving path from a REAL parse carries the ISO
    # dates the timeline places on its axis — and they survive the JSON round-trip (strings,
    # not datetimes). Then the real report renders the timeline without error.
    cp = r['critical_path']
    assert cp['current'] and all(isinstance(a.get('start'), (str, type(None))) for a in cp['current'])
    assert any(a.get('finish') for a in cp['current'])       # at least one dated activity on the path
    from p6_period.exporters import render_html
    html = render_html(r)
    assert 'Critical path timeline' in html                  # timeline renders from a REAL parsed report


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
