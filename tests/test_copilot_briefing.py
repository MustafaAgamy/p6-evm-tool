"""Manager Report extras (parse-derived): the named critical activities and the add-a-crew
recovery estimate with the new finish date."""
from datetime import datetime

from p6_copilot.briefing import critical_drivers, recovery_estimate, _minus_working_days


class _Cal:
    day_hours = 8.0

    def is_working_day(self, d):
        return d.weekday() < 5


class _Data:
    def __init__(self):
        self.calendars = {'C': _Cal()}
        self.project = {'data_date': datetime(2026, 1, 1)}
        self.activities = {
            's': {'id': 'STEEL', 'name': 'Structural Steel Erection', 'total_float_days': -18,
                  'planned_duration': 200, 'calendar_id': 'C', 'task_type': 'Task'},
            'c': {'id': 'CIVIL', 'name': 'Civil Works to Silo 3', 'total_float_days': -12,
                  'planned_duration': 120, 'calendar_id': 'C', 'task_type': 'Task'},
            'e': {'id': 'MEP', 'name': 'MEP First Fix', 'total_float_days': -9,
                  'planned_duration': 80, 'calendar_id': 'C', 'task_type': 'Task'},
            'k': {'id': 'SLACK', 'name': 'Landscaping', 'total_float_days': 20,
                  'planned_duration': 40, 'calendar_id': 'C', 'task_type': 'Task'},
            'm': {'id': 'FIN', 'name': 'Completion', 'total_float_days': -18, 'planned_duration': 0,
                  'calendar_id': 'C', 'task_type': 'FinishMilestone', 'planned_finish': datetime(2027, 11, 14)},
        }
        self.relationships = []


def test_critical_drivers_names_the_worst_first_and_flags_driving():
    d = critical_drivers(_Data())
    assert [x['name'] for x in d] == ['Structural Steel Erection', 'Civil Works to Silo 3', 'MEP First Fix']
    assert d[0]['late'] == 18 and d[0].get('driving') is True
    assert all(x['name'] != 'Landscaping' for x in d)      # positive float excluded
    assert all(x['name'] != 'Completion' for x in d)       # milestone excluded


def test_recovery_estimate_picks_top_driver_and_pulls_finish_in():
    r = recovery_estimate(_Data())
    assert r['activity'] == 'Structural Steel Erection'    # most-negative float
    assert r['recovered'] == 10                            # 25 wd remaining * 0.40
    assert r['new_finish'] is not None and r['new_finish'] < datetime(2027, 11, 14)


def test_recovery_none_when_nothing_is_critical():
    data = _Data()
    for a in data.activities.values():
        if a['task_type'] != 'FinishMilestone':
            a['total_float_days'] = 15                      # all positive float
    assert recovery_estimate(data) is None


def test_minus_working_days_skips_weekends():
    # Monday 05-Jan-2026 back 1 working day -> Friday 02-Jan-2026
    assert _minus_working_days(_Cal(), datetime(2026, 1, 5), 1).date() == datetime(2026, 1, 2).date()
