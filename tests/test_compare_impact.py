"""before_after — the but-for impact: delay before/after, manufactured days, forecast
completion, per-milestone before/after, and the consultant recommendation.

The assembly is pure given the two delays (positive = behind, matching the EVM tab);
before_after_from_paths wires in metrics.compute so the delay is the same number the
EVM tab shows.
"""
import textwrap
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_compare.impact import before_after, before_after_from_paths, check_corrected_file


def _sched(finish, milestone_finish):
    d = ScheduleData()
    d.project = {'name': 'P', 'scheduled_finish': finish, 'data_date': datetime(2026, 2, 9)}
    d.activities = {
        'm': {'id': 'M900', 'name': 'Handover', 'task_type': 'FinishMilestone', 'calendar_id': None,
              'planned_finish': milestone_finish},
    }
    return d


# ── pure assembly ──────────────────────────────────────────────────────────

def test_before_after_manufactured_forecast_milestones_recommendation():
    baseline = _sched(datetime(2027, 2, 9), datetime(2027, 2, 9))
    corrected = _sched(datetime(2027, 2, 15), datetime(2027, 2, 15))   # before changes (but-for)
    update = _sched(datetime(2027, 2, 22), datetime(2027, 2, 22))      # after changes (reported)
    r = before_after(baseline, update, corrected, delay_after=18, delay_before=4)
    assert (r['delay_after'], r['delay_before'], r['manufactured_days']) == (18, 4, 14)
    assert r['forecast'] == {'baseline': '09-Feb-2027', 'before': '15-Feb-2027', 'after': '22-Feb-2027'}
    m = r['milestones'][0]
    assert m['activity_id'] == 'M900'
    assert (m['baseline_finish'], m['before_finish'], m['after_finish']) == \
           ('09-Feb-2027', '15-Feb-2027', '22-Feb-2027')
    assert '18 working days' in r['recommendation'] and '4 working days' in r['recommendation']
    assert 'About 14' in r['recommendation'] and '15-Feb-2027' in r['recommendation']


def test_before_after_genuine_when_delay_unchanged():
    s = _sched(datetime(2027, 2, 22), datetime(2027, 2, 22))
    base = _sched(datetime(2027, 2, 9), datetime(2027, 2, 9))
    r = before_after(base, s, s, delay_after=18, delay_before=18)
    assert r['manufactured_days'] == 0
    assert 'genuine progress' in r['recommendation']


def test_before_after_handles_missing_delay():
    s = _sched(datetime(2027, 2, 22), datetime(2027, 2, 22))
    base = _sched(datetime(2027, 2, 9), datetime(2027, 2, 9))
    r = before_after(base, s, s, delay_after=None, delay_before=5)
    assert r['manufactured_days'] is None
    assert 'finish milestone' in r['recommendation']


# ── end-to-end wiring: three files → parse → compute → assemble ─────────────

def _finish_xml(tmp_path, name, finish):
    """A one-milestone schedule whose project finish is `finish` (YYYY-MM-DD) — so the
    date-based delay (finish variance vs baseline) can be exercised."""
    content = textwrap.dedent(f'''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Project>
        <ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name>
        <DataDate>2026-06-30T00:00:00</DataDate>
        <Activity>
          <ObjectId>1</ObjectId><Id>M900</Id><Name>Handover</Name>
          <Type>Finish Milestone</Type><Status>Not Started</Status>
          <CalendarObjectId></CalendarObjectId><PercentComplete>0</PercentComplete>
          <PlannedStartDate>{finish}T08:00:00</PlannedStartDate>
          <PlannedFinishDate>{finish}T08:00:00</PlannedFinishDate>
        </Activity>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / name
    p.write_text(content, encoding='utf-8')
    return str(p)


# ── check_corrected_file (guard the load-rescheduled step) ─────────────────

def _sched_with_rel(finish, lag_hours):
    d = ScheduleData()
    d.project = {'scheduled_finish': finish, 'data_date': datetime(2026, 2, 9)}
    d.activities = {
        'p': {'id': 'A050', 'name': 'Clearance', 'planned_duration': 80},
        's': {'id': 'A100', 'name': 'Excavate', 'planned_duration': 80},
    }
    d.relationships = [{'pred_id': 'p', 'succ_id': 's', 'type': 'FS',
                        'lag_days': lag_hours / 8.0, 'lag_hours': lag_hours}]
    return d


def test_check_ok_when_reverted_and_rescheduled():
    baseline = _sched_with_rel(datetime(2027, 2, 9), 0)
    update = _sched_with_rel(datetime(2027, 2, 22), 80)
    corrected = _sched_with_rel(datetime(2027, 2, 15), 0)   # reverted lag + finish moved
    assert check_corrected_file(baseline, update, corrected) is None


def test_check_warns_when_file_is_the_update():
    baseline = _sched_with_rel(datetime(2027, 2, 9), 0)
    update = _sched_with_rel(datetime(2027, 2, 22), 80)
    corrected = _sched_with_rel(datetime(2027, 2, 22), 80)  # nothing reverted (still == update)
    w = check_corrected_file(baseline, update, corrected)
    assert w and 'current update' in w


def test_check_warns_when_not_rescheduled():
    baseline = _sched_with_rel(datetime(2027, 2, 9), 0)
    update = _sched_with_rel(datetime(2027, 2, 22), 80)
    corrected = _sched_with_rel(datetime(2027, 2, 22), 0)   # reverted but finish unchanged from update
    w = check_corrected_file(baseline, update, corrected)
    assert w and 'F9' in w


def test_before_after_from_paths_date_based_delay(tmp_path):
    # Delay is the finish-date variance vs baseline (no calendar → calendar days). Reported =
    # update finish − baseline; but-for = corrected finish − baseline; manufactured = the gap.
    baseline = _finish_xml(tmp_path, 'b.xml', '2026-10-19')
    update = _finish_xml(tmp_path, 'u.xml', '2026-12-24')     # after changes (66 days behind)
    corrected = _finish_xml(tmp_path, 'c.xml', '2026-11-10')  # before changes / but-for (22 behind)
    r = before_after_from_paths(baseline, update, corrected)
    assert r['delay_after'] == 66      # reported delay, finish variance vs baseline
    assert r['delay_before'] == 22     # but-for delay (baseline logic rescheduled)
    assert r['manufactured_days'] == 44                                # 66 − 22, added by the edits
    assert r['forecast']['after'] == '24-Dec-2026'
    assert r['forecast']['before'] == '10-Nov-2026'
