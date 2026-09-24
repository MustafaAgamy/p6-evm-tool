"""New narrative sections: the generic Activity-ID decoder and key-dates picker."""
from types import SimpleNamespace

from p6_narrative.builder import _id_anatomy, _key_dates, _MILESTONE_TYPES


def _data(activities):
    return SimpleNamespace(activities=activities)


def test_id_anatomy_splits_a_delimited_id_generically():
    a = _id_anatomy(_data({'1': {'id': 'CONS.PL.S1.1000'}}))
    assert a['id'] == 'CONS.PL.S1.1000'
    assert [s['value'] for s in a['segments']] == ['CONS', 'PL', 'S1', '1000']
    assert a['segments'][-1]['label'] == 'Serial'          # last part labelled Serial
    assert a['segments'][0]['label'] == 'Module'


def test_id_anatomy_handles_dash_and_underscore_and_picks_richest():
    a = _id_anatomy(_data({'1': {'id': 'A-1'}, '2': {'id': 'SD_SUB_PL_S1_101'}}))
    assert a['id'] == 'SD_SUB_PL_S1_101'                    # the most-delimited one


def test_id_anatomy_none_when_no_delimiter():
    assert _id_anatomy(_data({'1': {'id': 'A1000'}})) is None


def test_key_dates_picks_milestones_and_sorts():
    ms = next(iter(_MILESTONE_TYPES))
    acts = {
        '1': {'name': 'Finish', 'task_type': ms, 'planned_finish': '2027-02-09'},
        '2': {'name': 'Start', 'task_type': ms, 'planned_finish': '2024-10-24'},
        '3': {'name': 'Normal task', 'task_type': 'Task', 'planned_finish': '2025-01-01'},
    }
    items = _key_dates(_data(acts))
    assert [i['label'] for i in items] == ['Start', 'Finish']   # milestones only, date-sorted
