"""Review F2 — every screen part and its report counterpart marks baseline-derived values
'· approx' (plus ONE 'Baseline: …' line) when the update's own Planned dates stand in for the
baseline P6 names (none inside the file, none attached) — not only Earned Value and Update
Analysis: Project Overview, WBS, Calendar Audit ('Baseline (approx)', not 'plan of record'),
Critical Path Analyzer, Update vs Update, and the EVM Planned % tile / category column.
An update read against a real baseline (inside the file or attached) carries no mark.
"""
import json
import urllib.request

import tests.test_parser_parity as H
from p6_evm.baseline import load_schedule, schedule_baseline


def _post(port, route, body):
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}/{route}', data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _files(tmp_path):
    return {'self': H._write(tmp_path, 'update.xer', H.build_xer(baseline_rows=False)),
            'embedded': H._write(tmp_path, 'update.xml', H.build_xml(with_baseline=True))}


def test_schedule_baseline_flags(tmp_path):
    f = _files(tmp_path)
    a = schedule_baseline(load_schedule(f['self']))
    assert a['baseline_approx'] is True and 'own Planned dates stand in (approximate)' in a['baseline_label']
    e = schedule_baseline(load_schedule(f['embedded']))
    assert e['baseline_approx'] is False and e['baseline_label'].startswith('inside the schedule file')
    assert schedule_baseline(None) == {'baseline_approx': False, 'baseline_label': None}


def test_parse_result_and_calendar_audit_carry_the_flag(test_server, tmp_path):
    from p6_calendar.report import render_calendar_report
    f = _files(tmp_path)
    for kind, path in f.items():
        r = _post(test_server, 'api/parse', {'path': path})
        assert r['ok'], r.get('error')
        res = r['result']
        assert res['baseline_approx'] is (kind == 'self'), kind
        d = (res.get('calendar_audit') or {}).get('dashboard') or {}
        assert d.get('baseline_approx') is (kind == 'self'), kind
        html = render_calendar_report(res['calendar_audit'], {'project_name': 'P', 'data_date': '2025-03-06'})
        if kind == 'self':
            assert 'Baseline (approx)' in html and 'plan of record' not in html
            assert 'Baseline: not in the file and none attached' in html
            assert d['baseline_label']
        else:
            assert 'plan of record' in html and 'Baseline (approx)' not in html
            assert 'Baseline: ' not in html and d.get('baseline_label') is None


def test_evm_pdf_and_excel_mark_planned_pct():
    from p6_evm.evm_report import render_evm_report
    from p6_evm.evm_excel import evm_excel
    result = {'spi': 0.5, 'cpi': 1.0, 'pv': 100.0, 'ev': 50.0, 'ac': 50.0, 'delay_days': 12,
              'categories': {'Civil': {'weight': 1.0, 'planned_pct': 0.5, 'actual_pct': 0.25}}}
    html = render_evm_report(result, {'project_name': 'P', 'data_date': '2025-04-01', 'baseline_approx': True})
    assert 'weighted table · approx' in html
    assert 'Planned % · approx' in html and 'Planned Weight % · approx' in html
    assert 'Overall Planned Weight % · approx' in html
    plain = render_evm_report(result, {'project_name': 'P', 'data_date': '2025-04-01'})
    assert '· approx' not in plain
    sheets = evm_excel({'result': dict(result, baseline_source='self'), 'meta': {}})
    flat = json.dumps(sheets, ensure_ascii=False)
    assert 'weighted table · approx' in flat and 'Planned % · approx' in flat
    flat = json.dumps(evm_excel({'result': dict(result, baseline_source='embedded'), 'meta': {}}), ensure_ascii=False)
    assert '· approx' not in flat


def test_overview_and_wbs_excel_mark_baseline_columns():
    from p6_evm.overview_excel import overview_excel
    from p6_evm.wbs_excel import wbs_excel
    result = {'spi': 0.9, 'pv': 1.0, 'overall_planned_pct': 0.5, 'baseline_finish': '2025-12-31',
              'categories': {'Civil': {'planned_pct': 0.5, 'actual_pct': 0.4, 'activity_count': 2}}}
    flat = json.dumps(overview_excel({'result': result, 'meta': {}, 'baseline_approx': True}), ensure_ascii=False)
    for lbl in ('SPI · schedule · approx', 'Baseline finish · approx',
                'Planned value · approx', 'Delay · approx', 'Planned % · approx'):
        assert lbl in flat, lbl
    assert '· approx' not in json.dumps(overview_excel({'result': result, 'meta': {}}), ensure_ascii=False)
    nodes = [{'id': '1', 'name': 'Root', 'depth': 0, 'baseline_finish': '2025-12-31', 'finish': '2026-01-10',
              'planned': 50.0, 'actual': 40.0}]
    hdr = wbs_excel({'wbs_summary': nodes, 'wbs_main': [], 'baseline_approx': True})[0]['blocks'][0]['headers']
    assert hdr[:8] == ['WBS', 'Baseline Start · approx', 'Baseline Finish · approx', 'Expected Start',
                       'Expected Finish', 'Planned % · approx', 'Actual %', 'Delay (Calendar days) · approx']   # then the Gantt's month columns


def test_critical_path_and_update_vs_update_reports(tmp_path):
    from p6_critpath.analysis import build_report
    from p6_critpath.exporters import render_html as cp_html, critpath_excel_sections
    f = _files(tmp_path)
    cur = load_schedule(f['self'])
    rep = build_report({'baseline': load_schedule(f['embedded']), 'current': cur}, 'update_baseline')
    assert rep['baseline_approx'] is True and 'stand in (approximate)' in rep['baseline_label']
    assert 'Baseline: not in the file and none attached' in cp_html(rep)
    assert 'Baseline finish · approx' in json.dumps(critpath_excel_sections(rep), ensure_ascii=False)
    ok = build_report({'baseline': load_schedule(f['embedded']), 'current': load_schedule(f['embedded'])},
                      'update_baseline')
    assert ok['baseline_approx'] is False and ok['baseline_label'] is None
    assert 'Baseline: ' not in cp_html(ok)

    from p6_period.report import build_report_from_data
    from p6_period.exporters import render_html as per_html, report_excel
    from p6_evm.metrics import compute
    from p6_evm.classify import auto_categories, build_wbs_classifier

    def m(d):
        return compute(d, {'categories': auto_categories(d)}, overrides={}, classifier=build_wbs_classifier(d))
    prev = load_schedule(H._write(tmp_path, 'prev.xer', H.build_xer(baseline_rows=False, data_date='2025-02-20 00:00')))
    pr = build_report_from_data(prev, cur, m(prev), m(cur))
    assert pr['baseline_approx'] is True
    html = per_html(pr)
    assert 'Baseline: not in the file and none attached' in html
    headers, rows = report_excel(pr)
    assert 'Baseline finish · approx' in json.dumps(rows, ensure_ascii=False)


def test_reporting_studio_kpis_carry_the_mark(temp_db, tmp_path):
    import db
    from p6_special.context import SpecialContext
    from p6_special.providers import evm          # (the Overview group left the Studio - comment 35)
    out = {}
    for kind, fields in (('self', {'baseline_source': 'self', 'baseline_expected': True}),
                         ('embedded', {'baseline_source': 'embedded', 'baseline_expected': True})):
        pid = db.upsert_project(f'P-{kind}', f'P-{kind}')
        sid = db.insert_snapshot(pid, '2025-04-01', 'x.xer', 'x.xer', kind, 1, 1)
        db.insert_metrics(sid, {'pv': 1.0, 'ev': 1.0, 'ac': 1.0, 'spi': 1.0, 'cpi': 1.0, 'delay_days': 2,
                                'overall_planned_pct': 0.5, 'overall_actual_pct': 0.5, 'variance': 0.0})
        db.save_evm_extras(sid, {'baseline_finish': '2025-12-31', 'baseline_fields': fields})
        ctx = SpecialContext(pid, snapshot_id=sid)
        labels = json.dumps([it.produce(ctx) for it in evm.provide(ctx)],
                            ensure_ascii=False, default=str)
        out[kind] = (ctx.baseline_ax(), labels)
    assert out['self'][0] == ' · approx' and out['embedded'][0] == ''
    for lbl in ('Baseline Finish · approx', 'Planned % · approx', 'Planned Value (PV) · approx', 'SPI · approx'):
        assert lbl in out['self'][1], lbl
    assert '· approx' not in out['embedded'][1]
