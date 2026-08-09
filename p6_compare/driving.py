"""Derive the driving predecessor / successor link(s) for an activity.

P6 does not export a "driving" flag (it is a scheduling result). We derive it from
the remaining early dates and the link lag: a link is driving when the working days
between the predecessor's controlling date and the successor's anchor equal the
link's lag (within a small tolerance). Ties — genuine co-driving links — are all
returned. Works on a p6_audit.graph.ScheduleGraph (pre-indexed predecessors /
successors), so it stays O(edges), not O(activities squared).
"""
from p6_evm.calendars import signed_working_days


def _working_days(cal, d1, d2):
    """Signed working days from d1 to d2 (falls back to calendar days). None if a date is missing."""
    if not d1 or not d2:
        return None
    if cal is None:
        return (d2 - d1).days
    try:
        return signed_working_days(cal, d1, d2)
    except Exception:
        return (d2 - d1).days


def _pred_controls(pred, rel_type):
    """The predecessor date that controls the link: finish for FS/FF, start for SS/SF."""
    return pred.get('remaining_early_finish') if rel_type in ('FS', 'FF') else pred.get('remaining_early_start')


def _succ_anchor(succ, rel_type):
    """The successor date the link constrains: start for FS/SS, finish for FF/SF."""
    return succ.get('remaining_early_start') if rel_type in ('FS', 'SS') else succ.get('remaining_early_finish')


def _is_driving(cal, pred, succ, rel_type, lag, tolerance):
    gap = _working_days(cal, _pred_controls(pred, rel_type), _succ_anchor(succ, rel_type))
    if gap is None:
        return False
    return abs(gap - (lag or 0.0)) <= tolerance


def driving_predecessors(graph, oid, tolerance=1.0):
    """Predecessor links that drive this activity's remaining early start/finish.
    Each item: {'pred_oid', 'type', 'lag_days'}."""
    act = graph.activities.get(oid)
    if not act:
        return []
    cal = graph.calendars.get(act.get('calendar_id'))
    out = []
    for link in graph.preds_of(oid):
        pred = graph.activities.get(link['other'])
        if not pred:
            continue
        t, lag = link.get('type', 'FS'), link.get('lag_days', 0.0) or 0.0
        if _is_driving(cal, pred, act, t, lag, tolerance):
            out.append({'pred_oid': link['other'], 'type': t, 'lag_days': lag})
    return out


def driving_successors(graph, oid, tolerance=1.0):
    """Successor links this activity drives. Each item: {'succ_oid', 'type', 'lag_days'}."""
    act = graph.activities.get(oid)
    if not act:
        return []
    out = []
    for link in graph.succs_of(oid):
        succ = graph.activities.get(link['other'])
        if not succ:
            continue
        cal = graph.calendars.get(succ.get('calendar_id'))
        t, lag = link.get('type', 'FS'), link.get('lag_days', 0.0) or 0.0
        if _is_driving(cal, act, succ, t, lag, tolerance):
            out.append({'succ_oid': link['other'], 'type': t, 'lag_days': lag})
    return out
