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


def _iso(x):
    return x.isoformat() if hasattr(x, 'isoformat') else (str(x) if x else None)


def _iso_day(x):
    return x.date().isoformat() if hasattr(x, 'date') else (str(x)[:10] if x else None)


def current_start(a):
    """P6 'Start': Actual Start once started, else the remaining early start, else Planned."""
    return a.get('actual_start') or a.get('remaining_early_start') or a.get('planned_start')


def current_finish(a):
    """P6 'Finish': Actual Finish once finished, else the remaining early finish, else Planned."""
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


def working_delay(cal, baseline_finish, finish):
    """Delay in WORKING days on `cal`, finish against baseline finish (+ late / − early), the
    way P6 works out its finish variance: the working HOURS between the two dates on the
    calendar's own work times, divided by the calendar's hours per day, shown to the whole day.
    A calendar with no work times falls back to counting whole working days. None when a date
    or the calendar is missing."""
    if cal is None or baseline_finish is None or finish is None:
        return None
    try:
        from p6_evm.calendars import float_working_days, signed_working_minutes
        hours = float(getattr(cal, 'day_hours', 0) or 0)
        if hours > 0 and callable(getattr(cal, 'has_intraday', None)) and cal.has_intraday():
            mins = signed_working_minutes(cal, baseline_finish, finish)
            if mins is not None:
                days = mins / (hours * 60.0)
                return int(days + 0.5) if days >= 0 else -int(-days + 0.5)
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


def float_delay(tf):
    """The Delay figure = the Total Float in days exactly as P6 shows it, to the whole day:
    a float of -72 d is a delay of -72 (late is NEGATIVE, spare float positive)."""
    if not isinstance(tf, (int, float)):
        return None
    d = tf
    return int(d + 0.5) if d >= 0 else -int(-d + 0.5)


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
    for r in records:
        a = r['activity']
        s, f = current_start(a), current_finish(a)
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
        bf = bl.get('planned_finish') if bl else None
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
                'ef': None, 'lf': None, 'open': 0, 'all': 0, 'b': 0.0, 'pv': 0.0, 'ev': 0.0, 'ps': None, 'pf': None}

    bl_by_id = getattr(data, 'baseline_by_id', None) or {}
    direct = defaultdict(base)
    for r in records:
        a = r['activity']
        wid = a.get('wbs_id')
        if wid is None:
            continue
        d = direct[wid]
        d['s'] = _mn(d['s'], current_start(a))          # current schedule (expected)
        d['f'] = _mx(d['f'], current_finish(a))
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
            d['bs'] = _mn(d['bs'], bl.get('planned_start'))
            d['bf'] = _mx(d['bf'], bl.get('planned_finish'))
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
            t['s'] = _mn(t['s'], c['s']); t['f'] = _mx(t['f'], c['f'])
            t['ef'] = _mx(t['ef'], c['ef']); t['lf'] = _mx(t['lf'], c['lf']); t['open'] += c['open']
            t['all'] += c['all']; t['b'] += c['b']; t['pv'] += c['pv']; t['ev'] += c['ev']
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
    return wbs_summary, wbs_main


def build_views(records, data):
    """Everything stored for the re-open path: {'activities', 'wbs_summary', 'wbs_main',
    'cost_loaded', 'progress_groups'}."""
    summary, main = wbs_views(records, data)
    return {'activities': gantt_activities(records, data.wbs, data), 'wbs_summary': summary, 'wbs_main': main,
            'wbs_critical': wbs_views(critical_records(records), data)[0],
            'cost_loaded': cost_loaded_overview(records), 'progress_groups': progress_groups(records, data)}
