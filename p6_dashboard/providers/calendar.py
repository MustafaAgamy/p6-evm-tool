"""Calendar Audit provider — working-time headline KPIs from the stored Calendar
Audit blob, plus the optional weather-adjusted finish from the last Weather run.

All parse-free: the audit blob comes from ``ctx.calendar()`` and the weather result
from ``ctx.settings()['last_weather']`` (Decision 001 — read the DB, never re-parse).
Follows the EVM provider pattern: read every value via ``ctx`` at provide() time and
bind it into the produce lambda's defaults so ``produce`` needs no closure state."""

from p6_dashboard.registry import (
    register_provider, component,
    payload_kpi,
)
from p6_dashboard import fmt

SOURCE = 'Calendar Audit'


@register_provider
def provide(ctx):
    cal = ctx.calendar()
    if not cal:
        # No Calendar Audit stored → this feature contributes nothing.
        return []

    dash = cal.get('dashboard') or {}
    settings = ctx.settings() or {}
    weather = settings.get('last_weather')
    avail = bool(cal)
    out = []

    wd = dash.get('total_working_days')
    out.append(component(
        'calendar.working_days', 'Working Days', SOURCE, 'kpi',
        lambda c, v=wd: payload_kpi(v, note='over the baseline window'),
        category='Time', available=avail))

    nwd = dash.get('total_nonworking_days')
    out.append(component(
        'calendar.nonworking', 'Non-working Days', SOURCE, 'kpi',
        lambda c, v=nwd: payload_kpi(v, note='weekends, holidays & shutdowns'),
        category='Time', available=avail))

    shut = dash.get('shutdown_periods')
    out.append(component(
        'calendar.shutdowns', 'Shutdowns', SOURCE, 'kpi',
        lambda c, v=shut: payload_kpi(v, note='shutdown period(s)'),
        category='Time', available=avail))

    exc = dash.get('total_exceptions')
    out.append(component(
        'calendar.exceptions', 'Calendar Exceptions', SOURCE, 'kpi',
        lambda c, v=exc: payload_kpi(v, note='holidays + special days'),
        category='Time', available=avail))

    # Weather-adjusted finish — only meaningful once a Weather run is stored for the
    # project. When absent, still surface the component (available=False) so the user
    # sees it exists and how to enable it.
    if weather:
        delay = weather.get('net_finish_delay')
        bad_total = weather.get('expected_bad_days_total')
        adj_finish = weather.get('weather_adjusted_finish')
        out.append(component(
            'calendar.weather_finish', 'Weather-adjusted Finish', SOURCE, 'kpi',
            lambda c, d=delay, n=bad_total, adj=adj_finish: payload_kpi(
                fmt.signed_days(d),
                note=f'{n} bad-weather days est. · weather-adjusted {adj}',
                status=('warn' if (d or 0) > 0 else 'good')),
            category='Time', available=True))
    else:
        out.append(component(
            'calendar.weather_finish', 'Weather-adjusted Finish', SOURCE, 'kpi',
            lambda c: payload_kpi('—', note='Not run yet'),
            category='Time', available=False,
            note='Set the project location in Calendar Audit → Weather to enable.'))

    return out
