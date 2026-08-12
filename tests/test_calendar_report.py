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
        'weather_adjusted_finish': '2025-04-07', 'monthly': [],
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
    html = render_calendar_report(result, META, weather=weather)
    assert 'Weather Impact' in html and 'Milestone Impact' in html
    assert 'Recovery Recommendations' in html
    # new results carried into the PDF: upcoming days with measured reason, source + limits
    assert 'Upcoming Bad-Weather Days' in html
    assert '45.5' in html and '42' in html            # measured reason value
    assert 'Open-Meteo' in html and 'heat ≥ 42' in html  # source + applied limit
    # the clarification Ibrahim asked for, plus the new report parts
    assert 'How this estimate is built' in html and 'What counts as a bad-weather day' in html
    assert 'Driving the Lost Days' in html            # cause breakdown table
    assert 'Weather Conclusion' in html and 'cost about 5 working days' in html
