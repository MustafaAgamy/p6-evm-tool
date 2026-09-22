"""Two-/three-file features — Critical Path Analyzer, Consultant Review, Update
vs Update. Each offers its feature's OWN report sections (exact detailed results +
real charts). They need an extra schedule the single import doesn't provide, so
items declare ``requires`` (a baseline XER, or a previous update); the UI
highlights it and lets the user attach — then Special Report runs the feature
itself and pulls its real sections in.
"""
import re

from p6_special import payloads as P
from p6_special import fmt
from p6_special import feature_reports as FR
from p6_special import reuse
from p6_special.registry import Item

BASELINE_REQ = [{'role': 'baseline', 'label': 'Baseline XER',
                 'accept': '.xer,.xml', 'hint': 'the approved baseline schedule'}]
PREV_REQ = [{'role': 'previous', 'label': 'Previous update',
             'accept': '.xml,.xer', 'hint': 'the earlier update to compare against'}]
# The impact / consultant-recommendation section additionally needs the rescheduled
# corrected but-for XML (F9'd in P6, re-exported) — the 3rd file the two-file compare
# cannot produce. Baseline first, then the corrected file.
CORRECTED_REQ = BASELINE_REQ + [{'role': 'corrected', 'label': 'Rescheduled corrected (but-for) XML',
                                 'accept': '.xml',
                                 'hint': 'the corrected file after F9 in P6, re-exported as XML'}]


def _need(role):
    return lambda ctx: 'ready' if (ctx.has_xml() and ctx.has_input(role)) else 'needs_input'


# ── Consultant Review quick figure (delay before/after) ──────────────────────
def _cmp_report(ctx):
    def build():
        cur, base = ctx.parsed(), ctx.parsed_input('baseline')
        if cur is None or base is None:
            return None
        from p6_compare.report import build_report_from_data
        return build_report_from_data(base, cur, ctx.config)
    return ctx.memo('cmp_report', build)


def _cmp_impact(ctx):
    if not ctx.has_input('baseline'):
        return P.NO_DATA
    try:
        r = _cmp_report(ctx)
    except Exception:
        return P.NO_DATA
    d = (r or {}).get('dashboard') or {}
    if not d:
        return P.NO_DATA
    # These are signed WORKING-day figures. Match the Consultant Review screen exactly:
    # (1) call them 'working days' (not calendar 'days'); (2) colour by DIRECTION —
    # reported delay is red when behind (>0), green when ahead (<0); but-for is neutral
    # ink (never amber); manufactured is red only when >0; (3) show a leading +/−.
    rep = d.get('delay_working_days')
    bf = d.get('butfor_delay_working_days')
    mfd = d.get('manufactured_working_days')
    changed = d.get('changed_activities')
    logic = d.get('logic_changed')
    dur = d.get('duration_only')

    def _dir_tone(v):
        if v is None or v == 0:
            return 'neutral'
        return 'bad' if v > 0 else 'good'

    changed_sub = None
    if logic is not None or dur is not None:
        changed_sub = f'{int(logic or 0)} logic / lag · {int(dur or 0)} duration'
    return P.kpi_group([
        P.kpi('Reported delay', fmt.working_days(rep, signed=True), tone=_dir_tone(rep)),
        P.kpi('But-for delay', fmt.working_days(bf, signed=True), tone='neutral'),
        P.kpi('Manufactured', fmt.working_days(mfd, signed=True),
              tone='bad' if (mfd or 0) > 0 else 'neutral'),
        # Raw integer count (no comma grouping) + the logic/duration breakdown sub-line,
        # exactly like the feature's _changedKpi.
        P.kpi('Changed activities',
              str(int(changed)) if changed is not None else fmt.DASH, sub=changed_sub),
    ])


# ── Consultant Review — section-by-section (parity with the feature's own PDF) ──
# p6_compare/exporters.render_html slices its report with a `sections=` INCLUDE-filter
# (COMPARE_SECTIONS = dashboard/charts/logic/duration/impact), NOT <section data-sec>
# wrappers — so section reuse is the feature's own `sections=[key]` filter one section at a
# time (the evm/calendar/weather pattern), not a data-sec regex slice. Each item mirrors
# exactly what the Consultant Review screen/PDF shows for that section. Self-contained here
# (imports p6_compare directly); the whole-report item (compare:report) and the impact KPI
# (compare:impact) are unchanged.

# (key, title) — mirrors ui/modules/compare.js COMPARE_SECTIONS (same keys, same order,
# same labels the feature's own Report-Contents picker shows). These four are the two-file
# view (baseline vs update) — available from the baseline alone.
COMPARE_SECS = [('dashboard', 'Executive dashboard — KPIs'),
                ('charts', 'Executive dashboard — charts'),
                ('logic', 'Driving logic & lag changes vs baseline'),
                ('duration', 'Duration & remaining changes vs baseline')]
# The impact / consultant-recommendation section is the only one that needs the 3rd file
# (the rescheduled corrected but-for XML); kept separate so it can be gated on 'corrected'.
COMPARE_IMPACT_SEC = ('impact', 'Impact & consultant recommendation (but-for)')

_CMP_SCOPE = '.srf-compare'


def _cmp_strip_banner(full_html):
    """Everything after </head>, minus the body/html wrappers and the compare report's
    leading <h1> + <div class="sub"> banner (the report header repeats project/date, which
    the composed Special Report already prints above every section)."""
    m = re.search(r'</head>(.*)', full_html or '', re.S | re.I)
    frag = m.group(1) if m else (full_html or '')
    frag = re.sub(r'</?(body|html)[^>]*>', '', frag, flags=re.I)
    frag = re.sub(r'^\s*<h1\b[^>]*>.*?</h1>', '', frag, count=1, flags=re.S | re.I)
    frag = re.sub(r'^\s*<div class="sub">.*?</div>', '', frag, count=1, flags=re.S | re.I)
    return frag.strip()


def _cmp_strip_leading_h2(frag):
    """Drop the section's own leading <h2> — the Studio wraps each section in its own
    numbered badge (the item title), so keeping it would stack two headings (identical to
    the update/critpath/period section reuse)."""
    return re.sub(r'^\s*<h2\b[^>]*>.*?</h2>', '', frag or '', count=1, flags=re.S | re.I).strip()


def _cmp_payload(full_html):
    """Wrap one compare section's markup as an `html` payload with the feature CSS scoped to
    .srf-compare — the SAME shape as the whole-report item (compare:report), so a picked
    section composes identically and looks exactly like the feature's own report."""
    if not full_html:
        return None
    frag = _cmp_strip_leading_h2(_cmp_strip_banner(full_html))
    if not frag:
        return None
    return {'kind': 'html', 'feature': 'compare',
            'css': reuse.scope_css(reuse.extract_styles(full_html), _CMP_SCOPE),
            'html': f'<div class="srf-compare">{frag}</div>'}


def _cmp_impact_data(ctx):
    """The before/after but-for impact dict — needs the rescheduled corrected 3rd file.
    Computed exactly as the feature's own /api/compare/before-after route (before_after_from_paths),
    so the picked section matches what the feature produces after the corrected file is loaded."""
    def build():
        base, upd, corr = ctx.input_path('baseline'), ctx.xml_path, ctx.input_path('corrected')
        if not (base and upd and corr):
            return None
        from p6_compare.impact import before_after_from_paths
        return before_after_from_paths(base, upd, corr, ctx.config)
    return ctx.memo('cmp_impact_data', build)


def _cmp_section(ctx, key):
    """One two-file section (dashboard/charts/logic/duration), rendered via the feature's own
    `sections=[key]` filter with impact=None — the two-file view the Consultant Review screen
    shows. Available from the baseline alone."""
    if not (ctx.has_xml() and ctx.has_input('baseline')):
        return None
    try:
        report = _cmp_report(ctx)
    except Exception:
        return None
    if report is None:
        return None

    def b():
        from p6_compare.exporters import render_html
        return render_html(report, sections=[key], theme=ctx.mode)
    return _cmp_payload(ctx.memo(f'cmp_sec:{key}:{ctx.mode}', b))


def _cmp_impact_section(ctx):
    """The impact / consultant-recommendation section — the one part that needs the corrected
    3rd file. Renders the feature's `sections=['impact']` block with the real before/after
    impact dict; None (→ no_data) until baseline + corrected are both attached."""
    if not (ctx.has_xml() and ctx.has_input('baseline') and ctx.has_input('corrected')):
        return None
    try:
        report = _cmp_report(ctx)
        impact = _cmp_impact_data(ctx)
    except Exception:
        return None
    if report is None or impact is None:
        return None

    def b():
        from p6_compare.exporters import render_html
        return render_html(report, impact=impact, sections=['impact'], theme=ctx.mode)
    return _cmp_payload(ctx.memo(f'cmp_sec:impact:{ctx.mode}', b))


def _need_corrected(ctx):
    return ('ready' if (ctx.has_xml() and ctx.has_input('baseline') and ctx.has_input('corrected'))
            else 'needs_input')


def provide(ctx):
    items = []
    # Critical Path Analyzer — every section of its own report (needs a baseline)
    for k, t in FR.CRITPATH_SECS:
        items.append(Item(f'critpath:{k}', 'critpath', 'Critical Path Analyzer', t, 'section',
                          (lambda ctx, k=k: FR.critpath_section(ctx, k) or P.NO_DATA),
                          _need('baseline'), BASELINE_REQ))
    # Consultant Review — quick delay figure, then every section of its own report, then the
    # full report (all need a baseline; the impact section additionally needs the corrected file)
    items.append(Item('compare:impact', 'compare', 'Consultant Review', 'Delay before / after (but-for)',
                      'kpi', _cmp_impact, _need('baseline'), BASELINE_REQ))
    for k, t in COMPARE_SECS:
        items.append(Item(f'compare:{k}', 'compare', 'Consultant Review', t, 'section',
                          (lambda ctx, k=k: _cmp_section(ctx, k) or P.NO_DATA),
                          _need('baseline'), BASELINE_REQ))
    # Impact / consultant recommendation — the one section needing the 3rd (corrected) file.
    # Gated needs_input until 'corrected' is attached; id kept distinct from the compare:impact KPI.
    items.append(Item('compare:impact_section', 'compare', 'Consultant Review',
                      COMPARE_IMPACT_SEC[1], 'section',
                      (lambda ctx: _cmp_impact_section(ctx) or P.NO_DATA),
                      _need_corrected, CORRECTED_REQ))
    items.append(Item('compare:report', 'compare', 'Consultant Review', 'Full Consultant Review report',
                      'section', (lambda ctx: FR.compare_full_report(ctx) or P.NO_DATA),
                      _need('baseline'), BASELINE_REQ))
    # Update vs Update — every section of its own report (needs the previous update)
    for k, t in FR.PERIOD_SECS:
        items.append(Item(f'period:{k}', 'period', 'Update vs Update', t, 'section',
                          (lambda ctx, k=k: FR.period_section(ctx, k) or P.NO_DATA),
                          _need('previous'), PREV_REQ))
    return items
