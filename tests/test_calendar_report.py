"""Task 6 — p6_calendar.report.render_calendar_report(result, meta) -> HTML."""
import textwrap
import report_theme
from p6_evm.parser import parse_file
from p6_calendar import calendar_audit
from p6_calendar.report import render_calendar_report

META = {'project_name': 'Test', 'data_date': '2025-02-01',
        'report_date': '07 Aug 2026', 'source_file': 's.xml'}


def _result(tmp_path):
    days = ''.join(
        f'<HolidayOrException><Date>2025-02-{d:02d}T00:00:00</Date></HolidayOrException>'
        for d in range(10, 17))
    content = textwrap.dedent(f'''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Calendar>
        <ObjectId>C1</ObjectId><Name>5 Days/Week</Name><Type>Global</Type><IsDefault>true</IsDefault>
        <HoursPerDay>8</HoursPerDay>
        <StandardWorkWeek>
          <StandardWorkHours><DayOfWeek>Friday</DayOfWeek></StandardWorkHours>
          <StandardWorkHours><DayOfWeek>Saturday</DayOfWeek></StandardWorkHours>
        </StandardWorkWeek>
        <HolidayOrExceptions>
          <HolidayOrException><Date>2025-01-01T00:00:00</Date></HolidayOrException>
          {days}
        </HolidayOrExceptions>
      </Calendar>
      <Project>
        <ObjectId>1</ObjectId><Id>P1</Id><Name>Test</Name>
        <DataDate>2025-02-01T00:00:00</DataDate>
        <PlannedStartDate>2025-01-01T00:00:00</PlannedStartDate>
        <ScheduledFinishDate>2025-03-31T17:00:00</ScheduledFinishDate>
        <WBS><ObjectId>10</ObjectId><Name>Construction</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity><ObjectId>A1</ObjectId><Id>A1</Id><Name>a</Name><Status>Not Started</Status>
          <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete></Activity>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / "s.xml"; p.write_text(content, encoding='utf-8')
    return calendar_audit(parse_file(str(p)), {}, {})


def test_report_has_sections_in_order(tmp_path):
    # The fixture has no in-window holidays, so §3 (holidays only) is dropped; use a fixture
    # that carries a holiday so all five numbered sections render in order.
    html = render_calendar_report(_result_with_holiday(tmp_path), META)
    order = ['1 · Execution Dashboard', '2 · Calendar Timeline &amp; Statistics',
             '3 · Calendar Non-working days', '4 · Working-hours Profile',
             '5 · Calendar Comparison &amp; Usage']
    pos = [html.find(s) for s in order]
    assert all(p != -1 for p in pos), pos
    assert pos == sorted(pos)
    # the deleted sections are gone
    assert 'Monthly Calendar Statistics' not in html
    assert 'Executive Conclusion' not in html
    assert 'Calendar Conflicts</h2>' not in html    # no standalone conflicts section


def _result_with_holiday(tmp_path):
    """Fixture with an in-window single-day holiday (10 Mar 2025) so §3 (holidays only) renders."""
    content = textwrap.dedent('''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Calendar>
        <ObjectId>C1</ObjectId><Name>5 Days/Week</Name><Type>Global</Type><IsDefault>true</IsDefault>
        <HoursPerDay>8</HoursPerDay>
        <StandardWorkWeek>
          <StandardWorkHours><DayOfWeek>Friday</DayOfWeek></StandardWorkHours>
          <StandardWorkHours><DayOfWeek>Saturday</DayOfWeek></StandardWorkHours>
          <StandardWorkHours><DayOfWeek>Sunday</DayOfWeek><WorkTime><Start>08:00:00</Start><Finish>16:00:00</Finish></WorkTime></StandardWorkHours>
          <StandardWorkHours><DayOfWeek>Monday</DayOfWeek><WorkTime><Start>08:00:00</Start><Finish>16:00:00</Finish></WorkTime></StandardWorkHours>
        </StandardWorkWeek>
        <HolidayOrExceptions>
          <HolidayOrException><Date>2025-03-10T00:00:00</Date></HolidayOrException>
        </HolidayOrExceptions>
      </Calendar>
      <Project>
        <ObjectId>1</ObjectId><Id>P1</Id><Name>Test</Name>
        <DataDate>2025-02-01T00:00:00</DataDate>
        <PlannedStartDate>2025-01-01T00:00:00</PlannedStartDate>
        <ScheduledFinishDate>2025-03-31T17:00:00</ScheduledFinishDate>
        <WBS><ObjectId>10</ObjectId><Name>Construction</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity><ObjectId>A1</ObjectId><Id>A1</Id><Name>a</Name><Status>Not Started</Status>
          <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete></Activity>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / "sh.xml"; p.write_text(content, encoding='utf-8')
    return calendar_audit(parse_file(str(p)), {}, {})


def test_report_is_html_and_has_content(tmp_path):
    html = render_calendar_report(_result(tmp_path), META)
    assert html.startswith('<!DOCTYPE html>')
    assert 'Test' in html                       # project name
    assert 'Execution Dashboard' in html        # §1 heading (renamed)
    assert 'Normal Hours' in html               # new dashboard tile
    assert '59' in html                         # total calendar days (forward from the data date)
    assert 'Monthly Calendar View' not in html  # merged into the Timeline (no duplicate)


def test_report_weather_section_only_when_provided(tmp_path):
    result = _result(tmp_path)
    assert 'Weather Impact' not in render_calendar_report(result, META)   # none by default
    weather = {
        'expected_bad_days_total': 12, 'net_finish_delay': 5,
        'weather_adjusted_finish': '2025-04-07',
        'monthly': [{'label': 'Mar 2025', 'count': 3}, {'label': 'Apr 2025', 'count': 1}],
        'histogram': [{'label': 'Mar 2025', 'net': 18, 'bad': 3, 'nonworking': 8, 'working': 21},
                      {'label': 'Apr 2025', 'net': 20, 'bad': 1, 'nonworking': 8, 'working': 21}],
        'source': 'Open-Meteo (forecast + ERA5 historical + air-quality)',
        'thresholds': {'rain_mm': 5, 'temp_max_c': 42, 'wind_kmh': None, 'dust': True},
        'bad_days': [{'date': '2025-03-03', 'day_name': 'Mon',
                      'condition': '🌡 45.5 °C ≥ 42 °C', 'confidence': 'forecast',
                      'effect': 'Non-working (construction)'}],
        'milestones': [{'name': 'M1', 'planned': '2025-03-01', 'bad_days_before': 3,
                        'already_allowed': 1, 'net_delay': 2, 'adjusted': '2025-03-05'}],
        'recovery': [{'period': 'M1', 'days': 2, 'option_longer_days': 'longer',
                      'option_extra_days': 'weekends', 'option_shift': 'shift'}],
        'by_cause': [{'label': 'Heat', 'count': 8}, {'label': 'Dust', 'count': 3},
                     {'label': 'Rain', 'count': 1}, {'label': 'Wind', 'count': 0, 'off': True}],
        'conclusion': 'Bad weather is estimated to cost about 5 working days to project finish.',
    }
    weather['bad_days'][0]['activities'] = ['Cable pulling']
    weather['bad_days'][0]['activities_count'] = 1
    html = render_calendar_report(result, META, weather=weather, feature='weather')
    assert 'Weather Impact' in html and 'Impact on Milestone Completion' in html
    assert 'Recovery Recommendations' in html
    # new results carried into the PDF: upcoming days with measured reason, source + limits
    assert 'Upcoming Bad-Weather Days' in html
    assert '45.5' in html and '42' in html            # measured reason value
    assert 'Open-Meteo' in html and 'heat ≥ 42' in html  # source + applied limit
    # the clarification Ibrahim asked for, plus the new report parts
    assert 'How this estimate is built' in html and 'What counts as a bad-weather day' in html
    assert 'Causing the Lost Days' in html            # cause breakdown table (relabelled #03)
    assert 'Weather Conclusion' in html and 'cost about 5 working days' in html
    # Feature-2 screen parity: §1 Execution Dashboard waterfall (three dates + variances)
    assert '1 · Execution Dashboard' in html
    assert 'Baseline Finish' in html and 'Forecast Completion' in html and 'Bad-weather Completion' in html
    assert '+5 wd' in html                            # weather-adds variance chip (net_finish_delay)
    # §2 Calendar Timeline & Statistics — the 3-colour histogram (net / bad / non-working)
    assert '2 · Calendar Timeline &amp; Statistics' in html
    assert 'class="h3bars"' in html and 's-net' in html and 's-bad' in html and 's-nw' in html
    assert 'net working days' in html                 # the histogram subtitle
    # sections are numbered to match the screen (3 Why … 7 Recovery)
    assert '5 · Upcoming Bad-Weather Days' in html and '6 · Impact on Milestone Completion' in html
    assert '7 · Recovery Recommendations' in html
    # #07 affected activities column + #12 milestone legend
    assert 'Affected work (by WBS)' in html and 'Cable pulling' in html
    assert 'How to read this table' in html and 'Net = Before' in html


def test_report_shows_site_type_criteria_and_why(tmp_path):
    """The stop-work criteria (site type) and the why-this-result read-out are shown in
    full in the PDF, so a consultant sees exactly how every lost day was decided."""
    from p6_calendar.weather import build_criteria, resolve_site_thresholds, SITE_TYPES
    thr = resolve_site_thresholds('marine')
    weather = {
        'expected_bad_days_total': 10, 'net_finish_delay': 8,
        'weather_adjusted_finish': '2027-02-17', 'monthly': [], 'by_cause': [],
        'bad_days': [], 'milestones': [], 'recovery': [],
        'thresholds': thr, 'site_type': 'marine',
        'site_type_label': SITE_TYPES['marine']['label'],
        'criteria': build_criteria('marine', thr),
        'limit_performance': [
            {'key': 'wind', 'label': 'Wind', 'on': True, 'limit': 35, 'unit': 'km/h',
             'flagged': 6, 'peak': 41.0},
            {'key': 'heat', 'label': 'Heat', 'on': True, 'limit': 40, 'unit': '°C',
             'flagged': 1, 'peak': 41.3},
        ],
    }
    html = render_calendar_report(_result(tmp_path), META, weather=weather, feature='weather')
    assert 'Stop-Work Criteria' in html and 'Marine / Port' in html
    assert 'What work it stops' in html and 'marine works' in html  # wind explanation shown
    assert 'Why This Result' in html and 'flagged 1 day' in html and '41.3' in html

    # A user-edited set is labelled "Custom limits", never mislabelled as the desert default.
    weather['site_type'] = 'custom'
    weather['site_type_label'] = None
    html2 = render_calendar_report(_result(tmp_path), META, weather=weather, feature='weather')
    assert 'Custom limits' in html2 and 'Default limits (Desert / inland)' not in html2


def test_report_nonworking_is_holidays_only(tmp_path):
    """§3 Calendar Non-working days is a holidays-only table (Date | Day | Description). The
    Feb 10–16 shutdown run is NOT a holiday, and the Jan holiday is before the data date, so
    the fixture yields no in-window holidays → §3 is dropped entirely."""
    html = render_calendar_report(_result(tmp_path), META)
    assert 'Calendar Non-working days' not in html   # no holidays in window → section dropped
    assert 'Shutdowns' not in html                   # shutdowns are excluded from §3
    assert 'Holidays & Vacations' not in html        # the old grouped layout is gone

    # A fixture WITH an in-window holiday renders the holidays-only table with the weekday.
    html2 = render_calendar_report(_result_with_holiday(tmp_path), META)
    assert '3 · Calendar Non-working days' in html2 and 'holidays only' in html2
    assert '10 Mar 2025' in html2 and 'Monday' in html2   # date + weekday
    assert 'Total holidays: <b>1</b>' in html2


def test_report_timeline_is_working_histogram(tmp_path):
    """#01 — §2 Calendar Timeline is the working/non-working days-per-month histogram."""
    html = render_calendar_report(_result(tmp_path), META)
    assert 'class="whist"' in html                 # the histogram is rendered
    assert 'Working days' in html and 'Non-working' in html   # its legend
    assert '2 · Calendar Timeline' in html and 'working vs non-working days per month' in html


def test_report_weather_cause_relabelled(tmp_path):
    """#03 — the cause breakdown is relabelled and explained."""
    weather = {
        'expected_bad_days_total': 3, 'net_finish_delay': 1, 'weather_adjusted_finish': '2025-04-01',
        'thresholds': {'rain_mm': 5, 'temp_max_c': 42, 'wind_kmh': None, 'dust': True},
        'by_cause': [{'label': 'Heat', 'count': 3}, {'label': 'Wind', 'count': 0, 'off': True}],
        'bad_days': [], 'milestones': [], 'recovery': [], 'monthly': [], 'conclusion': 'x',
    }
    html = render_calendar_report(_result(tmp_path), META, weather=weather, feature='weather')
    assert 'Causing the Lost Days' in html and 'by Weather Type' in html
    assert 'which condition causes them' in html


def test_report_weather_waterfall_shows_schedule_slip(tmp_path):
    """Feature 2 §1 waterfall — the schedule's own slip (baseline → forecast, calendar days)
    is shown separately from what weather adds (net_finish_delay, working days)."""
    result = _result(tmp_path)
    d = result['dashboard']
    d['baseline_finish'] = '2027-02-09'
    d['project_finish'] = '2027-02-19'                 # 10-day slip vs baseline
    weather = {
        'expected_bad_days_total': 5, 'net_finish_delay': 22,
        'weather_adjusted_finish': '2027-03-16',
        'thresholds': {'rain_mm': 5, 'temp_max_c': 42, 'wind_kmh': None, 'dust': True},
        'by_cause': [], 'bad_days': [], 'milestones': [], 'recovery': [], 'monthly': [],
    }
    html = render_calendar_report(result, META, weather=weather, feature='weather')
    assert '1 · Execution Dashboard' in html
    assert '+10 d' in html                             # schedule slip (calendar days)
    assert '+22 wd' in html                            # weather adds (working days)


def test_report_weather_hist3_omitted_without_histogram(tmp_path):
    """The §2 3-colour histogram is dropped cleanly when weather carries no histogram field."""
    weather = {
        'expected_bad_days_total': 0, 'net_finish_delay': 0, 'weather_adjusted_finish': '2025-03-31',
        'thresholds': {'rain_mm': 5, 'temp_max_c': 42, 'wind_kmh': None, 'dust': True},
        'by_cause': [], 'bad_days': [], 'milestones': [], 'recovery': [], 'monthly': [],
    }
    html = render_calendar_report(_result(tmp_path), META, weather=weather, feature='weather')
    assert 'class="h3bars"' not in html               # no histogram markup
    assert '1 · Execution Dashboard' in html          # the waterfall still renders


def test_report_honors_sections_list_for_both_features(tmp_path):
    """Regression — the Calendar Audit AND Bad Weather PDF previews now pass the ticked
    `sections` list through (the in-preview Report-contents toggle was dead). The report
    route must honour an explicit list for feature='calendar' AND feature='weather':
    an empty list drops the body, a ticked list renders exactly those sections."""
    result = _result(tmp_path)
    weather = {
        'expected_bad_days_total': 4, 'net_finish_delay': 3,
        'weather_adjusted_finish': '2025-04-03',
        'thresholds': {'rain_mm': 5, 'temp_max_c': 42, 'wind_kmh': None, 'dust': True},
        'by_cause': [], 'bad_days': [], 'milestones': [], 'recovery': [], 'monthly': [],
    }
    # feature='weather' — the whole report lives under the single 'weather' section key.
    # (Body-only waterfall labels as markers, so the CSS/header text can't mask the result.)
    on = render_calendar_report(result, META, weather=weather, feature='weather',
                                sections=['weather'])
    assert 'Baseline Finish' in on and 'Bad-weather Completion' in on
    off = render_calendar_report(result, META, weather=weather, feature='weather',
                                 sections=[])           # unticked → body dropped, valid HTML
    assert 'Baseline Finish' not in off and 'Bad-weather Completion' not in off
    assert off.startswith('<!DOCTYPE html>') and off.rstrip().endswith('</html>')

    # feature='calendar' — an explicit two-section list renders exactly those two, no more.
    two = render_calendar_report(result, META, sections=['dashboard', 'hours'])
    assert 'Baseline Finish' in two and 'Working-hours Profile' in two   # dashboard + hours in
    assert 'Calendar Timeline' not in two and 'Comparison &amp; Usage' not in two


def test_report_comparison_usage_and_section_picker(tmp_path):
    result = _result(tmp_path)
    html = render_calendar_report(result, META)
    # Merged Comparison & Usage: one table with hours/day, activities, % of activities and role
    assert 'Calendar Comparison &amp; Usage' in html
    assert 'Non-Working Days' in html and '% of Activities' in html and 'Assigned to' in html
    assert 'Unused' in html
    # #06 section-picker: only the requested sections render
    only_dash = render_calendar_report(result, META, sections=['dashboard'])
    assert 'Execution Dashboard' in only_dash
    assert 'Calendar Timeline' not in only_dash and 'Comparison &amp; Usage' not in only_dash


def test_report_shows_named_holiday_in_cell(tmp_path):
    """#05 — a stored shutdown/holiday name is printed inside the timeline day cell."""
    from p6_calendar import calendar_audit
    data = parse_file(_xml_for_name(tmp_path))
    r0 = calendar_audit(data, {}, {})
    key = r0['exceptions']['shutdowns'][0]['key']
    result = calendar_audit(data, {}, {'shutdown_reasons': {key: 'Plant Turnaround'}})
    html = render_calendar_report(result, META)
    assert 'Plant Turnaround' in html and 'class="cn"' in html


def test_report_prints_hours_note(tmp_path):
    """§5 — a planner's working-hours note prints in the PDF's Working Hours Profile."""
    _result(tmp_path)                                        # writes tmp_path/s.xml
    data = parse_file(str(tmp_path / 's.xml'))
    base = calendar_audit(data, {}, {})
    key = base['by_calendar'][base['primary_calendar_id']]['hours_profiles'][0]['key']
    result = calendar_audit(data, {}, {'hours_notes': {key: 'Summer / Ramadan reduced hours'}})
    html = render_calendar_report(result, META)
    assert 'Summer / Ramadan reduced hours' in html
    # blank note → nothing printed (no empty note row)
    assert 'Summer / Ramadan reduced hours' not in render_calendar_report(base, META)


def test_report_conflicts_appended_in_comparison(tmp_path):
    """§5 — the 'Calendar Conflicts — to be removed' list is appended INSIDE the Comparison &
    Usage section (no standalone Calendar Conflicts section)."""
    content = textwrap.dedent('''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Calendar><ObjectId>C1</ObjectId><Name>5 Days/Week</Name><IsDefault>true</IsDefault>
        <StandardWorkWeek><StandardWorkHours><DayOfWeek>Friday</DayOfWeek></StandardWorkHours>
        <StandardWorkHours><DayOfWeek>Saturday</DayOfWeek></StandardWorkHours></StandardWorkWeek></Calendar>
      <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Test</Name>
        <DataDate>2025-02-01T00:00:00</DataDate><PlannedStartDate>2025-01-01T00:00:00</PlannedStartDate>
        <ScheduledFinishDate>2025-03-31T17:00:00</ScheduledFinishDate>
        <Calendar><ObjectId>C3</ObjectId><Name>Old Unused</Name><IsDefault>false</IsDefault></Calendar>
        <WBS><ObjectId>10</ObjectId><Name>Construction</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity><ObjectId>A1</ObjectId><Id>A1</Id><Name>a</Name><Status>Not Started</Status>
          <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete></Activity>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / "cf.xml"; p.write_text(content, encoding='utf-8')
    result = calendar_audit(parse_file(str(p)), {}, {})
    html = render_calendar_report(result, META)
    assert 'Calendar Conflicts — to be removed' in html
    assert 'Unused calendar' in html and 'Old Unused' in html   # (quotes HTML-escaped)
    assert 'Calendar Conflicts</h2>' not in html      # not a standalone section


def test_report_hours_profile_is_a_table(tmp_path):
    """§4 — the Working-hours Profile is a table with a Days/week column."""
    html = render_calendar_report(_result(tmp_path), META)
    assert '4 · Working-hours Profile' in html
    assert 'Days / week' in html and 'Hrs / day' in html and 'Period' in html


def test_report_theme_default_is_light(tmp_path):
    html = render_calendar_report(_result(tmp_path), META)
    assert html.startswith('<!DOCTYPE html>') and html.rstrip().endswith('</html>')
    assert 'data-rpt-theme="light"' in html


def test_report_theme_dark(tmp_path):
    html = render_calendar_report(_result(tmp_path), META, theme='dark')
    assert 'data-rpt-theme="dark"' in html
    assert report_theme.THEMES['dark']['rpt-accent'] in html  # '#5b9bff'


def _xml_for_name(tmp_path):
    import textwrap
    days = ''.join(f'<HolidayOrException><Date>2025-02-{d:02d}T00:00:00</Date></HolidayOrException>'
                   for d in range(10, 17))
    content = textwrap.dedent(f'''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Calendar><ObjectId>C1</ObjectId><Name>5d</Name><IsDefault>true</IsDefault>
        <StandardWorkWeek><StandardWorkHours><DayOfWeek>Friday</DayOfWeek></StandardWorkHours>
        <StandardWorkHours><DayOfWeek>Saturday</DayOfWeek></StandardWorkHours></StandardWorkWeek>
        <HolidayOrExceptions>{days}</HolidayOrExceptions></Calendar>
      <Project><ObjectId>1</ObjectId><Id>P1</Id><Name>Test</Name>
        <DataDate>2025-02-01T00:00:00</DataDate><PlannedStartDate>2025-01-01T00:00:00</PlannedStartDate>
        <ScheduledFinishDate>2025-03-31T17:00:00</ScheduledFinishDate>
        <WBS><ObjectId>10</ObjectId><Name>Construction</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity><ObjectId>A1</ObjectId><Id>A1</Id><Name>a</Name><Status>Not Started</Status>
          <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete></Activity>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / "s2.xml"; p.write_text(content, encoding='utf-8')
    return str(p)
