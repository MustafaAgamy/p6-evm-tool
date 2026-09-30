"""R4 review round 2 — F6 / F8.

F6  A snapshot stored before the one baseline resolver has no record of which baseline its numbers
    used: an XML exported without its baseline re-opened from Recent Projects with PV 0, no banner
    and no Attach button. /api/project/load now recomputes such a snapshot ONCE, in place, through
    the import pipeline and stores baseline_fields, so later opens read the DB again.
F8  The embedded baseline's name travels in baseline_fields (baseline_embedded_name), so the EVM
    Excel header names it like the PDF head, and the EVM screen shows the same 'Baseline: …' line.
"""
import io
import json
import urllib.request
import zipfile

import db
from p6_evm.baseline import baseline_fields, baseline_label, schedule_baseline, load_schedule
from tests.test_baseline_everywhere import WITH_BL, NO_BL, BASELINE_ALONE

BL_NAME = 'Proj Rev.00 - B1'
WITH_NAMED_BL = WITH_BL.replace('<BaselineProject>', f'<BaselineProject><Name>{BL_NAME}</Name>', 1)


def _post(port, route, body):
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}/{route}', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    return str(p)


def _xlsx_text(path):
    with zipfile.ZipFile(path) as z:
        return ' '.join(z.read(n).decode('utf-8', 'replace') for n in z.namelist() if n.endswith('.xml'))


# ── F8 ───────────────────────────────────────────────────────────────────────────────────────

def test_embedded_name_is_in_baseline_fields_and_the_label(tmp_path):
    data = load_schedule(_write(tmp_path, 'with_bl.xml', WITH_NAMED_BL))
    f = baseline_fields(data.baseline_info)
    assert f['baseline_source'] == 'embedded' and f['baseline_embedded_name'] == BL_NAME
    want = f'inside the schedule file ({BL_NAME})'
    assert baseline_label(f) == want                       # no separate name argument needed
    assert schedule_baseline(data)['baseline_label'] == want
    # not embedded -> no embedded name
    nob = load_schedule(_write(tmp_path, 'no_bl.xml', NO_BL))
    assert baseline_fields(nob.baseline_info)['baseline_embedded_name'] is None


def test_evm_excel_pdf_and_screen_name_the_embedded_baseline_alike(test_server, tmp_path):
    path = _write(tmp_path, 'with_bl.xml', WITH_NAMED_BL)
    a = _post(test_server, 'api/parse', {'path': path})
    assert a['ok'], a
    want = f'inside the schedule file ({BL_NAME})'
    assert a['result']['baseline_label'] == want               # what the EVM screen line prints
    assert a['result']['baseline_embedded_name'] == BL_NAME
    ev = _post(test_server, 'api/report/evm', {'xml_path': path, 'cached_path': a['cached_path'],
                                               'snapshot_id': a['snapshot_id'], 'preview': True,
                                               'meta': {'project_name': 'Proj'}})
    assert f'<span>Baseline:</span> {want}' in ev['html']
    out = tmp_path / 'evm.xlsx'
    assert _post(test_server, 'api/evm/excel', {'report': {'result': a['result'], 'meta': {'project_name': 'Proj'}},
                                                'output_path': str(out)})['ok']
    assert want in _xlsx_text(out)
    # an older client result without baseline_label still gets the name from the fields
    res = {k: v for k, v in a['result'].items() if k != 'baseline_label'}
    out2 = tmp_path / 'evm2.xlsx'
    assert _post(test_server, 'api/evm/excel', {'report': {'result': res, 'meta': {'project_name': 'Proj'}},
                                                'output_path': str(out2)})['ok']
    assert want in _xlsx_text(out2)


# ── F6 ───────────────────────────────────────────────────────────────────────────────────────

def _make_old(sid, pv=None, spi=None):
    """Turn a fresh snapshot into one stored before the resolver: no baseline_fields in its extras
    (and, optionally, the old numbers - an XML without its baseline stored PV 0, no SPI)."""
    ex = db.get_evm_extras(sid) or {}
    ex.pop('baseline_fields', None)
    db.save_evm_extras(sid, ex)
    if pv is not None:
        with db.get_conn() as conn:
            conn.execute('UPDATE metrics SET pv = ?, spi = ? WHERE snapshot_id = ?', (pv, spi, sid))


def test_old_xml_without_baseline_reopens_with_the_attach_offer(test_server, tmp_path):
    path = _write(tmp_path, 'no_bl.xml', NO_BL)
    a = _post(test_server, 'api/parse', {'path': path})
    sid, pid = a['snapshot_id'], db.get_project_id_for_snapshot(a['snapshot_id'])
    fresh_pv = a['result']['pv']
    _make_old(sid, pv=0.0, spi=None)
    r = _post(test_server, 'api/project/load', {'project_id': pid})
    assert r['ok'] and r['snapshot_id'] == sid                 # recomputed IN PLACE, same snapshot
    res = r['result']
    assert res['baseline_source'] == 'self' and res['baseline_approx'] is True   # banner + Attach
    assert res['pv'] == fresh_pv and res['pv'] > 0             # own dates, marked approx - not PV 0
    assert (db.get_evm_extras(sid) or {}).get('baseline_fields', {}).get('baseline_source') == 'self'
    # stored now: the next open reads the DB (same answer)
    r2 = _post(test_server, 'api/project/load', {'project_id': pid})
    assert r2['result']['pv'] == fresh_pv and r2['result']['baseline_source'] == 'self'


def test_old_xml_with_embedded_baseline_reopens_named(test_server, tmp_path):
    path = _write(tmp_path, 'with_bl.xml', WITH_NAMED_BL)
    a = _post(test_server, 'api/parse', {'path': path})
    sid, pid = a['snapshot_id'], db.get_project_id_for_snapshot(a['snapshot_id'])
    _make_old(sid)
    res = _post(test_server, 'api/project/load', {'project_id': pid})['result']
    assert res['baseline_source'] == 'embedded' and res['pv'] == a['result']['pv']
    assert res['baseline_label'] == f'inside the schedule file ({BL_NAME})'


def test_old_snapshot_with_a_baseline_attached_the_old_way_reopens_attached(test_server, tmp_path):
    upd = _write(tmp_path, 'no_bl.xml', NO_BL)
    bl = _write(tmp_path, 'baseline.xml', BASELINE_ALONE)
    want = _post(test_server, 'api/parse', {'path': _write(tmp_path, 'with_bl.xml', WITH_BL)})['result']
    a = _post(test_server, 'api/parse', {'path': upd})
    sid = a['snapshot_id']
    up = _post(test_server, 'api/baseline/upload', {'path': bl, 'xml_path': upd,
                                                    'cached_path': a['cached_path'], 'snapshot_id': sid})
    assert up['ok'], up
    _make_old(sid, pv=0.0, spi=None)
    res = _post(test_server, 'api/project/load', {'project_id': db.get_project_id_for_snapshot(sid)})['result']
    assert res['baseline_source'] == 'attached' and res['baseline_name'] == 'baseline.xml'
    assert res['pv'] == want['pv'] and res['spi'] == want['spi']
