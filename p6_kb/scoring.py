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


# ── MEP-first evidence-weighted score (Phase 3) ──────────────────────────────
# A SECOND, distinct score beside the KB Constructability score above. It reads the
# evidence-graded R1–R7 findings only, and deducts from 100 by
#     points = strength_base × discipline_weight
# so a strong, MEP/commissioning finding costs the most and a weak civil-interface
# finding the least. MEP-first (Ibrahim's rule): commissioning / mechanical / electrical
# / piping / instrumentation carry full weight; civil enters only at its interface and
# is weighted lowest. Deterministic — an honest computed number, not a confidence figure.
EVIDENCE_CFG = {
    # cost of one finding at each evidence strength, before the discipline weight
    'strength_base': {'strong': 10, 'moderate': 5, 'weak': 2, 'insufficient': 2},
    # MEP-first discipline multipliers
    'discipline_weight': {'mep': 1.0, 'structural': 0.7, 'civil': 0.5, 'other': 0.8},
}

EVIDENCE_BANDS = [
    (85, 'Execution logic sound', 'green'),
    (70, 'Minor sequence risks', 'amber'),
    (50, 'Significant sequence risks', 'orange'),
    (0, 'Serious sequence risks', 'red'),
]

_MEP_ROOTS = ('MECH', 'ELEC', 'ELV', 'PIP', 'INSTR', 'PLUMB', 'FIRE', 'PROCESS', 'UTIL',
              'HVAC', 'MATERIAL HANDLING', 'BULK', 'CONVEY', 'COMMISSION')


def _evidence_band(score):
    for lo, label, color in EVIDENCE_BANDS:
        if score >= lo:
            return (label, color)
    return (EVIDENCE_BANDS[-1][1], EVIDENCE_BANDS[-1][2])


def _discipline_class(system, discipline):
    """MEP-first bucket for a finding, from its system then its KB discipline text.
    Civil enters only at its interface (weighted lowest); steel is structural; every
    real MEP / commissioning discipline is full-weight."""
    if system == 'civil_interface':
        return 'civil'
    if system == 'structural_steel':
        return 'structural'
    d = (discipline or '').upper()
    if any(root in d for root in _MEP_ROOTS):
        return 'mep'
    if 'CIVIL' in d:
        return 'civil'
    if 'STRUCT' in d:
        return 'structural'
    return 'other'


def evidence_score(findings, cfg=None):
    """Score the evidence-graded R1–R7 findings, MEP-first, strength-weighted. An empty
    finding list is a legitimate 100 (execution logic sound) — the caller decides whether
    it analysed the schedule at all (only score when an archetype actually resolved)."""
    cfg = cfg or EVIDENCE_CFG
    base = cfg.get('strength_base', EVIDENCE_CFG['strength_base'])
    dw = cfg.get('discipline_weight', EVIDENCE_CFG['discipline_weight'])
    findings = findings or []

    deductions, by_strength = [], {'strong': 0, 'moderate': 0, 'weak': 0, 'insufficient': 0}
    total = 0.0
    for f in findings:
        strength = f.get('strength', 'moderate')
        cls = _discipline_class(f.get('system'), f.get('discipline'))
        pts = base.get(strength, base['moderate']) * dw.get(cls, dw['other'])
        total += pts
        by_strength[strength] = by_strength.get(strength, 0) + 1
        deductions.append({
            'title': f.get('title', ''), 'system': f.get('system'),
            'discipline_class': cls, 'strength': strength, 'points': round(pts, 1),
        })

    overall = _round(100 - total)
    label, color = _evidence_band(overall)
    deductions.sort(key=lambda d: -d['points'])
    return {
        'overall': overall, 'band': color, 'band_label': label,
        'total_deducted': round(total, 1), 'finding_count': len(findings),
        'by_strength': {k: v for k, v in by_strength.items() if v},
        'deductions': deductions,
        'weights': {'strength_base': base, 'discipline_weight': dw},
        'basis': 'MEP-first · strength × discipline weight',
    }
