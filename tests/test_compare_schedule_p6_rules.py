"""The but-for scheduler (p6_compare.schedule) schedules like Primavera P6 — comment 44.

With no change applied it must reproduce P6's own schedule.  On MAFI it forecast 20 Dec 2026
where P6 has 19 Oct 2026 (and 7 months late on Alstom): it counted whole days, lags on the
wrong calendar, let Level of Effort activities drive their successors and ignored P6's
'start-to-start lag from early start' option.  Each P6 rule, on a hand-checkable schedule
(08:00-16:00, Friday off, 8 h/day — like the MAFI calendars):
"""
from datetime import datetime

from p6_evm.calendars import Calendar
from p6_evm.parser import ScheduleData
from p6_compare.schedule import forward_pass

DD = datetime(2026, 3, 1, 16, 0)            # a Sunday, end of the working day


def _cal(oid='C', days=('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Saturday')):
    return Calendar(object_id=oid, name=oid, nonworking_days={d for d in
                    ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday') if d not in days},
                    day_hours=8.0, work_intervals={d: [(480, 960)] for d in days})


def _act(oid, rem, tt='Task', **kw):
    a = {'id': oid, 'name': oid, 'task_type': tt, 'calendar_id': 'C', 'remaining_duration': rem}
    a.update(kw)
    return a


def _data(acts, rels, cals=None, **proj):
    d = ScheduleData()
    d.project = dict({'data_date': DD, 'lag_calendar': 'predecessor'}, **proj)
    d.calendars = cals or {'C': _cal()}
    d.activities = {a['id']: a for a in acts}
    d.relationships = [dict({'lag_hours': 0.0, 'lag_calendar_id': None}, pred_id=p, succ_id=s, type=t, **kw)
                       for p, s, t, kw in rels]
    return d


def test_remaining_work_starts_at_the_next_working_moment_and_counts_hours():
    ef = forward_pass(_data([_act('A', 26.4)], []))
    # 2 Mar 08:00 + 26.4 h (8 h/day): 2nd, 3rd, 4th full = 24 h, then 2.4 h on Thu 5th
    assert ef['A'] == datetime(2026, 3, 5, 10, 24)


def test_a_finish_ending_at_the_close_of_day_stays_there_and_its_successor_starts_next_morning():
    ef = forward_pass(_data([_act('A', 8), _act('B', 8)], [('A', 'B', 'FS', {})]))
    assert ef['A'] == datetime(2026, 3, 2, 16, 0) and ef['B'] == datetime(2026, 3, 3, 16, 0)


def test_the_lag_runs_on_the_lag_calendar_of_the_relationship():
    seven = _cal('S', ('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'))
    acts = [_act('A', 8, calendar_id='S'), _act('B', 8)]
    ef = forward_pass(_data(acts, [('A', 'B', 'FS', {'lag_hours': 40.0, 'lag_calendar_id': 'S'})],
                            cals={'C': _cal(), 'S': seven}))
    # A ends Mon 2 Mar 16:00; +5 days on the 7-day lag calendar = Sat 7 Mar 16:00; B = Sun 8 Mar
    assert ef['B'] == datetime(2026, 3, 8, 16, 0)


def test_a_level_of_effort_never_drives_its_successor():
    acts = [_act('L', 400, 'LOE'), _act('B', 8)]
    assert forward_pass(_data(acts, [('L', 'B', 'FF', {})]))['B'] == datetime(2026, 3, 2, 16, 0)


def test_start_to_start_from_a_started_predecessor_runs_from_its_remaining_early_start():
    acts = [_act('A', 16, actual_start=datetime(2026, 2, 1, 8)), _act('B', 8)]
    ef = forward_pass(_data(acts, [('A', 'B', 'SS', {'lag_hours': 8.0, 'lag_calendar_id': 'C'})]))
    # A's remaining work starts 2 Mar 08:00 → B after 8 h of lag: 3 Mar 08:00 → finish 3 Mar 16:00
    assert ef['B'] == datetime(2026, 3, 3, 16, 0)
    ef = forward_pass(_data(acts, [('A', 'B', 'SS', {'lag_hours': 8.0, 'lag_calendar_id': 'C'})],
                            ss_lag_from_early_start=False))
    assert ef['B'] == datetime(2026, 3, 2, 16, 0)       # from the actual start (long past)


def test_a_started_successor_has_met_its_start_link_to_a_started_predecessor():
    acts = [_act('A', 40, actual_start=datetime(2026, 2, 1, 8)),
            _act('B', 8, actual_start=datetime(2026, 2, 2, 8))]
    assert forward_pass(_data(acts, [('A', 'B', 'SS', {'lag_hours': 24.0})]))['B'] == datetime(2026, 3, 2, 16, 0)


def test_finish_to_finish_holds_the_start_back_and_a_finish_milestone_keeps_the_finish_time():
    acts = [_act('A', 24), _act('B', 8), _act('M', 0, 'FinishMilestone')]
    ef = forward_pass(_data(acts, [('A', 'B', 'FF', {}), ('B', 'M', 'FS', {})]))
    assert ef['B'] == datetime(2026, 3, 4, 16, 0) and ef['M'] == datetime(2026, 3, 4, 16, 0)


def test_a_start_constraint_and_whole_minutes():
    acts = [_act('A', 10.0 / 60.0, constraint_type='Start On or After', constraint_date=datetime(2026, 3, 10, 8))]
    assert forward_pass(_data(acts, []))['A'] == datetime(2026, 3, 10, 8, 10)
