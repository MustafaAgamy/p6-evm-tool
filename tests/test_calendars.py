"""Tests for p6_evm/calendars.py — Calendar + signed_working_days."""
from datetime import date, datetime

import pytest

from p6_evm.calendars import Calendar, signed_working_days

# Standard Mon-Fri calendar used in most tests
@pytest.fixture
def std_cal():
    return Calendar('1', 'Standard', nonworking_days={'Saturday', 'Sunday'})


# ── Calendar.is_working_day ────────────────────────────────────────────────

def test_weekday_is_working(std_cal):
    assert std_cal.is_working_day(date(2024, 7, 1))   # Monday

def test_saturday_nonworking(std_cal):
    assert not std_cal.is_working_day(date(2024, 7, 6))  # Saturday

def test_sunday_nonworking(std_cal):
    assert not std_cal.is_working_day(date(2024, 7, 7))  # Sunday

def test_holiday_overrides_weekday(std_cal):
    std_cal.holidays.add(date(2024, 7, 1))             # Monday flagged as holiday
    assert not std_cal.is_working_day(date(2024, 7, 1))

def test_added_work_day_overrides_weekend(std_cal):
    std_cal.added_work_days.add(date(2024, 7, 6))      # Saturday made working
    assert std_cal.is_working_day(date(2024, 7, 6))

def test_calendar_with_no_restrictions():
    cal = Calendar('1', 'All-week', nonworking_days=set())
    assert cal.is_working_day(date(2024, 7, 6))        # Saturday allowed


# ── signed_working_days ────────────────────────────────────────────────────

def test_none_calendar_returns_none(std_cal):
    result = signed_working_days(None, datetime(2024, 7, 1), datetime(2024, 7, 5))
    assert result is None

def test_none_start_returns_none(std_cal):
    assert signed_working_days(std_cal, None, datetime(2024, 7, 5)) is None

def test_none_end_returns_none(std_cal):
    assert signed_working_days(std_cal, datetime(2024, 7, 1), None) is None

def test_forward_weekdays_only(std_cal):
    # Mon Jul 1 → Fri Jul 5: counts Tue-Fri (exclusive start, inclusive end) = 4
    result = signed_working_days(std_cal, datetime(2024, 7, 1), datetime(2024, 7, 5))
    assert result == 4

def test_spans_weekend(std_cal):
    # Fri Jul 5 → Mon Jul 8: Sat+Sun skip, Mon = 1
    result = signed_working_days(std_cal, datetime(2024, 7, 5), datetime(2024, 7, 8))
    assert result == 1

def test_same_start_and_end(std_cal):
    result = signed_working_days(std_cal, datetime(2024, 7, 1), datetime(2024, 7, 1))
    assert result == 0

def test_negative_when_end_before_start(std_cal):
    # Symmetric with the forward case
    result = signed_working_days(std_cal, datetime(2024, 7, 5), datetime(2024, 7, 1))
    assert result == -4

def test_holiday_reduces_count(std_cal):
    # Jul 1-5 normally = 4 working days; add a holiday on Wed Jul 3 → 3
    std_cal.holidays.add(date(2024, 7, 3))
    result = signed_working_days(std_cal, datetime(2024, 7, 1), datetime(2024, 7, 5))
    assert result == 3

def test_added_work_day_increases_count(std_cal):
    # Jul 5 (Fri) → Jul 8 (Mon) normally = 1; add Sat Jul 6 as working → 2
    std_cal.added_work_days.add(date(2024, 7, 6))
    result = signed_working_days(std_cal, datetime(2024, 7, 5), datetime(2024, 7, 8))
    assert result == 2
