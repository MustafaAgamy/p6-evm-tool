"""Run stages — a long Run names its real step for the Run bar (owner comment 36).

Baseline Revision Comparison, Critical Path Analyzer and Consultant Review read two or three
whole schedules and then compare them. The page sends a `run_id`; the server records the step
it is really on (with that step's share of the bar) and GET /api/run/stage?id= reports it."""
import json
import urllib.request

import server as srv


def _post(port, path, payload):
    req = urllib.request.Request(
        f'http://localhost:{port}{path}', data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req).read())


def _get(port, path):
    return json.loads(urllib.request.urlopen(f'http://localhost:{port}{path}').read())


def test_bands_follow_the_estimates_and_cover_the_bar():
    st = srv._RunStages({'run_id': 'r1'}, [('Reading A', 1.0), ('Reading B', 3.0), ('Comparing', 1.0)])
    assert [(b['from'], b['to']) for b in st.bands] == [(0.0, 0.2), (0.2, 0.8), (0.8, 1.0)]
    st.enter(1)
    assert srv._RUN_STAGES['r1']['label'] == 'Reading B'
    assert srv._RUN_STAGES['r1']['step'] == 2 and srv._RUN_STAGES['r1']['steps'] == 3
    st.close()
    assert 'r1' not in srv._RUN_STAGES


def test_no_run_id_records_nothing():
    st = srv._RunStages({}, [('Reading A', 1.0)])
    st.enter(0)
    assert '' not in srv._RUN_STAGES
    st.close()


def test_parse_estimate_is_file_size_at_the_read_rate(xml_path):
    est = srv._parse_secs(str(xml_path))
    assert 0 < est < 1
    assert srv._parse_secs('Z:/no/such/file.xml') == 1.0


def test_stage_route(test_server):
    assert _get(test_server, '/api/run/stage?id=nope') == {'ok': True, 'stage': None}
    srv._RUN_STAGES['live'] = {'label': 'Reading Rev.01 — x.xml', 'from': 0.2, 'to': 0.8, 'est_s': 3.0,
                               'step': 2, 'steps': 3}
    try:
        r = _get(test_server, '/api/run/stage?id=live')
        assert r['stage']['label'] == 'Reading Rev.01 — x.xml' and r['stage']['to'] == 0.8
    finally:
        srv._RUN_STAGES.pop('live', None)


def _spy_parse(monkeypatch, run_id):
    """Record the stage the server reports at the moment each schedule is read."""
    import p6_evm.parser as parser
    seen = []
    real = parser.parse_file

    def spy(path, *a, **k):
        seen.append(dict(srv._RUN_STAGES.get(run_id) or {}).get('label'))
        return real(path, *a, **k)
    monkeypatch.setattr(parser, 'parse_file', spy)
    return seen


def test_revcompare_reports_each_real_step(test_server, xml_path, monkeypatch):
    seen = _spy_parse(monkeypatch, 'rc-1')
    r = _post(test_server, '/api/revcompare', {'rev0_path': str(xml_path), 'rev1_path': str(xml_path), 'run_id': 'rc-1'})
    assert r['ok'] is True and r['report']['rev0']['file'] == 'minimal.xml'
    assert seen == ['Reading Rev.00 — minimal.xml', 'Reading Rev.01 — minimal.xml']
    assert 'rc-1' not in srv._RUN_STAGES                      # cleared once the answer is sent


def test_critpath_reports_each_real_step(test_server, xml_path, monkeypatch):
    seen = _spy_parse(monkeypatch, 'cp-1')
    r = _post(test_server, '/api/critpath/analyze', {'mode': 'update_baseline', 'current_path': str(xml_path),
                                                     'baseline_path': str(xml_path), 'run_id': 'cp-1'})
    assert r['ok'] is True
    assert seen == ['Reading the current schedule — minimal.xml', 'Reading the baseline — minimal.xml']
    assert 'cp-1' not in srv._RUN_STAGES


def test_consultant_review_reports_each_real_step(test_server, xml_path, monkeypatch):
    seen = _spy_parse(monkeypatch, 'cr-1')
    r = _post(test_server, '/api/compare', {'baseline_path': str(xml_path), 'update_path': str(xml_path), 'run_id': 'cr-1'})
    assert r['ok'] is True and r['report']['baseline_file'] == 'minimal.xml'
    assert seen == ['Reading the baseline — minimal.xml', 'Reading the update — minimal.xml']
    assert 'cr-1' not in srv._RUN_STAGES


def test_failed_run_clears_its_stage(test_server, tmp_path):
    bad = tmp_path / 'broken.xml'
    bad.write_text('<not-a-schedule', encoding='utf-8')
    r = _post(test_server, '/api/revcompare', {'rev0_path': str(bad), 'rev1_path': str(bad), 'run_id': 'rc-bad'})
    assert r['ok'] is False
    assert 'rc-bad' not in srv._RUN_STAGES
