"""Word §8 (Project Calendars & Holidays) renderer tests.

Builds the narrative calendar payload with SLICE A's ``build_report`` from a real
calendars fixture, renders it with ``docx_calendar.render_calendar`` into a fresh
Document, saves + reopens the .docx, and asserts the approved section landed: 8.1 dashboard
tiles, 8.2 one native Word chart per calendar, 8.3 the dated holidays, 8.4 the working-hours
card — WITHOUT the excluded Baseline Start / Baseline Finish dates.
"""
import io
import sys
import textwrap

from docx import Document

from p6_evm.parser import parse_file
from p6_narrative import docx_calendar
from p6_narrative.report import build_report

# 5-day-week default calendar (Fri+Sat off) with one holiday (Wed 08-Jan.2025)
# and two activities spanning Jan–Mar 2025 — same shape as the SLICE A payload fixture.
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


def _calendar_payload(tmp_path):
    p = tmp_path / 'cal.xml'
    p.write_text(_XML, encoding='utf-8')
    data = parse_file(str(p))
    doc = build_report(data, path=str(p)).to_dict()
    for s in doc['sections']:
        if s.get('title', '').strip().lower() == 'project calendars & holidays':
            return s['payload']
    raise AssertionError('calendar section not found in report')


def _render(tmp_path, chrome=None):
    payload = _calendar_payload(tmp_path)
    document = Document()
    docx_calendar.render_calendar(document, payload, chrome)
    buf = io.BytesIO()
    document.save(buf)
    buf.seek(0)
    return Document(buf)


def _all_text(document):
    parts = [pa.text for pa in document.paragraphs]
    for t in document.tables:
        for row in t.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return '\n'.join(parts)


def _table_texts(table):
    return [cell.text for row in table.rows for cell in row.cells]


def test_renders_the_four_blocks_in_order(tmp_path):
    doc = _render(tmp_path)
    heads = [pa.text for pa in doc.paragraphs if pa.text.strip()[:2] == '8.']
    assert [h.split()[0] for h in heads] == ['8.1', '8.2', '8.3', '8.4']
    assert 'EXECUTIVE DASHBOARD' in heads[0] and 'CALENDAR TIMELINE' in heads[1]
    assert 'HOLIDAYS' in heads[2] and 'WORKING HOURS PROFILE' in heads[3]
    assert '1 calendar assigned to activities · 2 activities' in _all_text(doc)     # singular
    # dashboard tiles + holidays + hours card
    assert len(doc.tables) == 3


def test_dashboard_tiles_without_baseline_start_finish(tmp_path):
    doc = _render(tmp_path)
    text = _all_text(doc)
    assert 'Baseline Start' not in text and 'Baseline Finish' not in text
    assert 'Shutdown' not in text                              # no shutdown-periods tile
    tiles = dict(reversed(c.split('\n', 1)) for c in _table_texts(doc.tables[0]))
    # 2 Jan → 31-Mar.2025 = 89 days: 26 Fridays / Saturdays + the holiday = 27 non-working
    assert tiles == {'Total Calendar Days': '89', 'Working Days': '62', 'Non-Working Days': '27',
                     'Holidays': '1', 'Avg Work Days / Month': '20.7', 'Avg Work Hours / Day': '8.0 hrs'}


def test_timeline_is_a_native_word_chart_per_calendar(tmp_path):
    doc = _render(tmp_path)
    xml = doc.element.xml
    assert xml.count('<w:drawing') == 1 and 'c:chart' in xml    # one calendar → one chart, no picture file
    assert '5 Days/Week — 2 activities' in _all_text(doc)       # the chart's own title line


def test_holidays_table_lists_the_dated_holiday(tmp_path):
    doc = _render(tmp_path)
    hol = next((t for t in doc.tables
                if [c.text for c in t.rows[0].cells] == ['Date', 'Description']), None)
    assert hol is not None, 'holidays table not found'
    assert [row.cells[0].text for row in hol.rows[1:]] == ['08-Jan.2025']


def test_no_holiday_in_the_window_means_no_holidays_block(tmp_path, monkeypatch):
    # data date after the holiday: the section reports from the data date, so the list is empty
    monkeypatch.setattr(sys.modules[__name__], '_XML', _XML.replace('<DataDate>2025-01-01', '<DataDate>2025-02-01'))
    doc = _render(tmp_path)
    heads = [pa.text.split()[0] for pa in doc.paragraphs if pa.text.strip()[:2] == '8.']
    assert heads == ['8.1', '8.2', '8.4']                       # no heading over nothing
    assert 'Holidays' in _all_text(doc)                         # the tile still says 0


def test_hours_card_shows_days_per_week_and_hours(tmp_path):
    doc = _render(tmp_path)
    card = doc.tables[-1]
    assert _table_texts(card) == ['5 days/week\n5 Days/Week · 08:00–16:00']
