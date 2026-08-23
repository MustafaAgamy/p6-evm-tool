"""Constructability risk score — normalized, project-size-independent finding-severity
density (Ibrahim's V1 rule). Score = clamp(100 − (Σ severity points / total activities)
× 100, 0, 100). Severity points are per FINDING (Strong 10 / Moderate 5 / Low 2), never
per activity."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.scoring import evidence_score


def _f(strength, system='piping'):
    return {'system': system, 'strength': strength, 'title': 'x'}


def test_clean_schedule_scores_100():
    s = evidence_score([], total_activities=500)
    assert s['overall'] == 100 and s['band'] == 'green'
    assert s['finding_count'] == 0


def test_severity_points_per_finding():
    assert evidence_score([_f('strong')], 100)['deductions'][0]['points'] == 10
    assert evidence_score([_f('moderate')], 100)['deductions'][0]['points'] == 5
    assert evidence_score([_f('weak')], 100)['deductions'][0]['points'] == 2
    # stamped on the finding for the report's Score Impact column
    fs = [_f('strong')]
    evidence_score(fs, 100)
    assert fs[0]['score_impact'] == 10


def test_normalized_density_is_project_size_independent():
    # same density (10 severity points per 100 activities) → same score at any size
    small = evidence_score([_f('strong')], total_activities=100)              # 10/100×100 = 10
    large = evidence_score([_f('strong')] * 100, total_activities=10000)      # 1000/10000×100 = 10
    assert small['overall'] == large['overall'] == 90
    assert small['weighted_finding_density'] == large['weighted_finding_density'] == 10.0


def test_large_project_many_findings_does_not_collapse_to_zero():
    # 100 findings on a 10,000-activity project — a raw subtraction model would hit 0;
    # the normalized model keeps it sensible.
    s = evidence_score([_f('moderate')] * 100, total_activities=10000)        # 500/10000×100 = 5
    assert s['overall'] == 95 and s['band'] == 'green'


def test_one_finding_many_activities_counts_once():
    # a single finding that references 10 activities still contributes ONE severity weight
    f = {'system': 'piping', 'strength': 'strong', 'title': 'x',
         'p6': [{'id': f'A{i}'} for i in range(10)]}
    s = evidence_score([f], total_activities=1000)                            # 10/1000×100 = 1
    assert s['total_severity_points'] == 10 and s['overall'] == 99


def test_score_clamped_to_zero_never_negative():
    # dense findings on a tiny project — must clamp at 0, never go negative
    s = evidence_score([_f('strong')] * 50, total_activities=100)             # 500/100×100 = 500
    assert s['overall'] == 0 and s['band'] == 'red'


def test_bands_follow_risk_legend():
    assert evidence_score([_f('strong')], 500)['band_label'] == 'Low Risk'          # 98
    assert evidence_score([_f('strong')] * 15, 100)['overall'] == 0                  # High
    # a mid density lands in a mid band
    s = evidence_score([_f('strong')] * 3, 100)                                      # 30 → 70
    assert s['overall'] == 70 and s['band_label'] == 'Moderate Risk'
