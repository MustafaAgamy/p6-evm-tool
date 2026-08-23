"""Update Analysis provider — time status, activity-status counts, and the driving
path's work fronts.

Unlike the parse-free providers (EVM, Audit, Calendar), Update Analysis is **not
persisted** — it is re-derived on demand from the parsed schedule + its EVM metrics.
So ``provide`` stays cheap (only ``ctx.has_xml()``, no parse) and the recompute runs
once inside ``produce`` via a shared memo (``ctx.memo('update', ...)``), so all three
components share a single ``build_report_from_data`` call per dashboard request.
"""

from p6_dashboard.registry import (
    register_provider, component,
    payload_kpi, payload_bars, payload_table,
)
from p6_dashboard import fmt

SOURCE = 'Update Analysis'

# Office-style status colours (match the tool's report look).
_GREEN, _BLUE, _RED = '#7cae4c', '#3b6fa8', '#c0504d'

_UNAVAILABLE_NOTE = 'Open Update Analysis once for this project.'

_MON = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def _fmt_date(s):
    """ISO 'YYYY-MM-DD' (box bl_finish / exp_finish) → house '09-Feb.2027' read."""
    if not s:
        return '—'
    try:
        from datetime import datetime
        d = datetime.strptime(str(s)[:10], '%Y-%m-%d')
        return f'{d.day:02d}-{_MON[d.month - 1]}.{d.year}'
    except Exception:
        return str(s)


# ── Shared recompute (memoised: one parse+build for all three components) ─────

def _report(ctx):
    """The full Update-Analysis report, computed once per dashboard request."""
    return ctx.memo('update', lambda c=ctx: _run(c))


def _run(ctx):
    data = ctx.parsed()
    metrics = ctx.computed()
    if data is None or metrics is None:
        return None
    try:
        from p6_update.analysis import build_report_from_data
        return build_report_from_data(data, metrics)
    except Exception:
        return None


# ── Component payload builders (only run when a component is rendered) ─────────

def _produce_time(ctx):
    rep = _report(ctx) or {}
    ts = rep.get('time_status') or {}
    ep = ts.get('elapsed_pct')
    if ep is None:
        return payload_kpi('—', note=_UNAVAILABLE_NOTE, status='neutral')
    exceeded = ts.get('exceeded_days') or 0
    if exceeded and exceeded > 0:
        note = f'of the baseline window · baseline finish exceeded by {exceeded} d'
        status = 'bad'
    else:
        note = 'of the baseline window'
        status = 'neutral'
    return payload_kpi(fmt.pct(ep), note=note, status=status)


def _produce_counts(ctx):
    rep = _report(ctx) or {}
    counts = rep.get('counts') or {}
    rows = [
        {'label': 'Completed', 'value': counts.get('actual_completed') or 0, 'color': _GREEN},
        {'label': 'In Progress', 'value': counts.get('actual_in_progress') or 0, 'color': _BLUE},
        {'label': 'Not Started', 'value': counts.get('actual_not_started') or 0, 'color': _RED},
    ]
    return payload_bars(rows)


def _produce_critical_path(ctx):
    rep = _report(ctx) or {}
    cp = rep.get('critical_path') or {}
    charts = cp.get('charts') or []
    boxes = (charts[0].get('boxes') if charts else None) or []
    rows = [
        [b.get('name') or '—', fmt.pct(b.get('pct')), _fmt_date(b.get('exp_finish'))]
        for b in boxes
    ]
    return payload_table(['Work front', 'Complete', 'Forecast finish'], rows)


# ── Provider ──────────────────────────────────────────────────────────────────

@register_provider
def provide(ctx):
    """Cheap: gate on whether the XML is reachable (no parse here). The recompute is
    deferred into the produce callbacks above."""
    available = ctx.has_xml()

    if not available:
        # Emit the descriptors so the feature still shows in the catalog, greyed with a
        # note; produce returns a friendly empty payload if ever rendered.
        return [
            component(
                'update.time_elapsed', 'Time Elapsed', SOURCE, 'kpi',
                lambda c, n=_UNAVAILABLE_NOTE: payload_kpi('—', note=n, status='neutral'),
                category='Time', size=1, default_on=True,
                available=False, note=_UNAVAILABLE_NOTE),
            component(
                'update.counts', 'Activity Status', SOURCE, 'chart',
                lambda c: payload_bars([]),
                category='Progress', size=1, default_on=False,
                available=False, note=_UNAVAILABLE_NOTE),
            component(
                'update.critical_path', 'Driving Path Work Fronts', SOURCE, 'table',
                lambda c: payload_table(['Work front', 'Complete', 'Forecast finish'], []),
                category='Time', size=2, default_on=True,
                available=False, note=_UNAVAILABLE_NOTE),
        ]

    return [
        component(
            'update.time_elapsed', 'Time Elapsed', SOURCE, 'kpi',
            _produce_time,
            category='Time', size=1, default_on=True, available=True),
        component(
            'update.counts', 'Activity Status', SOURCE, 'chart',
            _produce_counts,
            category='Progress', size=1, default_on=False, available=True),
        component(
            'update.critical_path', 'Driving Path Work Fronts', SOURCE, 'table',
            _produce_critical_path,
            category='Time', size=2, default_on=True, available=True),
    ]
