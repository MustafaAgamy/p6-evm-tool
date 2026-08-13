"""Assemble the Consultant Review report dict (Baseline vs Current Update).

Slice 1 fills the header, dashboard counts, the driving logic & lag change table,
the duration/remaining table, the change summary, and milestone finishes (baseline
vs update). The before/after but-for impact and the three-way S-curve are filled in
Slice 2, once the corrected XML has been rescheduled in P6 and re-imported.
"""
from p6_audit.graph import ScheduleGraph
from p6_compare.model import MatchedSchedules
from p6_compare.diff import driving_pairs, diff_relationships, diff_durations
from p6_compare.revert import revert_operations
from p6_evm.parser import parse_file
from p6_evm.classify import classify_branch_names
from p6_evm.metrics import wbs_ancestor_names

_EXCLUDE_CATEGORIES = ('Engineering', 'Design', 'Procurement')

_KIND_LABEL = {
    'lag': 'driving lag changed',
    'type': 'relationship type changed',
    'added_driver': 'driving predecessor added',
    'removed_driver': 'driving link removed',
    'removed_added': 'link removed + new added',
}
_DUR_LABEL = {'extended': 'duration extended', 'not_burning': 'not burning down'}


def _fmt(d):
    return d.strftime('%d-%b-%Y') if hasattr(d, 'strftime') else None


def _project_finish(data):
    """Schedule finish for the dashboard: the project ScheduledFinishDate, else the
    latest activity finish. The XER reader stores no project finish, so an XER baseline
    would otherwise come up blank."""
    proj = data.project or {}
    if proj.get('scheduled_finish'):
        return proj['scheduled_finish']
    fins = [a.get('planned_finish') for a in data.activities.values() if a.get('planned_finish')]
    return max(fins) if fins else None


def _finish_delay_working_days(update, bf_date, uf_date):
    """Working days the completion date slipped vs the baseline (positive = later) — the
    'Finish − Baseline Finish' variance a planner reads in P6, and the honest delay when
    the export carries no reliable total float. Uses the calendar of the latest-finishing
    update activity (the finish driver); falls back to calendar days if no calendar."""
    if not (bf_date and uf_date):
        return None
    driver = max((a for a in update.activities.values() if a.get('planned_finish')),
                 key=lambda a: a['planned_finish'], default=None)
    cal = (getattr(update, 'calendars', {}) or {}).get(driver.get('calendar_id')) if driver else None
    if cal is None:
        return (uf_date - bf_date).days
    try:
        from p6_evm.calendars import signed_working_days
        return round(signed_working_days(cal, bf_date, uf_date))
    except Exception:
        return (uf_date - bf_date).days


def _construction_codes(data):
    """Codes to KEEP for the change tables: construction/execution work only. Keeps only
    **Task Dependent** activities (Ibrahim's rule) — this drops milestones, LOE, WBS
    summaries and resource-dependent rows in one stroke — and further drops engineering /
    design / procurement WBS phases (the submittals, approvals and deliveries). Uses a
    WBS exclude-list (not an allow-list) so genuine construction under an oddly-named
    branch is still kept rather than silently dropped."""
    out = set()
    for a in data.activities.values():
        code = a.get('id')
        if not code or a.get('task_type') != 'Task':   # Task Dependent only
            continue
        cat = classify_branch_names(wbs_ancestor_names(a.get('wbs_id'), data.wbs))
        if cat in _EXCLUDE_CATEGORIES:
            continue
        out.add(code)
    return out


def build_report_from_data(baseline, update, config=None):
    config = config or {}
    matched = MatchedSchedules(baseline, update)
    logic = diff_relationships(matched, driving_pairs(ScheduleGraph(update)))
    durations = diff_durations(matched)

    # Corrected-XML revert plan restores the FULL baseline logic (all relationships/lags +
    # all changed durations) — computed BEFORE the display filter below, so the corrected
    # file returns every baseline relationship, not just the construction subset shown.
    revert_ops = revert_operations(matched, logic, durations)

    # Keep only construction/execution activities (Ibrahim's rule) — the tables were
    # drowning in submittals, approvals, deliveries and milestones. Recompute the counts.
    cons = _construction_codes(update)
    logic['rows'] = [r for r in logic['rows'] if r['activity_id'] in cons]
    durations['rows'] = [r for r in durations['rows'] if r['activity_id'] in cons]
    _by_kind = {}
    for r in logic['rows']:
        _by_kind[r['primary_kind']] = _by_kind.get(r['primary_kind'], 0) + 1
    logic['summary'] = {'changed_activities': len(logic['rows']), 'by_kind': _by_kind}
    _dur_counts = {}
    for r in durations['rows']:
        _dur_counts[r['status']] = _dur_counts.get(r['status'], 0) + 1
    durations['counts'] = _dur_counts

    # Tag each summary item with its group so the dashboard "how the logic changed"
    # chart can pick out the logic kinds without re-listing them.
    items = [{'kind': k, 'label': _KIND_LABEL.get(k, k), 'count': n, 'group': 'logic'}
             for k, n in logic['summary']['by_kind'].items()]
    items += [{'kind': k, 'label': _DUR_LABEL.get(k, k), 'count': n, 'group': 'duration'}
              for k, n in durations['counts'].items()]

    # Reconcile the two "changed activities" numbers the user sees: the dashboard total
    # is the union of logic- and duration-changed activities; the table heading is the
    # logic subset. Split the total into logic_changed + duration_only (disjoint) so
    # logic_changed + duration_only == changed_activities exactly — no apparent conflict.
    logic_ids = {r['activity_id'] for r in logic['rows']}
    duration_ids = {r['activity_id'] for r in durations['rows']}
    changed_ids = logic_ids | duration_ids
    duration_only_ids = duration_ids - logic_ids

    # Finish slip for the dashboard chart: signed days the completion date moved
    # (positive = the update finishes later than the baseline). Raw dates kept so
    # baseline_finish / update_finish below format the same value.
    bf_date, uf_date = _project_finish(baseline), _project_finish(update)
    finish_slip_days = (uf_date - bf_date).days if (bf_date and uf_date) else None
    delay_working_days = _finish_delay_working_days(update, bf_date, uf_date)

    # Instant but-for delay (NO F9): forward-pass the update with the revert plan applied in
    # memory (baseline logic/durations restored), then measure its finish vs baseline. The tool
    # schedules it — an ESTIMATE, validated to reproduce P6's F9 finish on a progressed schedule
    # to the day. 'manufactured' = how many of the reported delay days the edits added.
    from p6_compare.schedule import but_for_finish as _but_for_finish
    try:
        bfr_date = _but_for_finish(update, revert_ops)
    except Exception:
        bfr_date = None
    butfor_delay_wd = _finish_delay_working_days(update, bf_date, bfr_date) if bfr_date else None
    manufactured_wd = ((delay_working_days - butfor_delay_wd)
                       if (delay_working_days is not None and butfor_delay_wd is not None) else None)

    milestones = []
    for code in matched.milestone_codes:
        b = matched.baseline_by_code[code]
        u = matched.update_by_code[code]
        milestones.append({
            'activity_id': code,
            'name': u.get('name', ''),
            'baseline_finish': _fmt(b.get('planned_finish')),
            'update_finish': _fmt(u.get('planned_finish') or u.get('remaining_early_finish')),
        })

    return {
        'project_name': (update.project or {}).get('name') or '',
        'data_date': _fmt((update.project or {}).get('data_date')),
        'baseline_finish': _fmt(bf_date),
        'update_finish': _fmt(uf_date),
        # Guard against a wrong baseline pick: if almost nothing matches by Activity ID,
        # an empty report means "these files don't line up", not "no changes".
        'matched_activities': len(matched.matched_codes),
        'update_activity_count': len(update.activities),
        'dashboard': {'changed_activities': len(changed_ids),
                      'logic_changed': len(logic_ids),
                      'duration_only': len(duration_only_ids),
                      'finish_slip_days': finish_slip_days,
                      'delay_working_days': delay_working_days,
                      'butfor_finish': _fmt(bfr_date),
                      'butfor_delay_working_days': butfor_delay_wd,
                      'manufactured_working_days': manufactured_wd},
        'change_summary': {'changed_activities': logic['summary']['changed_activities'], 'items': items},
        'logic': logic,
        'durations': durations,
        'milestones': milestones,
        # Corrected but-for XML: the revert plan (ALL relationships/lags + changed durations
        # back to baseline). Computed above from the unfiltered diff.
        'revert_ops': revert_ops,
    }


def build_report(baseline_path, update_path, config=None):
    """Parse a baseline (XER/XML) and update (XML/XER), then build the report."""
    return build_report_from_data(parse_file(baseline_path), parse_file(update_path), config)
