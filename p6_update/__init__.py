"""Update Analysis — a single-file read of one schedule update against its own baseline.

Three sections: Time Status (are we behind the clock), Planned vs Actual by activity
code, and the Critical Path Analyzer (the governing completion milestone's driving
path, rolled up to WBS work fronts). All figures come from what the tool already
computes on parse — no new scheduling.
"""
from p6_update.analysis import (
    time_status, by_code, by_code_combined, critical_path, build_report_from_data,
)

__all__ = [
    'time_status', 'by_code', 'by_code_combined', 'critical_path',
    'build_report_from_data',
]
