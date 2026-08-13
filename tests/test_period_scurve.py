"""p6_period.scurve — period S-curve: actual to date vs last period's forecast.

The forecast curve is the PREVIOUS update's own scheduled profile (full, to 100%);
the actual curve is a ramp through the known actual readings, stopping at the current
data date (None after)."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_period.scurve import cumulative_pct, period_scurve


def _sched(spans, dd=None):
    d = ScheduleData()
    d.activities = {
        str(i): {'id': f'A{i}', 'planned_start': s, 'planned_finish': f,
                 'remaining_early_start': s, 'remaining_early_finish': f, 'planned_duration': w}
        for i, (s, f, w) in enumerate(spans)
    }
    d.project = {'data_date': dd}
    return d


def test_cumulative_linear_midpoint():
    d = _sched([(datetime(2026, 1, 1), datetime(2026, 1, 11), 100)])
    b = [datetime(2026, 1, 1), datetime(2026, 1, 6), datetime(2026, 1, 11)]
    assert cumulative_pct(d, b) == [0.0, 50.0, 100.0]


def test_period_scurve_forecast_full_actual_stops_at_now():
    dd_prev, dd_now = datetime(2026, 6, 30), datetime(2026, 7, 31)
    prev = _sched([(datetime(2026, 1, 1), datetime(2026, 12, 1), 100)], dd=dd_prev)
    curr = _sched([(datetime(2026, 1, 1), datetime(2026, 12, 1), 100)], dd=dd_now)
    sc = period_scurve(prev, curr, actual_prev=34.0, actual_now=41.0)
    assert set(sc) >= {'periods', 'forecast', 'actual', 'dd_prev_idx', 'dd_now_idx'}
    n = len(sc['periods'])
    assert n > 0 and len(sc['forecast']) == n and len(sc['actual']) == n
    assert sc['forecast'][-1] == 100.0                    # forecast runs to completion
    # actual is present up to 'now' and None strictly after it
    assert sc['actual'][sc['dd_now_idx']] is not None
    assert all(v is None for v in sc['actual'][sc['dd_now_idx'] + 1:])
    # actual reading at 'now' equals the supplied actual_now
    assert abs(sc['actual'][sc['dd_now_idx']] - 41.0) < 1e-6


def test_period_scurve_empty():
    e = ScheduleData(); e.project = {}
    sc = period_scurve(e, e, actual_prev=0.0, actual_now=0.0)
    assert sc['periods'] == [] and sc['forecast'] == [] and sc['actual'] == []
