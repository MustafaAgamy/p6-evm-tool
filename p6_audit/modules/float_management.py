"""Management-dashboard layer for the Float Analysis report (V2 redesign).

This is a PRESENTATION-SUPPORT layer only. It does NOT change how total float is
read or thresholded — it re-aggregates the per-activity float the parser already
produced into the numbers the redesigned management report shows:

  * whole-schedule Schedule Statistics  (Critical / Near-Critical)
  * Construction-scope Float Indicators (activities over the 44-WD threshold)
  * a DCMA-anchored Float Health score  (High Float + Negative Float drivers)
  * a per-WBS Float Distribution table  (all packages, worst concentration first)
  * an auto-written Executive Conclusion

Kept in its own module so the float calculation engine (run_float) stays untouched.
Construction is detected by MEANING from the WBS names (classify_branch_names) —
the same construction/civil/structural/concrete/MEP vocabulary used everywhere —
so it works on any project without relying on per-project config.
"""
from collections import defaultdict
from p6_evm.classify import classify_branch_names, DEFAULT_CATEGORY

# DCMA 14-Point float targets → transparent 0-100 penalty curve.
# High Float (Metric 5): > 44 WD should be < 5% of activities.
# Negative Float (Metric 6): < 0 float should be 0 activities.
FH_DEFAULTS = {
    'high_target_pct': 5.0,  'high_max_pct': 20.0, 'high_max_penalty': 60.0,
    'neg_target_pct':  0.0,  'neg_max_pct':  5.0,  'neg_max_penalty':  40.0,
}


def short_wbs(path, n=3):
    """Last n WBS levels for readability; full path travels as a tooltip on screen."""
    if not path:
        return ''
    parts = [p.strip() for p in path.split('>') if p.strip()]
    return ' > '.join(parts[-n:])


def activity_category(wbs_path):
    """Construction / Engineering / Design / Procurement for an activity, by the
    meaning of its WBS branch names (Construction is the fallback)."""
    parts = [p.strip() for p in (wbs_path or '').split('>') if p.strip()]
    if not parts:
        return DEFAULT_CATEGORY
    return classify_branch_names(list(reversed(parts)))  # classify expects leaf→root


def _penalty(pct, target, max_pct, max_penalty):
    if pct <= target:
        return 0.0
    span = max_pct - target
    if span <= 0:
        return max_penalty
    return min(max_penalty, (pct - target) / span * max_penalty)


def float_health(high_pct, neg_pct, cfg=None):
    """DCMA-anchored composite → (score 0-100, high-float penalty, negative-float penalty).
    Meeting both DCMA targets scores 100; each driver pulls the score down toward 0."""
    c = {**FH_DEFAULTS, **(cfg or {})}
    hp = _penalty(high_pct, c['high_target_pct'], c['high_max_pct'], c['high_max_penalty'])
    npn = _penalty(neg_pct, c['neg_target_pct'], c['neg_max_pct'], c['neg_max_penalty'])
    score = max(0, round(100 - hp - npn))
    return score, round(hp), round(npn)


def fh_color(score):
    """Colour band (no subjective word-grade): green ≥ 85 · amber 60–84 · red < 60."""
    if score >= 85:
        return 'green'
    if score >= 60:
        return 'amber'
    return 'red'


def _pct(n, d):
    return round(100.0 * n / d, 1) if d else 0.0


def _conclusion(wbs, high_pct, over, base, stats, threshold, neg_count):
    """Auto-written management summary — where float concentrates, not a stat dump."""
    parts = []
    if over == 0:
        parts.append(
            f"No construction activities exceed the {threshold}-working-day float threshold; "
            f"float across the construction scope looks tight.")
    else:
        parts.append(
            f"Across the construction scope, {high_pct}% of activities ({over} of {base}) carry total float "
            f"greater than {threshold} working days — the construction logic needs a planning review to "
            f"tighten the driving relationships.")
    non_hot = [r['wbs'] for r in wbs if (not r['is_construction']) and r['over_44'] > 0]
    if non_hot:
        parts.append(
            f"{' and '.join(non_hot[:3])} also show high float but are excluded from the construction "
            f"KPIs by design.")
    if neg_count:
        unit = 'activities' if neg_count != 1 else 'activity'
        parts.append(
            f"{neg_count} {unit} carry negative float and are behind their need dates — resolve these first.")
    else:
        parts.append(
            f"The critical path is well-defined ({stats['critical_pct']}% critical, "
            f"{stats['near_critical_pct']}% near-critical).")
    return ' '.join(parts)


def _status(a):
    return (a.get('status') or '').strip().lower().replace(' ', '')


def _completed(a):
    """P6 Completed activity — carries no live float, so it's out of a float analysis."""
    s = _status(a)
    if s == 'completed':
        return True
    if s in ('inprogress', 'notstarted'):
        return False
    return (a.get('percent_complete') or 0) >= 100   # fallback when P6 Status is absent


def _has_progress(a):
    """True once an activity has started (In Progress / Completed / any % complete) —
    used to tell a working update from an un-progressed baseline."""
    s = _status(a)
    if s in ('inprogress', 'completed'):
        return True
    if s == 'notstarted':
        return False
    return (a.get('percent_complete') or 0) > 0


def _top_wbs_key(paths):
    """Group key = the top-level WBS BRANCH as named in P6 — the WBS node directly under the
    project root. Skips a single shared project-root segment; falls back to the first segment
    when the schedule has no single shared root."""
    firsts = set()
    for p in paths:
        segs = [s.strip() for s in (p or '').split('>') if s.strip()]
        if segs:
            firsts.add(segs[0])
    single_root = len(firsts) == 1

    def key(p):
        segs = [s.strip() for s in (p or '').split('>') if s.strip()]
        if not segs:
            return '(no WBS)'
        return segs[1] if (single_root and len(segs) >= 2) else segs[0]
    return key


def float_management(graph, config):
    """Re-aggregate per-activity float into the management-dashboard numbers.
    Returns a dict attached to the float module result as `mgmt`."""
    audit = config.get('audit', {})
    threshold = audit.get('float_threshold_days', 44)
    near_band = audit.get('near_critical_days', 10)
    fh_cfg = audit.get('float_health') or {}
    eff = {**FH_DEFAULTS, **fh_cfg}

    real = [(oid, a) for oid, a in graph.activities.items() if graph.is_real_activity(oid)]
    # Float analysis is about REMAINING work — completed activities carry no live float.
    remaining = [(oid, a) for oid, a in real if not _completed(a)]
    assessable = [(oid, a) for oid, a in remaining if a.get('total_float_days') is not None]
    total = len(assessable)

    # Baseline (no progress anywhere) vs update (something has started) → tile wording.
    is_update = any(_has_progress(a) for _, a in real)
    total_label = 'Remaining Total Activities' if is_update else 'Total Activities'

    critical = [a for _, a in assessable if a.get('is_critical')]
    near = [a for _, a in assessable
            if not a.get('is_critical') and 0 < a['total_float_days'] <= near_band]
    negative = [a for _, a in assessable if a['total_float_days'] < 0]

    constr = [(oid, a) for oid, a in assessable
              if activity_category(a.get('wbs_path')) == 'Construction']
    constr_over = [a for _, a in constr if a['total_float_days'] > threshold]

    # Distribution grouped by the top-level WBS BRANCH as named in P6 — one row per branch, every
    # activity beneath it merged. Uses the schedule's own major WBS, not a re-classification.
    top_key = _top_wbs_key([a.get('wbs_path') or '' for _, a in assessable])
    by_wbs = defaultdict(list)
    for _, a in assessable:
        by_wbs[top_key(a.get('wbs_path') or '')].append(a['total_float_days'])
    wbs = []
    for name, floats in by_wbs.items():
        n = len(floats)
        over = sum(1 for f in floats if f > threshold)
        wbs.append({
            'wbs': name,
            'short': name,
            'activities': n,
            'avg_float': round(sum(floats) / n, 1) if n else 0.0,
            'max_float': round(max(floats), 1) if floats else 0.0,
            'over_44': over,
            'pct': _pct(over, n),
            'is_construction': activity_category(name) == 'Construction',
        })
    wbs.sort(key=lambda r: (-r['pct'], -r['over_44'], -r['activities']))

    high_pct = _pct(len(constr_over), len(constr))
    neg_pct = _pct(len(negative), total)
    score, high_pen, neg_pen = float_health(high_pct, neg_pct, fh_cfg)

    highest = max((a for _, a in assessable), key=lambda a: a['total_float_days'], default=None)
    highest_float = round(highest['total_float_days'], 1) if highest else 0.0
    highest_wbs = top_key(highest.get('wbs_path') or '') if highest else ''

    # top discipline by float concentration (worst first)
    top = wbs[0] if wbs else None

    stats = {
        'total': total, 'total_label': total_label, 'is_update': is_update,
        'critical': len(critical), 'critical_pct': _pct(len(critical), total),
        'near_critical': len(near), 'near_critical_pct': _pct(len(near), total),
        'near_band': near_band,
    }
    indicators = {
        'threshold': threshold,
        'constr_total': len(constr), 'constr_over': len(constr_over), 'constr_over_pct': high_pct,
        'top_wbs': (top['short'] if top else '—'),
        'top_wbs_pct': (top['pct'] if top else 0.0),
        'highest_float': highest_float, 'highest_float_wbs': highest_wbs,
    }
    return {
        'float_health': score, 'fh_color': fh_color(score),
        'high': {'pct': high_pct, 'penalty': high_pen, 'count': len(constr_over), 'base': len(constr),
                 'target': eff['high_target_pct'], 'max_pct': eff['high_max_pct'], 'max_penalty': eff['high_max_penalty']},
        'neg': {'pct': neg_pct, 'penalty': neg_pen, 'count': len(negative),
                'target': eff['neg_target_pct'], 'max_pct': eff['neg_max_pct'], 'max_penalty': eff['neg_max_penalty']},
        'stats': stats,
        'indicators': indicators,
        'wbs': wbs,
        'conclusion': _conclusion(wbs, high_pct, len(constr_over), len(constr), stats, threshold, len(negative)),
    }
