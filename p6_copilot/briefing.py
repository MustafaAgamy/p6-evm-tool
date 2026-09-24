"""Parse-derived extras for the Manager Report — the named critical activities driving the
finish, and a concrete add-a-crew recovery estimate with the new finish date.

These need the full ScheduleData (activity float, calendars, the finish milestone), so they
are computed only on the report route — the sanctioned re-parse — never on the DB-only ask
path. Everything here is an estimate; the exact figure stays the planner's F9.
"""
from datetime import timedelta

from p6_copilot.whatif import estimate

_MILESTONE = ('StartMilestone', 'FinishMilestone')


def _critical_sorted(data):
    """Non-milestone activities on/behind the critical path (total float <= 0), most-negative
    float first — i.e. the ones most behind their required date."""
    acts = []
    for a in data.activities.values():
        if a.get('task_type') in _MILESTONE:
            continue
        tf = a.get('total_float_days')
        if tf is None or tf > 0:
            continue
        acts.append((tf, a))
    acts.sort(key=lambda t: t[0])
    return acts


def critical_drivers(data, top=3):
    """The top critical activities driving the finish. `late` = working days behind (the size
    of the negative float); 0 means on the critical path but not itself late. The first is
    flagged `driving`."""
    out = []
    for tf, a in _critical_sorted(data)[:top]:
        out.append({'id': a.get('id'), 'name': a.get('name') or a.get('id'),
                    'late': int(round(-tf)) if tf < 0 else 0})
    if out:
        out[0]['driving'] = True
    return out


def recovery_estimate(data):
    """Best add-a-crew recovery on the driving critical activities: {activity, recovered,
    new_finish}. Walks the critical activities most-behind first and returns the first that
    yields a real pull-in. None when nothing recovers time."""
    for tf, a in _critical_sorted(data):
        try:
            est = estimate(data, 'add_crew', a.get('id'))
        except Exception:
            continue
        impact = est.get('impact_days')
        rec = -impact if (impact is not None and impact < 0) else 0
        if rec > 0:
            return {'activity': a.get('name') or a.get('id'), 'recovered': rec,
                    'new_finish': _new_finish(data, rec)}
    return None


def _new_finish(data, recovered_wd):
    """The forecast finish pulled in by `recovered_wd` working days, on the finish activity's
    calendar. None if the finish or calendar can't be resolved."""
    try:
        from p6_claims.tia import _completion
        fin, act = _completion(data)
    except Exception:
        return None
    if not fin or not act:
        return None
    cal = data.calendars.get(act.get('calendar_id'))
    if cal is None:
        return None
    return _minus_working_days(cal, fin, recovered_wd)


def _minus_working_days(cal, when, n):
    """Step `when` back by `n` working days on the calendar. Bounded so a pathological
    (no-working-day) calendar can't loop forever."""
    d = when
    remaining = int(n)
    steps = 0
    cap = remaining * 4 + 30
    while remaining > 0 and steps < cap:
        d = d - timedelta(days=1)
        steps += 1
        day = d.date() if hasattr(d, 'date') else d
        try:
            working = cal.is_working_day(day)
        except Exception:
            working = True
        if working:
            remaining -= 1
    return d
