"""View-only projections of a computed schedule: the Schedule (Gantt) activity list and the
Project ▸ WBS summary tree.

Both are built ONCE on import from `compute()`'s records, sent to the screen and stored with the
snapshot (db.save_snapshot_views), so a project re-opened from Recent Projects shows the same
Gantt and WBS with no re-parse. Nothing here changes a metric — it only presents what the parse
and `compute()` already resolved.

Dates are the CURRENT schedule dates, as P6 shows them in its Start / Finish columns:
actual where the work has started / finished, the remaining early dates for the rest, and the
Planned dates only where the file carries neither (owner comment 26 — the bars used to be drawn
from Planned dates, so a progressed update showed finished work in the wrong place).
"""
from collections import defaultdict
from datetime import timedelta


def _iso(x):
    return x.isoformat() if hasattr(x, 'isoformat') else (str(x) if x else None)


def _iso_day(x):
    return x.date().isoformat() if hasattr(x, 'date') else (str(x)[:10] if x else None)


def p6_finish_day(f, s=None):
    """A FINISH P6 stores at 00:00 is the END of the day before (P6 shows 02-Jun for a finish saved
    as 03-Jun 00:00) - so it is read one second earlier, never before the start `s`."""
    try:
        if f is not None and (f.hour, f.minute, f.second) == (0, 0, 0):
            g = f - timedelta(seconds=1)
            if s is None or g >= s:
                return g
    except (AttributeError, TypeError):
        pass
    return f


def baseline_shown(data, aid, bl=None):
    """(start, finish) of one activity in the baseline as P6 lists them - BL Project Start /
    BL Project Finish, i.e. the baseline activity's own Start / Finish; its Planned dates when
    the file holds no such dates (a schedule with no baseline of its own)."""
    bl = bl or {}
    own = (getattr(data, 'baseline_dates_by_id', None) or {}).get(aid) or {} if data is not None else {}
    return own.get('start') or bl.get('planned_start'), own.get('finish') or bl.get('planned_finish')


def rescheduled_dates(data):
    """{activity ObjectId: (start, finish)} for the unfinished activities whose saved Finish lies
    BEFORE the data date. P6 never shows such a date - when it schedules, work that is not done
    moves to the data date or later - but an export can still carry the old one (seen on Grain
    Bulk: four 'Piles' submittals saved in May 2025 against a data date of 09-Aug.2026, which P6
    lists as 22 / 24 / 27 / 31-Aug.2026). Those activities, and only those, are given the dates
    of the in-tool forward pass; every other activity keeps the dates the file holds.
    View-only (WBS / Gantt dates); worked out once per schedule; never raises."""
    if data is None:
        return {}
    got = getattr(data, '_rescheduled_dates', None)
    if got is not None:
        return got
    out = {}
    try:
        acts = getattr(data, 'activities', None) or {}
        dd = (getattr(data, 'project', None) or {}).get('data_date')
        stale = set()
        if dd is not None and isinstance(acts, dict):
            for oid, a in acts.items():
                f = a.get('remaining_early_finish')      # only a date P6 itself scheduled and saved
                if not a.get('actual_finish') and f is not None and f < dd \
                        and a.get('task_type') not in ('LevelOfEffort', 'WBSSummary'):
                    stale.add(oid)
        if stale:
            from p6_compare.schedule import forward_pass
            es = {}
            ef = forward_pass(data, keep=set(acts) - stale, starts=es)
            for oid in stale:
                if ef.get(oid) is not None and ef[oid] >= dd:
                    out[oid] = (acts[oid].get('actual_start') or es.get(oid), ef[oid])
    except Exception:
        out = {}
    try:
        data._rescheduled_dates = out
    except Exception:
        pass
    return out


def current_start(a, moved=None):
    """P6 'Start': Actual Start once started, else the remaining early start, else Planned.
    ``moved`` = rescheduled_dates(data): a not-done activity saved before the data date."""
    m = (moved or {}).get(a.get('object_id'))
    if m and m[0] is not None:
        return m[0]
    return a.get('actual_start') or a.get('remaining_early_start') or a.get('planned_start')


def current_finish(a, moved=None):
    """P6 'Finish': Actual Finish once finished, else the remaining early finish, else Planned."""
    m = (moved or {}).get(a.get('object_id'))
    if m and m[1] is not None:
        return m[1]
    return a.get('actual_finish') or a.get('remaining_early_finish') or a.get('planned_finish')


def activity_status(a):
    if a.get('actual_finish'):
        return 'Completed'
    if a.get('actual_start'):
        return 'In Progress'
    s = str(a.get('status') or '').strip().lower().replace('_', ' ')
    if s.startswith('complete'):
        return 'Completed'
    if 'progress' in s or s == 'active':
        return 'In Progress'
    return 'Not Started'


def p6_order(wmap):
    """Sort key that lists WBS siblings the way P6 does: by the WBS Sequence Number the file
    carries, then by their order in the file (a file with no sequence keeps its own order)."""
    pos = {wid: i for i, wid in enumerate(wmap)}

    def key(wid):
        try:
            seq = float(wmap[wid].get('seq'))
        except (TypeError, ValueError):
            seq = float('inf')
        return (seq, pos.get(wid, 0))
    return key


def _p6_days(days):
    """A day count the way P6 prints it: one decimal, no trailing .0 (-7.5, -72)."""
    v = round(days + 0.0, 1)
    return int(v) if v == int(v) else v


def working_delay(cal, baseline_finish, finish):
    """Working days on `cal` from the first date to the second (+ when the second is later), the
    way P6 works a variance / float out: the working HOURS between the two dates on the
    calendar's own work times, divided by the calendar's hours per day - kept to one decimal
    as P6 shows it (-7.5 d stays -7.5). A calendar with no work times falls back to counting
    whole working days. None when a date or the calendar is missing."""
    if cal is None or baseline_finish is None or finish is None:
        return None
    try:
        from p6_evm.calendars import float_working_days, signed_working_minutes
        hours = float(getattr(cal, 'day_hours', 0) or 0)
        if hours > 0 and callable(getattr(cal, 'has_intraday', None)) and cal.has_intraday():
            mins = signed_working_minutes(cal, baseline_finish, finish)
            if mins is not None:
                return _p6_days(mins / (hours * 60.0))
        return float_working_days(cal, baseline_finish, finish)
    except Exception:
        return None


def working_span(cal, start, finish):
    """A summary bar's duration in working days on `cal` (P6's Original Duration of a WBS band:
    working hours from its start to its finish, over the calendar's hours per day)."""
    d = working_delay(cal, start, finish)
    return None if d is None else abs(d)


def critical_records(records):
    """The records P6's Critical filter keeps: flagged Critical and not finished."""
    out = []
    for r in records:
        a = r['activity']
        if is_critical(a, activity_status(a), r.get('total_float')):
            out.append(r)
    return out


def nocost_text(n, kind):
    """The Planned / Actual cell of a WBS that carries no cost: how many of its activities there
    are and how many are completed / in progress / not started - by actual status (kind 'a') or by
    the baseline dates at the cut-off date (kind 'p')."""
    total = n.get('nc_total') or 0
    if not total:
        return '—'
    parts = [f"{n.get('nc_%s_%s' % (kind, k)) or 0} {lbl}" for k, lbl in (('done', 'completed'), ('prog', 'in progress'), ('ns', 'not started'))
             if (n.get('nc_%s_%s' % (kind, k)) or 0)]
    return f"{total} activities: {', '.join(parts)}"


def float_delay(tf):
    """The Delay figure = the Total Float in days exactly as P6 shows it, to one decimal:
    a float of -7.5 d is a delay of -7.5, -72 d is -72 (late is NEGATIVE, spare float positive)."""
    if not isinstance(tf, (int, float)):
        return None
    return _p6_days(tf)


def _default_calendar(data):
    cals = getattr(data, 'calendars', None) or {}
    cid = (getattr(data, 'project', None) or {}).get('default_calendar_id')
    return cals.get(cid) or (next(iter(cals.values())) if cals else None)


def is_critical(a, status, tf):
    """Critical the way P6 flags it: the parser's ``is_critical`` (total float within the
    project's critical limit, or P6's Longest Path flag). Finished work is never critical.
    A record with no flag falls back to total float of zero or less."""
    if status == 'Completed':
        return False
    if 'is_critical' in a:
        return bool(a.get('is_critical'))
    return tf is not None and tf <= 0


def _cost_loaded(records):
    """The records that carry a budget in P6 (owner comments 63 / 93): only these have a
    Planned % and an Actual % that P6 itself can weight."""
    return [r for r in records if (r.get('bac') or 0) > 0 and r.get('planned_pct') is not None]


def cost_loaded_overview(records):
    """Project ▸ Overview figures from the COST-LOADED activities only (owner comment 93):
    Planned % and Actual % weighted by each activity's budget, Planned Value and Earned Value
    as those percentages of the total budget, SPI = Actual % / Planned %. Activities with no
    cost (Engineering / Procurement) take no part. None when the schedule carries no cost."""
    rows = _cost_loaded(records)
    bac = sum(r['bac'] for r in rows)
    if not rows or bac <= 0:
        return None
    pv = sum(r['bac'] * r['planned_pct'] for r in rows)
    ev = sum(r['bac'] * (r.get('actual_pct') or 0.0) for r in rows)
    return {
        'activities': len(rows),
        'all_activities': len(records),
        'bac': bac,
        'planned_pct': pv / bac,
        'actual_pct': ev / bac,
        'pv': pv,
        'ev': ev,
        'spi': (ev / pv) if pv else None,
    }


NO_CODE = '(No code assigned)'


def _progress_rows(pairs):
    """[(group name, record), …] → rows {name, activities, bac, planned_pct, actual_pct},
    budget-weighted, largest budget first."""
    b = {}
    for name, r in pairs:
        g = b.setdefault(name, {'name': name, 'activities': 0, 'bac': 0.0, 'pv': 0.0, 'ev': 0.0})
        g['activities'] += 1
        g['bac'] += r['bac']
        g['pv'] += r['bac'] * r['planned_pct']
        g['ev'] += r['bac'] * (r.get('actual_pct') or 0.0)
    out = []
    for g in b.values():
        out.append({'name': g['name'], 'activities': g['activities'], 'bac': g['bac'],
                    'planned_pct': g['pv'] / g['bac'], 'actual_pct': g['ev'] / g['bac']})
    out.sort(key=lambda x: (x['name'] == NO_CODE, -x['bac']))
    return out


def progress_groups(records, data):
    """Project ▸ Overview 'Progress by …' choices (owner comment 94): the cost-loaded
    activities grouped by WBS and by every P6 activity code that is assigned to at least one of
    them — Planned % vs Actual % per code value, weighted by budget as P6 does."""
    rows = _cost_loaded(records)
    if not rows:
        return []
    wmap = data.wbs
    paths = [wbs_path(r['activity'].get('wbs_id'), wmap) for r in rows]
    lvl = 0                                   # the first WBS level that really divides the work
    while paths and all(len(p) > lvl + 1 for p in paths) and len({p[lvl][0] for p in paths}) == 1:
        lvl += 1
    names = {}
    for p in paths:
        if len(p) > lvl:
            names.setdefault(p[lvl][0], p[lvl][1])
    dup = len(set(names.values())) < len(names)   # two WBS with one name: show the parent too
    def wname(p):
        if len(p) <= lvl:
            return '(No WBS)'
        return ' > '.join(n for _, n in p[max(0, lvl - 1):lvl + 1]) if dup else p[lvl][1]
    groups = [{'key': 'wbs', 'label': 'WBS', 'rows': _progress_rows([(wname(p), r) for p, r in zip(paths, rows)])}]
    for dim in list(getattr(data, 'activity_code_types', []) or []):
        pairs, coded = [], 0
        for r in rows:
            v = (r['activity'].get('activity_codes') or {}).get(dim)
            if v:
                coded += 1
            pairs.append((str(v) if v else NO_CODE, r))
        if coded:
            groups.append({'key': 'code:' + dim, 'label': dim, 'rows': _progress_rows(pairs)})
    return groups


def wbs_path(wbs_id, wbs_map):
    """[(wbs_id, name), …] from the TOP level down to the activity's own WBS (P6 order)."""
    out, seen, cur = [], set(), wbs_id
    while cur and cur not in seen:
        seen.add(cur)
        node = wbs_map.get(cur)
        if not node:
            break
        out.append((cur, node.get('name') or '(WBS)'))
        cur = node.get('parent_object_id')
    out.reverse()
    return out


def gantt_activities(records, wbs_map, data=None):
    """Slim, JSON-safe activity list for the Schedule (Gantt): one row per activity that has a
    start and a finish. `wbs` is the full path top → own WBS; `wbs_top` / `wbs_top_id` the true
    top-level WBS the row is grouped under."""
    out, paths, costs = [], [], []
    bl_by_id = (getattr(data, 'baseline_by_id', None) or {}) if data is not None else {}
    cals = (getattr(data, 'calendars', None) or {}) if data is not None else {}
    moved = rescheduled_dates(data)
    for r in records:
        a = r['activity']
        s, f = current_start(a, moved), current_finish(a, moved)
        if not s or not f:
            continue
        try:
            if f < s:
                f = s
        except TypeError:
            pass
        path = wbs_path(a.get('wbs_id'), wbs_map)
        status = activity_status(a)
        tf = r.get('total_float')
        ps, pf = a.get('planned_start'), a.get('planned_finish')
        bl = bl_by_id.get(a.get('id'))
        bf = baseline_shown(data, a.get('id'), bl)[1] if bl else None
        if a.get('task_type') != 'StartMilestone':      # the day P6 shows for a finish saved at 00:00
            f, pf, bf = p6_finish_day(f, s), p6_finish_day(pf, ps), p6_finish_day(bf)
        out.append({
            'id':         a.get('id') or '',
            'name':       a.get('name') or '',
            'wbs':        ' > '.join(n for _, n in path),
            'wbs_top':    path[0][1] if path else 'Ungrouped',
            'wbs_top_id': str(path[0][0]) if path else '',
            'start':      _iso(s),
            'finish':     _iso(f),
            'planned_start':  _iso(ps),
            'planned_finish': _iso(pf),
            'status':     status,
            'pct':        round((a.get('percent_complete') or 0) * 100),
            'tf':         round(tf, 1) if isinstance(tf, (int, float)) else None,
            'critical':   is_critical(a, status, tf),
            'milestone':  a.get('task_type') in ('StartMilestone', 'FinishMilestone'),
            'baseline_finish': _iso(bf),
            # Delay = the UPDATE's own Total Float exactly as P6 shows it (float -12 d = delay -12,
            # late is negative). Not a baseline comparison.
            'delay':      float_delay(tf) if status != 'Completed' else None,
            # the activity's P6 activity codes, for the Gantt's pick-a-code column
            'codes':      {k: str(v) for k, v in (a.get('activity_codes') or {}).items() if v},
            'wbs_id':     str(a.get('wbs_id')) if a.get('wbs_id') is not None else '',
            # P6 marks an actual date with an 'A' (19-Jun-26 A)
            'start_actual':  bool(a.get('actual_start')),
            'finish_actual': bool(a.get('actual_finish')),
        })
        paths.append(path)
        costs.append((r.get('bac') or 0) > 0)
    # A schedule whose whole WBS hangs under ONE node (a 'Project' root) would give a single
    # band: group one level down instead, repeating until the level really divides the work.
    lvl = 0
    while paths and all(len(p) > lvl + 1 for p in paths) and len({p[lvl][0] for p in paths}) == 1:
        lvl += 1
    if lvl:
        for row, p in zip(out, paths):
            row['wbs_top'], row['wbs_top_id'] = p[lvl][1], str(p[lvl][0])
    # Construction = the main WBS branches that hold cost-loaded activities (Engineering /
    # Procurement / key-date branches carry no cost). A schedule with no cost keeps every row.
    built = {row['wbs_top_id'] for row, c in zip(out, costs) if c}
    for row in out:
        row['construction'] = (row['wbs_top_id'] in built) if built else True
    out.sort(key=lambda x: x['start'])
    return out


def planned_by_dates(bs, bf, dd):
    """Planned % of a WBS from its BASELINE dates alone (owner): the calendar days of the
    baseline that have passed at the cut-off date / all its calendar days, both ends counted -
    baseline 01-Jan to 10-Jan, cut-off 05-Jan = 5 of 10 days = 50 %. None without the dates."""
    try:
        d = lambda x: x.date() if hasattr(x, 'date') else x
        s, f, c = d(bs), d(bf), d(dd)
        total = (f - s).days + 1
        if total <= 0:
            return 100.0 if c >= f else 0.0
        return round(100.0 * max(0, min(total, (c - s).days + 1)) / total, 1)
    except Exception:
        return None


def wbs_views(records, data):
    """→ (wbs_summary, wbs_main). Pre-order list of the WBS nodes whose subtree holds activities
    (with depth), each carrying weighted planned/actual %, an activity count and the rolled-up
    start/finish, using the same BAC-else-duration weighting as the EVM roll-up. `wbs_main`
    lists the selectable top-level branches (e.g. Engineering / Construction). Leaf nodes are
    the WBS that directly hold activities (activities themselves are NOT listed)."""
    wmap = data.wbs
    any_bac = any((r.get('bac') or 0) > 0 for r in records)

    def _mn(a, b):
        return b if a is None else (a if b is None else min(a, b))

    def _mx(a, b):
        return b if a is None else (a if b is None else max(a, b))

    def base():
        return {'n': 0, 'w': 0.0, 'wp': 0.0, 'wa': 0.0, 'c': 0, 's': None, 'f': None, 'bs': None, 'bf': None,
                'ef': None, 'lf': None, 'open': 0, 'all': 0, 'b': 0.0, 'pv': 0.0, 'ev': 0.0, 'ps': None, 'pf': None,
                'sa': None, 'began': 0, 'nc': 0, 'ad': 0, 'ap': 0, 'an': 0, 'pd': 0, 'pp': 0, 'pn': 0, 'ms': 0, 'msd': 0}

    bl_by_id = getattr(data, 'baseline_by_id', None) or {}
    dd0 = (getattr(data, 'project', None) or {}).get('data_date')
    direct = defaultdict(base)
    moved = rescheduled_dates(data)                # not-done work saved before the data date
    for r in records:
        a = r['activity']
        wid = a.get('wbs_id')
        if wid is None:
            continue
        d = direct[wid]
        if not (r.get('bac') or 0) > 0 and a.get('task_type') not in ('StartMilestone', 'FinishMilestone'):
            # an activity with no cost (a milestone is never counted): counted by its ACTUAL status and by where its BASELINE
            # dates put it at the cut-off date (completed / in progress / not started)
            d['nc'] += 1
            st = activity_status(a)
            d['ad' if st == 'Completed' else 'ap' if st == 'In Progress' else 'an'] += 1
            bl0 = bl_by_id.get(a.get('id')) or {}
            ps0, pf0 = bl0.get('planned_start') or a.get('planned_start'), bl0.get('planned_finish') or a.get('planned_finish')
            try:
                if dd0 is not None and ps0 is not None and pf0 is not None:
                    d['pd' if pf0 <= dd0 else 'pp' if ps0 <= dd0 else 'pn'] += 1
            except TypeError:
                pass
        if a.get('task_type') in ('StartMilestone', 'FinishMilestone'):
            d['ms'] += 1                                 # milestones, and the ones achieved
            d['msd'] += 1 if activity_status(a) == 'Completed' else 0
        cs = current_start(a, moved)
        if cs is not None and (d['s'] is None or cs < d['s']):
            d['sa'] = bool(a.get('actual_start'))        # is the band's start an ACTUAL date?
        d['began'] += 1 if a.get('actual_start') else 0
        d['s'] = _mn(d['s'], cs)                        # current schedule (expected)
        d['f'] = _mx(d['f'], current_finish(a, moved) if a.get('task_type') == 'StartMilestone' else p6_finish_day(current_finish(a, moved), cs))
        # for the WBS's own Total Float: its latest early finish and latest late finish
        d['ef'] = _mx(d['ef'], a.get('actual_finish') or a.get('remaining_early_finish'))
        d['lf'] = _mx(d['lf'], a.get('actual_finish') or a.get('remaining_late_finish'))
        d['open'] += 0 if a.get('actual_finish') else 1
        d['all'] += 1
        d['ps'] = _mn(d['ps'], a.get('planned_start'))   # P6's Original Duration of a band runs
        d['pf'] = _mx(d['pf'], a.get('planned_finish'))  # from its earliest Planned Start to its latest Planned Finish
        bac = r.get('bac') or 0.0                       # P6's Budgeted Total Cost / PV / EV
        d['b'] += bac
        d['pv'] += bac * (r.get('planned_pct') or 0.0)
        d['ev'] += bac * (r.get('actual_pct') or 0.0)
        bl = bl_by_id.get(a.get('id'))                  # embedded baseline, when present
        if bl:
            # P6's BL Project Start / Finish: the baseline's own Start / Finish (its Planned dates when absent)
            b_s, b_f = baseline_shown(data, a.get('id'), bl)
            d['bs'] = _mn(d['bs'], b_s)
            d['bf'] = _mx(d['bf'], p6_finish_day(b_f, b_s))
        if r.get('planned_pct') is None:
            continue
        w = (r.get('bac') or 0.0) if any_bac else float(a.get('planned_duration') or 1.0)
        d['n'] += 1
        d['c'] += 1 if (r.get('bac') or 0) > 0 else 0
        d['w'] += w
        d['wp'] += w * r['planned_pct']
        d['wa'] += w * (r.get('actual_pct') or 0.0)

    order = p6_order(wmap)
    cal = _default_calendar(data)
    kids = defaultdict(list)
    for wid, node in wmap.items():
        kids[node.get('parent_object_id')].append(wid)
    roots = [wid for wid in wmap
             if not wmap[wid].get('parent_object_id') or wmap[wid].get('parent_object_id') not in wmap]

    sub = {}

    def _rollup(wid):
        t = dict(direct.get(wid) or base())
        for k in kids.get(wid, []):
            c = _rollup(k)
            t['n'] += c['n']; t['w'] += c['w']; t['wp'] += c['wp']; t['wa'] += c['wa']; t['c'] += c['c']
            if c['s'] is not None and (t['s'] is None or c['s'] < t['s']):
                t['sa'] = c['sa']
            t['began'] += c['began']
            t['s'] = _mn(t['s'], c['s']); t['f'] = _mx(t['f'], c['f'])
            t['ef'] = _mx(t['ef'], c['ef']); t['lf'] = _mx(t['lf'], c['lf']); t['open'] += c['open']
            t['all'] += c['all']; t['b'] += c['b']; t['pv'] += c['pv']; t['ev'] += c['ev']
            for k in ('nc', 'ad', 'ap', 'an', 'pd', 'pp', 'pn', 'ms', 'msd'):
                t[k] += c[k]
            t['ps'] = _mn(t['ps'], c['ps']); t['pf'] = _mx(t['pf'], c['pf'])
            t['bs'] = _mn(t['bs'], c['bs']); t['bf'] = _mx(t['bf'], c['bf'])
        sub[wid] = t
        return t
    for rt in roots:
        _rollup(rt)

    wbs_summary = []

    def _emit(wid, depth, parent):
        t = sub.get(wid) or base()
        if t['n'] == 0:
            return
        childs = [k for k in kids.get(wid, []) if (sub.get(k) or base())['n'] > 0]
        wbs_summary.append({
            'id':         str(wid),
            'parent':     str(parent) if parent is not None else None,
            'name':       wmap[wid].get('name') or '(WBS)',
            'depth':      depth,
            'activities': t['n'],
            # activities under this WBS that carry a budget: a WBS with none has no Planned %
            # / Actual % in P6, so the screen and the report leave them out (owner comment 63)
            'cost_loaded': t['c'],
            'planned':    round(100 * t['wp'] / t['w'], 1) if t['w'] else None,
            'actual':     round(100 * t['wa'] / t['w'], 1) if t['w'] else None,
            'start':          _iso_day(t['s']),     # expected (current) start
            'finish':         _iso_day(t['f']),     # expected (current) finish
            'baseline_start': _iso_day(t['bs']),
            'baseline_finish': _iso_day(t['bf']),
            # Delay = the WBS's Total Float on the UPDATE (owner, round 3):
            # P6 works a summary float out from the summarised dates - latest Late Finish against
            # latest Early Finish - on the project's default calendar. None once all work is done.
            # shown with P6's own sign: late = negative (Total Float -72 → Delay -72)
            'delay':      working_delay(cal, t['ef'], t['lf']) if t['open'] else None,
            'total_float': working_delay(cal, t['ef'], t['lf']) if t['open'] else None,
            # P6 status of the WBS and its 'A' marks: the start is actual when its earliest
            # activity has started; the finish is actual only once every activity is finished
            'status':     ('Completed' if t['all'] and not t['open'] else ('In Progress' if t['began'] else 'Not Started')),
            'start_actual':  bool(t['sa']),
            'finish_actual': bool(t['all'] and not t['open']),
            # the activities of this WBS that carry NO cost, counted (a WBS with no cost has no %)
            'nc_total':   t['nc'],
            # COUNT-BASED Planned % / Actual % of a WBS with no cost: planned = activities whose baseline
            # finish is on/before the cut-off date, actual = activities started (in progress / completed)
            # Planned % by the baseline dates (owner): every WBS with baseline dates carries one
            'planned_time': planned_by_dates(t['bs'], t['bf'], dd0),
            'planned_count_pct': round(100.0 * t['pd'] / t['nc'], 1) if t['nc'] else None,
            'actual_count_pct':  round(100.0 * (t['ad'] + t['ap']) / t['nc'], 1) if t['nc'] else None,
            'nc_a_done':  t['ad'], 'nc_a_prog': t['ap'], 'nc_a_ns': t['an'],      # by actual status
            'nc_p_done':  t['pd'], 'nc_p_prog': t['pp'], 'nc_p_ns': t['pn'],      # by baseline dates at the cut-off
            # a WBS of milestones only (nothing to count, no cost): Actual % = milestones achieved / all (owner)
            'ms_total':   t['ms'], 'ms_done': t['msd'],
            'milestone_only': bool(t['ms'] and not t['nc'] and not t['c']),
            'actual_ms':  round(100.0 * t['msd'] / t['ms'], 1) if (t['ms'] and not t['nc'] and not t['c']) else None,
            # the other columns of P6's WBS band
            'count':      t['all'],                                   # Activity Count
            'orig_dur':   working_span(cal, t['ps'], t['pf']),        # Original Duration (working days)
            'bac':        round(t['b'], 2),                           # Budgeted Total Cost
            'pv':         round(t['pv'], 2),                          # Planned Value Cost
            'ev':         round(t['ev'], 2),                          # Earned Value Cost
            'leaf':       (direct.get(wid) or base())['n'] > 0 and not childs,
        })
        for k in sorted(childs, key=order):          # the order P6 itself lists them in
            _emit(k, depth + 1, wid)
    for rt in sorted(roots, key=order):
        _emit(rt, 0, None)

    # Selectable top-level branches: the activity-bearing roots when there are several, else
    # the activity-bearing children of the sole root (so a single "Project" root exposes
    # Engineering / Construction).
    roots_act = [rt for rt in roots if (sub.get(rt) or base())['n'] > 0]
    if len(roots_act) >= 2:
        main_ids = roots_act
    elif roots_act:
        ch = [k for k in kids.get(roots_act[0], []) if (sub.get(k) or base())['n'] > 0]
        main_ids = ch if len(ch) >= 2 else [roots_act[0]]
    else:
        main_ids = []
    main_ids = sorted(main_ids, key=order)
    wbs_main = [{'id': str(w), 'name': wmap[w].get('name') or '(WBS)'} for w in main_ids]
    try:                                        # view-only extras; the table itself never depends on them
        for m in wbs_main:
            stage_weighted_actual(wbs_summary, m['id'])
        for m in wbs_main:
            m['explain'] = wbs_explain(wbs_summary, m['id'], dd0)
    except Exception:
        pass
    return wbs_summary, wbs_main


def _wbs_block(nodes, wid):
    """The node ``wid`` and its descendants out of the pre-order WBS list."""
    i0 = next((i for i, n in enumerate(nodes) if str(n.get('id')) == str(wid)), -1)
    if i0 < 0:
        return []
    out = [nodes[i0]]
    for n in nodes[i0 + 1:]:
        if (n.get('depth') or 0) <= (nodes[i0].get('depth') or 0):
            break
        out.append(n)
    return out


def _by_cost(n):
    return (n.get('cost_loaded') or 0) > 0 and n.get('actual') is not None


def wbs_actual_shown(n):
    """The Actual % the WBS table prints for a WBS: the stage-weighted figure of a Procurement WBS,
    100 once all its work is done, Earned value / Budget when it carries cost, else activities
    started / all activities."""
    if n.get('actual_stage') is not None:
        return n['actual_stage']
    if n.get('finish_actual'):
        return 100.0
    if _by_cost(n):
        return n.get('actual')
    if n.get('actual_count_pct') is None and n.get('actual_ms') is not None:
        return n['actual_ms']                        # milestones only: achieved / all
    return n.get('actual_count_pct')


def stage_weighted_actual(nodes, wid):
    """Actual % of a PROCUREMENT main WBS by its stages (owner): the WBS right under it are its stages
    (Submittal, Approval, PO, Fabrication, Delivery ...); the stages that carry NO cost share the weight
    equally (4 stages = 25% each, 3 = 33.33%, 2 = 50%) and the WBS's Actual % = sum of weight x stage
    Actual %. Cost-loaded stages are left out of the weight and keep their own cost %. Nothing changes
    when every stage is cost loaded. Sets ``actual_stage`` + ``stages`` on the node."""
    blk = _wbs_block(nodes, wid)
    if not blk or 'procur' not in str(blk[0].get('name') or '').lower():
        return
    top = blk[0]
    kids = [n for n in blk[1:] if n.get('depth') == (top.get('depth') or 0) + 1]
    free = [n for n in kids if not _by_cost(n) and wbs_actual_shown(n) is not None]
    if not kids or not free:
        return
    w = 100.0 / len(free)
    top['stages'] = [{'name': n.get('name'), 'cost': _by_cost(n), 'weight': round(w, 2) if n in free else None,
                      'pct': wbs_actual_shown(n),
                      'weighted': round(w * wbs_actual_shown(n) / 100.0, 2) if n in free else None} for n in kids]
    top['actual_stage'] = round(sum(w * wbs_actual_shown(n) / 100.0 for n in free), 1)


def wbs_milestone_only(n):
    """A WBS that holds milestones only (no activity to count, no cost): its Actual % = milestones
    achieved / all its milestones, and it gets no 'how it is reached' table (owner) - its milestone
    chart is its analysis."""
    return not (n.get('nc_total') or n.get('cost_loaded'))


_STAGE_RE = None


def _stageish(name):
    """A WBS named after a stage of the work: Submittal, Approval, PO, Fabrication, Delivery ..."""
    global _STAGE_RE
    if _STAGE_RE is None:
        import re
        _STAGE_RE = re.compile(r'\b(submitt?als?|approvals?|po|purchase|issuance|fabrication|manufacturing|deliver\w*|deliever\w*)\b', re.I)
    return bool(_STAGE_RE.search(str(name or '')))


def _amount(v):
    v = float(v or 0)
    return '%.2f M' % (v / 1e6) if abs(v) >= 1e6 else '%.1f K' % (v / 1e3) if abs(v) >= 1e3 else '%.0f' % v


def _cell(n):
    """One figure of the 'how the Actual % is reached' panels = one Actual % of the WBS table, with what
    it is measured by: started / all activities (count) or Earned value / Budget (cost)."""
    pct = wbs_actual_shown(n)
    if n.get('actual_stage') is not None:
        return {'basis': 'stages', 'done': None, 'total': None, 'pct': pct, 'frac': 'by stage weights'}
    if _by_cost(n):
        ev, bac = n.get('ev') or 0, n.get('bac') or 0
        big = abs(bac) >= 1e6
        frac = ('%.2f ÷ %.2f M' % (ev / 1e6, bac / 1e6)) if big else '%s ÷ %s' % (_amount(ev), _amount(bac))
        return {'basis': 'cost', 'done': ev, 'total': bac, 'pct': pct, 'frac': frac}
    tot = n.get('nc_total') or 0
    got = (n.get('nc_a_done') or 0) + (n.get('nc_a_prog') or 0)
    return {'basis': 'count', 'done': got, 'total': tot, 'pct': pct, 'frac': '%d ÷ %d' % (got, tot)}


def _pct_txt(v):
    return '—' if v is None else '%.1f%%' % v


def _no_cost(ps):
    """Owner: a cost-loaded Actual % needs no clarification - a cost-loaded WBS gets no panel, and the
    cost-loaded stages of Procurement leave the strip and the table (one line names them)."""
    if not ps or ps[0]['result']['basis'] == 'cost':
        return []
    out = []
    for p in ps:
        p = dict(p)
        if p['kind'] == 'stages':
            p['left_out'] = [x['name'] for x in p['parts'] if x.get('weight') is None]
            p['parts'] = [x for x in p['parts'] if x.get('weight') is not None]
        elif p['kind'] == 'matrix':
            keep = list(range(len(p['cols'])))
            if p.get('weights'):
                keep = [i for i in keep if p['weights'][i]]
            if p.get('total'):
                keep = [i for i in keep if p['total'][i]['basis'] != 'cost']
            pick = lambda L: [L[i] for i in keep]
            p['cols'] = pick(p['cols'])
            p['rows'] = [dict(r_, cells=pick(r_['cells'])) for r_ in p['rows']]
            p['rows'] = [r_ for r_ in p['rows'] if r_.get('span') or any(r_['cells'])]
            for k in ('total', 'weights', 'weighted'):
                if p.get(k):
                    p[k] = pick(p[k])
            if not p['cols']:
                continue
        elif p['kind'] == 'list':
            p['rows'] = [r_ for r_ in p['rows'] if r_['basis'] != 'cost']
        out.append(p)
    return out


def wbs_explain(nodes, wid, dd=None):
    """How every ACTUAL % of a main WBS's table is reached - only what is NOT measured by cost."""
    return _no_cost(_explain_panels(nodes, wid))


def _explain_panels(nodes, wid):
    """The panels that show how every ACTUAL % of a main WBS's table is reached (owner) - stage by
    stage, not as one total. Planned % is by the baseline dates and is not broken down. A WBS of
    milestones only gets nothing. Panels, in order:
      'stages' / 'sum' - the WBS right under the main WBS as tiles ending in the main WBS's Actual %
                         (a Procurement WBS: with the equal weights of its stages without cost);
      'matrix'         - a row per WBS below, a COLUMN per stage (Actual Submittal % beside Actual
                         Approval % ...), each cell = one Actual % of the WBS table;
      'list'           - when the WBS below are not stages: one row per WBS, done / total and Actual %."""
    blk = _wbs_block(nodes, wid)
    if not blk or wbs_milestone_only(blk[0]):
        return []
    top, d0 = blk[0], blk[0].get('depth') or 0
    name = top.get('name') or ''
    kids = [i for i, n in enumerate(blk) if n.get('depth') == d0 + 1 and not wbs_milestone_only(n)]

    def below(i):
        out = []
        for m in blk[i + 1:]:
            if (m.get('depth') or 0) <= (blk[i].get('depth') or 0):
                break
            if not wbs_milestone_only(m):
                out.append(m)
        return out

    res = _cell(top)
    parts = [dict(_cell(blk[i]), name=blk[i].get('name')) for i in kids]
    if top.get('stages'):
        by = {s.get('name'): s for s in top['stages']}
        for p in parts:
            p['weight'], p['weighted'] = (by.get(p['name']) or {}).get('weight'), (by.get(p['name']) or {}).get('weighted')
            p['tag'] = ('weight %.2f%%' % p['weight']) if p['weight'] is not None else 'cost loaded — no weight'
        w = [p for p in parts if p.get('weight') is not None]
        formula = '%s = %s = %s' % (' + '.join('%.2f%% × %s' % (p['weight'], _pct_txt(p['pct'])) for p in w),
                                    ' + '.join('%.2f' % p['weighted'] for p in w), _pct_txt(res['pct']))
        head = {'kind': 'stages', 'title': 'The stages of %s, in order' % name, 'tag': 'equal weight for the stages without cost',
                'parts': parts, 'result': res, 'formula': formula, 'adds': False, 'name': name}
    else:
        same = bool(parts) and all(p['basis'] == res['basis'] for p in parts)
        adds = same and abs(sum(p['done'] or 0 for p in parts) - (res['done'] or 0)) < 1 \
            and abs(sum(p['total'] or 0 for p in parts) - (res['total'] or 0)) < 1
        if res['basis'] == 'count' and adds and len(parts) > 1:
            formula = '(%s) ÷ (%s) = %d ÷ %d = %s' % (' + '.join('%d' % p['done'] for p in parts), ' + '.join('%d' % p['total'] for p in parts),
                                                      res['done'], res['total'], _pct_txt(res['pct']))
        elif res['basis'] == 'cost':
            formula = 'Earned value ÷ Budget = %s = %s' % (res['frac'], _pct_txt(res['pct']))
        else:
            formula = 'activities started ÷ all activities = %s = %s' % (res['frac'], _pct_txt(res['pct']))
        head = {'kind': 'sum', 'title': 'How the %s of %s is reached' % (_pct_txt(res['pct']), name),
                'tag': 'Earned value ÷ Budget' if res['basis'] == 'cost' else 'activities started ÷ all activities',
                'parts': parts, 'result': res, 'formula': formula, 'adds': adds, 'name': name}
    panels = [head]
    if not kids:
        return panels
    result = {'pct': res['pct'], 'text': head['formula'], 'label': '%s Actual %%' % name}

    stage_kids = sum(1 for i in kids if _stageish(blk[i].get('name')))
    if len(kids) >= 2 and (top.get('stages') or stage_kids >= 2):
        # the WBS right under the main WBS are the stages = the columns
        toks = [set(str(blk[i].get('name') or '').lower().split()) for i in kids]
        common = set.intersection(*toks) if toks else set()

        def norm(s, drop):
            keep = [t for t in str(s or '').split() if t.lower().strip('.,') not in drop]
            return ' '.join(keep) or str(s or '')

        root, lone = {'kids': {}}, []
        for ci, i in enumerate(kids):
            drop = toks[ci] - common
            desc = below(i)
            if not desc:
                lone.append({'name': blk[i].get('name'), 'indent': 0, 'has_kids': False,
                             'cells': [(_cell(blk[i]) if c == ci else None) for c in range(len(kids))]})
                continue
            stack = []
            for m in desc:
                rel = min(max(0, (m.get('depth') or 0) - d0 - 2), len(stack))
                label = norm(m.get('name'), drop)
                par = root if rel == 0 else stack[rel - 1]
                key, k = label.lower(), 2
                while key in par['kids'] and ci in par['kids'][key]['cells']:
                    key, k = '%s #%d' % (label.lower(), k), k + 1
                node = par['kids'].setdefault(key, {'name': label, 'cells': {}, 'kids': {}})
                node['cells'][ci] = _cell(m)
                stack[rel:] = [node]
        rows = []

        def walk(node, indent):
            for ch in node['kids'].values():
                rows.append({'name': ch['name'], 'indent': indent, 'has_kids': bool(ch['kids']),
                             'cells': [ch['cells'].get(c) for c in range(len(kids))]})
                walk(ch, indent + 1)
        walk(root, 0)
        mat = {'kind': 'matrix', 'title': 'Actual %% of every stage — %s' % name, 'tag': 'each cell = one row of the WBS table',
               'first': 'WBS', 'cols': [blk[i].get('name') for i in kids], 'rows': rows + lone,
               'total': [_cell(blk[i]) for i in kids], 'total_label': 'Stage Actual %' if top.get('stages') else 'Total — %s' % name,
               'result': result}
        if top.get('stages'):
            mat['weights'] = [('%.2f%%' % p['weight']) if p.get('weight') is not None else None for p in parts]
            mat['weighted'] = [('%.2f%%' % p['weighted']) if p.get('weighted') is not None else None for p in parts]
        panels.append(mat)
        return panels

    deep = any((m.get('depth') or 0) > d0 + 2 for i in kids for m in below(i))
    split = sum(1 for i in kids for m in below(i) if _stageish(m.get('name')))
    if not deep and split >= 2:
        # the stages sit one level lower (Design: a package, then its Submittal and its Approval)
        cols, rows = [], []
        for i in kids:
            drop = set(str(blk[i].get('name') or '').lower().split())
            got = {}
            for m in below(i):
                label = ' '.join(t for t in str(m.get('name') or '').split() if t.lower() not in drop) or str(m.get('name') or '')
                if label not in cols:
                    cols.append(label)
                got[label] = _cell(m)
            rows.append({'name': blk[i].get('name'), 'indent': 0, 'has_kids': False, 'got': got, 'own': _cell(blk[i])})
        for r in rows:
            got, own = r.pop('got'), r.pop('own')
            r['cells'] = [got.get(c) for c in cols]
            if not got:
                r['span'] = own
        panels.append({'kind': 'matrix', 'title': 'Actual %% of every stage — %s' % name, 'tag': 'each cell = one row of the WBS table',
                       'first': 'WBS', 'cols': cols, 'rows': rows, 'total': None, 'total_label': 'Total — %s' % name, 'result': result})
        return panels

    rows = []
    for i in kids:
        sub_ = below(i)
        rows.append(dict(_cell(blk[i]), name=blk[i].get('name'), indent=0, has_kids=bool(sub_)))
        for j, m in enumerate(sub_):
            ind = (m.get('depth') or 0) - d0 - 1
            nxt = sub_[j + 1] if j + 1 < len(sub_) else None
            rows.append(dict(_cell(m), name=m.get('name'), indent=ind, has_kids=bool(nxt and (nxt.get('depth') or 0) > (m.get('depth') or 0))))
    panels.append({'kind': 'list', 'title': 'Actual %% by WBS — %s' % name, 'tag': 'each row = one row of the WBS table',
                   'measure': 'Earned ÷ Budget' if res['basis'] == 'cost' else 'Started ÷ Total',
                   'rows': rows, 'total': dict(res, name='Total — %s' % name), 'result': result})
    return panels


_MILESTONES = ('StartMilestone', 'FinishMilestone')
COST_LOADED_SHARE = 0.95      # a main WBS with this share of its activities cost loaded is measured by cost, not by count
_STAGE_ORDER = ['Schematic', 'Detailed design', 'IFC', 'Shop Drawing', 'Shop drawing', 'As-Built']
_STAGE_ALIAS = {'Detailed': 'Detailed design', 'Detailed Design': 'Detailed design', 'Material Submital': 'Material Submittal'}


def _row_rank(label):
    """The order of the rows of a count table, the same in every project: the design stages in their
    own order (Schematic, Detailed design, IFC, Shop drawing, As-Built) and a procurement chain as
    Submittal, then Approval, then PO, then Delivery."""
    if label in _STAGE_ORDER:
        return _STAGE_ORDER.index(label)
    low = str(label).lower()
    for i, key in enumerate(('submit', 'approv', 'po', 'deliver')):
        if (key == 'po' and (low.startswith('po') or ' po' in low)) or (key != 'po' and key in low):
            return 20 + i
    return 99


def uncosted_progress(records, data):
    """Progress BY COUNT of the activities that carry no cost (design, engineering, procurement,
    client inputs ...), E1-log style: one table per WBS area, one row per stage (Schematic, Detailed
    design, IFC, Shop drawing ...) with its Submittals and Approvals counted apart, and a Total row.
    Actual follows the owner's E1 rule - an activity counts ONCE IT HAS STARTED (In Progress or
    Completed, or any progress recorded) - / activities; Planned = activities whose BASELINE finish is on or
    before the cut-off date / activities. Milestone activities are left out one by one, and a
    top-level WBS made mostly of milestones (Key Dates, Inputs Required From Client, Control
    Milestones ...) is left out as a whole. None when no activity is without cost."""
    nocost = [r for r in records if not (r.get('bac') or 0) > 0]
    if not nocost:
        return None
    wmap, bl_by_id = data.wbs, getattr(data, 'baseline_by_id', None) or {}
    dd = (getattr(data, 'project', None) or {}).get('data_date')
    path_cache = {}

    def names_of(r):
        wid = r['activity'].get('wbs_id')
        if wid not in path_cache:
            path_cache[wid] = [n for _, n in wbs_path(wid, wmap)] or ['(no WBS)']
        return path_cache[wid]

    # a main WBS whose activities are (almost) all cost loaded is measured by COST, not by count: its
    # Planned % / Actual % are the cost-loaded %, so it is left out of the count-based progress
    tot_top = {}
    for r in records:
        t = tot_top.setdefault(names_of(r)[0], [0, 0])
        t[0] += 1
        t[1] += 1 if (r.get('bac') or 0) > 0 else 0
    cost_wbs = sorted(k for k, (n, c) in tot_top.items() if n and c / n >= COST_LOADED_SHARE)
    nocost = [r for r in nocost if names_of(r)[0] not in cost_wbs]
    by_top = {}
    for r in nocost:
        t = by_top.setdefault(names_of(r)[0], [0, 0])
        t[0] += 1
        t[1] += 1 if r['activity'].get('task_type') in _MILESTONES else 0
    excluded_wbs = sorted(k for k, (n, m) in by_top.items() if n and m / n >= 0.3)
    kept = [r for r in nocost if names_of(r)[0] not in excluded_wbs]
    excluded_n = len(nocost) - len(kept)
    rows_in = [r for r in kept if r['activity'].get('task_type') not in _MILESTONES]
    ms_n = len(kept) - len(rows_in)

    def kind(names):
        low = ' '.join(names[1:3]).lower()
        return 'S' if 'submit' in low else ('A' if 'approv' in low else 'O')

    staged = {names_of(r)[0] for r in rows_in if kind(names_of(r)) in ('S', 'A')}

    def is_type_name(n):
        return any(w in (n or '').lower() for w in ('submit', 'approv'))
    # some stages end in a WBS that is only called 'Submittal' / 'Approval' (no area name): such a
    # row belongs to the area its branch is named after most often
    area_votes = {}
    for r in rows_in:
        nm = names_of(r)
        if nm[0] in staged and len(nm) > 3 and not is_type_name(nm[3]):
            area_votes.setdefault(nm[0], {}).setdefault(nm[3], 0)
            area_votes[nm[0]][nm[3]] += 1

    def where(r):
        names = names_of(r)
        top = names[0]
        if top not in staged or len(names) < 3:
            # one table per main WBS: a main WBS's dashboard counts its OWN activities only (owner)
            return 'Other activities — %s' % top, ' › '.join(names[:2])
        stage = _STAGE_ALIAS.get(names[1], names[1])
        if stage == 'As-Built':
            return 'As-Built — per area', (names[3] if len(names) > 3 else names[-1])
        area = names[3] if len(names) > 3 else names[2]
        if is_type_name(area) and area_votes.get(top):
            area = max(area_votes[top], key=area_votes[top].get)
        group = 'Phase I Design + Engineering' if top in ('Phase I Design', 'Phase I Engineering') else top
        return '%s — %s' % (area, group), stage

    def counter():
        # st/sd/sdue = Submittal activities: total / started / planned till the cut-off date;
        # at/ad/adue = Approvals; ot/os/odue = the others (PO, delivery ...). n/started/due = all.
        return {'n': 0, 'sd': 0, 'st': 0, 'sdue': 0, 'ad': 0, 'at': 0, 'adue': 0, 'ot': 0, 'os': 0, 'odue': 0,
                'done': 0, 'prog': 0, 'ns': 0, 'started': 0, 'due': 0, 'due_prog': 0, 'due_ns': 0}
    tabs, total, branches = {}, counter(), {}
    for r in rows_in:
        a = r['activity']
        title, row = where(r)
        branches.setdefault(title, set()).add(names_of(r)[0])        # the main WBS branch(es) a table belongs to
        st = activity_status(a)
        bl = bl_by_id.get(a.get('id')) or {}
        ps, pf = bl.get('planned_start') or a.get('planned_start'), bl.get('planned_finish') or a.get('planned_finish')
        due = 'ns'
        try:
            if dd is not None and ps is not None and pf is not None:
                due = 'd' if pf <= dd else ('p' if ps <= dd else 'ns')
        except TypeError:
            pass
        k = kind(names_of(r))
        started = st in ('Completed', 'In Progress') or (a.get('percent_complete') or 0) > 0
        for c in (tabs.setdefault(title, {}).setdefault(row, counter()), total):
            c['n'] += 1
            c['done' if st == 'Completed' else 'prog' if st == 'In Progress' else 'ns'] += 1
            c['started'] += 1 if started else 0
            c['due' if due == 'd' else 'due_prog' if due == 'p' else 'due_ns'] += 1
            if k == 'S':
                c['st'] += 1
                c['sd'] += 1 if started else 0
                c['sdue'] += 1 if due == 'd' else 0
            elif k == 'A':
                c['at'] += 1
                c['ad'] += 1 if started else 0
                c['adue'] += 1 if due == 'd' else 0
            else:
                c['ot'] += 1
                c['os'] += 1 if started else 0
                c['odue'] += 1 if due == 'd' else 0

    def fin(label, c):
        n = c['n']
        out = dict(c, label=label)
        out['actual_pct'] = round(100.0 * c['started'] / n, 1) if n else None
        out['planned_pct'] = round(100.0 * c['due'] / n, 1) if n else None
        out['behind'] = max(0, c['due'] - c['started'])
        return out

    def title_key(t):
        return (0 if t.startswith('MCC') else 1 if t.startswith('Silos') else 2 if t.startswith(('Buildings', 'Infra')) else
                3 if t.startswith('As-Built') else 4 if 'Procurement' in t else 5 if t.startswith('Other') else 2, t)
    tables = []
    for t in sorted(tabs, key=title_key):
        rows = tabs[t]
        keys = sorted(rows, key=lambda k: (_row_rank(k), k))
        tt = counter()
        for c in rows.values():
            for k2 in tt:
                tt[k2] += c[k2]
        tables.append({'title': t, 'branches': sorted(branches.get(t, ())), 'first': 'Area' if t.startswith('As-Built') else ('WBS' if t.startswith('Other') else 'Stage'),
                       'rows': [fin(k, rows[k]) for k in keys], 'total': fin('Total — ' + t.split(' — ')[0], tt)})
    head = fin('All activities without cost', total)
    head.update({'share': round(100.0 * total['n'] / len(records), 1) if records else None,
                 'cost_loaded_wbs': cost_wbs, 'excluded_wbs': excluded_wbs, 'excluded_activities': excluded_n, 'milestones_excluded': ms_n})
    return {'summary': head, 'tables': tables}


def build_views(records, data):
    """Everything stored for the re-open path: {'activities', 'wbs_summary', 'wbs_main',
    'cost_loaded', 'progress_groups'}."""
    summary, main = wbs_views(records, data)
    return {'activities': gantt_activities(records, data.wbs, data), 'wbs_summary': summary, 'wbs_main': main,
            'wbs_critical': wbs_views(critical_records(records), data)[0],
            'cost_loaded': cost_loaded_overview(records), 'progress_groups': progress_groups(records, data),
            'uncosted': uncosted_progress(records, data)}
