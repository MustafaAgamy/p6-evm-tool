"""Instant, offline what-if ESTIMATES for the AI Copilot — computed from the analysis already
done on the XML update (each activity's P6 total float + the critical path), so a MANAGER gets
an answer and advice with NO Primavera round-trip.

These are grounded estimates, not P6's exact number: a delay is netted against the activity's
spare time; a speed-up only helps if the activity is on the critical path. The exact,
claim-grade figure stays the planner's F9 path (Decision 003). Every estimate is labelled.
"""
from p6_evm.calendars import signed_working_days
from p6_claims.tia import _completion


def _find(data, activity_id):
    for a in data.activities.values():
        if a.get('id') == activity_id:
            return a
    return None


def _r(x):
    return int(round(x)) if x is not None else 0


def _remaining_days(act, data):
    cal = data.calendars.get(act.get('calendar_id'))
    dh = (cal.day_hours if cal else 8.0) or 8.0
    return _r((act.get('planned_duration') or 0) / dh)


def _remaining_working_days(data):
    dd = (data.project or {}).get('data_date')
    fin, act = _completion(data)
    if not dd or not fin or not act:
        return 0
    cal = data.calendars.get(act.get('calendar_id'))
    wd = signed_working_days(cal, dd, fin) if cal else None
    return max(0, wd) if wd is not None else 0


def estimate(data, kind, activity_id=None, days=None):
    """Return a plain, advice-carrying estimate: {impact_days(+later/-earlier), direction,
    headline, basis, advice, estimate:True}."""
    if kind in ('delay', 'shorten'):
        act = _find(data, activity_id)
        if act is None:
            raise KeyError(f'Activity {activity_id!r} not found in the schedule.')
        name = act.get('name') or activity_id
        fl = act.get('total_float_days')
        spare = _r(fl) if (fl is not None and fl > 0) else 0
        n = int(days or 0)

        if kind == 'delay':
            impact = max(0, n - spare)
            if impact > 0:
                basis = (f"'{name}' has about {spare} working days of spare time; the rest of the slip flows to the finish."
                         if spare else f"'{name}' is on the critical path (no spare time), so the whole slip flows to the finish.")
                advice = f"Protect '{name}' — a slip here moves the end date. Add attention or resources before it starts."
            else:
                basis = f"'{name}' has about {spare} working days of spare time — enough to absorb a {n}-day slip."
                advice = f"A slip of up to about {spare} days here is safe; beyond that it starts to move the finish."
            return {'impact_days': impact, 'direction': 'later' if impact else 'none',
                    'headline': f"Delaying '{name}' by {n} working days would push the finish out by about {impact} working days.",
                    'basis': basis, 'advice': advice, 'estimate': True}

        # shorten / crash
        critical = fl is not None and fl <= 0
        if critical:
            pull = min(n, _remaining_days(act, data))
            return {'impact_days': -pull, 'direction': 'earlier' if pull else 'none',
                    'headline': f"Speeding up '{name}' by {n} working days could bring the finish in by up to {pull} working days.",
                    'basis': "it's on the critical path, so time saved here shortens the project — until another chain of work becomes the longest.",
                    'advice': "Worth it if the cost of accelerating is less than the time saved; re-check afterwards, as the driving path may move.",
                    'estimate': True}
        return {'impact_days': 0, 'direction': 'none',
                'headline': f"Speeding up '{name}' wouldn't move the finish date.",
                'basis': f"'{name}' isn't on the critical path — it already has about {spare} working days of spare time.",
                'advice': "To pull the finish in, speed up an activity that's on the critical path instead.",
                'estimate': True}

    if kind == 'six_day':
        rem = _remaining_working_days(data)
        pull = _r(rem / 6) if rem else 0
        return {'impact_days': -pull, 'direction': 'earlier' if pull else 'none',
                'headline': f"Working 6 days a week could bring the finish in by roughly {pull} working days.",
                'basis': "you'd gain about one extra working day each week across the remaining work.",
                'advice': "Weigh the gain against overtime cost and crew fatigue — best applied to the critical work only.",
                'estimate': True}

    raise ValueError(f'Unknown what-if kind: {kind!r}')
