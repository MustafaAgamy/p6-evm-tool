"""Schedule Intelligence — the schedule *profile* (a deterministic fingerprint).

``build_profile(context)`` returns a JSON-serialisable dict summarising the shape and
richness of a parsed schedule: how big it is, how densely it is logic-linked, what
relationship types it uses, how much of it is progressed / cost-loaded / coded, and
how deep/wide its WBS is. Later slices read this to decide *how* to analyse a given
file (e.g. how many instances make a pattern, similarity thresholds, chart caps) — so
the profile also carries ``params`` adaptively scaled by ``size_class``.

Pure and deterministic. No project-specific strings; every label is derived from the
file. Counts reconcile exactly with the raw parse.
"""
from p6_narrative.intel.grouping import discipline_of, package_of

_REL_TYPES = ('FS', 'SS', 'FF', 'SF')

# Adaptive analysis parameters per size class. Bigger schedules need more evidence
# before something counts as a repeating pattern, tolerate looser name-similarity,
# and allow bigger charts. Values are deterministic; a slice may read what it needs.
_PARAMS = {
    'small':  {'min_instances': 2, 'sim_threshold': 0.60, 'max_chart_items': 12, 'max_charts': 6},
    'medium': {'min_instances': 3, 'sim_threshold': 0.55, 'max_chart_items': 15, 'max_charts': 8},
    'large':  {'min_instances': 5, 'sim_threshold': 0.50, 'max_chart_items': 20, 'max_charts': 10},
}


def _size_class(n_activities):
    if n_activities < 500:
        return 'small'
    if n_activities < 5000:
        return 'medium'
    return 'large'


def build_profile(context) -> dict:
    """Return the schedule fingerprint dict for an :class:`IntelContext`."""
    data = context.data
    activities = data.activities
    rels = data.relationships

    n_activities = len(activities)          # reconciles EXACT with the raw parse
    n_steps = len(context.steps)
    n_milestones = len(context.milestones)
    n_rels = len(rels)                      # reconciles EXACT with the raw parse

    # Relationship-type mix (always all four keys present)
    rel_type_mix = {t: 0 for t in _REL_TYPES}
    for r in rels:
        t = r.get('type', 'FS')
        if t in rel_type_mix:
            rel_type_mix[t] += 1
        else:
            rel_type_mix[t] = rel_type_mix.get(t, 0) + 1

    # Logic density = links per activity
    logic_density = (n_rels / n_activities) if n_activities else 0.0

    # Progress: fraction of activities carrying an actual start (execution has begun)
    with_actuals = sum(1 for a in activities.values() if a.get('actual_start'))
    pct_with_actuals = (with_actuals / n_activities) if n_activities else 0.0

    critical_count = sum(1 for a in activities.values() if a.get('is_critical'))

    # WBS shape
    depths = [context.wbs_depth_of(wid) for wid in data.wbs]
    wbs_depth = max(depths) if depths else 0
    wbs_width = len(context.branch_ids)

    # Coverage flags
    code_dimensions = list(data.activity_code_types or [])
    has_cost = any(v > 0 for v in (data.bac_by_activity or {}).values())
    # The parser exposes resources only as rolled-up cost per activity (no resource
    # table), so "has resources" == any resource assignment produced a cost record.
    has_resources = bool(data.bac_by_activity or data.ac_by_activity)

    size_class = _size_class(n_activities)

    # Distinct disciplines / packages present (from the single grouping source of truth)
    n_disciplines = len({discipline_of(context, a) for a in context.steps.values()})
    n_packages = len({package_of(context, a) for a in context.steps.values()})

    return {
        'activities': n_activities,
        'step_activities': n_steps,
        'milestones': n_milestones,
        'relationships': n_rels,
        'logic_density': round(logic_density, 4),
        'rel_type_mix': rel_type_mix,
        'pct_with_actuals': round(pct_with_actuals, 4),
        'critical_count': critical_count,
        'wbs_depth': wbs_depth,
        'wbs_width': wbs_width,
        'disciplines': n_disciplines,
        'packages': n_packages,
        'code_dimensions': code_dimensions,
        'has_cost': has_cost,
        'has_resources': has_resources,
        'size_class': size_class,
        'params': dict(_PARAMS[size_class]),
    }
