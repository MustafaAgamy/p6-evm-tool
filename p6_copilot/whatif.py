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


def _find_with_oid(data, activity_id):
    """Like _find, but also returns the per-file ObjectId so predecessor links (keyed by
    ObjectId) can be looked up for the 'remove a constraint' estimate."""
    for oid, a in data.activities.items():
        if a.get('id') == activity_id:
            return oid, a
    return None, None


# Planning rules of thumb for the instant estimate — deliberately conservative, and clearly
# labelled estimates (the exact figure is always the planner's F9). Adjustable in one place.
_CREW_FACTOR = 0.40      # a second crew ~ 40% off the activity's remaining duration
_OVERTIME_FACTOR = 0.15  # overtime ~ 15% off, before productivity fall-off


def _speedup_estimate(data, activity_id, factor, verb, cost_note):
    """Shared engine for 'add a crew' / 'overtime': compress an activity's remaining duration
    by a factor; it only pulls the finish in when the activity is on the critical path."""
    act = _find(data, activity_id)
    if act is None:
        raise KeyError(f'Activity {activity_id!r} not found in the schedule.')
    name = act.get('name') or activity_id
    fl = act.get('total_float_days')
    critical = fl is not None and fl <= 0
    rem = _remaining_days(act, data)
    gain = _r(rem * factor)
    if critical and gain > 0:
        return {'impact_days': -gain, 'direction': 'earlier',
                'headline': f"{verb} on '{name}' could bring the finish in by roughly {gain} working days.",
                'basis': (f"it's on the critical path; {verb.lower()} could take about {int(factor * 100)}% off its "
                          f"remaining {rem} working days ({gain} wd), and time saved on the critical path shortens the project."),
                'advice': f"{cost_note} Re-check afterwards — the driving path can move once '{name}' speeds up.",
                'estimate': True}
    if not critical:
        spare = _r(fl) if (fl is not None and fl > 0) else 0
        return {'impact_days': 0, 'direction': 'none',
                'headline': f"{verb} on '{name}' wouldn't move the finish date.",
                'basis': f"'{name}' isn't on the critical path — it already has about {spare} working days of spare time, so speeding it up only adds slack.",
                'advice': "To pull the finish in, apply this to an activity that's on the critical path instead.",
                'estimate': True}
    return {'impact_days': 0, 'direction': 'none',
            'headline': f"{verb} on '{name}' wouldn't change the finish.",
            'basis': f"there's little remaining duration on '{name}' left to compress.",
            'advice': "Pick a critical-path activity with meaningful remaining work.",
            'estimate': True}


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

    if kind == 'add_crew':
        return _speedup_estimate(data, activity_id, _CREW_FACTOR, 'Adding a second crew',
                                 "Worth it if the extra crew's cost beats the days saved.")

    if kind == 'overtime':
        return _speedup_estimate(data, activity_id, _OVERTIME_FACTOR, 'Overtime',
                                 "Weigh the time saved against overtime cost and fatigue.")

    if kind == 'remove_relationship':
        oid, act = _find_with_oid(data, activity_id)
        if act is None:
            raise KeyError(f'Activity {activity_id!r} not found in the schedule.')
        name = act.get('name') or activity_id
        fl = act.get('total_float_days')
        critical = fl is not None and fl <= 0
        preds = [r for r in data.relationships if r.get('succ_id') == oid]
        if not critical:
            spare = _r(fl) if (fl is not None and fl > 0) else 0
            return {'impact_days': 0, 'direction': 'none',
                    'headline': f"Relaxing a constraint on '{name}' wouldn't move the finish date.",
                    'basis': f"'{name}' isn't on the critical path (about {spare} working days of spare time), so its predecessors aren't holding completion.",
                    'advice': "To pull the finish in, relax a driving relationship on a critical-path activity instead.",
                    'estimate': True}
        if not preds:
            return {'impact_days': 0, 'direction': 'none',
                    'headline': f"'{name}' has no predecessor links to remove.",
                    'basis': "nothing is constraining its start in the logic, so there's no relationship to relax.",
                    'advice': "Pick a critical activity that's waiting on a predecessor.",
                    'estimate': True}
        return {'impact_days': None, 'qualitative': True, 'direction': 'earlier?',
                'headline': f"Removing the driving constraint on '{name}' could bring the finish in — the exact amount needs P6's F9.",
                'basis': (f"'{name}' is on the critical path with {len(preds)} predecessor link(s); freeing its driving "
                          "predecessor could let it (and the finish) start earlier, but by how much depends on the "
                          "next-longest path — only a reschedule can tell."),
                'advice': "Build it as a scenario, remove the link in P6 and press F9 for the exact pull-in. Only relax logic that isn't a genuine physical constraint.",
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
