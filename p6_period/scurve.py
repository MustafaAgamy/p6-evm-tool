"""Period S-curve — actual to date vs the previous update's forecast.

Two curves on a shared monthly axis:
- forecast: the PREVIOUS update's own scheduled profile, full (runs to ~100%). Each
  activity spreads its duration-weight linearly across its forecast span (remaining
  early dates, falling back to planned). "Where last period said you'd be."
- actual: a ramp through the known actual readings (0 at project start -> actual_prev
  at the previous data date -> actual_now at the current data date), then None after
  now. We don't store a historical earned curve, so between readings it's linear.

A progress *profile* (a visual). The exact numbers live in the dashboard.
"""
from datetime import datetime


def _fspan(act):
    """Forecast span: remaining early dates first (the forecast), then planned."""
    s = act.get('remaining_early_start') or act.get('planned_start')
    f = act.get('remaining_early_finish') or act.get('planned_finish')
    return s, f


def _weighted_spans(data):
    out = []
    for act in getattr(data, 'activities', {}).values():
        s, f = _fspan(act)
        if s and f and f > s:
            out.append((s, f, (act.get('planned_duration') or 0.0) or 1.0))
    return out


def _month_boundaries(dmin, dmax):
    y, m = dmin.year, dmin.month
    out = []
    for _ in range(1200):
        out.append(datetime(y, m, 1))
        if y > dmax.year or (y == dmax.year and m > dmax.month):
            break
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def cumulative_pct(data, boundaries):
    """Cumulative scheduled % complete at each boundary datetime (0-100, rounded 0.1)."""
    spans = _weighted_spans(data)
    total = sum(w for _, _, w in spans) or 1.0
    out = []
    for t in boundaries:
        done = 0.0
        for s, f, w in spans:
            if t >= f:
                done += w
            elif t > s:
                done += w * (t - s).total_seconds() / (f - s).total_seconds()
        out.append(round(100.0 * done / total, 1))
    return out


def _floor_idx(boundaries, when):
    """Largest boundary index at or before `when` (0 if none/earlier)."""
    if not boundaries or not when:
        return 0
    bi = 0
    for i, b in enumerate(boundaries):
        if b <= when:
            bi = i
        else:
            break
    return bi


def _actual_ramp(n, prev_idx, now_idx, actual_prev, actual_now):
    """Actual earned ramp, interpolated across INDEX anchors (0,0) ->
    (prev_idx,actual_prev) -> (now_idx,actual_now); None strictly after now_idx.

    Index-anchored (not date-anchored) so the value AT the current-period column is
    exactly actual_now, regardless of where the data date falls within its month."""
    if n <= 0:
        return []
    anchors = [(0, 0.0)]
    if prev_idx > 0:
        anchors.append((prev_idx, actual_prev))
    anchors.append((max(now_idx, prev_idx), actual_now))
    out = []
    for i in range(n):
        if i > now_idx:
            out.append(None)
            continue
        v = anchors[0][1]
        for (i0, v0), (i1, v1) in zip(anchors, anchors[1:]):
            if i <= i0:
                v = v0
                break
            if i <= i1:
                v = v0 + (v1 - v0) * (i - i0) / ((i1 - i0) or 1)
                break
            v = v1
        out.append(round(v, 1))
    return out


def period_scurve(prev, curr, actual_prev=0.0, actual_now=0.0):
    """{'periods', 'forecast', 'actual', 'dd_prev_idx', 'dd_now_idx',
        'actual_prev', 'actual_now', 'forecast_now'}.

    forecast = the previous update's scheduled profile (to 100%); actual = the earned
    ramp, None after the current data date."""
    dd_prev = (getattr(prev, 'project', {}) or {}).get('data_date')
    dd_now = (getattr(curr, 'project', {}) or {}).get('data_date')
    dates = []
    for d in (prev, curr):
        for s, f, _ in _weighted_spans(d):
            dates += [s, f]
    for x in (dd_prev, dd_now):
        if x:
            dates.append(x)
    if not dates:
        return {'periods': [], 'forecast': [], 'actual': [], 'dd_prev_idx': 0,
                'dd_now_idx': 0, 'actual_prev': actual_prev, 'actual_now': actual_now,
                'forecast_now': None}
    boundaries = _month_boundaries(min(dates), max(dates))
    forecast = cumulative_pct(prev, boundaries)
    n = len(boundaries)
    dd_prev_idx = _floor_idx(boundaries, dd_prev)
    dd_now_idx = _floor_idx(boundaries, dd_now)
    return {
        'periods': [b.strftime('%b %y') for b in boundaries],
        'forecast': forecast,
        'actual': _actual_ramp(n, dd_prev_idx, dd_now_idx, actual_prev, actual_now),
        'dd_prev_idx': dd_prev_idx,
        'dd_now_idx': dd_now_idx,
        'actual_prev': actual_prev,
        'actual_now': actual_now,
        'forecast_now': forecast[dd_now_idx] if forecast else None,
    }
