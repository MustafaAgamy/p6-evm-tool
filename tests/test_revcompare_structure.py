"""Slice-2 WBS / calendar / constraint diffs (p6_revcompare.structure)."""
from datetime import datetime, date

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


def test_calendar_date_exceptions_flip():
    """A specific date that flips working status between revisions is reported (comment: e.g.
    07 Jan 2026 non-working in Rev.00 → working in Rev.01)."""
    c0 = Calendar(object_id='c1', name='6 Day', nonworking_days={'Friday'},
                  holidays={date(2026, 1, 7)}, added_work_days=set(), day_hours=8.0,
                  work_intervals={}, exception_intervals={})
    c1 = Calendar(object_id='c1', name='6 Day', nonworking_days={'Friday'},
                  holidays={date(2026, 9, 23)}, added_work_days=set(), day_hours=8.0,
                  work_intervals={}, exception_intervals={})
    rev0 = _sched([_act('A1', 'x', calid='c1')], cals=[c0])
    rev1 = _sched([_act('A1', 'x', calid='c1')], cals=[c1])
    d = diff_calendars(rev0, rev1, MatchedSchedules(rev0, rev1))
    pat = next(p for p in d['patterns'] if p['name'] == '6 Day')
    ex = {e['date']: e for e in pat['date_exceptions']}
    assert ex['07 Jan 2026']['change'] == 'now working'
    # rev0/rev1 now report status-or-hours: a full working day reads its hours ('8h/day').
    assert ex['07 Jan 2026']['rev0'] == 'Non-working' and ex['07 Jan 2026']['rev1'] == '8h/day'
    assert ex['23 Sep 2026']['change'] == 'now non-working'
    assert ex['23 Sep 2026']['rev0'] == '8h/day' and ex['23 Sep 2026']['rev1'] == 'Non-working'


def test_calendar_lists_shared_nonworking_dates():
    """The comparison lists EVERY non-working date of both revisions (not only the flips), so a
    shared holiday appears as 'unchanged' and the per-revision counts are reported (comment 3)."""
    shared = date(2026, 12, 25)
    c0 = Calendar(object_id='c1', name='6 Day', nonworking_days={'Friday'},
                  holidays={date(2026, 1, 7), shared}, added_work_days=set(), day_hours=8.0,
                  work_intervals={}, exception_intervals={})
    c1 = Calendar(object_id='c1', name='6 Day', nonworking_days={'Friday'},
                  holidays={shared}, added_work_days=set(), day_hours=8.0,
                  work_intervals={}, exception_intervals={})
    rev0 = _sched([_act('A1', 'x', calid='c1')], cals=[c0])
    rev1 = _sched([_act('A1', 'x', calid='c1')], cals=[c1])
    pat = next(p for p in diff_calendars(rev0, rev1, MatchedSchedules(rev0, rev1))['patterns'] if p['name'] == '6 Day')
    ex = {e['date']: e for e in pat['date_exceptions']}
    assert ex['07 Jan 2026']['change'] == 'now working'          # removed holiday → now working
    assert ex['25 Dec 2026']['change'] == 'unchanged'            # shared holiday still listed
    assert pat['nonworking_count'] == {'rev0': 2, 'rev1': 1}


def test_added_calendar_lists_its_own_nonworking_dates():
    """Round-16: a newly ADDED calendar has no prior revision to diff against, so its own dated
    non-working days are listed in full via `nonworking_dates` (holidays → 'Non-working', a
    reduced-hours exception → 'Nh/day')."""
    c_new = Calendar(object_id='cNEW', name='Marine Works', nonworking_days=set(),
                     holidays={date(2026, 1, 1), date(2026, 4, 25)}, added_work_days=set(),
                     day_hours=10.0, work_intervals={}, exception_intervals={})
    rev0 = _sched([_act('A1', 'x', calid='c6')], cals=[_cal('c6', 'Base', {'Friday'})])
    rev1 = _sched([_act('A2', 'y', calid='cNEW')], cals=[c_new])
    pat = next(p for p in diff_calendars(rev0, rev1, MatchedSchedules(rev0, rev1))['patterns']
               if p['name'] == 'Marine Works')
    assert pat['change'] == 'added'
    nd = {d['date']: d['status'] for d in pat['nonworking_dates']}
    assert nd == {'01 Jan 2026': 'Non-working', '25 Apr 2026': 'Non-working'}


def test_inboth_calendar_has_no_nonworking_dates_list():
    """A calendar present in BOTH revisions relies on date_exceptions for its differences, so the
    added/removed-only `nonworking_dates` list stays empty (no full dump for an in-both calendar)."""
    c = _cal('c1', '6 Day', {'Friday'})
    rev0 = _sched([_act('A1', 'x', calid='c1')], cals=[c])
    rev1 = _sched([_act('A1', 'x', calid='c1')], cals=[_cal('c1', '6 Day', {'Friday'})])
    pat = next(p for p in diff_calendars(rev0, rev1, MatchedSchedules(rev0, rev1))['patterns'] if p['name'] == '6 Day')
    assert pat['nonworking_dates'] == []


def test_reduced_hours_flagged_against_standard_day():
    """Round-17 #02 / round-20 #1: on a 24h/day calendar, a day that works only 8h is a REDUCED day
    and must be labelled '8h/day (reduced from 24h)' — while on an 8h/day calendar an 8h day is just
    '8h/day'."""
    from p6_evm.calendars import Calendar
    from datetime import date as _d
    d1 = _d(2026, 3, 23)
    # rev0: 24h calendar, 23 Mar non-working (holiday). rev1: 24h calendar, 23 Mar works 8h (reduced).
    c0 = Calendar(object_id='c1', name='24h', nonworking_days=set(), holidays={d1}, added_work_days=set(),
                  day_hours=24.0, work_intervals={}, exception_intervals={})
    c1 = Calendar(object_id='c1', name='24h', nonworking_days=set(), holidays=set(), added_work_days=set(),
                  day_hours=24.0, work_intervals={}, exception_intervals={d1: [(8 * 60, 16 * 60)]})
    rev0 = _sched([_act('A1', 'x', calid='c1')], cals=[c0])
    rev1 = _sched([_act('A1', 'x', calid='c1')], cals=[c1])
    pat = next(p for p in diff_calendars(rev0, rev1, MatchedSchedules(rev0, rev1))['patterns'] if p['name'] == '24h')
    e = {x['date']: x for x in pat['date_exceptions']}['23 Mar 2026']
    assert e['rev0'] == 'Non-working' and e['rev1'] == '8h/day (reduced from 24h)' and e['change'] == 'now working'


def test_calendar_comparison_limited_to_data_date_completion_window():
    """Round-19 #02 — the calendar comparison covers only data date → project completion; a
    historical exception before the data date and one past completion are dropped."""
    from p6_evm.calendars import Calendar
    old, infront, after = date(2010, 1, 1), date(2026, 3, 10), date(2030, 1, 1)
    c0 = Calendar(object_id='c1', name='6 Day', nonworking_days={'Friday'},
                  holidays={old, infront, after}, added_work_days=set(), day_hours=8.0,
                  work_intervals={}, exception_intervals={})
    c1 = Calendar(object_id='c1', name='6 Day', nonworking_days={'Friday'},
                  holidays={old, after}, added_work_days=set(), day_hours=8.0,
                  work_intervals={}, exception_intervals={})   # infront now working
    rev0 = _sched([_act('A1', 'x', calid='c1')], cals=[c0])
    rev1 = _sched([_act('A1', 'x', calid='c1')], cals=[c1])
    rev0.data_date = datetime(2026, 1, 1)
    rev1.data_date = datetime(2026, 1, 1)
    rev0.activities['o0']['planned_finish'] = datetime(2027, 1, 1)
    rev1.activities['o0']['planned_finish'] = datetime(2027, 1, 1)
    pat = next(p for p in diff_calendars(rev0, rev1, MatchedSchedules(rev0, rev1))['patterns'] if p['name'] == '6 Day')
    isos = {e['iso'] for e in pat['date_exceptions']}
    assert '2026-03-10' in isos          # in-window change kept
    assert '2010-01-01' not in isos      # historical (pre data date) dropped
    assert '2030-01-01' not in isos      # past completion dropped


def test_calendar_same_name_compared_from_xer_clndr_blobs():
    """End-to-end for XER: two SAME-NAMED calendars parsed from real clndr_data blobs with
    different holiday dates are still compared by their non-working days (the name being unchanged
    must not skip the comparison)."""
    from p6_evm.clndr import parse_clndr_data, _EPOCH

    def ser(y, m, d):
        return (date(y, m, d) - _EPOCH).days
    days = "(0||DaysOfWeek()(0||1())" + "".join(f"(0||{n}()(0||0(s|08:00|f|16:00)()))" for n in range(2, 8)) + ")"
    blob0 = "(0||CalendarData()" + days + f"(0||Exceptions()(0||0(d|{ser(2026,1,7)}))(0||1(d|{ser(2026,12,25)})))" + ")"
    blob1 = "(0||CalendarData()" + days + f"(0||Exceptions()(0||0(d|{ser(2026,12,25)}))(0||1(d|{ser(2026,9,23)})))" + ")"
    cd0, cd1 = parse_clndr_data(blob0), parse_clndr_data(blob1)
    c0 = Calendar(object_id='c1', name='6 Day Workweek', day_hours=8.0, **cd0)
    c1 = Calendar(object_id='c1', name='6 Day Workweek', day_hours=8.0, **cd1)   # SAME name in both revisions
    rev0 = _sched([_act('A1', 'x', calid='c1')], cals=[c0])
    rev1 = _sched([_act('A1', 'x', calid='c1')], cals=[c1])
    pat = next(p for p in diff_calendars(rev0, rev1, MatchedSchedules(rev0, rev1))['patterns']
               if p['name'] == '6 Day Workweek')
    ex = {e['date']: e for e in pat['date_exceptions']}
    assert ex['07 Jan 2026']['change'] == 'now working'          # holiday removed → now a working day
    assert ex['23 Sep 2026']['change'] == 'now non-working'      # holiday added
    assert ex['25 Dec 2026']['change'] == 'unchanged'            # shared holiday still listed
    assert pat['nonworking_count'] == {'rev0': 2, 'rev1': 2}


def test_calendar_rename_still_compares_nonworking_dates():
    """A calendar renamed between revisions (its activities reassigned to the new name) is paired
    as a rename — its non-working dates are still compared, not lost as removed+added."""
    c_old = Calendar(object_id='cOLD', name='Standard', nonworking_days={'Friday'},
                     holidays={date(2026, 1, 7)}, added_work_days=set(), day_hours=8.0,
                     work_intervals={}, exception_intervals={})
    c_new = Calendar(object_id='cNEW', name='Site Standard', nonworking_days={'Friday'},
                     holidays=set(), added_work_days=set(), day_hours=8.0,
                     work_intervals={}, exception_intervals={})
    rev0 = _sched([_act('A1', 'x', calid='cOLD')], cals=[c_old])
    rev1 = _sched([_act('A1', 'x', calid='cNEW')], cals=[c_new])
    d = diff_calendars(rev0, rev1, MatchedSchedules(rev0, rev1))
    pats = [p for p in d['patterns'] if p.get('renamed_to') == 'Site Standard']
    assert len(pats) == 1 and pats[0]['name'] == 'Standard' and pats[0]['change'] == 'renamed'
    ex = {e['date']: e for e in pats[0]['date_exceptions']}
    assert ex['07 Jan 2026']['change'] == 'now working'      # date change survives the rename
    # the rename is not also double-reported as a mass activity reassignment
    assert all(not (r['from'] == 'Standard' and r['to'] == 'Site Standard') for r in d['reassignments'])


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
