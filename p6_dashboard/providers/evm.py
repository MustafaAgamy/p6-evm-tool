"""EVM Results provider — headline KPIs + PV/EV, discipline progress and PV−EV gap
charts. All parse-free: read from the stored metrics + evm_extras (Decision 001)."""

from p6_dashboard.registry import (
    register_provider, component,
    payload_kpi, payload_bars,
)
from p6_dashboard import fmt

SOURCE = 'EVM Results'

# Office-style chart colours matching the tool's report look.
_BLUE, _GREEN, _AMBER = '#3b6fa8', '#7cae4c', '#e0a13a'


@register_provider
def provide(ctx):
    evm = ctx.evm()
    if not evm:
        return []
    extras = ctx.extras() or {}
    out = []

    spi = evm.get('spi')
    out.append(component(
        'evm.spi', 'SPI · Schedule', SOURCE, 'kpi',
        lambda c, v=spi: payload_kpi(
            fmt.num2(v),
            note=('Behind schedule' if (v or 0) < 0.95 else 'On schedule'),
            status=fmt.spi_status(v)),
        category='Time', default_on=True))

    cpi = evm.get('cpi')
    out.append(component(
        'evm.cpi', 'CPI · Cost', SOURCE, 'kpi',
        lambda c, v=cpi: payload_kpi(
            fmt.num2(v),
            note=('Over budget' if (v or 0) < 0.95 else 'On budget'),
            status=fmt.spi_status(v)),
        category='Cost', default_on=True))

    delay = evm.get('delay_days')
    out.append(component(
        'evm.delay', 'Delay · working days', SOURCE, 'kpi',
        lambda c, v=delay: payload_kpi(
            fmt.signed_days(v),
            note=('No slip vs baseline' if not v else 'Finish milestone slip'),
            status=('good' if not v else 'bad')),
        category='Time', default_on=True))

    var = evm.get('variance')
    out.append(component(
        'evm.variance', 'Cost Variance', SOURCE, 'kpi',
        lambda c, v=var: payload_kpi(
            fmt.money(v),
            note=('EV below PV' if (v or 0) < 0 else 'EV at/above PV'),
            status=('bad' if (v or 0) < 0 else 'good')),
        category='Cost', default_on=True))

    act = evm.get('overall_actual_pct')
    plan = evm.get('overall_planned_pct')
    out.append(component(
        'evm.actual_pct', 'Overall Complete', SOURCE, 'kpi',
        lambda c, v=act: payload_kpi(fmt.pct(v), note='Actual % complete',
                                     status='neutral'),
        category='Progress'))
    out.append(component(
        'evm.planned_pct', 'Planned to Date', SOURCE, 'kpi',
        lambda c, v=plan: payload_kpi(fmt.pct(v), note='Planned % to data date',
                                      status='neutral'),
        category='Progress'))

    # Planned vs Earned Value bars.
    pv, ev = evm.get('pv'), evm.get('ev')
    if pv is not None or ev is not None:
        out.append(component(
            'evm.pvev', 'Earned Value vs Planned Value', SOURCE, 'chart',
            lambda c, pv=pv, ev=ev: payload_bars([
                {'label': 'Planned (PV)', 'value': pv or 0, 'display': fmt.money(pv), 'color': _BLUE},
                {'label': 'Earned (EV)', 'value': ev or 0, 'display': fmt.money(ev), 'color': _GREEN},
            ], unit='EGP'),
            category='Cost', default_on=True))

    # Progress by discipline (category actual %).
    cats = evm.get('categories') or {}
    disc = [(n, v) for n, v in cats.items()
            if (v.get('weight') or 0) > 0 and v.get('actual_pct') is not None]
    if disc:
        out.append(component(
            'evm.categories', 'Progress by Discipline', SOURCE, 'chart',
            lambda c, disc=disc: payload_bars([
                {'label': n, 'value': v.get('actual_pct') or 0,
                 'display': fmt.pct(v.get('actual_pct')), 'color': _BLUE}
                for n, v in disc], unit='%'),
            category='Progress', default_on=True))

    # PV − EV gap by code (from stored extras).
    gap = extras.get('gap')
    groups = (gap or {}).get('groups') if isinstance(gap, dict) else None
    if groups:
        top = sorted(groups, key=lambda g: g.get('gap') or 0, reverse=True)[:6]
        out.append(component(
            'evm.gap', 'PV − EV Gap by Code', SOURCE, 'chart',
            lambda c, top=top: payload_bars([
                {'label': g.get('code') or '—', 'value': g.get('gap') or 0,
                 'display': fmt.money(g.get('gap')), 'color': _AMBER}
                for g in top], unit='EGP'),
            category='Cost'))

    return out
