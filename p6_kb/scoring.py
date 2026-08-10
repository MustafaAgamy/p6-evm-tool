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
