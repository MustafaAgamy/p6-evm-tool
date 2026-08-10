"""Tests for the Power BI HTTP routes + the best-effort parse hook."""
import http.client
import json
import os

import db
import p6_powerbi.paths as pbi_paths


def _post(port, path, payload):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read())


def _get(port, path):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
    conn.request('GET', path)
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read())


def _seed():
    pid = db.upsert_project('P1', 'Grain Terminal')
    sid = db.insert_snapshot(pid, '2026-07-31', '/p.xml', '/c.xml', 'h1', 100, 3)
    db.insert_metrics(sid, {'pv': 1000, 'ev': 900, 'ac': 950, 'spi': 0.9, 'cpi': 0.95,
                            'delay_days': 12, 'overall_planned_pct': 0.6,
                            'overall_actual_pct': 0.54, 'variance': -100})
    db.insert_category_metrics(sid, {'Civil': {'weight': 1.0, 'planned_pct': 0.5,
        'actual_pct': 0.4, 'bac': 1, 'ac': 1, 'activity_count': 1, 'overridden': False}})


def test_powerbi_open_route_builds_and_returns_paths(test_server, monkeypatch):
    monkeypatch.setattr(os, 'startfile', lambda p: None, raising=False)
    _seed()
    status, resp = _post(test_server, '/api/powerbi/open', {})
    assert status == 200 and resp['ok'] is True
    assert os.path.exists(resp['pbip'])
    assert os.path.exists(resp['dataset'])
    assert resp['errors'] == []
    # no schedule data / records leaked in this response
    assert 'result' not in resp and 'records' not in json.dumps(resp)


def test_powerbi_open_route_empty_db(test_server, monkeypatch):
    monkeypatch.setattr(os, 'startfile', lambda p: None, raising=False)
    status, resp = _post(test_server, '/api/powerbi/open', {})
    assert resp['ok'] is True
    assert os.path.exists(resp['pbip'])


def test_powerbi_status_route(test_server):
    status, resp = _get(test_server, '/api/powerbi/status')
    assert status == 200 and resp['ok'] is True
    assert 'dataset_exists' in resp and 'pbip_exists' in resp


def test_parse_hook_survives_powerbi_failure(test_server, xml_path, monkeypatch):
    """A dataset-refresh failure must never break an import."""
    import p6_powerbi

    def boom(*a, **k):
        raise RuntimeError('powerbi down')

    monkeypatch.setattr(p6_powerbi, 'write_dataset', boom)
    status, resp = _post(test_server, '/api/parse', {'path': str(xml_path)})
    assert status == 200 and resp['ok'] is True


def test_parse_hook_writes_live_dataset(test_server, xml_path):
    """After an import, the live Power BI workbook exists and is current."""
    status, resp = _post(test_server, '/api/parse', {'path': str(xml_path)})
    assert resp['ok'] is True
    assert os.path.exists(pbi_paths.dataset_workbook())
