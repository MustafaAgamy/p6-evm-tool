"""Baseline Revision Comparison — date-shift & duration modules (``dates.py``).

Two pure builders over the ``match`` dict (from :func:`p6_revcompare.matching.match_activities`)
and the two parsed revisions:

    build_date_shifts(match, rev0, rev1, cal)   -> report['date_shifts']
    build_duration_table(match, rev0, rev1, cal) -> report['duration_table']

``date_shifts`` reports the working-day movement of every matched pair's planned dates
(finish shift, falling back to start when a finish is absent), sorted so the biggest
movers lead, then lists the new (added) and removed activities. ``duration_table`` reports
each activity's planned duration before/after with its calendar on each revision, flagging
the case where a duration was cut at the same time its calendar changed (a planning caveat,
not a judgement).

Neutral evidence only — nothing here is a verdict. Every path is guarded: a missing
revision, calendar or date degrades to ``'—'`` / ``None`` rather than raising.
"""
from datetime import datetime

# Reuse the engine's own formatters/counters so output matches the rest of the report
# exactly. These are deferred-safe: dates.py is imported inside build_report_from_data,
# by which point compare.py is fully initialised (compare.py does not import dates at
# module load), so there is no import cycle.
from p6_revcompare.compare import _short, _d0, _dur_days, _wd_between


# ── calendar helpers ─────────────────────────────────────────────────────────

def _cal_for(data, act):
    cals = getattr(data, 'calendars', None) or {}
    return cals.get((act or {}).get('calendar_id'))


def _workdays_per_week(cal):
    nw = getattr(cal, 'nonworking_days', None)
    if nw is None:
        return None
    return 7 - len(nw)


def _cal_label(data, act):
    """The activity's calendar as ``'Name · N-day'``, ``'Name'`` (day-count unknown),
    or ``'—'`` when the calendar can't be resolved."""
    cal = _cal_for(data, act)
    name = getattr(cal, 'name', None) if cal else None
    if not name:
        return '—'
    wd = _workdays_per_week(cal)
    return f"{name} · {wd}-day" if wd is not None else name


def _shift_wd(cal, d0, d1):
    """Signed working-day shift from ``d0`` to ``d1`` (positive = later); ``None`` when
    either date is missing. Falls back to calendar days when there is no calendar."""
    if not (isinstance(d0, datetime) and isinstance(d1, datetime)):
        return None
    try:
        v = _wd_between(cal, _d0(d0), _d0(d1))
    except Exception:
        v = (_d0(d1) - _d0(d0)).days
    return int(v) if v is not None else None


def _tf_after(act):
    tf = (act or {}).get('total_float_days')
    return round(tf, 1) if tf is not None else None


# ── date shifts ──────────────────────────────────────────────────────────────

def build_date_shifts(match, rev0, rev1, cal, top=None):
    """Working-day movement of each matched pair's planned start/finish.

    Returns a flat list of ``{id, name, wbs, start0, start1, finish0, finish1, shift_wd}``.
    Matched movers (non-zero ``shift_wd``) come first, sorted by ``|shift_wd|`` descending
    (so the head is the "top movers"); ``top`` optionally caps that head. Added activities
    follow with the Rev.00 side blank (``start0``/``finish0`` = ``None``) and ``shift_wd``
    = ``None``; removed activities with the Rev.01 side blank. ``id`` is the canonical
    (Rev.00) code for matched pairs, matching the register.
    """
    match = match or {}
    movers = []
    for p in (match.get('pairs') or []):
        a0, a1 = p.get('act0') or {}, p.get('act1') or {}
        s0, s1 = a0.get('planned_start'), a1.get('planned_start')
        f0, f1 = a0.get('planned_finish'), a1.get('planned_finish')
        fin_shift = _shift_wd(cal, f0, f1)
        start_shift = _shift_wd(cal, s0, s1)
        shift = fin_shift if fin_shift is not None else start_shift
        if not shift:                          # 0 or None on both dates → unchanged
            continue
        movers.append({
            'id': p.get('canonical') or a1.get('id') or a0.get('id'),
            'name': a1.get('name') or a0.get('name') or p.get('canonical'),
            'wbs': a1.get('wbs_path') or a0.get('wbs_path') or '—',
            'start0': _short(s0), 'start1': _short(s1),
            'finish0': _short(f0), 'finish1': _short(f1),
            'shift_wd': shift,
        })
    movers.sort(key=lambda r: -abs(r['shift_wd']))
    if top:
        movers = movers[:top]

    rows = list(movers)
    for a in (match.get('added') or []):
        rows.append({
            'id': a.get('id'), 'name': a.get('name') or a.get('id'),
            'wbs': a.get('wbs_path') or '—',
            'start0': None, 'start1': _short(a.get('planned_start')),
            'finish0': None, 'finish1': _short(a.get('planned_finish')),
            'shift_wd': None,
        })
    for a in (match.get('removed') or []):
        rows.append({
            'id': a.get('id'), 'name': a.get('name') or a.get('id'),
            'wbs': a.get('wbs_path') or '—',
            'start0': _short(a.get('planned_start')), 'start1': None,
            'finish0': _short(a.get('planned_finish')), 'finish1': None,
            'shift_wd': None,
        })
    return rows


# ── duration table ───────────────────────────────────────────────────────────

def build_duration_table(match, rev0, rev1, cal, min_change=0.5):
    """Planned-duration change per activity with its calendar context.

    Returns a flat list of ``{id, name, wbs, before, after, variance, calendar_before,
    calendar_after, tf_after, calendar_flag}``. Durations are working days via
    :func:`_dur_days`. Matched activities whose duration moved by at least ``min_change``
    days are listed first, sorted by ``|variance|`` descending; then added activities
    (``before='—'``, ``variance=None``) and removed activities (``after='—'``).

    ``calendar_flag`` is ``True`` when a duration was cut (``variance < 0``) at the same
    time the activity's calendar changed — surfacing that the "shorter" duration may be a
    calendar reassignment rather than a genuine reduction in work. It stays ``False`` when
    either calendar can't be resolved (no false positive on unknown data).
    """
    match = match or {}
    rows = []
    for p in (match.get('pairs') or []):
        a0, a1 = p.get('act0') or {}, p.get('act1') or {}
        before = _dur_days(rev0, a0)
        after = _dur_days(rev1, a1)
        variance = round(after - before, 1)
        if abs(variance) < min_change:
            continue
        cal_b = _cal_label(rev0, a0)
        cal_a = _cal_label(rev1, a1)
        cal_changed = (cal_b != cal_a) and cal_b != '—' and cal_a != '—'
        rows.append({
            'id': p.get('canonical') or a1.get('id') or a0.get('id'),
            'name': a1.get('name') or a0.get('name') or p.get('canonical'),
            'wbs': a1.get('wbs_path') or a0.get('wbs_path') or '—',
            'before': before, 'after': after, 'variance': variance,
            'calendar_before': cal_b, 'calendar_after': cal_a,
            'tf_after': _tf_after(a1),
            'calendar_flag': bool(variance < 0 and cal_changed),
        })
    rows.sort(key=lambda r: -abs(r['variance']))

    for a in (match.get('added') or []):
        rows.append({
            'id': a.get('id'), 'name': a.get('name') or a.get('id'),
            'wbs': a.get('wbs_path') or '—',
            'before': '—', 'after': _dur_days(rev1, a), 'variance': None,
            'calendar_before': '—', 'calendar_after': _cal_label(rev1, a),
            'tf_after': _tf_after(a), 'calendar_flag': False,
        })
    for a in (match.get('removed') or []):
        rows.append({
            'id': a.get('id'), 'name': a.get('name') or a.get('id'),
            'wbs': a.get('wbs_path') or '—',
            'before': _dur_days(rev0, a), 'after': '—', 'variance': None,
            'calendar_before': _cal_label(rev0, a), 'calendar_after': '—',
            'tf_after': None, 'calendar_flag': False,
        })
    return rows
