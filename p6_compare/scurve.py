"""Three-way planned-progress S-curve for the Consultant Review.

Builds a cumulative planned-% curve for each of the baseline, the update (after the
changes) and the rescheduled corrected file (before the changes), on a shared monthly
axis. The gap between the before and after curves is the manufactured slip, made
visible.

Each activity spreads its duration-weight linearly between its planned start and
finish; the curve at a date is the weight-fraction scheduled complete by then. This
is a progress *profile* (a visual) — the exact delay numbers come from the finish
dates in the before/after impact, not from this curve.
"""
from datetime import datetime


def _span(act):
    s = act.get('planned_start') or act.get('remaining_early_start')
    f = act.get('planned_finish') or act.get('remaining_early_finish')
    return s, f


def _weighted_spans(data):
    """(start, finish, weight) for every TASK-dependent activity with a positive-length planned
    span. Task-dependent only (Ibrahim's rule, consistent with the change tables) so trailing
    milestones / LOE don't tail the curve past the construction finish."""
    out = []
    for act in getattr(data, 'activities', {}).values():
        if act.get('task_type') != 'Task':
            continue
        s, f = _span(act)
        if s and f and f > s:
            out.append((s, f, (act.get('planned_duration') or 0.0) or 1.0))
    return out


def _month_boundaries(dmin, dmax):
    """Month-start datetimes from dmin's month through one past dmax's month, so the
    last real month reaches ~100%."""
    y, m = dmin.year, dmin.month
    out = []
    # guard against a runaway loop on absurd inputs
    for _ in range(1200):
        out.append(datetime(y, m, 1))
        if y > dmax.year or (y == dmax.year and m > dmax.month):
            break
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def cumulative_pct(data, boundaries):
    """Cumulative planned % complete at each boundary datetime (0–100, rounded 0.1)."""
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


def three_way_scurve(baseline, update, corrected):
    """{'periods': ['Dec 25', ...], 'baseline': [...], 'before': [...], 'after': [...]}.

    'before' is the rescheduled corrected file, 'after' is the current update. Empty
    lists when no dated activities are available on any side."""
    dates = []
    for d in (baseline, update, corrected):
        for s, f, _ in _weighted_spans(d):
            dates.append(s)
            dates.append(f)
    if not dates:
        return {'periods': [], 'baseline': [], 'before': [], 'after': []}
    boundaries = _month_boundaries(min(dates), max(dates))
    return {
        'periods': [b.strftime('%b %y') for b in boundaries],
        'baseline': cumulative_pct(baseline, boundaries),
        'after': cumulative_pct(update, boundaries),
        'before': cumulative_pct(corrected, boundaries),
    }
