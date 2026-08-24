"""Two-file features — Consultant Review and Update-vs-Update.

Each needs an extra schedule the single import doesn't provide, so its components
declare ``requires`` (a baseline XER, or a previous update). The UI highlights the
requirement and lets the user **attach** the file inline; the attached path arrives
on ``ctx.inputs[role]`` and this provider **runs the feature itself** — the user
never opens the feature's own tab. Same model as the Special Report.
"""

from p6_dashboard.registry import (
    register_provider, component,
    payload_kpi, payload_bars, payload_summary,
)
from p6_dashboard import fmt

SOURCE_CR = 'Consultant Review'
SOURCE_UU = 'Update vs Update'

BASELINE_REQ = [{'role': 'baseline', 'label': 'Baseline (XER/XML)',
                 'accept': '.xer,.xml', 'hint': 'the approved baseline schedule'}]
PREV_REQ = [{'role': 'previous', 'label': 'Previous update (XER/XML)',
             'accept': '.xml,.xer', 'hint': 'the earlier update to compare against'}]

_RED, _GREEN, _AMBER, _BLUE = '#c0504d', '#7cae4c', '#e0a13a', '#3b6fa8'


def _metrics_for(ctx, data):
    from p6_evm.metrics import compute
    from p6_evm.classify import auto_categories, build_wbs_classifier
    cfg = dict(ctx.config() or {})
    cfg['categories'] = auto_categories(data)
    return compute(data, cfg, classifier=build_wbs_classifier(data))


# ── Consultant Review (baseline vs update) ───────────────────────────────────

def _cmp_report(ctx):
    def build():
        cur, base = ctx.parsed(), ctx.parsed_input('baseline')
        if cur is None or base is None:
            return None
        from p6_compare.report import build_report_from_data
        return build_report_from_data(base, cur, ctx.config())
    return ctx.memo('cmp_report', build)


def _cmp_delay(ctx):
    if not ctx.has_input('baseline'):
        return payload_bars([])
    d = (_cmp_report(ctx) or {}).get('dashboard') or {}
    return payload_bars([
        {'label': 'Reported', 'value': d.get('delay_working_days') or 0,
         'display': fmt.signed_days(d.get('delay_working_days')), 'color': _RED},
        {'label': 'But-for (genuine)', 'value': d.get('butfor_delay_working_days') or 0,
         'display': fmt.signed_days(d.get('butfor_delay_working_days')), 'color': _GREEN},
        {'label': 'Manufactured', 'value': d.get('manufactured_working_days') or 0,
         'display': fmt.signed_days(d.get('manufactured_working_days')), 'color': _AMBER},
    ])


def _cmp_slip(ctx):
    if not ctx.has_input('baseline'):
        return payload_kpi('—', note='Attach a baseline to run')
    r = _cmp_report(ctx) or {}
    d = r.get('dashboard') or {}
    fs = d.get('finish_slip_days')
    bf, uf = r.get('baseline_finish'), r.get('update_finish')
    note = f'{bf} → {uf}' if (bf and uf) else 'update vs baseline finish'
    return payload_kpi(fmt.signed_days(fs), note=note, status=('bad' if (fs or 0) > 0 else 'good'))


# ── Update vs Update (previous vs current) ───────────────────────────────────

def _pd_report(ctx):
    def build():
        cur, prev = ctx.parsed(), ctx.parsed_input('previous')
        if cur is None or prev is None:
            return None
        from p6_period.report import build_report_from_data
        return build_report_from_data(prev, cur, _metrics_for(ctx, prev), ctx.computed(), ctx.config())
    return ctx.memo('pd_report', build)


def _pd_slip(ctx):
    if not ctx.has_input('previous'):
        return payload_kpi('—', note='Attach the previous update to run')
    s = (_pd_report(ctx) or {}).get('summary') or {}
    val = s.get('finish_slip_days')
    if val is None:
        val = s.get('delay_change')
    fa = s.get('forecast_achievement')
    note = f'forecast achievement {fa}%' if fa is not None else 'finish movement this period'
    return payload_kpi(fmt.signed_days(val), note=note, status=('bad' if (val or 0) > 0 else 'good'))


def _pd_summary(ctx):
    if not ctx.has_input('previous'):
        return payload_summary([])
    s = (_pd_report(ctx) or {}).get('summary') or {}
    return payload_summary([
        {'label': 'SPI now', 'value': fmt.num2(s.get('curr_spi')), 'status': fmt.spi_status(s.get('curr_spi'))},
        {'label': 'SPI prev', 'value': fmt.num2(s.get('prev_spi'))},
        {'label': 'Delay now', 'value': fmt.signed_days(s.get('delay_now'))},
        {'label': 'Delay change', 'value': fmt.signed_days(s.get('delay_change'))},
    ])


@register_provider
def provide(ctx):
    return [
        component('consultant.delay', 'Delay — reported vs but-for', SOURCE_CR, 'chart',
                  _cmp_delay, category='Time', size=1,
                  available=ctx.has_input('baseline'), requires=BASELINE_REQ),
        component('consultant.finish_slip', 'Finish Slip · but-for', SOURCE_CR, 'kpi',
                  _cmp_slip, category='Time',
                  available=ctx.has_input('baseline'), requires=BASELINE_REQ),
        component('period.slip', 'Finish Slip · this period', SOURCE_UU, 'kpi',
                  _pd_slip, category='Time',
                  available=ctx.has_input('previous'), requires=PREV_REQ),
        component('period.summary', 'Period Progress', SOURCE_UU, 'summary', size=1,
                  produce=_pd_summary,
                  category='Progress',
                  available=ctx.has_input('previous'), requires=PREV_REQ),
    ]
