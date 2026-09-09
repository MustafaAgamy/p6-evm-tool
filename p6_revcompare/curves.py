"""Time-phased planned spread across two baseline revisions (``report['curves']``).

Baselines carry no progress, so everything here is **planned value** — the budget
cost and the resource units (man-hours) each revision *plans* to place in each
calendar month, never an earned/actual figure. Each activity's budget
(``bac_by_activity``, keyed by ObjectId) and resource units
(``assignments_by_activity``) are spread linearly across its ``planned_start`` ..
``planned_finish`` span, bucketed by calendar month, proportioned by the working
days that fall in each month (calendar days when the activity carries no calendar).

The whole module is **conditional on the data being present**: with no cost it
reports ``cost_available == False`` and empty value curves; with no resource
assignments it reports ``resource_available == False`` and empty manpower curves.
Nothing here throws on missing/partial data — a guarded, again-safe structure is
always returned.

Pure functions over parsed ScheduleData + the matcher outputs; unit-tested.

Public API:
    build_curves(rev0, rev1, matched, match, cal, orig_finish)
"""
from datetime import date, datetime, timedelta

_MS = ('StartMilestone', 'FinishMilestone')
_WBS_DIM = 'WBS'   # synthetic dimension: budget rolled up by the top WBS branch


# ── month helpers ────────────────────────────────────────────────────────────

def _mkey(d):
    """(year, month) key for a datetime/date, or None."""
    if isinstance(d, (datetime, date)):
        return (d.year, d.month)
    return None


def _mlabel(key):
    """(year, month) -> 'Mar 2025'."""
    return date(key[0], key[1], 1).strftime('%b %Y')


def _month_end(y, m):
    nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return nxt - timedelta(days=1)


def _next_month(key):
    y, m = key
    return (y + 1, 1) if m == 12 else (y, m + 1)


def _contiguous_axis(keys):
    """Contiguous list of (year, month) keys from the earliest to the latest present."""
    keys = [k for k in keys if k]
    if not keys:
        return []
    lo, hi = min(keys), max(keys)
    out, cur = [], lo
    # guard against a runaway range (bad dates) — a schedule spanning >100 years is not real.
    for _ in range(1200):
        out.append(cur)
        if cur >= hi:
            break
        cur = _next_month(cur)
    return out


# ── linear spread of one value across a span, by calendar month ───────────────

def _days_per_month(calobj, s, f):
    """{(year, month): working-day count} across the inclusive span s..f.

    Uses the activity's calendar to count working days; falls back to calendar days
    when there's no calendar. When a span has zero working days (e.g. sits entirely
    on non-working days) it falls back to a single calendar day at the start so the
    value is never silently dropped."""
    per = {}
    if calobj is not None:
        # working-day count, day by day (span is bounded by the activity duration)
        d, guard = s, 0
        while d <= f and guard < 40000:
            guard += 1
            if calobj.is_working_day(d):
                k = (d.year, d.month)
                per[k] = per.get(k, 0) + 1
            d += timedelta(days=1)
        if per:
            return per
        # no working day fell in the span — fall through to calendar days
    # calendar-day count, computed per month arithmetically (fast for long spans)
    y, m = s.year, s.month
    for _ in range(1200):
        ms = date(y, m, 1)
        me = _month_end(y, m)
        lo = max(s, ms)
        hi = min(f, me)
        n = (hi - lo).days + 1
        if n > 0:
            per[(y, m)] = per.get((y, m), 0) + n
        if (y, m) >= (f.year, f.month):
            break
        y, m = _next_month((y, m))
    return per


def _spread(calobj, start, finish, value):
    """{(year, month): portion of ``value``} spread linearly across start..finish."""
    if value in (None, 0) or not isinstance(start, (datetime, date)) or not isinstance(finish, (datetime, date)):
        return {}
    s = start.date() if isinstance(start, datetime) else start
    f = finish.date() if isinstance(finish, datetime) else finish
    if f < s:
        f = s
    per = _days_per_month(calobj, s, f)
    total = sum(per.values())
    if total <= 0:
        return {}
    return {k: value * (n / total) for k, n in per.items()}


# ── per-activity budget / units ───────────────────────────────────────────────

def _actcal(data, act):
    cals = getattr(data, 'calendars', None) or {}
    return cals.get(act.get('calendar_id'))


def _act_units(data, oid):
    """Total budgeted resource units (man-hours) assigned to an activity."""
    amap = getattr(data, 'assignments_by_activity', None) or {}
    tot = 0.0
    for a in amap.get(oid, []) or []:
        tot += a.get('budget_units') or 0.0
    return tot


def _total_bac(data):
    bac = getattr(data, 'bac_by_activity', None) or {}
    return sum(v or 0.0 for v in bac.values())


def _total_units(data):
    """Total budgeted resource units (man-hours) across the schedule — the real signal that
    resource/manpower data is present (a cost-only assignment carries no units)."""
    amap = getattr(data, 'assignments_by_activity', None) or {}
    return sum((a.get('budget_units') or 0.0) for lst in amap.values() for a in (lst or []))


def _span_days(calobj, s, f, after=None):
    """(total_days, days_after) across the inclusive span s..f — working days via the
    activity's calendar, calendar days as a fallback. ``days_after`` counts only days
    strictly after ``after`` (a date), for the finish-date exposure."""
    total = aft = 0
    if calobj is not None:
        d, guard = s, 0
        while d <= f and guard < 40000:
            guard += 1
            if calobj.is_working_day(d):
                total += 1
                if after is not None and d > after:
                    aft += 1
            d += timedelta(days=1)
        if total:
            return total, aft
    total = (f - s).days + 1
    if after is not None and f > after:
        lo = max(s, after + timedelta(days=1))
        aft = max(0, (f - lo).days + 1)
    return total, aft


def _value_after(data, orig_finish):
    """Rev.01 planned budget value falling strictly after the original governing finish DATE
    (day granularity — not the whole finish month), for the extended-works exposure callout."""
    if not isinstance(orig_finish, (datetime, date)):
        return 0.0
    of = orig_finish.date() if isinstance(orig_finish, datetime) else orig_finish
    bac = getattr(data, 'bac_by_activity', None) or {}
    total = 0.0
    for oid, v in bac.items():
        if not v:
            continue
        act = (getattr(data, 'activities', None) or {}).get(oid)
        if not act:
            continue
        s, f = act.get('planned_start'), act.get('planned_finish')
        if not isinstance(s, (datetime, date)) or not isinstance(f, (datetime, date)):
            continue
        s = s.date() if isinstance(s, datetime) else s
        f = f.date() if isinstance(f, datetime) else f
        if f < s:
            f = s
        tot, aft = _span_days(_actcal(data, act), s, f, after=of)
        if tot > 0 and aft > 0:
            total += v * (aft / tot)
    return total


def _has_assignments(data):
    amap = getattr(data, 'assignments_by_activity', None) or {}
    return any(v for v in amap.values())


def _top_branch(path):
    if not path:
        return '(no WBS)'
    return path.split(' > ', 1)[0].strip() or '(no WBS)'


# ── the module entry point ─────────────────────────────────────────────────────

def build_curves(rev0, rev1, matched, match, cal, orig_finish):
    """Time-phased planned-value and manpower curves for the two revisions.

    Parameters
    ----------
    rev0, rev1 : ScheduleData   the original and (canonicalised) revised schedules
    matched    : MatchedSchedules   (accepted for a stable signature; not required here)
    match      : dict from ``match_activities`` (accepted for signature; not required here)
    cal        : reference Calendar (fallback only; per-activity calendars are used first)
    orig_finish: datetime — Rev.00 governing finish, for ``value_after_orig_finish``

    Returns a fully-guarded, JSON-serialisable ``report['curves']`` dict.
    """
    cost_available = bool(_total_bac(rev0) or _total_bac(rev1))
    # resource data means MAN-HOURS (units), not merely an assignment row: a cost-only
    # assignment (budget_cost but no units) must not light up an all-zero manpower histogram.
    resource_available = bool(_total_units(rev0) or _total_units(rev1))

    # ── per-month planned budget cost (spread each activity's bac) ──────────────
    val0 = _phase_budget(rev0) if cost_available else {}
    val1 = _phase_budget(rev1) if cost_available else {}

    # ── per-month planned man-hours (spread each activity's assigned units) ─────
    mp0 = _phase_units(rev0) if resource_available else {}
    mp1 = _phase_units(rev1) if resource_available else {}

    axis = _contiguous_axis(set(val0) | set(val1) | set(mp0) | set(mp1))
    months = [_mlabel(k) for k in axis]

    # value curves
    value_monthly, value_cumulative = [], []
    if cost_available:
        c0 = c1 = 0.0
        for k in axis:
            v0, v1 = val0.get(k, 0.0), val1.get(k, 0.0)
            value_monthly.append({'month': _mlabel(k), 'rev0': round(v0), 'rev1': round(v1),
                                  'var': round(v1 - v0)})
            c0 += v0
            c1 += v1
            value_cumulative.append({'month': _mlabel(k), 'rev0': round(c0), 'rev1': round(c1),
                                     'var': round(c1 - c0)})

    # rev1 planned value falling strictly after the original governing finish DATE
    # (day granularity — counting the after-finish portion of the finish month too).
    value_after_orig_finish = round(_value_after(rev1, orig_finish)) if cost_available else 0.0

    # manpower curves
    manpower_monthly = []
    peak = {'rev0': 0.0, 'rev1': 0.0, 'rev0_month': None, 'rev1_month': None}
    if resource_available:
        best0 = best1 = -1.0
        for k in axis:
            u0, u1 = round(mp0.get(k, 0.0), 1), round(mp1.get(k, 0.0), 1)
            manpower_monthly.append({'month': _mlabel(k), 'rev0': u0, 'rev1': u1})
            if u0 > best0:
                best0, peak['rev0'], peak['rev0_month'] = u0, u0, _mlabel(k)
            if u1 > best1:
                best1, peak['rev1'], peak['rev1_month'] = u1, u1, _mlabel(k)
        if best0 < 0:
            peak['rev0'] = 0.0
        if best1 < 0:
            peak['rev1'] = 0.0

    return {
        'cost_available': cost_available,
        'resource_available': resource_available,
        'months': months,
        'value_monthly': value_monthly,
        'value_cumulative': value_cumulative,
        'value_after_orig_finish': value_after_orig_finish,
        'budget_by_dim': _budget_by_dim(rev0, rev1) if cost_available else {},
        'manpower_monthly': manpower_monthly,
        'peak': peak,
        'manhours_by_trade': _manhours_by_trade(rev0, rev1) if resource_available else [],
        'manhours_total': _manhours_total(rev0, rev1),
    }


# ── phasing over all activities ─────────────────────────────────────────────────

def _phase_budget(data):
    """{(year, month): planned budget cost} across the whole revision."""
    bac = getattr(data, 'bac_by_activity', None) or {}
    out = {}
    for oid, act in (getattr(data, 'activities', None) or {}).items():
        v = bac.get(oid) or 0.0
        if not v:
            continue
        for k, part in _spread(_actcal(data, act), act.get('planned_start'),
                               act.get('planned_finish'), v).items():
            out[k] = out.get(k, 0.0) + part
    return out


def _phase_units(data):
    """{(year, month): planned resource units (man-hours)} across the whole revision."""
    out = {}
    for oid, act in (getattr(data, 'activities', None) or {}).items():
        u = _act_units(data, oid)
        if not u:
            continue
        for k, part in _spread(_actcal(data, act), act.get('planned_start'),
                               act.get('planned_finish'), u).items():
            out[k] = out.get(k, 0.0) + part
    return out


# ── budget rolled up by activity-code dimension (+ WBS top branch) ──────────────

def _budget_by_dim(rev0, rev1):
    dims = []
    for d in (list(getattr(rev0, 'activity_code_types', None) or [])
              + list(getattr(rev1, 'activity_code_types', None) or [])):
        if d and d not in dims:
            dims.append(d)

    out = {}
    for dim in dims:
        out[dim] = _rollup(rev0, rev1, lambda a: (a.get('activity_codes') or {}).get(dim) or '(unassigned)')
    # always offer a WBS top-branch rollup
    out[_WBS_DIM] = _rollup(rev0, rev1, lambda a: _top_branch(a.get('wbs_path')))
    return out


def _rollup(rev0, rev1, category_of):
    def totals(data):
        bac = getattr(data, 'bac_by_activity', None) or {}
        agg = {}
        for oid, act in (getattr(data, 'activities', None) or {}).items():
            v = bac.get(oid) or 0.0
            if not v:
                continue
            cat = category_of(act) or '(unassigned)'
            agg[cat] = agg.get(cat, 0.0) + v
        return agg
    t0, t1 = totals(rev0), totals(rev1)
    rows = []
    for cat in sorted(set(t0) | set(t1)):
        v0, v1 = t0.get(cat, 0.0), t1.get(cat, 0.0)
        rows.append({'category': cat, 'rev0': round(v0), 'rev1': round(v1), 'var': round(v1 - v0)})
    rows.sort(key=lambda r: -max(r['rev0'], r['rev1']))
    return rows


# ── man-hour totals per resource (trade) ────────────────────────────────────────

def _units_by_resource(data):
    """{resource key -> {'name', 'units'}} summed across every activity in the revision."""
    amap = getattr(data, 'assignments_by_activity', None) or {}
    out = {}
    for assigns in amap.values():
        for a in assigns or []:
            key = a.get('resource_id') or a.get('resource_name')
            if not key:
                continue
            slot = out.setdefault(key, {'name': a.get('resource_name') or a.get('resource_id') or key,
                                        'units': 0.0})
            slot['units'] += a.get('budget_units') or 0.0
            if not slot['name']:
                slot['name'] = a.get('resource_name') or key
    return out


def _manhours_by_trade(rev0, rev1):
    r0, r1 = _units_by_resource(rev0), _units_by_resource(rev1)
    rows = []
    for key in sorted(set(r0) | set(r1)):
        s0, s1 = r0.get(key), r1.get(key)
        u0 = round(s0['units'], 1) if s0 else 0.0
        u1 = round(s1['units'], 1) if s1 else 0.0
        if u0 and not u1:
            kind = 'removed'
        elif u1 and not u0:
            kind = 'added'
        else:
            kind = 'changed'
        name = (s1 or s0)['name']
        rows.append({'resource_id': str(key), 'name': name, 'rev0': u0, 'rev1': u1,
                     'var': round(u1 - u0, 1), 'kind': kind})
    rows.sort(key=lambda r: -max(r['rev0'], r['rev1']))
    return rows


def _manhours_total(rev0, rev1):
    t0 = sum(s['units'] for s in _units_by_resource(rev0).values())
    t1 = sum(s['units'] for s in _units_by_resource(rev1).values())
    var = t1 - t0
    pct = round(var / t0 * 100, 1) if t0 else None
    return {'rev0': round(t0, 1), 'rev1': round(t1, 1), 'var': round(var, 1), 'pct': pct}
