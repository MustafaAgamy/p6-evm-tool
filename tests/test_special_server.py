"""End-to-end HTTP tests for the /api/special/* endpoints."""
import json
import os
import urllib.request


def _post(port, path, body):
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}/{path}',
        data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req).read())


def _seed(port, xml_path):
    r = _post(port, 'api/parse', {'path': str(xml_path)})
    assert r['ok'], r
    return r['snapshot_id']


def test_catalog_endpoint(test_server, xml_path):
    sid = _seed(test_server, xml_path)
    r = _post(test_server, 'api/special/catalog', {'snapshot_id': sid})
    assert r['ok'], r
    feats = {g['feature'] for g in r['groups']}
    assert {'evm', 'audit', 'calendar', 'update', 'critpath'}.issubset(feats)
    # two-file features report needs_input + declare requires
    cp = next(g for g in r['groups'] if g['feature'] == 'critpath')
    assert all(i['availability'] == 'needs_input' for i in cp['items'])
    assert cp['items'][0]['requires']
    # completeness: Critical Path exposes its charts, not just a couple of tables
    cp_ids = {i['id'] for i in cp['items']}
    assert {'critpath:crit_near', 'critpath:cpli_trend', 'critpath:slip',
            'critpath:float_migration'}.issubset(cp_ids)


def test_render_endpoint_word_safe(test_server, xml_path):
    sid = _seed(test_server, xml_path)
    r = _post(test_server, 'api/special/render',
              {'snapshot_id': sid, 'item_ids': ['evm:planned_pct', 'evm:actual_pct'],
               'report_name': 'Weekly Board', 'theme': 'dark'})
    assert r['ok'], r
    assert 'Weekly Board' in r['html']
    assert 'Table of contents' in r['html']
    assert 'var(--' not in r['html']
    assert 'Source:' not in r['html']   # internal feature-source labels removed from the report


def test_templates_roundtrip(test_server, xml_path):
    sid = _seed(test_server, xml_path)
    s = _post(test_server, 'api/special/templates/save',
              {'snapshot_id': sid, 'template': {'name': 'Board', 'item_ids': ['evm:spi']}})
    assert s['ok']
    tid = s['template']['id']
    lst = _post(test_server, 'api/special/templates/list', {'snapshot_id': sid})
    assert any(t['id'] == tid for t in lst['templates'])
    d = _post(test_server, 'api/special/templates/delete', {'snapshot_id': sid, 'id': tid})
    assert d['ok']
    lst2 = _post(test_server, 'api/special/templates/list', {'snapshot_id': sid})
    assert not any(t['id'] == tid for t in lst2['templates'])


def test_doc_endpoint_writes_word_file(test_server, xml_path, tmp_path):
    sid = _seed(test_server, xml_path)
    out = str(tmp_path / 'report.doc')
    r = _post(test_server, 'api/special/doc',
              {'snapshot_id': sid, 'item_ids': ['evm:planned_pct'],
               'report_name': 'R', 'theme': 'light', 'output_path': out})
    assert r['ok'], r
    assert os.path.exists(out)
    with open(out, encoding='utf-8') as f:
        html = f.read()
    assert 'WordSection1' in html and 'var(--' not in html
