"""Tests for p6_evm.copilot.build_copilot — the deterministic AI Copilot core.

TIA decomposes the finish slip into to-date / performance / weather; insights are
prioritised (most severe first) and derived from SPI/CPI/delay/category progress.
Pure and guarded — no LLM, no key, no network.
"""
from datetime import date

from p6_evm.copilot import build_copilot, build_forecast, build_insights, build_tia


def _r(**kw):
    base = {'project_name': 'Harbor', 'data_date': '2026-08-31',
            'expected_finish': '2027-08-31', 'baseline_finish': '2027-06-30',
            'spi': 0.66, 'cpi': 1.01,
            'categories': {'Engineering': {'planned_pct': 0.38, 'actual_pct': 0.61},
                           'Construction': {'planned_pct': 0.55, 'actual_pct': 0.30}}}
    base.update(kw)
    return base


def _comp(tia, key):
    return next((c for c in tia['components'] if c['key'] == key), None)


def test_tia_decomposes_the_slip():
    c = build_copilot(_r(), weather={'weather_adjusted_finish': '2027-10-20'})
    tia = c['tia']
    assert _comp(tia, 'to_date')['days'] == (date(2027, 8, 31) - date(2027, 6, 30)).days      # +62
    # performance = likely − best; weather = worst − likely
    perf = _comp(tia, 'performance')['days']
    assert perf > 0                                                     # SPI 0.66 adds slip
    assert _comp(tia, 'weather')['days'] == (date(2027, 10, 20) - date(2027, 8, 31)).days      # +50


def test_tia_no_weather_component_without_weather():
    tia = build_copilot(_r())['tia']
    assert _comp(tia, 'weather') is None
    assert _comp(tia, 'to_date') is not None


def test_insights_prioritised_most_severe_first():
    ins = build_copilot(_r())['insights']
    sev = [i['severity'] for i in ins]
    order = {'high': 0, 'med': 1, 'low': 2}
    assert sev == sorted(sev, key=lambda s: order[s])          # sorted by severity
    assert any('behind schedule' in i['title'].lower() and i['severity'] == 'high' for i in ins)


def test_insight_surfaces_worst_category():
    ins = build_copilot(_r())['insights']
    assert any('Construction' in i['title'] for i in ins)


def test_on_track_project_is_low_severity():
    ins = build_copilot(_r(spi=1.05, cpi=1.05, expected_finish='2027-06-15'))['insights']
    # ahead of schedule + early finish → no high-severity findings
    assert all(i['severity'] != 'high' for i in ins)


def test_has_forecast_flag_and_empty_safe():
    assert build_copilot(_r())['has_forecast'] is True
    empty = build_copilot({})
    assert empty['has_forecast'] is False
    assert empty['insights'] and empty['tia']['components'] == []
