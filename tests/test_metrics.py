"""Tests for p6_evm/metrics.py — compute() and helper functions.

Fixture design (two Construction activities, no calendar → raw time ratio):
  OBJ001: baseline start=finish=2024-01-01 → planned_pct=1.0 (already past)
           percent_complete=0.5, BAC=1000, AC=800
  OBJ002: baseline start=2024-07-01, finish=2024-12-31, data_date=2024-07-01
           → ratio=0/183d=0.0, percent_complete=0.0, BAC=2000, AC=0

Expected EVM (Construction weight=1.0):
  total_bac = 3000, total_ac = 800
  planned_pct = (1000×1.0 + 2000×0.0) / 3000 = 1/3
  actual_pct  = (1000×0.5 + 2000×0.0) / 3000 = 1/6
  PV = 3000 × 1/3 = 1000
  EV = 3000 × 1/6 = 500
  AC = 800
  SPI = EV/PV = 0.5
  CPI = EV/AC = 500/800 = 0.625
  variance = EV − PV = −500
"""
from datetime import datetime

import pytest

from p6_evm.calendars import Calendar
from p6_evm.metrics import activity_planned_pct, compute
from p6_evm.parser import ScheduleData


def make_schedule():
    """Construct a ScheduleData with known values — no parse_file() needed."""
    data = ScheduleData()
    data.project = {
        'data_date': datetime(2024, 7, 1),
        'id': 'PRJ001', 'name': 'Test', 'object_id': '1',
        'baseline_object_id': None,
    }
    data.wbs = {'W1': {'name': 'Phase I Construction Works', 'parent_object_id': None}}
    data.calendars = {}   # None → raw elapsed-time ratio
    data.activities = {
        'OBJ001': {
            'object_id': 'OBJ001', 'id': 'ACT001', 'name': 'Act 1',
            'status': 'In Progress', 'calendar_id': None, 'wbs_id': 'W1',
            'percent_complete': 0.5, 'planned_duration': 180.0,
            'planned_start': datetime(2024, 1, 1),
            'planned_finish': datetime(2024, 7, 1),
            'remaining_early_start': None, 'remaining_early_finish': None,
            'remaining_late_start': None,  'remaining_late_finish': None,
        },
        'OBJ002': {
            'object_id': 'OBJ002', 'id': 'ACT002', 'name': 'Act 2',
            'status': 'Not Started', 'calendar_id': None, 'wbs_id': 'W1',
            'percent_complete': 0.0, 'planned_duration': 184.0,
            'planned_start': datetime(2024, 7, 1),
            'planned_finish': datetime(2024, 12, 31),
            'remaining_early_start': None, 'remaining_early_finish': None,
            'remaining_late_start': None,  'remaining_late_finish': None,
        },
    }
    # OBJ001 baseline: start==finish → planned_pct=1.0 when data_date≥finish
    # OBJ002 baseline: at data_date=Jul1, elapsed=0 → planned_pct=0.0
    data.baseline_by_id = {
        'ACT001': {'planned_start': datetime(2024, 1, 1), 'planned_finish': datetime(2024, 1, 1)},
        'ACT002': {'planned_start': datetime(2024, 7, 1), 'planned_finish': datetime(2024, 12, 31)},
    }
    data.bac_by_activity = {'OBJ001': 1000.0, 'OBJ002': 2000.0}
    data.ac_by_activity  = {'OBJ001': 800.0,  'OBJ002': 0.0}
    return data


@pytest.fixture
def sample_schedule():
    return make_schedule()


# ── Core EVM values ────────────────────────────────────────────────────────

def test_pv(sample_schedule, test_config):
    assert compute(sample_schedule, test_config)['pv'] == pytest.approx(1000.0)

def test_ev(sample_schedule, test_config):
    assert compute(sample_schedule, test_config)['ev'] == pytest.approx(500.0)

def test_ac(sample_schedule, test_config):
    assert compute(sample_schedule, test_config)['ac'] == pytest.approx(800.0)

def test_spi(sample_schedule, test_config):
    assert compute(sample_schedule, test_config)['spi'] == pytest.approx(0.5)

def test_cpi(sample_schedule, test_config):
    assert compute(sample_schedule, test_config)['cpi'] == pytest.approx(0.625)

def test_variance(sample_schedule, test_config):
    assert compute(sample_schedule, test_config)['variance'] == pytest.approx(-500.0)

def test_overall_pcts(sample_schedule, test_config):
    result = compute(sample_schedule, test_config)
    # weight=1.0, so overall == category pcts
    assert result['overall_planned_pct'] == pytest.approx(1 / 3)
    assert result['overall_actual_pct']  == pytest.approx(1 / 6)


# ── Null cases ─────────────────────────────────────────────────────────────

def test_spi_none_when_no_baseline(test_config):
    data = make_schedule()
    data.baseline_by_id = {}   # planned_pct → None for every activity → costed list empty
    result = compute(data, test_config)
    assert result['spi'] is None

def test_cpi_none_when_no_ac(test_config):
    data = make_schedule()
    data.ac_by_activity = {}   # no AC anywhere
    result = compute(data, test_config)
    assert result['cpi'] is None
    assert result['spi'] is not None  # SPI still computable


# ── Category classification ────────────────────────────────────────────────

def test_category_present(sample_schedule, test_config):
    cats = compute(sample_schedule, test_config)['categories']
    assert 'Construction' in cats

def test_category_activity_count(sample_schedule, test_config):
    cat = compute(sample_schedule, test_config)['categories']['Construction']
    assert cat['activity_count'] == 2

def test_no_category_match():
    data = make_schedule()
    config = {'categories': [{'name': 'Other', 'weight': 1.0, 'wbs_match': 'Nonexistent'}]}
    result = compute(data, config)
    assert result['pv'] == pytest.approx(0.0)
    assert result['ev'] == pytest.approx(0.0)
    assert result['spi'] is None


# ── Overrides ──────────────────────────────────────────────────────────────

def test_override_replaces_planned_pct(sample_schedule, test_config):
    overrides = {'Construction': {'planned_pct': 0.9}}
    cat = compute(sample_schedule, test_config, overrides=overrides)['categories']['Construction']
    assert cat['planned_pct'] == pytest.approx(0.9)
    assert cat['overridden'] is True

def test_override_replaces_actual_pct(sample_schedule, test_config):
    overrides = {'Construction': {'actual_pct': 0.7}}
    cat = compute(sample_schedule, test_config, overrides=overrides)['categories']['Construction']
    assert cat['actual_pct'] == pytest.approx(0.7)
    assert cat['overridden'] is True

def test_no_override_not_flagged(sample_schedule, test_config):
    cat = compute(sample_schedule, test_config)['categories']['Construction']
    assert cat['overridden'] is False


# ── Delay days ─────────────────────────────────────────────────────────────

def test_delay_days_none_when_no_remaining_dates(sample_schedule, test_config):
    # Fixture has no remaining_* dates → total_float = None
    result = compute(sample_schedule, test_config)
    assert result['delay_days'] is None

def test_delay_days_computed_from_milestone(test_config):
    data = make_schedule()
    cal = Calendar('C1', 'Test', nonworking_days={'Saturday', 'Sunday'})
    data.calendars = {'C1': cal}
    # OBJ002 has later planned_finish (Dec 31) — make it the milestone
    data.activities['OBJ002']['calendar_id'] = 'C1'
    data.activities['OBJ002']['remaining_early_start'] = datetime(2024, 7, 1)
    data.activities['OBJ002']['remaining_late_start']  = datetime(2024, 7, 5)
    result = compute(data, test_config)
    # signed_working_days(cal, Jul 1, Jul 5) = 4 (Tue+Wed+Thu+Fri)
    assert result['delay_days'] == 4

def test_delay_days_negative_means_ahead(test_config):
    data = make_schedule()
    cal = Calendar('C1', 'Test', nonworking_days={'Saturday', 'Sunday'})
    data.calendars = {'C1': cal}
    data.activities['OBJ002']['calendar_id'] = 'C1'
    # late_start < early_start → signed negative → ahead of schedule
    data.activities['OBJ002']['remaining_early_start'] = datetime(2024, 7, 5)
    data.activities['OBJ002']['remaining_late_start']  = datetime(2024, 7, 1)
    result = compute(data, test_config)
    assert result['delay_days'] == -4


# ── activity_planned_pct helper ────────────────────────────────────────────

def test_planned_pct_no_baseline():
    act = {'id': 'A1', 'calendar_id': None}
    assert activity_planned_pct(act, {}, datetime(2024, 7, 1), {}) is None

def test_planned_pct_before_start():
    act = {'id': 'A1', 'calendar_id': None}
    baseline = {'planned_start': datetime(2024, 7, 1), 'planned_finish': datetime(2024, 12, 31)}
    result = activity_planned_pct(act, {'A1': baseline}, datetime(2024, 1, 1), {})
    assert result == pytest.approx(0.0)

def test_planned_pct_after_finish():
    act = {'id': 'A1', 'calendar_id': None}
    baseline = {'planned_start': datetime(2024, 1, 1), 'planned_finish': datetime(2024, 6, 30)}
    result = activity_planned_pct(act, {'A1': baseline}, datetime(2024, 12, 31), {})
    assert result == pytest.approx(1.0)

def test_planned_pct_at_midpoint():
    # Jan 1 → Jul 1 = 182 days; Apr 1 = 91 days in → ratio ≈ 0.5
    act = {'id': 'A1', 'calendar_id': None}
    baseline = {'planned_start': datetime(2024, 1, 1), 'planned_finish': datetime(2024, 7, 1)}
    result = activity_planned_pct(act, {'A1': baseline}, datetime(2024, 4, 1), {})
    assert result == pytest.approx(0.5, abs=0.002)

def test_planned_pct_clamped_above_one():
    # data_date far beyond finish — should clamp to 1.0
    act = {'id': 'A1', 'calendar_id': None}
    baseline = {'planned_start': datetime(2024, 1, 1), 'planned_finish': datetime(2024, 6, 30)}
    result = activity_planned_pct(act, {'A1': baseline}, datetime(2025, 1, 1), {})
    assert result == pytest.approx(1.0)

def test_planned_pct_start_equals_finish():
    # Milestone activity: when start==finish and data_date is after → 1.0
    act = {'id': 'A1', 'calendar_id': None}
    baseline = {'planned_start': datetime(2024, 1, 1), 'planned_finish': datetime(2024, 1, 1)}
    result = activity_planned_pct(act, {'A1': baseline}, datetime(2024, 7, 1), {})
    assert result == pytest.approx(1.0)

def test_planned_pct_with_calendar():
    cal = Calendar('C1', 'Test', nonworking_days={'Saturday', 'Sunday'})
    act = {'id': 'A1', 'calendar_id': 'C1'}
    # Mon Jul 1 → Mon Jul 8: elapsed=0 working days at Jul 1 itself
    baseline = {'planned_start': datetime(2024, 7, 1), 'planned_finish': datetime(2024, 7, 8)}
    result = activity_planned_pct(act, {'A1': baseline}, datetime(2024, 7, 1), {'C1': cal})
    assert result == pytest.approx(0.0)
