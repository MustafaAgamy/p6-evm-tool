"""Unit tests for p6_revcompare.dates — date_shifts & duration_table builders."""
from p6_evm.calendars import Calendar
from p6_revcompare.matching import match_activities
from p6_revcompare import dates
from tests.test_revcompare_engine import _act, _sched, _pair, D


# ── helpers ──────────────────────────────────────────────────────────────────

def _cal(name, nonworking, hours=8.0):
    return Calendar(object_id=name, name=name, nonworking_days=set(nonworking), day_hours=hours)


def _mk(code, name, dur, cal_id, tf=None, wbs='WBS 2 Slab'):
    a = _act(code, name, dur=dur, tf=tf, wbs=wbs)
    a['calendar_id'] = cal_id
    return a


FIVE = _cal('FIVE', {'Saturday', 'Sunday'})      # 5-day week
SIX = _cal('SIX', {'Sunday'})                    # 6-day week


def _dur_pair():
    """Two revisions built purely to exercise durations & calendar reassignment."""
    cals = {c.object_id: c for c in (FIVE, SIX)}
    rev0 = _sched([
        _mk('B1', 'Pour Slab', 80, 'FIVE'),           # 10 d
        _mk('B2', 'Cure', 40, 'FIVE'),                # 5 d — unchanged
        _mk('B3', 'Strip Forms', 80, 'FIVE', wbs='WBS 3 Fitout'),   # removed
        _mk('B5', 'Test Systems', 80, 'FIVE'),        # 10 d
    ], [], D(2025, 3, 1))
    rev0.calendars = dict(cals)
    rev1 = _sched([
        _mk('B1', 'Pour Slab', 48, 'SIX', tf=2),      # 6 d, calendar changed FIVE→SIX
        _mk('B2', 'Cure', 40, 'FIVE'),                # 5 d — unchanged
        _mk('B4', 'Backfill Excavation', 64, 'SIX', wbs='WBS 4 External'),  # added, 8 d
        _mk('B5', 'Test Systems', 40, 'FIVE'),        # 5 d, same calendar
    ], [], D(2025, 3, 1))
    rev1.calendars = dict(cals)
    return rev0, rev1


# ── date_shifts ──────────────────────────────────────────────────────────────

def test_date_shifts_sorted_by_abs_shift_desc():
    rev0, rev1 = _pair()
    m = match_activities(rev0, rev1)
    rows = dates.build_date_shifts(m, rev0, rev1, cal=None)
    movers = [r for r in rows if r['shift_wd'] is not None]
    assert movers, 'expected date movers'
    absshifts = [abs(r['shift_wd']) for r in movers]
    assert absshifts == sorted(absshifts, reverse=True)
    # Practical Completion is the biggest mover (12/19/2026 → 02/04/2027 = +47 cal days)
    assert movers[0]['name'] == 'Practical Completion'
    assert movers[0]['shift_wd'] == 47


def test_date_shifts_id_is_canonical_and_zero_shift_dropped():
    rev0, rev1 = _pair()
    m = match_activities(rev0, rev1)
    rows = dates.build_date_shifts(m, rev0, rev1, cal=None)
    ids = {r['id'] for r in rows if r['shift_wd'] is not None}
    assert 'A1220' in ids          # id-changed pair keyed to canonical (Rev.00 code)
    assert 'A1000' not in ids      # unchanged dates → 0 shift → dropped
    # short date format on a mover
    a1300 = next(r for r in rows if r['id'] == 'A1300')
    assert a1300['finish0'] == '20 May 2025' and a1300['finish1'] == '01 May 2025'
    assert a1300['shift_wd'] == -19


def test_date_shifts_new_and_removed_have_blank_side():
    rev0, rev1 = _pair()
    m = match_activities(rev0, rev1)
    rows = dates.build_date_shifts(m, rev0, rev1, cal=None)
    added = next(r for r in rows if r['id'] == 'A4400')
    assert added['start0'] is None and added['finish0'] is None
    assert added['start1'] is not None and added['shift_wd'] is None
    removed = next(r for r in rows if r['id'] == 'A1980')
    assert removed['start1'] is None and removed['finish1'] is None
    assert removed['finish0'] is not None and removed['shift_wd'] is None


def test_date_shifts_top_caps_movers_only():
    rev0, rev1 = _pair()
    m = match_activities(rev0, rev1)
    rows = dates.build_date_shifts(m, rev0, rev1, cal=None, top=1)
    movers = [r for r in rows if r['shift_wd'] is not None]
    assert len(movers) == 1 and movers[0]['name'] == 'Practical Completion'
    # added/removed still appended after the capped head
    assert any(r['id'] == 'A4400' for r in rows)
    assert any(r['id'] == 'A1980' for r in rows)


# ── duration_table ───────────────────────────────────────────────────────────

def test_duration_table_flags_calendar_coincident_cut():
    rev0, rev1 = _dur_pair()
    m = match_activities(rev0, rev1)
    rows = dates.build_duration_table(m, rev0, rev1, cal=None)
    by = {r['id']: r for r in rows}
    assert by['B1']['before'] == 10.0 and by['B1']['after'] == 6.0
    assert by['B1']['variance'] == -4.0
    assert by['B1']['calendar_before'] == 'FIVE · 5-day'
    assert by['B1']['calendar_after'] == 'SIX · 6-day'
    assert by['B1']['calendar_flag'] is True
    assert by['B1']['tf_after'] == 2.0


def test_duration_cut_without_calendar_change_not_flagged():
    rev0, rev1 = _dur_pair()
    m = match_activities(rev0, rev1)
    by = {r['id']: r for r in dates.build_duration_table(m, rev0, rev1, cal=None)}
    assert by['B5']['variance'] == -5.0
    assert by['B5']['calendar_before'] == 'FIVE · 5-day'
    assert by['B5']['calendar_after'] == 'FIVE · 5-day'
    assert by['B5']['calendar_flag'] is False


def test_duration_table_unchanged_dropped_and_sorted():
    rev0, rev1 = _dur_pair()
    m = match_activities(rev0, rev1)
    rows = dates.build_duration_table(m, rev0, rev1, cal=None)
    matched = [r for r in rows if r['variance'] is not None]
    assert 'B2' not in {r['id'] for r in matched}          # unchanged duration dropped
    assert [r['id'] for r in matched] == ['B5', 'B1']       # |−5| before |−4|


def test_duration_table_added_and_removed():
    rev0, rev1 = _dur_pair()
    m = match_activities(rev0, rev1)
    by = {r['id']: r for r in dates.build_duration_table(m, rev0, rev1, cal=None)}
    assert by['B4']['before'] == '—' and by['B4']['after'] == 8.0
    assert by['B4']['variance'] is None
    assert by['B4']['calendar_before'] == '—' and by['B4']['calendar_after'] == 'SIX · 6-day'
    assert by['B4']['calendar_flag'] is False
    assert by['B3']['after'] == '—' and by['B3']['before'] == 10.0
    assert by['B3']['variance'] is None and by['B3']['tf_after'] is None


# ── guards / degenerate inputs ────────────────────────────────────────────────

def test_guards_empty_and_none_inputs():
    assert dates.build_date_shifts(None, None, None, None) == []
    assert dates.build_duration_table(None, None, None, None) == []
    assert dates.build_date_shifts({}, None, None, None) == []
    assert dates.build_duration_table({}, None, None, None) == []


def test_identical_revisions_yield_empty_tables():
    rev0, _ = _pair()
    m = match_activities(rev0, rev0)
    assert dates.build_date_shifts(m, rev0, rev0, cal=None) == []
    assert dates.build_duration_table(m, rev0, rev0, cal=None) == []
