"""Integration + smoke tests for the inline feature providers (audit, calendar,
update, constructability, twofile) and the flagship update:counts item."""
import json

import db
from utils import resource_path
from p6_special import registry
from p6_special.context import SpecialContext


def _seed(fixture):
    """Seed a full project: metrics + category + audit modules + calendar audit,
    with the snapshot pointing at the real fixture so recompute features work."""
    from p6_evm.parser import parse_file
    from p6_evm.metrics import compute
    from p6_evm.classify import auto_categories, build_wbs_classifier

    with open(resource_path('config.json')) as f:
        config = json.load(f)
    data = parse_file(str(fixture))
    config['categories'] = auto_categories(data)
    result = compute(data, config, classifier=build_wbs_classifier(data))

    p6_id = (data.project or {}).get('id', '') or ''
    name = (data.project or {}).get('name', '') or 'Fixture'
    pid = db.upsert_project(p6_id, name)
    sid = db.insert_snapshot(pid, result.get('data_date'), str(fixture), str(fixture),
                             'hash', len(data.activities), len(data.calendars))
    db.insert_metrics(sid, result)
    db.insert_category_metrics(sid, result.get('categories'))
    try:
        from p6_audit import audit_modules
        db.insert_audit_modules(sid, audit_modules(data, config))
    except Exception:
        pass
    try:
        from p6_calendar import calendar_audit
        db.save_calendar_audit(sid, calendar_audit(data, config, {}))
    except Exception:
        pass
    return pid


def _payloads_ok(rendered):
    for r in rendered:
        assert isinstance(r['payload'], dict) and 'kind' in r['payload'], r['id']


# ── catalog / auto-discovery ─────────────────────────────────────────────────
def test_catalog_includes_every_feature(temp_db, xml_path):
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))
    features = {g['feature'] for g in registry.catalog(ctx)}
    for f in ('evm', 'audit', 'calendar', 'update', 'constructability',
              'critpath', 'compare', 'period'):
        assert f in features, f


# ── audit (parse-free) ───────────────────────────────────────────────────────
def test_audit_ready_and_renders(temp_db, xml_path):
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))
    groups = {g['feature']: g for g in registry.catalog(ctx)}
    audit_ids = [i['id'] for i in groups['audit']['items']]
    assert 'audit:float_score' in audit_ids
    # modules exist for the fixture → ready
    assert all(i['availability'] == 'ready' for i in groups['audit']['items'])
    _payloads_ok(registry.render(ctx, audit_ids))


# ── calendar (parse-free) ────────────────────────────────────────────────────
def test_calendar_renders(temp_db, xml_path):
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))
    groups = {g['feature']: g for g in registry.catalog(ctx)}
    cal_ids = [i['id'] for i in groups['calendar']['items']]
    _payloads_ok(registry.render(ctx, cal_ids))


# ── update (recompute) — real feature sections ───────────────────────────────
def test_update_renders_via_registry(temp_db, xml_path):
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))
    groups = {g['feature']: g for g in registry.catalog(ctx)}
    ids = [i['id'] for i in groups['update']['items']]
    assert 'update:counts' in ids
    assert all(i['availability'] == 'ready' for i in groups['update']['items'])
    _payloads_ok(registry.render(ctx, ids))   # no raise even on the minimal fixture


# ── constructability (recompute) ─────────────────────────────────────────────
def test_constructability_renders(temp_db, xml_path):
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))
    groups = {g['feature']: g for g in registry.catalog(ctx)}
    ids = [i['id'] for i in groups['constructability']['items']]
    _payloads_ok(registry.render(ctx, ids))


# ── two-file features — needs_input / attach / auto-run ───────────────────────
def test_twofile_needs_input_without_attachment(temp_db, xml_path):
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))       # no inputs attached
    groups = {g['feature']: g for g in registry.catalog(ctx)}
    for feat in ('critpath', 'compare', 'period'):
        for i in groups[feat]['items']:
            assert i['availability'] == 'needs_input', i['id']
            assert i['requires'], i['id']         # declares what to attach
    # producing without inputs yields no_data, never raises
    ids = [i['id'] for g in ('critpath', 'compare', 'period') for i in groups[g]['items']]
    for r in registry.render(ctx, ids):
        assert r['payload']['kind'] == 'no_data'


def test_twofile_ready_with_attachment(temp_db, xml_path):
    registry.clear_providers()
    pid = _seed(xml_path)
    # attach the fixture as a stand-in baseline + previous → features turn ready + auto-run
    ctx = SpecialContext(pid, inputs={'baseline': str(xml_path), 'previous': str(xml_path)})
    groups = {g['feature']: g for g in registry.catalog(ctx)}
    for feat in ('critpath', 'compare', 'period'):
        assert all(i['availability'] == 'ready' for i in groups[feat]['items']), feat
    ids = [i['id'] for g in ('critpath', 'compare', 'period') for i in groups[g]['items']]
    _payloads_ok(registry.render(ctx, ids))       # runs the feature; must not raise


# ── end-to-end ───────────────────────────────────────────────────────────────
def test_end_to_end_document(temp_db, xml_path):
    from p6_special.assemble import build_html, build_word
    registry.clear_providers()
    pid = _seed(xml_path)
    # granular (Word-clean) items → no CSS variables leak into the document
    ids = ['evm:planned_pct', 'evm:actual_pct', 'audit:dangling_score']
    html = build_html(pid, ids, 'October Board Report', mode='dark')
    assert 'October Board Report' in html
    assert 'Table of contents' in html
    assert 'var(--' not in html
    doc = build_word(pid, ids, 'October Board Report', mode='dark')
    assert 'WordSection1' in doc and 'var(--' not in doc


def test_reused_feature_section_composes(temp_db, xml_path):
    """A reused feature-report section (EVM full report) composes into the document
    with the feature's own markup + its scoped CSS."""
    from p6_special.assemble import build_html
    registry.clear_providers()
    pid = _seed(xml_path)
    html = build_html(pid, ['evm:full_report'], 'Detailed', mode='light')
    assert 'Detailed' in html and 'srf-evm' in html   # feature markup wrapped + scoped


# ── silent-empty / honest-availability regressions ───────────────────────────
def test_calendar_weather_gated_without_estimate(temp_db, xml_path):
    """No weather estimate -> 'Weather impact' must be no_data, not a 'ready' item
    that renders an empty weather section. And every 'ready' calendar section must
    render real content."""
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))          # calendar saved, no weather estimate
    cal = {g['feature']: g for g in registry.catalog(ctx)}['calendar']['items']
    avail = {i['id']: i['availability'] for i in cal}
    assert avail['calendar:weather'] == 'no_data'
    ready_ids = [i['id'] for i in cal if i['availability'] == 'ready']
    for r in registry.render(ctx, ready_ids):
        assert r['payload']['kind'] != 'no_data', r['id']


def test_evm_full_report_no_data_when_xml_missing(temp_db):
    """evm:full_report re-parses XML; with the file gone it must be no_data (not a
    'ready' item that renders 'No data')."""
    from p6_special.providers import evm
    pid = db.upsert_project('PX', 'Gone')
    sid = db.insert_snapshot(pid, '2026-01-01', 'C:/nope/missing.xml', 'C:/nope/missing.xml', 'h', 5, 1)
    db.insert_metrics(sid, {'pv': 1e6, 'ev': 6e5, 'ac': 7e5,
                            'overall_planned_pct': 0.6, 'overall_actual_pct': 0.4})
    ctx = SpecialContext(pid)
    full = {i.id: i for i in evm.provide(ctx)}['evm:full_report']
    assert full.availability(ctx) == 'no_data'     # ctx.evm truthy but no XML


def test_word_reused_section_has_no_css_vars(temp_db, xml_path):
    """Reused feature sections must be resolved to concrete hex in Word (var()/
    color-mix dropped by Word) so they stay themed like the PDF, in every mode."""
    from p6_special.assemble import build_word
    registry.clear_providers()
    pid = _seed(xml_path)
    doc = build_word(pid, ['evm:full_report'], 'Detailed', mode='midnight')
    assert 'srf-evm' in doc               # reused section present
    assert 'var(--' not in doc            # resolved to hex for Word
    assert 'color-mix(' not in doc
