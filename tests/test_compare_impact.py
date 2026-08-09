"""before_after — the but-for impact: delay before/after, manufactured days, forecast
completion, per-milestone before/after, and the consultant recommendation.

The assembly is pure given the two delays (positive = behind, matching the EVM tab);
before_after_from_paths wires in metrics.compute so the delay is the same number the
EVM tab shows.
"""
import textwrap
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_compare.impact import before_after, before_after_from_paths


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

def _finish_xml(tmp_path, name, float_hours):
    content = textwrap.dedent(f'''\
    <?xml version="1.0"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects">
      <Project>
        <ObjectId>1</ObjectId><Id>P1</Id><Name>Proj</Name>
        <DataDate>2026-02-09T00:00:00</DataDate>
        <Activity>
          <ObjectId>1</ObjectId><Id>M900</Id><Name>Handover</Name>
          <Type>Finish Milestone</Type><Status>Not Started</Status>
          <CalendarObjectId></CalendarObjectId><PercentComplete>0</PercentComplete>
          <PlannedStartDate>2027-02-22T08:00:00</PlannedStartDate>
          <PlannedFinishDate>2027-02-22T08:00:00</PlannedFinishDate>
          <TotalFloatHours>{float_hours}</TotalFloatHours>
        </Activity>
      </Project>
    </APIBusinessObjects>
    ''')
    p = tmp_path / name
    p.write_text(content, encoding='utf-8')
    return str(p)


def test_before_after_from_paths_wires_compute(tmp_path):
    # Different float on update vs corrected → different delays → the subtraction is exercised.
    baseline = _finish_xml(tmp_path, 'b.xml', '0')
    update = _finish_xml(tmp_path, 'u.xml', '-144')     # after changes
    corrected = _finish_xml(tmp_path, 'c.xml', '-32')   # before changes (but-for)
    r = before_after_from_paths(baseline, update, corrected)
    assert r['delay_after'] is not None and r['delay_before'] is not None
    assert r['delay_after'] != r['delay_before']                       # both != 0, milestone detected
    assert r['manufactured_days'] == r['delay_after'] - r['delay_before']
    assert abs(r['manufactured_days']) == 14                           # 18 vs 4 working days (−144 vs −32 h / 8)
    assert r['forecast']['after'] == '22-Feb-2027'
