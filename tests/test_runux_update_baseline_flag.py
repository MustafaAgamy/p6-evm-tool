"""RUNUX-05 (owner comment 36, "no gap after Run"): Update Analysis answered "This update has no
baseline inside it" only after re-reading the whole file on the server (GBT ~2 s, MAFI ~7.5 s under
the Run bar). The import already knows whether the file carries a baseline, so it records it
(`has_embedded_baseline`) on the result — kept for Recent Projects re-opens too — and the screen can
give that answer at once. The flag must agree exactly with what /api/update/analyze decides."""
import http.client
import json

from tests.test_update_server import _post_json, _sample


def _history_project_id(port):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    conn.request('GET', '/api/history')
    rows = json.loads(conn.getresponse().read())
    return rows[0]['project_id']


def _strip_baseline(src_path, tmp_path):
    src = open(src_path, encoding='utf-8').read()
    start = src.index('<BaselineProject>')
    end = src.index('</BaselineProject>') + len('</BaselineProject>')
    p = tmp_path / 'update_no_baseline.xml'
    p.write_text(src[:start] + src[end:], encoding='utf-8')
    return str(p)


def test_import_records_embedded_baseline_true(test_server, tmp_path):
    path = _sample(tmp_path)
    _, parsed = _post_json(test_server, '/api/parse', {'path': path})
    assert parsed['ok'] is True
    assert parsed['result']['has_embedded_baseline'] is True
    _, ana = _post_json(test_server, '/api/update/analyze', {'xml_path': path})
    assert ana['ok'] is True and ana['report']['has_baseline'] is True      # same answer as the analysis
    _, loaded = _post_json(test_server, '/api/project/load', {'project_id': _history_project_id(test_server)})
    assert loaded['ok'] is True and loaded['result']['has_embedded_baseline'] is True


def test_import_records_embedded_baseline_false(test_server, tmp_path):
    path = _strip_baseline(_sample(tmp_path), tmp_path)
    _, parsed = _post_json(test_server, '/api/parse', {'path': path})
    assert parsed['ok'] is True
    assert parsed['result']['has_embedded_baseline'] is False
    _, ana = _post_json(test_server, '/api/update/analyze', {'xml_path': path})
    assert ana['ok'] is False and ana['code'] == 'no_baseline'              # same answer as the analysis
    _, loaded = _post_json(test_server, '/api/project/load', {'project_id': _history_project_id(test_server)})
    assert loaded['ok'] is True and loaded['result']['has_embedded_baseline'] is False


def test_old_snapshot_without_flag_stays_unknown(test_server, tmp_path):
    """A snapshot imported before the flag existed has no answer stored: the result says None
    (unknown), so the screen still asks the server instead of guessing."""
    import db
    path = _sample(tmp_path)
    _, parsed = _post_json(test_server, '/api/parse', {'path': path})
    sid = parsed['snapshot_id']
    extras = db.get_evm_extras(sid) or {}
    extras.pop('has_embedded_baseline', None)
    db.save_evm_extras(sid, extras)
    _, loaded = _post_json(test_server, '/api/project/load', {'project_id': _history_project_id(test_server)})
    assert loaded['ok'] is True and loaded['result'].get('has_embedded_baseline') is None
