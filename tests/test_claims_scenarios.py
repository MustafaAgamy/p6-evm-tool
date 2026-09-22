"""Tests for the what-if scenario transforms (p6_claims/scenarios.py)."""
import xml.etree.ElementTree as ET

import pytest

from p6_claims import scenarios

NS = 'http://xmlns.oracle.com/Primavera/P6/V8.2/API/BusinessObjects'


def _xml():
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<APIBusinessObjects xmlns="{NS}">
  <Calendar>
    <ObjectId>C1</ObjectId><Name>5-day</Name>
    <StandardWorkWeek>
      <StandardWorkHours><DayOfWeek>Monday</DayOfWeek><WorkTime><Start>08:00:00</Start><Finish>17:00:00</Finish></WorkTime></StandardWorkHours>
      <StandardWorkHours><DayOfWeek>Saturday</DayOfWeek></StandardWorkHours>
      <StandardWorkHours><DayOfWeek>Sunday</DayOfWeek></StandardWorkHours>
    </StandardWorkWeek>
  </Calendar>
  <Project>
    <ObjectId>1</ObjectId><Id>PRJ</Id><Name>T</Name>
    <Activity>
      <ObjectId>OX1</ObjectId><Id>X1</Id><Name>Impacted</Name>
      <Status>Not Started</Status><CalendarObjectId>C1</CalendarObjectId>
      <PlannedDuration>80</PlannedDuration><RemainingDuration>80</RemainingDuration>
      <PlannedStartDate>2026-05-31T00:00:00</PlannedStartDate><PlannedFinishDate>2026-06-12T00:00:00</PlannedFinishDate>
    </Activity>
  </Project>
</APIBusinessObjects>'''


def _local(root, name):
    return [e for e in root.iter() if e.tag.split('}')[-1] == name]


def test_shorten_cuts_remaining_duration_by_working_days():
    out = scenarios.shorten_activity(_xml(), 'X1', 5, day_hours=8.0)
    root = ET.fromstring(out['xml'])
    assert float(_local(root, 'RemainingDuration')[0].text) == 80 - 5 * 8   # 40 hours left
    assert out['activity_name'] == 'Impacted'


def test_shorten_unknown_activity_raises():
    with pytest.raises(KeyError):
        scenarios.shorten_activity(_xml(), 'NOPE', 3)


def test_six_day_adds_saturday_worktime():
    out = scenarios.set_six_day_week(_xml())
    root = ET.fromstring(out['xml'])
    sat = next(sh for sh in _local(root, 'StandardWorkHours')
               if (sh.find('{%s}DayOfWeek' % NS) is not None
                   and sh.find('{%s}DayOfWeek' % NS).text == 'Saturday'))
    assert sat.find('{%s}WorkTime' % NS) is not None
    assert out['calendars_changed'] == 1


def test_six_day_parses_as_saturday_working(tmp_path):
    out = scenarios.set_six_day_week(_xml())
    p = tmp_path / 'sixday.xml'
    p.write_text(out['xml'], encoding='utf-8')
    from p6_evm.parser import parse_file
    cal = parse_file(str(p)).calendars['C1']
    assert 'Saturday' not in cal.nonworking_days
    assert 'Saturday' in cal.work_intervals        # now a working day


def test_build_scenario_dispatches_each_kind():
    assert scenarios.build_scenario(_xml(), 'shorten', activity_id='X1', days=3)['activity_name'] == 'Impacted'
    assert 'Saturday' in scenarios.build_scenario(_xml(), 'six_day')['label']
    assert scenarios.build_scenario(_xml(), 'delay', activity_id='X1', days=7, day_hours=8.0)['label']
    with pytest.raises(ValueError):
        scenarios.build_scenario(_xml(), 'nonsense')
