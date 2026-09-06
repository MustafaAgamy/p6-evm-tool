"""Slice-2 structure diffs — WBS, calendars and constraints — across two revisions.

All three read fields the parser already exposes (no parser changes):
  * WBS         : ``data.wbs`` (ObjectId -> {name, parent_object_id}) + each activity's
                  ``wbs_path``. Matched by full path since ObjectIds are per-file.
  * Calendars   : the ``Calendar`` objects in ``data.calendars`` + each activity's
                  ``calendar_id``. Matched by name.
  * Constraints : each activity's primary ``constraint_type`` / ``constraint_date``.

Pure functions over parsed ScheduleData / a MatchedSchedules; unit-tested.
"""
from datetime import datetime

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
    nw = getattr(cal, 'nonworking_days', None)
    if nw is None:
        return None
    return 7 - len(nw)


def _cal_by_name(data):
    out = {}
    for cal in (getattr(data, 'calendars', None) or {}).values():
        if getattr(cal, 'name', None):
            out[cal.name] = cal
    return out


def diff_calendars(rev0, rev1, matched):
    """Calendar-level changes (added/removed/workweek/day-hours/holidays) matched by name,
    plus per-activity calendar reassignments grouped by (from -> to) with the working-day
    /week change — the "88 activities moved 6-day → 7-day" signal.

    Returns {'calendars':[{name,change,detail}], 'reassignments':[{from,to,from_wd,to_wd,count,codes}]}.
    """
    c0, c1 = _cal_by_name(rev0), _cal_by_name(rev1)
    cals = []
    for name in sorted(set(c0) | set(c1)):
        a, b = c0.get(name), c1.get(name)
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

    # Per-activity reassignment (matched activities whose calendar name changed).
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
    reassignments = []
    for (n0, n1), codes in groups.items():
        reassignments.append({
            'from': n0, 'to': n1,
            'from_wd': _workdays_per_week(c0.get(n0)) if c0.get(n0) else None,
            'to_wd': _workdays_per_week(c1.get(n1)) if c1.get(n1) else None,
            'count': len(codes), 'codes': sorted(codes),
        })
    reassignments.sort(key=lambda r: -r['count'])
    return {'calendars': cals, 'reassignments': reassignments}


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
