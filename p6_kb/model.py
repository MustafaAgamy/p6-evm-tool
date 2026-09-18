"""A clean view of a schedule for the constructability engine.

Reads the already-parsed ``ScheduleData`` (validated against real P6 exports).
Two graphs are surfaced side by side:

* the legacy **activity-code-keyed** graph (``activities`` / ``by_code`` /
  ``relationships``) — kept byte-for-byte for the existing v1 review; and
* an **ObjectId-keyed** graph (``activities_oid`` / ``by_oid`` /
  ``relationships_oid``) — duplicate-code-safe (real P6 exports can carry every
  activity twice under one code), for the v2 relationship-intelligence engine.

Every field the parser already computes but the old view dropped — activity
codes, relationship **lag**, dates, float, status, duration — is now surfaced.
All additions are additive: v1 rules read only the legacy keys, so output is
unchanged (Phase 0 — "un-lose the data").
"""

_MILESTONE = ('StartMilestone', 'FinishMilestone')


def _activity_row(oid, a):
    """A rich activity record (identity fields are added later by the tagger)."""
    return {
        'object_id': oid,
        'id': a.get('id') or '',
        'name': a.get('name') or '',
        'wbs_path': a.get('wbs_path') or '',
        'is_milestone': a.get('task_type') in _MILESTONE,
        # ── surfaced from the parser (previously dropped) ──
        'task_type': a.get('task_type'),
        'status': a.get('status'),
        'percent_complete': a.get('percent_complete'),
        'planned_duration': a.get('planned_duration'),        # hours (parser unit)
        'planned_start': a.get('planned_start'),
        'planned_finish': a.get('planned_finish'),
        'actual_start': a.get('actual_start'),
        'actual_finish': a.get('actual_finish'),
        'total_float_days': a.get('total_float_days'),
        'is_critical': a.get('is_critical'),
        'constraint_type': a.get('constraint_type'),
        'constraint_date': a.get('constraint_date'),
        'activity_codes': a.get('activity_codes') or {},
    }


def schedule_view(data):
    oid_to_code = {oid: a.get('id') for oid, a in data.activities.items()}

    # ── ObjectId graph (dedup-safe): one row per real activity ObjectId ──
    activities_oid = [_activity_row(oid, a) for oid, a in data.activities.items()]
    by_oid = {r['object_id']: r for r in activities_oid}

    relationships_oid = []
    for r in data.relationships:
        p, s = r.get('pred_id'), r.get('succ_id')
        if p in by_oid and s in by_oid:
            relationships_oid.append({
                'pred_oid': p, 'succ_oid': s,
                'type': r.get('type') or 'FS',
                'lag_days': r.get('lag_days') or 0.0,
                'lag_hours': r.get('lag_hours') or 0.0,
            })

    # ── legacy code-keyed graph (unchanged shape; extra fields ride along) ──
    activities = [r for r in activities_oid if r['id']]
    by_code = {r['id']: r for r in activities}   # last-wins, as before

    relationships = []
    for r in data.relationships:
        pred = oid_to_code.get(r.get('pred_id'))
        succ = oid_to_code.get(r.get('succ_id'))
        if not pred or not succ:
            continue
        relationships.append({
            'pred': pred, 'succ': succ, 'type': r.get('type') or 'FS',
            'lag_days': r.get('lag_days') or 0.0, 'lag_hours': r.get('lag_hours') or 0.0,
        })

    wbs = [{'name': w.get('name') or ''} for w in data.wbs.values()]

    return {
        'activities': activities,
        'by_code': by_code,
        'relationships': relationships,
        'wbs': wbs,
        'activity_count': len(activities),
        'relationship_count': len(relationships),
        # ── additive (v2 engine) ──
        'activities_oid': activities_oid,
        'by_oid': by_oid,
        'relationships_oid': relationships_oid,
        'activity_code_types': list(getattr(data, 'activity_code_types', []) or []),
    }


def detection_text(view):
    """Lower-cased blob of activity + WBS names, for signature matching."""
    parts = [a['name'] for a in view['activities']] + [w['name'] for w in view['wbs']]
    parts += [a['wbs_path'] for a in view['activities']]
    return ' '.join(parts).lower()
