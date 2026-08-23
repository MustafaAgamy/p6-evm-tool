"""Critical Path Analyzer — compare the critical path across 2–3 schedules
(two updates / update-vs-baseline / two updates + baseline).

Reads the float, dates and driving logic already in each file — no new
scheduling, no F9. Critical = total float ≤ 0; near-critical = 0 < TF < 10 wd.
Critical path length = remaining working days from the data date to the finish
milestone. CPLI = (remaining length + total float) ÷ remaining length.
"""
from p6_critpath.analysis import cpli, schedule_census, build_report

__all__ = ['cpli', 'schedule_census', 'build_report']
