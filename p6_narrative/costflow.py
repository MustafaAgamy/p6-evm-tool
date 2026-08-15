"""Cost loading (share of budget by WBS) and the cash-flow curve.

Pure logic. Reads the budget the tool already parsed (``bac_by_activity``, keyed by
activity ObjectId) — recomputes nothing. Cash flow spreads each activity's budget
evenly across its planned start→finish calendar days and accumulates, which is the
standard cost-loaded S-curve; it is illustrative of the plan, not a new number.
"""
import bisect
from datetime import timedelta

from p6_narrative.util import as_date, top_wbs_name, wbs_grouping


def cost_by_wbs(activities, bac_by_activity, wbs):
    """Share of budget per major WBS branch.

    Groups by ``wbs_grouping`` (roots, or the children of a single root) so a project
    built under one top node still gets a real breakdown instead of one bar. Returns
    ``{'total', 'rows': [{'name', 'cost', 'pct'}]}`` sorted by cost desc.
    """
    group_of, _ = wbs_grouping(wbs)
    totals = {}
    for act in activities:
        cost = bac_by_activity.get(act.get('object_id'), 0.0) or 0.0
        if cost <= 0:
            continue
        gid = group_of.get(act.get('wbs_id'))
        name = (wbs.get(gid) or {}).get('name') or top_wbs_name(act.get('wbs_id'), wbs) or 'Unassigned'
        totals[name] = totals.get(name, 0.0) + cost
    total = sum(totals.values())
    rows = [
        {'name': name, 'cost': round(cost, 2),
         'pct': round(100 * cost / total, 2) if total else 0.0}
        for name, cost in sorted(totals.items(), key=lambda kv: -kv[1])
    ]
    return {'total': round(total, 2), 'rows': rows}


def branch_stats(activities, bac_by_activity, wbs):
    """Per major-branch ``{name, count, cost, pct}`` for the annotated WBS org-chart,
    in WBS branch order. Generic across any project."""
    group_of, branch_ids = wbs_grouping(wbs)
    by_branch = {bid: {'count': 0, 'cost': 0.0} for bid in branch_ids}
    for act in activities:
        gid = group_of.get(act.get('wbs_id'))
        if gid in by_branch:
            by_branch[gid]['count'] += 1
            by_branch[gid]['cost'] += bac_by_activity.get(act.get('object_id'), 0.0) or 0.0
    total_cost = sum(b['cost'] for b in by_branch.values()) or 1.0
    return [{'name': (wbs.get(bid) or {}).get('name') or '—',
             'count': by_branch[bid]['count'], 'cost': round(by_branch[bid]['cost'], 2),
             'pct': round(100 * by_branch[bid]['cost'] / total_cost, 1)}
            for bid in branch_ids]


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
