"""[parser:R3] review findings on the attach-baseline flow.

F11 — an attach reads the update and the baseline ONCE (the import pipeline decides 'already
      inside the file' / 'matches no activity' itself, before anything is stored), the refusal
      names the update's own format (XER or XML), and the no-snapshot answers hand the screen
      the result's baseline keys (source 'self' after a remove — never null).
"""
import db  # noqa: F401  (the test_server fixture patches its data folder)
import p6_evm.parser as parser_mod

from tests.test_baseline_everywhere import _files, _post
from tests.test_parser_parity import build_xer


def _count_parses(monkeypatch):
    calls = []
    real = parser_mod.parse_file

    def counting(path, *a, **kw):
        calls.append(str(path))
        return real(path, *a, **kw)
    monkeypatch.setattr(parser_mod, 'parse_file', counting)
    return calls


def test_attach_parses_the_update_and_the_baseline_once(test_server, tmp_path, monkeypatch):
    f = _files(tmp_path)
    b = _post(test_server, 'api/parse', {'path': f['no_bl']})
    assert b['ok'], b.get('error')
    calls = _count_parses(monkeypatch)
    up = _post(test_server, 'api/baseline/upload', {
        'path': f['baseline'], 'xml_path': f['no_bl'], 'cached_path': b['cached_path'],
        'snapshot_id': b['snapshot_id']})
    assert up['ok'] and up['matched'] == 3 and up['total'] == 3, up
    assert up['result']['baseline_source'] == 'attached'
    # the cached copy is what the snapshot remembers and what the result names
    assert up['baseline_cached'] == up['result']['baseline_path']
    assert db.get_attached_baseline(snapshot_id=b['snapshot_id']) == up['baseline_cached']
    upd = [c for c in calls if c.endswith('no_bl.xml')]
    bl = [c for c in calls if c.endswith('baseline.xml')]
    assert len(upd) == 1 and len(bl) == 1, calls       # was 2 + 2 (pre-parse, then the pipeline)


def test_wrong_project_is_decided_by_one_read_and_nothing_is_stored(test_server, tmp_path, monkeypatch):
    f = _files(tmp_path)
    b = _post(test_server, 'api/parse', {'path': f['no_bl']})
    calls = _count_parses(monkeypatch)
    up = _post(test_server, 'api/baseline/upload', {
        'path': f['other'], 'xml_path': f['no_bl'], 'cached_path': b['cached_path'],
        'snapshot_id': b['snapshot_id']})
    assert up['ok'] and up['matched'] == 0 and up['total'] == 3 and 'result' not in up
    assert up['baseline_name'] == 'other.xml'
    assert db.get_attached_baseline(snapshot_id=b['snapshot_id']) is None
    assert len(calls) == 2, calls
    # the stored snapshot is untouched: re-opening it still reads its own dates
    pid = db.get_project_id_for_snapshot(b['snapshot_id'])
    load = _post(test_server, 'api/project/load', {'project_id': pid})
    assert load['ok'] and load['result']['baseline_source'] == 'self'
    assert load['result']['pv'] == b['result']['pv']


def test_embedded_refusal_names_the_update_format(test_server, tmp_path):
    f = _files(tmp_path)
    xer = tmp_path / 'with_bl.xer'
    xer.write_text(build_xer(), encoding='utf-8', newline='')        # carries its baseline rows
    for path, fmt in ((str(xer), 'XER'), (f['with_bl'], 'XML')):
        imp = _post(test_server, 'api/parse', {'path': path})
        assert imp['ok'] and imp['result']['baseline_source'] == 'embedded', (fmt, imp.get('error'))
        up = _post(test_server, 'api/baseline/upload', {
            'path': f['baseline'], 'xml_path': path, 'cached_path': imp['cached_path'],
            'snapshot_id': imp['snapshot_id']})
        assert up['ok'] is False and up['code'] == 'embedded', up
        assert up['error'].startswith(f'This {fmt} already carries its baseline project'), up['error']
        assert db.get_attached_baseline(snapshot_id=imp['snapshot_id']) is None
        # and without a snapshot (nothing stored) — the same words
        up2 = _post(test_server, 'api/baseline/upload', {'path': f['baseline'], 'xml_path': path})
        assert up2['code'] == 'embedded' and up2['error'] == up['error']


def test_no_snapshot_answers_carry_the_baseline_keys(test_server, tmp_path):
    f = _files(tmp_path)
    up = _post(test_server, 'api/baseline/upload', {'path': f['baseline'], 'xml_path': f['no_bl']})
    assert up['ok'] and up['matched'] == 3 and 'result' not in up
    bf = up['baseline_fields']
    assert bf['baseline_source'] == 'attached' and bf['baseline_name'] == 'baseline.xml'
    assert bf['baseline_path'] == up['baseline_cached'] and bf['baseline_approx'] is False
    assert bf['baseline_label']

    cl = _post(test_server, 'api/baseline/clear', {'xml_path': f['no_bl']})
    assert cl['ok'] and 'result' not in cl
    bf = cl['baseline_fields']
    assert bf['baseline_source'] == 'self'          # not null — null reads as 'embedded' for an XML
    assert bf['baseline_approx'] is True and bf['baseline_label']
    assert bf['baseline_name'] is None and bf['baseline_path'] is None


def test_two_file_features_name_the_attached_baseline_not_its_cached_copy(test_server, tmp_path):
    """F9 — the attached baseline pre-fills the Baseline slot of Consultant Review and Critical
    Path Analyzer as its cached copy ({hash12}_name); the report names the planner's file."""
    f = _files(tmp_path)
    b = _post(test_server, 'api/parse', {'path': f['no_bl']})
    assert b['ok'], b.get('error')
    up = _post(test_server, 'api/baseline/upload', {
        'path': f['baseline'], 'xml_path': f['no_bl'], 'cached_path': b['cached_path'],
        'snapshot_id': b['snapshot_id']})
    cached = up['result']['baseline_path']
    assert cached != f['baseline'] and cached.endswith('_baseline.xml')

    cr = _post(test_server, 'api/compare', {
        'baseline_path': cached, 'update_path': f['no_bl'], 'cached_path': b['cached_path']})
    assert cr['ok'], cr.get('error')
    assert cr['report']['baseline_file'] == 'baseline.xml'
    assert cr['report']['update_file'] == 'no_bl.xml'

    cp = _post(test_server, 'api/critpath/analyze', {
        'mode': 'update_baseline', 'current_path': f['no_bl'], 'cached_path': b['cached_path'],
        'baseline_path': cached})
    assert cp['ok'], cp.get('error')
    assert cp['report']['files']['baseline'] == 'baseline.xml'
