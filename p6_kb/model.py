"""A clean, activity-code-keyed view of a schedule for the constructability engine.

Reads the already-parsed ``ScheduleData`` (validated against real P6 exports) and
re-keys relationships from per-file ObjectIds to stable activity codes.
"""

_MILESTONE = ('StartMilestone', 'FinishMilestone')


def schedule_view(data):
    oid_to_code = {oid: a.get('id') for oid, a in data.activities.items()}

    activities = []
    for a in data.activities.values():
        code = a.get('id')
        if not code:
            continue
        activities.append({
            'id': code,
            'name': a.get('name') or '',
            'wbs_path': a.get('wbs_path') or '',
            'is_milestone': a.get('task_type') in _MILESTONE,
        })
    by_code = {a['id']: a for a in activities}

    relationships = []
    for r in data.relationships:
        pred = oid_to_code.get(r.get('pred_id'))
        succ = oid_to_code.get(r.get('succ_id'))
        if not pred or not succ:
            continue
        relationships.append({'pred': pred, 'succ': succ, 'type': r.get('type') or 'FS'})

    wbs = [{'name': w.get('name') or ''} for w in data.wbs.values()]

    return {
        'activities': activities,
        'by_code': by_code,
        'relationships': relationships,
        'wbs': wbs,
        'activity_count': len(activities),
        'relationship_count': len(relationships),
    }


def detection_text(view):
    """Lower-cased blob of activity + WBS names, for signature matching."""
    parts = [a['name'] for a in view['activities']] + [w['name'] for w in view['wbs']]
    parts += [a['wbs_path'] for a in view['activities']]
    return ' '.join(parts).lower()
