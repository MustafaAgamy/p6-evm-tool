"""Update vs Update — Windows Analysis.

Compares two consecutive P6 updates (previous period -> current period): the
progress earned this period against what the *previous update itself* forecast for
it, the activity-level % complete variance, the schedule/critical-path movement in
this window, a period S-curve (actual vs last period's forecast) and a milestone
finish trend across every stored update.

Reference is the PREVIOUS update, not the baseline — the sibling of p6_compare
(Baseline vs Current Update). Reuses p6_compare (MatchedSchedules, driving_pairs,
diff_relationships, diff_durations) and p6_evm.metrics numbers so figures match the
EVM tab. The tool never computes a schedule date itself.

Progress is measured against last period's forecast (Option B); the period index is
"forecast achievement", never "SPI". Isolated from p6_evm compute — read-only reuse.
"""

__version__ = "1.0"
