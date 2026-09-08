"""Tests for the EVM Special Report provider's TREND + discipline-gap items.

These items only re-present the per-snapshot rows already stored in the DB — the
dashboard aggregates stored numbers, it never invents new EVM maths. So the
fixtures seed real snapshots/metrics rows (≥2 for a trend to have ≥2 points) and
assert the payloads are a straight read of those values.
"""
import db
from p6_special.providers import evm
from p6_special.context import SpecialContext


def _cats(planned_c, actual_c, planned_e, actual_e):
    return {
        'Construction': {'weight': 0.80, 'planned_pct': planned_c, 'actual_pct': actual_c,
                         'bac': 1e6, 'ac': 6e5, 'activity_count': 50, 'overridden': False},
        'Engineering': {'weight': 0.20, 'planned_pct': planned_e, 'actual_pct': actual_e,
                        'bac': 2e5, 'ac': 1e5, 'activity_count': 10, 'overridden': False},
    }


def _seed_two(fixture):
    """One project, TWO snapshots on two data dates, each with metrics + categories."""
    pid = db.upsert_project('P1', 'Grain')
    sid1 = db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h1', 10, 2)
    db.insert_metrics(sid1, {
        'pv': 1e6, 'ev': 5e5, 'ac': 6e5, 'spi': 0.50, 'cpi': 0.83, 'delay_days': 8,
        'overall_planned_pct': 0.50, 'overall_actual_pct': 0.30, 'variance': -0.20,
    })
    db.insert_category_metrics(sid1, _cats(0.55, 0.35, 0.60, 0.58))

    sid2 = db.insert_snapshot(pid, '2026-02-01', str(fixture), str(fixture), 'h2', 10, 2)
    db.insert_metrics(sid2, {
        'pv': 1.2e6, 'ev': 7e5, 'ac': 8e5, 'spi': 0.58, 'cpi': 0.875, 'delay_days': 6,
        'overall_planned_pct': 0.614, 'overall_actual_pct': 0.404, 'variance': -0.21,
    })
    # latest snapshot's categories drive the discipline gap:
    #   Construction shortfall 0.58-0.38 = 0.20  → worst
    #   Engineering  shortfall 0.65-0.63 = 0.02  → second
    db.insert_category_metrics(sid2, _cats(0.58, 0.38, 0.65, 0.63))
    return pid


def _seed_one(fixture):
    """One project, a SINGLE snapshot — no trend possible."""
    pid = db.upsert_project('P2', 'Solo')
    sid = db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    db.insert_metrics(sid, {
        'pv': 1e6, 'ev': 6e5, 'ac': 7e5, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 5,
        'overall_planned_pct': 0.614, 'overall_actual_pct': 0.404, 'variance': -0.21,
    })
    db.insert_category_metrics(sid, _cats(0.58, 0.38, 0.65, 0.63))
    return pid


def _items(ctx):
    return {i.id: i for i in evm.provide(ctx)}


# ── trends ────────────────────────────────────────────────────────────────────
def test_trend_spi_cpi_line_two_series_two_points(temp_db, xml_path):
    ctx = SpecialContext(_seed_two(xml_path))
    item = _items(ctx)['evm:trend_spi_cpi']
    assert item.availability(ctx) == 'ready'
    pl = item.produce(ctx)
    assert pl['kind'] == 'line'
    assert len(pl['series']) == 2
    for s in pl['series']:
        assert len(s['points']) >= 2
    # SPI/CPI read straight from the two snapshots, oldest → newest.
    assert pl['series'][0]['points'] == [0.50, 0.58]
    assert pl['series'][1]['points'] == [0.83, 0.875]
    # x-axis is the two data dates; reference line comes from the provider, not hardcoded downstream.
    assert pl['x'] == ['2026-01-01', '2026-02-01']
    assert pl['ref']['value'] == 1.0


def test_trend_delay_and_progress_ready_and_shaped(temp_db, xml_path):
    ctx = SpecialContext(_seed_two(xml_path))
    items = _items(ctx)

    delay = items['evm:trend_delay']
    assert delay.availability(ctx) == 'ready'
    dpl = delay.produce(ctx)
    assert dpl['kind'] == 'line'
    assert dpl['series'][0]['points'] == [8, 6]

    prog = items['evm:trend_progress']
    assert prog.availability(ctx) == 'ready'
    ppl = prog.produce(ctx)
    assert ppl['kind'] == 'line'
    assert ppl['y_max'] == 100
    # fractions scaled to a 0..100 chart
    assert ppl['series'][0]['points'][0] == 50.0            # planned 0.50 * 100
    assert round(ppl['series'][1]['points'][1], 1) == 40.4  # actual 0.404 * 100


def test_trends_no_data_with_single_snapshot(temp_db, xml_path):
    ctx = SpecialContext(_seed_one(xml_path))
    items = _items(ctx)
    for iid in ('evm:trend_spi_cpi', 'evm:trend_delay', 'evm:trend_progress'):
        assert items[iid].availability(ctx) == 'no_data', iid


# ── discipline gap ──────────────────────────────────────────────────────────
def test_discipline_gap_variance_bars_worst_first(temp_db, xml_path):
    ctx = SpecialContext(_seed_two(xml_path))
    item = _items(ctx)['evm:discipline_gap']
    assert item.availability(ctx) == 'ready'
    pl = item.produce(ctx)
    assert pl['kind'] == 'bars'
    assert pl['style'] == 'variance'
    assert all('target' in r for r in pl['rows'])
    # worst (largest planned − actual shortfall) first: Construction (0.20) before Engineering (0.02)
    assert [r['label'] for r in pl['rows']] == ['Construction', 'Engineering']
    # same 0..1 → x100 scale as the category table / paired bars
    assert round(pl['rows'][0]['values'][0], 6) == 38.0   # actual 0.38 * 100
    assert round(pl['rows'][0]['target'], 6) == 58.0      # planned 0.58 * 100
    assert pl['rows'][0]['display'] == ['38.0%']
    assert pl['rows'][0]['target_display'] == '58.0%'
    assert pl['rows'][0]['tone'] == 'bad'              # 20 pt behind
    assert pl['rows'][1]['tone'] == 'warn'             # 2 pt behind (within -0.05)


def test_discipline_gap_no_data_without_categories(temp_db):
    ctx = SpecialContext(9999)
    assert _items(ctx)['evm:discipline_gap'].availability(ctx) == 'no_data'


# ── KPI enrichment (spark + delta vs the previous update) ─────────────────────
def test_headline_kpis_carry_spark_and_delta_with_two_snapshots(temp_db, xml_path):
    ctx = SpecialContext(_seed_two(xml_path))
    items = _items(ctx)
    enriched = 0
    for iid in ('evm:spi', 'evm:cpi', 'evm:delay', 'evm:planned_pct', 'evm:actual_pct'):
        k = items[iid].produce(ctx)['items'][0]
        if k['spark'] is not None and k['delta'] is not None:
            enriched += 1
            assert len(k['spark']) >= 2
            assert isinstance(k['delta'], str)
            assert k['delta_tone'] == 'neutral'
    assert enriched >= 1
    # SPI: spark reads both snapshots; delta is the raw change vs the previous update.
    spi = items['evm:spi'].produce(ctx)['items'][0]
    assert spi['spark'] == [0.50, 0.58]
    assert spi['delta'] == '+0.08'
    assert spi['value'] == '0.58'  # existing value/tone untouched


def test_headline_kpis_no_spark_or_delta_with_one_snapshot(temp_db, xml_path):
    ctx = SpecialContext(_seed_one(xml_path))
    spi = _items(ctx)['evm:spi'].produce(ctx)['items'][0]
    assert spi['spark'] is None
    assert spi['delta'] is None
    assert spi['value'] == '0.60'  # unchanged headline
