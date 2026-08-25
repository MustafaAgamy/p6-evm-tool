"""Adapters that pull each feature's OWN report sections into Special Report.

Each feature renders its real report (its exact detailed tables + real charts) via
its own renderer; we slice the requested section and return it as an ``html``
payload carrying the feature's markup + its CSS scoped to a wrapper. Composed in
one document (with the shared report_theme tokens), the result looks exactly like
each feature's own report. Section granularity:
  - update / critpath / period : sliced by ``data-sec`` (per-section).
  - calendar                   : rendered one section at a time (``sections=[k]``).
  - audit                      : one item per module (Float/OOS/Lag/Dangling).
  - evm / compare / kb         : the whole feature report as one item.
"""
import re

from p6_special import reuse

# section catalogs (key, title) — the exact sections each feature's report offers
UPDATE_SECS = [('time', 'Time Status'), ('bycode', 'Planned vs Actual — by activity code'),
               ('driving', 'Driving Path Analyzer'), ('counts', 'Planned vs Actual — by activity count'),
               ('scope', 'Scope Weight & Recommendation'), ('conclusion', 'Executive read')]
CALENDAR_SECS = [('dashboard', 'Executive dashboard'), ('timeline', 'Working-day timeline'),
                 ('stats', 'Monthly working-day stats'), ('exceptions', 'Exceptions (holidays / shutdowns)'),
                 ('hours', 'Work-hours profiles'), ('comparison', 'Calendar comparison'),
                 ('usage', 'Calendar usage'), ('conflicts', 'Conflicts'),
                 ('weather', 'Weather impact'), ('conclusion', 'Conclusion')]
CRITPATH_SECS = [('verdict', 'Verdict'), ('dashboard', 'Execution dashboard'),
                 ('driving_path', 'Critical Path Analyzer (driving paths)'), ('census', 'Critical & near-critical census'),
                 ('milestones', 'Every-milestone finish table'), ('float_migration', 'Float migration'),
                 ('recommendation', 'Effect & recommendation')]
PERIOD_SECS = [('verdict', 'Verdict'), ('progress', 'Progress vs last forecast'), ('dashboard', 'Execution dashboard'),
               ('recommendation', 'What management needs to know'), ('critical_compare', 'Critical-path comparison'),
               ('critical', 'Critical-path movement'), ('progress_table', 'Progress by activity'),
               ('watch', 'Next-period watch list'), ('whatmoved', 'What moved this period'),
               ('bycode', 'Progress by activity code'), ('milestones', 'Milestones & drift'),
               ('conclusions', 'Executive conclusion')]
AUDIT_MODULES = [('float', 'Float Analysis'), ('out_of_sequence', 'Out of Sequence'),
                 ('lag_lead', 'Lag & Lead'), ('dangling', 'Dangling Activities')]


def _meta(ctx):
    return {'project_name': ctx.project_name, 'data_date': ctx.data_date}


def _strip_leading_header(frag):
    """Remove a leading ``<div class="rh|head">…</div>`` report banner with proper
    nested-div balancing (a naive non-greedy regex would cut at the first inner
    </div> and leave malformed HTML)."""
    m = re.match(r'\s*<div\s+class="(rh|head)"[^>]*>', frag, re.I)
    if not m:
        return frag
    depth, pos = 1, m.end()
    tag = re.compile(r'<(/?)div\b', re.I)
    while depth and pos < len(frag):
        t = tag.search(frag, pos)
        if not t:
            break
        depth += -1 if t.group(1) else 1
        pos = t.end()
        if depth == 0:
            close = frag.find('>', pos)
            return frag[close + 1:] if close != -1 else frag[pos:]
    return frag


def _body_after_head(html):
    """Everything after </head>, stripped of body/html wrappers + the leading
    report header banner (so a single-section render doesn't repeat the title)."""
    m = re.search(r'</head>(.*)', html or '', re.S | re.I)
    frag = m.group(1) if m else (html or '')
    frag = re.sub(r'</?(body|html)[^>]*>', '', frag, flags=re.I)
    return _strip_leading_header(frag.strip()).strip()


def _payload(feature, css, fragment):
    if not fragment or not fragment.strip():
        return None
    return {'kind': 'html', 'feature': feature,
            'css': reuse.scope_css(css, f'.srf-{feature}'),
            'html': f'<div class="srf-{feature}">{fragment}</div>'}


# ── whole-report renders (memoized per feature+mode) ─────────────────────────
def _rendered(ctx, key, fn):
    return ctx.memo(f'fr:{key}:{ctx.mode}', fn)


def _update_full(ctx):
    def b():
        data = ctx.parsed()
        if data is None:
            return None
        from p6_update.analysis import build_report_from_data
        from p6_update.exporters import render_html
        return render_html(build_report_from_data(data, ctx.computed()), theme=ctx.mode)
    return _rendered(ctx, 'update', b)


def _critpath_full(ctx):
    def b():
        cur, base = ctx.parsed(), ctx.parsed_input('baseline')
        if cur is None or base is None:
            return None
        from p6_critpath.analysis import build_report
        from p6_critpath.exporters import render_html
        rep = build_report({'current': cur, 'baseline': base}, mode='update_baseline')
        return render_html(rep, theme=ctx.mode)
    return _rendered(ctx, 'critpath', b)


def _period_full(ctx):
    def b():
        cur, prev = ctx.parsed(), ctx.parsed_input('previous')
        if cur is None or prev is None:
            return None
        from p6_period.report import build_report_from_data
        from p6_period.exporters import render_html
        from p6_evm.metrics import compute
        from p6_evm.classify import auto_categories, build_wbs_classifier
        cfg = dict(ctx.config)
        cfg['categories'] = auto_categories(prev)
        pm = compute(prev, cfg, overrides={}, classifier=build_wbs_classifier(prev))
        rep = build_report_from_data(prev, cur, pm, ctx.computed(), ctx.config)
        return render_html(rep, theme=ctx.mode)
    return _rendered(ctx, 'period', b)


def _datasec_section(full_html, feature, key):
    if not full_html:
        return None
    frag = reuse.extract_section(full_html, key)
    return _payload(feature, reuse.extract_styles(full_html), frag)


def update_section(ctx, key):
    return _datasec_section(_update_full(ctx), 'update', key)


def critpath_section(ctx, key):
    return _datasec_section(_critpath_full(ctx), 'critpath', key)


def period_section(ctx, key):
    return _datasec_section(_period_full(ctx), 'period', key)


def calendar_section(ctx, key):
    def b():
        if not ctx.calendar:
            return None
        from p6_calendar.report import render_calendar_report
        return render_calendar_report(ctx.calendar, _meta(ctx), weather=ctx.weather,
                                      sections=[key], theme=ctx.mode)
    html = ctx.memo(f'fr:calendar:{key}:{ctx.mode}', b)
    if not html:
        return None
    return _payload('calendar', reuse.extract_styles(html), _body_after_head(html))


def audit_module(ctx, key):
    def b():
        mod = ((ctx.audit or {}).get('modules') or {}).get(key)
        if not mod:
            return None
        from p6_audit.report import render_module_report
        return render_module_report(mod, _meta(ctx), theme=ctx.mode)
    html = ctx.memo(f'fr:audit:{key}:{ctx.mode}', b)
    if not html:
        return None
    return _payload('audit', reuse.extract_styles(html), _body_after_head(html))


def evm_full_report(ctx):
    def b():
        result = ctx.computed()
        if result is None:
            return None
        from p6_evm.evm_report import render_evm_report
        gap = (ctx.extras or {}).get('gap')
        return render_evm_report(result, _meta(ctx), gap=gap, theme=ctx.mode)
    html = ctx.memo(f'fr:evm_full:{ctx.mode}', b)
    if not html:
        return None
    return _payload('evm', reuse.extract_styles(html), _body_after_head(html))


def compare_full_report(ctx):
    def b():
        cur, base = ctx.parsed(), ctx.parsed_input('baseline')
        if cur is None or base is None:
            return None
        from p6_compare.report import build_report_from_data
        from p6_compare.exporters import render_html
        return render_html(build_report_from_data(base, cur, ctx.config), theme=ctx.mode)
    html = ctx.memo(f'fr:compare_full:{ctx.mode}', b)
    if not html:
        return None
    return _payload('compare', reuse.extract_styles(html), _body_after_head(html))


def kb_full_report(ctx):
    def b():
        data = ctx.parsed()
        if data is None:
            return None
        from p6_kb.review import run_review
        from p6_kb.exporters import render_html
        return render_html(run_review(data), theme=ctx.mode)
    html = ctx.memo(f'fr:kb_full:{ctx.mode}', b)
    if not html:
        return None
    return _payload('kb', reuse.extract_styles(html), _body_after_head(html))
