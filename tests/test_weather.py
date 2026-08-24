"""Task 7 — p6_calendar.weather: bad-weather-day classification and impact.
Pure/deterministic; network lives in fetch_weather() and is not exercised here.
Weather output is an ESTIMATE, kept separate from the exact P6 figures."""
from datetime import date
from p6_evm.calendars import Calendar
from p6_calendar.weather import (
    classify_day, bad_weather_days, weather_impact, DEFAULT_THRESHOLDS,
    SITE_TYPES, resolve_site_thresholds, build_criteria, limit_performance,
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


def test_wbs_brief_uses_nearest_named_wbs(tmp_path):
    """When the activity's direct WBS node is unnamed (common in P6), the brief uses the
    nearest NAMED ancestor — the 'Pile Works' level — not the activity name."""
    import textwrap
    from p6_evm.parser import parse_file
    from p6_calendar.weather import weather_inputs
    xml = textwrap.dedent('''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Calendar><ObjectId>C1</ObjectId><Name>c</Name><IsDefault>true</IsDefault></Calendar>
      <Project><ObjectId>1</ObjectId><Id>P</Id><Name>P</Name>
        <DataDate>2025-01-01T00:00:00</DataDate><ScheduledFinishDate>2025-12-31T00:00:00</ScheduledFinishDate>
        <WBS><ObjectId>10</ObjectId><Name>Construction</Name><ParentObjectId></ParentObjectId></WBS>
        <WBS><ObjectId>20</ObjectId><Name>Pile Works</Name><ParentObjectId>10</ParentObjectId></WBS>
        <WBS><ObjectId>30</ObjectId><Name></Name><ParentObjectId>20</ParentObjectId></WBS>
        <Activity><ObjectId>A1</ObjectId><Id>A1</Id><Name>Drilling</Name><Status>Not Started</Status>
          <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>30</WBSObjectId><PercentComplete>0</PercentComplete>
          <PlannedStartDate>2025-06-01T00:00:00</PlannedStartDate><PlannedFinishDate>2025-06-10T00:00:00</PlannedFinishDate></Activity>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / 's.xml'; p.write_text(xml, encoding='utf-8')
    acts = weather_inputs(parse_file(str(p)))['construction_activities']
    assert acts and acts[0]['wbs'] == 'Pile Works'   # nearest named WBS, not the unnamed leaf or 'Drilling'


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


# ── Multi-calendar consistency (the grain-terminal discrepancy fix) ──────────

def _multi_cal():
    """A dominant 5-day construction calendar + a degenerate 24h/all-off calendar,
    mirroring the grain terminal (Roots Silos 6591 vs the 24-Hrs 6592)."""
    main = Calendar(object_id='MAIN', name='Main 6d',
                    nonworking_days={'Friday', 'Saturday'}, day_hours=8.0)
    cont = Calendar(object_id='CONT', name='24h',
                    nonworking_days={'Monday', 'Tuesday', 'Wednesday', 'Thursday',
                                     'Friday', 'Saturday', 'Sunday'}, day_hours=24.0)
    return main, cont


def test_reference_calendar_is_the_one_with_most_activities():
    """Ibrahim's rule: the calendar that decides working vs non-working is the one MOST
    construction activities are assigned to — chosen deterministically, never set-order."""
    main, cont = _multi_cal()
    daily = {date(2025, 6, 3): {'rain_mm': 15}}      # Tue — working on MAIN, 'off' on CONT
    r = weather_impact(
        calendars={'MAIN': main, 'CONT': cont},
        construction_cal_ids={'MAIN', 'CONT'},
        construction_cal_counts={'MAIN': 1438, 'CONT': 17},   # MAIN dominates (like 6591)
        milestones=[{'name': 'Completion', 'date': date(2025, 6, 20), 'cal_id': 'CONT'}],
        data_date=date(2025, 6, 1), project_finish=date(2025, 6, 30),
        daily_weather=daily, forecast_horizon=date(2025, 6, 8),
        thresholds=DEFAULT_THRESHOLDS)
    bd = next(d for d in r['bad_days'] if d['date'] == '2025-06-03')
    assert bd['effect'].startswith('Non-working')            # a working (lost) day, not "falls on non-working"
    assert r['net_finish_delay'] == 1                        # counted on the dominant calendar
    # day-list, finish AND milestone all agree (even though the milestone's own cal is CONT)
    assert r['milestones'][0]['net_delay'] == 1
    assert r['weather_adjusted_finish'] > '2025-06-30'


def test_degenerate_24h_calendar_never_becomes_the_reference():
    """Even if the degenerate all-days-off (24h) calendar has MORE activities, it must not
    be the reference — it would mark every bad day non-working and hide the real slip."""
    main, cont = _multi_cal()
    daily = {date(2025, 6, 3): {'rain_mm': 15}}      # Tue
    r = weather_impact(
        calendars={'MAIN': main, 'CONT': cont},
        construction_cal_ids={'MAIN', 'CONT'},
        construction_cal_counts={'MAIN': 5, 'CONT': 100},     # CONT has more, but is degenerate
        milestones=[], data_date=date(2025, 6, 1), project_finish=date(2025, 6, 30),
        daily_weather=daily, forecast_horizon=date(2025, 6, 8), thresholds=DEFAULT_THRESHOLDS)
    assert r['net_finish_delay'] == 1                        # still counts on MAIN, not the 24h calendar
    assert next(d for d in r['bad_days'] if d['date'] == '2025-06-03')['effect'].startswith('Non-working')


def test_finish_equals_completion_milestone_no_contradiction():
    """The headline weather-adjusted finish must equal the completion milestone's adjusted
    date when they share the project-finish date — no dashboard-vs-table contradiction."""
    main, cont = _multi_cal()
    daily = {date(2025, 6, 3): {'rain_mm': 15}, date(2025, 6, 10): {'rain_mm': 15}}  # both Tue, working
    finish = date(2025, 6, 30)
    r = weather_impact(
        calendars={'MAIN': main, 'CONT': cont},
        construction_cal_ids={'MAIN', 'CONT'},
        construction_cal_counts={'MAIN': 100, 'CONT': 3},
        milestones=[{'name': 'Project Completion', 'date': finish, 'cal_id': 'MAIN'}],
        data_date=date(2025, 6, 1), project_finish=finish,
        daily_weather=daily, forecast_horizon=date(2025, 6, 8), thresholds=DEFAULT_THRESHOLDS)
    completion = next(m for m in r['milestones'] if m['name'] == 'Project Completion')
    assert r['weather_adjusted_finish'] == completion['adjusted']   # dashboard == table
    assert r['net_finish_delay'] == completion['net_delay'] == 2


# ── Multi-year climate history (representative year + monthly average) ───────

def _yearly(*vals):
    """{year: {rain_mm}} for the last len(vals) years, newest year last."""
    return {2021 + i: {'rain_mm': v} for i, v in enumerate(vals)}


def test_representative_year_drives_the_day_list():
    """Beyond the forecast, the day-list uses a TYPICAL (representative) year — the one whose
    bad-day count is closest to the N-year average — so a single freak year can't skew it, and
    the delay reflects a normal year's exposure (a strict exact-date match undercounts)."""
    cal = _cal()
    d1 = date(2025, 6, 17)   # Tue (working)
    d2 = date(2025, 6, 24)   # Tue (working)
    # d1: bad in years {2021,2022,2023} ; d2: bad only in 2021 (a high year).
    climate = {
        d1: _yearly(12, 9, 8, 0, 0),    # bad 3 yrs
        d2: _yearly(20, 0, 0, 0, 0),    # bad 1 yr
    }
    r = weather_impact(
        calendars={'C': cal}, construction_cal_ids={'C'}, milestones=[],
        data_date=date(2025, 6, 1), project_finish=date(2025, 6, 30),
        daily_weather={}, forecast_horizon=date(2025, 6, 8),
        climate_samples=climate, climate_meta={'years': 5, 'year_start': 2021, 'year_end': 2025},
        thresholds=DEFAULT_THRESHOLDS)
    # per-year totals: 2021→2 (d1,d2), 2022→1, 2023→1, 2024→0, 2025→0 ; mean 0.8 → rep year 2022 or 2023 (count 1)
    assert r['climate_reference']['representative_year'] in (2022, 2023)
    # a representative (count-1) year has exactly one bad day → d1 (bad in 2022/2023), not d2
    assert [d['date'] for d in r['bad_days']] == ['2025-06-17']
    assert all(d['confidence'] == 'expected' for d in r['bad_days'])
    assert r['climate_avg_total'] == 1                    # round(mean 0.8)


def test_monthly_bars_carry_average_and_range():
    cal = _cal()
    climate = {
        date(2025, 6, 17): _yearly(12, 9, 8, 0, 0),   # bad 3 of 5 yrs
        date(2025, 6, 24): _yearly(20, 0, 0, 0, 0),   # bad 1 of 5 yrs
    }
    r = weather_impact(
        calendars={'C': cal}, construction_cal_ids={'C'}, milestones=[],
        data_date=date(2025, 6, 1), project_finish=date(2025, 6, 30),
        daily_weather={}, forecast_horizon=date(2025, 6, 8),
        climate_samples=climate, thresholds=DEFAULT_THRESHOLDS)
    jun = next(m for m in r['monthly'] if m['label'] == 'Jun 2025')
    # per-year June counts: 2021→2, 2022→1, 2023→1, 2024→0, 2025→0 → avg 0.8, range 0–2
    assert jun['avg'] == 0.8 and jun['lo'] == 0 and jun['hi'] == 2


def test_forecast_day_kept_near_term():
    """A near-term FORECAST bad day is shown from the live forecast, labelled 'forecast'."""
    cal = _cal()
    r = weather_impact(
        calendars={'C': cal}, construction_cal_ids={'C'}, milestones=[],
        data_date=date(2025, 6, 1), project_finish=date(2025, 6, 30),
        daily_weather={date(2025, 6, 3): {'rain_mm': 15}},   # Tue, within horizon
        forecast_horizon=date(2025, 6, 8),
        climate_samples={date(2025, 6, 3): _yearly(0, 0, 0, 0, 0)},   # climate present
        thresholds=DEFAULT_THRESHOLDS)
    day = next(d for d in r['bad_days'] if d['date'] == '2025-06-03')
    assert day['confidence'] == 'forecast'


def test_climate_reference_in_result():
    ref = _impact()['climate_reference']
    assert 'ERA5' in ref['history_source'] and ref['history_url']
    assert ref['forecast_source'] == 'Open-Meteo'
    assert 'avg_total' in ref and 'representative_year' in ref


# ── Site-type presets (the East Port Said fix) ───────────────────────────────

def test_desert_preset_equals_current_default():
    """The 'no numbers change' guarantee: today's exact limits ARE the Desert preset."""
    assert SITE_TYPES['desert']['thresholds'] == DEFAULT_THRESHOLDS


def test_site_type_catalog_shape():
    for key in ('desert', 'marine', 'coastal', 'building'):
        st = SITE_TYPES[key]
        assert st['label'] and st['blurb']
        assert set(st['thresholds']) == {'rain_mm', 'temp_max_c', 'wind_kmh', 'dust'}
    # Marine is the fix: wind ON, heat lower than the desert 42.
    assert SITE_TYPES['marine']['thresholds']['wind_kmh'] == 35.0
    assert SITE_TYPES['marine']['thresholds']['temp_max_c'] == 40.0
    # Desert leaves wind off.
    assert SITE_TYPES['desert']['thresholds']['wind_kmh'] is None


def test_resolve_site_thresholds():
    assert resolve_site_thresholds('marine')['wind_kmh'] == 35.0
    # unknown / None → today's default behaviour, unchanged
    assert resolve_site_thresholds(None) == DEFAULT_THRESHOLDS
    assert resolve_site_thresholds('nope') == DEFAULT_THRESHOLDS
    # explicit edits win over the preset (a user tweak → Custom)
    assert resolve_site_thresholds('marine', {'wind_kmh': 30})['wind_kmh'] == 30
    # a returned dict is a copy — mutating it must not corrupt the catalog
    resolve_site_thresholds('marine')['wind_kmh'] = 999
    assert SITE_TYPES['marine']['thresholds']['wind_kmh'] == 35.0


def test_build_criteria_order_off_and_marine_framing():
    rows = build_criteria('marine', resolve_site_thresholds('marine'))
    assert [r['key'] for r in rows] == ['wind', 'heat', 'rain', 'dust']   # wind first (dominant)
    wind = rows[0]
    assert wind['on'] is True and '35' in wind['value']
    assert 'marine' in wind['explain'].lower() or 'crane' in wind['explain'].lower()
    # Desert → wind shown as off.
    dwind = build_criteria('desert', resolve_site_thresholds('desert'))[0]
    assert dwind['on'] is False and dwind['value'] == 'off'
    # Custom limits still render truthfully.
    crit = build_criteria('custom', {'rain_mm': None, 'temp_max_c': 38, 'wind_kmh': 30, 'dust': False})
    by = {r['key']: r for r in crit}
    assert by['rain']['on'] is False and by['rain']['value'] == 'off'
    assert by['dust']['on'] is False
    assert by['heat']['on'] is True and '38' in by['heat']['value']


def test_limit_performance_peak_and_flagged():
    daily = {
        date(2025, 6, 2):  {'wind_kmh': 41, 'temp_max_c': 30, 'rain_mm': 0},   # wind flags
        date(2025, 6, 5):  {'wind_kmh': 20, 'temp_max_c': 41.3, 'rain_mm': 1}, # nothing (heat<42/wind<35)
        date(2025, 6, 9):  {'wind_kmh': 36, 'temp_max_c': 25, 'rain_mm': 8.3}, # wind + rain flag
        date(2025, 5, 30): {'wind_kmh': 99, 'temp_max_c': 99, 'rain_mm': 99},  # BEFORE data date → ignored
    }
    by = {p['key']: p for p in limit_performance(
        daily, date(2025, 6, 1), date(2025, 6, 30), resolve_site_thresholds('marine'))}
    assert by['wind']['on'] is True
    assert by['wind']['flagged'] == 2                 # 41 and 36 ≥ 35 (the pre-window 99 excluded)
    assert abs(by['wind']['peak'] - 41) < 1e-6        # peak over the window only
    assert by['heat']['flagged'] == 1                 # 41.3 ≥ the marine 40 °C limit
    assert abs(by['heat']['peak'] - 41.3) < 1e-6      # hottest expected day shown
    assert by['rain']['flagged'] == 1                 # only the 8.3 mm day

    # The real East Port Said story: under the DESERT limit (42 °C) the hottest day
    # (41.3) never reaches it → flagged 0, but the peak is still reported so the user
    # sees WHY heat found nothing.
    d = {p['key']: p for p in limit_performance(
        daily, date(2025, 6, 1), date(2025, 6, 30), resolve_site_thresholds('desert'))}
    assert d['heat']['flagged'] == 0 and abs(d['heat']['peak'] - 41.3) < 1e-6
    assert d['wind']['on'] is False                   # desert leaves wind off


def test_weather_impact_emits_site_type_and_criteria():
    r = _impact(site_type='marine',
                thresholds=resolve_site_thresholds('marine'))
    assert r['site_type'] == 'marine'
    assert r['site_type_label'] == SITE_TYPES['marine']['label']
    assert [c['key'] for c in r['criteria']] == ['wind', 'heat', 'rain', 'dust']
    assert isinstance(r['limit_performance'], list) and r['limit_performance']
    # backward-compatible: no site type → still works, label is None
    r0 = _impact()
    assert r0['site_type'] is None and r0['criteria']
