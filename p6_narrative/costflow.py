"""Cost loading (share of budget by WBS) and the cash-flow curve.

Pure logic. Reads the budget the tool already parsed (``bac_by_activity``, keyed by
activity ObjectId) — recomputes nothing. Cash flow spreads each activity's budget
evenly across its planned start→finish calendar days and accumulates, which is the
standard cost-loaded S-curve; it is illustrative of the plan, not a new number.
"""
import bisect
from datetime import timedelta

from p6_narrative.util import as_date, top_wbs_name


def cost_by_wbs(activities, bac_by_activity, wbs):
    """Share of budget per top-level WBS branch.

    Returns ``{'total', 'rows': [{'name', 'cost', 'pct'}]}`` sorted by cost desc.
    """
    totals = {}
    for act in activities:
        cost = bac_by_activity.get(act.get('object_id'), 0.0) or 0.0
        if cost <= 0:
            continue
        name = top_wbs_name(act.get('wbs_id'), wbs) or 'Unassigned'
        totals[name] = totals.get(name, 0.0) + cost
    total = sum(totals.values())
    rows = [
        {'name': name, 'cost': round(cost, 2),
         'pct': round(100 * cost / total, 2) if total else 0.0}
        for name, cost in sorted(totals.items(), key=lambda kv: -kv[1])
    ]
    return {'total': round(total, 2), 'rows': rows}


def cash_flow(activities, bac_by_activity, n_points=24):
    """Cumulative planned-cost curve sampled at ``n_points`` points.

    Returns ``{'total', 'points': [{'date', 'cumulative', 'pct'}]}``.
    """
    daily = {}
    total = 0.0
    for act in activities:
        cost = bac_by_activity.get(act.get('object_id'), 0.0) or 0.0
        if cost <= 0:
            continue
        start = as_date(act.get('planned_start'))
        if not start:
            continue
        finish = as_date(act.get('planned_finish')) or start
        days = max((finish - start).days + 1, 1)
        per = cost / days
        for k in range(days):
            d = start + timedelta(days=k)
            daily[d] = daily.get(d, 0.0) + per
        total += cost

    if not daily or total <= 0:
        return {'total': round(total, 2), 'points': []}

    dates = sorted(daily)
    cum, cum_dates, cum_vals = 0.0, [], []
    for d in dates:
        cum += daily[d]
        cum_dates.append(d)
        cum_vals.append(cum)

    start, end = dates[0], dates[-1]
    span = (end - start).days or 1
    points = []
    for i in range(n_points + 1):
        target = start + timedelta(days=round(span * i / n_points))
        idx = bisect.bisect_right(cum_dates, target) - 1
        value = cum_vals[idx] if idx >= 0 else 0.0
        points.append({
            'date': target.isoformat(),
            'cumulative': round(value, 2),
            'pct': round(100 * value / total, 2) if total else 0.0,
        })
    return {'total': round(total, 2), 'points': points}
