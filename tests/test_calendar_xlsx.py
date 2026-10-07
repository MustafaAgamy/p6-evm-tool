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
                'holidays': [{'description': '25-Feb.2025', 'days': 1, 'reason': '25 Jan Revolution', 'key': 'k'}],
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


def test_weather_workbook_grid_highlights_bad_days_amber(tmp_path):
    """write_weather_xlsx: a construction-calendar month grid where the bad-weather days are
    highlighted amber (style 10), a Working/Non-working/Bad-weather legend, and the weather
    tables — Upcoming (with a serial #) + Causes."""
    from p6_evm.xlsx_writer import write_weather_xlsx
    months = [{'label': 'Feb 2025', 'year': 2025, 'month': 2, 'first_weekday': 5,
               'working_days': 8, 'nonworking_days': 2, 'holidays': 0, 'exceptions': 0,
               'working_hours': 64.0,
               'days': [{'d': d, 'status': ('weekend' if d in (22, 23) else 'work')}
                        for d in range(19, 29)]}]
    ca = {'primary_calendar_id': 'C1',
          'assigned_calendars': [{'object_id': 'C1', 'name': 'Site 6d', 'activity_count': 100}],
          'by_calendar': {'C1': {'monthly_stats': months,
                                 'exceptions': {'holidays': [], 'special': [], 'shutdowns': []}}},
          'project': {'timeline_start': '2025-02-19', 'hidden_months': 0}}
    weather = {'expected_bad_days_total': 2,
               'bad_days': [{'date': '2025-02-20', 'day_name': 'Thu', 'condition': '40 km/h >= 35',
                             'confidence': 'expected', 'activities': ['Piles'], 'activities_count': 1},
                            {'date': '2025-02-25', 'day_name': 'Tue', 'condition': '6 mm >= 5',
                             'confidence': 'expected', 'activities': [], 'activities_count': 0}],
               'by_cause': [{'label': 'Wind', 'count': 1}, {'label': 'Rain', 'count': 1}],
               'milestones': [{'name': 'M1', 'planned': '2025-09-15', 'bad_days_before': 2,
                               'already_allowed': 0, 'net_delay': 2, 'adjusted': '2025-09-17'}],
               'recovery': [{'period': 'M1', 'days': 2, 'option_longer_days': 'a',
                             'option_extra_days': 'b', 'option_shift': 'c'}]}
    p = tmp_path / 'wx.xlsx'
    write_weather_xlsx(str(p), ca, weather)
    _all_wellformed(str(p))
    txt = _sheets_text(str(p))
    assert txt.count('s="10"') >= 2          # the 2 bad-weather days painted amber (+ legend swatch)
    assert 'Bad-weather day' in txt          # weather legend
    assert 'Working' in txt and 'Non-working' in txt
    assert 'Upcoming Bad-Weather Days' in txt and 'Causing the Lost Days' in txt
    assert '>#<' in txt                       # serial column header (# cell)


def test_workbook_has_a_sheet_per_calendar_plus_report_tables(tmp_path):
    p = tmp_path / 'cal.xlsx'
    write_calendar_xlsx(str(p), _ca(), weather=_weather())
    with zipfile.ZipFile(p) as z:
        n_sheets = len([n for n in z.namelist() if n.startswith('xl/worksheets/sheet')])
        wb = z.read('xl/workbook.xml').decode()
    # C1, C2, Exceptions, Comparison, Usage, Weather + the rest of the report (owner comment 29)
    assert n_sheets >= 6
    # sheet names sanitise '/' → '-' (illegal in Excel sheet names)
    for s in ['5 Days-Week', '6 Days-Week', 'Exceptions', 'Comparison', 'Usage', 'Weather']:
        assert s in wb
    _all_wellformed(p)


def test_meta_header_block_on_first_sheet(tmp_path):
    """The standard report header/context block (app — feature / Project / Data date /
    Generated) is prepended to the first sheet, matching every other export."""
    meta = {'app': 'Controlyx', 'title': 'Calendar Audit',
            'context': [('Project', 'Metro Pkg 3'), ('Data date', '09-Feb.2026'),
                        ('Generated', '15-Sep.2026')]}
    p = tmp_path / 'cal.xlsx'
    write_calendar_xlsx(str(p), _ca(), weather=_weather(), meta=meta)
    with zipfile.ZipFile(p) as z:
        s1 = z.read('xl/worksheets/sheet1.xml').decode()
    assert 'Controlyx — Calendar Audit' in s1          # report title (style 11)
    assert 'Metro Pkg 3' in s1 and 'Data date: 09-Feb.2026' in s1   # context line (style 12)
    assert 's="11"' in s1 and 's="12"' in s1               # the two new report-block styles
    assert 'Calendar Timeline' in s1                        # the per-calendar title still follows
    _all_wellformed(p)
    # weather workbook carries the same block
    from p6_evm.xlsx_writer import write_weather_xlsx
    pw = tmp_path / 'wx.xlsx'
    write_weather_xlsx(str(pw), _ca(), _weather(),
                       meta={'app': 'Controlyx', 'title': 'Bad Weather', 'context': []})
    with zipfile.ZipFile(pw) as z:
        assert 'Controlyx — Bad Weather' in z.read('xl/worksheets/sheet1.xml').decode()
    _all_wellformed(pw)


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
    assert 'Affected work (by WBS)' in txt and 'Excavation' in txt


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


def test_weather_workbook_carries_the_dashboard_histogram_and_limits(tmp_path):
    """Final sweep (comment 3): the Bad Weather workbook had only report sections 4–7. It now
    also carries §1 the Execution Dashboard figures, §2 the days per month, the Stop-Work
    Criteria table and §3 how each limit performed — the same figures as the PDF."""
    from p6_evm.xlsx_writer import write_weather_xlsx
    ca = dict(_ca(), dashboard={'baseline_finish': '2025-09-01', 'project_finish': '2025-09-11'})
    w = dict(_weather(), expected_bad_days_total=7, net_finish_delay=4,
             weather_adjusted_finish='2025-09-17',
             histogram=[{'label': 'Aug 25', 'net': 20, 'bad': 3, 'nonworking': 8}],
             site_type_label='Coastal',
             criteria=[{'icon': '', 'label': 'Heat', 'value': '≥ 42 °C', 'explain': 'Concrete pours', 'on': True},
                       {'icon': '', 'label': 'Dust', 'value': 'PM10 ≥ 300', 'explain': 'Lifting', 'on': False}],
             limit_performance=[{'label': 'Heat', 'on': True, 'limit': 42, 'unit': '°C', 'flagged': 5, 'peak': 46},
                                {'label': 'Wind', 'on': False, 'unit': 'km/h', 'peak': 38}])
    p = tmp_path / 'wx.xlsx'
    write_weather_xlsx(str(p), ca, w)
    _all_wellformed(p)
    import openpyxl
    ws = openpyxl.load_workbook(p)['Weather Detail']
    vals = [[c for c in r if c is not None] for r in ws.iter_rows(values_only=True)]
    flat = [str(x) for r in vals for x in r]
    for title in ('Execution Dashboard — estimate, not a P6 figure',
                  'Calendar Timeline & Statistics — days per month', 'Stop-Work Criteria — Coastal',
                  'Why This Result — How Each Limit Performed', 'Upcoming Bad-Weather Days'):
        assert title in flat, title
    assert ['Schedule slip (calendar days)', '+10 d'] in vals
    assert ['Weather adds (working days)', '+4 wd'] in vals
    assert ['Bad-weather Completion', '17-Sep.2025'] in vals
    assert ['Aug 25', 20, 3, 8] in vals
    assert ['Dust', 'PM10 ≥ 300', 'Lifting (not counted)'] in vals
    assert ['Heat', 'on', '≥ 42 °C', 5, '46 °C'] in vals
    assert [x for x in next(r for r in vals if r and r[0] == 'Wind') if x != ''] == ['Wind', 'off (not counted)', '38 km/h']
    # the dashboard comes first, the day list after the limits — the report's order
    assert flat.index('Execution Dashboard — estimate, not a P6 figure') < flat.index('Upcoming Bad-Weather Days')


def test_calendar_and_weather_workbooks_centre_their_cells():
    """Owner, on comment 58: the data sits in the middle of the Excel cells."""
    import re
    from p6_evm import xlsx_writer as xw
    xfs = re.findall(r'<xf[^>]*?(?:/>|>.*?</xf>)', xw._CAL_STYLES[xw._CAL_STYLES.index('<cellXfs'):], re.S)
    centred = '<alignment horizontal="center" vertical="center" wrapText="1"/>'
    for i in (2, 3, 4, 5, 6, 7, 10, xw._CAL_CENTER_STYLE):          # header, day cells, table cells
        assert centred in xfs[i], i
    xml = xw._stacked_sheet([{'title': 'T', 'headers': ['A', 'B'], 'rows': [['x', 5]]}],
                            title_style=9, note_style=0, header_style=2, data_style=xw._CAL_CENTER_STYLE)
    assert f'<c r="A3" s="{xw._CAL_CENTER_STYLE}"' in xml and f'<c r="B3" s="{xw._CAL_CENTER_STYLE}"' in xml
