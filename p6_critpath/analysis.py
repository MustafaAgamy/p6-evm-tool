"""Critical Path Analyzer engine.

Compares the critical path across 2–3 schedules. Every figure comes from what
each file already carries (total float, dates, driving logic) — no rescheduling,
no F9. Definitions (Ibrahim's rules, locked in the scope note):

  * Critical        total float ≤ 0
  * Near-critical   0 < total float < 10 working days   (strictly under 10)
  * Critical path length   remaining working days, data date → finish milestone
                           (a baseline has no progress → its data date is the
                           project start, so its length is the full path)
  * CPLI            (remaining length + total float) ÷ remaining length
                    to the FORECAST finish; if a schedule carries no finish
                    total float, fall back to the baseline finish; else n/a.
"""
from datetime import datetime

NEAR_THRESHOLD = 10.0                       # working days; near-critical is 0 < TF < 10
_MILESTONES = ('StartMilestone', 'FinishMilestone')


def _iso(d):
    return d.strftime('%d-%b-%Y') if isinstance(d, datetime) else None


def _forecast_finish(act):
    """P6's own forecast finish — actual finish if complete, else remaining early
    finish, else planned finish. Read from the file; never computed here."""
    return act.get('actual_finish') or act.get('remaining_early_finish') or act.get('planned_finish')


def _governing_milestone(data):
    """The completion milestone with the latest forecast finish — the one that decides
    when the project actually finishes (same rule as the EVM Delay). Falls back to the
    latest-finishing activity when the schedule carries no finish milestone."""
    fin_ms = [a for a in data.activities.values()
              if a.get('task_type') == 'FinishMilestone' and _forecast_finish(a)]
    pool = fin_ms or [a for a in data.activities.values() if _forecast_finish(a)]
    if not pool:
        return None
    return max(pool, key=_forecast_finish)


def _ref_calendar(data, act=None):
    """The calendar to count working days on — the given activity's calendar if it has
    one, else the most common calendar in the file, else None (caller falls back to
    calendar days)."""
    cals = getattr(data, 'calendars', None) or {}
    if act is not None:
        c = cals.get(act.get('calendar_id'))
        if c is not None:
            return c
    if not cals:
        return None
    # most-referenced calendar across activities
    counts = {}
    for a in data.activities.values():
        cid = a.get('calendar_id')
        if cid in cals:
            counts[cid] = counts.get(cid, 0) + 1
    if not counts:
        return next(iter(cals.values()))
    return cals[max(counts, key=counts.get)]


def _wd_between(cal, d1, d2):
    """Signed working days from d1 to d2 (positive when d2 is later). Falls back to
    calendar days when there's no calendar."""
    if not (isinstance(d1, datetime) and isinstance(d2, datetime)):
        return None
    if cal is None:
        return (d2 - d1).days
    try:
        from p6_evm.calendars import signed_working_days
        return round(signed_working_days(cal, d1, d2))
    except Exception:
        return (d2 - d1).days


def _baseline_finish(data, act):
    bl = (getattr(data, 'baseline_by_id', None) or {}).get(act.get('id'))
    return bl.get('planned_finish') if bl else None


def cpli(path_length_wd, total_float_wd):
    """CPLI = (remaining path length + total float) ÷ remaining path length.
    None when there's no length (undefined) or no float reference (n/a)."""
    if not path_length_wd:                  # None or 0
        return None
    if total_float_wd is None:
        return None
    return round((path_length_wd + total_float_wd) / path_length_wd, 2)


def _census_activities(data):
    """The activities that count toward the critical / near-critical census: real
    schedulable work (not milestones) that carries a total-float value."""
    return [a for a in data.activities.values()
            if a.get('task_type') not in _MILESTONES and a.get('total_float_days') is not None]


def schedule_census(data, near_threshold=NEAR_THRESHOLD):
    """One schedule's critical-path headline: how many activities are critical and
    near-critical (count + % of all counted activities), the remaining critical-path
    length (working days, data date → governing finish), the governing finish
    milestone's total float, and the CPLI."""
    acts = _census_activities(data)
    total = len(acts)
    critical = sum(1 for a in acts if a['total_float_days'] <= 0)
    near = sum(1 for a in acts if 0 < a['total_float_days'] < near_threshold)
    pct = lambda n: round(n / total * 100, 1) if total else 0.0

    data_date = (getattr(data, 'project', None) or {}).get('data_date')
    ms = _governing_milestone(data)
    gov_forecast = _forecast_finish(ms) if ms else None
    gov_baseline = _baseline_finish(data, ms) if ms else None
    ref_cal = _ref_calendar(data, ms)

    length = _wd_between(ref_cal, data_date, gov_forecast)
    if length is not None and length < 0:
        length = 0                          # already past the forecast finish

    # Total float on the finish milestone. Prefer the file's own value; when it carries
    # none, fall back to (baseline finish − forecast finish) in working days so CPLI stays
    # meaningful for a schedule with no finish constraint.
    total_float = ms.get('total_float_days') if ms else None
    if total_float is None and gov_baseline and gov_forecast:
        total_float = _wd_between(ref_cal, gov_forecast, gov_baseline)

    return {
        'total_activities': total,
        'critical': critical, 'critical_pct': pct(critical),
        'near': near, 'near_pct': pct(near),
        'path_length_wd': length,
        'total_float_wd': total_float,
        'cpli': cpli(length, total_float),
        'data_date': _iso(data_date),
        'gov_finish': _iso(gov_forecast),
        'gov_baseline_finish': _iso(gov_baseline),
        'gov_name': (ms.get('name') or ms.get('id')) if ms else None,
    }


ROLE_LABEL = {'baseline': 'Baseline', 'previous': 'Previous update', 'current': 'Current update'}


def _lane_sub(role, ms):
    """Short caption under a lane's tag: finish date + slip."""
    if not ms:
        return ''
    fin = ms.get('expected_finish') if role != 'baseline' else (ms.get('baseline_finish') or ms.get('expected_finish'))
    slip = ms.get('slip_days')
    bits = []
    if fin:
        bits.append(f"finishes {fin}")
    if role != 'baseline' and slip is not None:
        bits.append(f"{'+' if slip > 0 else ''}{slip} d vs baseline")
    return ' · '.join(bits)


def _build_lanes(schedules, roles, milestone_code, summary_level):
    """One driving-path lane per schedule. The CURRENT lane highlights the NEW critical
    path: boxes that entered vs the comparison base are 'new', boxes that left are appended
    as 'left' ghosts. Baseline/previous lanes are reference (no highlight)."""
    from p6_critpath.paths import path_boxes, path_diff, _box_key
    paths = {r: path_boxes(schedules[r], milestone_code, summary_level) for r in roles}
    base_role = 'previous' if 'previous' in roles else ('baseline' if 'baseline' in roles else None)

    lanes = []
    for role in roles:
        p = paths[role]
        boxes = [dict(b) for b in p['boxes']]
        if role == 'current' and base_role:
            diff = path_diff(paths[base_role]['boxes'], p['boxes'])
            entered = {_box_key(b) for b in diff['entered']}
            for b in boxes:
                b['state'] = 'new' if _box_key(b) in entered else ('done' if b.get('complete') else 'stayed')
            for gb in diff['left']:                       # dropped work fronts, shown ghosted
                g = dict(gb)
                g['state'] = 'left'
                boxes.append(g)
        else:
            for b in boxes:
                b['state'] = 'done' if b.get('complete') else 'stayed'
        lanes.append({'role': role, 'label': ROLE_LABEL[role], 'sub': _lane_sub(role, p['milestone']),
                      'milestone': p['milestone'], 'boxes': boxes})
    return lanes


def build_report(schedules, mode, near_threshold=NEAR_THRESHOLD, milestone_code=None, summary_level=0):
    """Assemble the comparison report from {role: ScheduleData} where role is
    'baseline' | 'previous' | 'current'. Census + driving-path lanes (with the new critical
    path highlighted) + the milestone list for the selector. Later slices add the every-
    milestone table, float migration, dashboard and recommendation."""
    from p6_critpath.paths import milestone_list
    from p6_critpath.tables import milestones_table, float_migration
    roles = [r for r in ('baseline', 'previous', 'current') if r in schedules]
    census = {r: schedule_census(schedules[r], near_threshold) for r in roles}

    # Float migration is the period movement: previous → current when both are loaded,
    # else baseline → current.
    base_role = 'previous' if 'previous' in schedules else ('baseline' if 'baseline' in schedules else None)
    migration = (float_migration(schedules[base_role], schedules['current'], near_threshold)
                 if base_role and 'current' in schedules else None)

    report = {
        'mode': mode,
        'roles': roles,
        'census': census,
        'data_dates': {r: census[r]['data_date'] for r in roles},
        'milestones_list': milestone_list(schedules),
        'selected_milestone': milestone_code,
        'summary_level': summary_level,
        'lanes': _build_lanes(schedules, roles, milestone_code, summary_level),
        'milestones': milestones_table(schedules, near_threshold),
        'float_migration': migration,
        'float_migration_base': base_role,
    }
    from p6_critpath.dashboard import build_dashboard, build_narrative
    report['dashboard'] = build_dashboard(report)
    narrative = build_narrative(report)
    report['effect'] = narrative['effect']
    report['recommendation'] = narrative['recommendation']
    report['conclusion'] = narrative['conclusion']
    return report
