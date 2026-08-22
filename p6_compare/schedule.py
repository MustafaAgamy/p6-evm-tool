"""In-tool forward-pass scheduler — the but-for finish date WITHOUT F9.

Retained-logic CPM: each activity's early start/finish is computed from the logic, honouring
actuals, the data date, calendars and relationship types/lags; the project finish is the
latest early finish. Used to estimate the corrected (but-for) finish instantly, so the delay
analysis no longer requires the user to F9 the corrected file in P6. Validated against P6's
own scheduled dates (forward-passing an already-F9'd update must reproduce its finish).

Durations/lags are counted in whole working days on the activity's calendar — enough for a
finish-date estimate within a day or two of Primavera. Nothing here changes an EVM number.
"""
from datetime import timedelta
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


def _advance(cal, start, days):
    """`start` advanced by `days` working days (fractional rounded to whole days); negative
    goes backward. Calendar days when there is no calendar."""
    if start is None:
        return None
    n = int(round(days))
    if n == 0:
        return start
    if cal is None:
        return start + timedelta(days=n)
    d, step, cnt = start, (1 if n > 0 else -1), 0
    while cnt < abs(n):
        d += timedelta(days=step)
        if cal.is_working_day(d.date()):
            cnt += 1
    return d


def _topo_order(graph):
    """Kahn topological order; any activities trapped in a cycle are appended at the end."""
    indeg = {oid: 0 for oid in graph.activities}
    for oid in graph.activities:
        for link in graph.preds_of(oid):
            if link['other'] in indeg:
                indeg[oid] += 1
    q = deque(oid for oid, d in indeg.items() if d == 0)
    order, seen = [], set()
    while q:
        oid = q.popleft()
        order.append(oid); seen.add(oid)
        for link in graph.succs_of(oid):
            s = link['other']
            if s in indeg:
                indeg[s] -= 1
                if indeg[s] == 0:
                    q.append(s)
    if len(order) < len(indeg):
        order += [oid for oid in graph.activities if oid not in seen]
    return order


def forward_pass(data, data_date=None):
    """{oid: early_finish} for every activity (retained logic). Also usable for the finish."""
    graph = ScheduleGraph(data)
    acts, cals = graph.activities, graph.calendars
    dd = data_date or (getattr(data, 'project', None) or {}).get('data_date')
    es, ef = {}, {}
    for oid in _topo_order(graph):
        act = acts.get(oid) or {}
        cal = cals.get(act.get('calendar_id'))
        af = act.get('actual_finish')
        if af:                                    # completed — dates are actuals
            es[oid] = act.get('actual_start') or af
            ef[oid] = af
            continue
        rem_days = (act.get('remaining_duration') or 0.0) / _day_hours(cal)
        start_c, ef_c = dd, None
        for link in graph.preds_of(oid):
            p = link['other']
            if p not in ef:
                continue
            t, lag = link.get('type', 'FS'), (link.get('lag_days', 0.0) or 0.0)
            if t == 'FS':
                start_c = _later(start_c, _advance(cal, ef[p], lag))
            elif t == 'SS':
                start_c = _later(start_c, _advance(cal, es[p], lag))
            elif t == 'FF':
                ef_c = _later(ef_c, _advance(cal, ef[p], lag))
            elif t == 'SF':
                ef_c = _later(ef_c, _advance(cal, es[p], lag))
        a_start = act.get('actual_start')
        s = _later(dd, start_c) if a_start else (start_c or dd)
        if s is None:
            s = act.get('remaining_early_start') or act.get('planned_start')
        e = _advance(cal, s, rem_days)
        if ef_c and (e is None or ef_c > e):     # FF/SF pushes the finish
            e = ef_c
        es[oid] = a_start or s
        ef[oid] = e
    return ef


def project_finish(data, data_date=None):
    """Forward-pass project finish datetime (latest early finish). None if undatable."""
    ef = forward_pass(data, data_date)
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

    op_by_pair = {(op['pred_code'], op['succ_code']): op for op in ops
                  if op.get('kind') in ('set_rel', 'remove_rel', 'add_rel')}
    out_rels, present = [], set()
    for r in update.relationships:
        pair = (oid_code.get(r.get('pred_id')), oid_code.get(r.get('succ_id')))
        op = op_by_pair.get(pair)
        if op and op['kind'] == 'remove_rel':
            continue                             # drop every copy of an added link
        nr = dict(r)
        if op and op['kind'] == 'set_rel':       # revert type/lag on every copy
            nr['type'] = op['type']
            nr['lag_hours'] = op['lag_hours']
            nr['lag_days'] = op['lag_hours'] / 8.0
        out_rels.append(nr)
        present.add(pair)
    for op in ops:                               # restore removed baseline links
        if op['kind'] == 'add_rel' and (op['pred_code'], op['succ_code']) not in present:
            po, so = code_to_oids.get(op['pred_code']), code_to_oids.get(op['succ_code'])
            if po and so:
                out_rels.append({'pred_id': po[0], 'succ_id': so[0], 'type': op['type'],
                                 'lag_hours': op['lag_hours'], 'lag_days': op['lag_hours'] / 8.0})

    corrected = _copy.copy(update)
    corrected.activities = acts
    corrected.relationships = out_rels
    return project_finish(corrected)
