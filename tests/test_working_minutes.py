"""Working-MINUTES planned %: P6 measures Schedule % Complete in the calendar's intraday
work hours, not whole days. This is what makes Planned Value match P6 exactly on part-way
activities (verified against real files: Alstom PV 366,521.75, Saint Gobain 243,805,396.80)."""
from datetime import datetime
from p6_evm.calendars import Calendar, hhmmss_to_min
from p6_evm.metrics import activity_planned_pct


def _cal8():
    # Mon–Fri, 08:00–12:00 and 13:00–17:00 = 8 working hours/day
    iv = [(480, 720), (780, 1020)]
    return Calendar(object_id='C', name='8h/day',
                    work_intervals={d: iv for d in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']})


def test_hhmmss_to_min():
    assert hhmmss_to_min('08:00:00') == 480
    assert hhmmss_to_min('16:59:00') == 1019
    assert hhmmss_to_min('00:00') == 0
    assert hhmmss_to_min('') is None and hhmmss_to_min(None) is None


def test_has_intraday():
    assert _cal8().has_intraday() is True
    assert Calendar(object_id='X', name='none').has_intraday() is False


def test_working_minutes_partial_day():
    c = _cal8()   # Mon 2026-01-05
    # 10:00 → 15:00 = 2h morning (10–12) + 2h afternoon (13–15) = 240 min (the lunch gap excluded)
    assert c.working_minutes(datetime(2026, 1, 5, 10, 0), datetime(2026, 1, 5, 15, 0)) == 240
    # full work day = 480 min
    assert c.working_minutes(datetime(2026, 1, 5, 8, 0), datetime(2026, 1, 5, 17, 0)) == 480


def test_working_minutes_skips_weekend():
    c = _cal8()
    # Fri 17:00 → Mon 08:00 spans only the weekend → 0 working minutes
    assert c.working_minutes(datetime(2026, 1, 9, 17, 0), datetime(2026, 1, 12, 8, 0)) == 0
    # Mon 08:00 → Tue 12:00 = Mon full (8h) + Tue morning (4h) = 720 min
    assert c.working_minutes(datetime(2026, 1, 5, 8, 0), datetime(2026, 1, 6, 12, 0)) == 720


def test_planned_pct_is_hours_based_not_whole_day():
    c = _cal8()
    cals = {'C': c}
    act = {'id': 'A', 'calendar_id': 'C'}
    bl = {'A': {'planned_start': datetime(2026, 1, 5, 8, 0), 'planned_finish': datetime(2026, 1, 5, 17, 0)}}
    # data date at Mon 12:00 → 4 of 8 work-hours done = 50% (whole-day counting would say 0% or 100%)
    pp = activity_planned_pct(act, bl, datetime(2026, 1, 5, 12, 0), cals)
    assert round(pp, 4) == 0.5
