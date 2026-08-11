"""Tests for the instant offline what-if estimates (p6_copilot/whatif.py).

A fake ScheduleData carries just what estimate() reads — activity float, durations, a finish
milestone — so we test the estimate logic directly (delay netted against spare time; a speed-up
only helps on the critical path)."""
from datetime import datetime

import pytest

from p6_copilot.whatif import estimate


class _Cal:
    day_hours = 8.0

    def is_working_day(self, d):
        return d.weekday() < 5      # Mon-Fri


class _Data:
    def __init__(self):
        self.calendars = {'C': _Cal()}
        self.project = {'data_date': datetime(2026, 1, 1)}
        self.activities = {
            'a': {'id': 'CR', 'name': 'Critical task', 'total_float_days': 0, 'planned_duration': 80,
                  'calendar_id': 'C', 'task_type': 'Task'},
            'b': {'id': 'SL', 'name': 'Slack task', 'total_float_days': 10, 'planned_duration': 40,
                  'calendar_id': 'C', 'task_type': 'Task'},
            'm': {'id': 'FIN', 'name': 'Finish', 'total_float_days': 0, 'planned_duration': 0,
                  'calendar_id': 'C', 'task_type': 'FinishMilestone',
                  'planned_finish': datetime(2026, 3, 1), 'remaining_early_finish': None},
        }


def test_delay_on_critical_pushes_the_whole_slip():
    d = estimate(_Data(), 'delay', 'CR', 7)
    assert d['impact_days'] == 7 and d['direction'] == 'later'
    assert 'critical path' in d['basis'].lower()
    assert d['estimate'] is True


def test_delay_fully_absorbed_by_spare_time():
    d = estimate(_Data(), 'delay', 'SL', 6)          # 6 <= 10 days spare
    assert d['impact_days'] == 0 and d['direction'] == 'none'
    assert 'spare time' in d['basis'].lower()


def test_delay_partly_absorbed_nets_against_float():
    assert estimate(_Data(), 'delay', 'SL', 14)['impact_days'] == 4   # 14 - 10 spare


def test_shorten_critical_pulls_the_finish_in():
    d = estimate(_Data(), 'shorten', 'CR', 5)         # critical, remaining 10 wd -> min(5,10)
    assert d['impact_days'] == -5 and d['direction'] == 'earlier'


def test_shorten_non_critical_does_nothing_and_says_so():
    d = estimate(_Data(), 'shorten', 'SL', 5)
    assert d['impact_days'] == 0
    assert 'critical' in d['advice'].lower()


def test_six_day_pulls_in_and_gives_advice():
    d = estimate(_Data(), 'six_day')
    assert d['impact_days'] <= 0 and d['direction'] in ('earlier', 'none')
    assert d['advice'] and d['estimate'] is True


def test_unknown_activity_and_kind_raise():
    with pytest.raises(KeyError):
        estimate(_Data(), 'delay', 'NOPE', 3)
    with pytest.raises(ValueError):
        estimate(_Data(), 'teleport')
