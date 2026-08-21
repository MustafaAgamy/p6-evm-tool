"""Integration tests for /api/critpath/analyze against a real server + temp DB."""
import http.client
import json


def _post_json(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read())


def _schedule_xml(data_date, ms_finish, acts):
    """A P6 XML with a finish milestone and task activities carrying TotalFloatHours.
    acts: (oid, code, name, finish, total_float_hours)."""
    body = (f'<Activity><ObjectId>900</ObjectId><Id>M999</Id><Name>Project Completion</Name>'
            f'<Type>Finish Milestone</Type><WBSObjectId>100</WBSObjectId><CalendarObjectId></CalendarObjectId>'
            f'<RemainingEarlyFinishDate>{ms_finish}T00:00:00</RemainingEarlyFinishDate>'
            f'<TotalFloatHours>-80</TotalFloatHours></Activity>\n')
    for oid, code, name, finish, tf in acts:
        body += (f'<Activity><ObjectId>{oid}</ObjectId><Id>{code}</Id><Name>{name}</Name>'
                 f'<Type>Task Dependent</Type><WBSObjectId>100</WBSObjectId><CalendarObjectId></CalendarObjectId>'
                 f'<RemainingEarlyFinishDate>{finish}T00:00:00</RemainingEarlyFinishDate>'
                 f'<TotalFloatHours>{tf}</TotalFloatHours></Activity>\n')
    return ('<?xml version="1.0"?>\n<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">\n'
            f'  <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name><DataDate>{data_date}T00:00:00</DataDate>\n'
            '    <WBS><ObjectId>100</ObjectId><Name>Proj</Name><ParentObjectId></ParentObjectId></WBS>\n'
            f'{body}  </Project>\n</APIBusinessObjects>\n')


def _pair(tmp_path):
    # 8h/day → TotalFloatHours 80 = 10 wd, 40 = 5 wd, 0 = 0 wd, -24 = -3 wd
    prev = tmp_path / 'prev.xml'
    prev.write_text(_schedule_xml('2026-06-30', '2027-01-05', [
        (1, 'A050', 'Foundations', '2026-08-18', 120),   # safe (15 wd)
        (2, 'A100', 'Roof', '2026-09-05', 40),            # near (5 wd)
        (3, 'A200', 'MEP', '2026-11-01', 0)]),            # critical
        encoding='utf-8')
    curr = tmp_path / 'curr.xml'
    curr.write_text(_schedule_xml('2026-07-19', '2027-01-23', [
        (1, 'A050', 'Foundations', '2026-08-18', 120),   # safe
        (2, 'A100', 'Roof', '2026-09-05', 0),             # now critical
        (3, 'A200', 'MEP', '2026-11-20', -24)]),          # critical (-3 wd)
        encoding='utf-8')
    return str(prev), str(curr)


def test_critpath_two_updates(test_server, tmp_path):
    prev, curr = _pair(tmp_path)
    _, data = _post_json(test_server, '/api/critpath/analyze',
                         {'mode': 'two_updates', 'current_path': curr, 'previous_path': prev})
    assert data['ok'] is True, data
    r = data['report']
    assert r['mode'] == 'two_updates'
    assert set(r['roles']) == {'current', 'previous'}
    assert r['files']['current'] == 'curr.xml' and r['files']['previous'] == 'prev.xml'
    # current: A100 became critical, A200 critical → 2 critical, 0 near of 3
    assert r['census']['current']['critical'] == 2
    assert r['census']['current']['near'] == 0
    # previous: A200 critical → 1 critical, A100 near → 1 near
    assert r['census']['previous']['critical'] == 1
    assert r['census']['previous']['near'] == 1
    # CPLI present and < 1 (finish milestone TF -80h = -10 wd, behind)
    assert r['census']['current']['cpli'] is not None
    assert r['census']['current']['cpli'] < 1.0


def test_critpath_missing_previous(test_server, tmp_path):
    _, curr = _pair(tmp_path)
    _, data = _post_json(test_server, '/api/critpath/analyze',
                         {'mode': 'two_updates', 'current_path': curr})
    assert data['ok'] is False
    assert 'previous' in data['error'].lower()
