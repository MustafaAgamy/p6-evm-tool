"""Parse a P6 XER CALENDAR.clndr_data blob into the same working-time fields the XML parser
fills (work_intervals / nonworking_days / holidays / added_work_days / exception_intervals),
so a XER-built Calendar measures working time exactly like an XML one.

clndr_data format (P6):
  (0||CalendarData()(0||DaysOfWeek()(0||1()(...shifts...))...(0||7()()))(0||Exceptions()(0||K(d|SERIAL)(...shifts...))...))
  - DaysOfWeek entries keyed 1..7 where 1 = Sunday .. 7 = Saturday; a day with no shift is non-working.
  - each shift is  s|HH:MM|f|HH:MM  (start / finish, 24h; 24:00 = end of day).
  - Exceptions carry an Excel-style date serial (days since 1899-12-30); with shifts = an added
    working day, without shifts = a holiday.
Parsing is defensive: anything unrecognised is skipped, an empty/None blob yields empty sets so the
caller falls back to the bare (whole-day) calendar it built before.
"""
import re
from datetime import date, timedelta

from p6_evm.calendars import hhmmss_to_min

_P6_DOW = {1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday',
           5: 'Thursday', 6: 'Friday', 7: 'Saturday'}
_EPOCH = date(1899, 12, 30)                       # P6/Excel serial-date origin
_SHIFT_RE = re.compile(r's\|(\d{1,2}:\d{2})\|f\|(\d{1,2}:\d{2})')
_DAY_RE = re.compile(r'0\|\|([1-7])\(\)')          # a weekday header 0||N() (empty parens disambiguates from a shift 0||K(s|..))
_EXC_RE = re.compile(r'd\|(\d+)')                  # an exception's date serial


def _intervals(segment):
    out = []
    for s, f in _SHIFT_RE.findall(segment):
        sm, em = hhmmss_to_min(s), hhmmss_to_min(f)
        if sm is not None and em is not None and em > sm:
            out.append((sm, em))
    return out


def parse_clndr_data(blob):
    result = {'work_intervals': {}, 'nonworking_days': set(),
              'holidays': set(), 'added_work_days': set(), 'exception_intervals': {}}
    if not blob:
        return result

    # Separate the weekly pattern from the exceptions so an exception's shifts never leak into a weekday.
    idx = blob.find('Exceptions')
    days_part = blob[:idx] if idx != -1 else blob
    exc_part = blob[idx:] if idx != -1 else ''

    # Weekly pattern: each 0||N() header owns every shift up to the next header.
    day_hdrs = list(_DAY_RE.finditer(days_part))
    for i, m in enumerate(day_hdrs):
        dow = _P6_DOW[int(m.group(1))]
        seg_end = day_hdrs[i + 1].start() if i + 1 < len(day_hdrs) else len(days_part)
        ivs = _intervals(days_part[m.end():seg_end])
        if ivs:
            result['work_intervals'][dow] = ivs
        else:
            result['nonworking_days'].add(dow)

    # Exceptions: each d|SERIAL owns every shift up to the next d|.
    exc = list(_EXC_RE.finditer(exc_part))
    for i, m in enumerate(exc):
        seg_end = exc[i + 1].start() if i + 1 < len(exc) else len(exc_part)
        try:
            d = _EPOCH + timedelta(days=int(m.group(1)))
        except (OverflowError, ValueError):
            continue
        ivs = _intervals(exc_part[m.end():seg_end])
        if ivs:
            result['added_work_days'].add(d)
            result['exception_intervals'][d] = ivs
        else:
            result['holidays'].add(d)
    return result
