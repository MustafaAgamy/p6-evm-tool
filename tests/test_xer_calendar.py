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


# P6 also emits shifts FINISH-first: "f|finish|s|start" (seen in Saint-Gobain's real export).
# The parser must read them the same as "s|start|f|finish", else every day looks non-working.
FINISH_FIRST = (
    "(0||CalendarData()((0||DaysOfWeek()"
    "((0||1()((0||0(f|12:00|s|07:00)())(0||1(f|19:00|s|13:00)())))"   # Sunday: 07:00-12:00, 13:00-19:00
    "(0||2()((0||0(f|12:00|s|07:00)())(0||1(f|19:00|s|13:00)())))"
    "(0||3()((0||0(f|12:00|s|07:00)())(0||1(f|19:00|s|13:00)())))"
    "(0||4()((0||0(f|12:00|s|07:00)())(0||1(f|19:00|s|13:00)())))"
    "(0||5()((0||0(f|12:00|s|07:00)())(0||1(f|19:00|s|13:00)())))"
    "(0||6()())"                                                      # Friday off (6 = Friday)
    "(0||7()((0||0(f|12:00|s|07:00)())(0||1(f|19:00|s|13:00)())))))"  # Saturday worked
    "(0||Exceptions()())))"
)


def test_finish_first_shift_order():
    c = parse_clndr_data(FINISH_FIRST)
    # start=07:00 (420), finish=12:00 (720) and start=13:00 (780), finish=19:00 (1140) — 11h day
    assert c['work_intervals']['Sunday'] == [(420, 720), (780, 1140)]
    assert c['work_intervals']['Saturday'] == [(420, 720), (780, 1140)]
    # only Friday is non-working (a 6-day week), NOT all 7 days
    assert c['nonworking_days'] == {'Friday'}


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


# P6 writes a 24-hour day midnight-to-midnight, "s|00:00|f|00:00" (real SG 10095 "7 Days Per
# Week (AS3) - 24 Hrs per day" and GBT exception 2025-10-08); the XML twin writes 00:00-23:59.
# Finding P4: reading the 00:00 finish as minute 0 dropped the shift, so every 24-h weekday was
# NON-working and every 24-h exception day became a holiday.
TWENTY_FOUR_SEVEN = (
    "(0||CalendarData()((0||DaysOfWeek()("
    + "".join(f"(0||{n}()((0||0(s|00:00|f|00:00)())))" for n in range(1, 8))
    + "))(0||VIEW(ShowTotal|N)())(0||Exceptions()("
    "(0||0(d|45938)((0||0(s|00:00|f|00:00)())))"          # 2025-10-08 worked 24 h
    "(0||1(d|45939)())"                                     # 2025-10-09 holiday
    "(0||2(d|45940)((0||0(s|16:00|f|00:00)())))"          # 2025-10-10 16:00 to midnight
    "))))"
)


def test_24_hour_weekdays_are_working():
    c = parse_clndr_data(TWENTY_FOUR_SEVEN)
    assert c['nonworking_days'] == set()
    assert c['weekly_working_days'] == {'Sunday', 'Monday', 'Tuesday', 'Wednesday',
                                        'Thursday', 'Friday', 'Saturday'}
    for day, ivs in c['work_intervals'].items():
        assert ivs == [(0, 1440)], day                       # 24 working hours


def test_24_hour_exception_is_added_work_not_a_holiday():
    c = parse_clndr_data(TWENTY_FOUR_SEVEN)
    assert c['holidays'] == {date(2025, 10, 9)}
    assert c['added_work_days'] == {date(2025, 10, 8), date(2025, 10, 10)}
    assert c['exception_intervals'][date(2025, 10, 8)] == [(0, 1440)]
    assert c['exception_intervals'][date(2025, 10, 10)] == [(960, 1440)]   # 16:00-24:00


def test_24_hour_calendar_measures_working_time(tmp_path):
    """End-to-end: a 24/7 XER calendar counts 24 working hours a day (was 0)."""
    from datetime import datetime
    xer = (
        "ERMHDR\t19.12\n"
        "%T\tCALENDAR\n"
        "%F\tclndr_id\tclndr_name\tday_hr_cnt\tclndr_data\n"
        f"%R\tC24\t24 Hrs\t24\t{TWENTY_FOUR_SEVEN}\n"
        "%T\tPROJECT\n"
        "%F\tproj_id\tproj_short_name\tlast_recalc_date\n"
        "%R\t1\tJOB\t2026-02-09 00:00\n"
        "%E\n"
    )
    p = tmp_path / "c24.xer"
    p.write_text(xer, encoding='cp1252')
    cal = parse_xer(str(p)).calendars['C24']
    assert cal.nonworking_days == set()
    assert cal.working_minutes(datetime(2026, 2, 2), datetime(2026, 2, 3)) == 1440
