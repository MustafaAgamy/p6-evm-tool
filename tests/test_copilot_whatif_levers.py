"""What-if levers added in V2 Slice 5: add-a-crew, overtime, remove-a-constraint.

Crew / overtime compress an activity's remaining duration and only move the finish when it's
on the critical path; remove-a-constraint is a qualitative read that routes to F9 for the
exact figure. A fake ScheduleData carries just what estimate() reads.
"""
from datetime import datetime

from p6_copilot.whatif import estimate


class _Cal:
    day_hours = 8.0

    def is_working_day(self, d):
        return d.weekday() < 5


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
                  'calendar_id': 'C', 'task_type': 'FinishMilestone', 'planned_finish': datetime(2026, 3, 1)},
        }
        # CR (oid 'a') has a driving predecessor; SL (oid 'b') has none.
        self.relationships = [{'pred_id': 'x', 'succ_id': 'a', 'type': 'FS', 'lag_days': 0}]


def test_add_crew_on_critical_pulls_in_about_40pct():
    d = estimate(_Data(), 'add_crew', 'CR')            # 10 wd remaining * 0.40
    assert d['impact_days'] == -4 and d['direction'] == 'earlier'
    assert d['estimate'] is True


def test_add_crew_non_critical_changes_nothing():
    d = estimate(_Data(), 'add_crew', 'SL')
    assert d['impact_days'] == 0 and d['direction'] == 'none'
    assert 'critical path' in d['advice'].lower()


def test_overtime_on_critical_pulls_in_about_15pct():
    d = estimate(_Data(), 'overtime', 'CR')            # round(10 * 0.15) = 2
    assert d['impact_days'] == -2 and d['direction'] == 'earlier'


def test_remove_constraint_on_critical_is_qualitative_and_routes_to_f9():
    d = estimate(_Data(), 'remove_relationship', 'CR')
    assert d.get('qualitative') is True and d['impact_days'] is None
    assert 'f9' in (d['headline'] + ' ' + d['advice']).lower()


def test_remove_constraint_non_critical_changes_nothing():
    d = estimate(_Data(), 'remove_relationship', 'SL')
    assert d['impact_days'] == 0 and d['direction'] == 'none'


def test_remove_constraint_critical_but_no_predecessor_says_none():
    data = _Data()
    data.relationships = []                            # CR now has no predecessor links
    d = estimate(data, 'remove_relationship', 'CR')
    assert d['impact_days'] == 0 and 'no predecessor' in d['headline'].lower()
