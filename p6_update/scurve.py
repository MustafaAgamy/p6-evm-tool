"""Update Analysis · section 6 · Progress S-curve.

Ibrahim's rules (2026-11-23, Scope — Update Analysis Presentation + Progress S-curve):

- **Planned** = the Time Status Planned % rule (each activity's baseline dates, measured in
  its own calendar's working time by ``activity_planned_pct``, weighted by its budget — or
  by its planned duration when the file carries no cost at all), read at every month end
  and at the data date.
- **Earned** (up to the data date) = each activity's % complete spread over its actual
  start → actual finish (or the data date), in working time — "rebuilt". Where an earlier
  update of the same project was imported, its own Earned % stands at its data date
  (``merge_earlier``).
- **Forecast** (from the data date) = each activity's remaining work (100% − % complete)
  spread over its remaining early start → finish in this P6 file, in working time.

At the data date all three equal Time Status exactly: the point is summed from the very
same per-activity figures ``time_status`` sums. Nothing here touches ``p6_evm``.
"""
import calendar as _calendar
from datetime import datetime, timedelta

from p6_evm.metrics import activity_planned_pct


def _rows(metrics):
    """(weight, record) pairs — the same population and weights as time_status."""
    recs = (metrics or {}).get('records') or []
    cost_loaded = any((r.get('bac') or 0.0) > 0 for r in recs)
    rows = []
    for r in recs:
        if cost_loaded:
            w = r.get('bac') or 0.0
            if w <= 0:
                continue
        else:
            w = (r['activity'].get('planned_duration') or 0.0) or 1.0
        rows.append((w, r))
    return rows, cost_loaded


def earned_pct(metrics):
    """The Time Status Earned % (Earned Value ÷ Budget), 2 decimals — stored with every
    import so a later update can put this one on its S-curve without re-reading it."""
    rows, _ = _rows(metrics)
    tot = sum(w for w, _ in rows)
    if not tot:
        return None
    return round(100.0 * sum(w * (r.get('actual_pct') or 0.0) for w, r in rows) / tot, 2)


def _iso(d):
    return d.strftime('%Y-%m-%d') if d else None


def _month_ends(d0, d1):
    out = []
    y, m = d0.year, d0.month
    while True:
        end = datetime(y, m, _calendar.monthrange(y, m)[1], 23, 59)
        out.append(end)
        if end >= d1:
            return out
        m += 1
        if m > 12:
            y, m = y + 1, 1


def progress_scurve(data, metrics):
    """{'points': [{date, kind ('month' | 'data_date' | 'update'), planned, earned,
    earned_source ('rebuilt' | 'this update' | 'update' | None), forecast}],
    'basis': 'cost' | 'duration', 'last_remaining_finish', 'earlier': []}.
    Empty points when the file has no data date or nothing to weigh."""
    empty = {'points': [], 'basis': None, 'last_remaining_finish': None, 'earlier': []}
    dd = (getattr(data, 'project', None) or {}).get('data_date')
    rows, cost_loaded = _rows(metrics)
    if not dd or not rows:
        return empty
    cals = getattr(data, 'calendars', {}) or {}
    bl = getattr(data, 'baseline_by_id', None) or {}
    tot_w = sum(w for w, _ in rows)
    p_rows = [(w, r) for w, r in rows if r.get('planned_pct') is not None]
    p_w = sum(w for w, _ in p_rows)

    def frac(act, start, finish, t):
        """Share (0..1) of [start, finish] passed by t, in the activity's working time."""
        if not start:
            return 0.0
        finish = finish or start
        return activity_planned_pct(act, {act['id']: {'planned_start': start, 'planned_finish': finish}},
                                    t, cals) or 0.0

    rem_fins = [r['activity'].get('remaining_early_finish') for _, r in rows
                if r['activity'].get('remaining_early_finish')]
    last_rem = max(rem_fins) if rem_fins else None

    def planned_at(t):
        if not p_w:
            return None
        return 100.0 * sum(w * (activity_planned_pct(r['activity'], bl, t, cals) or 0.0)
                           for w, r in p_rows) / p_w

    def earned_at(t):
        v = 0.0
        for w, r in rows:
            a, pc = r['activity'], r.get('actual_pct') or 0.0
            if pc > 0 and a.get('actual_start'):
                v += w * pc * frac(a, a['actual_start'], a.get('actual_finish') or dd, t)
        return 100.0 * v / tot_w

    def forecast_at(t):
        v = 0.0
        for w, r in rows:
            a, pc = r['activity'], r.get('actual_pct') or 0.0
            rem = 1.0 - pc
            if rem > 0:
                fin = a.get('remaining_early_finish') or last_rem      # work left with no date
                start = max(a.get('remaining_early_start') or dd, dd)  # finishes with the project
                pc += rem * (frac(a, start, max(fin, start), t) if fin else 0.0)
            v += w * pc
        return 100.0 * v / tot_w

    starts = [b['planned_start'] for b in bl.values() if b.get('planned_start')]
    starts += [r['activity']['actual_start'] for _, r in rows if r['activity'].get('actual_start')]
    ends = [b['planned_finish'] for b in bl.values() if b.get('planned_finish')] + rem_fins + [dd]
    if not starts:
        return empty
    d0, d1 = min(starts + [dd]), max(ends)
    points = []
    for t in _month_ends(d0, d1):
        if t.date() == dd.date():
            continue                                   # the data-date point stands for that day
        past = t < dd
        pl = planned_at(t)
        points.append({'date': _iso(t), 'kind': 'month',
                       'planned': round(pl, 2) if pl is not None else None,
                       'earned': round(earned_at(t), 2) if past else None,
                       'earned_source': 'rebuilt' if past else None,
                       'forecast': None if past else round(forecast_at(t), 2)})
    # the data-date point: summed from the same per-activity figures as time_status
    now_p = (round(100.0 * sum(w * r['planned_pct'] for w, r in p_rows) / p_w, 2) if p_w else None)
    now_e = round(100.0 * sum(w * (r.get('actual_pct') or 0.0) for w, r in rows) / tot_w, 2)
    points.append({'date': _iso(dd), 'kind': 'data_date', 'planned': now_p, 'earned': now_e,
                   'earned_source': 'this update', 'forecast': now_e})
    points.sort(key=lambda p: (p['date'], p['kind'] != 'data_date'))
    return {'points': points, 'basis': 'cost' if cost_loaded else 'duration',
            'last_remaining_finish': _iso(last_rem), 'earlier': []}


def merge_earlier(scurve, earlier):
    """Put every ticked earlier update (``on``) on the Earned line at its own data date —
    before this update's data date only. ``scurve`` may already be merged: the rebuilt
    points are kept in ``base_points`` so ticking / unticking re-merges from them."""
    scurve = dict(scurve or {})
    base = scurve.get('base_points') or scurve.get('points') or []
    dd = next((p['date'] for p in base if p['kind'] == 'data_date'), None)
    pts = [dict(p) for p in base]
    on = sorted((e for e in (earlier or []) if e.get('on') and e.get('earned') is not None
                 and dd and str(e.get('data_date'))[:10] < dd), key=lambda e: str(e['data_date'])[:10])
    for e in on:
        d = str(e['data_date'])[:10]
        same = next((p for p in pts if p['date'] == d and p['kind'] == 'month'), None)
        if same:                                       # an update on a month end replaces the rebuilt value
            same.update(kind='update', earned=round(float(e['earned']), 2), earned_source='update',
                        snapshot_id=e.get('snapshot_id'))
            continue
        pts.append({'date': d, 'kind': 'update', 'planned': None, 'earned': round(float(e['earned']), 2),
                    'earned_source': 'update', 'forecast': None, 'snapshot_id': e.get('snapshot_id')})
    pts.sort(key=lambda p: (p['date'], p['kind'] != 'data_date'))
    scurve.update(points=pts, base_points=base, earlier=list(earlier or []))
    return scurve


def baseline_key(data):
    """Which baseline this update is measured against — '<baseline name>|<its data date>' —
    so later updates of the same job find this one (P6 gives every update its own project
    ID, so the ID can't link them). None when the file is read against its own dates."""
    src = getattr(data, 'baseline_source', None)
    if src not in ('embedded', 'attached'):
        return None
    info = getattr(data, 'baseline_info', None) or {}
    name = (info.get('embedded_name') if src == 'embedded' else info.get('name')) \
        or (getattr(data, 'project', None) or {}).get('baseline_name')
    bdd = getattr(data, 'baseline_data_date', None)
    if not name or not bdd:
        return None
    return f"{str(name).strip()}|{bdd.strftime('%Y-%m-%d') if hasattr(bdd, 'strftime') else str(bdd)[:10]}"


def earlier_on(candidates, key, picks):
    """Tick the earlier updates: same baseline (auto) unless removed, plus any added by hand."""
    picks = picks or {}
    add = {int(x) for x in picks.get('add') or []}
    rem = {int(x) for x in picks.get('remove') or []}
    out = []
    for c in candidates or []:
        c = dict(c)
        c['auto'] = bool(key) and c.get('baseline_key') == key
        sid = int(c['snapshot_id'])
        c['on'] = c.get('earned') is not None and ((c['auto'] and sid not in rem) or sid in add)
        out.append(c)
    return out


def attach_earlier(scurve, data_date, snapshot_id, key, after, picks=None):
    """Section 6: tick the earlier imported updates (same baseline, plus the planner's own
    picks saved for this snapshot) and put them on the Earned line. Read from the history
    DB only — no schedule is re-read. Used by the screen and by Reporting Studio alike."""
    import db
    scurve = dict(scurve or {})
    scurve['baseline_key'] = key
    scurve['baseline_data_date'] = after
    if not scurve.get('points') or not data_date:
        return scurve
    if picks is None and snapshot_id:
        try:
            picks = db.get_snapshot_ui_state(int(snapshot_id), 'ua_scurve_earlier')
        except Exception:
            picks = None
    cands = db.earlier_update_candidates(data_date, exclude_snapshot_id=snapshot_id, after=after)
    return merge_earlier(scurve, earlier_on(cands, key, picks))


def report_with_earlier(report, data, snapshot_id):
    """``report['scurve']`` with the earlier updates on it (never raises)."""
    try:
        bdd = getattr(data, 'baseline_data_date', None)
        report['scurve'] = attach_earlier(
            report.get('scurve'), report.get('data_date'), snapshot_id, baseline_key(data),
            bdd.strftime('%Y-%m-%d') if hasattr(bdd, 'strftime') else None)
    except Exception as exc:                      # pragma: no cover - defensive
        import sys
        print(f'[scurve] earlier updates skipped: {exc}', file=sys.stderr)
    return report
