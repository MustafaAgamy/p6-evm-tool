"""End-to-end: parse a real P6 XML → assemble the narrative document."""
import os

from p6_calendar.audit import calendar_audit
from p6_evm.parser import parse_file
from p6_narrative.builder import build_narrative

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def test_build_from_minimal_xml_has_core_sections():
    data = parse_file(FIX)
    doc = build_narrative(data, calendar_audit(data), meta={'source_name': 'minimal.xml'})
    dd = doc.to_dict()
    numbers = [s['number'] for s in dd['sections']]
    for n in ('1', '3', '3.1', '4', '5', '6', '7', '10', '13', '14'):
        assert n in numbers, f'missing section {n}'


def test_project_brief_and_costs_are_correct():
    data = parse_file(FIX)
    doc = build_narrative(data, calendar_audit(data))
    by_num = {s.number: s for s in doc.sections}
    assert any(r['k'] == 'Project name' and r['v'] == 'Test Project'
               for r in by_num['3'].payload['rows'])
    assert by_num['13'].payload['total'] == 3000.0            # 1000 + 2000
    assert by_num['14'].payload['points'][-1]['pct'] == 100.0  # cash flow ends at 100%


def test_calendars_section_comes_from_calendar_feature():
    data = parse_file(FIX)
    doc = build_narrative(data, calendar_audit(data))
    cal = next(s for s in doc.sections if s.number == '5')
    assert cal.provenance == 'calendar'
    assert cal.payload['calendars'][0]['activities'] == 2


def test_builds_without_calendar_or_codes():
    data = parse_file(FIX)
    doc = build_narrative(data)          # generic minimum — must not crash
    assert doc.sections
    assert '5' not in {s.number for s in doc.sections}   # no calendar report → no §5
