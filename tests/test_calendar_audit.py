"""Task 2 — p6_calendar.calendar_audit(data, config, settings).
Deterministic calendar analysis (Sections 1-9,11); no EVM numbers touched,
no network (weather is a separate module)."""
import textwrap
from p6_evm.parser import parse_file
from p6_calendar import calendar_audit


def _xml(tmp_path):
    # C1 = default Global 5-day (Fri+Sat off); C2 = Project 6-day; C3 = unused Global.
    # C1 exceptions: one holiday (Jan 1) + a 7-day shutdown run (Feb 10-16).
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
          <StandardWorkHours><DayOfWeek>Sunday</DayOfWeek><WorkTime><Start>08:00:00</Start><Finish>16:00:00</Finish></WorkTime></StandardWorkHours>
          <StandardWorkHours><DayOfWeek>Monday</DayOfWeek><WorkTime><Start>08:00:00</Start><Finish>16:00:00</Finish></WorkTime></StandardWorkHours>
          <StandardWorkHours><DayOfWeek>Tuesday</DayOfWeek><WorkTime><Start>08:00:00</Start><Finish>16:00:00</Finish></WorkTime></StandardWorkHours>
          <StandardWorkHours><DayOfWeek>Wednesday</DayOfWeek><WorkTime><Start>08:00:00</Start><Finish>16:00:00</Finish></WorkTime></StandardWorkHours>
          <StandardWorkHours><DayOfWeek>Thursday</DayOfWeek><WorkTime><Start>08:00:00</Start><Finish>16:00:00</Finish></WorkTime></StandardWorkHours>
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
        <Calendar>
          <ObjectId>C2</ObjectId><Name>6 Days/Week</Name><Type>Project</Type><IsDefault>false</IsDefault>
          <HoursPerDay>9</HoursPerDay>
          <StandardWorkWeek>
            <StandardWorkHours><DayOfWeek>Friday</DayOfWeek></StandardWorkHours>
          </StandardWorkWeek>
        </Calendar>
        <Calendar>
          <ObjectId>C3</ObjectId><Name>Old Unused</Name><Type>Global</Type><IsDefault>false</IsDefault>
        </Calendar>
        <WBS><ObjectId>10</ObjectId><Name>Construction</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity><ObjectId>A1</ObjectId><Id>A1</Id><Name>a</Name><Status>Not Started</Status>
          <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete></Activity>
        <Activity><ObjectId>A2</ObjectId><Id>A2</Id><Name>b</Name><Status>Not Started</Status>
          <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete></Activity>
        <Activity><ObjectId>A3</ObjectId><Id>A3</Id><Name>c</Name><Status>Not Started</Status>
          <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete></Activity>
        <Activity><ObjectId>A4</ObjectId><Id>A4</Id><Name>d</Name><Status>Not Started</Status>
          <CalendarObjectId>C2</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete></Activity>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / "s.xml"; p.write_text(content, encoding='utf-8')
    return str(p)


def _run(tmp_path, settings=None):
    data = parse_file(_xml(tmp_path))
    return calendar_audit(data, {}, settings or {})


def test_dashboard_window(tmp_path):
    r = _run(tmp_path)
    d = r['dashboard']
    assert d['total_calendar_days'] == 90            # Jan 1 .. Mar 31 inclusive
    assert d['total_working_days'] + d['total_nonworking_days'] == 90
    assert d['total_working_days'] > 0


def test_exceptions_split_holiday_vs_shutdown(tmp_path):
    r = _run(tmp_path)
    exc = r['exceptions']
    # one isolated non-working day -> holiday; a 7-day run -> one shutdown
    assert len(exc['holidays']) == 1
    assert len(exc['shutdowns']) == 1
    assert exc['shutdowns'][0]['days'] == 7
    assert r['dashboard']['shutdown_periods'] == 1


def test_manual_shutdown_added(tmp_path):
    r = _run(tmp_path, settings={'manual_shutdowns': [
        {'start': '2025-03-03', 'end': '2025-03-07', 'reason': 'Client turnaround'}]})
    shut = r['exceptions']['shutdowns']
    manual = [s for s in shut if s.get('source') == 'manual']
    assert len(manual) == 1
    assert manual[0]['reason'] == 'Client turnaround'
    assert r['dashboard']['shutdown_periods'] == 2   # P6 run + manual


def test_usage_roles_and_pct(tmp_path):
    r = _run(tmp_path)
    usage = {u['name']: u for u in r['usage']}
    assert usage['5 Days/Week']['role'] == 'Default'
    assert usage['5 Days/Week']['activities'] == 3
    assert usage['5 Days/Week']['pct'] == 75.0
    assert usage['Old Unused']['role'] == 'Unused'
    assert usage['Old Unused']['activities'] == 0


def test_conflicts_detected(tmp_path):
    r = _run(tmp_path)
    kinds = {c['type'] for c in r['conflicts']}
    assert 'mixed_wbs' in kinds        # WBS 10 has C1 and C2
    assert 'not_default' in kinds      # A4 on C2, default is C1
    assert 'unused' in kinds           # C3 unused


def test_primary_and_assigned_calendars(tmp_path):
    r = _run(tmp_path)
    assert r['primary_calendar_id'] == 'C1'          # the default
    assigned = {c['object_id'] for c in r['assigned_calendars']}
    assert assigned == {'C1', 'C2'}                  # C3 unused -> not "assigned"
    assert 'C1' in r['by_calendar'] and 'C2' in r['by_calendar']


def test_window_is_baseline_and_full_months(tmp_path):
    """Calendar window = baseline start → baseline finish, shown in FULL months
    (baseline finishing 09 Feb 2027 → window ends 28 Feb 2027)."""
    import textwrap
    content = textwrap.dedent('''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Calendar><ObjectId>C1</ObjectId><Name>5d</Name><IsDefault>true</IsDefault>
        <StandardWorkWeek><StandardWorkHours><DayOfWeek>Friday</DayOfWeek></StandardWorkHours>
        <StandardWorkHours><DayOfWeek>Saturday</DayOfWeek></StandardWorkHours></StandardWorkWeek></Calendar>
      <Project><ObjectId>1</ObjectId><Id>P</Id><Name>P</Name><DataDate>2026-06-01T00:00:00</DataDate>
        <PlannedStartDate>2025-12-20T00:00:00</PlannedStartDate>
        <ScheduledFinishDate>2027-03-15T00:00:00</ScheduledFinishDate>
        <WBS><ObjectId>10</ObjectId><Name>Construction</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity><ObjectId>A1</ObjectId><Id>A1</Id><Name>a</Name><Status>Not Started</Status>
          <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete>
          <PlannedStartDate>2025-12-20T00:00:00</PlannedStartDate>
          <PlannedFinishDate>2027-03-15T00:00:00</PlannedFinishDate></Activity>
      </Project>
      <BaselineProject>
        <Activity><Id>A1</Id><PlannedStartDate>2025-12-11T00:00:00</PlannedStartDate>
          <PlannedFinishDate>2027-02-09T00:00:00</PlannedFinishDate></Activity>
      </BaselineProject>
    </APIBusinessObjects>
    ''')
    p = tmp_path / "s.xml"; p.write_text(content, encoding='utf-8')
    r = calendar_audit(parse_file(str(p)), {}, {})
    d = r['dashboard']
    assert d['baseline_start'] == '2025-12-11'
    assert d['baseline_finish'] == '2027-02-09'          # exact baseline finish shown
    assert d['window_start'] == '2025-12-11'             # window starts at baseline start
    assert d['window_finish'] == '2027-02-28'           # full final month (Feb 2027)
    # months span Dec 2025 … Feb 2027, last month = Feb 2027
    months = r['by_calendar'][r['primary_calendar_id']]['monthly_stats']
    assert months[0]['label'].startswith('Dec 2025')
    assert months[-1]['label'].startswith('Feb 2027')


def test_conclusion_bullets(tmp_path):
    r = _run(tmp_path)
    concl = r['conclusion']
    assert isinstance(concl, list) and len(concl) >= 4
    joined = ' '.join(concl)
    assert 'Consistency' in joined and 'Shutdowns' in joined and 'Conflicts' in joined


def test_monthly_stats_present(tmp_path):
    r = _run(tmp_path)
    prim = r['by_calendar'][r['primary_calendar_id']]
    labels = [m['label'] for m in prim['monthly_stats']]
    assert labels[0].startswith('Jan 2025')
    assert labels[-1].startswith('Mar 2025')
    assert all('working_days' in m and 'working_hours' in m for m in prim['monthly_stats'])
