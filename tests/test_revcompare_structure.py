"""Slice-2 WBS / calendar / constraint diffs (p6_revcompare.structure)."""
from datetime import datetime

from p6_evm.parser import ScheduleData
from p6_evm.calendars import Calendar
from p6_compare.model import MatchedSchedules
from p6_revcompare.structure import diff_wbs, diff_calendars, diff_constraints


def _cal(oid, name, nonworking, dh=8.0, hol=0):
    return Calendar(object_id=oid, name=name, nonworking_days=set(nonworking), day_hours=dh,
                    holidays=set(range(hol)))


def _act(code, name, wbs='WBS 1 > Sub', calid='c6', cons=None, consd=None, tt='Task', tf=0):
    return {'id': code, 'name': name, 'wbs_path': wbs, 'wbs_id': 'w', 'calendar_id': calid,
            'constraint_type': cons, 'constraint_date': consd, 'task_type': tt, 'total_float_days': tf}


def _sched(acts, wbs=None, cals=None):
    d = ScheduleData()
    d.activities = {f'o{i}': a for i, a in enumerate(acts)}
    d.relationships = []
    d.wbs = wbs or {}
    d.calendars = {c.object_id: c for c in (cals or [])}
    return d


# ── WBS ──────────────────────────────────────────────────────────────────────

def test_wbs_added_and_removed():
    rev0 = _sched([_act('A1', 'x', wbs='WBS 1 > Sub')],
                  {'w0': {'name': 'WBS 1', 'parent_object_id': None}, 'w1': {'name': 'Sub', 'parent_object_id': 'w0'}})
    rev1 = _sched([_act('A1', 'x', wbs='WBS 1 > Sub'), _act('A2', 'y', wbs='WBS 1 > External')],
                  {'w0': {'name': 'WBS 1', 'parent_object_id': None}, 'w1': {'name': 'Sub', 'parent_object_id': 'w0'},
                   'w2': {'name': 'External', 'parent_object_id': 'w0'}})
    d = diff_wbs(rev0, rev1)
    assert [x['path'] for x in d['added']] == ['WBS 1 > External']
    assert d['removed'] == []


def test_wbs_rename_not_reported_as_add_remove():
    # Same parent, same members, different leaf name → rename.
    rev0 = _sched([_act('A1', 'x', wbs='WBS 1 > Substructure'), _act('A2', 'y', wbs='WBS 1 > Substructure')],
                  {'w0': {'name': 'WBS 1', 'parent_object_id': None}, 'w1': {'name': 'Substructure', 'parent_object_id': 'w0'}})
    rev1 = _sched([_act('A1', 'x', wbs='WBS 1 > Foundations'), _act('A2', 'y', wbs='WBS 1 > Foundations')],
                  {'w0': {'name': 'WBS 1', 'parent_object_id': None}, 'w1': {'name': 'Foundations', 'parent_object_id': 'w0'}})
    d = diff_wbs(rev0, rev1)
    assert len(d['renamed']) == 1
    assert d['renamed'][0]['from'] == 'WBS 1 > Substructure'
    assert d['renamed'][0]['to'] == 'WBS 1 > Foundations'
    assert d['added'] == [] and d['removed'] == []


# ── Calendars ────────────────────────────────────────────────────────────────

def test_calendar_reassignment_workweek_change():
    cals = [_cal('c6', '6-Day', {'Sunday'}), _cal('c7', '7-Day', set())]
    rev0 = _sched([_act('A1', 'x', calid='c6'), _act('A2', 'y', calid='c6')], cals=cals)
    rev1 = _sched([_act('A1', 'x', calid='c7'), _act('A2', 'y', calid='c7')], cals=cals)
    d = diff_calendars(rev0, rev1, MatchedSchedules(rev0, rev1))
    assert len(d['reassignments']) == 1
    g = d['reassignments'][0]
    assert (g['from'], g['to'], g['from_wd'], g['to_wd'], g['count']) == ('6-Day', '7-Day', 6, 7, 2)


def test_calendar_level_added_and_modified():
    rev0 = _sched([_act('A1', 'x', calid='c6')], cals=[_cal('c6', '6-Day', {'Sunday'})])
    rev1 = _sched([_act('A1', 'x', calid='c6')],
                  cals=[_cal('c6', '6-Day', {'Sunday'}, hol=3), _cal('cX', 'Shutdown', set())])
    d = diff_calendars(rev0, rev1, MatchedSchedules(rev0, rev1))
    names = {c['name']: c['change'] for c in d['calendars']}
    assert names.get('Shutdown') == 'added'
    assert names.get('6-Day') == 'modified'


def test_milestone_calendar_not_counted():
    cals = [_cal('c6', '6-Day', {'Sunday'}), _cal('c7', '7-Day', set())]
    rev0 = _sched([_act('M', 'PC', calid='c6', tt='FinishMilestone')], cals=cals)
    rev1 = _sched([_act('M', 'PC', calid='c7', tt='FinishMilestone')], cals=cals)
    d = diff_calendars(rev0, rev1, MatchedSchedules(rev0, rev1))
    assert d['reassignments'] == []


# ── Constraints ──────────────────────────────────────────────────────────────

def test_constraint_added_type_and_date():
    rev0 = _sched([_act('A1', 'x'), _act('A2', 'y', cons='StartOn', consd=datetime(2025, 5, 1)),
                   _act('A3', 'z', cons='StartOn', consd=datetime(2025, 6, 1))])
    rev1 = _sched([_act('A1', 'x', cons='MustFinishOn', consd=datetime(2025, 9, 1)),
                   _act('A2', 'y', cons='FinishOn', consd=datetime(2025, 5, 1)),
                   _act('A3', 'z', cons='StartOn', consd=datetime(2025, 7, 1))])
    rows = {r['activity_id']: r for r in diff_constraints(MatchedSchedules(rev0, rev1))}
    assert rows['A1']['kind'] == 'added' and rows['A1']['hard'] is True
    assert rows['A2']['kind'] == 'type'
    assert rows['A3']['kind'] == 'date'


def test_no_constraint_change_omitted():
    rev0 = _sched([_act('A1', 'x', cons='StartOn', consd=datetime(2025, 5, 1))])
    rev1 = _sched([_act('A1', 'x', cons='StartOn', consd=datetime(2025, 5, 1))])
    assert diff_constraints(MatchedSchedules(rev0, rev1)) == []
