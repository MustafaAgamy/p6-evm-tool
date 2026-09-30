"""Review F3 — a schedule with NO baseline assigned in P6 is not "exported without its baseline".

P6 names a project's baseline in XML ``<CurrentBaselineProjectObjectId>`` / XER
``PROJECT.sum_base_proj_id``. A baseline programme has none (GBT_REV03.xml and MAFI_BASELINE.xml
write ``<CurrentBaselineProjectObjectId xsi:nil="true" />``; GBT_REV03.xer leaves sum_base_proj_id
blank): its own Planned dates ARE its baseline, so the 'self' result is exact — no prompt, no
"approx", and Update Analysis reads it. Both formats agree (R4).
"""
import json
import urllib.request

import pytest

import tests.test_parser_parity as H
from p6_evm.parser import parse_file
from p6_evm.baseline import baseline_expected, load_schedule, baseline_fields

_PTR = f"<CurrentBaselineProjectObjectId>{H.BASELINE['object_id']}</CurrentBaselineProjectObjectId>"


@pytest.fixture
def unassigned(tmp_path, monkeypatch):
    """The parity schedule with no baseline assigned in P6, as XML and as XER."""
    xml = H.build_xml(with_baseline=False)
    assert xml.count(_PTR) == 1
    xml = xml.replace(_PTR, '<CurrentBaselineProjectObjectId xsi:nil="true" />')
    orig = H._xer_project_row
    monkeypatch.setattr(H, '_xer_project_row', lambda p, base_id: orig(p, ''))
    xer = H.build_xer(baseline_rows=False)
    return {'xml': H._write(tmp_path, 'unassigned.xml', xml),
            'xer': H._write(tmp_path, 'unassigned.xer', xer)}


def test_no_baseline_assigned_is_not_expected_in_either_format(unassigned):
    for fmt, path in unassigned.items():
        d = load_schedule(path)
        assert d.baseline_source == 'self', fmt
        assert baseline_expected(d) is False, fmt
        f = baseline_fields(d.baseline_info)
        assert f['baseline_expected'] is False and f['baseline_source'] == 'self', fmt


def test_an_update_naming_its_baseline_is_expected_in_both_formats(tmp_path):
    xml = H._write(tmp_path, 'u.xml', H.build_xml(with_baseline=False))
    xer = H._write(tmp_path, 'u.xer', H.build_xer(baseline_rows=False))
    for fmt, path in (('xml', xml), ('xer', xer)):
        d = load_schedule(path)
        assert d.baseline_source == 'self' and baseline_expected(d) is True, fmt
        assert baseline_fields(d.baseline_info)['baseline_expected'] is True, fmt


def test_a_project_pointing_at_itself_has_no_separate_baseline():
    class D:
        project = {'object_id': '42', 'baseline_object_id': '42'}
    assert baseline_expected(D()) is False
    D.project = {'object_id': '42', 'baseline_object_id': ''}
    assert baseline_expected(D()) is False
    D.project = {'object_id': '42', 'baseline_object_id': '41'}
    assert baseline_expected(D()) is True


def _post(port, route, body):
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}/{route}', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def test_pipeline_and_update_analysis_for_a_schedule_with_no_baseline_assigned(test_server, unassigned):
    out = {}
    for fmt, path in unassigned.items():
        r = _post(test_server, 'api/parse', {'path': path})
        assert r['ok'], r.get('error')
        assert r['result']['baseline_source'] == 'self'
        assert r['result']['baseline_expected'] is False     # the UI: no prompt, no "approx"
        ua = _post(test_server, 'api/update/analyze', {'xml_path': path, 'cached_path': r['cached_path'],
                                                        'snapshot_id': r['snapshot_id']})
        assert ua['ok'], ua                                  # read against its own dates, as P6
        assert ua['report']['has_baseline'] is True and ua['report']['baseline_expected'] is False
        out[fmt] = (r['result']['pv'], r['result']['spi'], r['result']['delay_days'])
    assert out['xml'][2] == out['xer'][2]                   # Delay identical
    assert out['xml'][0] == pytest.approx(out['xer'][0], abs=H.money_tolerance(50))   # XER money 4 dp (G2)
    assert out['xml'][1] == pytest.approx(out['xer'][1], abs=1e-6)
