"""Known-bad verification — a realistic schedule (real-project naming + WBS + activity
codes) with deliberately injected sequencing defects. Proves the engine tags real-style
activities AND that R1–R7 catch genuine defects (so 0 findings on a real schedule means
the schedule is clean for this rule set, not that the engine is blind)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.findings import generate_findings
from p6_kb.resolve import resolve
from p6_kb.tagging import tag_view

_ACTS = [
    ('EL-1010', 'Transformer & MV Switchgear Installation Works', 'Project > Electrical > Substation', {'Discipline': 'ELEC'}),
    ('EL-1020', 'MV Switchgear Energization', 'Project > Electrical > Substation', {'Discipline': 'ELEC'}),
    ('CH-1010', 'Chiller Unit Installation & Alignment', 'Project > MEP Works > Chilled Water', {'Discipline': 'MECH'}),
    ('CH-1020', 'Chiller Commissioning', 'Project > MEP Works > Chilled Water', {'Discipline': 'MECH'}),
    ('PP-1010', 'Process Pipe Spool Erection Works', 'Project > Piping > Unit 100', {'Discipline': 'PIPING'}),
    ('PP-1020', 'Process Pipe Hydrotest', 'Project > Piping > Unit 100', {'Discipline': 'PIPING'}),
    ('PP-1030', 'Process Pipe Insulation', 'Project > Piping > Unit 100', {'Discipline': 'PIPING'}),
    ('EQ-1010', 'Centrifugal Pump Installation Works', 'Project > Mechanical > Pumps', {'Discipline': 'MECH'}),
    ('EQ-1020', 'Centrifugal Pump Commissioning', 'Project > Mechanical > Pumps', {'Discipline': 'MECH'}),
    ('IT-1010', 'Plant Integrated Testing & SAT', 'Project > Commissioning', {'Discipline': 'COMM'}),
]
_RELS = [
    ('CH-1020', 'CH-1010'),   # DEFECT: chiller commissioning drives installation (R2/R4)
    ('CH-1010', 'CH-1020'),
    ('PP-1010', 'PP-1030'),
    ('PP-1030', 'PP-1020'),   # DEFECT: pipe insulation drives hydrotest (R6)
    ('EQ-1010', 'EQ-1020'),   # pump commissioning has no power predecessor (R1); pump has no foundation (R5)
    ('EL-1010', 'EL-1020'),
    ('EQ-1010', 'IT-1010'),   # integrated test has no commissioning predecessor (R7)
]


def _view():
    oid = [{'object_id': f'O{i}', 'id': a[0], 'name': a[1], 'wbs_path': a[2],
            'activity_codes': a[3], 'task_type': 'Task'} for i, a in enumerate(_ACTS)]
    idmap = {a['id']: a['object_id'] for a in oid}
    rels = [{'pred_oid': idmap[p], 'succ_oid': idmap[s], 'type': 'FS', 'lag_days': 0, 'lag_hours': 0}
            for p, s in _RELS]
    view = {'activities_oid': oid, 'by_oid': {a['object_id']: a for a in oid},
            'relationships_oid': rels, 'activities': oid, 'by_code': {}, 'relationships': [],
            'wbs': [], 'activity_count': len(oid), 'relationship_count': len(rels),
            'activity_code_types': []}
    tag_view(view)
    return view


def test_real_style_names_are_tagged():
    v = _view()
    tag = {a['id']: a['identity'] for a in v['activities_oid']}
    assert tag['EL-1010']['system'] == 'electrical_power'
    assert tag['CH-1010']['system'] == 'chilled_water'
    assert tag['PP-1010']['system'] == 'piping'
    assert tag['EQ-1010']['system'] == 'rotating_equipment'
    assert tag['IT-1010']['phase'] == 'INTEGRATED_TESTING'


def test_r1_to_r7_catch_the_injected_defects():
    v = _view()
    fs = generate_findings(v, resolve(v))
    kinds = [f['kind'] for f in fs]
    systems = {(f['kind'], f['system']) for f in fs}
    # R1 power-not-linked on both chiller and pump commissioning
    assert ('missing_interface', 'chilled_water') in systems
    assert ('missing_interface', 'rotating_equipment') in systems
    # R2/R4 within-system inversion (chiller test before install)
    assert any(f['kind'] == 'out_of_sequence' and f['system'] == 'chilled_water' for f in fs)
    # R6 pipe covered before hydrotest
    assert any(f['kind'] == 'out_of_sequence' and f['system'] == 'piping' for f in fs)
    # R7 integration with no commissioning behind it
    assert 'sequence_gap' in kinds
    # R5 equipment with no foundation
    assert any('foundation' in f['title'].lower() for f in fs)
    assert len(fs) >= 6
