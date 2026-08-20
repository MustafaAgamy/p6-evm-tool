"""MEP-first evidence-weighted score — a second, distinct score computed only from the
R1–R7 findings: points = strength_base × discipline_weight, deducted from 100. MEP /
commissioning carry full weight; civil (interface only) is weighted lowest."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.scoring import evidence_score


def _f(system, discipline, strength, title='x'):
    return {'system': system, 'discipline': discipline, 'strength': strength, 'title': title}


def test_clean_schedule_scores_100():
    s = evidence_score([])
    assert s['overall'] == 100 and s['band'] == 'green'
    assert s['finding_count'] == 0 and s['deductions'] == []


def test_strong_mep_costs_full_ten():
    s = evidence_score([_f('chilled_water', 'MECH', 'strong')])
    assert s['overall'] == 90            # 100 − 10×1.0
    assert s['deductions'][0]['points'] == 10.0
    assert s['deductions'][0]['discipline_class'] == 'mep'


def test_mep_first_civil_weighted_lowest():
    mep = evidence_score([_f('chilled_water', 'MECH', 'strong')])['overall']
    civil = evidence_score([_f('civil_interface', 'CIVIL', 'strong')])['overall']
    assert civil > mep                   # the same strong finding costs LESS when it is civil
    assert evidence_score([_f('civil_interface', 'CIVIL', 'strong')])['deductions'][0]['points'] == 5.0
    assert evidence_score([_f('structural_steel', 'STRUCT', 'strong')])['deductions'][0]['points'] == 7.0


def test_strength_ordering_and_bands():
    assert evidence_score([_f('piping', 'MECHANICAL_PIPING', 'strong')] * 5)['overall'] == 50
    assert evidence_score([_f('piping', 'MECHANICAL_PIPING', 'strong')] * 5)['band'] == 'orange'
    # strong costs more than moderate costs more than insufficient
    strong = 100 - evidence_score([_f('hvac', 'MECH', 'strong')])['overall']
    moderate = 100 - evidence_score([_f('hvac', 'MECH', 'moderate')])['overall']
    insufficient = 100 - evidence_score([_f('hvac', 'MECH', 'insufficient')])['overall']
    assert strong > moderate > insufficient


def test_never_below_zero_and_breakdown():
    s = evidence_score([_f('piping', 'MECHANICAL_PIPING', 'strong')] * 40)
    assert s['overall'] == 0 and s['band'] == 'red'
    assert s['by_strength'] == {'strong': 40}
    assert s['deductions'][0]['points'] >= s['deductions'][-1]['points']   # sorted worst-first


def test_deductions_sorted_worst_first():
    s = evidence_score([_f('civil_interface', 'CIVIL', 'moderate'),
                        _f('chilled_water', 'MECH', 'strong'),
                        _f('hvac', 'MECH', 'moderate')])
    pts = [d['points'] for d in s['deductions']]
    assert pts == sorted(pts, reverse=True)
    assert s['deductions'][0]['system'] == 'chilled_water'   # the strong MEP finding hurts most
