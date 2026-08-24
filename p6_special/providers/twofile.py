"""Two-/three-file features — Critical Path Analyzer, Consultant Review, Update
vs Update. These need an extra schedule the single import doesn't provide, so
each item declares ``requires`` (a baseline XER, or a previous update). The UI
highlights the requirement and lets the user attach the file; the attached path
arrives on ``ctx.inputs[role]`` and Special Report **runs the feature itself** —
the user never opens the feature's own tab.
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special.registry import Item
from p6_special.providers import _util as U

BASELINE_REQ = [{'role': 'baseline', 'label': 'Baseline XER',
                 'accept': '.xer,.xml', 'hint': 'the approved baseline schedule'}]
PREV_REQ = [{'role': 'previous', 'label': 'Previous update',
             'accept': '.xml,.xer', 'hint': 'the earlier update to compare against'}]


def _need(role):
    def avail(ctx):
        return 'ready' if (ctx.has_xml() and ctx.has_input(role)) else 'needs_input'
    return avail


def _metrics_for(ctx, data):
    from p6_evm.metrics import compute
    from p6_evm.classify import auto_categories, build_wbs_classifier
    cfg = dict(ctx.config)
    cfg['categories'] = auto_categories(data)
    return compute(data, cfg, overrides={}, classifier=build_wbs_classifier(data))


# ── Critical Path Analyzer (current + baseline) ──────────────────────────────
def _cp_report(ctx):
    def build():
        cur, base = ctx.parsed(), ctx.parsed_input('baseline')
        if cur is None or base is None:
            return None
        from p6_critpath.analysis import build_report
        return build_report({'current': cur, 'baseline': base}, mode='update_baseline')
    return ctx.memo('cp_report', build)


def _cp_health(ctx):
    if not ctx.has_input('baseline'):
        return P.NO_DATA
    try:
        r = _cp_report(ctx)
    except Exception:
        return P.NO_DATA
    if not r:
        return P.NO_DATA
    blocks = [U.kpi_from_dict(r.get('dashboard') or {})]
    if r.get('conclusion'):
        blocks.append(P.text(r['conclusion']))
    return P.group([b for b in blocks if b and b.get('kind') != 'no_data']) or P.NO_DATA


def _cp_census(ctx):
    if not ctx.has_input('baseline'):
        return P.NO_DATA
    try:
        r = _cp_report(ctx)
    except Exception:
        return P.NO_DATA
    census = (r or {}).get('census') or {}
    rows = []
    for role, c in census.items():
        if isinstance(c, dict):
            rows.append({'schedule': role,
                         **{k: v for k, v in c.items() if isinstance(v, (int, float, str))}})
    return U.table_from_dicts(rows) if rows else P.NO_DATA


def _cp_milestones(ctx):
    if not ctx.has_input('baseline'):
        return P.NO_DATA
    try:
        r = _cp_report(ctx)
    except Exception:
        return P.NO_DATA
    ms = (r or {}).get('milestones')
    if isinstance(ms, list) and ms and isinstance(ms[0], dict):
        return U.table_from_dicts(ms)
    return P.NO_DATA


# ── Consultant Review (baseline vs update) ───────────────────────────────────
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
    return P.kpi_group([
        P.kpi('Reported delay', fmt.days(d.get('delay_working_days')), tone='bad'),
        P.kpi('But-for delay', fmt.days(d.get('butfor_delay_working_days')), tone='warn'),
        P.kpi('Manufactured', fmt.days(d.get('manufactured_working_days')), tone='bad'),
        P.kpi('Changed activities', fmt.num(d.get('changed_activities'))),
    ])


def _cmp_changes(ctx):
    if not ctx.has_input('baseline'):
        return P.NO_DATA
    try:
        r = _cmp_report(ctx)
    except Exception:
        return P.NO_DATA
    items = ((r or {}).get('change_summary') or {}).get('items')
    if isinstance(items, list) and items:
        return U.table_from_dicts([{k: v for k, v in it.items() if k in ('label', 'count', 'group')}
                                   for it in items])
    return P.NO_DATA


def _cmp_milestones(ctx):
    if not ctx.has_input('baseline'):
        return P.NO_DATA
    try:
        r = _cmp_report(ctx)
    except Exception:
        return P.NO_DATA
    ms = (r or {}).get('milestones')
    if isinstance(ms, list) and ms and isinstance(ms[0], dict):
        return U.table_from_dicts(ms)
    return P.NO_DATA


# ── Update vs Update (previous vs current) ───────────────────────────────────
def _pd_report(ctx):
    def build():
        cur, prev = ctx.parsed(), ctx.parsed_input('previous')
        if cur is None or prev is None:
            return None
        from p6_period.report import build_report_from_data
        return build_report_from_data(prev, cur, _metrics_for(ctx, prev), ctx.computed(), ctx.config)
    return ctx.memo('pd_report', build)


def _pd_progress(ctx):
    if not ctx.has_input('previous'):
        return P.NO_DATA
    try:
        r = _pd_report(ctx)
    except Exception:
        return P.NO_DATA
    s = (r or {}).get('summary') or {}
    blocks = [U.kpi_from_dict(s)]
    if r.get('conclusion'):
        blocks.append(P.text(r['conclusion']))
    return P.group([b for b in blocks if b and b.get('kind') != 'no_data']) or P.NO_DATA


def _pd_critical(ctx):
    if not ctx.has_input('previous'):
        return P.NO_DATA
    try:
        r = _pd_report(ctx)
    except Exception:
        return P.NO_DATA
    cm = (r or {}).get('critical_movement')
    if isinstance(cm, list) and cm and isinstance(cm[0], dict):
        return U.table_from_dicts(cm)
    if isinstance(cm, dict):
        return U.kpi_from_dict(cm)
    return P.NO_DATA


def _pd_milestones(ctx):
    if not ctx.has_input('previous'):
        return P.NO_DATA
    try:
        r = _pd_report(ctx)
    except Exception:
        return P.NO_DATA
    ms = (r or {}).get('milestones')
    if isinstance(ms, list) and ms and isinstance(ms[0], dict):
        return U.table_from_dicts(ms)
    return P.NO_DATA


def provide(ctx):
    return [
        # Critical Path Analyzer
        Item('critpath:health', 'critpath', 'Critical Path Analyzer', 'Critical path health + CPLI',
             'score', _cp_health, _need('baseline'), BASELINE_REQ),
        Item('critpath:census', 'critpath', 'Critical Path Analyzer', 'Critical & near-critical counts',
             'kpi', _cp_census, _need('baseline'), BASELINE_REQ),
        Item('critpath:milestones', 'critpath', 'Critical Path Analyzer', 'Milestone slip table',
             'table', _cp_milestones, _need('baseline'), BASELINE_REQ),
        # Consultant Review
        Item('compare:impact', 'compare', 'Consultant Review', 'Delay before / after (but-for)',
             'kpi', _cmp_impact, _need('baseline'), BASELINE_REQ),
        Item('compare:changes', 'compare', 'Consultant Review', 'Logic & lag change summary',
             'table', _cmp_changes, _need('baseline'), BASELINE_REQ),
        Item('compare:milestones', 'compare', 'Consultant Review', 'Milestone finishes (baseline vs update)',
             'table', _cmp_milestones, _need('baseline'), BASELINE_REQ),
        # Update vs Update
        Item('period:progress', 'period', 'Update vs Update', 'Period progress',
             'kpi', _pd_progress, _need('previous'), PREV_REQ),
        Item('period:critical', 'period', 'Update vs Update', 'Critical-path movement this period',
             'table', _pd_critical, _need('previous'), PREV_REQ),
        Item('period:milestones', 'period', 'Update vs Update', 'Milestone finishes this period',
             'table', _pd_milestones, _need('previous'), PREV_REQ),
    ]
