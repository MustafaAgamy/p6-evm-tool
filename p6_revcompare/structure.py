"""Slice-2 structure diffs — WBS, calendars and constraints — across two revisions.

All three read fields the parser already exposes (no parser changes):
  * WBS         : ``data.wbs`` (ObjectId -> {name, parent_object_id}) + each activity's
                  ``wbs_path``. Matched by full path since ObjectIds are per-file.
  * Calendars   : the ``Calendar`` objects in ``data.calendars`` + each activity's
                  ``calendar_id``. Matched by name.
  * Constraints : each activity's primary ``constraint_type`` / ``constraint_date``.

Pure functions over parsed ScheduleData / a MatchedSchedules; unit-tested.
"""
from datetime import datetime, date

from p6_evm.parser import full_wbs_path

_MS = ('StartMilestone', 'FinishMilestone')
# P6 hard-constraint types that pin a date (worth a closer look than a soft "start on/after").
_HARD_CONSTRAINTS = ('MustFinishOn', 'MustStartOn', 'MandatoryStart', 'MandatoryFinish',
                     'StartOn', 'FinishOn')


# ── WBS structure ────────────────────────────────────────────────────────────

def _wbs_paths(data):
    """{full path -> ObjectId} for every WBS node that resolves to a non-empty path."""
    out = {}
    for oid in (getattr(data, 'wbs', None) or {}):
        p = full_wbs_path(oid, data.wbs)
        if p:
            out[p] = oid
    return out


def _members_by_path(data):
    """full WBS path -> set of activity codes sitting on that node (exact node, not descendants)."""
    out = {}
    for a in data.activities.values():
        p = a.get('wbs_path')
        code = a.get('id')
        if p and code:
            out.setdefault(p, set()).add(code)
    return out


def diff_wbs(rev0, rev1, moved_pairs=()):
    """Added / removed / renamed WBS branches, plus the count of activities moved between
    WBS. Rename = a removed path and an added path under the same parent whose member
    activities substantially overlap (so a simple rename isn't reported as add+remove).

    Returns {'added':[{path}], 'removed':[{path}], 'renamed':[{from,to}], 'moved_activities':int}.
    """
    p0, p1 = _wbs_paths(rev0), _wbs_paths(rev1)
    m0, m1 = _members_by_path(rev0), _members_by_path(rev1)
    added = sorted(set(p1) - set(p0))
    removed = sorted(set(p0) - set(p1))

    def parent(path):
        return path.rsplit(' > ', 1)[0] if ' > ' in path else ''

    renamed, used_add = [], set()
    for r in list(removed):
        rp, rm = parent(r), m0.get(r, set())
        best, best_ov = None, 0.0
        for a in added:
            if a in used_add or parent(a) != rp:
                continue
            am = m1.get(a, set())
            if not (rm or am):
                continue
            union = rm | am
            ov = len(rm & am) / len(union) if union else 0.0
            if ov > best_ov:
                best, best_ov = a, ov
        if best and best_ov >= 0.5:
            renamed.append({'from': r, 'to': best})
            used_add.add(best)

    ren_from = {x['from'] for x in renamed}
    ren_to = {x['to'] for x in renamed}
    return {
        'added': [{'path': p} for p in added if p not in ren_to],
        'removed': [{'path': p} for p in removed if p not in ren_from],
        'renamed': renamed,
        'moved_activities': len(moved_pairs),
    }


# ── Calendars ────────────────────────────────────────────────────────────────

def _workdays_per_week(cal):
    """Working days per week — robust for 24h / continuous calendars. Prefer the actual
    working-interval days (a 7×24 calendar has intervals on all 7 days); fall back to
    7 − non-working. A 0 from an all-non-working set is almost always a continuous calendar
    defined via intervals/exceptions, so treat it as 7 rather than the illogical 0."""
    if cal is None:
        return None
    wi = getattr(cal, 'work_intervals', None) or {}
    if wi:
        n = sum(1 for ivs in wi.values() if ivs)
        if n:
            return n
    nw = getattr(cal, 'nonworking_days', None)
    if nw is None:
        return None
    d = 7 - len(nw)
    return d if d > 0 else 7


def _cal_pattern(cal):
    """A plain working pattern for display: {days, hours, hpw} (days/week, hours/day,
    hours/week). None when the calendar is absent."""
    if cal is None:
        return None
    days = _workdays_per_week(cal)
    hours = getattr(cal, 'day_hours', None)
    hpw = round(days * hours) if (days is not None and hours is not None) else None
    return {'days': days, 'hours': hours, 'hpw': hpw}


_DOW = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
_DOW_ABBR = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _dow_grid(cal):
    """Mon→Sun working/non-working grid for a calendar: [{day, working}] × 7 (None if absent).
    A day is working when it carries work intervals, else when it's not in nonworking_days."""
    if cal is None:
        return None
    wi = getattr(cal, 'work_intervals', None) or {}
    nw = getattr(cal, 'nonworking_days', None)
    grid = []
    for full, ab in zip(_DOW, _DOW_ABBR):
        if wi:
            working = bool(wi.get(full))
        elif nw is not None:
            working = full not in nw
        else:
            working = None
        grid.append({'day': ab, 'working': working})
    return grid


def _dow_working(cal, dow_full):
    """Is `dow_full` (e.g. 'Monday') a working day in the calendar's weekly pattern?"""
    wi = getattr(cal, 'work_intervals', None) or {}
    if wi:
        return bool(wi.get(dow_full))
    nw = getattr(cal, 'nonworking_days', None)
    if nw is not None:
        return dow_full not in nw
    return True


def _interval_hours(ivs):
    """Total working hours from a list of (start_min, end_min) intervals."""
    return round(sum((em - sm) for sm, em in (ivs or []) if em is not None and sm is not None) / 60.0, 2)


def _date_hours(cal, d):
    """Effective working HOURS on a specific calendar DATE: an explicit exception's intervals win,
    then a holiday (0), else the weekly day-of-week hours. This catches reduced-hours exception
    days (e.g. a day dropped from 8h to 6h), not only full working/non-working flips."""
    exc = getattr(cal, 'exception_intervals', None) or {}
    if d in exc:
        return _interval_hours(exc[d])
    if d in (getattr(cal, 'added_work_days', None) or set()):
        return getattr(cal, 'day_hours', None) or 0.0     # working exception, intervals not captured
    if d in (getattr(cal, 'holidays', None) or set()):
        return 0.0
    dow = _DOW[d.weekday()]
    if _dow_working(cal, dow):
        wi = (getattr(cal, 'work_intervals', None) or {}).get(dow)
        return _interval_hours(wi) if wi else (getattr(cal, 'day_hours', None) or 0.0)
    return 0.0


def _date_working(cal, d):
    """Whether a specific date has any working time (compat helper)."""
    return _date_hours(cal, d) > 0


def _hlabel(h, std=None):
    """Status/hours label for a date in one revision: 'Non-working', 'Nh/day', or — when the day
    works FEWER hours than the calendar's standard day (e.g. 8h on a 24h calendar) — 'Nh/day
    (reduced)' so a reduced-hours period is visible against that revision's normal day (round-17 #02)."""
    if not h:
        return 'Non-working'
    if std and h < std - 1e-6:
        # round-20 #1 — name the standard day so "reduced" is unambiguous ("8h/day (reduced from 24h)").
        return f'{h:g}h/day (reduced from {std:g}h)'
    return f'{h:g}h/day'


def _in_window(d, win):
    """Round-19 #02 — keep only calendar dates within the comparison window [data date, project
    completion]; historical exceptions (before the data date) and dates past completion are dropped.
    Coerces datetime→date so a datetime exception compares cleanly against date bounds."""
    if not win:
        return True
    lo, hi = win
    dd = d.date() if isinstance(d, datetime) else d
    if lo is not None and dd < lo:
        return False
    if hi is not None and dd > hi:
        return False
    return True


def _date_exceptions(a, b, win=None):
    """Compare the specific calendar exception DATES of two revisions of one calendar: every date
    that is non-working in either revision OR whose working HOURS differ (e.g. a day reduced from
    8h to 6h, or restored 6h → 8h). Consecutive dates with the same before/after are grouped into a
    range (e.g. 01 Mar 2026 – 07 Mar 2026). Returns [{date, iso, rev0, rev1, change}] with changed
    entries first, then chronological. rev0/rev1 read 'Non-working' or 'Nh/day'; change reads
    'now working' / 'now non-working' / 'Ah → Bh' / 'unchanged'. ``win`` = (start, end) dates limits
    the comparison to the data-date→completion window (round-19 #02)."""
    if a is None or b is None:
        return []

    def _is_date(x):
        return hasattr(x, 'weekday') and hasattr(x, 'strftime') and hasattr(x, 'toordinal')
    dates = set()
    for cal in (a, b):
        for attr in ('holidays', 'added_work_days'):
            dates |= {d for d in (getattr(cal, attr, None) or set()) if _is_date(d)}
        dates |= {d for d in (getattr(cal, 'exception_intervals', None) or {}) if _is_date(d)}
    dates = {d for d in dates if _in_window(d, win)}

    # Per-date effective hours; keep dates that are non-working in one rev OR whose hours differ.
    kept = []
    for d in sorted(dates):
        h0, h1 = _date_hours(a, d), _date_hours(b, d)
        if (h0 == 0 or h1 == 0) or abs(h0 - h1) > 1e-6:
            kept.append((d, h0, h1))

    # Group consecutive calendar days that share the same (h0, h1) into a single range row.
    groups = []
    for d, h0, h1 in kept:
        if groups and groups[-1]['h0'] == h0 and groups[-1]['h1'] == h1 and (d.toordinal() - groups[-1]['end'].toordinal()) == 1:
            groups[-1]['end'] = d
        else:
            groups.append({'start': d, 'end': d, 'h0': h0, 'h1': h1})

    std0 = getattr(a, 'day_hours', None)
    std1 = getattr(b, 'day_hours', None)
    out = []
    for g in groups:
        h0, h1 = g['h0'], g['h1']
        if h0 == 0 and h1 == 0:
            change = 'unchanged'
        elif h0 == 0:
            change = 'now working'
        elif h1 == 0:
            change = 'now non-working'
        else:
            change = f'{h0:g}h → {h1:g}h'
        s, e = g['start'], g['end']
        label = s.strftime('%d %b %Y') if s == e else f"{s.strftime('%d %b %Y')} – {e.strftime('%d %b %Y')}"
        out.append({'date': label, 'iso': s.isoformat(), 'iso_end': e.isoformat(),
                    'rev0': _hlabel(h0, std0), 'rev1': _hlabel(h1, std1), 'change': change})
    out.sort(key=lambda x: (x['change'] == 'unchanged', x['iso']))
    return out


def _nonworking_dates(cal, win=None):
    """The dated non-working / reduced-hours exceptions of a SINGLE calendar — used for a newly
    ADDED (or removed) calendar, which has no other revision to diff against, so its non-working
    days are listed in full. Holidays → 'Non-working'; an exception day whose hours fall below the
    standard working day → 'Nh/day'. Consecutive same-status dates group into one range. The weekly
    days-off are conveyed by the working-pattern rows, not repeated here. ``win`` = (start, end)
    limits it to the data-date→completion window (round-19 #02)."""
    if cal is None:
        return []

    def _is_date(x):
        return hasattr(x, 'weekday') and hasattr(x, 'strftime') and hasattr(x, 'toordinal')
    day_h = getattr(cal, 'day_hours', None) or 0.0
    items = {}
    for d in (getattr(cal, 'holidays', None) or set()):
        if _is_date(d) and _in_window(d, win):
            items[d] = 0.0
    for d, ivs in (getattr(cal, 'exception_intervals', None) or {}).items():
        if not _is_date(d) or not _in_window(d, win):
            continue
        h = _interval_hours(ivs)
        if h == 0 or (day_h and h < day_h - 1e-6):   # non-working or reduced below the standard day
            items[d] = h
    groups = []
    for d, h in sorted(items.items()):
        if groups and abs(groups[-1]['h'] - h) < 1e-6 and (d.toordinal() - groups[-1]['end'].toordinal()) == 1:
            groups[-1]['end'] = d
        else:
            groups.append({'start': d, 'end': d, 'h': h})
    out = []
    for g in groups:
        s, e = g['start'], g['end']
        label = s.strftime('%d %b %Y') if s == e else f"{s.strftime('%d %b %Y')} – {e.strftime('%d %b %Y')}"
        out.append({'date': label, 'iso': s.isoformat(), 'status': _hlabel(g['h'], day_h)})
    return out


def _cal_by_name(data):
    out = {}
    for cal in (getattr(data, 'calendars', None) or {}).values():
        if getattr(cal, 'name', None):
            out[cal.name] = cal
    return out


def _assigned_breakdown(data, cal_name):
    """Which activities use a calendar, broken down by activity code (comment: know which activities
    are assigned to each calendar and at which activity code). Returns {count, ids, by_dim} where
    by_dim maps each activity-code dimension to a count per value (biggest first)."""
    cals = getattr(data, 'calendars', None) or {}
    idname = {cid: getattr(c, 'name', None) for cid, c in cals.items()}
    ids, by_dim = [], {}
    for a in (getattr(data, 'activities', None) or {}).values():
        if idname.get(a.get('calendar_id')) != cal_name:
            continue
        if a.get('id'):
            ids.append(a.get('id'))
        for dim, val in (a.get('activity_codes') or {}).items():
            if val:
                by_dim.setdefault(dim, {})[val] = by_dim.setdefault(dim, {}).get(val, 0) + 1
    by_dim_sorted = {dim: sorted(({'value': v, 'count': c} for v, c in vals.items()),
                                 key=lambda x: -x['count'])
                     for dim, vals in by_dim.items()}
    return {'count': len(ids), 'ids': sorted(ids), 'by_dim': by_dim_sorted}


def _as_date(v):
    """A datetime → its date; a date passes through; None otherwise. (datetime is a subclass of
    date, so the datetime check must come first.)"""
    if v is None:
        return None
    return v.date() if isinstance(v, datetime) else v


def _cal_window(rev0, rev1):
    """Round-19 #02 — the calendar-comparison window: from the DATA DATE to project COMPLETION.
    Start = the earliest data date of the two revisions; when neither carries one (common in XER,
    where last_recalc_date is blank) it falls back to the earliest planned START, which still drops
    the historical pre-project exceptions. End = the latest planned FINISH (completion). Either end
    is None when unavailable, which _in_window treats as unbounded."""
    dds = [_as_date(getattr(r, 'data_date', None)) for r in (rev0, rev1)]
    dds = [d for d in dds if d]
    starts, fins = [], []
    for data in (rev0, rev1):
        for a in (getattr(data, 'activities', None) or {}).values():
            s = _as_date(a.get('planned_start'))
            if s:
                starts.append(s)
            f = _as_date(a.get('planned_finish'))
            if f:
                fins.append(f)
    start = min(dds) if dds else (min(starts) if starts else None)
    end = max(fins) if fins else None
    return (start, end) if (start or end) else None


def diff_calendars(rev0, rev1, matched):
    """Calendar-level changes (added/removed/workweek/day-hours/holidays) matched by name,
    plus per-activity calendar reassignments grouped by (from -> to) with the working-day
    /week change — the "88 activities moved 6-day → 7-day" signal.

    Returns {'calendars':[{name,change,detail}], 'reassignments':[{from,to,from_wd,to_wd,count,codes}]}.
    """
    c0, c1 = _cal_by_name(rev0), _cal_by_name(rev1)

    # Round-19 #02 — the calendar comparison covers only the data-date → project-completion window,
    # so historical exceptions (before the data date) and dates past completion are dropped.
    win = _cal_window(rev0, rev1)

    # Per-calendar activity usage (drives the rename signal + the "activities" count).
    def _usage(data):
        out = {}
        cals = getattr(data, 'calendars', None) or {}
        idname = {cid: getattr(c, 'name', None) for cid, c in cals.items()}
        for a in (getattr(data, 'activities', None) or {}).values():
            n = idname.get(a.get('calendar_id'))
            if n:
                out[n] = out.get(n, 0) + 1
        return out
    u0, u1 = _usage(rev0), _usage(rev1)

    # Per-activity reassignment groups (matched activities whose calendar name changed).
    def cal_name(data, act):
        cal = (getattr(data, 'calendars', None) or {}).get(act.get('calendar_id'))
        return getattr(cal, 'name', None) if cal else None

    groups = {}
    for code in matched.matched_codes:
        a0 = matched.baseline_by_code.get(code) or {}
        a1 = matched.update_by_code.get(code) or {}
        if a1.get('task_type') in _MS:          # a milestone's calendar has no duration effect
            continue
        n0, n1 = cal_name(rev0, a0), cal_name(rev1, a1)
        if n0 and n1 and n0 != n1:
            groups.setdefault((n0, n1), []).append(code)

    # Calendar RENAME detection: a calendar whose name is only in Rev.00 paired with one only in
    # Rev.01 when (nearly) all of the old calendar's activities were reassigned to the new one —
    # i.e. it was renamed, not replaced. Uses the activity-usage signal (NOT holiday overlap, which
    # is exactly what we are comparing), so a renamed calendar's non-working dates are still diffed
    # rather than lost as an unrelated removed+added pair.
    removed_names, added_names = set(c0) - set(c1), set(c1) - set(c0)
    rename_map, used_new = {}, set()
    for n0 in sorted(removed_names):
        best, best_cnt = None, 0
        for (g0, g1), codes in groups.items():
            if g0 == n0 and g1 in added_names and g1 not in used_new and len(codes) > best_cnt:
                best, best_cnt = g1, len(codes)
        if best is not None and best_cnt >= max(1, round((u0.get(n0, 0)) * 0.6)):
            rename_map[n0] = best
            used_new.add(best)
    renamed_to = set(rename_map.values())

    reassignments = []
    for (n0, n1), codes in groups.items():
        if rename_map.get(n0) == n1:          # a rename is not a mass reassignment — don't double-report
            continue
        reassignments.append({
            'from': n0, 'to': n1,
            'from_wd': _workdays_per_week(c0.get(n0)) if c0.get(n0) else None,
            'to_wd': _workdays_per_week(c1.get(n1)) if c1.get(n1) else None,
            'count': len(codes), 'codes': sorted(codes),
        })
    reassignments.sort(key=lambda r: -r['count'])

    # Calendar-level change list (rename collapses removed+added into one entry).
    cals = []
    for name in sorted(set(c0) | set(c1)):
        if name in renamed_to:
            continue
        rn = rename_map.get(name)
        a = c0.get(name)
        b = c1.get(rn) if rn else c1.get(name)
        if rn:
            cals.append({'name': f'{name} → {rn}', 'change': 'renamed', 'detail': f'Calendar renamed ({name} → {rn})'})
            continue
        if a and not b:
            cals.append({'name': name, 'change': 'removed', 'detail': 'Calendar removed'})
            continue
        if b and not a:
            cals.append({'name': name, 'change': 'added', 'detail': 'Calendar added'})
            continue
        det = []
        wa, wb = _workdays_per_week(a), _workdays_per_week(b)
        if wa is not None and wb is not None and wa != wb:
            det.append(f'workweek {wa}-day → {wb}-day')
        if getattr(a, 'day_hours', None) != getattr(b, 'day_hours', None):
            det.append(f'hours/day {getattr(a, "day_hours", "?")} → {getattr(b, "day_hours", "?")}')
        h0, h1 = len(getattr(a, 'holidays', None) or ()), len(getattr(b, 'holidays', None) or ())
        if h0 != h1:
            det.append(f'holidays {h0} → {h1}')
        if det:
            cals.append({'name': name, 'change': 'modified', 'detail': '; '.join(det)})

    # Per-calendar working-pattern + non-working-date comparison view.
    def _nw_count(cal):
        if cal is None:
            return None
        return sum(1 for d in (getattr(cal, 'holidays', None) or set()) if hasattr(d, 'weekday'))

    patterns = []
    for name in sorted(set(c0) | set(c1)):
        if name in renamed_to:               # rendered via its Rev.00-side rename row
            continue
        rn = rename_map.get(name)
        a = c0.get(name)
        b = c1.get(rn) if rn else c1.get(name)
        p0, p1 = _cal_pattern(a), _cal_pattern(b)
        g0, g1 = _dow_grid(a), _dow_grid(b)
        changed = []
        if g0 and g1:
            changed = [g1[i]['day'] for i in range(7) if g0[i]['working'] != g1[i]['working']]
        date_exc = _date_exceptions(a, b, win) if (a and b) else []
        date_flips = [e for e in date_exc if e['change'] != 'unchanged']
        # Count of specific NON-WORKING exception dates (holidays) in each revision.
        nw0, nw1 = _nw_count(a), _nw_count(b)
        change = ('renamed' if rn else 'removed' if (a and not b) else 'added' if (b and not a)
                  else 'modified' if (p0 != p1 or changed or date_flips) else 'unchanged')
        # Which activities use this calendar, by activity code — from the revision where it exists
        # (Rev.01 for renamed/added/modified/unchanged; Rev.00 for a removed calendar).
        if a and not b:
            assigned, assigned_rev = _assigned_breakdown(rev0, name), 'rev0'
        else:
            assigned, assigned_rev = _assigned_breakdown(rev1, rn or name), 'rev1'
        # For an added/removed calendar there is no other revision to diff against, so list its own
        # dated non-working / reduced-hours days in full (round-16 comment: "clarify the non-working
        # days for [a] new calendar added").
        nonworking_dates = (_nonworking_dates(b, win) if (b and not a)
                            else _nonworking_dates(a, win) if (a and not b) else [])
        patterns.append({'name': name, 'renamed_to': rn, 'rev0': p0, 'rev1': p1,
                         'rev0_grid': g0, 'rev1_grid': g1, 'changed_days': changed,
                         'date_exceptions': date_exc,
                         'nonworking_count': {'rev0': nw0, 'rev1': nw1},
                         'nonworking_dates': nonworking_dates,
                         'assigned': assigned, 'assigned_rev': assigned_rev,
                         'activities': (u1.get(rn) if rn else u1.get(name)) or u0.get(name) or 0,
                         'change': change})

    return {'calendars': cals, 'reassignments': reassignments, 'patterns': patterns}


# ── Constraints ──────────────────────────────────────────────────────────────

def _ctype(act):
    t = act.get('constraint_type')
    return t if t else None


def _cdate(act):
    d = act.get('constraint_date')
    return d.date() if isinstance(d, datetime) else d


def diff_constraints(matched):
    """Primary-constraint changes on matched activities: added / removed / type / date.
    Returns [{activity_id, name, kind, rev0, rev1, hard}]."""
    rows = []
    for code in matched.matched_codes:
        a0 = matched.baseline_by_code.get(code) or {}
        a1 = matched.update_by_code.get(code) or {}
        t0, t1 = _ctype(a0), _ctype(a1)
        d0, d1 = _cdate(a0), _cdate(a1)
        kind = None
        if not t0 and t1:
            kind = 'added'
        elif t0 and not t1:
            kind = 'removed'
        elif t0 and t1 and t0 != t1:
            kind = 'type'
        elif t0 and t1 and d0 != d1:
            kind = 'date'
        if not kind:
            continue
        rows.append({
            'activity_id': code, 'name': a1.get('name') or a0.get('name') or code,
            'kind': kind,
            'rev0': _fmt_constraint(t0, d0), 'rev1': _fmt_constraint(t1, d1),
            'hard': (t1 in _HARD_CONSTRAINTS) or (t0 in _HARD_CONSTRAINTS),
            'tf0': a0.get('total_float_days'), 'tf1': a1.get('total_float_days'),
        })
    return rows


def _fmt_constraint(t, d):
    if not t:
        return '—'
    ds = d.strftime('%d %b %Y') if hasattr(d, 'strftime') else ''
    return f'{t}{" " + ds if ds else ""}'
