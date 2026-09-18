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
# Only keys the Calendar Audit report (feature='calendar') actually emits — the
# feature folds monthly stats into 'timeline' and usage/conflicts into 'comparison',
# and has no standalone 'stats'/'usage'/'conflicts'/'conclusion' section, so advertising
# those produced dead, never-rendering items (which also dragged the group to 'No data').
CALENDAR_SECS = [('dashboard', 'Executive dashboard'), ('timeline', 'Working-day timeline'),
                 ('exceptions', 'Exceptions (holidays / shutdowns)'),
                 ('hours', 'Work-hours profiles'), ('comparison', 'Calendar comparison')]
# Bad-Weather report — the SAME 7 selectable sub-sections the feature's own screen
# offers (WEATHER_SECTIONS), rendered via feature='weather' so each is its own data-sec.
WEATHER_SECS = [('wx_dashboard', 'Weather — Execution dashboard'),
                ('wx_timeline', 'Weather — Timeline & statistics'),
                ('wx_why', 'Weather — Why this result'),
                ('wx_upcoming', 'Weather — Upcoming bad-weather days'),
                ('wx_causes', "Weather — What's causing the lost days"),
                ('wx_milestones', 'Weather — Impact on milestones'),
                ('wx_recovery', 'Weather — Recovery recommendations')]
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


def _strip_trailing_foot(frag):
    """Drop the Calendar report's boilerplate footer sentence. Without this, a
    section whose body rendered empty (e.g. Weather with no estimate, Exceptions
    with none ahead) would still carry the always-present footer div, so the
    fragment looks non-empty and the section shows a heading over just boilerplate.
    Removing it lets an empty section collapse to '' -> NO_DATA -> honestly gated."""
    return re.sub(r'\s*<div class="foot">.*?</div>\s*$', '', frag or '', flags=re.S).strip()


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


def _strip_leading_h2(frag):
    """Drop a data-sec section's own leading ``<h2>…</h2>`` heading. Each reused
    update/critpath/period section carries the report's own fixed-number heading
    (e.g. "1 · Time Status"), but the Studio already wraps the section in its own
    numbered badge (the picked item's title), so without this the section shows two
    stacked headings whose numbers disagree (pick order vs the report's fixed 1–5)."""
    return re.sub(r'^\s*<h2\b[^>]*>.*?</h2>', '', frag or '', count=1, flags=re.S | re.I)


def _datasec_section(full_html, feature, key):
    if not full_html:
        return None
    frag = reuse.extract_section(full_html, key)
    return _payload(feature, reuse.extract_styles(full_html), _strip_leading_h2(frag))


# Activity-code tier order the Update screen uses to pick Section 2's default
# dimension (_defaultCodeType in ui/modules/update.js) — discipline first.
_CODE_TIERS = [r'disciplin', r'type of work', r'type of civil', r'\btrade\b',
               r'main wbs', r'\bphase\b']


def _default_code_type(types):
    for pat in _CODE_TIERS:
        for t in (types or []):
            if re.search(pat, str(t), re.I):
                return t
    return (types or [None])[0]


def _update_bycode(ctx):
    """Section 2 (Planned vs Actual by activity code) rendered for the screen's DEFAULT
    dimension (the discipline-preferred code type) rather than whatever code type happens
    to be first — so the picked result charts the same dimension the Update screen shows."""
    def b():
        data = ctx.parsed()
        if data is None:
            return None
        from p6_update.analysis import build_report_from_data
        from p6_update.exporters import render_html
        rep = build_report_from_data(data, ctx.computed())
        default = _default_code_type(rep.get('code_types') or [])
        cf = {'types': [default]} if default else None
        return render_html(rep, sections=['bycode'], code_filter=cf, theme=ctx.mode)
    html = ctx.memo(f'fr:update:bycode:{ctx.mode}', b)
    if not html:
        return None
    frag = reuse.extract_section(html, 'bycode')
    return _payload('update', reuse.extract_styles(html), _strip_leading_h2(frag))


def update_section(ctx, key):
    if key == 'bycode':
        return _update_bycode(ctx)
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
    return _payload('calendar', reuse.extract_styles(html), _strip_trailing_foot(_body_after_head(html)))


def weather_section(ctx, key):
    """One sub-section of the Bad-Weather report, reused verbatim. Rendered with
    feature='weather' so render_calendar_report takes the is_weather branch that wraps
    each of the 7 sub-sections in its own data-sec — matching the feature's own
    per-section picker (WEATHER_SECTIONS) instead of one coarse all-or-nothing block."""
    def b():
        if not (ctx.calendar and ctx.weather):
            return None
        from p6_calendar.report import render_calendar_report
        return render_calendar_report(ctx.calendar, _meta(ctx), weather=ctx.weather,
                                      sections=[key], theme=ctx.mode, feature='weather')
    html = ctx.memo(f'fr:weather:{key}:{ctx.mode}', b)
    if not html:
        return None
    return _payload('weather', reuse.extract_styles(html),
                    _strip_trailing_foot(_body_after_head(html)))


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
        extras = ctx.extras or {}
        gap = extras.get('gap')
        # Match the on-screen / feature-PDF Executive Dashboard: pass the stored finish
        # dates and (if present) the entered Actual Cost so the tiles show real dates
        # and AC instead of '—' / the P6 fallback. The AC override lives client-side
        # (localStorage), so it is only threaded when the snapshot actually stored one.
        meta = dict(_meta(ctx))
        for k in ('baseline_finish', 'expected_finish', 'actual_cost'):
            if extras.get(k) is not None:
                meta[k] = extras.get(k)
        # Render the Engineering Progress section like the feature: prefer the stored
        # E1 rows (with their aggregates) else the P6 drawings-by-trade rows. Absent
        # engineering just leaves the section empty (as the feature does with no data).
        engineering = None
        e1_rows = extras.get('engineering_e1')
        p6_rows = extras.get('engineering_p6')
        if e1_rows:
            engineering = {'mode': 'E1', 'rows': e1_rows,
                           'overall': extras.get('engineering_overall') or {},
                           'by_trade': extras.get('engineering_by_trade') or [],
                           'gaps': extras.get('engineering_gaps') or {}}
        elif p6_rows:
            engineering = {'mode': 'P6', 'rows': p6_rows}
        return render_evm_report(result, meta, gap=gap, engineering=engineering, theme=ctx.mode)
    html = ctx.memo(f'fr:evm_full:{ctx.mode}', b)
    if not html:
        return None
    return _payload('evm', reuse.extract_styles(html), _body_after_head(html))


# EVM report section keys (render_evm_report's `sections=` filter), so a picked
# EVM result looks EXACTLY like that section in the real EVM Report — the report's
# own heading + styled table/bars — instead of a re-derived generic block.
EVM_SECS = [('progress', 'Project Progress — Planned vs Actual'),
            ('category', 'Category Weights & Overall Progress'),
            ('value', 'Planned Value vs Earned Value')]


def evm_section(ctx, key):
    """One section of the EVM Report, reused verbatim (its exact style + format).

    Renders the EVM report limited to ``key`` (no gap/engineering add-ons, so only
    that section appears), then strips the report banner + footer so it drops into
    a Special Report section cleanly."""
    def b():
        result = ctx.computed()
        if result is None:
            return None
        from p6_evm.evm_report import render_evm_report
        return render_evm_report(result, _meta(ctx), sections=[key], theme=ctx.mode)
    html = ctx.memo(f'fr:evm:{key}:{ctx.mode}', b)
    if not html:
        return None
    return _payload('evm', reuse.extract_styles(html),
                    _strip_trailing_foot(_body_after_head(html)))


def evm_gap_section(ctx):
    """The EVM Report's PV-EV Gap section, reused verbatim. Parse-free: the gap
    section only formats the STORED gap dict (ctx.extras['gap']), so it needs no
    re-parse — ``sections=['gap']`` matches no core key, leaving only the
    data-driven gap block to render."""
    gap = (ctx.extras or {}).get('gap')
    if not (isinstance(gap, dict) and gap.get('groups')):
        return None
    def b():
        from p6_evm.evm_report import render_evm_report
        return render_evm_report(ctx.evm or {}, _meta(ctx), gap=gap, sections=['gap'], theme=ctx.mode)
    html = ctx.memo(f'fr:evm_gap:{ctx.mode}', b)
    if not html:
        return None
    return _payload('evm', reuse.extract_styles(html),
                    _strip_trailing_foot(_body_after_head(html)))


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


def kb_v2_report(ctx):
    """The CURRENT Constructability Review report — the v2 'Project Risk Summary' +
    'Constructability Findings' the screen shows — rendered through the SAME Global
    Print-Preview framework the feature's own Preview/PDF use (default-ON components
    only). Not the legacy KB dashboard (a second, contradictory score the feature
    intentionally hides), so a picked result == the feature's screen."""
    def b():
        data = ctx.parsed()
        if data is None:
            return None
        from p6_kb.review import run_review
        from p6_report import build_document, get_spec
        report = ctx.memo('kb_review', lambda: run_review(data))
        spec = get_spec('constructability', report)
        if spec is None:
            return None
        # selected_ids=None → the spec's default-ON components (v2 summary + findings).
        return build_document(spec, report, None, None, theme=ctx.mode)
    html = ctx.memo(f'fr:kb_v2:{ctx.mode}', b)
    if not html:
        return None
    return _payload('kb', reuse.extract_styles(html), _body_after_head(html))
