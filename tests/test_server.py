"""Tests for server.py — HTTP API contract.

Each test gets a fresh server backed by its own temp DB (test_server fixture
from conftest.py). No browser/Chrome needed; /api/report is excluded.
"""
import http.client
import json

import pytest


# ── HTTP helpers ──────────────────────────────────────────────────────────

def _get(port, path):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    conn.request('GET', path)
    resp = conn.getresponse()
    body = resp.read()
    return resp.status, resp.getheader('Content-Type', ''), body

def _post_json(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    data = json.dumps(payload).encode()
    conn.request('POST', path, body=data, headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    body = resp.read()
    return resp.status, json.loads(body)


# ── POST /api/compare (Consultant Review — Baseline vs Update) ─────────────

_BASELINE_XER = (
    "ERMHDR\t19.12\n"
    "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t1\tP1\t2026-02-09 00:00\n"
    "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\n%R\t10\t8hr\t8\n"
    "%T\tPROJWBS\n%F\twbs_id\twbs_name\tparent_wbs_id\tproj_node_flag\n%R\t100\tProj\t\tY\n"
    "%T\tTASK\n%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_type\ttask_code\ttask_name"
    "\ttarget_drtn_hr_cnt\tremain_drtn_hr_cnt\trestart_date\treend_date\n"
    "%R\t1\t1\t100\t10\tTT_Task\tA050\tClearance\t40\t40\t2026-01-05 00:00\t2026-01-10 00:00\n"
    "%R\t2\t1\t100\t10\tTT_Task\tA100\tExcavate\t80\t80\t2026-01-10 00:00\t2026-01-18 00:00\n"
    "%T\tTASKPRED\n%F\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt\n%R\t2\t1\tPR_FS\t0\n"
    "%E\n"
)

_UPDATE_XML = (
    '<?xml version="1.0"?>\n'
    '<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">\n'
    '  <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name>'
    '<DataDate>2026-02-09T00:00:00</DataDate>\n'
    '    <WBS><ObjectId>100</ObjectId><Name>Proj</Name><ParentObjectId></ParentObjectId></WBS>\n'
    '    <Activity><ObjectId>1</ObjectId><Id>A050</Id><Name>Clearance</Name>'
    '<Type>Task Dependent</Type><WBSObjectId>100</WBSObjectId><CalendarObjectId></CalendarObjectId>'
    '<RemainingEarlyFinishDate>2026-01-10T00:00:00</RemainingEarlyFinishDate></Activity>\n'
    '    <Activity><ObjectId>2</ObjectId><Id>A100</Id><Name>Excavate</Name>'
    '<Type>Task Dependent</Type><WBSObjectId>100</WBSObjectId><CalendarObjectId></CalendarObjectId>'
    '<PlannedDuration>120</PlannedDuration><RemainingDuration>120</RemainingDuration>'
    '<RemainingEarlyStartDate>2026-01-20T00:00:00</RemainingEarlyStartDate></Activity>\n'
    '    <Relationship><PredecessorActivityObjectId>1</PredecessorActivityObjectId>'
    '<SuccessorActivityObjectId>2</SuccessorActivityObjectId><Type>Finish to Start</Type>'
    '<Lag>80</Lag></Relationship>\n'
    '  </Project>\n</APIBusinessObjects>\n'
)


def _write_pair(tmp_path):
    b = tmp_path / "baseline.xer"; b.write_text(_BASELINE_XER, encoding='cp1252')
    u = tmp_path / "update.xml"; u.write_text(_UPDATE_XML, encoding='utf-8')
    return str(b), str(u)


def test_compare_missing_files_returns_error(test_server):
    _, data = _post_json(test_server, '/api/compare',
                         {'baseline_path': 'nope.xer', 'update_path': 'nope.xml'})
    assert data['ok'] is False and 'not found' in data['error'].lower()


def test_compare_detects_lag_change_across_xer_and_xml(test_server, tmp_path):
    b, u = _write_pair(tmp_path)
    _, data = _post_json(test_server, '/api/compare', {'baseline_path': b, 'update_path': u})
    assert data['ok'] is True
    r = data['report']
    assert r['baseline_file'] == 'baseline.xer' and r['update_file'] == 'update.xml'
    # A050 -> A100 lag went FS+0 -> FS+10 — shown on BOTH ends (all relationships per activity)
    assert [row['activity_id'] for row in r['logic']['rows']] == ['A050', 'A100']
    assert r['logic']['summary']['by_kind'] == {'lag': 2}
    # Duration path end-to-end across XER (remain_drtn_hr_cnt) + XML (RemainingDuration):
    # A100 original 80h/8=10d in baseline, 120h/8=15d in update → extended.
    dur = {row['activity_id']: row for row in r['durations']['rows']}
    assert dur['A100']['status'] == 'extended'
    assert dur['A100']['baseline_orig_days'] == 10.0 and dur['A100']['update_orig_days'] == 15.0


def test_compare_report_pdf_route_runs_without_reschedule(test_server, tmp_path, monkeypatch):
    """Regression: _handle_compare_report used tempfile/subprocess without importing them,
    so the Consultant Review PDF always failed with a NameError — regardless of any
    reschedule. Mock Chrome so the full route (tempfile → subprocess) runs end to end."""
    import server
    ran = {}
    monkeypatch.setattr(server, '_find_chrome', lambda: 'chrome-stub')
    monkeypatch.setattr(server.subprocess, 'run', lambda *a, **k: ran.update(ok=True))
    out = str(tmp_path / 'consultant_review.pdf')
    report = {'baseline_file': 'b.xer', 'update_file': 'u.xml',
              'dashboard': {'changed_activities': 0, 'logic_changed': 0, 'duration_only': 0,
                            'finish_slip_days': None},
              'change_summary': {'items': []}, 'logic': {'rows': []}, 'durations': {'rows': []}}
    _, data = _post_json(test_server, '/api/compare/report',
                         {'report': report, 'impact': None, 'output_path': out})
    assert data['ok'] is True and ran.get('ok')     # route completed — no NameError, no reschedule needed


# ── GET / ─────────────────────────────────────────────────────────────────

def test_index_returns_200(test_server):
    status, ct, _ = _get(test_server, '/')
    assert status == 200

def test_index_content_type_html(test_server):
    _, ct, _ = _get(test_server, '/')
    assert 'text/html' in ct

def test_index_injects_server_port(test_server):
    _, _, body = _get(test_server, '/')
    assert f'window.__SERVER_PORT__ = {test_server}'.encode() in body


# ── GET /ui/* ─────────────────────────────────────────────────────────────

def test_serve_css(test_server):
    status, ct, _ = _get(test_server, '/ui/style.css')
    assert status == 200
    assert 'text/css' in ct

def test_serve_js_module(test_server):
    status, ct, _ = _get(test_server, '/ui/app.js')
    assert status == 200
    assert 'javascript' in ct

def test_serve_missing_static_returns_404(test_server):
    status, _, _ = _get(test_server, '/ui/nonexistent_file.js')
    assert status == 404


# ── GET /api/history ──────────────────────────────────────────────────────

def test_history_empty_on_fresh_db(test_server):
    status, _, body = _get(test_server, '/api/history')
    assert status == 200
    assert json.loads(body) == []


# ── GET unknown route ─────────────────────────────────────────────────────

def test_unknown_route_returns_404(test_server):
    status, ct, body = _get(test_server, '/api/nonexistent')
    assert status == 404
    data = json.loads(body)
    assert data['ok'] is False


# ── POST /api/parse ────────────────────────────────────────────────────────

def test_parse_missing_file_returns_error(test_server):
    status, data = _post_json(test_server, '/api/parse', {'path': '/nonexistent/file.xml'})
    assert status == 200
    assert data['ok'] is False
    assert 'error' in data

def test_parse_valid_xml_returns_ok(test_server, xml_path):
    status, data = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    assert status == 200
    assert data['ok'] is True
    assert 'result' in data
    assert 'cached_path' in data

def test_parse_result_has_expected_fields(test_server, xml_path):
    _, data = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    result = data['result']
    for field in ('pv', 'ev', 'ac', 'spi', 'cpi', 'data_date',
                  'activity_count', 'calendar_count', 'project_name'):
        assert field in result, f'Missing field: {field}'

def test_parse_result_excludes_records(test_server, xml_path):
    _, data = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    assert 'records' not in data['result']

def test_parse_populates_history(test_server, xml_path):
    _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    _, _, body = _get(test_server, '/api/history')
    history = json.loads(body)
    assert len(history) == 1
    assert history[0]['filename'] == 'minimal.xml'

def test_parse_same_file_twice_deduplicates_project(test_server, xml_path):
    _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    _, _, body = _get(test_server, '/api/history')
    # Same project → still only one project row in history
    history = json.loads(body)
    assert len(history) == 1

def test_parse_empty_path_returns_error(test_server):
    _, data = _post_json(test_server, '/api/parse', {'path': ''})
    assert data['ok'] is False


# ── POST /api/project/delete ───────────────────────────────────────────────

def test_project_delete_missing_id_returns_error(test_server):
    _, data = _post_json(test_server, '/api/project/delete', {})
    assert data['ok'] is False
    assert 'error' in data

def test_project_delete_removes_from_history(test_server, xml_path):
    _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    _, _, body = _get(test_server, '/api/history')
    project_id = json.loads(body)[0]['project_id']

    _, del_data = _post_json(test_server, '/api/project/delete', {'project_id': project_id})
    assert del_data['ok'] is True

    _, _, body_after = _get(test_server, '/api/history')
    assert json.loads(body_after) == []

def test_project_delete_invalid_id_still_ok(test_server):
    # Deleting a non-existent project_id should succeed silently
    _, data = _post_json(test_server, '/api/project/delete', {'project_id': 999999})
    assert data['ok'] is True

def test_project_delete_with_string_id(test_server, xml_path):
    # The browser sends dataset.projectId which is always a string
    _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    _, _, body = _get(test_server, '/api/history')
    project_id = json.loads(body)[0]['project_id']
    _, del_data = _post_json(test_server, '/api/project/delete', {'project_id': str(project_id)})
    assert del_data['ok'] is True
    _, _, body_after = _get(test_server, '/api/history')
    assert json.loads(body_after) == []


# ── Audit dashboard (Plan 2) ──────────────────────────────────────────────

def test_parse_returns_modules_and_snapshot(test_server, xml_path):
    _, data = _post_json(test_server, '/api/parse', {'path': str(xml_path), 'overrides_path': None})
    assert data['ok'] is True
    assert 'snapshot_id' in data and isinstance(data['snapshot_id'], int)
    am = data['result']['audit_modules']
    assert set(am['modules'].keys()) == {
        'dangling', 'float', 'out_of_sequence', 'lag_lead',
        'open_ends', 'relationship_types', 'hard_constraints', 'high_duration',
        'leads', 'negative_float', 'whole_day', 'circular', 'cpli'}
    assert am['module_order'] == [
        'dangling', 'float', 'out_of_sequence', 'lag_lead',
        'open_ends', 'relationship_types', 'hard_constraints', 'high_duration',
        'leads', 'negative_float', 'whole_day', 'circular', 'cpli']
    # minimal.xml has two unlinked activities -> dangling module finds them
    assert am['modules']['dangling']['kpis']['total_dangling'] >= 1
    # each module carries its own isolated score/grade
    assert 'score' in am['modules']['float'] and 'grade' in am['modules']['float']


def test_lag_justification_round_trip(test_server, tmp_path):
    """Save a Lag & Lead justification, then re-import the same file and confirm it is
    merged back from project settings — the persistence path a re-open depends on."""
    p = tmp_path / 'lag.xml'
    p.write_text(_UPDATE_XML, encoding='utf-8')   # carries A050 --FS Lag 80h (=10wd)--> A100

    _, d1 = _post_json(test_server, '/api/parse', {'path': str(p), 'overrides_path': None})
    sid = d1['snapshot_id']
    lag = d1['result']['audit_modules']['modules']['lag_lead']
    assert lag['kpis']['lagged_count'] == 1
    f0 = lag['findings'][0]
    assert f0['justification'] == ''
    rel_key = f0['rel_key']
    assert rel_key == 'A050|A100|FS'

    _, d2 = _post_json(test_server, '/api/lag/justification',
                       {'snapshot_id': sid, 'rel_key': rel_key, 'text': 'Cure + strike per MS-07'})
    assert d2['ok'] is True
    assert d2['lag_justifications'][rel_key] == 'Cure + strike per MS-07'

    # Re-import the same file → the saved reason is merged into the fresh register.
    _, d3 = _post_json(test_server, '/api/parse', {'path': str(p), 'overrides_path': None})
    lag3 = d3['result']['audit_modules']['modules']['lag_lead']
    assert lag3['findings'][0]['justification'] == 'Cure + strike per MS-07'

    # Blanking the text clears the stored reason.
    _, d4 = _post_json(test_server, '/api/lag/justification',
                       {'snapshot_id': sid, 'rel_key': rel_key, 'text': '   '})
    assert rel_key not in d4['lag_justifications']


def test_parse_returns_calendar_audit(test_server, xml_path):
    _, data = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    assert data['ok'] is True
    ca = data['result'].get('calendar_audit')
    assert ca is not None
    assert 'dashboard' in ca and 'usage' in ca and 'conflicts' in ca
    assert ca['dashboard']['total_calendar_days'] >= 1


def test_calendar_report_preview_returns_html(test_server, xml_path):
    _, parsed = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    sid = parsed['snapshot_id']
    _, data = _post_json(test_server, '/api/report/calendar',
                         {'snapshot_id': sid, 'preview': True, 'meta': {'project_name': 'X'}})
    assert data['ok'] is True
    assert '<!DOCTYPE html>' in data['html']
    assert 'Execution Dashboard' in data['html']


def test_calendar_excel_writes_file(test_server, xml_path, tmp_path):
    _, parsed = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    sid = parsed['snapshot_id']
    out = str(tmp_path / 'calendar.xlsx')
    _, data = _post_json(test_server, '/api/export/calendar_excel',
                         {'snapshot_id': sid, 'output_path': out})
    assert data['ok'] is True
    import os
    assert os.path.exists(out)


def test_calendar_report_missing_output(test_server):
    _, data = _post_json(test_server, '/api/report/calendar', {'snapshot_id': 1})
    assert data['ok'] is False


def test_project_load_returns_calendar_audit(test_server, xml_path):
    _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    _, _, body = _get(test_server, '/api/history')
    project_id = json.loads(body)[0]['project_id']
    _, data = _post_json(test_server, '/api/project/load', {'project_id': project_id})
    assert data['ok'] is True
    assert data['result'].get('calendar_audit') is not None


def test_parse_returns_evm_extras(test_server, xml_path):
    _, data = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    assert data['ok'] is True
    r = data['result']
    assert 'engineering_p6' in r and isinstance(r['engineering_p6'], list)
    assert 'activity_code_types' in r and isinstance(r['activity_code_types'], list)


def test_project_load_returns_modules(test_server, xml_path):
    _, parsed = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    _, _, body = _get(test_server, '/api/history')
    project_id = json.loads(body)[0]['project_id']
    _, data = _post_json(test_server, '/api/project/load', {'project_id': project_id})
    assert data['ok'] is True
    am = data['result']['audit_modules']
    assert am is not None
    assert 'dangling' in am['modules'] and 'float' in am['modules']
    assert isinstance(data['snapshot_id'], int)


def test_export_excel_per_module_writes_file(test_server, xml_path, tmp_path):
    _, parsed = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    sid = parsed['snapshot_id']
    out = str(tmp_path / 'dangling.xlsx')
    _, data = _post_json(test_server, '/api/export/excel',
                         {'snapshot_id': sid, 'module': 'dangling', 'output_path': out})
    assert data['ok'] is True
    import os
    assert os.path.exists(out)


def test_export_excel_unknown_module_fails(test_server, xml_path, tmp_path):
    _, parsed = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    sid = parsed['snapshot_id']
    _, data = _post_json(test_server, '/api/export/excel',
                         {'snapshot_id': sid, 'module': 'nope', 'output_path': str(tmp_path / 'x.xlsx')})
    assert data['ok'] is False


def test_export_excel_missing_output_path(test_server):
    _, data = _post_json(test_server, '/api/export/excel', {'snapshot_id': 1, 'module': 'float'})
    assert data['ok'] is False


def test_gap_route_reparses(test_server, xml_path):
    _, parsed = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    _, data = _post_json(test_server, '/api/gap', {
        'xml_path': str(xml_path), 'cached_path': parsed.get('cached_path'), 'dimension': 'Type of Works'})
    assert data['ok'] is True
    assert 'gap' in data and 'groups' in data['gap']


def test_e1_upload_missing_file(test_server):
    _, data = _post_json(test_server, '/api/e1/upload', {'snapshot_id': 1, 'path': '/nope.xlsx'})
    assert data['ok'] is False


def test_parse_returns_gap_and_finish_extras(test_server, xml_path):
    _, data = _post_json(test_server, '/api/parse', {'path': str(xml_path)})
    r = data['result']
    assert 'gap' in r                    # present (may be None if no codes)
    # engineering + code types already covered; ensure keys exist
    assert 'engineering_p6' in r


def test_evm_report_preview_returns_html_no_chrome(test_server, xml_path):
    """The preview flag renders the report HTML and returns it WITHOUT invoking Chrome,
    so the UI can show a fit-to-window preview before writing any PDF."""
    _post_json(test_server, '/api/parse', {'path': str(xml_path)})   # ensure it's importable/cached
    status, data = _post_json(test_server, '/api/report/evm', {
        'xml_path': str(xml_path), 'preview': True,
        'meta': {'project_name': 'Test', 'data_date': '2024-07-01'}})
    assert status == 200
    assert data.get('ok') is True
    assert isinstance(data.get('html'), str) and len(data['html']) > 200
    assert 'output_path' not in data     # nothing written


def test_evm_report_without_output_path_or_preview_errors(test_server, xml_path):
    _, data = _post_json(test_server, '/api/report/evm', {'xml_path': str(xml_path)})
    assert data['ok'] is False           # neither preview nor a save path → clear error


# ── POST /api/report (PDF write path) not tested — requires Chrome ─────────
