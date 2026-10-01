"""SLICE A — the narrative Calendar section carries the full Calendar-Audit passthrough.

``build_report`` must widen the trimmed calendar payload into the full CONTRACT: the
dashboard tiles, the monthly working/non-working grid, dated holidays (with weekday),
the hours profile, and the comparison + usage tables — indexed on the primary calendar.
The renderer must draw the monthly + comparison tables. Baseline start/finish are cover
meta, not dashboard tiles, so they must be dropped from the dashboard block.
"""
import os
import textwrap

from p6_evm.parser import parse_file
from p6_narrative.html import render_narrative_html
from p6_narrative.report import build_report

# A 5-day-week default calendar (Fri+Sat off) with one holiday (Wed 08 Jan 2025)
# and a 7-day shutdown run, one WBS, two activities spanning Jan–Mar 2025.
_XML = textwrap.dedent('''\
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
      <StandardWorkHours><DayOfWeek>Tuesday</DayOfWeek><WorkTime><Start>08:00:00</Start><Finish>16:00:00</Finish></WorkTime></StandardWorkHours>
      <StandardWorkHours><DayOfWeek>Wednesday</DayOfWeek><WorkTime><Start>08:00:00</Start><Finish>16:00:00</Finish></WorkTime></StandardWorkHours>
      <StandardWorkHours><DayOfWeek>Thursday</DayOfWeek><WorkTime><Start>08:00:00</Start><Finish>16:00:00</Finish></WorkTime></StandardWorkHours>
    </StandardWorkWeek>
    <HolidayOrExceptions>
      <HolidayOrException><Date>2025-01-08T00:00:00</Date></HolidayOrException>
    </HolidayOrExceptions>
  </Calendar>
  <Project>
    <ObjectId>1</ObjectId><Id>P1</Id><Name>Calendar Project</Name>
    <DataDate>2025-01-01T00:00:00</DataDate>
    <PlannedStartDate>2025-01-01T00:00:00</PlannedStartDate>
    <ScheduledFinishDate>2025-03-31T17:00:00</ScheduledFinishDate>
    <WBS><ObjectId>10</ObjectId><Name>Construction</Name><ParentObjectId></ParentObjectId></WBS>
    <Activity><ObjectId>A1</ObjectId><Id>A1</Id><Name>a</Name><Status>Not Started</Status>
      <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete>
      <PlannedStartDate>2025-01-02T00:00:00</PlannedStartDate>
      <PlannedFinishDate>2025-02-15T00:00:00</PlannedFinishDate></Activity>
    <Activity><ObjectId>A2</ObjectId><Id>A2</Id><Name>b</Name><Status>Not Started</Status>
      <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete>
      <PlannedStartDate>2025-02-16T00:00:00</PlannedStartDate>
      <PlannedFinishDate>2025-03-31T00:00:00</PlannedFinishDate></Activity>
  </Project>
</APIBusinessObjects>
''')


def _write(tmp_path):
    p = tmp_path / 'cal.xml'
    p.write_text(_XML, encoding='utf-8')
    return str(p)


def _calendar_section(doc):
    for s in doc['sections']:
        if s.get('title', '').strip().lower() == 'project calendars & holidays':
            return s
    raise AssertionError('calendar section not found')


def test_calendar_payload_carries_the_approved_contract(tmp_path):
    data = parse_file(_write(tmp_path))
    doc = build_report(data).to_dict()
    sec = _calendar_section(doc)
    p = sec['payload']

    # the approved section: 8.1 dashboard tiles, 8.2 one working / non-working timeline per
    # assigned calendar, the dated holidays, and one working-hours card per calendar
    assert set(p) == {'view', 'header', 'dashboard', 'calendars', 'holidays', 'hours_profiles'}
    assert p['header'] == {'calendar_count': 1, 'activity_count': 2}

    # baseline start/finish are cover meta, NOT dashboard tiles
    assert 'baseline_start' not in p['dashboard'] and 'baseline_finish' not in p['dashboard']
    assert p['dashboard']['total_working_days'] + p['dashboard']['total_nonworking_days'] \
        == p['dashboard']['total_calendar_days']

    cal = p['calendars'][0]
    assert cal['name'] == '5 Days/Week' and cal['activity_count'] == 2
    # the monthly grid: one row per month from the first activity (2 Jan 2025) to completion (Mar 2025)
    assert cal['months'] == [m['label'] for m in cal['monthly']] == ['Jan 2025', 'Feb 2025', 'Mar 2025']
    for m, wd, nwd in zip(cal['monthly'], cal['net_working_days'], cal['nonworking_days']):
        assert m['working_days'] == wd and m['nonworking_days'] == nwd and wd > nwd > 0
    assert cal['working_days'] == sum(cal['net_working_days'])
    # January from the 2nd: 30 days, 9 of them Fridays / Saturdays, plus the holiday on the 8th
    assert cal['monthly'][0] == {'label': 'Jan 2025', 'working_days': 20, 'nonworking_days': 10}

    # the dated holiday (Wed 08 Jan 2025) is listed and counted
    assert p['dashboard']['total_holidays'] == 1 and len(p['holidays']) == 1
    assert '2025' in p['holidays'][0]['date'] and 'Jan' in p['holidays'][0]['date']

    assert p['hours_profiles'] == [{'name': '5 Days/Week', 'hours': '08:00–16:00', 'sub': '5 days/week'}]


def test_cover_meta_defaults(tmp_path):
    data = parse_file(_write(tmp_path))
    doc = build_report(data).to_dict()
    meta = doc['meta']
    # data_date filled from the project (full-date string), location/revision None-safe
    assert meta.get('data_date')
    assert '2025' in str(meta['data_date'])
    assert 'location' in meta and 'revision' in meta


def test_renderer_draws_the_dashboard_timeline_holidays_and_hours(tmp_path):
    data = parse_file(_write(tmp_path))
    doc = build_report(data).to_dict()
    h = render_narrative_html(doc)
    assert '1 calendar assigned to activities' in h          # singular, not '1 calendars'
    for caption in ('Executive Dashboard', 'Calendar Timeline', 'Working Hours Profile'):
        assert caption in h, caption
    assert 'Total Calendar Days' in h and 'Avg Work Days / Month' in h
    assert 'Jan 2025' in h and 'Mar 2025' in h               # the timeline's months
