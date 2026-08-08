"""Task 1 — additive parser reads for the Calendar Audit module:
calendar Type + IsDefault, and project planned start / scheduled finish.
These must not change any EVM number (covered elsewhere)."""
import textwrap
from datetime import datetime
from p6_evm.parser import parse_file


def _xml(tmp_path):
    content = textwrap.dedent('''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Calendar>
        <ObjectId>C1</ObjectId><Name>Standard 5-Day</Name>
        <Type>Global</Type><IsDefault>true</IsDefault>
        <StandardWorkWeek>
          <StandardWorkHours><DayOfWeek>Saturday</DayOfWeek></StandardWorkHours>
          <StandardWorkHours><DayOfWeek>Sunday</DayOfWeek></StandardWorkHours>
        </StandardWorkWeek>
      </Calendar>
      <Project>
        <ObjectId>1</ObjectId><Id>T33</Id><Name>Tower 33</Name>
        <DataDate>2026-07-24T00:00:00</DataDate>
        <PlannedStartDate>2025-01-05T08:00:00</PlannedStartDate>
        <ScheduledFinishDate>2026-06-28T17:00:00</ScheduledFinishDate>
        <Calendar>
          <ObjectId>C2</ObjectId><Name>6 Days/Week</Name>
          <Type>Project</Type><IsDefault>false</IsDefault>
          <StandardWorkWeek>
            <StandardWorkHours><DayOfWeek>Friday</DayOfWeek></StandardWorkHours>
          </StandardWorkWeek>
        </Calendar>
        <WBS><ObjectId>10</ObjectId><Name>Structure</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity>
          <ObjectId>1001</ObjectId><Id>A230</Id><Name>Roof Steel</Name>
          <Status>In Progress</Status><WBSObjectId>10</WBSObjectId>
          <CalendarObjectId>C2</CalendarObjectId><PercentComplete>40</PercentComplete>
          <PlannedStartDate>2025-02-01T08:00:00</PlannedStartDate>
          <PlannedFinishDate>2025-05-01T17:00:00</PlannedFinishDate>
        </Activity>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / "s.xml"; p.write_text(content, encoding='utf-8')
    return str(p)


def test_calendar_type_and_default(tmp_path):
    data = parse_file(_xml(tmp_path))
    assert data.calendars['C1'].type == 'Global'
    assert data.calendars['C1'].is_default is True
    assert data.calendars['C2'].type == 'Project'
    assert data.calendars['C2'].is_default is False


def test_calendar_fields_default_when_absent(tmp_path):
    """A calendar with no Type/IsDefault (minimal export) degrades cleanly."""
    from p6_evm.calendars import Calendar
    c = Calendar(object_id='X', name='n')
    assert c.type == ''
    assert c.is_default is False


def test_project_planned_start_and_scheduled_finish(tmp_path):
    data = parse_file(_xml(tmp_path))
    assert data.project['planned_start'] == datetime(2025, 1, 5, 8, 0, 0)
    assert data.project['scheduled_finish'] == datetime(2026, 6, 28, 17, 0, 0)
