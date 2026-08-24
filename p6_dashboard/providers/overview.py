"""Project Overview provider — the top-of-board summary tile plus a cross-feature
attention panel. All parse-free: reads the stored EVM result, evm_extras and the
stored audit modules (Decision 001). Never recomputes a feature's numbers — it only
re-presents what the EVM tab and the Schedule Audit modules already produced.
"""

from p6_dashboard.registry import (
    register_provider, component,
    payload_summary, payload_findings,
)
from p6_dashboard import fmt

SOURCE = 'Project Overview'

# Worst-first ordering for the attention panel.
_SEV_RANK = {'bad': 0, 'warn': 1, 'info': 2}


def _signed_pts(actual, planned):
    """Signed 'points ahead/behind plan' string + status. 'good' when at/ahead of
    plan (>= 0), 'bad' when behind; '—'/neutral when either side is missing."""
    if actual is None or planned is None:
        return '—', 'neutral'
    diff = actual - planned
    sign = '+' if diff >= 0 else ''
    return f'{sign}{diff:.1f} pts', ('good' if diff >= 0 else 'bad')


def _plural(n, one='y', many='ies'):
    return one if n == 1 else many


def _build_alerts(evm, audit):
    """Top ~5 attention items across EVM + the stored audit modules, worst first.

    EVM-derived flags are always considered (they work with no audit). Audit modules
    are read defensively — any that is absent simply contributes nothing.
    """
    items = []

    # ── EVM-derived flags (available even when audit is None) ────────────────
    delay = evm.get('delay_days')
    if delay is not None and delay > 0:
        d = int(round(delay))
        items.append({
            'severity': 'bad', 'source': 'EVM Results',
            'text': f'Project finish is {d} working day{"s" if d != 1 else ""} behind baseline.',
        })

    spi = evm.get('spi')
    if spi is not None and spi < 0.85:
        items.append({
            'severity': 'bad', 'source': 'EVM Results',
            'text': f'SPI {fmt.num2(spi)} — schedule performance is behind plan.',
        })

    # ── Audit-derived flags (each module guarded) ───────────────────────────
    modules = (audit or {}).get('modules') or {}

    # Out of Sequence — critical / near-critical progress breaking predecessor logic.
    m = modules.get('out_of_sequence') or {}
    k = m.get('kpis') or {}
    src = m.get('name') or 'Out of Sequence'
    crit_oos = k.get('critical_oos') or 0
    near_oos = k.get('near_critical_oos') or 0
    oos = k.get('oos_count') or 0
    oos_pct = k.get('oos_pct')
    if crit_oos > 0:
        items.append({
            'severity': 'bad', 'source': src,
            'text': f'{crit_oos} out-of-sequence activit{_plural(crit_oos)} on the critical '
                    f'path — direct completion-date impact.',
        })
    elif near_oos > 0:
        items.append({
            'severity': 'warn', 'source': src,
            'text': f'{oos} out-of-sequence activit{_plural(oos)} ({fmt.pct(oos_pct)} of '
                    f'schedule); {near_oos} near-critical.',
        })
    elif oos > 0:
        items.append({
            'severity': 'info', 'source': src,
            'text': f'{oos} out-of-sequence activit{_plural(oos)} ({fmt.pct(oos_pct)} of schedule).',
        })

    # Float Analysis — activities over the float threshold (DCMA high-float line = 5%).
    m = modules.get('float') or {}
    k = m.get('kpis') or {}
    src = m.get('name') or 'Float Analysis'
    fpct = k.get('float_pct')
    thr = k.get('threshold')
    if fpct is not None and fpct > 5.0:
        items.append({
            'severity': 'warn', 'source': src,
            'text': f'{fmt.pct(fpct)} of activities exceed the {thr}-day float threshold '
                    f'(DCMA line 5%).',
        })

    # Lag & Lead — DCMA verdict + links needing a documented reason.
    m = modules.get('lag_lead') or {}
    k = m.get('kpis') or {}
    src = m.get('name') or 'Lag & Lead'
    if (k.get('verdict') or '') == 'Needs attention':
        need = k.get('need_justification_count') or 0
        text = k.get('verdict_reason') or (
            f'{need} lag/lead link{"s" if need != 1 else ""} need justification.')
        items.append({'severity': 'warn', 'source': src, 'text': text})

    # Dangling Activities — open ends (start/finish not driven by logic).
    m = modules.get('dangling') or {}
    k = m.get('kpis') or {}
    src = m.get('name') or 'Dangling Activities'
    dang = k.get('total_dangling') or 0
    dpct = k.get('dangling_pct')
    if dang > 0:
        sev = 'warn' if (dpct or 0) > 5.0 else 'info'
        items.append({
            'severity': sev, 'source': src,
            'text': f'{dang} dangling activit{_plural(dang)} ({fmt.pct(dpct)}) — '
                    f'open ends in the logic.',
        })

    items.sort(key=lambda it: _SEV_RANK.get(it['severity'], 3))
    return items[:5]


@register_provider
def provide(ctx):
    evm = ctx.evm()
    if not evm:
        return []
    extras = ctx.extras() or {}
    audit = ctx.audit()
    avail = bool(evm)
    out = []

    # ── Summary tile ─────────────────────────────────────────────────────────
    act = evm.get('overall_actual_pct')
    plan = evm.get('overall_planned_pct')
    delta_text, delta_status = _signed_pts(act, plan)
    forecast = extras.get('expected_finish') or '—'
    stats = [
        {'label': 'Overall Complete', 'value': fmt.pct(act)},
        {'label': 'Planned to Date', 'value': fmt.pct(plan)},
        {'label': 'Behind/Ahead Plan', 'value': delta_text, 'status': delta_status},
        {'label': 'Forecast Finish', 'value': forecast},
    ]
    out.append(component(
        'overview.summary', 'Project Summary', SOURCE, 'summary',
        lambda c, stats=stats: payload_summary(stats),
        category='Overview', size=2, default_on=True, available=avail))

    # ── Attention panel (cross-feature alerts) ───────────────────────────────
    alerts = _build_alerts(evm, audit)
    out.append(component(
        'overview.alerts', 'Attention Required', SOURCE, 'findings',
        lambda c, items=alerts: payload_findings(items),
        category='Overview', size=1, default_on=True, available=avail))

    return out
