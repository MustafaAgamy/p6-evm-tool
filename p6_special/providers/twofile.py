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


def _cp(ctx):
    """Guarded CPA report (baseline attached) or None."""
    if not ctx.has_input('baseline'):
        return None
    try:
        return _cp_report(ctx)
    except Exception:
        return None


def _cp_health(ctx):
    r = _cp(ctx)
    if not r:
        return P.NO_DATA
    d = r.get('dashboard') or {}
    blocks = []
    cpli = d.get('cpli')
    if cpli is not None or d.get('status_label'):
        blocks.append(P.kpi_group([P.kpi('Critical Path Health', d.get('status_label') or '—',
                                         sub=(f'CPLI {fmt.ratio(cpli)}' if cpli is not None else None),
                                         tone=('good' if (cpli or 0) >= 1 else 'bad'))]))
    if d.get('verdict'):
        blocks.append(P.text(d['verdict']))
    return P.group([b for b in blocks if b]) if blocks else P.NO_DATA


def _cp_kpis(ctx):
    r = _cp(ctx)
    d = (r or {}).get('dashboard') or {}
    kpis = d.get('kpis') or []
    if not kpis:
        return P.NO_DATA
    items = []
    for k in kpis:
        v = k.get('value')
        val = fmt.ratio(v) if k.get('key') == 'cpli' else fmt.num(v)
        dlt = k.get('delta')
        sub = None
        if dlt not in (None, 0):
            sub = f'{dlt:+g} vs baseline'
        items.append(P.kpi(k.get('label'), val, sub=sub))
    return P.kpi_group(items)


def _cp_crit_near(ctx):
    r = _cp(ctx)
    ch = ((r or {}).get('dashboard') or {}).get('charts') or {}
    cn = ch.get('crit_near') or {}
    roles = cn.get('roles') or []
    if not roles:
        return P.NO_DATA
    crit, near = cn.get('critical') or [], cn.get('near') or []
    vals = [x for x in (crit + near) if isinstance(x, (int, float))]
    amax = max(vals) if vals else None
    rows = [{'label': roles[i].title(),
             'values': [crit[i] if i < len(crit) else 0, near[i] if i < len(near) else 0],
             'display': [fmt.num(crit[i] if i < len(crit) else 0),
                         fmt.num(near[i] if i < len(near) else 0)]}
            for i in range(len(roles))]
    return P.bars(rows, series=[{'label': 'Critical', 'tone': 'bad'},
                                {'label': 'Near-critical', 'tone': 'warn'}], axis_max=amax)


def _cp_cpli_trend(ctx):
    r = _cp(ctx)
    ch = ((r or {}).get('dashboard') or {}).get('charts') or {}
    tr = ch.get('cpli_trend') or {}
    roles, values = tr.get('roles') or [], tr.get('values') or []
    pts = [(roles[i], values[i]) for i in range(len(roles)) if i < len(values) and values[i] is not None]
    if not pts:
        return P.NO_DATA
    amax = max(v for _, v in pts) * 1.1
    rows = [{'label': role.title(), 'values': [v], 'display': [fmt.ratio(v)]} for role, v in pts]
    return P.bars(rows, series=[{'label': 'CPLI', 'tone': 'accent'}], axis_max=amax)


def _cp_slip(ctx):
    r = _cp(ctx)
    ch = ((r or {}).get('dashboard') or {}).get('charts') or {}
    msv = ch.get('ms_variance') or []
    if not msv:
        return P.NO_DATA
    rows = []
    for m in msv:
        v = m.get('var')
        tone = 'neutral' if v is None else ('bad' if v > 0 else 'good')
        rows.append([m.get('name'), (fmt.days(v), tone)])
    return P.table(['Milestone', 'Slip vs baseline'], rows, aligns=['l', 'r'])


def _cp_census(ctx):
    r = _cp(ctx)
    census = (r or {}).get('census') or {}
    rows = []
    for role, c in census.items():
        if isinstance(c, dict):
            rows.append({'schedule': role.title(),
                         **{k: v for k, v in c.items() if isinstance(v, (int, float, str))}})
    return U.table_from_dicts(rows) if rows else P.NO_DATA


def _cp_milestones(ctx):
    r = _cp(ctx)
    ms = (r or {}).get('milestones')
    if isinstance(ms, list) and ms and isinstance(ms[0], dict):
        return U.table_from_dicts(ms)
    return P.NO_DATA


def _cp_float_migration(ctx):
    r = _cp(ctx)
    fmg = (r or {}).get('float_migration')
    if isinstance(fmg, list) and fmg and isinstance(fmg[0], dict):
        return U.table_from_dicts(fmg)
    if isinstance(fmg, dict):
        return U.kpi_from_dict(fmg)
    return P.NO_DATA


def _cp_recommendation(ctx):
    r = _cp(ctx)
    if not r:
        return P.NO_DATA
    parts = [r.get('effect'), r.get('recommendation'), r.get('conclusion')]
    parts = [p for p in parts if p]
    return P.text(parts) if parts else P.NO_DATA


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


def _cmp_durations(ctx):
    if not ctx.has_input('baseline'):
        return P.NO_DATA
    try:
        r = _cmp_report(ctx)
    except Exception:
        return P.NO_DATA
    rows = ((r or {}).get('durations') or {}).get('rows')
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return U.table_from_dicts(rows)
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


def _pd_bycode(ctx):
    if not ctx.has_input('previous'):
        return P.NO_DATA
    try:
        r = _pd_report(ctx)
    except Exception:
        return P.NO_DATA
    bc = (r or {}).get('progress_by_code')
    if isinstance(bc, list) and bc and isinstance(bc[0], dict):
        return U.table_from_dicts(bc)
    return P.NO_DATA


def _pd_watch(ctx):
    if not ctx.has_input('previous'):
        return P.NO_DATA
    try:
        r = _pd_report(ctx)
    except Exception:
        return P.NO_DATA
    w = (r or {}).get('watch_list')
    if isinstance(w, list) and w and isinstance(w[0], dict):
        return U.table_from_dicts(w)
    return P.NO_DATA


def provide(ctx):
    return [
        # Critical Path Analyzer
        Item('critpath:health', 'critpath', 'Critical Path Analyzer', 'Critical path health + CPLI',
             'score', _cp_health, _need('baseline'), BASELINE_REQ),
        Item('critpath:kpis', 'critpath', 'Critical Path Analyzer', 'CPLI / length / critical / near-critical',
             'kpi', _cp_kpis, _need('baseline'), BASELINE_REQ),
        Item('critpath:crit_near', 'critpath', 'Critical Path Analyzer', 'Critical & near-critical by schedule (chart)',
             'chart', _cp_crit_near, _need('baseline'), BASELINE_REQ),
        Item('critpath:cpli_trend', 'critpath', 'Critical Path Analyzer', 'CPLI by schedule (chart)',
             'chart', _cp_cpli_trend, _need('baseline'), BASELINE_REQ),
        Item('critpath:slip', 'critpath', 'Critical Path Analyzer', 'Milestone slip (chart)',
             'chart', _cp_slip, _need('baseline'), BASELINE_REQ),
        Item('critpath:census', 'critpath', 'Critical Path Analyzer', 'Critical & near-critical census',
             'table', _cp_census, _need('baseline'), BASELINE_REQ),
        Item('critpath:milestones', 'critpath', 'Critical Path Analyzer', 'Every-milestone finish table',
             'table', _cp_milestones, _need('baseline'), BASELINE_REQ),
        Item('critpath:float_migration', 'critpath', 'Critical Path Analyzer', 'Float migration',
             'table', _cp_float_migration, _need('baseline'), BASELINE_REQ),
        Item('critpath:recommendation', 'critpath', 'Critical Path Analyzer', 'Effect & recommendation',
             'text', _cp_recommendation, _need('baseline'), BASELINE_REQ),
        # Consultant Review
        Item('compare:impact', 'compare', 'Consultant Review', 'Delay before / after (but-for)',
             'kpi', _cmp_impact, _need('baseline'), BASELINE_REQ),
        Item('compare:changes', 'compare', 'Consultant Review', 'Logic & lag change summary',
             'table', _cmp_changes, _need('baseline'), BASELINE_REQ),
        Item('compare:durations', 'compare', 'Consultant Review', 'Duration & remaining changes',
             'table', _cmp_durations, _need('baseline'), BASELINE_REQ),
        Item('compare:milestones', 'compare', 'Consultant Review', 'Milestone finishes (baseline vs update)',
             'table', _cmp_milestones, _need('baseline'), BASELINE_REQ),
        # Update vs Update
        Item('period:progress', 'period', 'Update vs Update', 'Period progress',
             'kpi', _pd_progress, _need('previous'), PREV_REQ),
        Item('period:critical', 'period', 'Update vs Update', 'Critical-path movement this period',
             'table', _pd_critical, _need('previous'), PREV_REQ),
        Item('period:bycode', 'period', 'Update vs Update', 'Progress by activity code',
             'table', _pd_bycode, _need('previous'), PREV_REQ),
        Item('period:watch', 'period', 'Update vs Update', 'Next-period watch list',
             'table', _pd_watch, _need('previous'), PREV_REQ),
        Item('period:milestones', 'period', 'Update vs Update', 'Milestone finishes this period',
             'table', _pd_milestones, _need('previous'), PREV_REQ),
    ]
