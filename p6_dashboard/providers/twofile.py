"""Two-file feature provider — Consultant Review and Update-vs-Update.

Both features compare TWO schedule files, so they cannot be recomputed from the
single open project the way EVM/audit providers do. Instead, when the user runs
either feature in its own tab, the app persists a small summary into the
per-project settings blob. This provider reads only those persisted summaries
(``dashboard_consultant`` / ``dashboard_period``) via :meth:`ctx.settings`.

When a summary is absent the component still appears in the catalog — but with
``available=False`` and a note telling the user to run that feature first, and a
friendly placeholder payload if it is ever rendered anyway.
"""

from p6_dashboard.registry import (
    register_provider, component,
    payload_kpi, payload_bars, payload_line,
)
from p6_dashboard import fmt

SOURCE_CR = 'Consultant Review'
SOURCE_UU = 'Update vs Update'

# Notes shown when the feature hasn't been run yet.
_NOTE_CR = 'Run Consultant Review (baseline + update) to populate.'
_NOTE_UU = 'Run Update vs Update (this period vs last) to populate.'

# Office-style chart colours matching the tool's report look.
_RED, _GREEN, _AMBER, _BLUE = '#c0504d', '#7cae4c', '#e0a13a', '#3b6fa8'


@register_provider
def provide(ctx):
    s = ctx.settings() or {}
    dc = s.get('dashboard_consultant')   # dict | None
    dp = s.get('dashboard_period')       # dict | None
    out = []

    # ── Consultant Review ───────────────────────────────────────────────────
    avail_cr = bool(dc)

    def _delay(c, dc=dc):
        if not dc:
            return payload_bars([])
        return payload_bars([
            {'label': 'Reported', 'value': dc.get('reported_delay') or 0,
             'display': fmt.signed_days(dc.get('reported_delay')), 'color': _RED},
            {'label': 'But-for (genuine)', 'value': dc.get('butfor_delay') or 0,
             'display': fmt.signed_days(dc.get('butfor_delay')), 'color': _GREEN},
            {'label': 'Manufactured', 'value': dc.get('manufactured') or 0,
             'display': fmt.signed_days(dc.get('manufactured')), 'color': _AMBER},
        ], unit='d')

    out.append(component(
        'consultant.delay', 'Delay — reported vs but-for', SOURCE_CR, 'chart',
        _delay, category='Time', size=1,
        available=avail_cr, note=(None if avail_cr else _NOTE_CR),
        needs='Baseline (XER) + this update', action='compare'))

    def _finish_slip(c, dc=dc, absent_note=_NOTE_CR):
        if not dc:
            return payload_kpi('—', note=absent_note)
        fs = dc.get('finish_slip')
        bf, uf = dc.get('baseline_finish'), dc.get('update_finish')
        note = f'{bf} → {uf}' if (bf and uf) else 'Update vs baseline finish'
        return payload_kpi(
            fmt.signed_days(fs), note=note,
            status=('bad' if (fs or 0) > 0 else 'good'))

    out.append(component(
        'consultant.finish_slip', 'Finish Slip · but-for', SOURCE_CR, 'kpi',
        _finish_slip, category='Time',
        available=avail_cr, note=(None if avail_cr else _NOTE_CR),
        needs='Baseline (XER) + this update', action='compare'))

    # ── Update vs Update ────────────────────────────────────────────────────
    avail_uu = bool(dp)
    spi_series = dp.get('spi_series') if dp else None
    avail_trend = bool(dp and spi_series)

    def _period_slip(c, dp=dp, absent_note=_NOTE_UU):
        if not dp:
            return payload_kpi('—', note=absent_note)
        val = dp.get('finish_slip') or dp.get('delay_change')
        fa = dp.get('forecast_achievement')
        note = f'forecast achievement {fa}%' if fa is not None else ''
        return payload_kpi(
            fmt.signed_days(val), note=note,
            status=('bad' if (val or 0) > 0 else 'good'))

    out.append(component(
        'period.slip', 'Finish Slip · this period', SOURCE_UU, 'kpi',
        _period_slip, category='Time',
        available=avail_uu, note=(None if avail_uu else _NOTE_UU),
        needs='The previous update schedule', action='period'))

    def _spi_trend(c, series=spi_series, absent_note=_NOTE_UU):
        if not series:
            return payload_line([])
        return payload_line([{
            'name': 'SPI', 'color': _BLUE,
            'points': [(v or 0) * 100 for v in series],
        }], y_max=100)

    out.append(component(
        'period.spi_trend', 'SPI Trend · by period', SOURCE_UU, 'trend',
        _spi_trend, category='Progress', size=1,
        available=avail_trend, note=(None if avail_trend else _NOTE_UU),
        needs='The previous update schedule', action='period'))

    return out
