"""Update Analysis provider — offers the feature's OWN report sections (exact
detailed results + real charts), recomputed on demand from the imported file.

Section 2 (Planned vs Actual — by activity code) and Section 5 (Scope Weight &
Recommendation) each produce one result *per activity-code dimension* in the
schedule — not just the screen's default dimension. So this provider exposes one
item per dimension (``update:bycode:<type>`` / ``update:scope:<type>``) alongside
the original default items, giving the Reporting Studio the feature's FULL result
set. Every per-dimension item is rendered through the feature's own renderer
(``p6_update.exporters.render_html``) with the same ``code_filter`` / ``scope_code``
the feature's screen uses, then sliced by ``data-sec`` — parity by construction.
"""
from p6_special import payloads as P
from p6_special import reuse
from p6_special import feature_reports as FR
from p6_special.registry import Item

FEATURE = 'update'
FEATURE_TITLE = 'Update Analysis'


def _ready(ctx):
    return 'ready' if ctx.has_xml() else 'no_data'


def _mk(key, title):
    return Item(f'update:{key}', FEATURE, FEATURE_TITLE, title, 'section',
                lambda ctx, k=key: FR.update_section(ctx, k) or P.NO_DATA, _ready)


# ── self-contained reuse adapter (mirrors feature_reports._payload /
# _strip_leading_h2 so per-dimension items look byte-for-byte like the existing
# default Update items) ───────────────────────────────────────────────────────
def _payload(fragment, css):
    if not fragment or not fragment.strip():
        return None
    return {'kind': 'html', 'feature': FEATURE,
            'css': reuse.scope_css(css, f'.srf-{FEATURE}'),
            'html': f'<div class="srf-{FEATURE}">{fragment}</div>'}


def _section_payload(html, key):
    """Slice ``<section data-sec="KEY">`` from a rendered Update report and wrap it
    as an ``html`` payload — the report's own numbered ``<h2>`` is dropped (the
    Studio wraps the section in its own numbered badge), exactly as the default
    Update items do (feature_reports._datasec_section / _update_bycode)."""
    if not html:
        return None
    frag = FR._strip_leading_h2(reuse.extract_section(html, key))
    return _payload(frag, reuse.extract_styles(html))


# ── the Update report, built once per context (parse + compute), memoized ──────
def _report(ctx):
    """The full Update-Analysis report for the open file, via the feature's own
    ``build_report_from_data`` (reuses the feature machinery, no maths here).
    None when the file isn't available (evicted cache / no import)."""
    def build():
        data = ctx.parsed()
        if data is None:
            return None
        from p6_update.analysis import build_report_from_data
        return build_report_from_data(data, ctx.computed())
    try:
        return ctx.memo('update:report', build)
    except Exception:
        return None


# ── Section 2 · Planned vs Actual — one item per activity-code dimension ───────
def _bycode_dim_html(ctx, code_type):
    def b():
        rep = _report(ctx)
        if rep is None:
            return None
        from p6_update.exporters import render_html
        return render_html(rep, sections=['bycode'],
                           code_filter={'types': [code_type]}, theme=ctx.mode)
    return ctx.memo(f'update:bycode:{code_type}:{ctx.mode}', b)


def _bycode_dim_renders(ctx, code_type):
    """This dimension actually renders real content only when its by-code bucket has
    rows — otherwise the section would show just a 'No values for this activity code'
    note, so it must gate 'no_data' (availability exactly complements produce)."""
    rep = _report(ctx)
    return bool(rep and (rep.get('by_code') or {}).get(code_type))


def _bycode_dim_produce(ctx, code_type):
    if not _bycode_dim_renders(ctx, code_type):
        return P.NO_DATA
    return _section_payload(_bycode_dim_html(ctx, code_type), 'bycode') or P.NO_DATA


def _bycode_dim_avail(ctx, code_type):
    return 'ready' if _bycode_dim_renders(ctx, code_type) else 'no_data'


def _bycode_items(ctx):
    """One item per code dimension present, enumerated from the built report's
    'code_types' (the feature's own dimension list)."""
    rep = _report(ctx)
    if not rep:
        return []
    out = []
    for t in (rep.get('code_types') or []):
        out.append(Item(
            f'update:bycode:{t}', FEATURE, FEATURE_TITLE,
            f'Planned vs Actual — by {t}', 'section',
            lambda ctx, t=t: _bycode_dim_produce(ctx, t),
            lambda ctx, t=t: _bycode_dim_avail(ctx, t)))
    return out


# ── Section 5 · Scope Weight & Recommendation — one item per cost-loaded dim ───
def _scope_dim_html(ctx, code_type):
    def b():
        rep = _report(ctx)
        if rep is None:
            return None
        from p6_update.exporters import render_html
        return render_html(rep, sections=['scope'], scope_code=code_type, theme=ctx.mode)
    return ctx.memo(f'update:scope:{code_type}:{ctx.mode}', b)


def _scope_dim_renders(ctx, code_type):
    """report['scope'] (scope_all) holds only the cost-loaded dimensions with rows —
    so a dimension present there always renders; anything else gates 'no_data'."""
    rep = _report(ctx)
    return bool(rep and (rep.get('scope') or {}).get(code_type))


def _scope_dim_produce(ctx, code_type):
    if not _scope_dim_renders(ctx, code_type):
        return P.NO_DATA
    return _section_payload(_scope_dim_html(ctx, code_type), 'scope') or P.NO_DATA


def _scope_dim_avail(ctx, code_type):
    return 'ready' if _scope_dim_renders(ctx, code_type) else 'no_data'


def _scope_items(ctx):
    """One item per cost-loaded dimension, enumerated from the report's scope keys
    (report['scope'] = analysis.scope_all — only dimensions that carry cost)."""
    rep = _report(ctx)
    if not rep:
        return []
    out = []
    for t in (rep.get('scope') or {}).keys():
        out.append(Item(
            f'update:scope:{t}', FEATURE, FEATURE_TITLE,
            f'Scope Weight & Recommendation — by {t}', 'section',
            lambda ctx, t=t: _scope_dim_produce(ctx, t),
            lambda ctx, t=t: _scope_dim_avail(ctx, t)))
    return out


def provide(ctx):
    # The feature's sections in report order, with the per-dimension items injected
    # right after their default sibling. The original default items are kept intact
    # (update:bycode uses the discipline-preferred dimension from
    # feature_reports._default_code_type; update:scope uses the report's scope_default).
    items = []
    for k, t in FR.UPDATE_SECS:
        items.append(_mk(k, t))
        if k == 'bycode':
            items.extend(_bycode_items(ctx))
        elif k == 'scope':
            items.extend(_scope_items(ctx))
    return items
