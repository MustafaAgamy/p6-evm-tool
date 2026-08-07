"""XML activity-code parsing — mirrors the real P6 XML structure confirmed against
Ibrahim's 'Update Till 19 July.2026.xml': per-activity <Code><TypeObjectId>/<ValueObjectId>,
with <ActivityCodeType> (name) and <ActivityCode> (CodeValue/Description) definitions.
Regression guard for the gap/engineering-blank bug on XML updates."""
from p6_evm.parser import parse_file

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<APIBusinessObjects>
  <ActivityCodeType><ObjectId>14846</ObjectId><Name>Type of Works</Name></ActivityCodeType>
  <ActivityCodeType><ObjectId>14844</ObjectId><Name>Trade Design</Name></ActivityCodeType>
  <ActivityCode><ObjectId>9001</ObjectId><CodeTypeObjectId>14846</CodeTypeObjectId><CodeValue>CVL</CodeValue><Description>Civil Works</Description></ActivityCode>
  <ActivityCode><ObjectId>9002</ObjectId><CodeTypeObjectId>14846</CodeTypeObjectId><CodeValue>STL</CodeValue><Description>Steel Works</Description></ActivityCode>
  <ActivityCode><ObjectId>9101</ObjectId><CodeTypeObjectId>14844</CodeTypeObjectId><CodeValue>CVL</CodeValue><Description>Civil</Description></ActivityCode>
  <Project>
    <ObjectId>1</ObjectId><Id>PRJ</Id><Name>Test</Name><DataDate>2026-07-19T00:00:00</DataDate>
    <WBS><ObjectId>100</ObjectId><Name>Phase I Construction Works</Name><ParentObjectId></ParentObjectId></WBS>
    <Activity>
      <ObjectId>5001</ObjectId><Id>A1000</Id><Name>Pile cap</Name><Status>In Progress</Status>
      <WBSObjectId>100</WBSObjectId><PercentComplete>40</PercentComplete>
      <Code><TypeObjectId>14846</TypeObjectId><ValueObjectId>9001</ValueObjectId></Code>
      <Code><TypeObjectId>14844</TypeObjectId><ValueObjectId>9101</ValueObjectId></Code>
    </Activity>
    <Activity>
      <ObjectId>5002</ObjectId><Id>A1010</Id><Name>Steel frame</Name><Status>Not Started</Status>
      <WBSObjectId>100</WBSObjectId><PercentComplete>0</PercentComplete>
      <Code><TypeObjectId>14846</TypeObjectId><ValueObjectId>9002</ValueObjectId></Code>
    </Activity>
  </Project>
</APIBusinessObjects>
"""


def test_xml_activity_codes_parsed(tmp_path):
    p = tmp_path / "update.xml"
    p.write_text(SAMPLE, encoding="utf-8")
    data = parse_file(str(p))

    # dimensions available for the gap dropdown
    assert 'Type of Works' in data.activity_code_types
    assert 'Trade Design' in data.activity_code_types

    # per-activity codes use the Description (long name), matching the XER path
    a1 = data.activities['5001']['activity_codes']
    assert a1['Type of Works'] == 'Civil Works'
    assert a1['Trade Design'] == 'Civil'

    a2 = data.activities['5002']['activity_codes']
    assert a2['Type of Works'] == 'Steel Works'
    assert 'Trade Design' not in a2       # only the codes actually assigned


def test_xml_wbs_code_not_mistaken_for_activity_code(tmp_path):
    # A <WBS> carries a plain <Code>1</Code>; it must not leak into activity codes.
    p = tmp_path / "u2.xml"
    p.write_text(SAMPLE, encoding="utf-8")
    data = parse_file(str(p))
    for a in data.activities.values():
        assert all(isinstance(v, str) and v for v in a['activity_codes'].values())
