"""Review F4 — the baseline a report was measured against is labelled, never silent: the screen
shows it (EVM banner / Update Analysis line) and so does every output (EVM PDF · Word · HTML ·
Excel from the one report HTML, the legacy EVM Excel, Update Analysis PDF + Excel), and the
figures that come from the file's own dates are marked 'approx' on screen and in the report.
"""
import io
import json
import re
import urllib.request
import zipfile

from p6_evm.baseline import baseline_label, baseline_approx
from p6_evm.evm_report import render_evm_report
from tests.test_baseline_everywhere import WITH_BL, NO_BL, BASELINE_ALONE


def test_baseline_label_names_every_source():
    assert baseline_label({'baseline_source': 'embedded'}, 'Proj Rev.00') == 'inside the schedule file (Proj Rev.00)'
    assert baseline_label({'baseline_source': 'attached', 'baseline_name': 'BL.xer',
                           'baseline_matched': 12, 'baseline_total': 12}) == 'attached: BL.xer (12/12 activities matched)'
    assert baseline_label({'baseline_source': 'attached', 'baseline_name': 'BL.xer', 'baseline_matched': 10,
                           'baseline_total': 12}).startswith('attached: BL.xer (10/12 activities matched) — 2 ')
    s = baseline_label({'baseline_source': 'self', 'baseline_expected': True, 'baseline_missing': 'BL.xml'})
    assert 'own Planned dates stand in (approximate)' in s and 'BL.xml' in s
    assert 'none assigned in P6' in baseline_label({'baseline_source': 'self', 'baseline_expected': False})
    assert baseline_label({}) is None
    assert baseline_approx({'baseline_source': 'self'}) is True
    assert baseline_approx({'baseline_source': 'self', 'baseline_expected': False}) is False
    assert baseline_approx({'baseline_source': 'embedded'}) is False


def _result():
    return {'spi': 0.5, 'cpi': 1.0, 'pv': 100.0, 'ev': 50.0, 'ac': 50.0, 'delay_days': 12,
            'categories': {'Civil': {'weight': 1.0, 'planned_pct': 0.5, 'actual_pct': 0.25}}}


def _tiles(html):
    return re.findall(r'<div class="k">([^<]*)</div><div class="v"[^>]*>[^<]*</div><div class="n">([^<]*)</div>', html)


def test_evm_report_head_and_tiles():
    meta = {'project_name': 'P', 'data_date': '2025-04-01', 'baseline_finish': '2025-04-01',
            'baseline_label': "not in the file and none attached — the update's own Planned dates stand in (approximate)",
            'baseline_approx': True}
    html = render_evm_report(_result(), meta)
    assert '<span>Baseline:</span> not in the file and none attached' in html
    notes = dict(_tiles(html)) if _tiles(html) else {}
    assert 'approx' in notes.get('Planned Value', '') and 'approx' in notes.get('Delay', '')
    assert 'approx' in notes.get('Baseline Finish', '') and 'approx' in notes.get('SPI · Schedule', '')

    exact = render_evm_report(_result(), dict(meta, baseline_label='inside the schedule file', baseline_approx=False))
    assert '<span>Baseline:</span> inside the schedule file' in exact and 'approx' not in exact
    assert '<span>Baseline:</span>' not in render_evm_report(_result(), {'project_name': 'P'})   # older callers


def test_one_document_excel_header_carries_the_baseline():
    from p6_export.html_model import parse_report
    from p6_export.to_xlsx import build_meta
    html = render_evm_report(_result(), {'project_name': 'P', 'data_date': '2025-04-01',
                                         'baseline_label': 'attached: BL.xer (3/3 activities matched)'})
    ctx = dict(build_meta(parse_report(html), feature='Earned Value')['context'])
    assert ctx['Baseline'] == 'attached: BL.xer (3/3 activities matched)'
    assert ctx['Project'] == 'P'


def _post(port, route, body):
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}/{route}', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _xlsx_text(path):
    with zipfile.ZipFile(path) as z:
        return ' '.join(z.read(n).decode('utf-8', 'replace') for n in z.namelist() if n.endswith('.xml'))


def test_evm_and_update_analysis_outputs_name_the_baseline(test_server, tmp_path):
    files = {}
    for name, txt in (('with_bl.xml', WITH_BL), ('no_bl.xml', NO_BL), ('baseline.xml', BASELINE_ALONE)):
        p = tmp_path / name
        p.write_text(txt, encoding='utf-8')
        files[name.split('.')[0]] = str(p)

    # 1. embedded — EVM report head + Update Analysis screen/PDF/Excel
    a = _post(test_server, 'api/parse', {'path': files['with_bl']})
    ev = _post(test_server, 'api/report/evm', {'xml_path': files['with_bl'], 'cached_path': a['cached_path'],
                                               'snapshot_id': a['snapshot_id'], 'preview': True,
                                               'meta': {'project_name': 'Proj'}})
    assert ev['ok'], ev
    assert '<span>Baseline:</span> inside the schedule file' in ev['html'] and 'approx' not in ev['html']
    ua = _post(test_server, 'api/update/analyze', {'xml_path': files['with_bl'], 'cached_path': a['cached_path'],
                                                   'snapshot_id': a['snapshot_id']})
    assert ua['ok'] and ua['report']['baseline_label'].startswith('inside the schedule file')
    rep = _post(test_server, 'api/update/report', {'report': ua['report'], 'preview': True})
    assert 'Baseline: inside the schedule file' in rep['html']
    out = tmp_path / 'ua.xlsx'
    assert _post(test_server, 'api/update/excel', {'report': ua['report'], 'output_path': str(out)})['ok']
    assert 'inside the schedule file' in _xlsx_text(out)

    # 2. no baseline in the file, none attached → the report says so and marks the figures approx
    b = _post(test_server, 'api/parse', {'path': files['no_bl']})
    ev = _post(test_server, 'api/report/evm', {'xml_path': files['no_bl'], 'cached_path': b['cached_path'],
                                               'snapshot_id': b['snapshot_id'], 'preview': True,
                                               'meta': {'project_name': 'Proj'}})
    assert "own Planned dates stand in (approximate)" in ev['html'] and 'approx' in ev['html']

    # 3. attached — the report names the file and the match count; the legacy EVM Excel too
    up = _post(test_server, 'api/baseline/upload', {'path': files['baseline'], 'xml_path': files['no_bl'],
                                                    'cached_path': b['cached_path'], 'snapshot_id': b['snapshot_id']})
    assert up['ok'], up
    ev = _post(test_server, 'api/report/evm', {'xml_path': files['no_bl'], 'cached_path': b['cached_path'],
                                               'snapshot_id': b['snapshot_id'], 'preview': True,
                                               'meta': {'project_name': 'Proj'}})
    assert '<span>Baseline:</span> attached: baseline.xml (3/3 activities matched)' in ev['html']
    out = tmp_path / 'evm.xlsx'
    assert _post(test_server, 'api/evm/excel', {'report': {'result': up['result'], 'meta': {'project_name': 'Proj'}},
                                                       'output_path': str(out)})['ok']
    assert 'attached: baseline.xml' in _xlsx_text(out)
