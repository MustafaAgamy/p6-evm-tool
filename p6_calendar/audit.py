"""Calendar Timeline & Audit — deterministic analysis of the P6 calendars.

`calendar_audit(data, config, settings)` turns a parsed ScheduleData into a
JSON-serialisable report (Sections 1-9 & 11 of the spec). It never touches any
EVM number and never hits the network — the weather layer (Section 10) is a
separate module (p6_calendar.weather).

Key rules (set by Ibrahim):
  * A run of SHUTDOWN_MIN_DAYS+ consecutive non-working exception days = a
    shutdown; shorter runs are holidays. User reasons/labels override, and the
    user may add manual shutdowns (settings) that aren't in the P6 file.
  * The module works over every calendar actually ASSIGNED to a project
    activity; the main view defaults to the project's default calendar.
"""
from datetime import date, datetime, timedelta

from p6_evm.calendars import DOW_NAMES

SHUTDOWN_MIN_DAYS = 5
_MONTH_ABBR = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ── small date helpers ───────────────────────────────────────────────────────

def _to_date(x):
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    try:
        return datetime.fromisoformat(str(x)[:19]).date()
    except ValueError:
        return None


def _iso(d):
    return d.isoformat() if d else None


def _group_runs(dates):
    """Sorted list of date objects -> list of (start, end, length) consecutive runs."""
    runs = []
    for d in sorted(set(dates)):
        if runs and d == runs[-1][1] + timedelta(days=1):
            s, _e, n = runs[-1]
            runs[-1] = (s, d, n + 1)
        else:
            runs.append((d, d, 1))
    return runs


def _fmt_range(s, e):
    if s == e:
        return f'{s.day:02d} {_MONTH_ABBR[s.month]} {s.year}'
    if (s.month, s.year) == (e.month, e.year):
        return f'{s.day:02d}–{e.day:02d} {_MONTH_ABBR[s.month]} {s.year}'
    return f'{s.day:02d} {_MONTH_ABBR[s.month]} {s.year} – {e.day:02d} {_MONTH_ABBR[e.month]} {e.year}'


def _month_iter(start, finish):
    """Yield (year, month) for each month touching [start, finish]."""
    y, m = start.year, start.month
    while (y, m) <= (finish.year, finish.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def _month_last_day(y, m):
    if m == 12:
        return date(y, 12, 31)
    return date(y, m + 1, 1) - timedelta(days=1)


# ── project window + baseline ────────────────────────────────────────────────

def _project_window(data):
    starts = [_to_date(a.get('planned_start')) for a in data.activities.values()]
    finishes = [_to_date(a.get('planned_finish')) for a in data.activities.values()]
    starts = [d for d in starts if d]
    finishes = [d for d in finishes if d]
    start = _to_date(data.project.get('planned_start')) or (min(starts) if starts else None)
    finish = _to_date(data.project.get('scheduled_finish')) or (max(finishes) if finishes else None)
    return start, finish


def _baseline_window(data):
    bs = [_to_date(b.get('planned_start')) for b in data.baseline_by_id.values()]
    bf = [_to_date(b.get('planned_finish')) for b in data.baseline_by_id.values()]
    bs = [d for d in bs if d]
    bf = [d for d in bf if d]
    return (min(bs) if bs else None), (max(bf) if bf else None)


# ── per-calendar exception classification ────────────────────────────────────

def _classify_exceptions(cal, start, finish, reasons, manual):
    """Return {'holidays':[...], 'special':[...], 'shutdowns':[...]} for one calendar
    within [start, finish]. `reasons` maps a block key -> stored reason string.
    `manual` is a list of user-added shutdowns (project-level) already normalised."""
    in_window = [d for d in cal.holidays if start <= d <= finish]
    holidays, shutdowns = [], []
    for s, e, n in _group_runs(in_window):
        key = f'{cal.object_id}:{s.isoformat()}'
        reason = reasons.get(key, '')
        entry = {'start': _iso(s), 'end': _iso(e), 'days': n,
                 'description': _fmt_range(s, e), 'reason': reason, 'source': 'p6',
                 'key': key}
        if n >= SHUTDOWN_MIN_DAYS:
            shutdowns.append(entry)
        else:
            holidays.append(entry)

    # Special / reduced-hours days: exception days that DO carry work time (added_work).
    special = []
    added = [d for d in cal.exception_intervals if start <= d <= finish]
    # group by identical interval signature so a Ramadan block is one row
    added_sorted = sorted(added)
    i = 0
    while i < len(added_sorted):
        d0 = added_sorted[i]
        sig = cal.exception_intervals[d0]
        j = i
        while (j + 1 < len(added_sorted)
               and added_sorted[j + 1] == added_sorted[j] + timedelta(days=1)
               and cal.exception_intervals[added_sorted[j + 1]] == sig):
            j += 1
        s, e = d0, added_sorted[j]
        special_minutes = sum(em - sm for sm, em in sig)
        # Ibrahim's rule (#03): ignore trivial differences from the standard working day.
        # P6 stores work times to the minute, so a sub-5-minute change is rounding noise,
        # not a real "reduced hours" period — don't clutter the report with it.
        if abs(special_minutes - _standard_minutes(cal, d0)) < 5:
            i = j + 1
            continue
        hrs = special_minutes / 60.0
        first = sig[0]
        special.append({'start': _iso(s), 'end': _iso(e), 'days': (e - s).days + 1,
                        'hours': _hhmm(first[0]) + '–' + _hhmm(sig[-1][1]),
                        'hours_per_day': round(hrs, 2),
                        'description': _fmt_range(s, e)})
        i = j + 1

    # Manual shutdowns (project-level) — only for the primary calendar's list
    for ms in manual:
        shutdowns.append(ms)

    return {'holidays': holidays, 'special': special, 'shutdowns': shutdowns,
            'holiday_dates': _holiday_dates(holidays)}


def _holiday_dates(holidays):
    """§3 Calendar Non-working days — expand each holiday RUN into individual dates, each
    carrying its weekday name. Reuses the run's block key + stored reason so the existing
    shutdown_reasons plumbing edits the (editable) description. HOLIDAYS ONLY — shutdowns and
    reduced/special-hours days are deliberately excluded."""
    out = []
    for grp in holidays:
        s, e = _to_date(grp['start']), _to_date(grp['end'])
        d = s
        while d and e and d <= e:
            out.append({'date': _iso(d), 'weekday': DOW_NAMES[d.weekday()],
                        'reason': grp.get('reason', ''), 'key': grp.get('key', '')})
            d += timedelta(days=1)
    return out


def _hhmm(minutes):
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def _standard_minutes(cal, d):
    """The calendar's normal working minutes for the weekday of `d` — the reference a
    reduced/special day is compared against (#03). Falls back to the flat day hours."""
    ivs = cal.work_intervals.get(DOW_NAMES[d.weekday()])
    if ivs:
        return sum(em - sm for sm, em in ivs)
    return int(round(cal.day_hours * 60))


def _exception_date_names(exc):
    """{date: user-typed name} for holidays/shutdowns that carry a stored reason — used
    to print the name inside the timeline day cell and Excel (#05)."""
    names = {}
    for grp in list(exc.get('holidays', [])) + list(exc.get('shutdowns', [])):
        nm = (grp.get('reason') or '').strip()
        if not nm:
            continue
        s, e = _to_date(grp['start']), _to_date(grp['end'])
        d = s
        while d and e and d <= e:
            names[d] = nm
            d += timedelta(days=1)
    return names


def _normalise_manual(manual_raw):
    out = []
    for m in manual_raw or []:
        s = _to_date(m.get('start'))
        e = _to_date(m.get('end')) or s
        if not s:
            continue
        if e < s:
            s, e = e, s
        out.append({'start': _iso(s), 'end': _iso(e), 'days': (e - s).days + 1,
                    'description': _fmt_range(s, e), 'reason': m.get('reason', ''),
                    'source': 'manual', 'key': f'manual:{s.isoformat()}'})
    return out


def _shutdown_dates(exc):
    dates = set()
    for grp in exc['shutdowns']:
        s, e = _to_date(grp['start']), _to_date(grp['end'])
        d = s
        while d <= e:
            dates.add(d)
            d += timedelta(days=1)
    return dates


def _day_status(cal, d, shutdown_dates):
    if d in shutdown_dates:
        return 'shutdown'
    if d in cal.exception_intervals:
        return 'special'
    if d in cal.holidays:
        return 'holiday'
    if not cal.is_working_day(d):
        return 'weekend'
    return 'work'


# ── per-calendar monthly build ───────────────────────────────────────────────

def _months_for_calendar(cal, start, finish, shutdown_dates, date_names=None):
    date_names = date_names or {}
    months = []
    for y, m in _month_iter(start, finish):
        m_first = max(date(y, m, 1), start)
        m_last = min(_month_last_day(y, m), finish)
        days, wd, hol, exc, hours = [], 0, 0, 0, 0.0
        d = m_first
        while d <= m_last:
            st = _day_status(cal, d, shutdown_dates)
            cell = {'d': d.day, 'status': st}
            nm = date_names.get(d)
            if nm:
                cell['name'] = nm
            days.append(cell)
            if st == 'work' or st == 'special':
                wd += 1
                hours += cal.day_working_hours(d)
            if st == 'holiday':
                hol += 1
            if st in ('holiday', 'shutdown', 'special'):
                exc += 1
            d += timedelta(days=1)
        flag = None
        shut_in = sum(1 for c in days if c['status'] == 'shutdown')
        sp_in = sum(1 for c in days if c['status'] == 'special')
        if shut_in:
            flag = f'Shutdown {shut_in}d'
        elif sp_in:
            flag = f'Special {sp_in}d'
        months.append({
            'label': f'{_MONTH_ABBR[m]} {y}', 'year': y, 'month': m,
            'first_weekday': m_first.weekday(),  # Mon=0
            'working_days': wd, 'nonworking_days': len(days) - wd, 'holidays': hol,
            'exceptions': exc, 'working_hours': round(hours, 1), 'flag': flag, 'days': days,
        })
    return months


def _calendar_totals(cal, start, finish):
    wd = nwd = 0
    hours = 0.0
    d = start
    while d <= finish:
        if cal.is_working_day(d):
            wd += 1
            hours += cal.day_working_hours(d)
        else:
            nwd += 1
        d += timedelta(days=1)
    return wd, nwd, round(hours, 1)


def _hours_profiles(cal, notes=None):
    """Distinct working-hour patterns: the standard week + any special blocks. Each profile
    also carries a stable `key` (its hours string; a duplicate is suffixed with its index) and
    a planner-typed `note` — a justification for a reduced-hours period, restored from
    `notes` (settings['hours_notes']). Mirrors how shutdown reasons persist."""
    notes = notes or {}
    profiles = []
    # Standard: pick the most common intraday interval across the week, else flat hours.
    week_sigs = {}
    for dow, ivs in cal.work_intervals.items():
        week_sigs.setdefault(tuple(ivs), 0)
        week_sigs[tuple(ivs)] += 1
    if week_sigs:
        sig = max(week_sigs, key=week_sigs.get)
        if sig:
            hrs = sum(em - sm for sm, em in sig) / 60.0
            profiles.append({'name': 'Normal',
                             'hours': _hhmm(sig[0][0]) + '–' + _hhmm(sig[-1][1]),
                             'hours_per_day': round(hrs, 2),
                             'sub': f'{cal.days_per_week()} days/week'})
    if not profiles:
        profiles.append({'name': 'Normal', 'hours': f'{cal.day_hours:g} hrs/day',
                         'hours_per_day': cal.day_hours,
                         'sub': f'{cal.days_per_week()} days/week'})
    # Stable per-profile key = the hours string; a repeat gets an index suffix so each card
    # keeps its own note. Restore the saved note (default '') onto every profile.
    seen = {}
    for p in profiles:
        base = p['hours']
        n = seen.get(base, 0)
        seen[base] = n + 1
        key = base if n == 0 else f'{base}#{n}'
        p['key'] = key
        p['note'] = notes.get(key, '')
        p['days_per_week'] = cal.days_per_week()   # §4 table column (mirror of the 'sub' text)
    return profiles


# ── main entry ───────────────────────────────────────────────────────────────

def calendar_audit(data, config=None, settings=None):
    settings = settings or {}
    reasons = settings.get('shutdown_reasons', {}) or {}
    manual = _normalise_manual(settings.get('manual_shutdowns', []))
    hours_notes = settings.get('hours_notes', {}) or {}

    cals = data.calendars
    cstart, cfinish = _project_window(data)      # current schedule window (fallback)
    bstart, bfinish = _baseline_window(data)     # baseline window — the report's window
    start = bstart or cstart
    fin_exact = bfinish or cfinish
    if not start or not fin_exact or fin_exact < start:
        # Degrade gracefully: no usable dates.
        start = fin_exact = _to_date(data.project.get('data_date')) or date.today()
    # Ibrahim's rule: the calendar runs from Baseline Start to Baseline Finish, shown in
    # FULL months — so a baseline finishing 09 Feb still shows the whole of February.
    finish = _month_last_day(fin_exact.year, fin_exact.month)

    # Ibrahim's rule: the whole Calendar Audit is forward-looking — everything runs from the
    # DATA DATE to finish (the past is actualised). The timeline, the per-month stats, the
    # Calendar-Statistics tiles AND the exception lists (holidays / reduced-hours / shutdowns)
    # all start at the data date; nothing before it is shown. If the data date is outside the
    # window, nothing is hidden.
    dd = _to_date(data.project.get('data_date'))
    display_start = start
    hidden_months = 0
    if dd and start < dd <= finish:
        display_start = dd
        hidden_months = sum(1 for _ in _month_iter(start, dd)) - 1

    # Usage counts
    usage_count = {}
    for a in data.activities.values():
        cid = a.get('calendar_id')
        if cid and cid in cals:
            usage_count[cid] = usage_count.get(cid, 0) + 1
    total_assigned = sum(usage_count.values())

    # default calendar → primary; else most-used
    default_id = next((cid for cid, c in cals.items() if c.is_default and cid in usage_count), None)
    if not default_id and usage_count:
        default_id = max(usage_count, key=usage_count.get)
    primary_id = default_id or (next(iter(usage_count), None)) or (next(iter(cals), None))

    assigned_ids = [cid for cid in cals if usage_count.get(cid, 0) > 0]

    # per-calendar views
    by_calendar = {}
    for cid in assigned_ids:
        cal = cals[cid]
        is_primary = (cid == primary_id)
        exc = _classify_exceptions(cal, display_start, finish, reasons,
                                   manual if is_primary else [])
        shut_dates = _shutdown_dates(exc)
        months = _months_for_calendar(cal, display_start, finish, shut_dates,
                                      _exception_date_names(exc))
        wd, nwd, hours = _calendar_totals(cal, display_start, finish)
        by_calendar[cid] = {
            'object_id': cid, 'name': cal.name,
            'monthly_stats': months,
            'exceptions': exc,
            'hours_profiles': _hours_profiles(cal, hours_notes),
            'totals': {'working_days': wd, 'nonworking_days': nwd, 'working_hours': hours},
        }

    # top-level exceptions = primary calendar's (project's main calendar)
    prim_exc = by_calendar.get(primary_id, {}).get(
        'exceptions', {'holidays': [], 'special': [], 'shutdowns': []})
    prim_totals = by_calendar.get(primary_id, {}).get(
        'totals', {'working_days': 0, 'nonworking_days': 0, 'working_hours': 0.0})

    total_calendar_days = (finish - display_start).days + 1
    n_months = sum(1 for _ in _month_iter(display_start, finish)) or 1
    total_holidays = sum(h['days'] for h in prim_exc['holidays'])
    total_exc_days = (total_holidays
                      + sum(s['days'] for s in prim_exc['shutdowns'])
                      + sum(s['days'] for s in prim_exc['special']))
    wd = prim_totals['working_days']

    # §1 Execution Dashboard — the primary calendar's standard working hours (e.g. "08:00–16:00"),
    # read by both the screen and the PDF as the "Normal hours" tile.
    prim_profiles = by_calendar.get(primary_id, {}).get('hours_profiles', [])
    normal_hours = prim_profiles[0]['hours'] if prim_profiles else ''

    dashboard = {
        'project_start': _iso(cstart or start),
        'project_finish': _iso(cfinish or fin_exact),
        'data_date': _iso(_to_date(data.project.get('data_date'))),
        'baseline_start': _iso(bstart),
        'baseline_finish': _iso(bfinish),
        'window_start': _iso(display_start),
        'window_finish': _iso(finish),
        'total_calendar_days': total_calendar_days,
        'total_working_days': wd,
        'total_nonworking_days': prim_totals['nonworking_days'],
        'total_holidays': total_holidays,
        'total_exceptions': total_exc_days,
        'shutdown_periods': len(prim_exc['shutdowns']),
        'avg_working_days_per_month': round(wd / n_months, 1),
        'avg_working_hours_per_day': round(prim_totals['working_hours'] / wd, 1) if wd else 0.0,
        'normal_hours': normal_hours,
    }

    usage = _usage(cals, usage_count, total_assigned)
    conflicts = _conflicts(data, cals, usage_count, default_id)
    return {
        'dashboard': dashboard,
        'project': {'start': _iso(start), 'finish': _iso(finish),
                    'baseline_start': _iso(bstart), 'baseline_finish': _iso(bfinish),
                    'timeline_start': _iso(display_start), 'hidden_months': hidden_months},
        'primary_calendar_id': primary_id,
        'assigned_calendars': _assigned_list(cals, usage_count, assigned_ids, start, finish),
        'by_calendar': by_calendar,
        'exceptions': prim_exc,
        'comparison': _comparison(cals, usage_count, assigned_ids, display_start, finish),
        'usage': usage,
        'conflicts': conflicts,
        'conclusion': _conclusion(dashboard, prim_exc, usage, conflicts, primary_id, cals),
    }


def _conclusion(dashboard, exc, usage, conflicts, primary_id, cals):
    """Auto management summary (Section 11) — plain bullets from the numbers above."""
    bullets = []
    total_assigned = sum(u['activities'] for u in usage)
    prim = next((u for u in usage if u['object_id'] == primary_id), None)
    if prim and total_assigned:
        bullets.append(
            f"Consistency: {prim['pct']:g}% of activities run on one calendar "
            f"(\"{prim['name']}\") — the project is calendar-{'consistent' if prim['pct'] >= 80 else 'mixed'}.")
    n_conf = len(conflicts)
    if n_conf:
        top = conflicts[0]['title']
        bullets.append(f"Conflicts: {n_conf} issue{'s' if n_conf != 1 else ''} found — most notable: {top}.")
    else:
        bullets.append("Conflicts: none detected — calendar assignments look clean.")
    used = sum(1 for u in usage if u['activities'] > 0)
    bullets.append(f"Utilisation: {used} of {len(usage)} defined calendars are in use.")
    sd = exc['shutdowns']
    if sd:
        days = sum(s['days'] for s in sd)
        bullets.append(f"Shutdowns: {len(sd)} period{'s' if len(sd) != 1 else ''} "
                       f"totalling {days} days — they reduce available working time.")
    else:
        bullets.append("Shutdowns: none in the project window.")
    hdays = sum(h['days'] for h in exc['holidays'])
    bullets.append(f"Holidays: {hdays} holiday day{'s' if hdays != 1 else ''} across the project.")
    bullets.append(f"Working hours: average {dashboard['avg_working_hours_per_day']:g} hrs/day, "
                   f"{dashboard['avg_working_days_per_month']:g} working days/month.")
    if exc['special']:
        bullets.append(f"Special hours: {len(exc['special'])} reduced/seasonal period(s) — see the profile.")
    return bullets


def _assigned_list(cals, usage_count, assigned_ids, start, finish):
    out = []
    for cid in sorted(assigned_ids, key=lambda c: -usage_count.get(c, 0)):
        cal = cals[cid]
        out.append({'object_id': cid, 'name': cal.name, 'type': cal.type,
                    'is_default': cal.is_default,
                    'activity_count': usage_count.get(cid, 0),
                    'hours_per_day': cal.day_hours,
                    'days_per_week': cal.days_per_week()})
    return out


def _comparison(cals, usage_count, assigned_ids, start, finish):
    """Per-calendar comparison. Ibrahim's changes: no Activities column (those live in
    Usage, #09); the last column counts the non-working days that are still AHEAD — from
    the data date to finish (weekends + holidays + shutdowns). Elapsed past days are
    excluded, so `start` here is the data-date window start, not the baseline start."""
    rows = []
    for cid in sorted(assigned_ids, key=lambda c: -usage_count.get(c, 0)):
        cal = cals[cid]
        _wd, nwd, _hours = _calendar_totals(cal, start, finish)
        rows.append({'name': cal.name, 'hours_per_day': cal.day_hours,
                     'days_per_week': cal.days_per_week(),
                     'nonworking_days': nwd,
                     'is_default': cal.is_default})
    return rows


def _usage(cals, usage_count, total_assigned):
    rows = []
    for cid, cal in cals.items():
        n = usage_count.get(cid, 0)
        if cal.is_default:
            role = 'Default'
        elif n == 0:
            role = 'Unused'
        else:
            role = 'Non-default'
        rows.append({'object_id': cid, 'name': cal.name, 'activities': n,
                     'pct': round(n / total_assigned * 100, 1) if total_assigned else 0.0,
                     'role': role})
    rows.sort(key=lambda r: -r['activities'])
    return rows


def _conflicts(data, cals, usage_count, default_id):
    conflicts = []
    # 1) mixed calendars inside one WBS
    by_wbs = {}
    for a in data.activities.values():
        cid = a.get('calendar_id')
        if not cid or cid not in cals:
            continue
        wid = a.get('wbs_id')
        by_wbs.setdefault(wid, {}).setdefault(cid, 0)
        by_wbs[wid][cid] += 1
    for wid, calmap in by_wbs.items():
        if len(calmap) > 1:
            wbs_name = (data.wbs.get(wid, {}) or {}).get('name', 'WBS')
            names = ', '.join(f'{cals[c].name} ({calmap[c]})' for c in calmap)
            conflicts.append({'type': 'mixed_wbs', 'severity': 'High',
                              'title': f'Mixed calendars inside "{wbs_name}"',
                              'detail': f'Activities split across {len(calmap)} calendars: {names}.'})
    # 2) activities not on the project default calendar
    if default_id:
        off = sum(n for cid, n in usage_count.items() if cid != default_id)
        if off:
            conflicts.append({'type': 'not_default', 'severity': 'Medium',
                              'title': f'{off} activities not on the project default calendar',
                              'detail': f'Assigned to a calendar other than the default '
                                        f'"{cals[default_id].name}".'})
    # 3) unused calendars
    for cid, cal in cals.items():
        if usage_count.get(cid, 0) == 0:
            conflicts.append({'type': 'unused', 'severity': 'Low',
                              'title': f'Unused calendar "{cal.name}"',
                              'detail': 'Defined in the file but used by zero activities.'})
    return conflicts
