"""Tests for the Baseline Narrative Special Report provider.

The provider reuses ``p6_evm.narrative.build_narrative`` on the stored DB result,
so these tests seed a snapshot + metrics (+ a category) via ``temp_db`` and the
``xml_path`` fixture, then assert each item's ``produce(ctx)`` returns a payload
dict without raising, and that availability exactly complements produce().
"""
import db
from p6_special.providers import narrative
from p6_special.context import SpecialContext


def _seed(fixture):
    pid = db.upsert_project('P1', 'Grain')
    sid = db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    db.insert_metrics(sid, {
        'pv': 1e6, 'ev': 6e5, 'ac': 7e5, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 5,
        'overall_planned_pct': 0.614, 'overall_actual_pct': 0.404, 'variance': -0.21,
    })
    db.insert_category_metrics(sid, {
        'Construction': {'weight': 0.855, 'planned_pct': 0.58, 'actual_pct': 0.38,
                         'bac': 1e6, 'ac': 7e5, 'activity_count': 50, 'overridden': False},
    })
    return pid


def _items(ctx):
    return {i.id: i for i in narrative.provide(ctx)}


# ── shape: every item produces a payload dict without raising ─────────────────
def test_every_item_produces_a_payload_dict(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    # status + the 5 sections
    assert set(items) == {
        'narrative:status', 'narrative:summary', 'narrative:schedule',
        'narrative:cost', 'narrative:areas', 'narrative:outlook',
    }
    for iid, it in items.items():
        pl = it.produce(ctx)
        assert isinstance(pl, dict) and pl.get('kind') != 'no_data', iid


def test_status_is_keyvals_mirroring_the_header(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    pl = _items(ctx)['narrative:status'].produce(ctx)
    assert pl['kind'] == 'keyvals'
    pairs = dict(pl['pairs'])
    assert pairs['Project'] == 'Grain'
    assert pairs['Data date'] == '2026-01-01'          # sliced YYYY-MM-DD, like narrative.js
    # SPI 0.6 → 'is significantly behind schedule' → overall tone bad → 'Action needed'.
    assert pairs['Status'] == 'Action needed'


def test_sections_are_text_payloads_with_paragraphs(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    for key in ('summary', 'schedule', 'cost', 'areas', 'outlook'):
        pl = items[f'narrative:{key}'].produce(ctx)
        assert pl['kind'] == 'text'
        assert pl['paragraphs'] and all(isinstance(p, str) and p for p in pl['paragraphs'])


def test_section_text_matches_build_narrative(temp_db, xml_path):
    """The reused generator IS the source of truth — the item text must equal
    build_narrative's own section paragraphs (no divergent hand-rebuild)."""
    from p6_evm.narrative import build_narrative
    ctx = SpecialContext(_seed(xml_path))
    result = ctx.evm
    secs = {s['key']: s for s in build_narrative(result)['sections']}
    for key in ('summary', 'schedule', 'cost', 'areas', 'outlook'):
        pl = _items(ctx)[f'narrative:{key}'].produce(ctx)
        assert pl['paragraphs'] == secs[key]['paragraphs']


def test_item_title_equals_section_heading(temp_db, xml_path):
    from p6_evm.narrative import build_narrative
    ctx = SpecialContext(_seed(xml_path))
    titles = {s['key']: s['title'] for s in build_narrative(ctx.evm)['sections']}
    items = _items(ctx)
    for key, title in titles.items():
        assert items[f'narrative:{key}'].title == title


# ── availability exactly complements produce() ────────────────────────────────
def test_availability_ready_with_stored_result(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    for it in narrative.provide(ctx):
        assert it.availability(ctx) == 'ready'


def test_availability_no_data_without_result(temp_db):
    """No stored result → every item reports 'no_data' AND produce returns the
    NO_DATA sentinel (never a 'ready' item that then renders empty)."""
    ctx = SpecialContext(9999)
    for it in narrative.provide(ctx):
        assert it.availability(ctx) == 'no_data'
        assert it.produce(ctx)['kind'] == 'no_data'
