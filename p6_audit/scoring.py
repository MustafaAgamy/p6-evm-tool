# ── V2 module scoring: KPI percentage → module score + grade ───────────────
# Score curve anchored to the agreed status bands (straight-line between).
# A LOWER percentage is better (fewer bad activities), so score falls as % rises.
_SCORE_ANCHORS = [(0.0, 100.0), (2.0, 90.0), (5.0, 75.0), (8.0, 50.0), (20.0, 0.0)]

# Status bands (percentage thresholds), best-first.
_PCT_BANDS = [(2.0, 'Excellent'), (5.0, 'Acceptable'), (8.0, 'Needs Attention')]


def module_score(pct):
    """Map a module KPI percentage (0..100, lower is better) to a 0-100 score."""
    if pct is None:
        return 100
    if pct <= 0:
        return 100
    if pct >= _SCORE_ANCHORS[-1][0]:
        return 0
    for (x0, y0), (x1, y1) in zip(_SCORE_ANCHORS, _SCORE_ANCHORS[1:]):
        if x0 <= pct <= x1:
            frac = (pct - x0) / (x1 - x0)
            return round(y0 + frac * (y1 - y0))
    return 0


def grade_for_pct(pct):
    """4-level engineering grade from the KPI percentage."""
    if pct is None:
        return 'Excellent'
    for cutoff, label in _PCT_BANDS:
        if pct <= cutoff:
            return label
    return 'Critical'


# ── Schedule Health Review scoring: score = 100 − defect%, uniform legend ──────
def linear_score(defect_pct):
    """Schedule Health Review model: score = 100 - defect%, shown as a percent. Clamped to [0,100], one decimal."""
    if defect_pct is None:
        return 100.0
    return round(max(0.0, min(100.0, 100.0 - defect_pct)), 1)


_UNIFORM_BANDS = [(98.0, 'Excellent'), (95.0, 'Good'), (90.0, 'Acceptable')]


def uniform_grade(score):
    """Uniform Schedule Health legend: >=98 Excellent, >=95 Good, >=90 Acceptable, else Critical."""
    if score is None:
        return 'Excellent'
    for cutoff, label in _UNIFORM_BANDS:
        if score >= cutoff:
            return label
    return 'Critical'


# ── Legacy penalty scoring (superseded by module scoring above; retained so
#    the original engine path and its tests keep working during the V2 build) ──
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
