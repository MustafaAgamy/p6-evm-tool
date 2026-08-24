"""Tests for the EVM Special Report provider (reference provider)."""
import db
from p6_special.providers import evm
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
    return {i.id: i for i in evm.provide(ctx)}


def test_planned_kpi_scaled_to_percent(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    pl = _items(ctx)['evm:planned_pct'].produce(ctx)
    assert pl['kind'] == 'kpi_group'
    assert pl['items'][0]['value'] == '61.4%'


def test_actual_kpi(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    assert _items(ctx)['evm:actual_pct'].produce(ctx)['items'][0]['value'] == '40.4%'


def test_variance_signed_and_bad_tone(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    v = _items(ctx)['evm:variance'].produce(ctx)['items'][0]
    assert v['value'] == '-21.0%'
    assert v['tone'] == 'bad'


def test_spi_ratio_and_tone(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    s = _items(ctx)['evm:spi'].produce(ctx)['items'][0]
    assert s['value'] == '0.60'
    assert s['tone'] == 'bad'


def test_money_ev(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    assert _items(ctx)['evm:ev'].produce(ctx)['items'][0]['value'] == '600,000'


def test_paired_bars(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    b = _items(ctx)['evm:planned_vs_actual'].produce(ctx)
    assert b['kind'] == 'bars'
    assert b['rows'][0]['display'] == ['61.4%', '40.4%']
    assert b['rows'][0]['values'][0] == 61.4  # 0.614 * 100


def test_category_table(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    t = _items(ctx)['evm:category_table'].produce(ctx)
    assert t['kind'] == 'table'
    assert t['rows'][0][0] == 'Construction'
    assert t['rows'][0][1] == '85.5%'   # weight
    assert t['rows'][0][2] == '58.0%'   # planned


def test_availability_ready(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    assert _items(ctx)['evm:planned_pct'].availability(ctx) == 'ready'


def test_availability_needs_run_without_data(temp_db):
    ctx = SpecialContext(9999)
    assert evm.provide(ctx)[0].availability(ctx) == 'needs_run'
