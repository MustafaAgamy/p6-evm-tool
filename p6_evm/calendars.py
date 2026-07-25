from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

DOW_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


@dataclass
class Calendar:
    object_id: str
    name: str
    nonworking_days: set = field(default_factory=set)
    holidays: set = field(default_factory=set)
    added_work_days: set = field(default_factory=set)

    def is_working_day(self, d: date) -> bool:
        if d in self.added_work_days:
            return True
        if d in self.holidays:
            return False
        return DOW_NAMES[d.weekday()] not in self.nonworking_days


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
