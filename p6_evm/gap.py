"""PV vs EV gap analysis, grouped by a chosen P6 activity code.

Per activity: PV = BAC × planned %, EV = BAC × actual %. Grouped under each
value of the selected activity-code dimension, the gap (PV − EV) shows where
the schedule slippage concentrates (e.g. Piles Works 50%, Columns Works 50%).
"""

def gap_by_code(records, dimension):
    """records: metrics compute() records (each has 'activity', 'bac',
    'planned_pct', 'actual_pct'). dimension: activity-code name to group by.
    Returns {dimension, total_pv, total_ev, total_gap, groups:[...]} where each
    group = {code, pv, ev, gap, pct_of_gap}, sorted by gap descending.
    """
    buckets = {}
    for r in records:
        planned = r.get('planned_pct')
        if planned is None:
            continue
        code = (r.get('activity', {}).get('activity_codes', {}) or {}).get(dimension)
        if not code:
            continue      # skip activities not coded for this dimension (no "uncoded" bucket)
        bac = r.get('bac') or 0.0
        pv = bac * planned
        ev = bac * (r.get('actual_pct') or 0.0)
        b = buckets.setdefault(code, {'code': code, 'pv': 0.0, 'ev': 0.0})
        b['pv'] += pv
        b['ev'] += ev

    groups = []
    for b in buckets.values():
        b['gap'] = b['pv'] - b['ev']
        groups.append(b)

    total_pv = sum(b['pv'] for b in groups)
    total_ev = sum(b['ev'] for b in groups)
    total_gap = total_pv - total_ev
    for b in groups:
        b['pct_of_gap'] = (100.0 * b['gap'] / total_gap) if total_gap else 0.0

    groups.sort(key=lambda b: b['gap'], reverse=True)
    return {
        'dimension': dimension,
        'total_pv': total_pv,
        'total_ev': total_ev,
        'total_gap': total_gap,
        'groups': groups,
    }
