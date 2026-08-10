"""Assemble the Update-vs-Update report from two consecutive updates + their metrics.

build_report_from_data is pure (takes pre-computed metrics.compute() results, so the
figures match the EVM tab); build_report is a parse+compute convenience for CLI/tests.
Slice 1: dashboard summary + activity % variance + period S-curve. Later slices fold
in critical-path movement, what-moved buckets, the conclusion and the milestone trend.
"""
from p6_compare.model import MatchedSchedules
from p6_period.progress import activity_progress, period_summary
from p6_period.scurve import period_scurve


def build_report_from_data(prev, curr, prev_metrics, curr_metrics, config=None):
    """Report dict for the two updates. `prev`/`curr` are ScheduleData; `*_metrics`
    are metrics.compute() results for each (reused for actual % and delay)."""
    matched = MatchedSchedules(prev, curr)
    summary = period_summary(prev, curr, prev_metrics, curr_metrics)
    progress = activity_progress(matched)
    scurve = period_scurve(prev, curr, summary['actual_prev'], summary['actual_now'])
    return {
        'project_name': summary['project_name'],
        'data_date_prev': summary['data_date_prev'],
        'data_date_now': summary['data_date_now'],
        # Guard against mismatched files: near-zero matches means "these don't line up".
        'matched_activities': len(matched.matched_codes),
        'update_activity_count': len(curr.activities),
        'summary': summary,
        'progress': progress,
        'scurve': scurve,
    }


def build_report(prev_path, curr_path, config=None):
    """Parse both updates, compute EVM metrics for each, then build the report."""
    import json
    from p6_evm.parser import parse_file
    from p6_evm.metrics import compute
    from utils import resource_path
    cfg = config
    if cfg is None:
        with open(resource_path('config.json')) as f:
            cfg = json.load(f)
    prev = parse_file(prev_path)
    curr = parse_file(curr_path)
    prev_m = compute(prev, cfg)
    curr_m = compute(curr, cfg)
    return build_report_from_data(prev, curr, prev_m, curr_m, cfg)
