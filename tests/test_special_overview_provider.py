"""Tests for the Overview Special Report provider.

The Overview provider mirrors the Project ▸ Overview screen exactly: a 10-tile
"Key indicators" grid and a "Progress by category" bar list. These tests assert:
  * the KPI grid has the screen's ten tiles in order, with the screen's formatting
    (SPI/CPI as ratios; PV/EV/AC exact and comma-grouped) and the screen's colours
    (SPI reddens below 1.0; Delay reddens when behind),
  * the category bars are a chartable ``bars`` payload (one row per WBS category),
  * both items are registered in the catalog,
  * availability is gated on the stored EVM result / categories.
"""
import db
from p6_special import registry
from p6_special.providers import overview
from p6_special.context import SpecialContext


def _seed(fixture, spi=0.6, cpi=0.857, delay=5, with_cats=True):
    pid = db.upsert_project('OV1', 'Overview Fixture')
    sid = db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    db.insert_metrics(sid, {
        'pv': 1e6, 'ev': 6e5, 'ac': 7e5, 'spi': spi, 'cpi': cpi, 'delay_days': delay,
        'overall_planned_pct': 0.61, 'overall_actual_pct': 0.40, 'variance': -0.21,
    })
    if with_cats:
        db.insert_category_metrics(sid, {
            'Construction': {'weight': 0.8, 'planned_pct': 0.58, 'actual_pct': 0.38,
                             'bac': 1e6, 'ac': 7e5, 'activity_count': 50, 'overridden': False},
            'Engineering': {'weight': 0.2, 'planned_pct': 0.70, 'actual_pct': 0.60,
                            'bac': 3e5, 'ac': 1e5, 'activity_count': 20, 'overridden': False},
        })
    return pid, sid


def _items(ctx):
    return {i.id: i for i in overview.provide(ctx)}


# ── key indicators grid ───────────────────────────────────────────────────────
def test_kpi_grid_has_ten_screen_tiles(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    ctx = SpecialContext(pid, snapshot_id=sid)
    pl = _items(ctx)['overview:kpis'].produce(ctx)
    assert pl['kind'] == 'kpi_group'
    labels = [t['label'] for t in pl['items']]
    assert labels == ['SPI · schedule', 'Forecast finish', 'Delay', 'Baseline finish',
                      'Overall planned', 'Overall actual', 'Planned value',
                      'Earned value', 'Actual cost', 'CPI · cost']


def test_kpi_grid_spi_is_ratio_and_reddens_below_one(temp_db, xml_path):
    pid, sid = _seed(xml_path, spi=0.6)
    ctx = SpecialContext(pid, snapshot_id=sid)
    tiles = {t['label']: t for t in _items(ctx)['overview:kpis'].produce(ctx)['items']}
    spi = tiles['SPI · schedule']
    assert spi['value'] == '0.60'          # ratio here (the Overview screen), not a percent
    assert spi['tone'] == 'bad'            # spi < 1 → red, like the screen
    # CPI shows as a ratio too, and the screen does not colour it
    assert tiles['CPI · cost']['value'] == '0.86'
    assert tiles['CPI · cost']['tone'] == 'neutral'


def test_kpi_grid_spi_not_red_at_or_above_one(temp_db, xml_path):
    pid, sid = _seed(xml_path, spi=1.05)
    ctx = SpecialContext(pid, snapshot_id=sid)
    tiles = {t['label']: t for t in _items(ctx)['overview:kpis'].produce(ctx)['items']}
    assert tiles['SPI · schedule']['tone'] == 'neutral'


def test_kpi_grid_money_is_exact_and_comma_grouped(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    ctx = SpecialContext(pid, snapshot_id=sid)
    tiles = {t['label']: t for t in _items(ctx)['overview:kpis'].produce(ctx)['items']}
    assert tiles['Planned value']['value'] == '1,000,000'   # exact, not '1.00M'
    assert tiles['Earned value']['value'] == '600,000'
    assert tiles['Actual cost']['value'] == '700,000'


def test_kpi_grid_delay_reddens_when_behind(temp_db, xml_path):
    pid, sid = _seed(xml_path, delay=5)
    ctx = SpecialContext(pid, snapshot_id=sid)
    tiles = {t['label']: t for t in _items(ctx)['overview:kpis'].produce(ctx)['items']}
    d = tiles['Delay']
    assert d['value'] == '5 d'
    assert d['tone'] == 'bad'


def test_kpi_grid_availability(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    ctx = SpecialContext(pid, snapshot_id=sid)
    assert _items(ctx)['overview:kpis'].availability(ctx) == 'ready'
    assert overview.provide(SpecialContext(9999))[0].availability(SpecialContext(9999)) == 'no_data'


# ── progress by category ──────────────────────────────────────────────────────
def test_category_bars_is_chartable_payload(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    ctx = SpecialContext(pid, snapshot_id=sid)
    pl = _items(ctx)['overview:categories'].produce(ctx)
    assert pl['kind'] == 'bars'
    assert len(pl['rows']) == 2                        # one row per WBS category
    assert [s['label'] for s in pl['series']] == ['Planned', 'Actual']


def test_category_bars_availability(temp_db, xml_path):
    pid, sid = _seed(xml_path, with_cats=False)
    ctx = SpecialContext(pid, snapshot_id=sid)
    assert _items(ctx)['overview:categories'].availability(ctx) == 'no_data'


# ── registration ─────────────────────────────────────────────────────────────
def test_both_items_registered_in_catalog(temp_db, xml_path):
    registry.clear_providers()
    pid, sid = _seed(xml_path)
    ctx = SpecialContext(pid, snapshot_id=sid)
    ids = {i['id'] for g in registry.catalog(ctx) for i in g['items']}
    assert 'overview:kpis' in ids
    assert 'overview:categories' in ids
