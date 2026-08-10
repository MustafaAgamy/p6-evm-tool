import xml.etree.ElementTree as ET

import pytest

from p6_claims import fragnet

NS = 'http://xmlns.oracle.com/Primavera/P6/V8.2/API/BusinessObjects'


def _xml(with_ns=True):
    xmlns = f' xmlns="{NS}"' if with_ns else ''
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<APIBusinessObjects{xmlns}>
  <Project>
    <ObjectId>1</ObjectId>
    <Id>PRJ</Id>
    <Name>Test</Name>
    <Activity>
      <ObjectId>OX1</ObjectId>
      <Id>X1</Id>
      <Name>Impacted activity</Name>
      <Status>Not Started</Status>
      <CalendarObjectId>C1</CalendarObjectId>
      <WBSObjectId>W1</WBSObjectId>
      <PlannedDuration>80</PlannedDuration>
      <PlannedStartDate>2026-05-31T00:00:00</PlannedStartDate>
      <PlannedFinishDate>2026-06-12T00:00:00</PlannedFinishDate>
    </Activity>
  </Project>
</APIBusinessObjects>'''


def _local(root, name):
    return [e for e in root.iter() if e.tag.split('}')[-1] == name]


def _ctext(el, name):
    for c in el:
        if c.tag.split('}')[-1] == name:
            return c.text
    return None


def test_inserts_named_delay_activity_with_working_day_duration():
    out = fragnet.insert_start_delay(_xml(True), 'X1', 14, day_hours=8.0,
                                     label='Delay: late access (14 wd)')
    root = ET.fromstring(out['xml'])
    acts = _local(root, 'Activity')
    ids = {_ctext(a, 'Id') for a in acts}
    assert 'X1' in ids                     # original untouched
    assert out['delay_id'] in ids          # new delay present
    delay = next(a for a in acts if _ctext(a, 'Id') == out['delay_id'])
    assert _ctext(delay, 'Name') == 'Delay: late access (14 wd)'
    assert float(_ctext(delay, 'PlannedDuration')) == 14 * 8.0  # 112 hours


def test_adds_driving_finish_to_start_link_into_impacted():
    out = fragnet.insert_start_delay(_xml(True), 'X1', 14)
    root = ET.fromstring(out['xml'])
    rels = _local(root, 'Relationship')
    assert len(rels) == 1
    r = rels[0]
    assert _ctext(r, 'PredecessorActivityObjectId') == out['delay_oid']
    assert _ctext(r, 'SuccessorActivityObjectId') == 'OX1'
    assert _ctext(r, 'Type') == 'Finish to Start'


def test_anchors_delay_at_impacted_original_start():
    out = fragnet.insert_start_delay(_xml(True), 'X1', 3)
    root = ET.fromstring(out['xml'])
    delay = next(a for a in _local(root, 'Activity') if _ctext(a, 'Id') == out['delay_id'])
    assert _ctext(delay, 'PrimaryConstraintType') == 'Start On or After'
    assert _ctext(delay, 'PrimaryConstraintDate') == '2026-05-31T00:00:00'


def test_default_namespace_preserved_without_prefix():
    out = fragnet.insert_start_delay(_xml(True), 'X1', 5)
    assert 'ns0:' not in out['xml']
    assert f'xmlns="{NS}"' in out['xml']


def test_works_without_namespace():
    out = fragnet.insert_start_delay(_xml(False), 'X1', 7, day_hours=8.0)
    root = ET.fromstring(out['xml'])
    ids = {_ctext(a, 'Id') for a in _local(root, 'Activity')}
    assert out['delay_id'] in ids


def test_unknown_activity_raises_keyerror():
    with pytest.raises(KeyError):
        fragnet.insert_start_delay(_xml(True), 'NOPE', 5)


def test_result_is_parseable_by_the_tool_parser(tmp_path):
    out = fragnet.insert_start_delay(_xml(True), 'X1', 10, day_hours=8.0)
    p = tmp_path / 'impacted.xml'
    p.write_text(out['xml'], encoding='utf-8')
    from p6_evm.parser import parse_file
    data = parse_file(str(p))
    delay_ids = {a['id'] for a in data.activities.values()}
    assert out['delay_id'] in delay_ids
    # the driving link landed and points at the impacted activity
    assert any(r['succ_id'] == 'OX1' and r['type'] == 'FS' for r in data.relationships)
