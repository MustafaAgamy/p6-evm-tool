"""Tests for the AI Copilot · TIA Special Report provider.

Seeds the DB the way import does (metrics + categories + evm_extras finish dates +
optional saved weather), then asserts each item produces a payload without raising
and that availability exactly complements produce (a 'ready' item never renders
empty; a missing finish forecast reports 'no_data')."""
import db
from p6_special.providers import copilot
from p6_special.context import SpecialContext


def _seed(fixture, weather=None):
    pid = db.upsert_project('P1', 'Grain')
    sid = db.insert_snapshot(pid, '2026-06-01', str(fixture), str(fixture), 'h', 10, 2)
    db.insert_metrics(sid, {
        'pv': 1e6, 'ev': 6e5, 'ac': 7e5, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 40,
        'overall_planned_pct': 0.614, 'overall_actual_pct': 0.404, 'variance': -0.21,
    })
    db.insert_category_metrics(sid, {
        'Construction': {'weight': 0.6, 'planned_pct': 0.58, 'actual_pct': 0.38,
                         'bac': 1e6, 'ac': 7e5, 'activity_count': 50, 'overridden': False},
        'Engineering': {'weight': 0.4, 'planned_pct': 0.70, 'actual_pct': 0.30,
                        'bac': 5e5, 'ac': 2e5, 'activity_count': 20, 'overridden': False},
    })
    # Finish dates live in evm_extras (the screen's currentResult carries them).
    db.save_evm_extras(sid, {'baseline_finish': '2027-01-01', 'expected_finish': '2027-03-01'})
    if weather:
        db.save_project_settings(pid, {'last_weather': weather})
    return pid


def _items(ctx):
    return {i.id: i for i in copilot.provide(ctx)}


def test_tia_kpis_match_screen(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    pl = _items(ctx)['copilot:tia'].produce(ctx)
    assert pl['kind'] == 'kpi_group'
    by_label = {t['label']: t for t in pl['items']}
    assert {'Baseline finish', 'Likely finish', 'Total impact', 'Worst case'} <= set(by_label)
    # Baseline finish formatted like the screen's en-GB 2-digit/short/numeric read-out.
    assert by_label['Baseline finish']['value'] == '01 Jan 2027'
    # Total impact carries a signed '+N d' slip and a 'bad' tone when late (SPI 0.60).
    tot = by_label['Total impact']
    assert tot['value'].startswith('+') and tot['value'].endswith(' d')
    assert tot['tone'] == 'bad'
    # No weather run → worst case is the '—' / "run weather in Calendar Audit" tile.
    assert by_label['Worst case']['value'] == '—'


def test_drivers_table(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    t = _items(ctx)['copilot:drivers'].produce(ctx)
    assert t['kind'] == 'table'
    assert t['columns'] == ['Component', 'Impact', 'Basis']
    assert t['rows']
    # 'Slippage to date' is the first TIA component (baseline → current forecast finish).
    assert any(r[0] == 'Slippage to date' for r in t['rows'])
    # Impact cell is a coloured (text, tone) tuple carrying the signed '+N d' figure.
    impact = t['rows'][0][1]
    assert isinstance(impact, tuple) and impact[0].endswith(' d')


def test_insights_findings(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    f = _items(ctx)['copilot:insights'].produce(ctx)
    assert f['kind'] == 'findings'
    assert f['items']
    assert {i['severity'] for i in f['items']} <= {'high', 'medium', 'low', 'info'}
    # SPI 0.60 < 0.85 → a High 'significantly behind schedule' insight, most severe first.
    assert f['items'][0]['severity'] == 'high'
    assert 'behind schedule' in f['items'][0]['title'].lower()


def test_worst_case_tile_with_weather(temp_db, xml_path):
    # A saved weather estimate adds the worst-case scenario → a real worst-case date.
    ctx = SpecialContext(_seed(xml_path, weather={'weather_adjusted_finish': '2027-03-20'}))
    pl = _items(ctx)['copilot:tia'].produce(ctx)
    worst = next(t for t in pl['items'] if t['label'] == 'Worst case')
    assert worst['value'] != '—'


def test_availability_ready(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    items = _items(ctx)
    assert items['copilot:tia'].availability(ctx) == 'ready'
    assert items['copilot:drivers'].availability(ctx) == 'ready'
    assert items['copilot:insights'].availability(ctx) == 'ready'


def test_availability_needs_run_without_data(temp_db):
    ctx = SpecialContext(9999)
    for it in copilot.provide(ctx):
        assert it.availability(ctx) == 'needs_run'


def test_tia_no_data_without_finish_forecast(temp_db, xml_path):
    """No stored finish milestone → build_copilot yields no forecast components, so
    the TIA tiles/drivers must report 'no_data' (not 'ready' then empty), while the
    metric-driven insights stay available."""
    pid = db.upsert_project('P2', 'NoFinish')
    sid = db.insert_snapshot(pid, '2026-06-01', str(xml_path), str(xml_path), 'h2', 10, 2)
    db.insert_metrics(sid, {'pv': 1e6, 'ev': 5e5, 'ac': 6e5, 'spi': 0.6, 'cpi': 0.9,
                            'delay_days': None, 'overall_planned_pct': 0.5,
                            'overall_actual_pct': 0.4, 'variance': -0.1})
    # No evm_extras → no baseline_finish/expected_finish → no forecast.
    ctx = SpecialContext(pid)
    items = _items(ctx)
    assert items['copilot:tia'].availability(ctx) == 'no_data'
    assert items['copilot:tia'].produce(ctx)['kind'] == 'no_data'
    assert items['copilot:drivers'].availability(ctx) == 'no_data'
    assert items['copilot:drivers'].produce(ctx)['kind'] == 'no_data'
    # Insights are independent of the finish forecast.
    assert items['copilot:insights'].availability(ctx) == 'ready'
    assert items['copilot:insights'].produce(ctx)['kind'] == 'findings'
