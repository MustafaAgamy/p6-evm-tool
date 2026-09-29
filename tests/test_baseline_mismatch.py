"""Review F4 — the wrong baseline revision is never attached silently.

P6 names the update's baseline (XER ``BASELINE_EXPORT.proj_name`` / XML
``<BaselineProject><Name>``). That name now reaches the result (``baseline_expected_name``), so
the Earned Value prompt / banner and the Update Analysis no-baseline screen say WHICH project to
export, and an attached file whose project is not that baseline (an earlier / later revision
shares most Activity IDs, so the match count alone cannot tell) is flagged
``baseline_mismatch`` — 'P6 names X; you attached Y' on screen and in every report's Baseline line.
"""
import json
import urllib.request

import tests.test_parser_parity as H
from p6_evm.baseline import (baseline_mismatch, baseline_label, baseline_fields, resolve_baseline,
                             expected_baseline_advice)
from p6_evm.parser import parse_file

GBT_B1 = 'Grain Bulk Terminal Detailed Schedule - Phase I REV.03 - B1'


def test_mismatch_rule_on_the_real_project_identities():
    # GBT: P6's baseline is the REV.03 copy "- B1" (id 11558); the planner exports the source
    # project, from either database — both are the right baseline.
    assert baseline_mismatch(GBT_B1, '11558', {'object_id': '9674', 'id': 'GBT-SUB-REV.03',
                             'name': 'Grain Bulk Terminal Detailed Schedule - Phase I'}) is None
    assert baseline_mismatch(GBT_B1, '11558', {'object_id': '5170', 'id': 'GBT-SUB-REV.03',
                             'name': 'Grain Bulk Terminal Detailed Schedule - Phase I REV.03'}) is None
    # REV.01 of the same terminal (876/1503 Activity IDs shared) is NOT the baseline P6 names
    assert baseline_mismatch(GBT_B1, '11558', {'object_id': '8565', 'id': 'GBT-SUB.REV0.2-1-LAST REV-8',
                             'name': 'Grain Bulk Terminal Phase I - Schedule Last REV'}) \
        == 'Grain Bulk Terminal Phase I - Schedule Last REV'
    sg = 'SAINT GOBAIN, AS2 -  Civil Package 03 - Rev.01 Clean'
    assert baseline_mismatch(sg, '7834', {'object_id': '5274', 'id': 'SNT_GBN_IB_AS2-Fin-3', 'name': sg}) is None
    assert baseline_mismatch(sg, '7834', {'object_id': '7885', 'id': 'SNT_GBN_BL_AS2-UP.11-00',
                             'name': 'SAINT GOBAIN, AS2 -  Civil Package 03 - Rev.00 Clean..22.Aug.25'})
    # the same ObjectId is always the right one; no expected name → nothing to compare
    assert baseline_mismatch('Anything', '7', {'object_id': '7', 'name': 'Other'}) is None
    assert baseline_mismatch(None, '11558', {'object_id': '8565', 'name': 'x'}) is None


def test_label_says_which_baseline_p6_names():
    f = {'baseline_source': 'attached', 'baseline_name': 'GBT_REV01.xer', 'baseline_matched': 1503,
         'baseline_total': 1503, 'baseline_mismatch': True, 'baseline_expected_name': GBT_B1,
         'baseline_attached_project': 'Grain Bulk Terminal Phase I - Schedule Last REV'}
    s = baseline_label(f)
    assert s.startswith('attached: GBT_REV01.xer (1503/1503 activities matched)')
    assert f'not the baseline P6 names (“{GBT_B1}”)' in s and 'Schedule Last REV' in s
    part = baseline_label({'baseline_source': 'attached', 'baseline_name': 'BL.xer',
                           'baseline_matched': 876, 'baseline_total': 1503})
    assert '627 activities are not in it' in part
    assert expected_baseline_advice('X') == 'P6 names “X” as this update’s baseline — export that project (XER or XML) and attach it.'
    assert expected_baseline_advice(None) == ''


def _files(tmp_path):
    upd_xer = H._write(tmp_path, 'update.xer', H.build_xer(baseline_rows=False))
    xml = H.build_xml(with_baseline=False)
    # a later revision of the same project: every Activity ID matches, but it is the update itself
    wrong = H._write(tmp_path, 'rev02.xml', xml)
    # the baseline P6 names (by name — the source project of the baseline copy)
    right = H._write(tmp_path, 'baseline.xml', xml.replace(H.PROJECT['name'], H.BASELINE['name']))
    return upd_xer, wrong, right


def test_resolve_baseline_flags_the_wrong_revision(tmp_path):
    upd, wrong, right = _files(tmp_path)
    d = parse_file(upd)
    info = resolve_baseline(d, wrong, parse_file)
    assert info['source'] == 'attached' and info['matched'] == info['total']
    assert info['expected_name'] == H.BASELINE['name']
    assert info['mismatch'] is True and info['attached_project'] == H.PROJECT['name']
    f = baseline_fields(info)
    assert f['baseline_mismatch'] is True and f['baseline_expected_name'] == H.BASELINE['name']
    d = parse_file(upd)
    info = resolve_baseline(d, right, parse_file)
    assert info['source'] == 'attached' and info['mismatch'] is False


def _post(port, route, body):
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}/{route}', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def test_pipeline_names_the_expected_baseline_and_flags_a_wrong_attach(test_server, tmp_path):
    upd, wrong, right = _files(tmp_path)
    r = _post(test_server, 'api/parse', {'path': upd})
    assert r['ok'], r.get('error')
    assert r['result']['baseline_source'] == 'self'
    assert r['result']['baseline_expected_name'] == H.BASELINE['name']        # reaches the UI
    ua = _post(test_server, 'api/update/analyze', {'xml_path': upd, 'cached_path': r['cached_path'],
                                                    'snapshot_id': r['snapshot_id']})
    assert ua['code'] == 'no_baseline' and ua['baseline_expected_name'] == H.BASELINE['name']

    body = {'xml_path': upd, 'cached_path': r['cached_path'], 'snapshot_id': r['snapshot_id']}
    up = _post(test_server, 'api/baseline/upload', dict(body, path=wrong))
    assert up['ok'] and up['matched'] == up['total']          # every Activity ID lines up …
    assert up['baseline_mismatch'] is True                    # … but it is not P6's baseline
    assert up['baseline_attached_project'] == H.PROJECT['name']
    res = up['result']
    assert res['baseline_mismatch'] is True and res['baseline_expected_name'] == H.BASELINE['name']
    ua = _post(test_server, 'api/update/analyze', body)
    assert ua['ok'] and 'not the baseline P6 names' in ua['report']['baseline_label']

    up = _post(test_server, 'api/baseline/upload', dict(body, path=right))
    assert up['ok'] and up['baseline_mismatch'] is False and up['result']['baseline_mismatch'] is False
    ua = _post(test_server, 'api/update/analyze', body)
    assert ua['ok'] and 'not the baseline P6 names' not in ua['report']['baseline_label']
