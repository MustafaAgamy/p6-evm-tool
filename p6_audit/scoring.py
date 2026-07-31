CATEGORY_OF_CHECK = {
    'LOGIC-001': 'Schedule Logic',
    'LOGIC-002': 'Schedule Logic',
    'LOGIC-003': 'Schedule Logic',
    'FLOAT-001': 'Float Analysis',
}

_GRADES = [(95, 'Excellent'), (85, 'Very Good'), (70, 'Good'), (50, 'Fair'), (0, 'Poor')]


def _grade(score):
    for cutoff, label in _GRADES:
        if score >= cutoff:
            return label
    return 'Poor'


def score_categories(findings, config):
    audit_cfg = config.get('audit', {})
    penalties = audit_cfg.get('severity_penalties', {})
    weights = audit_cfg.get('category_weights', {})
    result = {}
    for cat, weight in weights.items():
        cat_findings = [f for f in findings if CATEGORY_OF_CHECK.get(f.check_id) == cat]
        penalty = sum(penalties.get(f.severity, 0) for f in cat_findings)
        result[cat] = {
            'score': max(0, 100 - penalty),
            'finding_count': len(cat_findings),
            'weight': weight,
        }
    return result


def overall_score(category_scores):
    total_weight = sum(c['weight'] for c in category_scores.values())
    if not total_weight:
        return {'score': 100, 'categories_evaluated': 0, 'categories_total': 0, 'grade': 'Excellent'}
    weighted = sum(c['score'] * c['weight'] for c in category_scores.values()) / total_weight
    score = round(weighted)
    return {
        'score': score,
        'categories_evaluated': len(category_scores),
        'categories_total': len(category_scores),
        'grade': _grade(score),
    }
