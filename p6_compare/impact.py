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
        'recommendation': _recommendation(delay_before, delay_after, manufactured, forecast),
    }


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
    baseline = parse_file(baseline_path)
    update = parse_file(update_path)
    corrected = parse_file(corrected_path)
    return before_after(baseline, update, corrected,
                        _delay(update, config), _delay(corrected, config))
