from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

DOW_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def hhmmss_to_min(s):
    """'HH:MM:SS' (or 'HH:MM') -> minutes past midnight, or None."""
    if not s:
        return None
    parts = s.split(':')
    try:
        h = int(parts[0]); m = int(parts[1]) if len(parts) > 1 else 0
        return h * 60 + m
    except (ValueError, IndexError):
        return None


@dataclass
class Calendar:
    object_id: str
    name: str
    nonworking_days: set = field(default_factory=set)
    holidays: set = field(default_factory=set)
    added_work_days: set = field(default_factory=set)
    day_hours: float = 8.0
    # Intraday work schedule (P6's actual work times), for exact working-time %:
    work_intervals: dict = field(default_factory=dict)       # DOW name -> [(start_min, end_min), ...]
    exception_intervals: dict = field(default_factory=dict)  # date -> [(start_min, end_min), ...]
    # Calendar Audit metadata (additive — never affects EVM math):
    type: str = ''            # 'Global' | 'Project' | 'Resource' (raw P6 Type), '' when absent
    is_default: bool = False  # P6 IsDefault flag

    def is_working_day(self, d: date) -> bool:
        if d in self.added_work_days:
            return True
        if d in self.holidays:
            return False
        return DOW_NAMES[d.weekday()] not in self.nonworking_days

    def has_intraday(self) -> bool:
        """True when the calendar carries real intraday work times (from an XML export),
        so working_minutes() is meaningful. XER-built/minimal calendars return False and
        callers fall back to whole-working-day counting."""
        return bool(self.work_intervals or self.exception_intervals)

    def _intervals_for(self, d: date):
        if d in self.exception_intervals:
            return self.exception_intervals[d]
        if d in self.holidays:
            return []
        if DOW_NAMES[d.weekday()] in self.nonworking_days:
            return []
        return self.work_intervals.get(DOW_NAMES[d.weekday()], [])

    def working_minutes(self, start: datetime, end: datetime) -> float:
        """Working time between two datetimes, in minutes, using the calendar's intraday
        work intervals + holidays/exceptions. This is how P6 measures Schedule % Complete
        (part-way activities count in work HOURS, not whole days)."""
        if start is None or end is None or end <= start:
            return 0.0
        total = 0.0
        d = start.date()
        last = end.date()
        while d <= last:
            base = datetime(d.year, d.month, d.day)
            for sm, em in self._intervals_for(d):
                lo = max(base + timedelta(minutes=sm), start)
                hi = min(base + timedelta(minutes=em), end)
                if hi > lo:
                    total += (hi - lo).total_seconds() / 60.0
            d += timedelta(days=1)
        return total


def signed_working_days(calendar: Calendar, start: datetime, end: datetime):
    """Working-day count from start to end, signed negative if end precedes start.

    Total Float in P6 is measured on the activity's own calendar, not raw
    calendar days -- a flat datetime subtraction silently ignores weekends
    and project holidays and will not match P6's reported figure.
    """
    if calendar is None or start is None or end is None:
        return None
    sign = 1
    a, b = start, end
    if b < a:
        a, b = b, a
        sign = -1
    n = 0
    d = a
    while d < b:
        d += timedelta(days=1)
        if calendar.is_working_day(d.date()):
            n += 1
    return sign * n


def float_working_days(calendar: Calendar, early: datetime, late: datetime):
    """Total Float in whole working days, boundary-correct — for the DELAY figure only.

    Unlike signed_working_days (whose convention cancels out in the ratio-based planned%),
    the absolute Total Float must not count a boundary day that carries no working time
    (a late date at end-of-day, an early date at start-of-day). Counting the whole working
    days strictly BETWEEN the two dates matches P6 exactly (a milestone 10 days late = −10).
    """
    if calendar is None or early is None or late is None:
        return None
    sign = 1
    a, b = early, late
    if b < a:
        a, b = b, a
        sign = -1
    # Count working days whose work lies inside [a, b]. A boundary day is excluded only when
    # its working time is outside: the lower date if it starts in the afternoon (work already
    # done), the upper date if it ends in the morning (work not yet begun). Midday split ~12:00.
    ad, bd = a.date(), b.date()
    n = 0
    d = ad
    while d <= bd:
        if calendar.is_working_day(d):
            skip = (d == ad and a.hour >= 12) or (d == bd and b.hour < 12)
            if not skip:
                n += 1
        d += timedelta(days=1)
    return sign * n
