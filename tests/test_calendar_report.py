"""Task 6 — p6_calendar.report.render_calendar_report(result, meta) -> HTML."""
import textwrap
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
    html = render_calendar_report(_result(tmp_path), META)
    order = ['Executive Dashboard', 'Calendar Timeline', 'Monthly Calendar Statistics',
             'Calendar Exceptions', 'Working Hours Profile',
             'Calendar Comparison', 'Calendar Usage', 'Calendar Conflicts', 'Executive Conclusion']
    pos = [html.find(s) for s in order]
    assert all(p != -1 for p in pos), pos
    assert pos == sorted(pos)


def test_report_is_html_and_has_content(tmp_path):
    html = render_calendar_report(_result(tmp_path), META)
    assert html.startswith('<!DOCTYPE html>')
    assert 'Test' in html                       # project name
    assert 'Shutdowns' in html                  # exception group
    assert '90' in html                         # total calendar days
    assert 'Monthly Calendar View' not in html  # merged into the Timeline (no duplicate)


def test_report_weather_section_only_when_provided(tmp_path):
    result = _result(tmp_path)
    assert 'Weather Impact' not in render_calendar_report(result, META)   # none by default
    weather = {
        'expected_bad_days_total': 12, 'net_finish_delay': 5,
        'weather_adjusted_finish': '2025-04-07',
        'monthly': [{'label': 'Mar 2025', 'count': 3}, {'label': 'Apr 2025', 'count': 1}],
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
    html = render_calendar_report(result, META, weather=weather)
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
    # the monthly histogram ("When the risk falls") must be in the PDF, not just on screen
    assert 'When the Risk Falls' in html and 'wxb-bar' in html
    # #07 affected activities column + #12 milestone legend
    assert 'Affected work (by WBS)' in html and 'Cable pulling' in html
    assert 'How to read this table' in html and 'Net = Before' in html


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
    html = render_calendar_report(_result(tmp_path), META, weather=weather)
    assert 'Causing the Lost Days' in html and 'by Weather Type' in html
    assert 'which condition causes them' in html


def test_report_comparison_usage_and_section_picker(tmp_path):
    result = _result(tmp_path)
    html = render_calendar_report(result, META)
    # #09 comparison: Non-Working Days column, no Activities column header in comparison
    assert 'Non-Working Days' in html
    # #10 usage role legend
    assert 'Roles.' in html and 'Non-default' in html and 'Unused' in html
    # #06 section-picker: only the requested sections render
    only_dash = render_calendar_report(result, META, sections=['dashboard'])
    assert 'Executive Dashboard' in only_dash
    assert 'Calendar Timeline' not in only_dash and 'Calendar Usage' not in only_dash


def test_report_shows_named_holiday_in_cell(tmp_path):
    """#05 — a stored shutdown/holiday name is printed inside the timeline day cell."""
    from p6_calendar import calendar_audit
    data = parse_file(_xml_for_name(tmp_path))
    r0 = calendar_audit(data, {}, {})
    key = r0['exceptions']['shutdowns'][0]['key']
    result = calendar_audit(data, {}, {'shutdown_reasons': {key: 'Plant Turnaround'}})
    html = render_calendar_report(result, META)
    assert 'Plant Turnaround' in html and 'class="cn"' in html


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
