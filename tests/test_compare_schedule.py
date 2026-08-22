"""In-tool forward-pass scheduler — the but-for finish (no F9). Small hand-computable
schedules (calendar-less → calendar days, 8h/day) so the finish dates are exact."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_compare.schedule import project_finish, but_for_finish


def _sched(rels):
    d = ScheduleData()
    d.project = {'data_date': datetime(2026, 1, 1)}
    d.calendars = {}
    d.activities = {
        '1': {'id': 'A050', 'name': 'Clear', 'task_type': 'Task', 'calendar_id': None, 'remaining_duration': 40},  # 5d
        '2': {'id': 'A100', 'name': 'Dig', 'task_type': 'Task', 'calendar_id': None, 'remaining_duration': 80},    # 10d
    }
    d.relationships = rels
    return d


def _fs(lag_days=0.0, lag_hours=0.0):
    return [{'pred_id': '1', 'succ_id': '2', 'type': 'FS', 'lag_days': lag_days, 'lag_hours': lag_hours}]


def test_forward_pass_chain_finish():
    # A050: Jan1 + 5d = Jan6; A100: Jan6 + 10d = Jan16
    assert project_finish(_sched(_fs())) == datetime(2026, 1, 16)


def test_forward_pass_respects_lag():
    # FS+10: A100 start pushed to Jan16, + 10d = Jan26
    assert project_finish(_sched(_fs(10.0, 80.0))) == datetime(2026, 1, 26)


def test_but_for_reverts_lag_and_pulls_finish_in():
    upd = _sched(_fs(10.0, 80.0))
    assert project_finish(upd) == datetime(2026, 1, 26)                          # reported
    ops = [{'kind': 'set_rel', 'pred_code': 'A050', 'succ_code': 'A100', 'type': 'FS', 'lag_hours': 0.0}]
    assert but_for_finish(upd, ops) == datetime(2026, 1, 16)                     # but-for: 10 days earlier


def test_but_for_removes_added_link():
    upd = _sched(_fs(10.0, 80.0))
    ops = [{'kind': 'remove_rel', 'pred_code': 'A050', 'succ_code': 'A100'}]
    # link gone → A100 starts at the data date: max(A050 Jan6, A100 Jan1+10=Jan11) = Jan11
    assert but_for_finish(upd, ops) == datetime(2026, 1, 11)


def test_completed_activity_uses_actuals():
    d = _sched([])
    d.activities['1']['actual_start'] = datetime(2025, 12, 1)
    d.activities['1']['actual_finish'] = datetime(2025, 12, 20)
    # A100 not started, no preds → Jan1 + 10d = Jan11; A050 completed Dec20 → finish Jan11
    assert project_finish(d) == datetime(2026, 1, 11)
