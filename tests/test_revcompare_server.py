"""HTTP routes for Baseline Revision Comparison (/api/revcompare[/report])."""
import json
import urllib.request

import pytest


def _post(port, path, payload):
    req = urllib.request.Request(
        f'http://localhost:{port}{path}', data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req).read())


def test_revcompare_requires_both_inputs(test_server, xml_path):
    r = _post(test_server, '/api/revcompare', {'rev0_path': '', 'rev1_path': str(xml_path)})
    assert r['ok'] is False and 'Rev.00' in r['error']
    r = _post(test_server, '/api/revcompare', {'rev0_path': str(xml_path), 'rev1_path': ''})
    assert r['ok'] is False and 'Rev.01' in r['error']


def test_revcompare_returns_report(test_server, xml_path):
    r = _post(test_server, '/api/revcompare', {'rev0_path': str(xml_path), 'rev1_path': str(xml_path)})
    assert r['ok'] is True
    rep = r['report']
    for key in ('summary', 'register', 'critical_path', 'milestones', 'findings', 'rev0', 'rev1'):
        assert key in rep
    assert rep['rev0']['file'] == 'minimal.xml'
    # identical files → no changes
    assert rep['register'] == []


def test_revcompare_report_preview(test_server, xml_path):
    r = _post(test_server, '/api/revcompare', {'rev0_path': str(xml_path), 'rev1_path': str(xml_path)})
    pv = _post(test_server, '/api/revcompare/report',
               {'report': r['report'], 'meta': {'report_date': '02 Sep 2026'}, 'preview': True, 'theme': 'dark'})
    assert pv['ok'] is True
    assert '<section' in pv['html'] and 'Baseline Revision Comparison' in pv['html']


def test_revcompare_report_requires_output_path(test_server, xml_path):
    r = _post(test_server, '/api/revcompare', {'rev0_path': str(xml_path), 'rev1_path': str(xml_path)})
    er = _post(test_server, '/api/revcompare/report', {'report': r['report']})
    assert er['ok'] is False
