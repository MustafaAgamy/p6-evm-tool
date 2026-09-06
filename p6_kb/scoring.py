"""Constructability Score — the 45 / 45 / 10 rubric (Ibrahim's rule).

Identical rubric to the dormant ``p6_ai.scoring`` (kept independent so the active
engine doesn't depend on the future-Pro module). Derived from the finding counts —
an honest computed number, not a confidence figure.

    overall = 0.45·logic + 0.45·completeness + 0.10·structure
    logic        = 100 − illogical_pct × sensitivity   (default ×5)
    completeness = 100 − missing_pct    × sensitivity
    structure    = 100 − missing_wbs × 10 − suggestion_rate × 0.5
"""

DEFAULT_CFG = {
    'sensitivity': 5,
    'weights': {'logic': 0.45, 'completeness': 0.45, 'structure': 0.10},
    'wbs_penalty': 10,
    'suggestion_load_factor': 0.5,
}

BANDS = [
    (85, 'Ready to baseline', 'green'),
    (70, 'Minor gaps', 'amber'),
    (50, 'Significant gaps', 'orange'),
    (0, 'Major gaps', 'red'),
]


def _clamp(v):
    return max(0.0, min(100.0, v))


def _round(v):
    return int(_clamp(v) + 0.5)


def band_for(score):
    for lo, label, color in BANDS:
        if score >= lo:
            return (label, color)
    return (BANDS[-1][1], BANDS[-1][2])


def compute_score(*, illogical_pct, missing_pct, missing_wbs,
                  suggestion_count, activity_count, cfg=None):
    cfg = cfg or {}
    sens = cfg.get('sensitivity', DEFAULT_CFG['sensitivity'])
    weights = cfg.get('weights', DEFAULT_CFG['weights'])
    wbs_penalty = cfg.get('wbs_penalty', DEFAULT_CFG['wbs_penalty'])
    load_factor = cfg.get('suggestion_load_factor', DEFAULT_CFG['suggestion_load_factor'])

    w_logic = weights.get('logic', DEFAULT_CFG['weights']['logic'])
    w_comp = weights.get('completeness', DEFAULT_CFG['weights']['completeness'])
    w_struct = weights.get('structure', DEFAULT_CFG['weights']['structure'])

    logic = _round(100 - illogical_pct * sens)
    completeness = _round(100 - missing_pct * sens)
    suggestion_rate = 100.0 * suggestion_count / max(activity_count, 1)
    structure = _round(100 - missing_wbs * wbs_penalty - suggestion_rate * load_factor)

    overall = _round(w_logic * logic + w_comp * completeness + w_struct * structure)
    label, color = band_for(overall)
    return {
        'logic': logic, 'completeness': completeness, 'structure': structure,
        'overall': overall, 'band_label': label, 'band': color,
        'sensitivity': sens,
        'weights': {'logic': w_logic, 'completeness': w_comp, 'structure': w_struct},
    }


# ── Constructability risk score — normalized finding-severity DENSITY ─────────
# A SECOND, distinct score beside the KB Constructability score above, computed only
# from the evidence-graded R1–R7 findings. Project-size independent (Ibrahim's V1 rule):
# a raw "100 − Σ impacts" collapses on a large project with many findings even when the
# finding density is low. So we normalise by project size:
#     severity points  : Strong = 10, Moderate = 5, Low = 2   (PER FINDING, never per activity)
#     weighted density  = (Σ severity points / total project activities) × 100
#     risk score        = clamp(100 − weighted density, 0, 100)
# One finding counts once regardless of how many activities it references.
EVIDENCE_CFG = {
    'severity_points': {'strong': 10, 'moderate': 5, 'weak': 2, 'insufficient': 2},
}

# Risk bands (Ibrahim's V1 spec). The score is a 0–100 where HIGHER = lower risk;
# the legend in the report makes that explicit.
EVIDENCE_BANDS = [
    (80, 'Low Risk', 'green'),
    (60, 'Moderate Risk', 'amber'),
    (40, 'Significant Risk', 'orange'),
    (0, 'High Risk', 'red'),
]

# Display names for evidence strength (internal 'weak'/'insufficient' both read as 'Low').
STRENGTH_DISPLAY = {'strong': 'Strong', 'moderate': 'Moderate', 'weak': 'Low', 'insufficient': 'Low'}


def _evidence_band(score):
    for lo, label, color in EVIDENCE_BANDS:
        if score >= lo:
            return (label, color)
    return (EVIDENCE_BANDS[-1][1], EVIDENCE_BANDS[-1][2])


def evidence_score(findings, total_activities=0, cfg=None):
    """Normalized constructability risk score from the R1–R7 findings, independent of
    project size. Score = clamp(100 − (Σ severity points / total activities) × 100, 0,
    100). Severity points are per FINDING (Strong 10 / Moderate 5 / Low 2), never per
    activity. An empty finding list is a legitimate 100. The caller only scores when an
    archetype resolved; it passes the project's total activity count for the density."""
    cfg = cfg or EVIDENCE_CFG
    pts_map = cfg.get('severity_points', EVIDENCE_CFG['severity_points'])
    findings = findings or []

    deductions, by_strength = [], {'strong': 0, 'moderate': 0, 'weak': 0, 'insufficient': 0}
    total_points = 0.0
    for f in findings:
        strength = f.get('strength', 'moderate')
        pts = pts_map.get(strength, pts_map['moderate'])
        total_points += pts
        by_strength[strength] = by_strength.get(strength, 0) + 1
        # stamp the per-finding severity points (one finding = one contribution, whatever
        # the activity count) — the report's 'Score Impact' column reads this.
        if isinstance(f, dict):
            f['score_impact'] = pts
        deductions.append({'title': f.get('title', ''), 'system': f.get('system'),
                           'strength': strength, 'points': pts})

    acts = max(int(total_activities or 0), 1)
    density = (total_points / acts) * 100.0
    overall = _round(max(0.0, 100.0 - density))
    label, color = _evidence_band(overall)
    deductions.sort(key=lambda d: -d['points'])
    return {
        'overall': overall, 'band': color, 'band_label': label,
        'total_severity_points': int(total_points),
        'weighted_finding_density': round(density, 2),
        'total_activities': acts, 'finding_count': len(findings),
        'by_strength': {k: v for k, v in by_strength.items() if v},
        'deductions': deductions,
        'basis': 'finding-severity density (project-size independent)',
    }
