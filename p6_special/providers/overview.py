"""Overview provider — mirrors the Project ▸ Overview screen exactly.

The Overview screen (ui/modules/overview.js renderOverview) shows a 10-tile "Key
indicators" grid and a "Progress by category" bar list. A picked Overview result in
the Reporting Studio must look the same, so this provider reproduces those two
results verbatim from the stored EVM result (parse-free):

  * Key indicators — SPI, Forecast finish, Delay, Baseline finish, Overall planned,
    Overall actual, Planned value, Earned value, Actual cost, CPI — in the screen's
    order, with the screen's formatting and colours (SPI reddens below 1.0; Delay is
    red when behind / green when ahead; SPI and CPI are shown as ratios here, matching
    the Overview screen — NOT as percentages).
  * Progress by category — one planned/actual bar pair per WBS category.

It invents no verdict/RAG header and no cross-feature "attention" register (those do
not exist on the Overview screen); at-a-glance status lives under each owning feature.
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special.registry import Item

FEATURE = 'overview'
FEATURE_TITLE = 'Overview'


def _fmt_date(v):
    """Format as 'DD Mon YYYY' (e.g. '01 Jan 2026') to match the Overview screen's
    fmtDate; falls back to the raw date if it can't be parsed."""
    if not v:
        return fmt.DASH
    s = str(v).split('T')[0].split(' ')[0]
    try:
        from datetime import datetime
        return datetime.strptime(s, '%Y-%m-%d').strftime('%d %b %Y')
    except Exception:
        return s


def _delay_days(ctx):
    """Delay in days, matching the screen: stored delay_days, else forecast − baseline."""
    e = ctx.evm or {}
    d = e.get('delay_days')
    if d is not None:
        return d
    ex = ctx.extras or {}
    bf, ef = ex.get('baseline_finish'), ex.get('expected_finish')
    if bf and ef:
        try:
            from datetime import datetime
            fmt_in = '%Y-%m-%d'
            a = datetime.fromisoformat(str(ef)[:10])
            b = datetime.fromisoformat(str(bf)[:10])
            return (a - b).days
        except Exception:
            return None
    return None


def _kpi_grid(ctx):
    """The 10-tile Key-indicators grid, in the Overview screen's order + formatting."""
    e = ctx.evm or {}
    if not e:
        return P.NO_DATA
    ex = ctx.extras or {}
    spi, cpi = e.get('spi'), e.get('cpi')
    d = _delay_days(ctx)
    delay_tone = 'neutral' if d in (None,) else ('bad' if d > 0 else ('good' if d < 0 else 'neutral'))
    return P.kpi_group([
        P.kpi('SPI · schedule', fmt.ratio(spi), tone=('bad' if (spi is not None and spi < 1) else 'neutral')),
        P.kpi('Forecast finish', _fmt_date(ex.get('expected_finish')), tone='neutral'),
        P.kpi('Delay', (fmt.DASH if d is None else f'{int(round(d))} d'), tone=delay_tone),
        P.kpi('Baseline finish', _fmt_date(ex.get('baseline_finish')), tone='neutral'),
        P.kpi('Overall planned', fmt.pct01(e.get('overall_planned_pct'), dp=2), tone='neutral'),
        P.kpi('Overall actual', fmt.pct01(e.get('overall_actual_pct'), dp=2), tone='neutral'),
        P.kpi('Planned value', fmt.num(e.get('pv')), tone='neutral'),
        P.kpi('Earned value', fmt.num(e.get('ev')), tone='neutral'),
        P.kpi('Actual cost', fmt.num(e.get('ac')), tone='neutral'),
        P.kpi('CPI · cost', fmt.ratio(cpi), tone='neutral'),
    ])


def _cat_label(name, c):
    """The category's bar label, folding in the sub-line the screen shows under each
    name: ``<name> (<N> activities[ · manual override])`` — matching overview.js's
    ``<span>${c.activity_count} activities${c.overridden ? ' · manual override' : ''}</span>``.
    The count is dropped only when the stored value is missing."""
    parts = []
    n = c.get('activity_count')
    if n is not None:
        parts.append(f'{int(n)} activities')
    if c.get('overridden'):
        parts.append('manual override')
    return f'{name} ({" · ".join(parts)})' if parts else name


def _category_bars(ctx):
    """Per-category planned/actual bars, matching the screen's Progress-by-category list
    (values on a literal 0..100 scale, plan + actual per category). Each row's label
    carries the screen's per-category sub-line (activity count + manual-override flag)."""
    e = ctx.evm or {}
    cats = e.get('categories') or {}
    if not cats:
        return P.NO_DATA
    rows = []
    for name, c in cats.items():
        p, a = c.get('planned_pct'), c.get('actual_pct')
        rows.append({'label': _cat_label(name, c),
                     'values': [(p or 0) * 100, (a or 0) * 100],
                     'display': [fmt.pct01(p, dp=2), fmt.pct01(a, dp=2)]})
    return P.bars(
        rows=rows,
        series=[{'label': 'Planned', 'tone': 'neutral'},
                {'label': 'Actual', 'tone': 'accent'}],
    )


def _count(n):
    """Integer count as the header chips print it (raw integer, or '—' when absent),
    matching overview.js's ``${result.activity_count ?? '—'}``."""
    return fmt.DASH if n is None else f'{int(n)}'


def _snapshot(ctx):
    """The header 'at a glance' chip row as a label/value list — Data date, Activities,
    Calendars, WBS categories — mirroring overview.js's ``ov-chips`` block."""
    e = ctx.evm or {}
    if not e:
        return P.NO_DATA
    cats = e.get('categories') or {}
    return P.keyvals([
        ('Data date', _fmt_date(e.get('data_date'))),
        ('Activities', _count(e.get('activity_count'))),
        ('Calendars', _count(e.get('calendar_count'))),
        ('WBS categories', f'{len(cats)}'),
    ])


def _snapshot_avail(ctx):
    return 'ready' if ctx.evm else 'no_data'


def _kpis_avail(ctx):
    return 'ready' if ctx.evm else 'no_data'


def _cats_avail(ctx):
    return 'ready' if (ctx.evm or {}).get('categories') else 'no_data'


def provide(ctx):
    return [
        Item('overview:snapshot', FEATURE, FEATURE_TITLE, 'Project snapshot',
             'summary', _snapshot, _snapshot_avail),
        Item('overview:kpis', FEATURE, FEATURE_TITLE, 'Key indicators',
             'kpi', _kpi_grid, _kpis_avail),
        Item('overview:categories', FEATURE, FEATURE_TITLE, 'Progress by category',
             'chart', _category_bars, _cats_avail),
    ]
