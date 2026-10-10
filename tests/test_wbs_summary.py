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
    '<PlannedStartDate>2025-12-01T00:00:00</PlannedStartDate><PlannedFinishDate>2026-10-30T16:00:00</PlannedFinishDate></Activity>\n'
    '    <Activity><ObjectId>O2</ObjectId><Id>QW-1</Id><Name>Piling</Name>'
    '<CalendarObjectId>CAL1</CalendarObjectId><WBSObjectId>1211</WBSObjectId>'
    '<PercentComplete>0.50</PercentComplete><PlannedDuration>160</PlannedDuration>'
    '<PlannedStartDate>2026-02-02T00:00:00</PlannedStartDate><PlannedFinishDate>2026-07-15T16:00:00</PlannedFinishDate></Activity>\n'
    '    <Activity><ObjectId>O3</ObjectId><Id>QW-2</Id><Name>Capping</Name>'
    '<CalendarObjectId>CAL1</CalendarObjectId><WBSObjectId>1211</WBSObjectId>'
    '<PercentComplete>0.30</PercentComplete><PlannedDuration>180</PlannedDuration>'
    '<PlannedStartDate>2026-06-01T00:00:00</PlannedStartDate><PlannedFinishDate>2026-11-30T16:00:00</PlannedFinishDate></Activity>\n'
    '    <ResourceAssignment><ActivityObjectId>O1</ActivityObjectId><PlannedCost>1000000</PlannedCost><ActualCost>600000</ActualCost></ResourceAssignment>\n'
    '    <ResourceAssignment><ActivityObjectId>O2</ActivityObjectId><PlannedCost>2000000</PlannedCost><ActualCost>1000000</ActualCost></ResourceAssignment>\n'
    '    <ResourceAssignment><ActivityObjectId>O3</ActivityObjectId><PlannedCost>1000000</PlannedCost><ActualCost>300000</ActualCost></ResourceAssignment>\n'
    '  </Project>\n'
    '  <BaselineProject>\n'
    '    <Activity><Id>ENG-1</Id><PlannedStartDate>2026-01-01T00:00:00</PlannedStartDate><PlannedFinishDate>2027-06-30T16:00:00</PlannedFinishDate></Activity>\n'
    '    <Activity><Id>QW-1</Id><PlannedStartDate>2026-01-01T00:00:00</PlannedStartDate><PlannedFinishDate>2026-09-30T16:00:00</PlannedFinishDate></Activity>\n'
    '    <Activity><Id>QW-2</Id><PlannedStartDate>2026-03-01T00:00:00</PlannedStartDate><PlannedFinishDate>2026-10-31T16:00:00</PlannedFinishDate></Activity>\n'
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
    # in P6's own order (the file lists Engineering before Construction), not alphabetical.
    mains = tree_result['wbs_main']
    assert [m['name'] for m in mains] == ['Engineering', 'Construction']
    assert [m['id'] for m in mains] == ['1100', '1200']


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


def test_a_finish_saved_at_midnight_is_the_day_before_as_p6_shows_it():
    """P6 stores some finishes as the next day 00:00 (the END of the day): P6 shows 02-Jun for a
    finish saved as 03-Jun 00:00, and so do the WBS and the Gantt."""
    from datetime import datetime
    from p6_evm.schedule_view import p6_finish_day
    assert p6_finish_day(datetime(2025, 6, 3, 0, 0)).date().isoformat() == '2025-06-02'
    assert p6_finish_day(datetime(2025, 6, 2, 16, 0)).date().isoformat() == '2025-06-02'
    # never before its own start (a zero-length activity keeps its day)
    assert p6_finish_day(datetime(2025, 6, 3), datetime(2025, 6, 3)).date().isoformat() == '2025-06-03'
    assert p6_finish_day(None) is None


def test_baseline_dates_are_p6_bl_project_start_and_finish():
    """P6 lists a baseline activity by its own Start / Finish (BL Project Start / Finish), not
    by its Planned dates; a schedule that holds no such dates falls back to the Planned ones."""
    from datetime import datetime
    from types import SimpleNamespace
    from p6_evm.schedule_view import baseline_shown
    bl = {'planned_start': datetime(2024, 12, 8, 8), 'planned_finish': datetime(2025, 1, 8, 16)}
    data = SimpleNamespace(baseline_dates_by_id={'A1': {'start': datetime(2024, 12, 7, 20), 'finish': datetime(2025, 1, 7, 16)}})
    assert baseline_shown(data, 'A1', bl) == (datetime(2024, 12, 7, 20), datetime(2025, 1, 7, 16))
    assert baseline_shown(data, 'A2', bl) == (bl['planned_start'], bl['planned_finish'])
    assert baseline_shown(SimpleNamespace(), 'A1', bl) == (bl['planned_start'], bl['planned_finish'])


def test_not_done_work_saved_before_the_data_date_takes_the_scheduled_dates(monkeypatch):
    """An export can carry a not-started activity with dates BEFORE the data date (Grain Bulk:
    'Piles IFC App.' saved 19-May.2025 against a data date of 09-Aug.2026). P6 shows such work
    at the data date or later, so the view takes the forward-pass dates for it - and for it only."""
    from datetime import datetime
    from types import SimpleNamespace
    import p6_compare.schedule as sched
    from p6_evm.schedule_view import rescheduled_dates, current_start, current_finish
    acts = {
        'old': {'object_id': 'old', 'remaining_early_start': datetime(2025, 5, 18, 8), 'remaining_early_finish': datetime(2025, 5, 19, 16)},
        'ok':  {'object_id': 'ok', 'remaining_early_start': datetime(2026, 9, 1, 8), 'remaining_early_finish': datetime(2026, 9, 5, 16)},
        'done': {'object_id': 'done', 'actual_start': datetime(2025, 5, 1, 8), 'actual_finish': datetime(2025, 5, 3, 16)},
    }
    data = SimpleNamespace(activities=acts, project={'data_date': datetime(2026, 8, 9, 8)})
    seen = {}

    def fake(d, keep=None, starts=None):
        seen['keep'] = keep
        starts.update({'old': datetime(2026, 8, 23, 8)})
        return {'old': datetime(2026, 8, 24, 16), 'ok': datetime(2030, 1, 1), 'done': datetime(2030, 1, 1)}
    monkeypatch.setattr(sched, 'forward_pass', fake)
    moved = rescheduled_dates(data)
    assert moved == {'old': (datetime(2026, 8, 23, 8), datetime(2026, 8, 24, 16))}
    assert seen['keep'] == {'ok', 'done'}                     # every other activity keeps P6's own dates
    assert current_finish(acts['old'], moved) == datetime(2026, 8, 24, 16)
    assert current_start(acts['old'], moved) == datetime(2026, 8, 23, 8)
    assert current_finish(acts['ok'], moved) == datetime(2026, 9, 5, 16)
    assert current_finish(acts['done'], moved) == datetime(2025, 5, 3, 16)
    assert rescheduled_dates(SimpleNamespace(activities={'ok': acts['ok']}, project={'data_date': datetime(2026, 8, 9, 8)})) == {}


def test_planned_pct_of_a_wbs_follows_its_baseline_dates():
    from datetime import datetime as D
    from p6_evm.schedule_view import planned_by_dates as p
    assert p(D(2026, 1, 1), D(2026, 1, 10), D(2026, 1, 5)) == 50.0      # the owner's example
    assert p(D(2026, 1, 1), D(2026, 1, 10), D(2025, 12, 20)) == 0.0     # cut-off before the baseline start
    assert p(D(2026, 1, 1), D(2026, 1, 10), D(2026, 3, 1)) == 100.0     # cut-off after the baseline finish
    assert p(None, D(2026, 1, 10), D(2026, 1, 5)) is None


# --- Procurement by stage weights + the tables that explain every % of the WBS table (owner) ----------
def _stage_nodes(cost_po=True):
    n = lambda i, name, depth, **k: dict({'id': i, 'name': name, 'depth': depth, 'cost_loaded': 0, 'actual': None, 'nc_total': 0,
                                          'nc_a_done': 0, 'nc_a_prog': 0, 'actual_count_pct': None, 'finish_actual': False, 'count': 0,
                                          'baseline_start': '2026-01-01', 'baseline_finish': '2026-01-10', 'planned_time': 50.0}, **k)
    po = dict(cost_loaded=2, actual=72.1, bac=200.0, ev=144.2, count=2) if cost_po else dict(nc_total=2, nc_a_done=1, actual_count_pct=50.0, count=2)
    return [n('1', 'Procurement', 0, cost_loaded=2 if cost_po else 0, actual=72.1 if cost_po else None, nc_total=9, nc_a_done=7, actual_count_pct=77.8, count=11),
            n('2', 'Material Submittal', 1, nc_total=4, nc_a_done=4, actual_count_pct=100.0, finish_actual=True, count=4),
            n('3', 'Material Approval', 1, nc_total=2, nc_a_done=2, actual_count_pct=100.0, count=2),
            n('4', 'PO Issuance', 1, **po),
            n('5', 'Fabrication', 1, nc_total=3, nc_a_done=1, nc_a_prog=1, actual_count_pct=66.7, count=3),
            n('6', 'Engineering', 0, nc_total=4, nc_a_done=1, actual_count_pct=25.0, count=4)]


def test_procurement_actual_is_the_equal_weight_of_its_stages_without_cost():
    from p6_evm.schedule_view import stage_weighted_actual
    nodes = _stage_nodes()
    stage_weighted_actual(nodes, '1')
    stage_weighted_actual(nodes, '6')
    assert nodes[0]['actual_stage'] == 88.9                       # (100 + 100 + 66.7) / 3; the cost-loaded PO stage is left out
    assert [s['weight'] for s in nodes[0]['stages']] == [33.33, 33.33, None, 33.33]
    assert 'actual_stage' not in nodes[5]                         # only a Procurement WBS
    four = _stage_nodes(cost_po=False)
    stage_weighted_actual(four, '1')
    assert [s['weight'] for s in four[0]['stages']] == [25.0] * 4 and four[0]['actual_stage'] == 79.2


def test_the_actual_pct_without_cost_is_reached_stage_by_stage():
    """Owner: only the Actual % of a WBS WITHOUT cost is broken down - the stages as tiles ending in the
    WBS Actual %, then a column per stage; the cost-loaded stage is named as left out, never worked out."""
    from p6_evm.schedule_view import stage_weighted_actual, wbs_explain
    from datetime import datetime
    nodes = _stage_nodes()
    stage_weighted_actual(nodes, '1')
    tabs = wbs_explain(nodes, '1', datetime(2026, 1, 5))
    assert [t['kind'] for t in tabs] == ['stages', 'matrix']
    st, mx = tabs
    assert [p['name'] for p in st['parts']] == ['Material Submittal', 'Material Approval', 'Fabrication']
    assert st['left_out'] == ['PO Issuance'] and st['result']['pct'] == 88.9 and st['formula'].endswith('= 88.9%')
    fab = st['parts'][2]
    assert (fab['done'], fab['total'], fab['pct'], fab['frac'], fab['weight'], fab['weighted']) == (2, 3, 66.7, '2 ÷ 3', 33.33, 22.23)
    assert mx['cols'] == ['Material Submittal', 'Material Approval', 'Fabrication'] and mx['result']['pct'] == 88.9
    assert mx['weights'] == ['33.33%'] * 3 and mx['weighted'][-1] == '22.23%'
    assert 'planned' not in json.dumps(tabs).lower()            # Planned % is by the baseline dates - never broken down


def test_a_wbs_of_milestones_only_still_has_an_actual_pct():
    """Owner: 'put an actual % even it is milestone' - milestones achieved / all its milestones."""
    from p6_evm.schedule_view import wbs_actual_shown
    n = {'cost_loaded': 0, 'actual': None, 'actual_count_pct': None, 'finish_actual': False,
         'ms_total': 14, 'ms_done': 2, 'milestone_only': True, 'actual_ms': 14.3}
    assert wbs_actual_shown(n) == 14.3
    from p6_evm.wbs_excel import _pct, _measure
    assert _pct(n, 'actual') == 14.3 and _measure(n) == 'milestones achieved ÷ all'


def test_explain_panels_reach_the_screen_the_report_and_the_excel():
    import pathlib
    from p6_evm.schedule_view import stage_weighted_actual, wbs_explain
    from p6_evm.wbs_excel import _explain_blocks
    from datetime import datetime
    nodes = _stage_nodes()
    stage_weighted_actual(nodes, '1')
    blocks = _explain_blocks({'explain': wbs_explain(nodes, '1', datetime(2026, 1, 5))}, '05-Jan.2026')
    assert blocks[0]['rows'][-1][3] == '88.9%' and 'PO Issuance is cost loaded' in blocks[0]['note']
    assert blocks[1]['headers'] == ['WBS', 'Material Submittal', 'Material Approval', 'Fabrication']
    assert blocks[1]['rows'][-1][1].endswith('= 88.9%')
    assert _explain_blocks({'explain': [{'kind': 'explain', 'rows': [{}]}, None]}) is not None     # an older shape never raises
    js = pathlib.Path(__file__).resolve().parents[1].joinpath('ui/modules/overview.js').read_text(encoding='utf-8')
    assert '${main ? main.body : \'\'}${explain}${msSection}' in js and 'explainPanels(result, m.id)' in js
    assert 'How the Actual % is reached' in js and 'not part of the stage weights' in js
    # the report: page 1 = every main WBS in one table, last page = the reading notes
    assert "key: 'overview'" in js and 'wbsSummaryTable(nodes, list, ctx' in js and "key: 'notes'" in js
    # the chart: baseline over expected, the slip after the Baseline Finish, months written out by name
    for tag in ('data-g="base"', 'data-g="slip"', 'data-g="line"', 'data-g="label"', 'WBS_MON[d.getMonth()]'):
        assert tag in js


def test_word_draws_the_two_bars_of_a_wbs_row():
    """The Word export reads the same tags the PDF prints: baseline, expected bar + fill, slip, label."""
    from p6_export import html_model, to_docx
    import inspect
    src = inspect.getsource(html_model) + inspect.getsource(to_docx)
    for k in ("'base', 'slip', 'line'", "out['label']", "bar.get('base')", "bar.get('mss')"):
        assert k in src
