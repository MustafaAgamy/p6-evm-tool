"""write_calendar_xlsx — the full Calendar Audit workbook: one coloured timeline sheet
per assigned calendar (names inside the day cells), plus Exceptions, Comparison, Usage
and Weather sheets. Validated by unzipping + XML-parsing (no openpyxl dependency)."""
import zipfile
import xml.dom.minidom as minidom
from p6_evm.xlsx_writer import write_calendar_xlsx, write_xlsx


def _months():
    return [
        {'label': 'Feb 2025', 'first_weekday': 5, 'working_days': 18, 'holidays': 1,
         'exceptions': 1, 'working_hours': 144.0,
         'days': [dict({'d': d, 'status': ('holiday' if d == 25 else 'work')},
                       **({'name': '25 Jan Revolution'} if d == 25 else {})) for d in range(19, 29)]},
    ]


def _ca():
    m = _months()
    return {
        'primary_calendar_id': 'C1',
        'assigned_calendars': [
            {'object_id': 'C1', 'name': '5 Days/Week', 'activity_count': 100,
             'is_default': True, 'hours_per_day': 8, 'days_per_week': 5},
            {'object_id': 'C2', 'name': '6 Days/Week', 'activity_count': 20,
             'is_default': False, 'hours_per_day': 9, 'days_per_week': 6},
        ],
        'by_calendar': {
            'C1': {'monthly_stats': m, 'exceptions': {
                'holidays': [{'description': '25 Feb 2025', 'days': 1, 'reason': '25 Jan Revolution', 'key': 'k'}],
                'special': [], 'shutdowns': []}},
            'C2': {'monthly_stats': m, 'exceptions': {'holidays': [], 'special': [], 'shutdowns': []}},
        },
        'comparison': [
            {'name': '5 Days/Week', 'hours_per_day': 8, 'days_per_week': 5, 'nonworking_days': 174, 'is_default': True},
            {'name': '6 Days/Week', 'hours_per_day': 9, 'days_per_week': 6, 'nonworking_days': 150, 'is_default': False},
        ],
        'usage': [
            {'name': '5 Days/Week', 'activities': 100, 'pct': 83.3, 'role': 'Default'},
            {'name': '6 Days/Week', 'activities': 20, 'pct': 16.7, 'role': 'Non-default'},
        ],
        'project': {'timeline_start': '2025-02-19', 'hidden_months': 1},
    }


def _weather():
    return {
        'bad_days': [{'date': '2025-08-12', 'day_name': 'Tue', 'condition': '🌡 44 °C ≥ 42 °C',
                      'confidence': 'forecast', 'effect': 'Non-working (construction)',
                      'activities': ['Excavation', 'Backfill'], 'activities_count': 2}],
        'milestones': [{'name': 'M1', 'planned': '2025-09-15', 'bad_days_before': 3,
                        'already_allowed': 1, 'net_delay': 2, 'adjusted': '2025-09-17'}],
        'recovery': [{'period': 'M1', 'days': 2, 'option_longer_days': 'longer',
                      'option_extra_days': 'weekends', 'option_shift': 'shift'}],
    }


def _sheets_text(path):
    with zipfile.ZipFile(path) as z:
        return '\n'.join(z.read(n).decode() for n in z.namelist()
                         if n.startswith('xl/worksheets/'))


def _all_wellformed(path):
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.endswith('.xml'):
                minidom.parseString(z.read(n).decode())


def test_workbook_has_a_sheet_per_calendar_plus_report_tables(tmp_path):
    p = tmp_path / 'cal.xlsx'
    write_calendar_xlsx(str(p), _ca(), weather=_weather())
    with zipfile.ZipFile(p) as z:
        n_sheets = len([n for n in z.namelist() if n.startswith('xl/worksheets/sheet')])
        wb = z.read('xl/workbook.xml').decode()
    assert n_sheets == 6                      # C1, C2, Exceptions, Comparison, Usage, Weather
    # sheet names sanitise '/' → '-' (illegal in Excel sheet names)
    for s in ['5 Days-Week', '6 Days-Week', 'Exceptions', 'Comparison', 'Usage', 'Weather']:
        assert s in wb
    _all_wellformed(p)


def test_named_holiday_shows_inside_the_day_cell(tmp_path):
    p = tmp_path / 'cal.xlsx'
    write_calendar_xlsx(str(p), _ca())
    with zipfile.ZipFile(p) as z:
        s1 = z.read('xl/worksheets/sheet1.xml').decode()   # first calendar's timeline
    assert '25 Jan Revolution' in s1          # the name is written into the grid cell (#05)
    styles = zipfile.ZipFile(str(p)).read('xl/styles.xml').decode()
    assert 'wrapText' in styles                # day cells wrap so the name fits


def test_weather_sheet_names_affected_activities(tmp_path):
    p = tmp_path / 'cal.xlsx'
    write_calendar_xlsx(str(p), _ca(), weather=_weather())
    txt = _sheets_text(p)
    assert 'Affected planned activities' in txt and 'Excavation' in txt


def test_comparison_sheet_has_nonworking_days(tmp_path):
    p = tmp_path / 'cal.xlsx'
    write_calendar_xlsx(str(p), _ca())
    txt = _sheets_text(p)
    assert 'Non-Working Days' in txt          # #09 Comparison column + #02 monthly-stats column
    # each calendar's monthly-stats table carries the Non-Working Days column too (#02)
    with zipfile.ZipFile(p) as z:
        assert 'Non-Working Days' in z.read('xl/worksheets/sheet1.xml').decode()


def test_workbook_from_real_audit_end_to_end(tmp_path):
    """parse → calendar_audit → workbook, so the REAL audit output shape is exercised
    (not a hand-built dict). Guards against a shape drift between audit and the writer."""
    import textwrap
    from p6_evm.parser import parse_file
    from p6_calendar import calendar_audit
    days = ''.join(f'<HolidayOrException><Date>2026-11-{d:02d}T00:00:00</Date></HolidayOrException>'
                   for d in range(1, 8))          # a 7-day shutdown run
    xml = textwrap.dedent(f'''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Calendar><ObjectId>C1</ObjectId><Name>5 Days/Week</Name><IsDefault>true</IsDefault>
        <StandardWorkWeek><StandardWorkHours><DayOfWeek>Friday</DayOfWeek></StandardWorkHours>
        <StandardWorkHours><DayOfWeek>Saturday</DayOfWeek></StandardWorkHours></StandardWorkWeek>
        <HolidayOrExceptions>{days}</HolidayOrExceptions></Calendar>
      <Project><ObjectId>1</ObjectId><Id>P</Id><Name>P</Name><DataDate>2026-07-19T00:00:00</DataDate>
        <PlannedStartDate>2024-10-01T00:00:00</PlannedStartDate>
        <ScheduledFinishDate>2027-02-09T00:00:00</ScheduledFinishDate>
        <WBS><ObjectId>10</ObjectId><Name>Construction</Name><ParentObjectId></ParentObjectId></WBS>
        <Activity><ObjectId>A1</ObjectId><Id>A1</Id><Name>a</Name><Status>Not Started</Status>
          <CalendarObjectId>C1</CalendarObjectId><WBSObjectId>10</WBSObjectId><PercentComplete>0</PercentComplete></Activity>
      </Project>
    </APIBusinessObjects>
    ''')
    path = tmp_path / 's.xml'; path.write_text(xml, encoding='utf-8')
    data = parse_file(str(path))
    r0 = calendar_audit(data, {}, {})
    key = r0['exceptions']['shutdowns'][0]['key']
    ca = calendar_audit(data, {}, {'shutdown_reasons': {key: 'Annual Maintenance'}})
    p = tmp_path / 'e2e.xlsx'
    write_calendar_xlsx(str(p), ca)               # must not raise on the real shape
    with zipfile.ZipFile(p) as z:
        wb = z.read('xl/workbook.xml').decode()
        assert '5 Days-Week' in wb and 'Comparison' in wb and 'Usage' in wb
        txt = '\n'.join(z.read(n).decode() for n in z.namelist() if n.startswith('xl/worksheets/'))
        assert 'Annual Maintenance' in txt        # stored name flows all the way into a cell
    _all_wellformed(p)


def test_write_xlsx_still_works(tmp_path):
    p = tmp_path / 'flat.xlsx'
    write_xlsx(str(p), 'Sheet', ['A', 'B'], [['x', 1], ['y', 2]])
    with zipfile.ZipFile(p) as z:
        s = z.read('xl/worksheets/sheet1.xml').decode()
    assert 'autoFilter' in s
    minidom.parseString(s)
