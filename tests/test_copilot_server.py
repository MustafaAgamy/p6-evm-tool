"""HTTP contract tests for the AI Copilot V2 routes: /api/copilot/ask + /api/copilot/report.
Each test imports the schedule (creating a snapshot), then queries the offline engine. No
cloud, no Chrome (report tested with preview=True → HTML, not PDF).
"""
import http.client
import json


def _post(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read())


def _import(port, xml_path):
    _, data = _post(port, '/api/parse', {'path': str(xml_path), 'overrides_path': None})
    return data


def test_ask_answers_from_the_loaded_schedule(test_server, xml_path):
    imported = _import(test_server, xml_path)
    assert imported['ok'], imported
    sid = imported['snapshot_id']
    _, data = _post(test_server, '/api/copilot/ask',
                    {'snapshot_id': sid, 'question_id': 'health', 'mode': 'management'})
    assert data['ok'], data
    assert data['answer']['headline']                 # a real answer came back


def test_ask_resolves_a_typed_question(test_server, xml_path):
    sid = _import(test_server, xml_path)['snapshot_id']
    _, data = _post(test_server, '/api/copilot/ask',
                    {'snapshot_id': sid, 'question_text': 'can we claim an extension?', 'mode': 'management'})
    assert data['ok'], data
    assert data['matched'] is True and data['question_id'] == 'eot_likely'
    assert data['answer']['headline']


def test_ask_defers_gracefully_on_an_unknown_typed_question(test_server, xml_path):
    sid = _import(test_server, xml_path)['snapshot_id']
    _, data = _post(test_server, '/api/copilot/ask',
                    {'snapshot_id': sid, 'question_text': 'zzz qwerty foobar', 'mode': 'management'})
    assert data['ok'] and data['matched'] is False
    blob = (data['answer']['headline'] + ' ' + ' '.join(data['answer']['body'])).lower()
    assert "can't answer" in blob or 'premium' in blob


def test_planning_mode_answers_are_reachable_over_http(test_server, xml_path):
    sid = _import(test_server, xml_path)['snapshot_id']
    _, data = _post(test_server, '/api/copilot/ask',
                    {'snapshot_id': sid, 'question_id': 'delay_method', 'mode': 'planning'})
    assert data['ok'] and data['answer']['headline']
    assert "can't answer" not in data['answer']['headline'].lower()


def test_whatif_add_crew_needs_no_day_count(test_server, xml_path):
    _import(test_server, xml_path)
    _, data = _post(test_server, '/api/copilot/whatif',
                    {'xml_path': str(xml_path), 'kind': 'add_crew', 'activity_id': 'ACT002'})
    assert data['ok'], data
    assert 'impact_days' in data['result'] and data['result']['estimate'] is True


def test_report_preview_returns_manager_html(test_server, xml_path):
    sid = _import(test_server, xml_path)['snapshot_id']
    _, data = _post(test_server, '/api/copilot/report', {'snapshot_id': sid, 'preview': True})
    assert data['ok'], data
    assert '<html' in data['html'].lower() and 'Manager Report' in data['html']
    assert 'status' in data['report']


def test_report_preview_with_xml_parses_extras_without_crashing(test_server, xml_path):
    sid = _import(test_server, xml_path)['snapshot_id']
    _, data = _post(test_server, '/api/copilot/report',
                    {'snapshot_id': sid, 'preview': True, 'xml_path': str(xml_path)})
    assert data['ok'], data
    assert '<html' in data['html'].lower() and 'Manager Report' in data['html']


def test_copilot_needs_a_schedule(test_server):
    _, data = _post(test_server, '/api/copilot/ask', {'snapshot_id': None, 'question_id': 'health'})
    assert data['ok'] is False


def test_whatif_gives_an_instant_estimate_with_advice(test_server, xml_path):
    _import(test_server, xml_path)
    _, data = _post(test_server, '/api/copilot/whatif',
                    {'xml_path': str(xml_path), 'kind': 'delay', 'activity_id': 'ACT002', 'days': 5})
    assert data['ok'], data
    r = data['result']
    assert 'impact_days' in r and r['estimate'] is True and r['advice']


def test_whatif_shorten_needs_an_activity(test_server, xml_path):
    _import(test_server, xml_path)
    _, data = _post(test_server, '/api/copilot/whatif',
                    {'xml_path': str(xml_path), 'kind': 'shorten', 'activity_id': '', 'days': 5})
    assert data['ok'] is False


def test_scenario_shorten_builds_and_validates(test_server, xml_path, tmp_path):
    _import(test_server, xml_path)
    out = str(tmp_path / 'whatif.xml')
    _, bad = _post(test_server, '/api/copilot/scenario',
                   {'xml_path': str(xml_path), 'kind': 'shorten', 'activity_id': '', 'days': 5, 'output_path': out})
    assert bad['ok'] is False                       # a shorten needs an activity
    _, ok = _post(test_server, '/api/copilot/scenario',
                  {'xml_path': str(xml_path), 'kind': 'shorten', 'activity_id': 'ACT002', 'days': 5, 'output_path': out})
    assert ok['ok'], ok
    assert ok['activity_name'] == 'Activity Two'
