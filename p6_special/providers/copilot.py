"""AI Copilot · TIA provider — the deterministic, offline core.

Mirrors the AI Copilot · TIA SCREEN (``ui/modules/copilot.js``), which is driven
by ``p6_evm.copilot.build_copilot(result, weather)`` — no server-side HTML
renderer exists, so these are hand-built payloads that reproduce the screen's
numbers, labels and formatting exactly:

  • the Time-Impact Analysis finish-forecast summary (baseline → likely finish,
    total impact, worst case) as a row of KPI tiles — the screen's ``cp-tia-head``;
  • the TIA driver decomposition ("What's driving the slip") as a table — the
    screen's ``cp-tia-rows`` bars, with the same signed ``+N d`` impact + colour;
  • the prioritised copilot insights as a findings register — the screen's
    ``cp-insights`` list, most-severe first.

Pure DB read path (no XML parse): the copilot server handler builds from
``db.get_project_result`` + the saved weather estimate, and the screen's
``currentResult`` additionally carries ``baseline_finish`` / ``expected_finish``
(stored in ``evm_extras``). We reconstruct that exact ``result`` here — ``ctx.evm``
plus those two finish dates from ``ctx.extras`` — and feed it to the SAME
``build_copilot`` the feature uses, so the Studio auto-tracks the copilot.
"""
from datetime import datetime

from p6_special import payloads as P
from p6_special import fmt
from p6_special.registry import Item

FEATURE = 'copilot'
FEATURE_TITLE = 'AI Copilot · TIA'

# copilot.js SEV_LABEL maps the copilot's short severities onto the report's
# findings severities ('med' is spelled 'medium' in the findings vocabulary).
_SEV = {'high': 'high', 'med': 'medium', 'low': 'low'}


# ── result reconstruction + the one build (memoized) ─────────────────────────
def _copilot(ctx):
    """Run the SAME ``build_copilot`` the copilot screen/handler runs, from the DB
    read path. Memoized so availability() and produce() share one build.

    ``result`` = the stored EVM result (``ctx.evm``) plus ``baseline_finish`` /
    ``expected_finish`` (kept in ``evm_extras``, merged into the screen's result on
    load); ``weather`` = the project's saved Calendar-Audit weather estimate
    (``ctx.weather``), reused, never recomputed — exactly like ``_handle_copilot``."""
    def build():
        e = ctx.evm
        if not e:
            return None
        r = dict(e)
        extras = ctx.extras or {}
        r['baseline_finish'] = extras.get('baseline_finish')
        r['expected_finish'] = extras.get('expected_finish')
        from p6_evm.copilot import build_copilot
        return build_copilot(r, ctx.weather)
    return ctx.memo('copilot_report', build)


def _tia(ctx):
    return (_copilot(ctx) or {}).get('tia') or {}


def _components(ctx):
    return _tia(ctx).get('components') or []


# ── screen-faithful formatters (mirror copilot.js fmtDate / dTxt / dCls) ─────
def _fmt_date(iso):
    """ISO date → the screen's en-GB '2-digit / short / numeric' read-out
    (``fmtDate`` in format.js), e.g. '01 Jan 2027'. '—' when absent, the raw
    string when unparseable — matching the screen."""
    if not iso:
        return fmt.DASH
    try:
        return datetime.strptime(str(iso)[:10], '%Y-%m-%d').strftime('%d %b %Y')
    except Exception:
        return str(iso)


def _dtxt(d):
    """Signed day figure exactly like copilot.js dTxt: '+59 d' / '-12 d' / '0 d' / '—'
    (a leading '+' only when late; the '-' is inherent to a negative value)."""
    if d is None:
        return fmt.DASH
    return f'{"+" if d > 0 else ""}{d} d'


def _dtone(d):
    """copilot.js dCls: late (>0) is bad, early (<0) is good, 0/None neutral."""
    if d is None or d == 0:
        return 'neutral'
    return 'bad' if d > 0 else 'good'


# ── producers ────────────────────────────────────────────────────────────────
def _tia_kpis(ctx):
    """The TIA finish-forecast summary as KPI tiles — the screen's ``cp-tia-head``
    (Baseline finish → Likely finish · Total impact) plus its worst-case note."""
    if not _components(ctx):
        return P.NO_DATA
    tia = _tia(ctx)
    likely_slip = tia.get('likely_slip')
    worst_finish = tia.get('worst_finish')
    worst_slip = tia.get('worst_slip')
    tiles = [
        P.kpi('Baseline finish', _fmt_date(tia.get('baseline_finish')),
              sub='the approved target', tone='neutral'),
        P.kpi('Likely finish', _fmt_date(tia.get('likely_finish')),
              sub='if the current SPI continues', tone='neutral'),
        P.kpi('Total impact', _dtxt(likely_slip),
              sub='likely finish vs baseline', tone=_dtone(likely_slip)),
    ]
    if worst_finish:
        tiles.append(P.kpi('Worst case', _fmt_date(worst_finish),
                           sub=f'{_dtxt(worst_slip)} · adds expected weather',
                           tone=_dtone(worst_slip)))
    else:
        # The screen: "Worst-case adds weather (run weather in Calendar Audit)".
        tiles.append(P.kpi('Worst case', fmt.DASH,
                           sub='run weather in Calendar Audit', tone='neutral'))
    return P.kpi_group(tiles)


def _drivers(ctx):
    """"What's driving the slip" — the TIA component decomposition, the screen's
    ``cp-tia-rows`` bars rendered as a table (Component · Impact · Basis) with the
    same signed ``+N d`` figure and late/early colour on the impact cell."""
    comps = _components(ctx)
    if not comps:
        return P.NO_DATA
    rows = []
    for c in comps:
        days = c.get('days')
        rows.append([c.get('label', ''), (_dtxt(days), _dtone(days)), c.get('basis', '')])
    return P.table(columns=['Component', 'Impact', 'Basis'], rows=rows,
                   aligns=['l', 'r', 'l'])


def _insights(ctx):
    """The prioritised copilot insights (the screen's ``cp-insights`` list) as a
    findings register — same titles, details and most-severe-first order."""
    ins = (_copilot(ctx) or {}).get('insights') or []
    if not ins:
        return P.NO_DATA
    items = [{'severity': _SEV.get(i.get('severity'), 'info'),
              'title': i.get('title', ''), 'detail': i.get('detail', '')}
             for i in ins]
    return P.findings(items, empty='No insights.')


# ── availability (exactly complements produce) ───────────────────────────────
def _tia_ready(ctx):
    """The TIA tiles/drivers render only when the copilot has a finish forecast:
    the screen shows its no-forecast message unless ``tia.components`` is non-empty
    (which requires the stored finish milestone + baseline). Gate on that exact
    condition so a 'ready' item never renders empty."""
    if not ctx.evm:
        return 'needs_run'
    return 'ready' if _components(ctx) else 'no_data'


def _insights_ready(ctx):
    """Insights are metric-driven (SPI/CPI/delay/worst category), independent of the
    finish forecast — the screen always lists at least one. Ready whenever there is
    a stored result and ``build_copilot`` returns insights."""
    if not ctx.evm:
        return 'needs_run'
    return 'ready' if (_copilot(ctx) or {}).get('insights') else 'no_data'


def provide(ctx):
    return [
        Item('copilot:tia', FEATURE, FEATURE_TITLE,
             'Time-Impact Analysis — finish forecast', 'kpi', _tia_kpis, _tia_ready),
        Item('copilot:drivers', FEATURE, FEATURE_TITLE,
             "What's driving the slip", 'table', _drivers, _tia_ready),
        Item('copilot:insights', FEATURE, FEATURE_TITLE,
             'Copilot insights — most severe first', 'findings', _insights, _insights_ready),
    ]
