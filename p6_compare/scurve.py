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


def _project_finish(data):
    """The schedule's finish date shown on the dashboard: project ScheduledFinishDate, else
    the latest planned activity finish."""
    proj = getattr(data, 'project', None) or {}
    if proj.get('scheduled_finish'):
        return proj['scheduled_finish']
    fins = [a.get('planned_finish') for a in getattr(data, 'activities', {}).values() if a.get('planned_finish')]
    return max(fins) if fins else None


def _weighted_spans(data, cap=None):
    """(start, finish, weight) for every TASK-dependent activity with a positive-length planned
    span. Task-dependent only (Ibrahim's rule, consistent with the change tables). Each finish is
    capped at ``cap`` (the schedule's project finish) so the curve reaches 100% at the finish date
    the dashboard shows — trailing work after the finish milestone folds into that 100%, instead of
    tailing the curve past it."""
    out = []
    for act in getattr(data, 'activities', {}).values():
        if act.get('task_type') != 'Task':
            continue
        s, f = _span(act)
        if cap and f and f > cap:
            f = cap
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


def cumulative_pct(data, boundaries, cap=None):
    """Cumulative planned % complete at each boundary datetime (0–100, rounded 0.1). Finishes
    capped at ``cap`` so the curve reaches 100% at the schedule's finish date."""
    spans = _weighted_spans(data, cap)
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


def _frac_idx(date, boundaries):
    """Fractional x-index of ``date`` along the monthly boundaries (for a finish marker)."""
    if not date or len(boundaries) < 2:
        return None
    if date <= boundaries[0]:
        return 0.0
    if date >= boundaries[-1]:
        return float(len(boundaries) - 1)
    for i in range(len(boundaries) - 1):
        if boundaries[i] <= date < boundaries[i + 1]:
            frac = (date - boundaries[i]).total_seconds() / (boundaries[i + 1] - boundaries[i]).total_seconds()
            return round(i + frac, 3)
    return float(len(boundaries) - 1)


def three_way_scurve(baseline, update, corrected):
    """{'periods', 'baseline', 'before', 'after', 'markers'}. Each curve is anchored to its own
    project finish (reaches 100% there); 'markers' gives the x-index of the baseline and update
    finishes so the chart can mark them and shade the slip between. 'before' is the rescheduled
    corrected file, 'after' the current update. Empty when no dated activities exist."""
    bf, uf, cf = _project_finish(baseline), _project_finish(update), _project_finish(corrected)
    dates = []
    for d, cap in ((baseline, bf), (update, uf), (corrected, cf)):
        for s, f, _ in _weighted_spans(d, cap):
            dates.append(s)
            dates.append(f)
    if not dates:
        return {'periods': [], 'baseline': [], 'before': [], 'after': [], 'markers': {}}
    boundaries = _month_boundaries(min(dates), max(dates))
    return {
        'periods': [b.strftime('%b %y') for b in boundaries],
        'baseline': cumulative_pct(baseline, boundaries, bf),
        'after': cumulative_pct(update, boundaries, uf),
        'before': cumulative_pct(corrected, boundaries, cf),
        'markers': {
            'baseline_idx': _frac_idx(bf, boundaries), 'baseline_label': _fmt(bf),
            'update_idx': _frac_idx(uf, boundaries), 'update_label': _fmt(uf),
        },
    }


def _fmt(d):
    return d.strftime('%d-%b-%Y') if hasattr(d, 'strftime') else None
