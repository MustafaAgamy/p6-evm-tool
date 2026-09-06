"""R3–R7 — the KB-driven generalized constructability rules, each proven POSITIVE /
NEGATIVE-correct / NEGATIVE-N/A per the binding validation gate.

Synthetic but realistic activity names (so the Phase-1 tagger tags them) + explicit
relationships. A rule must FIRE on the intended defect and stay SILENT when the
sequence is legitimate or the interface is simply not in the project.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.findings import generate_findings
from p6_kb.resolve import resolve
from p6_kb.tagging import tag_view


def mkview(activities, rels=()):
    oid = [{'object_id': f'O{i}', 'id': f'A{i:03d}', 'name': n, 'wbs_path': '',
            'activity_codes': {}, 'task_type': 'Task'} for i, n in enumerate(activities)]
    view = {
        'activities_oid': oid,
        'by_oid': {a['object_id']: a for a in oid},
        'relationships_oid': [{'pred_oid': f'O{p}', 'succ_oid': f'O{s}', 'type': 'FS',
                               'lag_days': 0, 'lag_hours': 0} for p, s in rels],
        'activities': oid, 'by_code': {a['id']: a for a in oid},
        'relationships': [], 'wbs': [], 'activity_count': len(oid),
        'relationship_count': len(rels), 'activity_code_types': [],
    }
    tag_view(view)
    return view


def _fire(view, kind=None, system=None):
    f = generate_findings(view, resolve(view))
    if kind:
        f = [x for x in f if x['kind'] == kind]
    if system:
        f = [x for x in f if x['system'] == system]
    return f


_CTX = ['Transformer Installation', 'LV Cable Tray & Cable Pulling', 'Cable Termination',
        'HVAC Ductwork Installation', 'Plumbing Pipework First Fix', 'Lighting Fixtures Installation']


# ── Rule 3: cross-system enabler inversion (dependent scheduled ahead of enabler) ──

def test_R3_positive_enabler_pushed_behind_dependent():
    # process_equipment requires piping (a non-mutual strong interface); here the
    # equipment COMMISSIONING (g2) drives the pipe erection (g1) — enabler behind the
    # dependent it enables
    v = mkview(['Ball Mill Equipment Installation', 'Ball Mill Testing & Commissioning',
                'Process Pipe Spool Erection'],
               rels=[(1, 2)])
    f = _fire(v, kind='out_of_sequence', system='process_equipment')
    assert f, 'R3 must flag an enabler scheduled behind the dependent it enables'
    assert f[0]['strength'] == 'strong' and f[0]['activities']
    assert f[0]['reason'] and f[0]['expected'] and f[0]['recommendation']


def test_R3_negative_correct_enabler_first():
    v = mkview(['Ball Mill Equipment Installation', 'Ball Mill Testing & Commissioning',
                'Process Pipe Spool Erection'],
               rels=[(2, 1)])   # pipe erection (g1) -> equipment commissioning (g2): correct
    assert not _fire(v, kind='out_of_sequence', system='process_equipment'), \
        'R3 must stay silent when the enabler correctly precedes the dependent'


def test_R3_negative_na_when_enabler_absent():
    # equipment present in correct internal order, but NO piping system at all → N/A
    v = mkview(['Ball Mill Equipment Installation', 'Ball Mill Testing & Commissioning'],
               rels=[(0, 1)])   # install -> commissioning (correct); no enabler system
    assert not _fire(v, kind='out_of_sequence', system='process_equipment'), \
        'R3 must stay silent when the required enabler system is not in the project'


# ── Rule 4: within-system phase-GROUP inversion (generalises R2) ──

def test_R4_positive_integration_drives_install():
    v = mkview(_CTX + ['Chiller Performance Test', 'Chiller Installation & Alignment'],
               rels=[(6, 7)])   # performance (g3) -> installation (g1), same system
    f = _fire(v, kind='out_of_sequence', system='chilled_water')
    assert f, 'R4 must flag a later-group activity driving an earlier-group one'
    assert f[0]['strength'] == 'strong'


def test_R4_negative_correct_group_order():
    v = mkview(_CTX + ['Chiller Installation & Alignment', 'Chiller Performance Test'],
               rels=[(6, 7)])   # install (g1) -> performance (g3): correct
    assert not _fire(v, kind='out_of_sequence', system='chilled_water'), \
        'R4 must stay silent on the correct phase-group order'


# ── Rule 5: equipment set with no civil/steel support interface ──

def test_R5_positive_equipment_no_foundation():
    v = mkview(['Pump Skid Equipment Installation', 'Pump Skid Alignment & Grouting',
                'Transformer Installation'],
               rels=[(0, 1)])   # equipment set with NO civil and NO steel predecessor
    f = [x for x in _fire(v, kind='missing_interface') if 'foundation' in x['title'].lower()]
    assert f, 'R5 must flag equipment set with no foundation or steel support'
    assert f[0]['strength'] == 'moderate'


def test_R5_negative_foundation_present():
    v = mkview(['Equipment Foundation & Anchor Bolts', 'Pump Skid Equipment Installation',
                'Pump Skid Alignment & Grouting'],
               rels=[(0, 1), (1, 2)])   # foundation -> equipment install: correct
    assert not _fire(v, kind='missing_interface', system='mechanical_equipment'), \
        'R5 must stay silent when a civil foundation precedes the equipment'


def test_R5_negative_na_no_equipment():
    v = mkview(_CTX, rels=[])   # no equipment systems at all
    assert not _fire(v, kind='missing_interface', system='mechanical_equipment'), \
        'R5 must stay silent when there is no equipment in the project'


# ── Rule 6: piping insulation / reinstatement before hydrotest ──

def test_R6_positive_insulation_before_hydrotest():
    v = mkview(['Process Pipe Spool Erection', 'Process Pipe Insulation',
                'Process Pipe Hydrotest'],
               rels=[(1, 2)])   # insulation -> hydrotest: covered before tested
    f = _fire(v, kind='out_of_sequence', system='piping')
    assert f, 'R6 must flag piping insulated/boxed up before the hydrotest'
    assert f[0]['strength'] == 'strong'


def test_R6_negative_hydrotest_first():
    v = mkview(['Process Pipe Spool Erection', 'Process Pipe Hydrotest',
                'Process Pipe Insulation'],
               rels=[(0, 1), (1, 2)])   # erection -> hydrotest -> insulation: correct
    assert not _fire(v, kind='out_of_sequence', system='piping'), \
        'R6 must stay silent when the hydrotest precedes insulation'


def test_R6_negative_na_no_hydrotest():
    v = mkview(['Process Pipe Spool Erection', 'Process Pipe Insulation'],
               rels=[(0, 1)])   # no hydrotest activity at all
    assert not _fire(v, kind='out_of_sequence', system='piping'), \
        'R6 must stay silent when there is no hydrotest in the piping scope'


# ── Rule 7: integrated/performance/start-up test with no commissioning behind it ──

def test_R7_positive_integration_without_commissioning():
    v = mkview(['Equipment Installation', 'Plant Integrated Testing & SAT',
                'Performance Guarantee Test'],
               rels=[(0, 1), (1, 2)])   # integration with NO commissioning predecessor
    f = _fire(v, kind='sequence_gap')
    assert f, 'R7 must flag integrated/performance testing with no commissioning behind it'


def test_R7_negative_commissioning_present():
    v = mkview(['Equipment Installation', 'System Commissioning',
                'Plant Integrated Testing & SAT'],
               rels=[(0, 1), (1, 2)])   # install -> commissioning -> integrated: correct
    assert not _fire(v, kind='sequence_gap'), \
        'R7 must stay silent when commissioning precedes integrated testing'


def test_R7_negative_na_no_integration():
    v = mkview(_CTX + ['Chiller Installation & Alignment', 'Chiller Commissioning'],
               rels=[(6, 7)])   # no integrated/performance/start-up activity at all
    assert not _fire(v, kind='sequence_gap'), \
        'R7 must stay silent when there is no integrated/performance testing'


def test_all_new_findings_are_fully_auditable():
    v = mkview(['Ball Mill Equipment Installation', 'Ball Mill Testing & Commissioning',
                'Instrument Installation & Calibration', 'Pipe Insulation & Cladding',
                'Piping Hydrotest & Flushing', 'Plant Integrated Testing'],
               rels=[(1, 2), (3, 4), (0, 5)])
    fs = generate_findings(v, resolve(v))
    assert fs, 'expected several findings on this deliberately-broken schedule'
    for g in fs:
        for field in ('kind', 'system', 'discipline', 'existing', 'expected',
                      'reason', 'evidence', 'strength', 'impact', 'recommendation', 'activities'):
            assert field in g, f"{g.get('kind')} finding missing field: {field}"
