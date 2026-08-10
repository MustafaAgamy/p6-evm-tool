"""Build the compact schedule *skeleton* sent to the AI.

This is the privacy boundary: it is the only representation of the schedule that
ever leaves the machine. It carries the structure the AI needs to judge
construction logic and scope completeness — activity codes, names, WBS, links,
rough durations — and deliberately **omits costs and the client/project name**.

Relationships are re-keyed from per-file ObjectIds to stable activity *codes*
(the same choice the compare module makes), so the AI reasons in the planner's
own identifiers.
"""
from p6_evm.parser import full_wbs_path

_MILESTONE_TYPES = ('StartMilestone', 'FinishMilestone')


def _duration_days(act, data):
    """Best-effort working-day duration from P6's hour-based PlannedDuration."""
    pd = act.get('planned_duration') or 0
    if not pd:
        return 0
    cal = data.calendars.get(act.get('calendar_id'))
    day_hours = cal.day_hours if cal else 8.0
    return round(pd / (day_hours or 8.0), 1)


def build_skeleton(data):
    """Return a JSON-serialisable dict describing the schedule for AI review.

    Shape::

        {
          'activity_count': int, 'relationship_count': int,
          'activities':    [{'id','name','wbs_path','is_milestone','duration_days'}],
          'relationships': [{'pred','succ','type','lag_days'}],   # codes, not oids
          'wbs':           [{'name','path'}],
        }

    Never includes cost or client-name fields.
    """
    oid_to_code = {oid: a.get('id') for oid, a in data.activities.items()}

    activities = []
    for oid, a in data.activities.items():
        code = a.get('id')
        if not code:
            continue  # an activity with no code can't be referenced or acted on
        activities.append({
            'id': code,
            'name': a.get('name') or '',
            'wbs_path': a.get('wbs_path') or '',
            'is_milestone': a.get('task_type') in _MILESTONE_TYPES,
            'duration_days': _duration_days(a, data),
        })

    relationships = []
    for r in data.relationships:
        pred = oid_to_code.get(r.get('pred_id'))
        succ = oid_to_code.get(r.get('succ_id'))
        if not pred or not succ:
            continue  # drop links that reference an activity we can't name
        relationships.append({
            'pred': pred,
            'succ': succ,
            'type': r.get('type') or 'FS',
            'lag_days': round(r.get('lag_days') or 0.0, 1),
        })

    wbs = [{'name': w.get('name') or '', 'path': full_wbs_path(oid, data.wbs)}
           for oid, w in data.wbs.items()]

    return {
        'activity_count': len(activities),
        'relationship_count': len(relationships),
        'activities': activities,
        'relationships': relationships,
        'wbs': wbs,
    }
