"""Tests for the Professional Dashboard aggregation layer (p6_dashboard)."""
import os
import tempfile
import zipfile
from xml.dom.minidom import parseString

import pytest

import db
from p6_dashboard import registry
from p6_dashboard.registry import component, catalog, render, register_provider
from p6_dashboard.exporters import render_dashboard_html, write_dashboard_xlsx


# ── a configurable fake context (no DB / no parse) ──────────────────────────

class FakeCtx:
    def __init__(self, **kw):
        self._d = kw
        self.project_id = kw.get('project_id')
        self.snapshot_id = kw.get('snapshot_id')

    def _v(self, k, default=None):
        return self._d.get(k, default)

    def evm(self):        return self._v('evm')
    def audit(self):      return self._v('audit')
    def calendar(self):   return self._v('calendar')
    def extras(self):     return self._v('extras', {})
    def e1(self):         return self._v('e1')
    def settings(self):   return self._v('settings', {})
    def snapshots(self):  return self._v('snapshots', [])
    def has_xml(self):    return self._v('has_xml', False)
    def parsed(self):     return self._v('parsed')
    def computed(self):   return self._v('computed')
    def memo(self, k, fn):  # no caching needed in tests
        return fn()


EVM = {
    'spi': 0.66, 'cpi': 0.98, 'delay_days': 0, 'variance': -3_100_000,
    'overall_actual_pct': 40.4, 'overall_planned_pct': 61.4,
    'pv': 156_500_000, 'ev': 145_600_000,
    'categories': {'Piles': {'weight': 10, 'actual_pct': 18.1}},
}
AUDIT = {
    'modules': {
        'float': {'module': 'float', 'name': 'Float Analysis', 'score': 72, 'grade': 'Acceptable',
                  'kpis': {'float_pct': 14, 'threshold': 5}},
        'oos': {'module': 'oos', 'name': 'Out of Sequence', 'score': 54, 'grade': 'Needs Attention',
                'kpis': {'oos_pct': 7.4, 'oos_count': 142, 'critical_oos': 12}},
        'lag_lead': {'module': 'lag_lead', 'name': 'Lag & Lead', 'score': 80,
                     'kpis': {'verdict': 'Review needed', 'verdict_reason': 'DCMA lag 6.2%'}},
        'dangling': {'module': 'dangling', 'name': 'Dangling', 'score': 88,
                     'kpis': {'dangling_pct': 2.1, 'total_dangling': 10}},
    },
    'module_order': ['float', 'oos', 'lag_lead', 'dangling'],
}


# ── registry / discovery ────────────────────────────────────────────────────

def test_discover_registers_all_builtin_providers():
    registry.clear_providers()
    registry.discover()
    assert len(registry._PROVIDERS) >= 7


def test_component_rejects_unknown_type():
    with pytest.raises(ValueError):
        component('x', 'X', 'S', 'bogus', lambda c: {})


def test_catalog_empty_project_only_unavailable_components():
    registry.clear_providers()
    cat = catalog(FakeCtx())
    # recompute + two-file providers still advertise (greyed); parse-free ones stay silent
    assert cat, 'expected the recompute/two-file descriptors'
    assert all(not c['available'] for c in cat)
    ids = {c['id'] for c in cat}
    assert {'construct.score', 'update.time_elapsed', 'consultant.delay', 'period.spi_trend'} <= ids


def test_render_never_raises_on_empty():
    registry.clear_providers()
    ctx = FakeCtx()
    cat = catalog(ctx)
    payloads = render(ctx, [c['id'] for c in cat])
    assert len(payloads) == len(cat)
    assert all('type' in p for p in payloads.values())


def test_broken_provider_does_not_break_catalog():
    registry.clear_providers()
    registry.discover()

    @register_provider
    def _boom(ctx):
        raise RuntimeError('provider blew up')

    cat = catalog(FakeCtx(evm=EVM))   # should still return EVM components
    assert any(c['id'] == 'evm.spi' for c in cat)


# ── EVM provider ─────────────────────────────────────────────────────────────

def test_evm_provider_components_and_status():
    registry.clear_providers()
    ctx = FakeCtx(evm=EVM, extras={'gap': {'groups': [{'code': 'Piles', 'gap': 52_400_000}]}})
    cat = catalog(ctx)
    ids = {c['id'] for c in cat}
    assert {'evm.spi', 'evm.cpi', 'evm.delay', 'evm.variance', 'evm.pvev', 'evm.categories', 'evm.gap'} <= ids
    p = render(ctx, ['evm.spi'])['evm.spi']
    assert p['data']['value'] == '0.66'
    assert p['data']['status'] == 'bad'          # 0.66 < 0.85
    delay = render(ctx, ['evm.delay'])['evm.delay']
    assert delay['data']['status'] == 'good'     # 0 days slip


def test_evm_provider_silent_without_data():
    registry.clear_providers()
    assert not [c for c in catalog(FakeCtx()) if c['source'] == 'EVM Results']


# ── Audit provider ───────────────────────────────────────────────────────────

def test_audit_provider_maps_modules():
    registry.clear_providers()
    ctx = FakeCtx(audit=AUDIT)
    cat = catalog(ctx)
    ids = {c['id'] for c in cat}
    assert {'audit.health', 'audit.float_health', 'audit.oos', 'audit.lag', 'audit.dangling'} <= ids
    oos = render(ctx, ['audit.oos'])['audit.oos']
    assert '142' in oos['data']['note'] and oos['data']['status'] == 'warn'   # 7.4% in [5,10)
    health = render(ctx, ['audit.health'])['audit.health']
    labels = [s['label'] for s in health['data']['stats']]
    assert 'Out of Sequence' in labels
    # worst score first
    assert health['data']['stats'][0]['value'] == 54


# ── exporters ────────────────────────────────────────────────────────────────

_COMP = {
    'header': {'title': 'GBT', 'subtitle': 'Data date 2026-02-15'},
    'components': [
        {'id': 'a', 'type': 'kpi', 'title': 'SPI', 'source': 'EVM', 'size': 1,
         'payload': {'type': 'kpi', 'data': {'value': '0.66', 'note': 'behind', 'status': 'bad'}}},
        {'id': 'c', 'type': 'chart', 'title': 'PV vs EV', 'source': 'EVM', 'size': 1,
         'payload': {'type': 'chart', 'data': {'kind': 'bars',
                     'rows': [{'label': 'PV', 'value': 100, 'display': '156M', 'color': '#3b6fa8'}]}}},
        {'id': 'e', 'type': 'table', 'title': 'Fronts', 'source': 'UA', 'size': 2,
         'payload': {'type': 'table', 'data': {'headers': ['Front', '%'], 'rows': [['Silo 9', '48%']]}}},
    ],
}


def test_render_dashboard_html():
    html = render_dashboard_html(_COMP)
    assert '<html' in html and 'GBT' in html and 'Silo 9' in html
    assert 'panel' in html


def test_write_dashboard_xlsx_is_valid_workbook():
    path = os.path.join(tempfile.gettempdir(), 'pd_unit.xlsx')
    write_dashboard_xlsx(path, _COMP)
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            assert '[Content_Types].xml' in names and 'xl/worksheets/sheet1.xml' in names
            for nm in names:
                if nm.endswith('.xml'):
                    parseString(z.read(nm))     # well-formed
    finally:
        os.remove(path)


# ── DB layout roundtrip ──────────────────────────────────────────────────────

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_end_to_end_from_real_xml(temp_db):
    """Parse the real fixture → DB → DashboardContext → catalog/render, asserting the
    parse-free path yields REAL values (not placeholders). This is the end-to-end guard
    a fake-context unit test cannot give."""
    import json
    from p6_evm.parser import parse_file
    from p6_evm.metrics import compute
    from p6_evm.classify import auto_categories, build_wbs_classifier
    from p6_dashboard.context import DashboardContext

    xmlp = os.path.join(_ROOT, 'tests', 'fixtures', 'minimal.xml')
    with open(os.path.join(_ROOT, 'config.json')) as f:
        config = json.load(f)
    data = parse_file(xmlp)
    config['categories'] = auto_categories(data)
    result = compute(data, config, classifier=build_wbs_classifier(data))

    pid = db.upsert_project(data.project.get('id', '') or '', data.project.get('name', '') or 'x')
    sid = db.insert_snapshot(project_id=pid, data_date=result.get('data_date'),
                             original_path=xmlp, cached_path=None, file_hash='e2e',
                             activity_count=len(data.activities), calendar_count=len(data.calendars))
    db.insert_metrics(sid, result)
    db.insert_category_metrics(sid, result.get('categories'))
    try:
        from p6_audit import audit_modules as run_audit_modules
        db.insert_audit_modules(sid, run_audit_modules(data, config))
    except Exception:
        pass

    registry.clear_providers()
    ctx = DashboardContext(snapshot_id=sid, project_id=pid, xml_path=xmlp)
    cat = catalog(ctx)
    ids = {c['id'] for c in cat}
    assert 'evm.spi' in ids and 'overview.summary' in ids
    assert next(c for c in cat if c['id'] == 'evm.spi')['available'] is True

    payloads = render(ctx, ['evm.spi', 'overview.summary'])
    assert payloads['evm.spi']['data']['value'] not in (None, '', '—')
    stats = payloads['overview.summary']['data']['stats']
    assert stats and any(s['value'] not in (None, '—') for s in stats)


def test_dashboard_layout_roundtrip(temp_db):
    pid = db.upsert_project('P-DASH', 'Dash Project')
    assert db.get_dashboard_layout(pid) is None
    layout = {'components': [{'id': 'evm.spi'}, {'id': 'x', 'title': 'My Title', 'size': 2}],
              'custom': {}, 'header': {'title': 'GBT'}}
    db.save_dashboard_layout(pid, layout)
    got = db.get_dashboard_layout(pid)
    assert got == layout
    # a summary save must not clobber the layout (shallow-merge)
    db.save_dashboard_summary(pid, 'dashboard_consultant', {'reported_delay': 66})
    assert db.get_dashboard_layout(pid) == layout
    assert db.get_project_settings(pid)['dashboard_consultant']['reported_delay'] == 66
