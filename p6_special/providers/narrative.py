"""Baseline Narrative provider — the master (basic) narrative.

The master narrative has NO server-side HTML report renderer: the screen
(``ui/modules/narrative.js``) is client JS that POSTs to ``/api/narrative`` and
prints the deterministic text structure produced by
``p6_evm.narrative.build_narrative(result)``. That builder IS the single source
of truth (the server, the screen and the Excel export all call it), so this
provider REUSES it — it calls ``build_narrative`` on the stored DB result
(``ctx.evm``, the same read path the server uses) and maps each piece of its
output to a payload, matching narrative.js one-for-one:

  * the header chip row (project · data date · one overall status word) →
    a ``keyvals`` "Overall status" item;
  * each of the five prose sections (Executive summary, Schedule performance,
    Cost performance, Progress by area, Outlook & recommendation) → its own
    ``text`` item, whose Item title is the section's own heading. Selecting the
    lot reproduces the whole on-screen ``narr-doc`` with correct headings.

No metric is recomputed: ``build_narrative`` reads only the already-stored
result fields (SPI/CPI/delay/overall %/categories/PV·EV·AC) — exactly the
figures narrative.js says it shares with the dashboards and PDF. When the rich
'Baseline Narrative Report' branch merges, the orchestrator refreshes this to
track that renderer instead.
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special.registry import Item

FEATURE = 'narrative'
FEATURE_TITLE = 'Baseline Narrative'

# narrative.js TONE_WORD — the single overall status chip shown in the header.
_TONE_WORD = {'good': 'On track', 'warn': 'Watch', 'bad': 'Action needed', 'neutral': ''}

# The five sections build_narrative always returns, in order, by stable key.
# (Title is echoed only as a fallback — the real title comes from the builder.)
_SECTIONS = [
    ('summary', 'Executive summary'),
    ('schedule', 'Schedule performance'),
    ('cost', 'Cost performance'),
    ('areas', 'Progress by area'),
    ('outlook', 'Outlook & recommendation'),
]


def _narr(ctx):
    """The master narrative built from the stored DB result, memoized.

    Reuses the feature's OWN generator (``p6_evm.narrative.build_narrative``) on
    ``ctx.evm`` — the same DB read path ``server._handle_narrative`` uses — so
    the Studio auto-tracks the master narrative with no maths reimplemented.
    Returns ``None`` when there is no stored result to narrate."""
    def _build():
        result = ctx.evm
        if not result:
            return None
        from p6_evm.narrative import build_narrative
        return build_narrative(result)
    return ctx.memo('narrative', _build)


def _section(ctx, key):
    """The section dict for ``key`` from the built narrative, or None."""
    narr = _narr(ctx)
    if not narr:
        return None
    for sec in (narr.get('sections') or []):
        if sec.get('key') == key:
            return sec
    return None


# ── figure formatters — mirror p6_evm.narrative_excel._header_block exactly ─────
def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _whole_pct(frac):
    """Stored 0–1 fraction → whole-percent string ('0.614' → '61'); None → DASH.
    Mirrors narrative_excel._pct_whole (its numeric cell) as a display string."""
    n = _num(frac)
    return fmt.DASH if n is None else f'{round(n * 100)}'


def _delay_txt(v):
    """Delay in days as narrative_excel shows it — the bare int (can be negative /
    ahead), '—' when absent. The label carries the '(days)' unit."""
    try:
        return fmt.DASH if v is None else f'{int(v)}'
    except (TypeError, ValueError):
        return fmt.DASH


# ── availability ──────────────────────────────────────────────────────────────
def _ready(ctx):
    """'ready' only when there is a stored result to narrate (ctx.evm present) —
    the narrative is a pure DB read (no re-parse), so it does NOT need the XML on
    disk; gating on the DB slice exactly complements produce(), which returns
    NO_DATA when ctx.evm is falsy."""
    return 'ready' if ctx.evm else 'no_data'


# ── producers ─────────────────────────────────────────────────────────────────
def _status(ctx):
    """The header block: the chip row (project · data date · overall status word)
    plus the figures the feature's OWN header shows — SPI, CPI, planned/actual
    complete and delay. A keyvals mirror of narrative.js's ``ov-chips`` extended
    with the figure block of ``p6_evm.narrative_excel._header_block``, read
    straight from ``ctx.evm`` (the same fields the Excel header uses)."""
    narr = _narr(ctx)
    if not narr:
        return P.NO_DATA
    e = ctx.evm or {}
    dd = e.get('data_date')
    # narrative.js prints the data-date chip as String(data_date).slice(0,10).
    date_txt = str(dd)[:10] if dd else fmt.DASH
    word = _TONE_WORD.get(narr.get('tone'), '') or fmt.DASH
    return P.keyvals([
        ('Project', e.get('project_name') or 'Project'),
        ('Data date', date_txt),
        ('Status', word),
        # The figures the narrative is written from — the same block the Excel
        # header carries (SPI/CPI 2 dp, complete % whole, delay in days).
        ('SPI · Schedule', fmt.ratio(e.get('spi'))),
        ('CPI · Cost', fmt.ratio(e.get('cpi'))),
        ('Planned complete (%)', _whole_pct(e.get('overall_planned_pct'))),
        ('Actual complete (%)', _whole_pct(e.get('overall_actual_pct'))),
        ('Delay (days)', _delay_txt(e.get('delay_days'))),
    ])


def _make_section_producer(key):
    def _produce(ctx):
        sec = _section(ctx, key)
        if not sec:
            return P.NO_DATA
        paras = sec.get('paragraphs') or []
        if not paras:
            return P.NO_DATA
        body = P.text(paras)
        # Surface the section's own tone from build_narrative — the same per-section
        # verdict the Excel export shows (narrative_excel._section_block): when the
        # tone is non-neutral, append a small coloured 'Verdict: <word>' note using
        # this provider's _TONE_WORD map (the section tones good/warn/bad map straight
        # onto the note tones). Neutral sections stay plain text (no false verdict).
        tone = sec.get('tone')
        word = _TONE_WORD.get(tone) if (tone and tone != 'neutral') else None
        if not word:
            return body
        return P.group([body, P.note(f'Verdict: {word}', tone=tone)])
    return _produce


def provide(ctx):
    items = [
        Item('narrative:status', FEATURE, FEATURE_TITLE, 'Overall status', 'summary',
             _status, _ready),
    ]
    for key, title in _SECTIONS:
        items.append(Item(f'narrative:{key}', FEATURE, FEATURE_TITLE, title, 'text',
                          _make_section_producer(key), _ready))
    return items
