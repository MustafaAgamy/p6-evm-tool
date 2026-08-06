from p6_evm.calendars import signed_working_days, float_working_days


def clamp01(x):
    return max(0.0, min(1.0, x))


def activity_planned_pct(activity, baseline_by_id, data_date, calendars):
    """Time-based Planned% Complete: how far along the activity should be by
    the data date, measured in the activity's own calendar's working time --
    not raw elapsed calendar time, which overstates progress across
    weekends/holidays exactly like an unaware Total Float would."""
    baseline = baseline_by_id.get(activity['id'])
    if not baseline or not baseline['planned_start'] or not baseline['planned_finish']:
        return None
    start, finish = baseline['planned_start'], baseline['planned_finish']
    if finish <= start:
        return 1.0 if data_date >= finish else 0.0
    cal = calendars.get(activity['calendar_id'])
    if cal is None:
        ratio = (data_date - start).total_seconds() / (finish - start).total_seconds()
        return clamp01(ratio)
    total = signed_working_days(cal, start, finish)
    if not total:
        return 1.0 if data_date >= finish else 0.0
    elapsed = signed_working_days(cal, start, min(data_date, finish))
    return clamp01(elapsed / total)


def activity_total_float(activity, calendars):
    tf = activity.get('total_float_days')
    if tf is not None:
        return tf
    cal = calendars.get(activity['calendar_id'])
    if activity.get('remaining_late_start') and activity.get('remaining_early_start'):
        return signed_working_days(cal, activity['remaining_early_start'], activity['remaining_late_start'])
    if activity.get('remaining_late_finish') and activity.get('remaining_early_finish'):
        return signed_working_days(cal, activity['remaining_early_finish'], activity['remaining_late_finish'])
    return None


def wbs_ancestor_names(wbs_id, wbs_map):
    names = []
    seen = set()
    current = wbs_id
    while current and current not in seen:
        seen.add(current)
        node = wbs_map.get(current)
        if not node:
            break
        if node['name']:
            names.append(node['name'])
        current = node['parent_object_id']
    return names


def classify_activity(activity, wbs_map, categories, classifier=None):
    names = wbs_ancestor_names(activity['wbs_id'], wbs_map)
    if classifier is not None:
        # Auto mode: classify by WBS meaning (construction synonyms). Only keep the
        # result if it's one of the configured category names.
        cat = classifier(names)
        valid = {c['name'] for c in categories}
        return cat if cat in valid else None
    for cat in categories:
        if cat.get('wbs_match') and any(cat['wbs_match'] in name for name in names):
            return cat['name']
    return None


def compute(data, config, overrides=None, classifier=None):
    """Compute per-activity records and rolled-up EVM metrics.

    Cost-based PV/EV/AC/SPI/CPI/Variance are scoped to whichever configured
    categories actually carry budget (BAC > 0) -- categories with no cost
    loaded (e.g. pure design/engineering scope) only contribute a %
    complete to the overall blended progress, never to the $ figures,
    since there is nothing in the XML to derive a $ value from.

    `overrides` is an optional {category_name: {"planned_pct": .., "actual_pct": ..}}
    mapping supplied by the user alongside the XML, for categories whose
    progress isn't derivable from the schedule at all (e.g. drawing-count-based
    design progress) -- it replaces the computed roll-up for that category
    outright rather than blending with it.
    """
    data_date = data.project['data_date']
    categories = config['categories']
    overrides = overrides or {}

    records = []
    for activity in data.activities.values():
        object_id = activity['object_id']
        bac = data.bac_by_activity.get(object_id, 0.0)
        ac = data.ac_by_activity.get(object_id, 0.0)
        planned_pct = activity_planned_pct(activity, data.baseline_by_id, data_date, data.calendars)
        actual_pct = activity['percent_complete']
        total_float = activity_total_float(activity, data.calendars)
        category = classify_activity(activity, data.wbs, categories, classifier)
        records.append({
            'activity': activity,
            'bac': bac,
            'ac': ac,
            'planned_pct': planned_pct,
            'actual_pct': actual_pct,
            'total_float': total_float,
            'category': category,
        })

    category_results = {}
    for cat in categories:
        cat_records = [
            r for r in records
            if r['category'] == cat['name'] and r['planned_pct'] is not None
        ]
        total_bac = sum(r['bac'] for r in cat_records)
        if total_bac > 0:
            def weight_of(r):
                return r['bac']
        else:
            def weight_of(r):
                return r['activity']['planned_duration'] or 1.0
        total_weight = sum(weight_of(r) for r in cat_records) or 1.0
        planned_pct = sum(weight_of(r) * r['planned_pct'] for r in cat_records) / total_weight
        actual_pct = sum(weight_of(r) * r['actual_pct'] for r in cat_records) / total_weight

        override = overrides.get(cat['name'])
        is_overridden = False
        if override:
            if 'planned_pct' in override:
                planned_pct = override['planned_pct']
                is_overridden = True
            if 'actual_pct' in override:
                actual_pct = override['actual_pct']
                is_overridden = True

        category_results[cat['name']] = {
            'weight': cat['weight'],
            'planned_pct': planned_pct,
            'actual_pct': actual_pct,
            'bac': total_bac,
            'ac': sum(r['ac'] for r in cat_records),
            'activity_count': len(cat_records),
            'overridden': is_overridden,
        }

    overall_planned_pct = sum(
        cat['weight'] * category_results[cat['name']]['planned_pct']
        for cat in categories if cat['name'] in category_results
    )
    overall_actual_pct = sum(
        cat['weight'] * category_results[cat['name']]['actual_pct']
        for cat in categories if cat['name'] in category_results
    )

    costed = [c for c in category_results.values() if c['bac'] > 0]
    total_bac = sum(c['bac'] for c in costed)
    total_ac = sum(c['ac'] for c in costed)
    if total_bac > 0:
        costed_planned_pct = sum(c['bac'] * c['planned_pct'] for c in costed) / total_bac
        costed_actual_pct = sum(c['bac'] * c['actual_pct'] for c in costed) / total_bac
    else:
        costed_planned_pct = costed_actual_pct = 0.0

    pv = total_bac * costed_planned_pct
    ev = total_bac * costed_actual_pct
    spi = (costed_actual_pct / costed_planned_pct) if costed_planned_pct else None
    cpi = (ev / total_ac) if total_ac else None
    variance = ev - pv

    # Delay = float of the project finish milestone, in whole working days.
    # Prefer an actual Finish Milestone; fall back to the latest-finishing activity.
    with_finish = [r for r in records if r['activity']['planned_finish']]
    delay_days = None
    if with_finish:
        milestones = [r for r in with_finish if r['activity'].get('task_type') == 'FinishMilestone']
        pool = milestones or with_finish
        milestone = max(pool, key=lambda r: r['activity']['planned_finish'])
        a = milestone['activity']
        if a.get('tf_from_hours'):
            # P6's stored float (XER) — authoritative, use as-is.
            tf = milestone['total_float']
            delay_days = round(tf) if tf is not None else None
        else:
            # Reconstructed (XML): recompute boundary-correct so Delay matches P6 and the XER.
            cal = data.calendars.get(a['calendar_id'])
            es, ls = a.get('remaining_early_start'), a.get('remaining_late_start')
            fw = float_working_days(cal, es, ls) if (cal and es and ls) else None
            tf = milestone['total_float']
            delay_days = fw if fw is not None else (round(tf) if tf is not None else None)

    return {
        'data_date': data_date,
        'categories': category_results,
        'overall_planned_pct': overall_planned_pct,
        'overall_actual_pct': overall_actual_pct,
        'pv': pv,
        'ev': ev,
        'ac': total_ac,
        'spi': spi,
        'cpi': cpi,
        'variance': variance,
        'delay_days': delay_days,
        'records': records,
    }
