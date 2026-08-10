"""Baseline Constructability Score — the 45/45/10 rubric (Ibrahim's rule).

Score = 45% construction logic + 45% scope completeness + 10% structure.
Each sub-score = 100 − (its % × sensitivity, default ×5), clamped 0–100.
Structure = 100 − missing_wbs×10 − suggestion_rate×0.5.
4 action bands: 85+ Ready to baseline · 70+ Minor gaps · 50+ Significant · else Major.
"""
from p6_ai.scoring import compute_score, band_for


def test_perfect_baseline_scores_100():
    s = compute_score(illogical_pct=0, missing_pct=0, missing_wbs=0,
                      suggestion_count=0, activity_count=100)
    assert s['logic'] == 100
    assert s['completeness'] == 100
    assert s['structure'] == 100
    assert s['overall'] == 100
    assert s['band_label'] == 'Ready to baseline'
    assert s['band'] == 'green'


def test_sub_scores_from_percentages_default_sensitivity():
    # 4% illogical → logic 80; 6% missing → completeness 70;
    # 2 missing WBS → −20; 18/180 = 10% suggestion rate → −5 → structure 75.
    s = compute_score(illogical_pct=4.0, missing_pct=6.0, missing_wbs=2,
                      suggestion_count=18, activity_count=180)
    assert s['logic'] == 80
    assert s['completeness'] == 70
    assert s['structure'] == 75
    # 0.45*80 + 0.45*70 + 0.10*75 = 75
    assert s['overall'] == 75
    assert s['band_label'] == 'Minor gaps'
    assert s['band'] == 'amber'


def test_percentages_clamp_at_zero():
    s = compute_score(illogical_pct=40, missing_pct=50, missing_wbs=30,
                      suggestion_count=999, activity_count=100)
    assert s['logic'] == 0
    assert s['completeness'] == 0
    assert s['structure'] == 0
    assert s['overall'] == 0
    assert s['band_label'] == 'Major gaps'
    assert s['band'] == 'red'


def test_sensitivity_is_configurable():
    lenient = compute_score(illogical_pct=4.0, missing_pct=4.0, missing_wbs=0,
                            suggestion_count=0, activity_count=100,
                            cfg={'sensitivity': 1})
    assert lenient['logic'] == 96  # 100 - 4*1
    strict = compute_score(illogical_pct=4.0, missing_pct=4.0, missing_wbs=0,
                           suggestion_count=0, activity_count=100,
                           cfg={'sensitivity': 10})
    assert strict['logic'] == 60  # 100 - 4*10


def test_weights_are_configurable():
    # All logic, no completeness/structure weight → overall == logic sub-score.
    s = compute_score(illogical_pct=10, missing_pct=99, missing_wbs=9,
                      suggestion_count=0, activity_count=100,
                      cfg={'weights': {'logic': 1.0, 'completeness': 0.0, 'structure': 0.0}})
    assert s['overall'] == s['logic'] == 50  # 100 - 10*5


def test_band_edges():
    assert band_for(100) == ('Ready to baseline', 'green')
    assert band_for(85) == ('Ready to baseline', 'green')
    assert band_for(84) == ('Minor gaps', 'amber')
    assert band_for(70) == ('Minor gaps', 'amber')
    assert band_for(69) == ('Significant gaps', 'orange')
    assert band_for(50) == ('Significant gaps', 'orange')
    assert band_for(49) == ('Major gaps', 'red')
    assert band_for(0) == ('Major gaps', 'red')
