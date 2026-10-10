"""In-tool forward-pass scheduler — the but-for finish date WITHOUT F9.

Retained-logic CPM: each activity's early start/finish is computed from the logic, honouring
actuals, the data date, calendars and relationship types/lags; the project finish is the
latest early finish. Used to estimate the corrected (but-for) finish instantly, so the delay
analysis no longer requires the user to F9 the corrected file in P6. Validated against P6's
own scheduled dates (forward-passing an already-F9'd update must reproduce its finish).

Durations/lags are counted in whole working days on the activity's calendar — enough for a
finish-date estimate within a day or two of Primavera. Nothing here changes an EVM number.
"""
from datetime import datetime, timedelta
from collections import deque
from p6_audit.graph import ScheduleGraph


def _day_hours(cal):
    dh = getattr(cal, 'day_hours', 0.0) if cal else 0.0
    return dh if dh and dh > 0 else 8.0


def _later(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b


def _intervals(cal, d):
    """[(start_dt, end_dt)] of working time on date ``d`` — the calendar's intraday work times
    (holidays / exceptions included); a whole-day calendar without intervals works 08:00 + day_hours."""
    base = datetime(d.year, d.month, d.day)
    if cal.has_intraday():
        return [(base + timedelta(minutes=sm), base + timedelta(minutes=em)) for sm, em in cal._intervals_for(d)]
    if not cal.is_working_day(d):
        return []
    return [(base + timedelta(hours=8), base + timedelta(hours=8 + _day_hours(cal)))]


_MAX_DAYS = 3660                                  # never walk more than ~10 years for one step


def _minute(t):
    """P6 keeps times to the minute — drop the seconds that hour arithmetic leaves behind."""
    if t is None:
        return None
    return (t + timedelta(seconds=30)).replace(second=0, microsecond=0)


def _snap(cal, t):
    """The first working moment at or after ``t`` (P6 starts remaining work there)."""
    if cal is None or t is None:
        return t
    d = t.date()
    for _ in range(_MAX_DAYS):
        for a, b in _intervals(cal, d):
            if t < b:
                return max(a, t)
        d += timedelta(days=1)
        t = max(t, datetime(d.year, d.month, d.day))
    return t


def _snap_back(cal, t):
    """The last working moment at or before ``t`` — a finish that lands outside working time
    (e.g. an FF lag ending at the next morning's start) is the close of the last work period
    before it: P6 shows 16:00 the day before, not 08:00 (comment 44, Grain Bulk / MAFI)."""
    if cal is None or t is None:
        return t
    d = t.date()
    for _ in range(_MAX_DAYS):
        for a, b in reversed(_intervals(cal, d)):
            if a < t:                         # a period's opening moment holds no work yet
                return min(b, t)
        d -= timedelta(days=1)
        t = min(t, datetime(d.year, d.month, d.day) + timedelta(days=1))
    return t


def _at_work(cal, t):
    """True when ``t`` lies in a work period of ``cal`` or exactly at its close."""
    if cal is None or t is None:
        return True
    return any(a <= t <= b for a, b in _intervals(cal, t.date()))


def _add(cal, start, hours):
    """``start`` moved by ``hours`` of WORKING time on ``cal`` (negative = backward). A move that
    ends exactly at the end of a work period stays there (P6 finishes at 16:00, not next 08:00).
    No calendar: calendar time, 8 working hours = 1 day (the hand-computable test schedules)."""
    if start is None:
        return None
    if cal is None:
        return start + timedelta(days=(hours or 0.0) / 8.0)
    mins = round((hours or 0.0) * 60.0, 6)
    if mins == 0:
        return start
    t = start
    if mins > 0:
        d = t.date()
        for _ in range(_MAX_DAYS):
            for a, b in _intervals(cal, d):
                if b <= t:
                    continue
                lo = max(a, t)
                room = (b - lo).total_seconds() / 60.0
                if mins <= room + 1e-9:
                    return lo + timedelta(minutes=mins)
                mins -= room
                t = b
            d += timedelta(days=1)
        return t
    mins = -mins
    d = t.date()
    for _ in range(_MAX_DAYS):
        for a, b in reversed(_intervals(cal, d)):
            if a >= t:
                continue
            hi = min(b, t)
            room = (hi - a).total_seconds() / 60.0
            if mins <= room + 1e-9:
                return hi - timedelta(minutes=mins)
            mins -= room
            t = a
        d -= timedelta(days=1)
    return t


def _advance(cal, start, days):
    """`start` advanced by `days` working days (kept for callers outside the forward pass)."""
    return _add(cal, start, (days or 0.0) * _day_hours(cal))


def _topo_order(graph, skip_from=None):
    """Kahn topological order; any activities trapped in a cycle are appended at the end.
    ``skip_from``: predecessors whose links do not drive (Level of Effort / WBS summary) — their
    links are left out of the order too, so a 'loop' that only closes through an LOE (P6 does
    not schedule it as one) never puts a predecessor after its successor (Alstom update)."""
    skip_from = skip_from or set()
    indeg = {oid: 0 for oid in graph.activities}
    for oid in graph.activities:
        for link in graph.preds_of(oid):
            if link['other'] in indeg and link['other'] not in skip_from:
                indeg[oid] += 1
    q = deque(oid for oid, d in indeg.items() if d == 0)
    order, seen = [], set()
    while q:
        oid = q.popleft()
        order.append(oid); seen.add(oid)
        if oid in skip_from:
            continue
        for link in graph.succs_of(oid):
            s = link['other']
            if s in indeg:
                indeg[s] -= 1
                if indeg[s] == 0:
                    q.append(s)
    if len(order) < len(indeg):
        order += [oid for oid in graph.activities if oid not in seen]
    return order


_NO_DRIVE = ('LOE', 'WBSSummary')                                    # never drive their successors in P6
_SNET = ('Start On', 'Start On or After', 'Mandatory Start')        # forward pass: start no earlier than
_FNET = ('Finish On', 'Finish On or After', 'Mandatory Finish')     # forward pass: finish no earlier than


def forward_pass(data, data_date=None, keep=None, starts=None):
    """{oid: early_finish} for every activity — retained logic, in WORKING TIME as P6 schedules:
    remaining work starts at the first working moment after the data date / its predecessors,
    durations and lags are counted in working hours on the activity's calendar and the lag on
    the relationship's lag calendar (the project's 'Calendar for scheduling Relationship Lag'),
    FF / SF links also hold the start back, start / finish constraints are honoured.  Forward-
    passing an already-F9'd update reproduces P6's early finishes (final P6 test, comment 44).

    ``keep``: activities (ObjectIds) whose dates are P6's own, as the file holds them — the ones
    a but-for change does not reach. P6 may have set them by resource leveling or before a later
    calendar edit; either way they are what P6 shows, so they are kept, not recomputed."""
    graph = ScheduleGraph(data)
    acts, cals = graph.activities, graph.calendars
    dd = data_date or (getattr(data, 'project', None) or {}).get('data_date')
    preds = {}
    for r in getattr(data, 'relationships', None) or []:
        if r.get('pred_id') in acts and r.get('succ_id') in acts:
            preds.setdefault(r['succ_id'], []).append(r)
    proj = getattr(data, 'project', None) or {}
    twenty_four = (proj.get('lag_calendar') == '24h')
    ss_from_early = proj.get('ss_lag_from_early_start', True)
    es, ef, rs = {}, {}, {}                    # rs = remaining early start (where remaining work begins)
    no_drive = {oid for oid, a in acts.items() if a.get('task_type') in _NO_DRIVE}
    for oid in _topo_order(graph, no_drive):
        act = acts.get(oid) or {}
        cal = cals.get(act.get('calendar_id'))
        if keep and oid in keep and (act.get('actual_finish') or act.get('remaining_early_finish')):
            es[oid] = act.get('actual_start') or act.get('remaining_early_start') or act.get('planned_start')
            rs[oid] = act.get('remaining_early_start') or es[oid]
            ef[oid] = act.get('actual_finish') or act.get('remaining_early_finish')
            continue
        af = act.get('actual_finish')
        if af:                                    # completed — dates are actuals
            es[oid] = rs[oid] = act.get('actual_start') or af
            ef[oid] = af
            continue
        rem_h = act.get('remaining_duration') or 0.0
        a_start = act.get('actual_start')
        start_c, finish_c = dd, None
        for r in preds.get(oid, []):
            p = r['pred_id']
            if p not in ef or acts[p].get('task_type') in _NO_DRIVE:
                continue                          # a Level of Effort / WBS summary never drives (as P6)
            t = r.get('type', 'FS')
            lag_h = r.get('lag_hours')
            if lag_h is None:
                lag_h = (r.get('lag_days', 0.0) or 0.0) * 8.0
            lcal = None if twenty_four else (cals.get(r.get('lag_calendar_id')) or
                                             cals.get(acts[p].get('calendar_id')) or cal)
            if twenty_four:
                lagged = lambda x: x + timedelta(hours=lag_h) if x else x
            else:
                lagged = lambda x: _add(lcal, x, lag_h)
            # A start link (SS / SF) from a predecessor that has started — P6 with 'SS lag from early
            # start' (seen on MAFI, Alstom, Grain Bulk and Saint Gobain, baselines and updates):
            p_as, p_af = acts[p].get('actual_start'), acts[p].get('actual_finish')
            if t in ('SS', 'SF') and p_as and p_af:
                start_anchor = lagged(p_as)                     # finished: the full lag from its start
            elif t in ('SS', 'SF') and p_as and ss_from_early and not twenty_four and lcal is not None and dd:
                # in progress: the lag already elapsed at the data date is used up; the rest runs
                # from the predecessor's remaining early start
                used = lcal.working_minutes(p_as, dd) / 60.0 if lcal.has_intraday() else 0.0
                start_anchor = _add(lcal, rs[p], max(0.0, lag_h - used))
            elif t in ('SS', 'SF'):
                start_anchor = lagged(rs[p] if ss_from_early else es[p])
            if t == 'FS':
                start_c = _later(start_c, lagged(ef[p]))
            elif t == 'SS':
                start_c = _later(start_c, start_anchor)
            elif t == 'FF':
                finish_c = _later(finish_c, lagged(ef[p]))
            elif t == 'SF':
                finish_c = _later(finish_c, start_anchor)
        ctype, cdate = act.get('constraint_type'), act.get('constraint_date')
        if not a_start and cdate and ctype in _SNET:
            start_c = _later(start_c, cdate)
        if cdate and ctype in _FNET:
            finish_c = _later(finish_c, cdate)
        s = _later(dd, start_c) if a_start else (start_c or dd)
        if s is None:
            s = act.get('remaining_early_start') or act.get('planned_start')
        finish_ms = act.get('task_type') == 'FinishMilestone'
        # remaining work begins at the next working moment; a finish milestone keeps its
        # predecessor's finish time when that is working time (or a day's close) on its OWN
        # calendar, else it too moves to the next working moment (Alstom: a holiday on its calendar)
        if finish_c is not None:                  # FF / SF / finish constraint holds the start back
            s = _later(s, _add(cal, finish_c, -rem_h))
        if not finish_ms or not _at_work(cal, s):
            s = _snap(cal, s)
        e = _add(cal, s, rem_h)
        if finish_c is not None and (e is None or finish_c > e):
            if finish_ms:
                e = finish_c if _at_work(cal, finish_c) else _snap(cal, finish_c)
            else:
                e = max(e, _snap_back(cal, finish_c)) if e is not None else _snap_back(cal, finish_c)
        es[oid] = a_start or _minute(s)
        rs[oid] = _minute(s)
        ef[oid] = _minute(e)
    if starts is not None:                      # the caller also wants the early starts
        starts.update(es)
    return ef


def project_finish(data, data_date=None, keep=None):
    """Forward-pass project finish datetime (latest early finish). None if undatable."""
    ef = forward_pass(data, data_date, keep)
    finishes = [v for v in ef.values() if v is not None]
    return max(finishes) if finishes else None


def but_for_finish(update, ops):
    """The but-for finish datetime: forward-pass the update with the revert ``ops`` applied
    in memory (baseline relationships / lags / durations restored) — no file written, no F9.
    Every op is applied to ALL copies of a code (duplicate-code exports). An estimate; label it."""
    import copy as _copy
    code_to_oids, oid_code = {}, {}
    for oid, a in update.activities.items():
        c = a.get('id')
        oid_code[oid] = c
        if c:
            code_to_oids.setdefault(c, []).append(oid)

    acts = {oid: dict(a) for oid, a in update.activities.items()}
    for op in ops:
        if op.get('kind') == 'set_duration':
            for oid in code_to_oids.get(op['activity_id'], []):
                acts[oid]['planned_duration'] = op['planned_hours']
                acts[oid]['remaining_duration'] = op['remaining_hours']

    from p6_compare.revert import relink
    op_by_pair = {(op['pred_code'], op['succ_code']): op for op in ops
                  if op.get('kind') in ('set_rel', 'remove_rel', 'add_rel')}
    rel_pair = lambda r: (oid_code.get(r.get('pred_id')), oid_code.get(r.get('succ_id')))
    types_of = {}
    for r in update.relationships:
        types_of.setdefault(rel_pair(r), []).append(r.get('type', 'FS'))
    relinked = {pair: relink(op, types_of.get(pair, [])) for pair, op in op_by_pair.items()
                if op['kind'] == 'set_rel'}
    out_rels, present, first = [], set(), {}
    for r in update.relationships:
        pair = rel_pair(r)
        op = op_by_pair.get(pair)
        if op and op['kind'] == 'remove_rel':
            continue                             # drop every copy of an added link
        nr = dict(r)
        if op and op['kind'] == 'set_rel':       # each link back to its baseline type / lag
            m = relinked[pair][0].get(r.get('type', 'FS'))
            if m is None:
                continue
            nr['type'], nr['lag_hours'] = m[0], m[1]
            nr['lag_days'] = m[1] / 8.0
        out_rels.append(nr)
        present.add(pair)
        first.setdefault(pair, r)
    for pair, (_m, missing) in relinked.items():  # a baseline link of the pair the update dropped
        for t, h in missing:
            if pair in first:
                out_rels.append(dict(first[pair], type=t, lag_hours=h, lag_days=h / 8.0))
    for op in ops:                               # restore removed baseline links
        if op['kind'] == 'add_rel' and (op['pred_code'], op['succ_code']) not in present:
            po, so = code_to_oids.get(op['pred_code']), code_to_oids.get(op['succ_code'])
            if po and so:
                for t, h in (op.get('links') or [(op['type'], op['lag_hours'])]):
                    out_rels.append({'pred_id': po[0], 'succ_id': so[0], 'type': t,
                                     'lag_hours': h, 'lag_days': h / 8.0})

    corrected = _copy.copy(update)
    corrected.activities = acts
    corrected.relationships = out_rels
    return project_finish(corrected, keep=unreached(corrected, ops, update.relationships))


def unreached(data, ops, old_relationships=()):
    """ObjectIds the revert ``ops`` cannot move: everything except the activities an op names
    (a reverted duration, the successor of a reverted link) and all their successors, through
    the corrected logic and the update's own. Those keep P6's dates as the file holds them, so
    with no change applied the but-for finish IS P6's finish (comment 44); a Level of Effort
    whose span touches a reached activity is reached too (it stretches between its neighbours)."""
    acts = data.activities
    by_code = {}
    for oid, a in acts.items():
        by_code.setdefault(a.get('id'), []).append(oid)
    seeds = set()
    for op in ops or []:
        code = op.get('activity_id') if op.get('kind') == 'set_duration' else op.get('succ_code')
        seeds.update(by_code.get(code, []))
    succs, preds_of = {}, {}
    for r in list(getattr(data, 'relationships', None) or []) + list(old_relationships or []):
        succs.setdefault(r.get('pred_id'), set()).add(r.get('succ_id'))
        preds_of.setdefault(r.get('succ_id'), set()).add(r.get('pred_id'))
    reached, stack = set(seeds), list(seeds)
    while stack:
        for n in succs.get(stack.pop(), ()):
            if n not in reached:
                reached.add(n)
                stack.append(n)
    for oid, a in acts.items():
        if a.get('task_type') in _NO_DRIVE and (succs.get(oid, set()) | preds_of.get(oid, set())) & reached:
            reached.add(oid)
    return set(acts) - reached
