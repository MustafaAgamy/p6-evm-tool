"""Baseline Constructability Score — Ibrahim's 45 / 45 / 10 rubric.

The score is an **honest derived number**, not an AI confidence figure: it is
computed here in plain Python from the counted findings (how many illogical
relationships, how many missing activities, how many missing WBS branches, how
many suggestions the AI had to make). The AI supplies the findings; this module
turns their counts into the score.

    overall = 0.45·logic + 0.45·completeness + 0.10·structure

    logic        = 100 − illogical_pct   × sensitivity   (default ×5)
    completeness = 100 − missing_pct      × sensitivity
    structure    = 100 − missing_wbs × 10 − suggestion_rate × 0.5

All sub-scores clamp to 0–100. Bands (action labels shown on the report):
    ≥85 Ready to baseline · ≥70 Minor gaps · ≥50 Significant gaps · else Major gaps

Every constant is overridable via ``cfg`` (the ``ai`` block of ``config.json``),
because the numbers are Ibrahim's to tune.
"""

DEFAULT_CFG = {
    'sensitivity': 5,
    'weights': {'logic': 0.45, 'completeness': 0.45, 'structure': 0.10},
    'wbs_penalty': 10,             # points off structure per missing WBS branch
    'suggestion_load_factor': 0.5,  # points off structure per 1% suggestion rate
}

# (min_score_inclusive, label, colour) — highest first.
BANDS = [
    (85, 'Ready to baseline', 'green'),
    (70, 'Minor gaps', 'amber'),
    (50, 'Significant gaps', 'orange'),
    (0, 'Major gaps', 'red'),
]


def _clamp(v):
    return max(0.0, min(100.0, v))


def _round(v):
    """Round-half-up on a clamped 0–100 value (deterministic, no banker's rounding)."""
    return int(_clamp(v) + 0.5)


def band_for(score):
    """(label, colour) for an overall score."""
    for lo, label, color in BANDS:
        if score >= lo:
            return (label, color)
    return (BANDS[-1][1], BANDS[-1][2])


def compute_score(*, illogical_pct, missing_pct, missing_wbs,
                  suggestion_count, activity_count, cfg=None):
    """Return the three sub-scores, the blended overall, and its band.

    Args are the counted outputs of the AI review (percentages already computed
    against the schedule's totals). ``cfg`` may override any DEFAULT_CFG key,
    partially — missing keys fall back to the defaults.
    """
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
        'logic': logic,
        'completeness': completeness,
        'structure': structure,
        'overall': overall,
        'band_label': label,
        'band': color,
        'sensitivity': sens,
        'weights': {'logic': w_logic, 'completeness': w_comp, 'structure': w_struct},
    }
