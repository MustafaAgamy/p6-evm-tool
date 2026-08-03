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
    assert set(am['modules'].keys()) == {'dangling', 'float'}
    assert am['module_order'] == ['dangling', 'float']
    # minimal.xml has two unlinked activities -> dangling module finds them
    assert am['modules']['dangling']['kpis']['total_dangling'] >= 1
    # each module carries its own isolated score/grade
    assert 'score' in am['modules']['float'] and 'grade' in am['modules']['float']


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


# ── POST /api/report not tested — requires Chrome ─────────────────────────
