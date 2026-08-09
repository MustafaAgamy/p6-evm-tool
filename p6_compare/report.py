"""Assemble the Consultant Review report dict (Baseline vs Current Update).

Slice 1 fills the header, dashboard counts, the driving logic & lag change table,
the duration/remaining table, the change summary, and milestone finishes (baseline
vs update). The before/after but-for impact and the three-way S-curve are filled in
Slice 2, once the corrected XML has been rescheduled in P6 and re-imported.
"""
from p6_audit.graph import ScheduleGraph
from p6_compare.model import MatchedSchedules
from p6_compare.diff import driving_link_map, diff_logic, diff_durations
from p6_evm.parser import parse_file

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


def build_report_from_data(baseline, update, config=None):
    config = config or {}
    matched = MatchedSchedules(baseline, update)
    logic = diff_logic(driving_link_map(ScheduleGraph(baseline)),
                       driving_link_map(ScheduleGraph(update)))
    durations = diff_durations(matched)

    items = [{'kind': k, 'label': _KIND_LABEL.get(k, k), 'count': n}
             for k, n in logic['summary']['by_kind'].items()]
    items += [{'kind': k, 'label': _DUR_LABEL.get(k, k), 'count': n}
              for k, n in durations['counts'].items()]

    changed_ids = {r['activity_id'] for r in logic['rows']} | {r['activity_id'] for r in durations['rows']}

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
        'baseline_finish': _fmt((baseline.project or {}).get('scheduled_finish')),
        'update_finish': _fmt((update.project or {}).get('scheduled_finish')),
        'dashboard': {'changed_activities': len(changed_ids)},
        'change_summary': {'changed_activities': logic['summary']['changed_activities'], 'items': items},
        'logic': logic,
        'durations': durations,
        'milestones': milestones,
    }


def build_report(baseline_path, update_path, config=None):
    """Parse a baseline (XER/XML) and update (XML/XER), then build the report."""
    return build_report_from_data(parse_file(baseline_path), parse_file(update_path), config)
