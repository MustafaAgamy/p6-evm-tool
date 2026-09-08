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


def _full_ready(ctx):
    """The full EVM report re-renders from a fresh XML parse (ctx.computed), so it
    must gate on the file being available — not just on the DB metrics existing —
    or an evicted-cache project would advertise 'ready' then render 'No data'."""
    if not ctx.evm:
        return 'needs_run'
    return 'ready' if ctx.has_xml() else 'no_data'


def _paired_ready(ctx):
    if not ctx.evm:
        return 'needs_run'
    e = ctx.evm
    return 'ready' if (e.get('overall_planned_pct') is not None
                       or e.get('overall_actual_pct') is not None) else 'no_data'


def _value_ready(ctx):
    if not ctx.evm:
        return 'needs_run'
    e = ctx.evm
    return 'ready' if any(isinstance(e.get(k), (int, float)) for k in ('pv', 'ev', 'ac')) else 'no_data'


def _cats_ready(ctx):
    if not ctx.evm:
        return 'needs_run'
    return 'ready' if (ctx.evm or {}).get('categories') else 'no_data'


def _var_tone(v):
    if v is None:
        return 'neutral'
    return 'good' if v >= 0 else 'bad'


def _ratio_tone(x):
    if x is None:
        return 'neutral'
    return 'good' if x >= 1 else 'bad'


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# ── trend helpers (a straight READ of the stored per-snapshot rows) ───────────
def _date10(d):
    """A snapshot's data_date as a 'YYYY-MM-DD' x-axis label (or None)."""
    return str(d)[:10] if d else None


def _points(ctx, key, scale=1.0):
    """The metric `key` per snapshot (oldest→newest); null stays None (a gap)."""
    return [(s.get(key) * scale) if _num(s.get(key)) else None
            for s in (ctx.snapshots_trend() or [])]


def _count_present(ctx, key):
    return sum(1 for s in (ctx.snapshots_trend() or []) if _num(s.get(key)))


def _spark(ctx, key, scale=1.0):
    """Up to the last 8 non-null values of `key` (oldest→newest), or None if <2.

    The sparkline needs ≥2 real points to mean anything; a lone value is left off
    rather than drawn as a flat line."""
    vals = [s.get(key) * scale for s in (ctx.snapshots_trend() or []) if _num(s.get(key))]
    return vals[-8:] if len(vals) >= 2 else None


def _delta(ctx, key, fmt_fn, scale=1.0):
    """Raw change of `key` vs the previous snapshot — the second-to-last row by
    data_date (``ctx.snapshots`` is ordered data_date ASC). No smoothing, no
    threshold. None when <2 snapshots or either endpoint is null."""
    snaps = ctx.snapshots_trend() or []
    if len(snaps) < 2:
        return None
    cur, prev = snaps[-1].get(key), snaps[-2].get(key)
    if not (_num(cur) and _num(prev)):
        return None
    return fmt_fn((cur - prev) * scale)


def _trend_ready(key):
    """A trend is 'ready' only with ≥2 snapshots carrying a non-null `key`."""
    def _avail(ctx):
        return 'ready' if _count_present(ctx, key) >= 2 else 'no_data'
    return _avail


# ── atomic KPI producers ─────────────────────────────────────────────────────
def _kpi_planned(ctx):
    e = ctx.evm or {}
    return P.kpi_group([P.kpi('Planned %', fmt.pct01(e.get('overall_planned_pct')),
                              sub='where the plan says we should be', tone='accent',
                              spark=_spark(ctx, 'overall_planned_pct', scale=100.0),
                              delta=_delta(ctx, 'overall_planned_pct',
                                           lambda d: f'{d:+.1f}%', scale=100.0),
                              delta_tone='neutral')])


def _kpi_actual(ctx):
    e = ctx.evm or {}
    return P.kpi_group([P.kpi('Actual %', fmt.pct01(e.get('overall_actual_pct')),
                              sub='where the project actually is', tone='neutral',
                              spark=_spark(ctx, 'overall_actual_pct', scale=100.0),
                              delta=_delta(ctx, 'overall_actual_pct',
                                           lambda d: f'{d:+.1f}%', scale=100.0),
                              delta_tone='neutral')])


def _kpi_variance(ctx):
    e = ctx.evm or {}
    p, a = e.get('overall_planned_pct'), e.get('overall_actual_pct')
    v = (a - p) if (p is not None and a is not None) else None
    return P.kpi_group([P.kpi('Variance', fmt.signed_pct01(v),
                              sub='actual minus planned', tone=_var_tone(v))])


def _kpi_spi(ctx):
    e = ctx.evm or {}
    return P.kpi_group([P.kpi('SPI', fmt.ratio(e.get('spi')),
                              sub='schedule performance index', tone=_ratio_tone(e.get('spi')),
                              spark=_spark(ctx, 'spi'),
                              delta=_delta(ctx, 'spi', lambda d: f'{d:+.2f}'),
                              delta_tone='neutral')])


def _kpi_cpi(ctx):
    e = ctx.evm or {}
    return P.kpi_group([P.kpi('CPI', fmt.ratio(e.get('cpi')),
                              sub='cost performance index', tone=_ratio_tone(e.get('cpi')),
                              spark=_spark(ctx, 'cpi'),
                              delta=_delta(ctx, 'cpi', lambda d: f'{d:+.2f}'),
                              delta_tone='neutral')])


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
                              sub='working days behind baseline finish', tone=tone,
                              spark=_spark(ctx, 'delay_days'),
                              delta=_delta(ctx, 'delay_days', lambda x: f'{x:+.0f} d'),
                              delta_tone='neutral')])


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


# ── trend producers (a straight read of the stored per-update rows) ───────────
def _trend_spi_cpi(ctx):
    snaps = ctx.snapshots_trend() or []
    return P.line(
        [{'label': 'SPI', 'tone': 'accent', 'points': _points(ctx, 'spi')},
         {'label': 'CPI', 'tone': 'good', 'points': _points(ctx, 'cpi')}],
        x=[_date10(s.get('data_date')) for s in snaps],
        ref={'value': 1.0, 'label': '1.00 target'},
        note='Across the weekly updates')


def _trend_delay(ctx):
    snaps = ctx.snapshots_trend() or []
    return P.line(
        [{'label': 'Delay (d)', 'tone': 'bad', 'points': _points(ctx, 'delay_days')}],
        x=[_date10(s.get('data_date')) for s in snaps],
        note='Working days behind baseline finish, per update')


def _trend_progress(ctx):
    snaps = ctx.snapshots_trend() or []
    return P.line(
        [{'label': 'Planned %', 'tone': 'neutral',
          'points': _points(ctx, 'overall_planned_pct', scale=100.0)},
         {'label': 'Actual %', 'tone': 'accent',
          'points': _points(ctx, 'overall_actual_pct', scale=100.0)}],
        x=[_date10(s.get('data_date')) for s in snaps],
        y_max=100, note='Weekly updates')


# ── discipline progress gap ───────────────────────────────────────────────────
# Re-presents the SAME per-category numbers the category table reads
# (`_category_table` above): planned_pct / actual_pct are 0..1 fractions shown via
# fmt.pct01, and the behind/slightly-behind band is the same 0 / -0.05 split. No
# EVM is recomputed — this is only a worst-first variance view of stored values.
def _is_structural(c):
    """A zero-weight / weightless category carries no progress signal."""
    w = c.get('weight')
    return not _num(w) or w == 0


def _gap_categories(ctx):
    cats = (ctx.evm or {}).get('categories') or {}
    return [(name, c) for name, c in cats.items() if not _is_structural(c)]


def _gap_tone(v):
    """Same banding the category table uses: on/ahead → good, small miss → warn,
    a large (>5 pt) miss → bad."""
    if v is None:
        return 'neutral'
    if v >= 0:
        return 'good'
    return 'warn' if v >= -0.05 else 'bad'


def _discipline_gap(ctx):
    items = _gap_categories(ctx)
    if not items:
        return P.NO_DATA
    rows = []
    for name, c in items:
        p, a = c.get('planned_pct'), c.get('actual_pct')
        v = (a - p) if (_num(p) and _num(a)) else None       # actual − planned (0..1)
        shortfall = (p or 0) - (a or 0)                        # planned − actual, sort key
        rows.append((shortfall, {
            'label': name,
            'values': [(a or 0) * 100],
            'display': [fmt.pct01(a)],
            'target': (p or 0) * 100,
            'target_display': fmt.pct01(p),
            'tone': _gap_tone(v),
        }))
    rows.sort(key=lambda r: r[0], reverse=True)                # worst (largest shortfall) first
    return P.bars(
        rows=[r for _, r in rows],
        series=[{'label': 'Actual', 'tone': 'accent'}],
        style='variance',
        note='Bar = actual · tick = planned · shaded = shortfall')


def _discipline_gap_ready(ctx):
    return 'ready' if _gap_categories(ctx) else 'no_data'


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
             'Planned % vs Actual % — overall (paired)', 'chart', _paired, _paired_ready),
        Item('evm:category_table', FEATURE, FEATURE_TITLE,
             'Planned % vs Actual % — by category', 'table', _category_table, _cats_ready),
        Item('evm:spi', FEATURE, FEATURE_TITLE, 'SPI', 'kpi', _kpi_spi, A),
        Item('evm:cpi', FEATURE, FEATURE_TITLE, 'CPI', 'kpi', _kpi_cpi, A),
        Item('evm:pv', FEATURE, FEATURE_TITLE, 'Planned Value (PV)', 'kpi', _kpi_pv, A),
        Item('evm:ev', FEATURE, FEATURE_TITLE, 'Earned Value (EV)', 'kpi', _kpi_ev, A),
        Item('evm:ac', FEATURE, FEATURE_TITLE, 'Actual Cost (AC)', 'kpi', _kpi_ac, A),
        Item('evm:delay', FEATURE, FEATURE_TITLE, 'Delay in working days', 'kpi', _kpi_delay, A),
        Item('evm:pv_ev_ac', FEATURE, FEATURE_TITLE, 'Planned / Earned / Actual value (chart)', 'chart', _pv_ev_ac, _value_ready),
        Item('evm:gap', FEATURE, FEATURE_TITLE, 'PV − EV gap by activity code', 'table', _gap, _gap_ready),
        Item('evm:trend_spi_cpi', FEATURE, FEATURE_TITLE, 'SPI / CPI trend', 'chart',
             _trend_spi_cpi, _trend_ready('spi')),
        Item('evm:trend_delay', FEATURE, FEATURE_TITLE, 'Delay trend (days)', 'chart',
             _trend_delay, _trend_ready('delay_days')),
        Item('evm:trend_progress', FEATURE, FEATURE_TITLE, 'Progress trend — planned vs actual', 'chart',
             _trend_progress, _trend_ready('overall_actual_pct')),
        Item('evm:discipline_gap', FEATURE, FEATURE_TITLE, 'Discipline progress gap — worst first', 'chart',
             _discipline_gap, _discipline_gap_ready),
        Item('evm:full_report', FEATURE, FEATURE_TITLE, 'Full EVM report (detailed)', 'section',
             lambda ctx: FR.evm_full_report(ctx) or P.NO_DATA, _full_ready),
    ]
