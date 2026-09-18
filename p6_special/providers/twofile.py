"""Two-/three-file features — Critical Path Analyzer, Consultant Review, Update
vs Update. Each offers its feature's OWN report sections (exact detailed results +
real charts). They need an extra schedule the single import doesn't provide, so
items declare ``requires`` (a baseline XER, or a previous update); the UI
highlights it and lets the user attach — then Special Report runs the feature
itself and pulls its real sections in.
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special import feature_reports as FR
from p6_special.registry import Item

BASELINE_REQ = [{'role': 'baseline', 'label': 'Baseline XER',
                 'accept': '.xer,.xml', 'hint': 'the approved baseline schedule'}]
PREV_REQ = [{'role': 'previous', 'label': 'Previous update',
             'accept': '.xml,.xer', 'hint': 'the earlier update to compare against'}]


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


def provide(ctx):
    items = []
    # Critical Path Analyzer — every section of its own report (needs a baseline)
    for k, t in FR.CRITPATH_SECS:
        items.append(Item(f'critpath:{k}', 'critpath', 'Critical Path Analyzer', t, 'section',
                          (lambda ctx, k=k: FR.critpath_section(ctx, k) or P.NO_DATA),
                          _need('baseline'), BASELINE_REQ))
    # Consultant Review — quick delay figure + the full report (needs a baseline)
    items.append(Item('compare:impact', 'compare', 'Consultant Review', 'Delay before / after (but-for)',
                      'kpi', _cmp_impact, _need('baseline'), BASELINE_REQ))
    items.append(Item('compare:report', 'compare', 'Consultant Review', 'Full Consultant Review report',
                      'section', (lambda ctx: FR.compare_full_report(ctx) or P.NO_DATA),
                      _need('baseline'), BASELINE_REQ))
    # Update vs Update — every section of its own report (needs the previous update)
    for k, t in FR.PERIOD_SECS:
        items.append(Item(f'period:{k}', 'period', 'Update vs Update', t, 'section',
                          (lambda ctx, k=k: FR.period_section(ctx, k) or P.NO_DATA),
                          _need('previous'), PREV_REQ))
    return items
