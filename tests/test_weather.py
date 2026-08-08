"""Task 7 — p6_calendar.weather: bad-weather-day classification and impact.
Pure/deterministic; network lives in fetch_weather() and is not exercised here.
Weather output is an ESTIMATE, kept separate from the exact P6 figures."""
from datetime import date
from p6_evm.calendars import Calendar
from p6_calendar.weather import (
    classify_day, bad_weather_days, weather_impact, DEFAULT_THRESHOLDS,
)


def _cal():
    # Sun–Thu working, Fri+Sat off; 8h/day (flat).
    return Calendar(object_id='C', name='6d', nonworking_days={'Friday', 'Saturday'}, day_hours=8.0)


def test_classify_day_conditions():
    assert classify_day({'rain_mm': 12}, DEFAULT_THRESHOLDS)[0] is True
    assert 'rain' in classify_day({'rain_mm': 12}, DEFAULT_THRESHOLDS)[1].lower()
    assert classify_day({'temp_max_c': 47}, DEFAULT_THRESHOLDS)[0] is True
    assert 'heat' in classify_day({'temp_max_c': 47}, DEFAULT_THRESHOLDS)[1].lower()
    assert classify_day({'wind_kmh': 55}, DEFAULT_THRESHOLDS)[0] is True
    assert classify_day({'dust': True}, DEFAULT_THRESHOLDS)[0] is True
    assert classify_day({'rain_mm': 1, 'temp_max_c': 30, 'wind_kmh': 10}, DEFAULT_THRESHOLDS)[0] is False


def test_bad_weather_days_map():
    daily = {
        date(2025, 6, 3):  {'rain_mm': 15},
        date(2025, 6, 4):  {'rain_mm': 0, 'temp_max_c': 35},
        date(2025, 6, 10): {'dust': True},
    }
    bad = bad_weather_days(daily, DEFAULT_THRESHOLDS)
    assert set(bad.keys()) == {date(2025, 6, 3), date(2025, 6, 10)}


def _impact(**over):
    cal = _cal()
    daily = {
        date(2025, 6, 3):  {'rain_mm': 15},   # Tue — working
        date(2025, 6, 7):  {'rain_mm': 20},   # Sat — weekend (must NOT count)
        date(2025, 6, 10): {'dust': True},    # Tue — working
        date(2025, 6, 25): {'rain_mm': 12},   # Wed — working, after M1
    }
    args = dict(
        calendars={'C': cal},
        construction_cal_ids={'C'},
        milestones=[{'name': 'M1', 'date': date(2025, 6, 20), 'cal_id': 'C'}],
        data_date=date(2025, 6, 1),
        project_finish=date(2025, 6, 30),
        daily_weather=daily,
        forecast_horizon=date(2025, 6, 8),
        thresholds=DEFAULT_THRESHOLDS,
    )
    args.update(over)
    return weather_impact(**args)


def test_milestone_net_delay_ignores_weekends():
    r = _impact()
    m = r['milestones'][0]
    # bad working days before 20 Jun: 3 Jun + 10 Jun = 2 (7 Jun is a weekend → excluded)
    assert m['net_delay'] == 2
    assert m['already_allowed'] == 1          # 7 Jun fell on a non-working day
    assert m['bad_days_before'] == 3


def test_weather_adjusted_finish_and_total():
    r = _impact()
    # working bad days up to 30 Jun: 3, 10, 25 = 3
    assert r['net_finish_delay'] == 3
    assert r['weather_adjusted_finish'] > '2025-06-30'   # ISO string, pushed out
    assert r['expected_bad_days_total'] >= 3


def test_daily_list_confidence_split():
    r = _impact()
    conf = {d['date']: d['confidence'] for d in r['bad_days']}
    assert conf['2025-06-03'] == 'forecast'   # <= horizon (8 Jun)
    assert conf['2025-06-25'] == 'expected'   # beyond horizon


def test_recovery_recommendations_present():
    r = _impact()
    assert isinstance(r['recovery'], list) and len(r['recovery']) >= 1
    rec = r['recovery'][0]
    assert 'days' in rec and rec['days'] >= 1
    assert rec.get('option_longer_days') and rec.get('option_extra_days')


def test_no_location_no_construction_is_safe():
    # No construction calendars → no impact, empty lists, zero delay.
    r = _impact(construction_cal_ids=set())
    assert r['net_finish_delay'] == 0
    assert r['milestones'][0]['net_delay'] == 0
