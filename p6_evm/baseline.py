"""Apply an attached baseline schedule to an update schedule so EVM matches P6 / the XML.

A P6 XER *update* export doesn't embed its baseline, so its Planned Value is wrong. When the user
attaches the baseline (a separate XER/XML), this feeds the update both halves P6 anchors PV and the
WBS %-rollup to — the baseline PLANNED DATES and the baseline BUDGET — matched by Activity Id, the
same linkage the XML parser does from <BaselineProject>. metrics.compute() already reads
`baseline_by_id` and `baseline_bac_by_activity`; this just fills them from the attached file.
"""


def apply_baseline(data, baseline_data):
    """Mutate `data` in place: set baseline planned dates + baseline budget from `baseline_data`.

    Returns {'matched': int, 'total': int, 'bac_matched': int} — how many of the update's
    activities line up with the baseline by Activity Id (for the UI's confidence count).
    """
    # Baseline planned dates + object-id → Activity-Id map, keyed by the baseline's Activity Id (code).
    bl_dates = {}
    bl_oid_to_id = {}
    for oid, a in (baseline_data.activities or {}).items():
        aid = a.get('id')
        if not aid:
            continue
        bl_oid_to_id[oid] = aid
        bl_dates[aid] = {'planned_start': a.get('planned_start'),
                         'planned_finish': a.get('planned_finish')}

    # Baseline budget per Activity Id — only where the baseline actually carries cost (mirrors the
    # XML path, where an activity with no baseline resource assignment falls back to the current BAC).
    bl_bac_by_id = {}
    for boid, cost in (getattr(baseline_data, 'bac_by_activity', None) or {}).items():
        aid = bl_oid_to_id.get(boid)
        if aid is not None:
            bl_bac_by_id[aid] = bl_bac_by_id.get(aid, 0.0) + cost

    data.baseline_by_id = bl_dates
    new_bac = {}
    matched = 0
    for oid, a in (data.activities or {}).items():
        aid = a.get('id')
        if aid in bl_dates:
            matched += 1
        if aid in bl_bac_by_id:
            new_bac[oid] = bl_bac_by_id[aid]
    data.baseline_bac_by_activity = new_bac

    return {'matched': matched, 'total': len(data.activities or {}), 'bac_matched': len(new_bac)}
