"""Productivity & Resource Intelligence provider for Special Report / Reporting Studio.

``p6_prodintel`` is a *knowledge* feature, not a project-file feature: its screen
(``ui/modules/prodintel.js``) is an interactive query tool over a bundled productivity-
norm KB, and it has **no server-side HTML report** (only a per-item Excel export). Its
one project-file-independent, genuinely composable output is therefore the KB itself —
the coverage summary, the productivity-norm library and the honest evidence/provenance
mix. This provider exposes exactly those, matched to the SCREEN.

Parity + never-invent:
- Every number flows through the feature's OWN engine entry point
  (``p6_prodintel.item_result`` / ``build_tree``), so rates, component states and
  confidence read exactly as the screen renders them — nothing is re-derived here.
- The per-item DRIVER outputs (man-hours / crew / duration) need an interactive item +
  quantity the user picks on the screen; that selection does not exist in a Studio
  render context, so this provider does NOT fabricate one — it exposes only the
  quantity-independent norm reference (rate, range, output/day, crew) the screen shows
  before a quantity is entered.
- The on-screen rail's "Knowledge coverage" mini-bar (64/31/5 %) is a hard-coded
  decorative bar in the JS — deliberately NOT reproduced. The evidence mix here is the
  REAL component-state tally from the engine (honest provenance).

Self-contained: imports ``p6_prodintel`` directly for its reuse helpers; registers
nothing in shared files (the orchestrator wires load_builtins afterward).
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special.registry import Item

FEATURE = 'prodintel'
FEATURE_TITLE = 'Productivity & Resource Intelligence'


# ── KB access, all memoized on the render context ─────────────────────────────
def _items(ctx):
    """The merged productivity-norm KB items (bundled + user overlay)."""
    def _load():
        try:
            from p6_prodintel import load_items
            return load_items() or []
        except Exception:
            return []
    return ctx.memo('prodintel_items', _load)


def _tree(ctx):
    """Discipline ▸ System ▸ Item tree (sorted) — the screen's cascade / browse order."""
    def _build():
        try:
            from p6_prodintel import build_tree
            return build_tree(_items(ctx)) or []
        except Exception:
            return []
    return ctx.memo('prodintel_tree', _build)


def _results(ctx):
    """Every KB item run through the engine with NO quantity — i.e. the pure knowledge
    lookup the screen shows before a quantity is entered. Each carries engine-computed
    component ``state`` / ``confidence`` / ``rate`` (exact parity with the screen)."""
    def _run():
        try:
            from p6_prodintel import item_result
        except Exception:
            return []
        out = []
        for it in _items(ctx):
            try:
                out.append(item_result(it))
            except Exception:
                continue
        return out
    return ctx.memo('prodintel_results', _run)


def _result_by_id(ctx):
    return ctx.memo('prodintel_by_id', lambda: {r.get('item_id'): r for r in _results(ctx)})


def _flat_in_tree_order(ctx):
    """Item results in the screen's browse-library order (sorted disc → system → item)."""
    by_id = _result_by_id(ctx)
    out = []
    for d in _tree(ctx):
        for s in d.get('systems', []):
            for node in s.get('items', []):
                r = by_id.get(node.get('item_id'))
                if r is not None:
                    out.append(r)
    return out


# ── availability: ready ONLY when the KB actually loaded ──────────────────────
def _kb_ready(ctx):
    # Project-independent: prodintel is a bundled knowledge base, so it is 'ready'
    # whenever the KB is present (a broken/empty deployment → honest 'no_data', never a
    # 'ready' item that renders empty). It does NOT gate on ctx.has_xml() — the norms
    # are reference material, addable to any report.
    return 'ready' if _items(ctx) else 'no_data'


# ── screen-faithful formatters (mirror prodintel.js exactly) ──────────────────
def _rate_phrase(comp):
    """A component's productivity rate exactly as ``ratePhrase().big`` renders it:
    output/day + crew, else MH/unit. Splitting output_unit on '/' also drops the
    stray separator glyph some KB files carry (e.g. 'm2/crew·day')."""
    rate = comp.get('rate')
    if not rate:
        return 'no reference'
    unit = comp.get('unit') or ''
    out_unit = (rate.get('output_unit') or unit) or ''
    unit_noun = out_unit.split('/')[0].strip() or unit
    crew = ' + '.join('%s %s' % (g.get('count'), g.get('trade'))
                      for g in (comp.get('gang') or [])) or 'crew'
    if rate.get('output_per_day'):
        return '%s %s / %s / day' % (rate.get('output_per_day'), unit_noun, crew)
    return '%s MH/%s' % (rate.get('mh_per_unit'), unit)


def _rate_range(comp):
    """The screen's 'range low–high MH/unit' line (only when a real spread exists)."""
    rate = comp.get('rate') or {}
    lo, hi = rate.get('low'), rate.get('high')
    unit = comp.get('unit') or ''
    if lo is not None and hi is not None and hi > lo:
        return '%s–%s MH/%s' % (lo, hi, unit)
    return fmt.DASH


# Component evidence word — mirrors stateChip(state, confidence) in prodintel.js.
_CONF_WORD = {'high': 'High', 'moderate': 'Moderate', 'draft': 'Draft',
              'low': 'Moderate', 'none': 'Insufficient'}


def _evidence_word(comp):
    st = comp.get('state')
    if st == 'no_reference':
        return 'No reference'
    if st == 'validated':
        return 'Validated'
    return _CONF_WORD.get(comp.get('confidence'), 'Draft')


def _evidence_tone(state):
    return {'validated': 'good', 'no_reference': 'neutral'}.get(state, 'warn')


# Item-level overall-confidence word (engine _worst_confidence output).
_OVERALL_WORD = {'high': 'High', 'moderate': 'Moderate', 'draft': 'Draft', 'none': 'No reference'}
_OVERALL_TONE = {'high': 'good', 'moderate': 'warn', 'draft': 'warn', 'none': 'neutral'}


# ── producers ─────────────────────────────────────────────────────────────────
def _coverage(ctx):
    """KB coverage KPIs — mirrors the toolbar 'Browse library (N)' count and the
    Discipline ▸ System ▸ Item cascade breadth."""
    tree = _tree(ctx)
    items = _items(ctx)
    if not items:
        return P.NO_DATA
    n_disc = len(tree)
    n_sys = sum(len(d.get('systems', [])) for d in tree)
    n_items = len(items)
    n_comps = sum(len(r.get('components', [])) for r in _results(ctx))
    return P.kpi_group([
        P.kpi('Disciplines', fmt.num(n_disc), sub='knowledge areas', tone='accent'),
        P.kpi('Systems', fmt.num(n_sys), sub='within the disciplines'),
        P.kpi('Work items', fmt.num(n_items), sub='norm-carrying activities'),
        P.kpi('Component norms', fmt.num(n_comps), sub='crew rates behind the items'),
    ])


def _discipline_table(ctx):
    """Per-discipline coverage — mirrors the Browse-library modal's discipline headers
    (name + item count) plus the system / component depth beneath each."""
    tree = _tree(ctx)
    by_id = _result_by_id(ctx)
    if not tree:
        return P.NO_DATA
    rows = []
    tot_sys = tot_items = tot_comps = 0
    for d in tree:
        systems = d.get('systems', [])
        n_sys = len(systems)
        n_items = d.get('count', 0)
        n_comps = 0
        for s in systems:
            for node in s.get('items', []):
                r = by_id.get(node.get('item_id'))
                if r:
                    n_comps += len(r.get('components', []))
        tot_sys += n_sys
        tot_items += n_items
        tot_comps += n_comps
        rows.append([d.get('name'), fmt.num(n_sys), fmt.num(n_items), fmt.num(n_comps)])
    rows.append(['All disciplines', fmt.num(tot_sys), fmt.num(tot_items), fmt.num(tot_comps)])
    return P.table(
        columns=['Discipline', 'Systems', 'Work items', 'Component norms'],
        rows=rows, aligns=['l', 'r', 'r', 'r'])


def _norm_library(ctx):
    """The productivity-norm LIBRARY (item level) — one row per work item, in the
    screen's browse order. Mirrors the cascade / browse list: Discipline ▸ System ▸
    Item, with its primary unit, component count and honest overall confidence."""
    flat = _flat_in_tree_order(ctx)
    if not flat:
        return P.NO_DATA
    rows = []
    for r in flat:
        oc = r.get('overall_confidence') or 'none'
        rows.append([
            r.get('discipline') or '', r.get('system') or '',
            r.get('item') or r.get('item_id') or '',
            r.get('primary_unit') or fmt.DASH,
            fmt.num(len(r.get('components', []))),
            (_OVERALL_WORD.get(oc, 'Draft'), _OVERALL_TONE.get(oc, 'warn')),
        ])
    return P.table(
        columns=['Discipline', 'System', 'Work item', 'Primary unit', 'Components', 'Evidence'],
        rows=rows, aligns=['l', 'l', 'l', 'c', 'r', 'l'])


def _component_norms(ctx):
    """The productivity NORM table (component level) — every crew rate in the KB, exactly
    as the screen's 'Productivity rate → man-hours — by component' cards show it BEFORE a
    quantity is entered (rate, range, evidence). No man-hours/duration: those need a
    quantity the screen collects interactively and Studio has none, so they are honestly
    omitted rather than invented."""
    flat = _flat_in_tree_order(ctx)
    if not flat:
        return P.NO_DATA
    rows = []
    for r in flat:
        item = r.get('item') or r.get('item_id') or ''
        for c in r.get('components', []):
            rows.append([
                item, c.get('name') or '', c.get('unit') or fmt.DASH,
                _rate_phrase(c), _rate_range(c),
                (_evidence_word(c), _evidence_tone(c.get('state'))),
            ])
    if not rows:
        return P.NO_DATA
    return P.table(
        columns=['Work item', 'Component', 'Unit', 'Productivity rate', 'Range', 'Evidence'],
        rows=rows, aligns=['l', 'l', 'c', 'l', 'l', 'l'])


def _evidence_mix(ctx):
    """Honest provenance mix across every component norm, tallied by the SAME evidence
    word the norms-by-component table and the screen's chips show (High / Moderate /
    Draft / Validated / Insufficient / No reference), so the chart and the table below
    it never disagree. This is the REAL engine tally, not the rail's decorative bar."""
    from collections import OrderedDict
    results = _results(ctx)
    if not results:
        return P.NO_DATA
    _order = ['Validated', 'High', 'Moderate', 'Draft', 'Insufficient', 'No reference']
    _tone = {'Validated': 'good', 'High': 'good', 'Moderate': 'warn', 'Draft': 'warn',
             'Insufficient': 'neutral', 'No reference': 'neutral'}
    counts = OrderedDict((w, 0) for w in _order)
    for r in results:
        for c in r.get('components', []):
            w = _evidence_word(c)
            counts[w] = counts.get(w, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return P.NO_DATA
    segs = [{'label': w, 'value': counts[w], 'tone': _tone.get(w, 'neutral')}
            for w in counts if counts[w] > 0]
    parts = ' · '.join('%d %s' % (counts[w], w) for w in counts if counts[w] > 0)
    note = ('%d component norms · %s — the evidence word matches the norms-by-component '
            'table and the screen chips; built-in norms carry no project records until '
            'validated evidence is imported; nothing is fabricated.' % (total, parts))
    return P.segbar(segs, note=note)


def provide(ctx):
    A = _kb_ready
    return [
        Item('prodintel:coverage', FEATURE, FEATURE_TITLE,
             'Knowledge base coverage', 'kpi', _coverage, A),
        Item('prodintel:discipline_table', FEATURE, FEATURE_TITLE,
             'Coverage by discipline', 'table', _discipline_table, A),
        Item('prodintel:evidence_mix', FEATURE, FEATURE_TITLE,
             'Evidence & provenance mix', 'chart', _evidence_mix, A),
        Item('prodintel:norm_library', FEATURE, FEATURE_TITLE,
             'Productivity-norm library (work items)', 'table', _norm_library, A),
        Item('prodintel:component_norms', FEATURE, FEATURE_TITLE,
             'Productivity norms by component (rates)', 'table', _component_norms, A),
    ]
