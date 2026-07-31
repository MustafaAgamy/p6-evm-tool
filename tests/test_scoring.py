from p6_audit.findings import Finding
from p6_audit.scoring import score_categories, overall_score, CATEGORY_OF_CHECK

CONFIG = {'audit': {
    'severity_penalties': {'Critical': 25, 'High': 12, 'Medium': 5, 'Low': 2},
    'category_weights': {'Schedule Logic': 0.5, 'Float Analysis': 0.5},
}}


def _f(check_id, sev):
    return Finding(check_id=check_id, check_name='x', category=None, severity=sev,
                   activity_id='a', activity_name='a', wbs_path='')


def test_category_score_deducts_penalties():
    findings = [_f('LOGIC-001', 'High'), _f('LOGIC-002', 'Medium')]  # 12 + 5 = 17
    cats = score_categories(findings, CONFIG)
    assert cats['Schedule Logic']['score'] == 83
    assert cats['Float Analysis']['score'] == 100


def test_score_floors_at_zero():
    findings = [_f('LOGIC-003', 'Critical')] * 10  # 250 penalty
    cats = score_categories(findings, CONFIG)
    assert cats['Schedule Logic']['score'] == 0


def test_overall_is_weighted_and_reports_coverage():
    cats = score_categories([_f('LOGIC-001', 'High')], CONFIG)  # Logic 88, Float 100
    ov = overall_score(cats)
    assert ov['score'] == 94  # 0.5*88 + 0.5*100
    assert ov['categories_total'] == 2
    assert ov['grade'] == 'Very Good'
