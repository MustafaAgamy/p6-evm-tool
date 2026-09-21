"""Tests for the Schedule Audit / Schedule Health Review Special Report provider.

Covers the FULL result set the provider now exposes: the executive Schedule Health
roll-up (score KPI + whole Summary dashboard) and EVERY module the review ran
(module_order-driven), each with its full module report and — where the feature
shows one — a headline score. Circular Logic (a gate) and Lag & Lead (score
deferred) must expose a report but NO score. Availability must exactly complement
produce() for every item (the #1 past defect).
"""
import json

import db
from utils import resource_path
from p6_special.providers import audit as A
from p6_special.context import SpecialContext


def _seed(fixture, with_audit=True):
    """Seed a project with metrics + (optionally) the audit modules, snapshot
    pointing at the real fixture. Returns the project id."""
    from p6_evm.parser import parse_file
    from p6_evm.metrics import compute
    from p6_evm.classify import auto_categories, build_wbs_classifier

    with open(resource_path('config.json')) as f:
        config = json.load(f)
    data = parse_file(str(fixture))
    config['categories'] = auto_categories(data)
    result = compute(data, config, classifier=build_wbs_classifier(data))

    pid = db.upsert_project((data.project or {}).get('id', '') or '',
                            (data.project or {}).get('name', '') or 'Fixture')
    sid = db.insert_snapshot(pid, result.get('data_date'), str(fixture), str(fixture),
                             'hash', len(data.activities), len(data.calendars))
    db.insert_metrics(sid, result)
    db.insert_category_metrics(sid, result.get('categories'))
    if with_audit:
        from p6_audit import audit_modules
        db.insert_audit_modules(sid, audit_modules(data, config))
    return pid


def _items(ctx):
    return {i.id: i for i in A.provide(ctx)}


# ── coverage: every module the review ran appears ─────────────────────────────
def test_every_module_has_a_full_report(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    order = ctx.audit['module_order']
    assert len(order) >= 13                       # the engine runs ~13 modules
    for key in order:
        assert f'audit:{key}_report' in items, key


def test_previously_missing_modules_now_present(temp_db, xml_path):
    """The old provider exposed only 4 modules; the review runs many more."""
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    for key in ('cpli', 'hard_constraints', 'open_ends', 'negative_float',
                'whole_day', 'leads', 'circular', 'relationship_types', 'high_duration'):
        assert f'audit:{key}_report' in items, key


def test_full_report_is_reused_feature_html(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    pl = _items(ctx)['audit:cpli_report'].produce(ctx)
    assert pl['kind'] == 'html'
    assert 'srf-audit' in pl['html']              # feature markup wrapped + scoped


# ── score items ───────────────────────────────────────────────────────────────
def test_scored_modules_expose_a_score(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    for key in ('dangling', 'out_of_sequence', 'cpli', 'hard_constraints',
                'open_ends', 'negative_float', 'whole_day', 'leads',
                'relationship_types', 'high_duration'):
        assert f'audit:{key}_score' in items, key
        pl = items[f'audit:{key}_score'].produce(ctx)
        assert pl['kind'] == 'kpi_group'
        assert pl['items'][0]['value'].endswith('/100')


def test_score_colour_bands_85_60(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    # dangling scores 0 on the fixture -> red; cpli scores 100 -> green.
    assert items['audit:dangling_score'].produce(ctx)['items'][0]['tone'] == 'bad'
    assert items['audit:cpli_score'].produce(ctx)['items'][0]['tone'] == 'good'


def test_float_score_uses_float_health(temp_db, xml_path):
    """Float keeps its special handling — headline is Float Health, no word-grade."""
    ctx = SpecialContext(_seed(xml_path))
    kpi = _items(ctx)['audit:float_score'].produce(ctx)['items'][0]
    assert kpi['label'] == 'Float Health'
    assert kpi['sub'] is None                     # Float deliberately shows no grade


def test_circular_is_a_gate_no_score(temp_db, xml_path):
    """Circular Logic is a gate — a full report, but never a fabricated score item."""
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    assert 'audit:circular_report' in items
    assert 'audit:circular_score' not in items


def test_lag_lead_has_no_score(temp_db, xml_path):
    """Lag & Lead scoring is deliberately deferred — the feature shows no score."""
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    assert 'audit:lag_lead_report' in items
    assert 'audit:lag_lead_score' not in items


# ── Schedule Health roll-up (the executive Summary) ──────────────────────────
def test_health_score_kpi(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    item = _items(ctx)['audit:health_score']
    assert item.availability(ctx) == 'ready'
    pl = item.produce(ctx)
    assert pl['kind'] == 'kpi_group'
    kpi = pl['items'][0]
    assert kpi['label'] == 'Schedule Health'
    assert kpi['value'].endswith('/100')
    # the verdict travels in the sub-line (mirrors the on-screen Summary)
    assert ctx.audit['health']['verdict'] in (kpi['sub'] or '')


def test_summary_report_is_reused_dashboard(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    item = _items(ctx)['audit:summary_report']
    assert item.availability(ctx) == 'ready'
    pl = item.produce(ctx)
    assert pl['kind'] == 'html'
    # the whole Summary dashboard, reused verbatim (weighted roll-up).
    assert 'srf-audit' in pl['html']
    assert 'Overall Schedule Health' in pl['html']


# ── honest availability: no ready item renders empty (the #1 past defect) ─────
def test_availability_exactly_complements_produce(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    for it in A.provide(ctx):
        avail = it.availability(ctx)
        kind = it.produce(ctx).get('kind')
        if avail == 'ready':
            assert kind != 'no_data', it.id       # never a ready item that renders empty
        else:
            assert kind == 'no_data', it.id       # never real content hidden behind no_data


def test_all_items_ready_and_render_on_fixture(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    items = A.provide(ctx)
    assert items
    for it in items:
        assert it.availability(ctx) == 'ready', it.id
        assert it.produce(ctx)['kind'] != 'no_data', it.id


# ── no-data gating: audit not run -> honest no_data, never a raise ────────────
def test_health_items_no_data_without_audit(temp_db, xml_path):
    """A project whose snapshot carries no audit modules must gate the Schedule
    Health items as no_data (not a ready item that renders empty), and expose no
    per-module items."""
    ctx = SpecialContext(_seed(xml_path, with_audit=False))
    items = _items(ctx)
    assert items['audit:health_score'].availability(ctx) == 'no_data'
    assert items['audit:health_score'].produce(ctx)['kind'] == 'no_data'
    assert items['audit:summary_report'].availability(ctx) == 'no_data'
    assert items['audit:summary_report'].produce(ctx)['kind'] == 'no_data'
    # no module ran -> no per-module report/score items
    assert not [i for i in items if i.endswith('_report') and i != 'audit:summary_report']
