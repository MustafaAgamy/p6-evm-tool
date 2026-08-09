"""Orchestrates one AI Constructability Review.

skeleton → Claude (structured output) → count the findings → derive the
percentages and the 45/45/10 score → assemble the report dict the UI renders.
Everything the AI returns is treated as advisory opinion.
"""
from p6_ai.client import call_claude
from p6_ai.prompt import build_request
from p6_ai.scoring import compute_score
from p6_ai.skeleton import build_skeleton


def _round1(x):
    return round(x, 1)


def _ensure_unique_ids(missing, existing_ids):
    """Defensive: never let a suggested activity id collide with an existing one."""
    used = set(existing_ids)
    for m in missing:
        sid = (m.get('suggested_id') or 'NEW').strip() or 'NEW'
        if sid in used:
            n = 1
            while f'{sid}-{n}' in used:
                n += 1
            sid = f'{sid}-{n}'
        m['suggested_id'] = sid
        used.add(sid)
    return missing


def run_review(data, api_key, *, reference_data=None, cfg=None, _call=None):
    """Return the report dict for ``data`` (a ScheduleData). ``_call`` is a test seam."""
    cfg = cfg or {}
    model = cfg.get('model', 'claude-opus-5')
    effort = cfg.get('effort', 'medium')
    ai_cfg = cfg.get('ai') or {}

    skeleton = build_skeleton(data)
    reference = build_skeleton(reference_data) if reference_data is not None else None
    request = build_request(skeleton, model=model, reference=reference, effort=effort)

    call = _call or call_claude
    ai = call(request, api_key)

    illogical = ai.get('illogical') or []
    missing = _ensure_unique_ids(ai.get('missing') or [],
                                 {a['id'] for a in skeleton['activities']})
    missing_wbs = ai.get('missing_wbs') or []

    total_rel = skeleton['relationship_count']
    total_act = skeleton['activity_count']
    illogical_pct = 100.0 * len(illogical) / max(total_rel, 1)
    missing_pct = 100.0 * len(missing) / max(total_act, 1)
    suggestion_count = len(illogical) + len(missing) + len(missing_wbs)

    score = compute_score(
        illogical_pct=illogical_pct, missing_pct=missing_pct,
        missing_wbs=len(missing_wbs), suggestion_count=suggestion_count,
        activity_count=total_act, cfg=ai_cfg)

    critical_affected = any((f.get('impact') == 'Critical') for f in illogical)

    return {
        'mode': 'reference' if reference is not None else 'engineering',
        'project_type': ai.get('project_type') or 'Unrecognised',
        'understood': ai.get('understood') or {'summary': '', 'phases': []},
        'dashboard': {
            'illogical_count': len(illogical),
            'illogical_pct': _round1(illogical_pct),
            'total_relationships': total_rel,
            'missing_count': len(missing),
            'missing_pct': _round1(missing_pct),
            'total_activities': total_act,
            'missing_wbs': len(missing_wbs),
            'critical_affected': critical_affected,
        },
        'score': score,
        'illogical': illogical,
        'missing': missing,
        'missing_wbs': missing_wbs,
        'wbs_review': ai.get('wbs_review') or [],
        'conclusion': ai.get('conclusion') or '',
    }
