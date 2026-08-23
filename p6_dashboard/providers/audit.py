"""Schedule Audit provider — per-check health scores + headline logic KPIs.

Parse-free: reads the stored audit modules (Decision 001). The persisted module dict
exposes only ``score``/``grade``/``pct``/``kpis``/``wbs_summary``/``findings`` — NOT
the float module's live ``mgmt`` layer — so Float Health here uses the module's own
0-100 ``score`` (which is persisted), never a mgmt-only field.
"""

from p6_dashboard.registry import (
    register_provider, component,
    payload_kpi, payload_score, payload_status, payload_summary,
)
from p6_dashboard import fmt

SOURCE = 'Schedule Audit'


def _modules(ctx):
    return (ctx.audit() or {}).get('modules') or {}


def _find(mods, *candidate_ids):
    """Return the module dict matching any of the candidate ids — checked against both
    the dict key and each module's own 'module' field (naming varies: 'oos' vs
    'out_of_sequence', 'lag' vs 'lag_lead')."""
    cands = set(candidate_ids)
    for cid in candidate_ids:
        if cid in mods:
            return mods[cid]
    for m in mods.values():
        if isinstance(m, dict) and m.get('module') in cands:
            return m
    return None


@register_provider
def provide(ctx):
    mods = _modules(ctx)
    if not mods:
        return []

    order = (ctx.audit() or {}).get('module_order') or list(mods.keys())
    out = []

    # Schedule health by check — one row per module, worst first.
    def _health(c, order=order, mods=mods):
        stats = []
        for key in order:
            m = mods.get(key)
            if not isinstance(m, dict):
                continue
            score = m.get('score')
            stats.append({'label': m.get('name') or key,
                          'value': int(round(score)) if score is not None else '—',
                          'status': fmt.band_status(score)})
        stats.sort(key=lambda s: (s['value'] if isinstance(s['value'], int) else 999))
        return payload_summary(stats)

    out.append(component(
        'audit.health', 'Schedule Health by Check', SOURCE, 'summary',
        _health, category='Logic', size=1, default_on=True))

    # Float Health — the Float module's own 0-100 score (persisted).
    fl = _find(mods, 'float', 'float_analysis')
    if isinstance(fl, dict):
        out.append(component(
            'audit.float_health', 'Float Health', SOURCE, 'score',
            lambda c, m=fl: payload_score(
                int(round(m.get('score'))) if m.get('score') is not None else 0,
                band=m.get('grade') or '', status=fmt.band_status(m.get('score')),
                detail=_float_detail(m.get('kpis') or {})),
            category='Logic', size=1, default_on=True))

    # Out of sequence %.
    oos = _find(mods, 'oos', 'out_of_sequence')
    if isinstance(oos, dict):
        k = oos.get('kpis') or {}
        out.append(component(
            'audit.oos', 'Out of Sequence', 'Out of Sequence', 'kpi',
            lambda c, k=k: payload_kpi(
                fmt.pct(k.get('oos_pct')),
                note=f"{k.get('oos_count', 0)} activities · {k.get('critical_oos', 0)} critical",
                status=_pct_status(k.get('oos_pct'), 5, 10)),
            category='Logic', default_on=True))

    # Lag & Lead verdict.
    lag = _find(mods, 'lag', 'lag_lead')
    if isinstance(lag, dict):
        k = lag.get('kpis') or {}
        out.append(component(
            'audit.lag', 'Lag & Lead Verdict', 'Lag Report', 'status',
            lambda c, k=k: payload_status(
                k.get('verdict') or 'Reviewed',
                status=_verdict_status(k.get('verdict')),
                note=(k.get('verdict_reason')
                      or f"lag {fmt.pct(k.get('lagged_pct'))} · "
                         f"{k.get('need_justification_count', 0)} need justification")),
            category='Logic', size=1))

    # Dangling logic.
    dang = _find(mods, 'dangling')
    if isinstance(dang, dict):
        k = dang.get('kpis') or {}
        out.append(component(
            'audit.dangling', 'Dangling Logic', SOURCE, 'kpi',
            lambda c, k=k: payload_kpi(
                fmt.pct(k.get('dangling_pct')),
                note=f"{k.get('total_dangling', 0)} activities open-ended",
                status=_pct_status(k.get('dangling_pct'), 5, 15)),
            category='Logic'))

    return out


def _float_detail(kpis):
    fp = kpis.get('float_pct')
    if fp is None:
        return ''
    return f"High-float {fmt.pct(fp)} · threshold {kpis.get('threshold', '—')} d"


def _pct_status(v, warn, bad):
    if v is None:
        return 'neutral'
    if v >= bad:
        return 'bad'
    if v >= warn:
        return 'warn'
    return 'good'


def _verdict_status(verdict):
    v = (verdict or '').lower()
    if 'attention' in v or 'critical' in v or 'fail' in v:
        return 'bad'
    if 'review' in v or 'caution' in v:
        return 'warn'
    return 'good'
