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


def _critical_from_paths(data):
    """When a schedule carries no per-activity float (a common baseline export), its critical
    activities are the ones on its critical (longest) path — the driving chain to the GOVERNING
    finish milestone (the one that sets project completion), which is exactly what the path
    length and CPLI are measured against. Returns a set of activity ObjectIds.

    NB: we trace ONLY the governing milestone, not every finish milestone. Unioning all finish
    milestones would count activities on lower-float zone/phase paths as critical — in a floated
    schedule those carry positive float (TF > 0) and are NOT critical, so unioning inflates the
    count toward 100%."""
    from p6_critpath.paths import _governing_finish_ms, trace_driving_chain
    from p6_audit.graph import ScheduleGraph
    gov = _governing_finish_ms(data)
    if not gov:
        return set()
    start = next((k for k, v in data.activities.items() if v is gov), None)
    if not start:
        return set()
    graph = ScheduleGraph(data)
    oids = set()
    for oid in trace_driving_chain(graph, start):
        a = data.activities.get(oid)
        if a and a.get('task_type') not in _MILESTONES:
            oids.add(oid)
    return oids


def schedule_census(data, near_threshold=NEAR_THRESHOLD):
    """One schedule's critical-path headline: how many activities are critical and near-
    critical (count + % of the counted activities), the remaining critical-path length
    (working days, data date → governing forecast finish), the governing finish milestone's
    total float, and the CPLI.

    When the export carries per-activity float, critical = TF ≤ 0 and near = 0 < TF < 10 wd.
    When it carries NO float (e.g. an unscheduled baseline), critical is derived from the
    critical/longest path so it is still counted, and near-critical is reported as unknown
    (n/a) because it can't be judged without float."""
    non_ms = [a for a in data.activities.values() if a.get('task_type') not in _MILESTONES]
    floated = [a for a in non_ms if a.get('total_float_days') is not None]

    if floated:
        total = len(floated)
        critical = sum(1 for a in floated if a['total_float_days'] <= 0)
        near = sum(1 for a in floated if 0 < a['total_float_days'] < near_threshold)
        source = 'float'
    else:
        total = len(non_ms)
        crit_oids = _critical_from_paths(data)
        critical = sum(1 for k, a in data.activities.items()
                       if k in crit_oids and a.get('task_type') not in _MILESTONES)
        near = None
        source = 'path'
    pct = lambda n: (round(n / total * 100, 1) if (total and n is not None) else (None if n is None else 0.0))

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
        'critical_source': source,          # 'float' (TF≤0) or 'path' (derived, no float in file)
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


def _lanes_for_milestone(schedules, roles, milestone_code, summary_level):
    """One driving-path lane per schedule for ONE finish milestone. The CURRENT lane
    highlights the NEW critical path: boxes that entered vs the comparison base are 'new',
    boxes that left are appended as 'left' ghosts. Baseline/previous lanes are reference."""
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
            left_boxes = []
            for gb in diff['left']:                       # work fronts that left the path
                g = dict(gb)
                g['state'] = 'left'
                left_boxes.append(g)
            # Insert the LEFT boxes inline at the reroute point — right before the first NEW box —
            # so the chain reads shared/stayed → [LEFT] → arrow → NEW (Ibrahim's sketch), instead
            # of dangling the left boxes at the very end.
            insert_at = next((i for i, b in enumerate(boxes) if b['state'] == 'new'), len(boxes))
            boxes = boxes[:insert_at] + left_boxes + boxes[insert_at:]
        else:
            for b in boxes:
                b['state'] = 'done' if b.get('complete') else 'stayed'
        lanes.append({'role': role, 'label': ROLE_LABEL[role], 'sub': _lane_sub(role, p['milestone']),
                      'milestone': p['milestone'], 'boxes': boxes})
    return lanes


def _build_milestone_paths(schedules, roles, summary_level):
    """The Critical Path Analyzer view: one path block per finish milestone that affects
    completion (governing first), each with its lanes across schedules and the reroute
    highlight. Milestones with no driving path in any schedule are skipped."""
    from p6_critpath.paths import milestone_list
    out = []
    for ms in milestone_list(schedules):
        lanes = _lanes_for_milestone(schedules, roles, ms['id'], summary_level)
        if not any(ln.get('boxes') for ln in lanes):
            continue                                     # no path anywhere → doesn't drive anything
        cur = next((ln for ln in lanes if ln['role'] == 'current'), lanes[-1])
        cur_ms = cur.get('milestone') or {}
        out.append({
            'id': ms['id'], 'name': ms['name'], 'is_governing': ms['is_governing'],
            'baseline_finish': cur_ms.get('baseline_finish'),
            'current_finish': cur_ms.get('expected_finish'),
            'slip_days': cur_ms.get('slip_days'),
            'lanes': lanes,
        })
    return out


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

    # Every finish milestone's driving path (the Critical Path Analyzer view). The governing
    # milestone's lanes are also exposed as `lanes` so the dashboard/narrative can read the
    # reroute off the path that decides the project finish.
    milestone_paths = _build_milestone_paths(schedules, roles, summary_level)
    gov_block = next((m for m in milestone_paths if m['is_governing']), milestone_paths[0] if milestone_paths else None)

    report = {
        'mode': mode,
        'roles': roles,
        'census': census,
        'data_dates': {r: census[r]['data_date'] for r in roles},
        'milestones_list': milestone_list(schedules),
        'summary_level': summary_level,
        'milestone_paths': milestone_paths,
        'lanes': gov_block['lanes'] if gov_block else [],
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
