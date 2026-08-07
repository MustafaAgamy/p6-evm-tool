"""XER calendars carry their working week + holidays inside the CALENDAR.clndr_data blob.
Parsing it (like the XML parser reads <WorkTime>) is what lets an attached-baseline XER's
Planned% and Delay match the XML to the penny — otherwise the XER counts all 7 days as working.

P6 clndr_data facts encoded here:
  - DaysOfWeek entries are keyed 1..7 where 1 = Sunday .. 7 = Saturday.
  - A day with no work shifts is a non-working day.
  - Exceptions carry an Excel-style date serial (days since 1899-12-30); with shifts = an added
    working day, without = a holiday.
"""
from datetime import date
from p6_evm.clndr import parse_clndr_data
from p6_evm.xer import parse_xer

# 5-day week: Mon–Fri work 08:00–12:00 and 13:00–17:00; Sat/Sun off.
# One holiday (2026-01-01, serial 46023) and one added working Saturday (2026-01-10, serial 46032).
BLOB = (
    "(0||CalendarData()(0||DaysOfWeek()"
    "(0||1()())"                                                   # Sunday  — off
    "(0||2()(0||0(s|08:00|f|12:00)(0||1(s|13:00|f|17:00))))"       # Monday
    "(0||3()(0||0(s|08:00|f|12:00)(0||1(s|13:00|f|17:00))))"       # Tuesday
    "(0||4()(0||0(s|08:00|f|12:00)(0||1(s|13:00|f|17:00))))"       # Wednesday
    "(0||5()(0||0(s|08:00|f|12:00)(0||1(s|13:00|f|17:00))))"       # Thursday
    "(0||6()(0||0(s|08:00|f|12:00)(0||1(s|13:00|f|17:00))))"       # Friday
    "(0||7()())"                                                   # Saturday — off
    ")(0||Exceptions()"
    "(0||0(d|46023)())"                                            # holiday 2026-01-01
    "(0||1(d|46032)(0||0(s|08:00|f|12:00)))"                       # added work 2026-01-10 (half day)
    "))"
)


def test_workdays_and_shifts():
    c = parse_clndr_data(BLOB)
    # Monday–Friday are working with two shifts (08:00–12:00 = 480–720, 13:00–17:00 = 780–1020)
    for day in ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'):
        assert c['work_intervals'][day] == [(480, 720), (780, 1020)]
    # Saturday + Sunday carry no work → non-working
    assert c['nonworking_days'] == {'Saturday', 'Sunday'}


def test_holiday_and_added_work_exceptions():
    c = parse_clndr_data(BLOB)
    assert date(2026, 1, 1) in c['holidays']
    assert date(2026, 1, 10) in c['added_work_days']
    assert c['exception_intervals'][date(2026, 1, 10)] == [(480, 720)]
    # a working exception is never also a holiday
    assert date(2026, 1, 10) not in c['holidays']


def test_empty_blob_is_safe():
    c = parse_clndr_data('')
    assert c['work_intervals'] == {}
    assert c['nonworking_days'] == set()
    assert c['holidays'] == set()


def test_parse_xer_fills_intraday_calendar(tmp_path):
    """End-to-end: a XER whose CALENDAR row carries clndr_data yields an intraday-capable
    Calendar (has_intraday() True), so working-time math matches the XML path."""
    xer = (
        "ERMHDR\t19.12\n"
        "%T\tCALENDAR\n"
        "%F\tclndr_id\tclndr_name\tday_hr_cnt\tclndr_data\n"
        f"%R\tC1\t5 Day Workweek\t8\t{BLOB}\n"
        "%T\tPROJECT\n"
        "%F\tproj_id\tproj_short_name\tlast_recalc_date\n"
        "%R\t1\tJOB\t2026-02-09 00:00\n"
        "%E\n"
    )
    p = tmp_path / "c.xer"
    p.write_text(xer, encoding='cp1252')
    data = parse_xer(str(p))
    cal = data.calendars['C1']
    assert cal.has_intraday() is True
    assert 'Saturday' in cal.nonworking_days and 'Sunday' in cal.nonworking_days
    assert date(2026, 1, 1) in cal.holidays
