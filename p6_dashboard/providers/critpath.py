"""Critical Path Analyzer provider.

The CPA compares the critical path across 2–3 schedules, so its results (CPLI,
critical/near-critical census, reroute) aren't derivable from the single open
project. Its cards therefore appear in the catalog as *run-to-enable* until the
CPA tab is run and its summary is persisted (a future hook, like the other
two-file features). This keeps every finished feature represented in the catalog.
"""

from p6_dashboard.registry import register_provider, component, payload_kpi, payload_score, payload_bars
from p6_dashboard import fmt

SOURCE = 'Critical Path Analyzer'
_NOTE = 'Open the Critical Path Analyzer tab (compare 2–3 schedules) to populate.'


@register_provider
def provide(ctx):
    settings = ctx.settings() or {}
    cp = settings.get('dashboard_critpath')   # persisted by the CPA tab (future hook)
    have = bool(cp)

    def kpi_cpli(c, cp=cp):
        if not cp:
            return payload_kpi('—', note=_NOTE, status='neutral')
        v = cp.get('cpli')
        return payload_kpi(fmt.num2(v), note='Critical Path Length Index',
                           status=('good' if (v or 0) >= 1 else 'bad'))

    def score_cpli(c, cp=cp):
        if not cp:
            return payload_score(0, band='Not run', status='neutral', detail=_NOTE)
        v = cp.get('cpli') or 0
        return payload_score(int(round(min(v, 1.5) / 1.5 * 100)),
                             band=('On track' if v >= 1 else 'Behind'),
                             status=('good' if v >= 1 else 'bad'),
                             detail=f'CPLI {fmt.num2(v)}')

    def census(c, cp=cp):
        if not cp:
            return payload_bars([])
        return payload_bars([
            {'label': 'Critical', 'value': cp.get('critical', 0), 'display': cp.get('critical', 0), 'color': '#c0504d'},
            {'label': 'Near-critical', 'value': cp.get('near', 0), 'display': cp.get('near', 0), 'color': '#e0a13a'},
        ])

    return [
        component('critpath.cpli', 'CPLI', SOURCE, 'kpi', kpi_cpli,
                  category='Time', available=have, note=(None if have else _NOTE),
                  needs='Baseline (XER/XML) to compare against', action='critpath'),
        component('critpath.cpli_gauge', 'CPLI Health', SOURCE, 'score', score_cpli,
                  category='Time', size=1, available=have, note=(None if have else _NOTE),
                  needs='Baseline (XER/XML) to compare against', action='critpath'),
        component('critpath.census', 'Critical / Near-critical', SOURCE, 'chart', census,
                  category='Time', size=1, available=have, note=(None if have else _NOTE),
                  needs='Baseline (XER/XML) to compare against', action='critpath'),
    ]
