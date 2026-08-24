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
    """A P6 XML with a finish milestone, task activities each in their OWN WBS work front,
    and Relationships chaining them into a driving path to the milestone — so the driving-
    path trace (the centre of the feature) is exercised from a REAL parse, not a hand-built
    ScheduleData. acts: (oid, code, name, finish, total_float_hours, start)."""
    wbs = ('    <WBS><ObjectId>100</ObjectId><Name>Project</Name><ParentObjectId></ParentObjectId></WBS>\n')
    body = (f'<Activity><ObjectId>900</ObjectId><Id>M999</Id><Name>Project Completion</Name>'
            f'<Type>Finish Milestone</Type><WBSObjectId>100</WBSObjectId><CalendarObjectId></CalendarObjectId>'
            f'<RemainingEarlyStartDate>{ms_finish}T00:00:00</RemainingEarlyStartDate>'
            f'<RemainingEarlyFinishDate>{ms_finish}T00:00:00</RemainingEarlyFinishDate>'
            f'<TotalFloatHours>-80</TotalFloatHours></Activity>\n')
    rels, prev = '', None
    for oid, code, name, finish, tf, start in acts:
        wid = 200 + oid
        wbs += f'    <WBS><ObjectId>{wid}</ObjectId><Name>{name}</Name><ParentObjectId>100</ParentObjectId></WBS>\n'
        body += (f'<Activity><ObjectId>{oid}</ObjectId><Id>{code}</Id><Name>{name} work</Name>'
                 f'<Type>Task Dependent</Type><WBSObjectId>{wid}</WBSObjectId><CalendarObjectId></CalendarObjectId>'
                 f'<RemainingEarlyStartDate>{start}T00:00:00</RemainingEarlyStartDate>'
                 f'<RemainingEarlyFinishDate>{finish}T00:00:00</RemainingEarlyFinishDate>'
                 f'<TotalFloatHours>{tf}</TotalFloatHours></Activity>\n')
        if prev is not None:
            rels += (f'<Relationship><PredecessorActivityObjectId>{prev}</PredecessorActivityObjectId>'
                     f'<SuccessorActivityObjectId>{oid}</SuccessorActivityObjectId><Type>Finish to Start</Type><Lag>0</Lag></Relationship>\n')
        prev = oid
    rels += (f'<Relationship><PredecessorActivityObjectId>{prev}</PredecessorActivityObjectId>'
             f'<SuccessorActivityObjectId>900</SuccessorActivityObjectId><Type>Finish to Start</Type><Lag>0</Lag></Relationship>\n')
    return ('<?xml version="1.0"?>\n<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">\n'
            f'  <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name><DataDate>{data_date}T00:00:00</DataDate>\n'
            f'{wbs}{body}{rels}  </Project>\n</APIBusinessObjects>\n')


def _pair(tmp_path):
    # 8h/day → TotalFloatHours 120 = 15 wd (safe), 40 = 5 wd (near), 0 = crit, -24 = -3 wd (crit).
    # prev path runs through Roof; curr path reroutes through MEP → Roof leaves, MEP enters.
    prev = tmp_path / 'prev.xml'
    prev.write_text(_schedule_xml('2026-06-30', '2027-01-05', [
        (1, 'A050', 'Foundations', '2026-08-18', 120, '2026-06-01'),   # safe (15 wd)
        (2, 'A100', 'Roof', '2026-09-05', 40, '2026-08-18'),           # near (5 wd)
        (4, 'A400', 'Fit-out', '2026-11-01', 0, '2026-09-05')]),       # critical
        encoding='utf-8')
    curr = tmp_path / 'curr.xml'
    curr.write_text(_schedule_xml('2026-07-19', '2027-01-23', [
        (1, 'A050', 'Foundations', '2026-08-18', 120, '2026-07-19'),   # safe
        (3, 'A300', 'MEP', '2026-11-20', 0, '2026-08-18'),             # critical — the reroute
        (4, 'A400', 'Fit-out', '2026-12-20', -24, '2026-11-20')]),     # critical (-3 wd)
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
    # Driving-path lanes populated from a REAL parse (not synthetic ScheduleData), and the
    # reroute is detected: MEP entered the current path, Roof left it.
    cur_lane = next(l for l in r['lanes'] if l['role'] == 'current')
    assert cur_lane['boxes'], 'current lane should have work-front boxes from the parsed chain'
    states = {b['name']: b['state'] for b in cur_lane['boxes']}
    assert states.get('MEP') == 'new'
    assert states.get('Roof') == 'left'


def test_critpath_missing_previous(test_server, tmp_path):
    _, curr = _pair(tmp_path)
    _, data = _post_json(test_server, '/api/critpath/analyze',
                         {'mode': 'two_updates', 'current_path': curr})
    assert data['ok'] is False
    assert 'previous' in data['error'].lower()


def test_critpath_report_preview_and_excel(test_server, tmp_path):
    prev, curr = _pair(tmp_path)
    _, ana = _post_json(test_server, '/api/critpath/analyze',
                        {'mode': 'two_updates', 'current_path': curr, 'previous_path': prev})
    assert ana['ok'] is True
    report = ana['report']
    # PDF preview returns HTML with the section markers
    _, prev_resp = _post_json(test_server, '/api/critpath/report', {'report': report, 'preview': True})
    assert prev_resp['ok'] is True
    assert 'data-sec="dashboard"' in prev_resp['html']
    assert 'data-sec="driving_path"' in prev_resp['html']
    # Excel export writes a real workbook
    out = tmp_path / 'cpa.xlsx'
    _, xl = _post_json(test_server, '/api/critpath/excel', {'report': report, 'output_path': str(out)})
    assert xl['ok'] is True
    assert out.exists() and out.stat().st_size > 0
