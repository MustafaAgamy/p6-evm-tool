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


def test_paired_is_a_bars_payload(temp_db, xml_path):
    # Composite EVM results ship DATA (bars / table): the narrative Document renders
    # it in the house style, and the Dashboard turns the same data into a chart.
    ctx = SpecialContext(_seed(xml_path))
    b = _items(ctx)['evm:planned_vs_actual'].produce(ctx)
    assert b['kind'] == 'bars'
    assert b.get('rows')


def test_category_is_a_table_payload(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    t = _items(ctx)['evm:category_table'].produce(ctx)
    assert t['kind'] == 'table'
    assert t.get('rows') and t.get('columns')


def test_availability_ready(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    assert _items(ctx)['evm:planned_pct'].availability(ctx) == 'ready'


def test_availability_needs_run_without_data(temp_db):
    ctx = SpecialContext(9999)
    assert evm.provide(ctx)[0].availability(ctx) == 'needs_run'


def test_gap_gated_no_data_when_absent(temp_db, xml_path):
    """PV-EV gap is optional: with no stored gap it must report 'no_data', not a
    'ready' item that then renders an empty section (silent-empty regression)."""
    ctx = SpecialContext(_seed(xml_path))
    item = _items(ctx)['evm:gap']
    assert item.availability(ctx) == 'no_data'
    assert item.produce(ctx)['kind'] == 'no_data'


def test_gap_ready_and_reuses_report_section_when_present(temp_db, xml_path):
    pid = _seed(xml_path)
    sid = db.get_latest_snapshot_id(pid)
    # The REAL stored gap is a dict {dimension, total_*, groups:[{code,pv,ev,gap,pct_of_gap}]}
    # (p6_evm.gap.gap_by_code) — not a list. Seed the real shape.
    db.save_evm_extras(sid, {'gap': {
        'dimension': 'Discipline', 'total_pv': 1000.0, 'total_ev': 600.0, 'total_gap': 400.0,
        'groups': [{'code': 'CIV', 'pv': 700.0, 'ev': 400.0, 'gap': 300.0, 'pct_of_gap': 75.0},
                   {'code': 'MECH', 'pv': 300.0, 'ev': 200.0, 'gap': 100.0, 'pct_of_gap': 25.0}],
    }})
    ctx = SpecialContext(pid, snapshot_id=sid)
    item = _items(ctx)['evm:gap']
    assert item.availability(ctx) == 'ready'
    pl = item.produce(ctx)
    # Reuses the EVM Report's OWN PV-EV Gap section (exact style), not a generic table.
    assert pl['kind'] == 'html'
    assert 'Gap' in pl['html'] and 'CIV' in pl['html']


def test_gap_no_data_when_stored_shape_is_wrong(temp_db, xml_path):
    # A stray list (the old buggy shape) must NOT advertise 'ready'.
    pid = _seed(xml_path)
    sid = db.get_latest_snapshot_id(pid)
    db.save_evm_extras(sid, {'gap': [{'code': 'CIV'}]})
    ctx = SpecialContext(pid, snapshot_id=sid)
    assert _items(ctx)['evm:gap'].availability(ctx) == 'no_data'
