"""Consultant Review (p6_compare) Special Report provider.

Covers the section-by-section items added beside the existing compare:impact KPI and
compare:report full report: the two-file sections (dashboard / charts / logic / duration)
gated on a baseline, and the impact / consultant-recommendation section gated on the 3rd
(corrected) file. The central assertion is the #1 past defect: availability must exactly
complement produce() — every 'ready' item renders real content, never an empty section.
"""
import json

import db
from utils import resource_path
from p6_special import registry
from p6_special.context import SpecialContext

# Every two-file section item plus the impact section, in provider order.
_SECTION_IDS = ['compare:dashboard', 'compare:charts', 'compare:logic', 'compare:duration']
_IMPACT_SEC = 'compare:impact_section'
# The pre-existing items that must stay untouched.
_KEEP = ['compare:impact', 'compare:report']


def _seed(fixture):
    """Seed a project whose snapshot points at the real fixture, so the two-/three-file
    recompute path (ctx.parsed / ctx.xml_path) works."""
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
    return pid


def _compare_items(ctx):
    groups = {g['feature']: g for g in registry.catalog(ctx)}
    assert 'compare' in groups, 'Consultant Review group missing from catalog'
    return groups['compare']['items']


# ── the new items exist beside the kept ones ──────────────────────────────────
def test_new_section_items_present(temp_db, xml_path):
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))
    ids = [i['id'] for i in _compare_items(ctx)]
    for iid in _SECTION_IDS + [_IMPACT_SEC] + _KEEP:
        assert iid in ids, iid


# ── no inputs → honestly gated, never raises, never fabricates ────────────────
def test_needs_input_without_attachment(temp_db, xml_path):
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))          # nothing attached
    items = {i['id']: i for i in _compare_items(ctx)}
    for iid in _SECTION_IDS + [_IMPACT_SEC]:
        assert items[iid]['availability'] == 'needs_input', iid
        assert items[iid]['requires'], iid          # declares what to attach
    # the impact section declares the extra 'corrected' role on top of 'baseline'
    roles = {r['role'] for r in items[_IMPACT_SEC]['requires']}
    assert 'baseline' in roles and 'corrected' in roles
    # producing with nothing attached is no_data, never an exception
    for r in registry.render(ctx, _SECTION_IDS + [_IMPACT_SEC]):
        assert r['payload']['kind'] == 'no_data', r['id']


# ── baseline only → two-file sections ready + render real content ─────────────
def test_two_file_sections_ready_with_baseline(temp_db, xml_path):
    registry.clear_providers()
    pid = _seed(xml_path)
    # fixture stands in as its own baseline → the two-file sections turn ready
    ctx = SpecialContext(pid, inputs={'baseline': str(xml_path)})
    items = {i['id']: i for i in _compare_items(ctx)}
    for iid in _SECTION_IDS:
        assert items[iid]['availability'] == 'ready', iid
    # the impact section still needs the corrected 3rd file
    assert items[_IMPACT_SEC]['availability'] == 'needs_input'

    # availability complements produce: every ready section renders a real html payload
    for r in registry.render(ctx, _SECTION_IDS):
        assert r['payload']['kind'] == 'html', r['id']
        assert r['payload'].get('html', '').strip(), r['id']       # non-empty markup
        assert 'srf-compare' in r['payload']['html'], r['id']       # feature markup wrapped
    # the impact section, still gated, produces no_data (not an empty 'ready' render)
    imp = registry.render(ctx, [_IMPACT_SEC])[0]
    assert imp['payload']['kind'] == 'no_data'


# ── baseline + corrected → impact section ready + renders real content ────────
def test_impact_section_ready_with_corrected(temp_db, xml_path):
    registry.clear_providers()
    pid = _seed(xml_path)
    # fixture stands in as baseline AND corrected → the impact section turns ready
    ctx = SpecialContext(pid, inputs={'baseline': str(xml_path), 'corrected': str(xml_path)})
    items = {i['id']: i for i in _compare_items(ctx)}
    assert items[_IMPACT_SEC]['availability'] == 'ready'

    r = registry.render(ctx, [_IMPACT_SEC])[0]
    assert r['payload']['kind'] == 'html'
    assert r['payload'].get('html', '').strip()
    assert 'srf-compare' in r['payload']['html']


# ── the kept items are unchanged and still gated on the baseline ──────────────
def test_kept_items_unchanged(temp_db, xml_path):
    registry.clear_providers()
    pid = _seed(xml_path)
    # no inputs → the kept KPI + full report are needs_input, produce no_data
    ctx0 = SpecialContext(pid)
    items0 = {i['id']: i for i in _compare_items(ctx0)}
    for iid in _KEEP:
        assert items0[iid]['availability'] == 'needs_input', iid
    for r in registry.render(ctx0, _KEEP):
        assert r['payload']['kind'] == 'no_data', r['id']
    # baseline attached → ready + render real content
    ctx1 = SpecialContext(pid, inputs={'baseline': str(xml_path)})
    items1 = {i['id']: i for i in _compare_items(ctx1)}
    for iid in _KEEP:
        assert items1[iid]['availability'] == 'ready', iid
    for r in registry.render(ctx1, _KEEP):
        assert r['payload']['kind'] != 'no_data', r['id']


# ── every ready item across the group renders (blanket availability↔produce) ──
def test_every_ready_item_renders_content(temp_db, xml_path):
    registry.clear_providers()
    pid = _seed(xml_path)
    ctx = SpecialContext(pid, inputs={'baseline': str(xml_path), 'corrected': str(xml_path)})
    items = _compare_items(ctx)
    ready_ids = [i['id'] for i in items if i['availability'] == 'ready']
    assert ready_ids
    for r in registry.render(ctx, ready_ids):
        assert r['payload']['kind'] != 'no_data', r['id']
