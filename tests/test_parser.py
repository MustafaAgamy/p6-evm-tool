"""Tests for p6_evm/parser.py — parse_file() and ScheduleData population."""
from datetime import datetime
from pathlib import Path

import pytest

from p6_evm.parser import parse_file, ScheduleData


# ── Fixture parse (reused across tests) ───────────────────────────────────

@pytest.fixture(scope='module')
def parsed(xml_path):
    return parse_file(str(xml_path))


# ── ScheduleData type ──────────────────────────────────────────────────────

def test_parse_returns_schedule_data(parsed):
    assert isinstance(parsed, ScheduleData)


# ── Project fields ─────────────────────────────────────────────────────────

def test_project_id(parsed):
    assert parsed.project['id'] == 'PRJ-001'

def test_project_name(parsed):
    assert parsed.project['name'] == 'Test Project'

def test_project_data_date(parsed):
    assert parsed.project['data_date'] == datetime(2024, 7, 1)

def test_project_object_id(parsed):
    assert parsed.project['object_id'] == '1'


# ── WBS ────────────────────────────────────────────────────────────────────

def test_wbs_present(parsed):
    assert '100' in parsed.wbs

def test_wbs_name(parsed):
    assert parsed.wbs['100']['name'] == 'Phase I Construction Works'

def test_wbs_parent_empty(parsed):
    # ParentObjectId tag is present but empty → None or ''
    assert parsed.wbs['100']['parent_object_id'] in (None, '')


# ── Activities ─────────────────────────────────────────────────────────────

def test_activity_count(parsed):
    assert len(parsed.activities) == 2

def test_activity_fields_obj001(parsed):
    act = parsed.activities['OBJ001']
    assert act['id'] == 'ACT001'
    assert act['name'] == 'Activity One'
    assert act['wbs_id'] == '100'
    assert act['percent_complete'] == pytest.approx(0.5)
    assert act['planned_duration'] == pytest.approx(180.0)
    assert act['calendar_id'] == 'CAL1'

def test_activity_planned_dates(parsed):
    act = parsed.activities['OBJ001']
    assert act['planned_start'] == datetime(2024, 1, 1)
    assert act['planned_finish'] == datetime(2024, 7, 1)

def test_activity_not_started_pct(parsed):
    assert parsed.activities['OBJ002']['percent_complete'] == pytest.approx(0.0)


# ── Calendar ───────────────────────────────────────────────────────────────

def test_calendar_present(parsed):
    assert 'CAL1' in parsed.calendars

def test_calendar_name(parsed):
    assert parsed.calendars['CAL1'].name == 'Standard Calendar'

def test_calendar_saturday_nonworking(parsed):
    assert 'Saturday' in parsed.calendars['CAL1'].nonworking_days

def test_calendar_sunday_nonworking(parsed):
    assert 'Sunday' in parsed.calendars['CAL1'].nonworking_days


# ── Baseline ───────────────────────────────────────────────────────────────

def test_baseline_act001_present(parsed):
    assert 'ACT001' in parsed.baseline_by_id

def test_baseline_act001_dates(parsed):
    b = parsed.baseline_by_id['ACT001']
    assert b['planned_start'] == datetime(2024, 1, 1)
    assert b['planned_finish'] == datetime(2024, 1, 1)

def test_baseline_act002_dates(parsed):
    b = parsed.baseline_by_id['ACT002']
    assert b['planned_start'] == datetime(2024, 7, 1)
    assert b['planned_finish'] == datetime(2024, 12, 31)


# ── Resource assignments ───────────────────────────────────────────────────

def test_bac_obj001(parsed):
    assert parsed.bac_by_activity['OBJ001'] == pytest.approx(1000.0)

def test_ac_obj001(parsed):
    assert parsed.ac_by_activity['OBJ001'] == pytest.approx(800.0)

def test_bac_obj002(parsed):
    assert parsed.bac_by_activity['OBJ002'] == pytest.approx(2000.0)

def test_ac_obj002_zero(parsed):
    assert parsed.ac_by_activity.get('OBJ002', 0.0) == pytest.approx(0.0)


# ── Multiple resource assignments accumulate ───────────────────────────────

def test_multiple_assignments_accumulate(tmp_path):
    xml = '''\
<?xml version="1.0" encoding="UTF-8"?>
<APIBusinessObjects>
  <Project>
    <ObjectId>1</ObjectId>
    <Id>P1</Id>
    <Name>Test</Name>
    <DataDate>2024-07-01T00:00:00</DataDate>
    <Activity>
      <ObjectId>A1</ObjectId>
      <Id>ACT001</Id>
      <Name>Act</Name>
      <PercentComplete>0</PercentComplete>
      <PlannedDuration>10</PlannedDuration>
    </Activity>
    <ResourceAssignment>
      <ActivityObjectId>A1</ActivityObjectId>
      <PlannedCost>500</PlannedCost>
      <ActualCost>100</ActualCost>
    </ResourceAssignment>
    <ResourceAssignment>
      <ActivityObjectId>A1</ActivityObjectId>
      <PlannedCost>300</PlannedCost>
      <ActualCost>50</ActualCost>
    </ResourceAssignment>
  </Project>
</APIBusinessObjects>'''
    p = tmp_path / 'test.xml'
    p.write_text(xml, encoding='utf-8')
    data = parse_file(str(p))
    assert data.bac_by_activity.get('A1') == pytest.approx(800.0)
    assert data.ac_by_activity.get('A1') == pytest.approx(150.0)


# ── No baseline section ────────────────────────────────────────────────────

def test_no_baseline_section(tmp_path):
    xml = '''\
<?xml version="1.0" encoding="UTF-8"?>
<APIBusinessObjects>
  <Project>
    <ObjectId>1</ObjectId>
    <Id>P1</Id>
    <Name>Test</Name>
    <DataDate>2024-07-01T00:00:00</DataDate>
  </Project>
</APIBusinessObjects>'''
    p = tmp_path / 'test.xml'
    p.write_text(xml, encoding='utf-8')
    data = parse_file(str(p))
    assert data.baseline_by_id == {}
    assert data.activities == {}


# ── Namespace detection (xml with xmlns) ──────────────────────────────────

def test_namespaced_xml_parses(tmp_path):
    xml = '''\
<?xml version="1.0" encoding="UTF-8"?>
<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V18.8/API/BusinessObjects">
  <Project>
    <ObjectId>1</ObjectId>
    <Id>NS-001</Id>
    <Name>NS Project</Name>
    <DataDate>2024-07-01T00:00:00</DataDate>
  </Project>
</APIBusinessObjects>'''
    p = tmp_path / 'ns.xml'
    p.write_text(xml, encoding='utf-8')
    data = parse_file(str(p))
    assert data.project['id'] == 'NS-001'
    assert data.project['name'] == 'NS Project'
