"""Comment 47 — Relationship Types shows the total number of activities and how SS % / FF %
are worked out: each type's relationships ÷ all relationships (Alstom: SS 252 ÷ 4,925 = 5.1%)."""
from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules.relationship_types import run_relationship_types
from p6_audit.presentation import build_presentation


def _graph():
    d = ScheduleData()
    d.activities = {c: {'id': c, 'name': c, 'task_type': 'Task', 'status': 'Not Started'} for c in 'ABCD'}
    d.activities['D']['status'] = 'Completed'
    d.relationships = [{'pred_id': 'A', 'succ_id': 'B', 'type': 'FS', 'lag_days': 0},
                       {'pred_id': 'B', 'succ_id': 'C', 'type': 'SS', 'lag_days': 0},
                       {'pred_id': 'A', 'succ_id': 'C', 'type': 'FF', 'lag_days': 0},
                       {'pred_id': 'C', 'succ_id': 'D', 'type': 'FS', 'lag_days': 0}]
    return ScheduleGraph(d)


def test_counts_behind_each_percentage_and_activity_totals():
    g = _graph()
    m = run_relationship_types(g, {'audit': {}})
    k = m['kpis']
    assert (k['fs_count'], k['ss_count'], k['ff_count'], k['sf_count']) == (2, 1, 1, 0)
    assert k['ss_pct'] == 25.0 and k['ff_pct'] == 25.0
    m['p6_counts'] = {'total': len(g.p6_all()), 'remaining': len(g.p6_remaining())}
    p = build_presentation(m)
    tiles = {t['label']: t['value'] for t in p['tiles']}
    assert tiles['Total Activities'] == '4' and tiles['Remaining Activities'] == '3'
    assert tiles['SS %'] == '25% (1)' and tiles['FF %'] == '25% (1)'
    assert 'SS % = 1 ÷ 4 = 25%' in p['verdict']
