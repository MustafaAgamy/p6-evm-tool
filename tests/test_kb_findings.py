"""Phase 3 validation gate — every rule proven on POSITIVE, NEGATIVE-correct and
NEGATIVE-N/A cases. A rule must FIRE on the intended defect and stay SILENT when
the condition is legitimately correct or not applicable. "It fired" is not proof.

Each synthetic schedule is built from real-ish activity names (so the Phase-1
tagger tags them) + explicit relationships, then run through the full pipeline:
tag → resolve archetype → generate_findings.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.findings import generate_findings
from p6_kb.resolve import resolve
from p6_kb.tagging import tag_view


def mkview(activities, rels=()):
    """activities: list of names. rels: list of (pred_index, succ_index)."""
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


# A common MEP context so an archetype resolves (buildings/data-centre-ish).
_CTX = ['Transformer Installation', 'LV Cable Tray & Cable Pulling', 'Cable Termination',
        'HVAC Ductwork Installation', 'Plumbing Pipework First Fix', 'Lighting Fixtures Installation']


# ── Rule 1: commissioning/testing not linked to a required prerequisite system ──

def test_R1_positive_commissioning_without_power_link():
    # chiller commissioning present, electrical energization present, but NOT linked
    v = mkview(_CTX + ['Chiller Installation & Alignment', 'CHW Piping Connection',
                       'Transformer Energization', 'Chiller Commissioning'],
               rels=[(6, 9)])   # chiller install -> chiller commissioning only (no power link)
    f = _fire(v, kind='missing_interface', system='chilled_water')
    assert f, 'R1 must flag chiller commissioning not tied to electrical_power'
    g = f[0]
    assert g['strength'] in ('strong', 'moderate')
    assert g['existing'] and g['expected'] and g['reason'] and g['evidence'] and g['recommendation']
    assert g['activities']            # the actual activities are carried as evidence


def test_R1_negative_correct_when_power_is_linked():
    v = mkview(_CTX + ['Chiller Installation & Alignment', 'CHW Piping Connection',
                       'Transformer Energization', 'Chiller Commissioning'],
               rels=[(6, 9), (8, 9)])   # power energization -> chiller commissioning IS present
    assert not _fire(v, kind='missing_interface', system='chilled_water'), \
        'R1 must stay silent when the prerequisite link is present'


def test_R1_negative_na_when_prerequisite_system_absent():
    # chiller commissioning present but NO electrical system at all → power is out of
    # scope for this (impossible) mini-project → not a defect, must stay silent
    v = mkview(['Chiller Installation & Alignment', 'CHW Piping Connection', 'Chiller Commissioning',
                'HVAC Ductwork Installation', 'Plumbing Pipework First Fix'],
               rels=[(0, 2)])
    assert not _fire(v, kind='missing_interface', system='chilled_water'), \
        'R1 must stay silent when the required prerequisite system is not in the project'


# ── Rule 2: within-system testing/commissioning BEFORE installation ──

def test_R2_positive_testing_before_install():
    v = mkview(_CTX + ['Chiller Commissioning', 'Chiller Installation & Alignment'],
               rels=[(6, 7)])   # commissioning -> installation (reversed / impossible)
    f = _fire(v, kind='out_of_sequence')
    assert f, 'R2 must flag testing/commissioning driving installation'
    assert f[0]['strength'] == 'strong' and f[0]['activities']


def test_R2_negative_correct_order():
    v = mkview(_CTX + ['Chiller Installation & Alignment', 'Chiller Commissioning'],
               rels=[(6, 7)])   # install -> commissioning (correct)
    assert not _fire(v, kind='out_of_sequence'), 'R2 must stay silent on the correct order'


def test_findings_are_fully_auditable():
    v = mkview(_CTX + ['Chiller Installation & Alignment', 'Transformer Energization', 'Chiller Commissioning'],
               rels=[(6, 8)])
    for g in generate_findings(v, resolve(v)):
        for field in ('kind', 'system', 'discipline', 'existing', 'expected',
                      'reason', 'evidence', 'strength', 'impact', 'recommendation', 'activities'):
            assert field in g, f'finding missing auditable field: {field}'
