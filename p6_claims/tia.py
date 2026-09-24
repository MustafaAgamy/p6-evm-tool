"""Read the exact Time-Impact-Analysis impact back from P6-rescheduled programmes.

The impact is the movement of the completion — the latest finish, preferring a
Finish Milestone (the same anchor :func:`p6_evm.metrics.compute` uses for Delay) —
between the base update and the impacted programme after F9, measured in working
days on that milestone's calendar. The number is P6's: nothing here reschedules
or invents a date.
"""
from p6_evm.calendars import signed_working_days


def _completion(data):
    """(finish_datetime, activity) of the programme's completion, or (None, None)."""
    def fin(a):
        return a.get('remaining_early_finish') or a.get('planned_finish')

    acts = [a for a in data.activities.values() if fin(a)]
    if not acts:
        return None, None
    milestones = [a for a in acts if a.get('task_type') == 'FinishMilestone']
    pool = milestones or acts
    a = max(pool, key=fin)
    return fin(a), a


def compute_impact(base_data, impacted_data):
    """How far the completion moved between the two programmes, in working days.

    Returns ``{'before_finish', 'after_finish', 'impact_days', 'milestone_id',
    'milestone_name'}``. ``impact_days`` is positive when completion moved later (a
    delay), rounded to whole working days like the Delay metric; ``None`` when a
    finish can't be determined.
    """
    before, base_act = _completion(base_data)
    after, _ = _completion(impacted_data)
    result = {
        'before_finish': before,
        'after_finish': after,
        'impact_days': None,
        'milestone_id': base_act.get('id') if base_act else None,
        'milestone_name': base_act.get('name') if base_act else None,
    }
    if before is None or after is None or base_act is None:
        return result
    cal = base_data.calendars.get(base_act.get('calendar_id'))
    impact = signed_working_days(cal, before, after)
    result['impact_days'] = round(impact) if impact is not None else None
    return result
