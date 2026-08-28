"""EVM provider — the reference provider for Special Report.

All items are parse-free: they read the stored result from ``ctx.evm``
(db.get_project_result). Metrics are offered atomically (Planned %, Actual %,
Variance, SPI, CPI, PV, EV, AC, Delay) so the user picks exactly what they
want — plus a couple of curated combined items (paired bars, category table).

Copy this file's shape to add a provider for another feature:
  - ``provide(ctx)`` returns a list of ``Item``; keep it cheap.
  - each ``Item`` has a globally-unique id ``"<feature>:<key>"``.
  - each ``produce(ctx)`` returns a payload (see p6_special.payloads).
  - ``availability(ctx)`` returns 'ready' | 'needs_run' | 'no_data'.
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special import feature_reports as FR
from p6_special.registry import Item

FEATURE = 'evm'
FEATURE_TITLE = 'EVM Report'


def _ready(ctx):
    return 'ready' if ctx.evm else 'needs_run'


def _var_tone(v):
    if v is None:
        return 'neutral'
    return 'good' if v >= 0 else 'bad'


def _ratio_tone(x):
    if x is None:
        return 'neutral'
    return 'good' if x >= 1 else 'bad'


# ── atomic KPI producers ─────────────────────────────────────────────────────
def _kpi_planned(ctx):
    e = ctx.evm or {}
    return P.kpi_group([P.kpi('Planned %', fmt.pct01(e.get('overall_planned_pct')),
                              sub='where the plan says we should be', tone='accent')])


def _kpi_actual(ctx):
    e = ctx.evm or {}
    return P.kpi_group([P.kpi('Actual %', fmt.pct01(e.get('overall_actual_pct')),
                              sub='where the project actually is', tone='neutral')])


def _kpi_variance(ctx):
    e = ctx.evm or {}
    p, a = e.get('overall_planned_pct'), e.get('overall_actual_pct')
    v = (a - p) if (p is not None and a is not None) else None
    return P.kpi_group([P.kpi('Variance', fmt.signed_pct01(v),
                              sub='actual minus planned', tone=_var_tone(v))])


def _kpi_spi(ctx):
    e = ctx.evm or {}
    return P.kpi_group([P.kpi('SPI', fmt.ratio(e.get('spi')),
                              sub='schedule performance index', tone=_ratio_tone(e.get('spi')))])


def _kpi_cpi(ctx):
    e = ctx.evm or {}
    return P.kpi_group([P.kpi('CPI', fmt.ratio(e.get('cpi')),
                              sub='cost performance index', tone=_ratio_tone(e.get('cpi')))])


def _kpi_pv(ctx):
    e = ctx.evm or {}
    return P.kpi_group([P.kpi('Planned Value (PV)', fmt.money(e.get('pv')), tone='neutral')])


def _kpi_ev(ctx):
    e = ctx.evm or {}
    return P.kpi_group([P.kpi('Earned Value (EV)', fmt.money(e.get('ev')), tone='accent')])


def _kpi_ac(ctx):
    e = ctx.evm or {}
    return P.kpi_group([P.kpi('Actual Cost (AC)', fmt.money(e.get('ac')), tone='neutral')])


def _kpi_delay(ctx):
    e = ctx.evm or {}
    d = e.get('delay_days')
    tone = 'neutral' if d is None else ('good' if d <= 0 else 'bad')
    return P.kpi_group([P.kpi('Finish Delay', fmt.days(d),
                              sub='working days behind baseline finish', tone=tone)])


# ── combined items ───────────────────────────────────────────────────────────
def _paired(ctx):
    e = ctx.evm or {}
    p, a = e.get('overall_planned_pct'), e.get('overall_actual_pct')
    if p is None and a is None:
        return P.NO_DATA
    return P.bars(
        rows=[{'label': 'Overall progress',
               'values': [(p or 0) * 100, (a or 0) * 100],
               'display': [fmt.pct01(p), fmt.pct01(a)]}],
        series=[{'label': 'Planned', 'tone': 'neutral'},
                {'label': 'Actual', 'tone': 'accent'}],
    )


def _category_table(ctx):
    e = ctx.evm or {}
    cats = e.get('categories') or {}
    if not cats:
        return P.NO_DATA
    rows = []
    for name, c in cats.items():
        w = c.get('weight')
        p = c.get('planned_pct')
        a = c.get('actual_pct')
        v = (a - p) if (p is not None and a is not None) else None
        if v is None:
            status = ('—', 'neutral')
        elif v >= 0:
            status = ('On / ahead', 'good')
        elif v >= -0.05:
            status = ('Slightly behind', 'warn')
        else:
            status = ('Behind', 'bad')
        rows.append([
            name, fmt.pct01(w), fmt.pct01(p), fmt.pct01(a),
            (fmt.signed_pct01(v), _var_tone(v)), status,
        ])
    return P.table(
        columns=['Category', 'Weight', 'Planned %', 'Actual %', 'Variance', 'Status'],
        rows=rows,
        aligns=['l', 'r', 'r', 'r', 'r', 'l'],
    )


def _pv_ev_ac(ctx):
    e = ctx.evm or {}
    pv, ev, ac = e.get('pv'), e.get('ev'), e.get('ac')
    vals = [x for x in (pv, ev, ac) if isinstance(x, (int, float))]
    if not vals:
        return P.NO_DATA
    amax = max(vals) * 1.05
    return P.bars(
        rows=[{'label': 'Value', 'values': [pv or 0, ev or 0, ac or 0],
               'display': [fmt.money(pv), fmt.money(ev), fmt.money(ac)]}],
        series=[{'label': 'Planned Value', 'tone': 'neutral'},
                {'label': 'Earned Value', 'tone': 'accent'},
                {'label': 'Actual Cost', 'tone': 'warn'}],
        axis_max=amax)


def _gap_rows(ctx):
    """The PV−EV gap-by-code rows if present for this snapshot, else None.

    ``gap`` is optional stored data (only present when the engineering/E1 gap was
    computed), so its item gates on this rather than on EVM alone — otherwise it
    would advertise as 'ready' and then render an empty 'No data' section, the
    exact silent-empty case Special Report must avoid."""
    gap = (ctx.extras or {}).get('gap')
    if isinstance(gap, list) and gap and isinstance(gap[0], dict):
        return gap
    return None


def _gap(ctx):
    gap = _gap_rows(ctx)
    if gap:
        from p6_special.providers import _util as U
        return U.table_from_dicts(gap)
    return P.NO_DATA


def _gap_ready(ctx):
    if not ctx.evm:
        return 'needs_run'
    return 'ready' if _gap_rows(ctx) is not None else 'no_data'


def provide(ctx):
    A = _ready
    return [
        Item('evm:planned_pct', FEATURE, FEATURE_TITLE, 'Planned % — overall', 'kpi', _kpi_planned, A),
        Item('evm:actual_pct', FEATURE, FEATURE_TITLE, 'Actual % — overall', 'kpi', _kpi_actual, A),
        Item('evm:variance', FEATURE, FEATURE_TITLE, 'Variance — overall', 'kpi', _kpi_variance, A),
        Item('evm:planned_vs_actual', FEATURE, FEATURE_TITLE,
             'Planned % vs Actual % — overall (paired)', 'chart', _paired, A),
        Item('evm:category_table', FEATURE, FEATURE_TITLE,
             'Planned % vs Actual % — by category', 'table', _category_table, A),
        Item('evm:spi', FEATURE, FEATURE_TITLE, 'SPI', 'kpi', _kpi_spi, A),
        Item('evm:cpi', FEATURE, FEATURE_TITLE, 'CPI', 'kpi', _kpi_cpi, A),
        Item('evm:pv', FEATURE, FEATURE_TITLE, 'Planned Value (PV)', 'kpi', _kpi_pv, A),
        Item('evm:ev', FEATURE, FEATURE_TITLE, 'Earned Value (EV)', 'kpi', _kpi_ev, A),
        Item('evm:ac', FEATURE, FEATURE_TITLE, 'Actual Cost (AC)', 'kpi', _kpi_ac, A),
        Item('evm:delay', FEATURE, FEATURE_TITLE, 'Delay in working days', 'kpi', _kpi_delay, A),
        Item('evm:pv_ev_ac', FEATURE, FEATURE_TITLE, 'Planned / Earned / Actual value (chart)', 'chart', _pv_ev_ac, A),
        Item('evm:gap', FEATURE, FEATURE_TITLE, 'PV − EV gap by activity code', 'table', _gap, _gap_ready),
        Item('evm:full_report', FEATURE, FEATURE_TITLE, 'Full EVM report (detailed)', 'section',
             lambda ctx: FR.evm_full_report(ctx) or P.NO_DATA, A),
    ]
