"""The Calendar day index (working_minutes / signed_working_days / float_working_days) must give
exactly what counting one day at a time gives - the index is a speed-up, never a new rule."""
import random
from datetime import date, datetime, timedelta

from p6_evm.calendars import (Calendar, float_working_days, signed_working_days,
                              signed_working_minutes)


def _by_day_minutes(cal, start, end):
    if end <= start:
        return 0.0
    total, d = 0.0, start.date()
    while d <= end.date():
        total += cal._day_overlap(d, start, end)
        d += timedelta(days=1)
    return total


def _by_day_signed_days(cal, start, end):
    sign, a, b = 1, start, end
    if b < a:
        a, b, sign = b, a, -1
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        n += cal.is_working_day(d.date())
    return sign * n


def _by_day_float_days(cal, early, late):
    sign, a, b = 1, early, late
    if b < a:
        a, b, sign = b, a, -1
    n, d = 0, a.date()
    while d <= b.date():
        if cal.is_working_day(d) and not ((d == a.date() and a.hour >= 12) or (d == b.date() and b.hour < 12)):
            n += 1
        d += timedelta(days=1)
    return sign * n


def _calendar():
    """Sun-Thu 08:00-12:00 + 13:00-17:00, Fri off, Sat 08:00-12:00, a holiday, a worked Friday
    with its own hours, and a 24-hour exception day."""
    week = {dow: [(480, 720), (780, 1020)] for dow in ('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday')}
    week['Saturday'] = [(480, 720)]
    return Calendar(object_id='1', name='Site', nonworking_days={'Friday'},
                    holidays={date(2025, 3, 10)}, added_work_days={date(2025, 3, 14), date(2025, 4, 1)},
                    work_intervals=week,
                    exception_intervals={date(2025, 3, 14): [(540, 900)], date(2025, 4, 1): [(0, 1440)]},
                    weekly_working_days=set(week))


def _spans(rng, n):
    base = datetime(2025, 1, 1)
    for _ in range(n):
        a = base + timedelta(days=rng.randint(-60, 500), minutes=rng.randint(0, 1439), seconds=rng.choice([0, 0, 30]))
        b = a + rng.choice([1, -1]) * timedelta(minutes=rng.choice([0, 1, 300, 1440, 4000, rng.randint(1, 900_000)]))
        yield a, b


def test_index_matches_day_by_day_counting():
    cal, rng = _calendar(), random.Random(7)
    for a, b in _spans(rng, 3000):
        assert abs(cal.working_minutes(a, b) - _by_day_minutes(cal, a, b)) < 1e-9
        assert signed_working_days(cal, a, b) == _by_day_signed_days(cal, a, b)
        assert float_working_days(cal, a, b) == _by_day_float_days(cal, a, b)
        sm = signed_working_minutes(cal, a, b)
        assert abs(sm - (_by_day_minutes(cal, a, b) if b >= a else -_by_day_minutes(cal, b, a))) < 1e-9


def test_index_rebuilds_when_the_calendar_changes():
    cal = _calendar()
    a, b = datetime(2025, 3, 1, 8), datetime(2025, 3, 31, 17)
    before = cal.working_minutes(a, b)
    cal.holidays.add(date(2025, 3, 17))          # a Monday: 8 h less
    assert cal.working_minutes(a, b) == before - 480
    assert signed_working_days(cal, a, b) == _by_day_signed_days(cal, a, b)


def test_interval_past_midnight_falls_back_to_day_by_day():
    cal = _calendar()
    cal.work_intervals = dict(cal.work_intervals, Monday=[(1200, 1560)])   # 20:00 -> 02:00 next day
    a, b = datetime(2025, 3, 2, 0), datetime(2025, 3, 25, 1)
    assert cal.working_minutes(a, b) == _by_day_minutes(cal, a, b)


def test_far_off_dates_are_counted_without_an_index():
    cal = _calendar()
    a, b = datetime(1990, 1, 1), datetime(2080, 1, 1)
    assert signed_working_days(cal, a, b) == _by_day_signed_days(cal, a, b)
    assert cal._idx is None


def test_stand_in_calendar_still_works():
    class Weekdays:
        def is_working_day(self, d):
            return d.weekday() < 5
    a, b = datetime(2025, 3, 3, 9), datetime(2025, 3, 17, 9)
    assert signed_working_days(Weekdays(), a, b) == 10
    assert float_working_days(Weekdays(), a, b) == _by_day_float_days(Weekdays(), a, b) == 10


def test_index_is_not_part_of_calendar_identity():
    a, b = _calendar(), _calendar()
    a.working_minutes(datetime(2025, 3, 1), datetime(2025, 6, 1))
    assert a == b and '_idx' not in repr(a)
