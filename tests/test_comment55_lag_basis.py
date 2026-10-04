"""Comment 55 — the Lag Report says how 'Lags by relationship type' and 'Lags by WBS area' are
counted: from the relationships carrying a lag or lead; each type's / area's lagged links ÷ all
lagged links; a link counted under its successor's WBS area (the level below the project)."""
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.lag_lead import run_lag_lead
from p6_audit.report import _lag_charts


def _graph():
    d = ScheduleData()
    acts = {'A': 'P > Civil > X', 'B': 'P > Civil > Y', 'C': 'P > MEP > Z', 'D': 'P > MEP > Z'}
    d.activities = {c: {'id': c, 'name': c, 'task_type': 'Task', 'wbs_path': w, 'status': 'Not Started'}
                    for c, w in acts.items()}
    d.relationships = [{'pred_id': 'A', 'succ_id': 'B', 'type': 'FS', 'lag_days': 2.0},
                       {'pred_id': 'B', 'succ_id': 'C', 'type': 'SS', 'lag_days': 3.0},
                       {'pred_id': 'A', 'succ_id': 'D', 'type': 'FS', 'lag_days': 1.0},
                       {'pred_id': 'C', 'succ_id': 'D', 'type': 'FS', 'lag_days': 0.0}]
    return ScheduleGraph(d)


def test_basis_lines_name_the_counts_and_the_successor_area():
    m = run_lag_lead(_graph(), {'audit': {}})
    k = m['kpis']
    assert k['lagged_count'] == 3 and k['total_relationships'] == 4
    assert 'Counted from the 3 relationships that carry a lag or a lead (of all 4 relationships)' in k['basis_type']
    assert 'FS 2 ÷ 3 = 66.7%' in k['basis_type']
    assert "successor activity's WBS area" in k['basis_wbs']
    assert {r['wbs']: r['lagged'] for r in m['wbs_summary']} == {'MEP': 2, 'Civil': 1}   # by the successor
    assert 'MEP 2 ÷ 3 = 66.7%' in k['basis_wbs']


def test_pdf_prints_the_basis_under_each_chart():
    html = _lag_charts(run_lag_lead(_graph(), {'audit': {}}))
    assert 'Counted from the 3 relationships' in html and "successor activity&#x27;s WBS area" in html
