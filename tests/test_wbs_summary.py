"""Tests for the WBS summary tree in the /api/parse response.

server.py rolls the WBS hierarchy up to the level that directly holds
activities and returns it as `wbs_summary` (a pre-order list with depth,
weighted planned/actual %, rolled-up start/finish and leaf flags) plus
`wbs_main` (the selectable top-level branches). These assert that contract.
"""
import json

import pytest


def _post_json(port, path, payload):
    import http.client
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    conn.request('POST', path, body=json.dumps(payload).encode(),
                 headers={'Content-Type': 'application/json'})
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read())


# Programme ─┬─ Engineering ── Design            (ENG-1, ahead of plan)
#            └─ Construction ─ Marine ─ Quay Wall (QW-1, QW-2, behind plan)
# BAC weights come from ResourceAssignment PlannedCost; baselines give planned%.
_TREE_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<APIBusinessObjects>\n'
    '  <Calendar><ObjectId>CAL1</ObjectId><Name>Standard</Name></Calendar>\n'
    '  <Project><ObjectId>1</ObjectId><Id>PRJ</Id><Name>Programme Project</Name>\n'
    '    <DataDate>2026-08-31T00:00:00</DataDate>\n'
    '    <CurrentBaselineProjectObjectId>10</CurrentBaselineProjectObjectId>\n'
    '    <WBS><ObjectId>1000</ObjectId><Name>Programme</Name><ParentObjectId></ParentObjectId></WBS>\n'
    '    <WBS><ObjectId>1100</ObjectId><Name>Engineering</Name><ParentObjectId>1000</ParentObjectId></WBS>\n'
    '    <WBS><ObjectId>1110</ObjectId><Name>Design</Name><ParentObjectId>1100</ParentObjectId></WBS>\n'
    '    <WBS><ObjectId>1200</ObjectId><Name>Construction</Name><ParentObjectId>1000</ParentObjectId></WBS>\n'
    '    <WBS><ObjectId>1210</ObjectId><Name>Marine</Name><ParentObjectId>1200</ParentObjectId></WBS>\n'
    '    <WBS><ObjectId>1211</ObjectId><Name>Quay Wall</Name><ParentObjectId>1210</ParentObjectId></WBS>\n'
    '    <Activity><ObjectId>O1</ObjectId><Id>ENG-1</Id><Name>Design work</Name>'
    '<CalendarObjectId>CAL1</CalendarObjectId><WBSObjectId>1110</WBSObjectId>'
    '<PercentComplete>0.60</PercentComplete><PlannedDuration>240</PlannedDuration>'
    '<PlannedStartDate>2025-12-01T00:00:00</PlannedStartDate><PlannedFinishDate>2026-10-30T00:00:00</PlannedFinishDate></Activity>\n'
    '    <Activity><ObjectId>O2</ObjectId><Id>QW-1</Id><Name>Piling</Name>'
    '<CalendarObjectId>CAL1</CalendarObjectId><WBSObjectId>1211</WBSObjectId>'
    '<PercentComplete>0.50</PercentComplete><PlannedDuration>160</PlannedDuration>'
    '<PlannedStartDate>2026-02-02T00:00:00</PlannedStartDate><PlannedFinishDate>2026-07-15T00:00:00</PlannedFinishDate></Activity>\n'
    '    <Activity><ObjectId>O3</ObjectId><Id>QW-2</Id><Name>Capping</Name>'
    '<CalendarObjectId>CAL1</CalendarObjectId><WBSObjectId>1211</WBSObjectId>'
    '<PercentComplete>0.30</PercentComplete><PlannedDuration>180</PlannedDuration>'
    '<PlannedStartDate>2026-06-01T00:00:00</PlannedStartDate><PlannedFinishDate>2026-11-30T00:00:00</PlannedFinishDate></Activity>\n'
    '    <ResourceAssignment><ActivityObjectId>O1</ActivityObjectId><PlannedCost>1000000</PlannedCost><ActualCost>600000</ActualCost></ResourceAssignment>\n'
    '    <ResourceAssignment><ActivityObjectId>O2</ActivityObjectId><PlannedCost>2000000</PlannedCost><ActualCost>1000000</ActualCost></ResourceAssignment>\n'
    '    <ResourceAssignment><ActivityObjectId>O3</ActivityObjectId><PlannedCost>1000000</PlannedCost><ActualCost>300000</ActualCost></ResourceAssignment>\n'
    '  </Project>\n'
    '  <BaselineProject>\n'
    '    <Activity><Id>ENG-1</Id><PlannedStartDate>2026-01-01T00:00:00</PlannedStartDate><PlannedFinishDate>2027-06-30T00:00:00</PlannedFinishDate></Activity>\n'
    '    <Activity><Id>QW-1</Id><PlannedStartDate>2026-01-01T00:00:00</PlannedStartDate><PlannedFinishDate>2026-09-30T00:00:00</PlannedFinishDate></Activity>\n'
    '    <Activity><Id>QW-2</Id><PlannedStartDate>2026-03-01T00:00:00</PlannedStartDate><PlannedFinishDate>2026-10-31T00:00:00</PlannedFinishDate></Activity>\n'
    '  </BaselineProject>\n'
    '</APIBusinessObjects>\n'
)


@pytest.fixture()
def tree_result(test_server, tmp_path):
    p = tmp_path / 'tree.xml'
    p.write_text(_TREE_XML, encoding='utf-8')
    _, data = _post_json(test_server, '/api/parse', {'path': str(p)})
    assert data['ok'] is True
    return data['result']


def _by_id(result):
    return {n['id']: n for n in result['wbs_summary']}


def test_wbs_main_lists_top_level_branches(tree_result):
    # sole root "Programme" -> its activity-bearing children are the branches,
    # sorted by name (Construction before Engineering).
    mains = tree_result['wbs_main']
    assert [m['name'] for m in mains] == ['Construction', 'Engineering']
    assert [m['id'] for m in mains] == ['1200', '1100']


def test_wbs_summary_tree_shape_and_depths(tree_result):
    nodes = _by_id(tree_result)
    assert nodes['1000']['depth'] == 0 and nodes['1000']['parent'] is None
    assert nodes['1100']['depth'] == 1 and nodes['1100']['parent'] == '1000'
    assert nodes['1110']['depth'] == 2 and nodes['1110']['parent'] == '1100'
    assert nodes['1211']['depth'] == 3 and nodes['1211']['parent'] == '1210'


def test_leaf_nodes_are_those_holding_activities(tree_result):
    nodes = _by_id(tree_result)
    assert nodes['1110']['leaf'] is True      # Design directly holds ENG-1
    assert nodes['1211']['leaf'] is True      # Quay Wall directly holds QW-1/QW-2
    assert nodes['1100']['leaf'] is False     # Engineering is a summary
    assert nodes['1200']['leaf'] is False     # Construction is a summary


def test_activity_counts_roll_up(tree_result):
    nodes = _by_id(tree_result)
    assert nodes['1000']['activities'] == 3
    assert nodes['1200']['activities'] == 2
    assert nodes['1211']['activities'] == 2
    assert nodes['1110']['activities'] == 1


def test_actual_pct_is_bac_weighted(tree_result):
    nodes = _by_id(tree_result)
    # Quay Wall: (2M*50 + 1M*30) / 3M = 43.3
    assert nodes['1211']['actual'] == pytest.approx(43.3, abs=0.1)
    # Programme: (1M*60 + 2M*50 + 1M*30) / 4M = 47.5
    assert nodes['1000']['actual'] == pytest.approx(47.5, abs=0.1)


def test_dates_roll_up_to_min_start_max_finish(tree_result):
    nodes = _by_id(tree_result)
    assert nodes['1211']['start'] == '2026-02-02'   # min(QW-1, QW-2)
    assert nodes['1211']['finish'] == '2026-11-30'  # max(QW-1, QW-2)
    assert nodes['1000']['start'] == '2025-12-01'   # earliest across all
    assert nodes['1000']['finish'] == '2026-11-30'  # latest across all


def test_baseline_dates_roll_up_from_baseline_project(tree_result):
    # Baseline start/finish come from the BaselineProject activities, keyed by Id,
    # and roll up min-start / max-finish exactly like the expected dates do.
    nodes = _by_id(tree_result)
    # Quay Wall: QW-1 [01 Jan 26 → 30 Sep 26], QW-2 [01 Mar 26 → 31 Oct 26]
    assert nodes['1211']['baseline_start'] == '2026-01-01'
    assert nodes['1211']['baseline_finish'] == '2026-10-31'
    # Design (ENG-1) carries the latest baseline finish in the programme
    assert nodes['1110']['baseline_finish'] == '2027-06-30'
    # Programme rolls up the widest span across every branch
    assert nodes['1000']['baseline_start'] == '2026-01-01'
    assert nodes['1000']['baseline_finish'] == '2027-06-30'


def test_baseline_dates_distinct_from_expected(tree_result):
    # The two date pairs are independent: Quay Wall's expected finish (30 Nov 26)
    # differs from its baseline finish (31 Oct 26), which is what drives Delay.
    nodes = _by_id(tree_result)
    qw = nodes['1211']
    assert qw['finish'] == '2026-11-30' and qw['baseline_finish'] == '2026-10-31'
    assert qw['finish'] != qw['baseline_finish']


def test_planned_present_and_behind_vs_ahead(tree_result):
    nodes = _by_id(tree_result)
    # baselines supplied -> planned% is computed (not None)
    assert nodes['1211']['planned'] is not None
    assert nodes['1110']['planned'] is not None
    # Quay Wall is behind plan (planned > actual); Design is ahead (actual > planned)
    assert nodes['1211']['planned'] > nodes['1211']['actual']
    assert nodes['1110']['actual'] > nodes['1110']['planned']


def test_pre_order_branch_precedes_descendants(tree_result):
    order = [n['id'] for n in tree_result['wbs_summary']]
    # Construction appears before its Marine/Quay Wall descendants
    assert order.index('1200') < order.index('1210') < order.index('1211')
