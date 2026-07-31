from p6_evm.parser import ScheduleData, full_wbs_path
from p6_evm.calendars import Calendar


def test_scheduledata_has_relationships_list():
    data = ScheduleData()
    assert data.relationships == []


def test_calendar_has_default_day_hours():
    cal = Calendar(object_id='1', name='5-day')
    assert cal.day_hours == 8.0


def test_full_wbs_path_root_first():
    wbs_map = {
        'r': {'name': 'Tower 33', 'parent_object_id': None},
        'f': {'name': 'Foundation', 'parent_object_id': 'r'},
        'a': {'name': 'Raft', 'parent_object_id': 'f'},
    }
    assert full_wbs_path('a', wbs_map) == 'Tower 33 > Foundation > Raft'


def test_full_wbs_path_unknown_is_empty():
    assert full_wbs_path('nope', {}) == ''
