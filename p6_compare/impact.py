"""Before/after impact — the but-for comparison for the Consultant Review.

Once the corrected XML has been rescheduled (F9) in P6 and re-exported, this
compares three schedules — the baseline, the current update (**after** the changes)
and the rescheduled corrected file (**before** the changes) — and shows how much of
the reported delay was manufactured by editing the logic, lags and durations.

The delay is P6's own finish-milestone float via ``metrics.compute`` — the exact
same number the EVM tab shows — so nothing here re-derives a date. P6 did the
scheduling; the corrected file is what it scheduled.

Convention (matches the EVM tab): ``delay_days`` is **positive when behind**, so
``manufactured = delay_after - delay_before`` is positive when the edits added delay.
"""
from p6_compare.model import MatchedSchedules
from p6_compare.scurve import three_way_scurve


def _fmt(d):
    return d.strftime('%d-%b-%Y') if hasattr(d, 'strftime') else None


def _project_finish(data):
    """The schedule's finish date: the project ScheduledFinishDate, else the latest
    activity finish present."""
    proj = getattr(data, 'project', None) or {}
    if proj.get('scheduled_finish'):
        return proj['scheduled_finish']
    fins = [a.get('planned_finish') for a in getattr(data, 'activities', {}).values()
            if a.get('planned_finish')]
    return max(fins) if fins else None


def _recommendation(delay_before, delay_after, manufactured, forecast):
    if delay_before is None or delay_after is None:
        return ('Could not read a finish-milestone delay from one of the schedules — check that both the '
                'update and the rescheduled corrected file contain the project finish milestone.')
    parts = [f"The reported delay is {delay_after} working days; with the flagged relationship, lag and "
             f"duration changes reverted to the baseline it is {delay_before} working days."]
    if manufactured and manufactured > 0:
        parts.append(f"About {manufactured} of those {delay_after} working days were introduced by editing the "
                     f"schedule against the baseline, not by a shortfall in physical progress. Corrected "
                     f"forecast completion is {forecast.get('before') or '—'}.")
        parts.append(f"Recommendation: the contractor should reinstate the flagged relationships, lags and "
                     f"durations to the baseline, or substantiate each change with dated records, before the "
                     f"additional {manufactured} working days are accepted into the programme.")
    else:
        parts.append("Reverting the flagged changes does not reduce the delay — it appears driven by genuine "
                     "progress, not by logic, lag or duration manipulation.")
    return ' '.join(parts)


def before_after(baseline, update, corrected, delay_after, delay_before):
    """Assemble the before/after impact dict. Pure given the two delays (the caller
    computes them with ``metrics.compute`` so the number matches the EVM tab)."""
    manufactured = (delay_after - delay_before) if (delay_after is not None and delay_before is not None) else None

    forecast = {
        'baseline': _fmt(_project_finish(baseline)),
        'before': _fmt(_project_finish(corrected)),
        'after': _fmt(_project_finish(update)),
    }

    m_bu = MatchedSchedules(baseline, update)
    corrected_by_code = {a.get('id'): a for a in getattr(corrected, 'activities', {}).values() if a.get('id')}
    milestones = []
    for code in m_bu.milestone_codes:
        b = m_bu.baseline_by_code[code]
        u = m_bu.update_by_code[code]
        c = corrected_by_code.get(code, {})
        milestones.append({
            'activity_id': code,
            'name': u.get('name', ''),
            'baseline_finish': _fmt(b.get('planned_finish')),
            'before_finish': _fmt(c.get('planned_finish') or c.get('remaining_early_finish')),
            'after_finish': _fmt(u.get('planned_finish') or u.get('remaining_early_finish')),
        })

    return {
        'delay_before': delay_before,
        'delay_after': delay_after,
        'manufactured_days': manufactured,
        'forecast': forecast,
        'milestones': milestones,
        'scurve': three_way_scurve(baseline, update, corrected),
        'recommendation': _recommendation(delay_before, delay_after, manufactured, forecast),
    }


def _rel_sig(x):
    return None if x is None else (x.get('type'), round(x.get('lag_hours', 0.0) or 0.0, 3))


def check_corrected_file(baseline, update, corrected):
    """Guard the load-rescheduled step: is this really the rescheduled but-for file?

    Returns a plain-language warning, or None when it looks right. Two mix-ups it
    catches: (1) the user loaded the current update (none of the flagged changes are
    reverted); (2) the corrected file was loaded before F9 in P6 (baseline logic is
    back, but the finish date never moved). Non-blocking — the UI still shows results.
    """
    m_bu = MatchedSchedules(baseline, update)
    m_bc = MatchedSchedules(baseline, corrected)
    corrected_rels = m_bc.update_rels
    corrected_by_code = m_bc.update_by_code

    changed = reverted = unreverted = 0
    for key in set(m_bu.baseline_rels) | set(m_bu.update_rels):
        b, u = m_bu.baseline_rels.get(key), m_bu.update_rels.get(key)
        if _rel_sig(b) == _rel_sig(u):
            continue
        changed += 1
        c = _rel_sig(corrected_rels.get(key))
        if c == _rel_sig(b):
            reverted += 1
        elif c == _rel_sig(u):
            unreverted += 1
    for code in m_bu.matched_codes:
        bp = m_bu.baseline_by_code[code].get('planned_duration') or 0.0
        up = m_bu.update_by_code[code].get('planned_duration') or 0.0
        if abs(bp - up) <= 1e-6:
            continue
        changed += 1
        cp = (corrected_by_code.get(code, {}) or {}).get('planned_duration') or 0.0
        if abs(cp - bp) <= 1e-6:
            reverted += 1
        elif abs(cp - up) <= 1e-6:
            unreverted += 1

    if changed and reverted == 0:
        return ('This looks like the current update, not the corrected file — load the '
                '"…_but-for.xml" you generated (after rescheduling it in P6).')
    uf, cf = _project_finish(update), _project_finish(corrected)
    if reverted and uf and cf and uf == cf:
        return ('The corrected file has the baseline logic put back, but its finish date is '
                'unchanged from the update — press F9 in P6 and re-export before loading it, '
                'so the before/after uses the rescheduled dates.')
    return None


def _delay(data, config):
    """Finish-milestone delay via metrics.compute — identical to the EVM tab. None on failure."""
    from p6_evm.metrics import compute
    try:
        return compute(data, config or {'categories': []}).get('delay_days')
    except Exception:
        return None


def before_after_from_paths(baseline_path, update_path, corrected_path, config=None):
    """Route entry: parse the three files, compute both delays with metrics.compute,
    and assemble the before/after impact."""
    from p6_evm.parser import parse_file
    baseline = parse_file(baseline_path, all_projects=True)
    update = parse_file(update_path, all_projects=True)
    corrected = parse_file(corrected_path, all_projects=True)
    result = before_after(baseline, update, corrected,
                          _delay(update, config), _delay(corrected, config))
    result['warning'] = check_corrected_file(baseline, update, corrected)
    return result
