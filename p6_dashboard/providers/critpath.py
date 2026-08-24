"""Critical Path Analyzer provider.

CPA compares the critical path across schedules, so it needs a baseline the single
import doesn't provide. The component declares ``requires`` (a baseline XER/XML); the
UI lets the user attach it inline, the path arrives on ``ctx.inputs['baseline']`` and
this provider **runs CPA itself** (current vs baseline) — the user never opens the
CPA tab. Same model as the Special Report and the two-file provider.
"""

from p6_dashboard.registry import (
    register_provider, component, payload_kpi, payload_score, payload_bars,
)
from p6_dashboard import fmt

SOURCE = 'Critical Path Analyzer'
BASELINE_REQ = [{'role': 'baseline', 'label': 'Baseline (XER/XML)',
                 'accept': '.xer,.xml', 'hint': 'the approved baseline to compare against'}]
_STATUS = {'good': 'good', 'warn': 'warn', 'bad': 'bad'}


def _cp(ctx):
    def build():
        cur, base = ctx.parsed(), ctx.parsed_input('baseline')
        if cur is None or base is None:
            return None
        from p6_critpath.analysis import build_report
        from p6_critpath.dashboard import build_dashboard
        rep = build_report({'current': cur, 'baseline': base}, mode='update_baseline')
        return {'report': rep, 'dash': build_dashboard(rep)}
    return ctx.memo('cp', build)


def _cur_census(ctx):
    r = _cp(ctx) or {}
    return ((r.get('report') or {}).get('census') or {}).get('current') or {}


def _cpli_kpi(ctx):
    if not ctx.has_input('baseline'):
        return payload_kpi('—', note='Attach a baseline to run')
    v = (_cp(ctx) or {}).get('dash', {}).get('cpli')
    return payload_kpi(fmt.num2(v), note='Critical Path Length Index',
                       status=('good' if (v or 0) >= 1 else 'bad'))


def _cpli_health(ctx):
    if not ctx.has_input('baseline'):
        return payload_score(0, band='Not run', status='neutral', detail='Attach a baseline to run')
    dash = (_cp(ctx) or {}).get('dash') or {}
    v = dash.get('cpli') or 0
    return payload_score(int(round(min(v, 1.5) / 1.5 * 100)),
                         band=dash.get('status_label') or '',
                         status=_STATUS.get(dash.get('status'), 'neutral'),
                         detail=dash.get('verdict') or f'CPLI {fmt.num2(v)}')


def _census(ctx):
    if not ctx.has_input('baseline'):
        return payload_bars([])
    c = _cur_census(ctx)
    return payload_bars([
        {'label': 'Critical', 'value': c.get('critical') or 0, 'display': c.get('critical') or 0, 'color': '#c0504d'},
        {'label': 'Near-critical', 'value': c.get('near') or 0, 'display': c.get('near') or 0, 'color': '#e0a13a'},
    ])


@register_provider
def provide(ctx):
    have = ctx.has_input('baseline')
    return [
        component('critpath.cpli', 'CPLI', SOURCE, 'kpi', _cpli_kpi,
                  category='Time', available=have, requires=BASELINE_REQ),
        component('critpath.cpli_gauge', 'CPLI Health', SOURCE, 'score', _cpli_health,
                  category='Time', size=1, available=have, requires=BASELINE_REQ),
        component('critpath.census', 'Critical / Near-critical', SOURCE, 'chart', _census,
                  category='Time', size=1, available=have, requires=BASELINE_REQ),
    ]
