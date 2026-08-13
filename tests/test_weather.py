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
    # rain ≥ 5, heat ≥ 42, dust on, wind OFF by default
    assert classify_day({'rain_mm': 12}, DEFAULT_THRESHOLDS)[0] is True
    assert 'rain' in classify_day({'rain_mm': 12}, DEFAULT_THRESHOLDS)[1].lower()
    assert classify_day({'temp_max_c': 43}, DEFAULT_THRESHOLDS)[0] is True     # ≥ 42
    assert classify_day({'temp_max_c': 41}, DEFAULT_THRESHOLDS)[0] is False    # under 42
    assert classify_day({'dust': True}, DEFAULT_THRESHOLDS)[0] is True
    assert classify_day({'wind_kmh': 55}, DEFAULT_THRESHOLDS)[0] is False      # wind off by default
    assert classify_day({'wind_kmh': 55}, {'wind_kmh': 40})[0] is True         # explicit wind limit
    assert classify_day({'rain_mm': 2, 'temp_max_c': 39}, DEFAULT_THRESHOLDS)[0] is False  # drizzle ignored


def test_classify_day_detail_has_measured_value():
    _, _, detail = classify_day({'temp_max_c': 45.5}, DEFAULT_THRESHOLDS)
    assert '45.5' in detail and '42' in detail          # shows measured value vs limit
    _, _, rdetail = classify_day({'rain_mm': 22}, DEFAULT_THRESHOLDS)
    assert '22' in rdetail and 'mm' in rdetail


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


def test_weather_inputs_from_schedule(tmp_path):
    import textwrap
    from p6_evm.parser import parse_file
    from p6_calendar.weather import weather_inputs
    xml = textwrap.dedent('''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Calendar><ObjectId>C1</ObjectId><Name>6d</Name><IsDefault>true</IsDefault>
        <StandardWorkWeek><StandardWorkHours><DayOfWeek>Friday</DayOfWeek></StandardWorkHours></StandardWorkWeek>
      </Calendar>
      <Project><ObjectId>1</ObjectId><Id>P</Id><Name>P</Name>
        <DataDate>2025-02-01T00:00:00</DataDate><ScheduledFinishDate>2025-12-31T00:00:00</ScheduledFinishDate>
        <WBS><ObjectId>10</ObjectId><Name>Construction Works</Name><ParentObjectId></ParentObjectId></WBS>
        <WBS><ObjectId>20</ObjectId><Name>Engineering</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity><ObjectId>A1</ObjectId><Id>A1</Id><Name>Pour</Name><Status>Not Started</Status>
          <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete>
          <PlannedFinishDate>2025-06-01T00:00:00</PlannedFinishDate></Activity>
        <Activity><ObjectId>A2</ObjectId><Id>A2</Id><Name>Design work</Name><Status>Not Started</Status>
          <Type>Task Dependent</Type><CalendarObjectId>C1</CalendarObjectId><WBSObjectId>20</WBSObjectId><PercentComplete>0</PercentComplete></Activity>
        <Activity><ObjectId>S1</ObjectId><Id>S1</Id><Name>Site handover start</Name><Type>Start Milestone</Type>
          <Status>Not Started</Status><CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId>
          <PercentComplete>0</PercentComplete><PlannedStartDate>2025-02-05T00:00:00</PlannedStartDate></Activity>
        <Activity><ObjectId>M1</ObjectId><Id>M1</Id><Name>Foundations complete</Name><Type>Finish Milestone</Type>
          <Status>Not Started</Status><CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId>
          <PercentComplete>0</PercentComplete><PlannedFinishDate>2025-06-15T00:00:00</PlannedFinishDate></Activity>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / 's.xml'; p.write_text(xml, encoding='utf-8')
    inp = weather_inputs(parse_file(str(p)))
    assert 'C1' in inp['construction_cal_ids']       # construction activity uses C1
    names = [m['name'] for m in inp['milestones']]
    assert 'Foundations complete' in names           # finish milestone included
    assert 'Site handover start' not in names        # START milestone EXCLUDED (finish-only rule)
    assert inp['project_finish'] == date(2025, 12, 31)


def test_no_location_no_construction_is_safe():
    # No construction calendars → no impact, empty lists, zero delay.
    r = _impact(construction_cal_ids=set())
    assert r['net_finish_delay'] == 0
    assert r['milestones'][0]['net_delay'] == 0


def test_by_cause_breakdown():
    r = _impact()
    causes = {c['label']: c['count'] for c in r['by_cause']}
    # remaining bad days (1 Jun < d ≤ 30 Jun): 3 Jun rain, 7 Jun rain, 10 Jun dust, 25 Jun rain
    assert causes['Rain'] == 3
    assert causes['Dust'] == 1
    assert causes['Heat'] == 0
    wind = next(c for c in r['by_cause'] if c['label'] == 'Wind')
    assert wind['count'] == 0 and wind['off'] is True     # wind off by default
    # counts cover every flagged day (matches the KPI total)
    assert sum(causes.values()) == r['expected_bad_days_total']


def test_conclusion_string_reflects_numbers():
    r = _impact()
    c = r['conclusion']
    assert isinstance(c, str) and c
    assert '3 working days' in c            # net finish delay = 3
    assert 'rain' in c.lower()              # dominant cause named
    assert 'P6 Delay' in c                  # honesty line kept


def test_conclusion_no_impact_is_graceful():
    r = _impact(construction_cal_ids=set(), daily_weather={})
    assert 'no weather delay' in r['conclusion'].lower()


def test_bad_days_brief_by_wbs_deduplicated():
    """#07 — each working bad-weather day briefs the affected work BY WBS, de-duplicated:
    the pile activities under 'Pile Works' show as 'Pile Works' once, not one row each."""
    cal = _cal()
    daily = {date(2025, 6, 3): {'rain_mm': 15},   # Tue — working
             date(2025, 6, 10): {'dust': True}}   # Tue — working, nothing scheduled
    acts = [
        {'name': 'Drilling',     'start': date(2025, 6, 1), 'finish': date(2025, 6, 5), 'wbs': 'Pile Works'},
        {'name': 'RFT for pile', 'start': date(2025, 6, 2), 'finish': date(2025, 6, 4), 'wbs': 'Pile Works'},
        {'name': 'Excavation',   'start': date(2025, 6, 1), 'finish': date(2025, 6, 5), 'wbs': 'Earthworks'},
        {'name': 'Paving',       'start': date(2025, 6, 20), 'finish': date(2025, 6, 30), 'wbs': 'Roadworks'},
    ]
    r = weather_impact(
        calendars={'C': cal}, construction_cal_ids={'C'}, construction_activities=acts,
        milestones=[], data_date=date(2025, 6, 1), project_finish=date(2025, 6, 30),
        daily_weather=daily, forecast_horizon=date(2025, 6, 8), thresholds=DEFAULT_THRESHOLDS)
    by_date = {d['date']: d for d in r['bad_days']}
    # 3 Jun: Drilling + RFT (Pile Works) + Excavation (Earthworks) active → deduped by WBS
    assert by_date['2025-06-03']['activities'] == ['Pile Works', 'Earthworks']
    assert by_date['2025-06-03']['activities_count'] == 2   # Pile Works counted once
    assert by_date['2025-06-10']['activities'] == []        # nothing active that date


def test_bad_days_brief_falls_back_to_name_without_wbs():
    """If an activity has no WBS name, its own name is used (still de-duplicated)."""
    cal = _cal()
    daily = {date(2025, 6, 3): {'rain_mm': 15}}
    acts = [{'name': 'Pour', 'start': date(2025, 6, 1), 'finish': date(2025, 6, 5), 'wbs': ''}]
    r = weather_impact(
        calendars={'C': cal}, construction_cal_ids={'C'}, construction_activities=acts,
        milestones=[], data_date=date(2025, 6, 1), project_finish=date(2025, 6, 30),
        daily_weather=daily, forecast_horizon=date(2025, 6, 8), thresholds=DEFAULT_THRESHOLDS)
    assert next(d for d in r['bad_days'] if d['date'] == '2025-06-03')['activities'] == ['Pour']
