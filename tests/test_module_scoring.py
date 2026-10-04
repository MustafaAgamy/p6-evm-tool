from p6_audit.scoring import module_score, grade_for_pct


def test_score_anchors():
    assert module_score(0) == 100
    assert module_score(2) == 90
    assert module_score(5) == 75
    assert module_score(8) == 50
    assert module_score(20) == 0
    assert module_score(39.3) == 0     # beyond 20% floors at 0


def test_score_interpolates_between_anchors():
    # 3.1% sits between 2%(90) and 5%(75): 90 - (1.1/3)*15 = 84.5 -> 84/85
    s = module_score(3.1)
    assert 84 <= s <= 85


def test_grade_bands():
    # defect % -> Score = 100 − % -> the one band legend (Pass ≥ 95 · Review 90–95 · Critical < 90)
    assert grade_for_pct(0) == 'Pass' and grade_for_pct(5) == 'Pass'
    assert grade_for_pct(5.1) == 'Review' and grade_for_pct(10) == 'Review'
    assert grade_for_pct(10.1) == 'Critical' and grade_for_pct(39.3) == 'Critical'
