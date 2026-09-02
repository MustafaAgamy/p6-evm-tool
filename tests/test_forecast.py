"""Tests for p6_evm.forecast.build_forecast — the Weather → Forecast finish-date model.

best = the schedule's own forecast finish; likely = remaining time stretched by 1/SPI;
worst = likely + the weather impact Calendar Audit already computed (reused, not
recomputed). Guarded throughout: no finish → no scenarios; no weather → no worst case.
"""
from datetime import date

from p6_evm.forecast import build_forecast


def _r(**kw):
    base = {'data_date': '2026-08-31', 'expected_finish': '2027-08-31',
            'baseline_finish': '2027-06-30', 'spi': 0.66}
    base.update(kw)
    return base


def _scen(f, key):
    return next((s for s in f['scenarios'] if s['key'] == key), None)


def test_best_is_the_schedule_forecast_finish():
    f = build_forecast(_r())
    best = _scen(f, 'best')
    assert best['date'] == '2027-08-31'
    assert best['delta_days'] == (date(2027, 8, 31) - date(2027, 6, 30)).days   # +62 vs baseline


def test_likely_stretches_by_spi_and_equals_best_at_spi_1():
    slow = _scen(build_forecast(_r(spi=0.5)), 'likely')
    assert slow['date'] > '2027-08-31'                       # SPI<1 pushes the finish out
    on_plan = _scen(build_forecast(_r(spi=1.0)), 'likely')
    assert on_plan['date'] == '2027-08-31'                   # SPI=1 → no stretch


def test_worst_adds_weather_when_present():
    f = build_forecast(_r(spi=1.0), weather={'weather_adjusted_finish': '2027-10-15'})
    assert f['has_weather'] is True
    assert f['weather_days'] == (date(2027, 10, 15) - date(2027, 8, 31)).days
    worst = _scen(f, 'worst')
    assert worst is not None and worst['date'] > '2027-08-31'


def test_weather_net_finish_delay_fallback():
    f = build_forecast(_r(spi=1.0), weather={'net_finish_delay': 20})
    assert f['has_weather'] is True and f['weather_days'] == 20


def test_no_weather_means_no_worst_case():
    f = build_forecast(_r())
    assert f['has_weather'] is False
    assert _scen(f, 'worst') is None
    assert {s['key'] for s in f['scenarios']} == {'best', 'likely'}


def test_no_finish_yields_no_scenarios():
    f = build_forecast({'data_date': '2026-08-31', 'spi': 0.7})
    assert f['scenarios'] == []


def test_empty_result_is_safe():
    f = build_forecast({})
    assert f['scenarios'] == [] and f['has_weather'] is False
