"""End-to-end Baseline Revision Comparison engine (p6_revcompare.compare)."""
from datetime import datetime

from p6_evm.parser import ScheduleData
from p6_revcompare import build_report_from_data
from p6_revcompare.exporters import render_html


def D(y, m, d):
    return datetime(y, m, d)


def _act(code, name, tt='Task', tf=None, wbs='WBS 1.2 Substructure', dur=80.0, ps=None, pf=None):
    return {'id': code, 'name': name, 'task_type': tt, 'total_float_days': tf, 'wbs_id': 'w1',
            'wbs_path': wbs, 'planned_duration': dur, 'remaining_duration': dur,
            'planned_start': ps, 'planned_finish': pf, 'remaining_early_finish': pf,
            'calendar_id': 'c1', 'activity_codes': {}}


def _sched(acts, rels, dd):
    d = ScheduleData()
    d.activities = {f'o{i}': a for i, a in enumerate(acts)}
    code2oid = {a['id']: f'o{i}' for i, a in enumerate(acts)}
    d.relationships = [{'pred_id': code2oid[p], 'succ_id': code2oid[s], 'type': t, 'lag_days': l, 'lag_hours': l * 8}
                       for p, s, t, l in rels]
    d.project = {'data_date': dd, 'name': 'Test'}
    d.wbs = {'w1': {'name': 'Substructure', 'parent_object_id': None}}
    return d


def _pair():
    rev0 = _sched([
        _act('A1000', 'Excavation', tf=0, ps=D(2025, 3, 1), pf=D(2025, 3, 20)),
        _act('A1100', 'Blinding', tf=0, ps=D(2025, 3, 21), pf=D(2025, 4, 10)),
        _act('A1220', 'Waterproofing to Raft — Zone B', tf=8, ps=D(2025, 4, 12), pf=D(2025, 4, 28), dur=112),
        _act('A1300', 'Raft', tf=0, ps=D(2025, 4, 29), pf=D(2025, 5, 20)),
        _act('A1500', 'Columns', tf=0, ps=D(2025, 5, 21), pf=D(2025, 6, 20)),
        _act('A2050', 'Steel Procurement', tf=12, ps=D(2025, 4, 1), pf=D(2025, 6, 1)),
        _act('A2075', 'Steel Erection', tf=12, ps=D(2025, 6, 2), pf=D(2025, 7, 15)),
        _act('A1980', 'Temp Dewatering', tf=20, ps=D(2025, 3, 5), pf=D(2025, 3, 30)),
        _act('MS-PC', 'Practical Completion', 'FinishMilestone', tf=0, ps=D(2026, 12, 19), pf=D(2026, 12, 19)),
    ], [
        ('A1000', 'A1100', 'FS', 0), ('A1100', 'A1220', 'FS', 0), ('A1220', 'A1300', 'FS', 0),
        ('A1300', 'A1500', 'FS', 0), ('A1500', 'MS-PC', 'FS', 0), ('A2050', 'A2075', 'FS', 0),
    ], D(2025, 3, 1))
    rev1 = _sched([
        _act('A1000', 'Excavation', tf=0, ps=D(2025, 3, 1), pf=D(2025, 3, 20)),
        _act('A1100', 'Blinding', tf=0, ps=D(2025, 3, 21), pf=D(2025, 4, 10)),
        _act('A1362', 'Raft Waterproofing — Zone B', tf=0, ps=D(2025, 5, 2), pf=D(2025, 5, 18), dur=112),
        _act('A1300', 'Raft', tf=0, ps=D(2025, 4, 29), pf=D(2025, 5, 1)),
        _act('A1500', 'Columns', tf=0, ps=D(2025, 5, 21), pf=D(2025, 6, 20)),
        _act('A2050', 'Steel Procurement', tf=0, ps=D(2025, 4, 1), pf=D(2025, 6, 1)),
        _act('A2075', 'Steel Erection', tf=0, ps=D(2025, 5, 15), pf=D(2025, 7, 1)),
        _act('A4400', 'MEP Risers', tf=0, wbs='WBS 1.5 MEP', ps=D(2025, 8, 1), pf=D(2025, 10, 18)),
        _act('MS-PC', 'Practical Completion', 'FinishMilestone', tf=0, ps=D(2027, 2, 4), pf=D(2027, 2, 4)),
    ], [
        ('A1000', 'A1100', 'FS', 0), ('A1100', 'A1300', 'FS', 0), ('A1300', 'A1362', 'FS', 0),
        ('A1362', 'A1500', 'FS', 0), ('A1500', 'MS-PC', 'FS', 0), ('A2050', 'A2075', 'SS', 0),
    ], D(2025, 3, 1))
    return rev0, rev1


def test_scope_counts():
    r = build_report_from_data(*_pair(), config={})
    s = r['summary']
    assert s['added'] == 1 and s['removed'] == 1
    assert s['id_changes'] == 1


def test_id_change_appears_in_register_not_as_add_remove():
    r = build_report_from_data(*_pair(), config={})
    id_rows = [x for x in r['register'] if x['change_type'] == 'idchange']
    assert len(id_rows) == 1
    assert id_rows[0]['change'] == 'A1220 → A1362'


def test_sequence_reversal_detected_with_detail():
    r = build_report_from_data(*_pair(), config={})
    assert r['summary']['sequence'] == 1
    seq_rows = [x for x in r['register'] if x['change_type'] == 'sequence']
    assert len(seq_rows) == 1
    d = seq_rows[0]['detail']
    assert d['rev0']['id'] == 'A1220' and d['rev1']['id'] == 'A1362'
    assert d['rev0']['criticality'] == 'Near-critical' and d['rev1']['criticality'] == 'Critical'


def test_logic_type_change_captured():
    r = build_report_from_data(*_pair(), config={})
    assert r['summary']['logic']['type'] == 1
    logic_rows = [x for x in r['register'] if x['change_type'] == 'logic' and x['activity_id'] == 'A2075']
    assert logic_rows and 'SS' in str(logic_rows[0]['rev1'])


def test_milestone_slip_delayed():
    r = build_report_from_data(*_pair(), config={})
    pc = next(m for m in r['milestones'] if m['name'] == 'Practical Completion')
    assert pc['kind'] == 'delayed' and pc['change_days'] > 0
    assert r['rev1']['finish'] == '04 Feb 2027'


def test_critical_path_entered_includes_added_and_promoted():
    r = build_report_from_data(*_pair(), config={})
    entered = {e['code'] for e in r['critical_path']['entered']}
    assert 'A4400' in entered            # added activity, critical
    assert 'A2075' in entered            # steel erection promoted to critical


def test_float_movement_became_critical():
    r = build_report_from_data(*_pair(), config={})
    became = {f['activity_id'] for f in r['float_movement'] if 'critical' in f['movement'].lower()}
    assert {'A2050', 'A2075'} <= became


def test_findings_are_neutral_and_present():
    r = build_report_from_data(*_pair(), config={})
    assert r['findings']
    blob = ' '.join(f['body'] + ' ' + f['title'] for f in r['findings']).lower()
    assert 'wrong' not in blob and 'bad change' not in blob
    assert 'planning review' in r['narrative'].lower()


def test_identical_revisions_yield_empty_register():
    rev0, _ = _pair()
    r = build_report_from_data(rev0, rev0, config={})
    assert r['register'] == []
    assert r['summary']['added'] == 0 and r['summary']['removed'] == 0


def test_report_html_renders_all_sections():
    r = build_report_from_data(*_pair(), config={})
    html = render_html(r, meta={'report_date': '02 Sep 2026'}, theme='light')
    for key in ('summary', 'overview', 'milestones', 'critpath', 'sequence', 'register'):
        assert f'data-sec="{key}"' in html
    assert '<!doctype html>' in html.lower()
