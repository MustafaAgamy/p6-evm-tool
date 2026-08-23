"""Constructability Review provider — the 45/45/10 readiness score plus the two
headline gap counts (illogical links, missing activities).

Unlike the EVM/audit providers, this feature is **not persisted** — there is no
stored blob to read, so the numbers are recomputed from the parsed schedule via
``p6_kb.review.run_review``. That is expensive (parse + KB match), so ``provide``
stays cheap: it only declares descriptors (``available = ctx.has_xml()``) and never
parses. The heavy run happens the first time a component's ``produce`` is rendered,
behind a shared ``ctx.memo`` so it runs exactly once even when all three components
are on the board together.
"""

from p6_dashboard.registry import (
    register_provider, component,
    payload_kpi, payload_score,
)
from p6_dashboard import fmt

SOURCE = 'Constructability Review'

# The fixed rubric weights (Ibrahim's rule) — shown under the score tile.
_SCORE_DETAIL = 'Logic 45 · Completeness 45 · Structure 10'


# ── Shared recompute (runs once per dashboard request via ctx.memo) ─────────

def _review(ctx):
    """The Constructability Review result for this project, or None if the schedule
    XML is unavailable. Memoised so the parse + review runs once, shared by every
    component's produce()."""
    return ctx.memo('constructability', lambda c=ctx: _run(c))


def _run(ctx):
    data = ctx.parsed()
    if data is None:
        return None
    from p6_kb.review import run_review
    return run_review(data)


# ── produce() closures — cheap read of the memoised result ──────────────────

def _produce_score(ctx):
    r = _review(ctx)
    if r is None:
        return payload_kpi('—', note='Schedule unavailable')
    score = r.get('score') or {}
    overall = score.get('overall')
    if overall is None:
        return payload_score('—', band=(r.get('project_type') or 'Unrecognised'),
                             status='neutral', detail=_SCORE_DETAIL)
    return payload_score(
        overall,
        band=score.get('band_label') or '',
        status=fmt.band_status(overall),
        detail=_SCORE_DETAIL)


def _produce_illogical(ctx):
    r = _review(ctx)
    if r is None:
        return payload_kpi('—', note='Schedule unavailable')
    dash = r.get('dashboard') or {}
    count = dash.get('illogical_count')
    pct = dash.get('illogical_pct')
    pct = pct if pct is not None else 0
    return payload_kpi(
        count if count is not None else '—',
        note=f'{pct}% of relationships',
        status='neutral')


def _produce_missing(ctx):
    r = _review(ctx)
    if r is None:
        return payload_kpi('—', note='Schedule unavailable')
    dash = r.get('dashboard') or {}
    count = dash.get('missing_count')
    shown = count if count is not None else 0
    return payload_kpi(
        count if count is not None else '—',
        note=f'{shown} missing activities suggested',
        status='neutral')


# ── Provider — cheap: declares descriptors only, never parses ───────────────

@register_provider
def provide(ctx):
    avail = ctx.has_xml()
    note = None if avail else 'Open Constructability Review once for this project.'

    return [
        component(
            'construct.score', 'Constructability Score', SOURCE, 'score',
            _produce_score,
            category='Quality', size=1, available=avail, note=note),
        component(
            'construct.illogical', 'Illogical Links', SOURCE, 'kpi',
            _produce_illogical,
            category='Quality', available=avail, note=note),
        component(
            'construct.missing', 'Missing Activities', SOURCE, 'kpi',
            _produce_missing,
            category='Quality', available=avail, note=note),
    ]
