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

# A 5-day-week default calendar (Fri+Sat off) with a New-Year holiday (Wed 01 Jan 2025)
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
      <HolidayOrException><Date>2025-01-01T00:00:00</Date></HolidayOrException>
    </HolidayOrExceptions>
  </Calendar>
  <Project>
    <ObjectId>1</ObjectId><Id>P1</Id><Name>Calendar Project</Name>
    <DataDate>2025-02-01T00:00:00</DataDate>
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


def test_calendar_payload_carries_full_contract(tmp_path):
    data = parse_file(_write(tmp_path))
    doc = build_report(data).to_dict()
    sec = _calendar_section(doc)
    p = sec['payload']

    # legacy keys preserved (flat-fallback compatibility)
    assert 'calendars' in p and 'holidays' in p

    # full SLICE A passthrough present
    for key in ('dashboard', 'monthly', 'holiday_dates', 'comparison', 'usage'):
        assert key in p, f'missing calendar payload key: {key}'
    assert p['monthly'], 'monthly grid should be populated'
    assert p['comparison'], 'comparison table should be populated'
    assert p['usage'], 'usage table should be populated'

    # baseline start/finish are cover meta, NOT dashboard tiles
    assert 'baseline_start' not in p['dashboard']
    assert 'baseline_finish' not in p['dashboard']

    # dated holidays carry a weekday name (01 Jan 2025 is a Wednesday)
    hd = p['holiday_dates']
    assert hd, 'holiday_dates should be populated'
    row = next(r for r in hd if r['date'] == '2025-01-01')
    assert row['weekday'] == 'Wednesday'
    assert all('weekday' in r for r in hd)


def test_cover_meta_defaults(tmp_path):
    data = parse_file(_write(tmp_path))
    doc = build_report(data).to_dict()
    meta = doc['meta']
    # data_date filled from the project (full-date string), location/revision None-safe
    assert meta.get('data_date')
    assert '2025' in str(meta['data_date'])
    assert 'location' in meta and 'revision' in meta


def test_renderer_draws_monthly_and_comparison(tmp_path):
    data = parse_file(_write(tmp_path))
    doc = build_report(data).to_dict()
    h = render_narrative_html(doc)
    assert 'Working / non-working days by month' in h   # monthly table caption
    assert 'Calendar comparison' in h                   # comparison table caption
    assert 'Dated holidays' in h                        # holiday_dates table caption
