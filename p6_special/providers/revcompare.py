"""Baseline Revision Comparison provider — two-file (Rev.00 vs Rev.01).

The Baseline Revision Comparison compares two approved baseline revisions. It owns a
real report renderer (``p6_revcompare.exporters.render_html``) that emits the exact
detailed tables + charts of every section, so this provider REUSES that renderer and
slices each ``data-sec`` section — the Studio auto-tracks the feature with no
hand-rebuilt tables (parity by construction).

It is a two-file feature: the open schedule is taken as **Rev.01 (Revised)** — the
same file the feature's own screen pre-fills into the Rev.01 slot — and the user
attaches the **Rev.00 (Original)** baseline it is compared against. Items therefore
declare ``requires`` (like ``providers/twofile.py``); until the original is attached
every item reports ``needs_input``, after which each section is ``ready`` only when it
actually renders (``resource`` needs cost/resource loading; ``detailed`` needs at least
one material change) — availability exactly complements ``produce``.
"""
import os
import re

from p6_special import payloads as P
from p6_special import reuse
from p6_special.registry import Item

FEATURE = 'revcompare'
FEATURE_TITLE = 'Baseline Revision Comparison'
_WRAP = 'srf-revcompare'

# The original baseline (Rev.00) the open schedule is compared against — mirrors the
# two-file 'requires' pattern (see providers/twofile.py).
ORIGINAL_REQ = [{'role': 'original', 'label': 'Original baseline (Rev.00)',
                 'accept': '.xml,.xer',
                 'hint': 'the first approved baseline; the open schedule is compared '
                         'against it as Rev.01 (Revised)'}]

# The exact data-sec keys + section titles p6_revcompare/exporters.render_html emits,
# in report order — so each item mirrors one feature section 1:1 and the Studio's
# numbered heading matches the section's own title. ('resource' is emitted only when a
# revision carries cost/resource loading; 'detailed' only when there is a material
# change — both are gated honestly by availability below.)
SECS = [
    ('summary', 'Executive Summary'),
    ('overview', 'Revision Overview'),
    ('milestones', 'Milestone Comparison'),
    ('critpath', 'Critical Path Comparison'),
    ('sequence', 'Major Sequence Changes'),
    ('logic', 'Major Relationship / Logic Changes'),
    ('scope', 'WBS, Calendar & Constraint Changes'),
    ('resource', 'Resource & Cost Comparison'),
    ('register', 'Detailed Change Register'),
    ('detailed', 'Detailed Change Analysis'),
]


def _full(ctx):
    """Render the WHOLE Baseline Revision Comparison report once (memoized per mode),
    exactly as the feature's PDF/preview does, so every sliced section auto-tracks the
    feature. Rev.01 = the open schedule; Rev.00 = the attached original baseline."""
    def build():
        rev1 = ctx.parsed()                     # open file  = Revised baseline (Rev.01)
        rev0 = ctx.parsed_input('original')     # attachment = Original baseline (Rev.00)
        if rev0 is None or rev1 is None:
            return None
        from p6_revcompare import build_report_from_data
        from p6_revcompare.exporters import render_html
        report = build_report_from_data(rev0, rev1, ctx.config)
        # File labels for the Overview / Executive tiles — the same basenames the
        # feature's own server handler sets (report['rev0']['file'] / ['rev1']['file']).
        try:
            report['rev0']['file'] = os.path.basename(ctx.input_path('original') or '') or None
            # ctx.xml_path may resolve to the cached copy ('{hash12}_{name}') when the
            # original path has moved (normal for a re-opened Recent Project); strip that
            # 12-hex cache prefix so the Rev.01 label shows the clean name the feature does.
            rev1_name = re.sub(r'^[0-9a-f]{12}_', '', os.path.basename(ctx.xml_path or ''))
            report['rev1']['file'] = rev1_name or None
        except Exception:
            pass
        return render_html(report, theme=ctx.mode)
    return ctx.memo(f'rc:full:{ctx.mode}', build)


def _strip_leading_h2(frag):
    """Drop the section's own leading ``<h2>…</h2>`` heading — the Studio already wraps
    each section in its own numbered badge (the picked item's title), so keeping the
    section's heading would stack two titles (matches feature_reports._strip_leading_h2)."""
    return re.sub(r'^\s*<h2\b[^>]*>.*?</h2>', '', frag or '', count=1, flags=re.S | re.I)


def _section(ctx, key):
    """One data-sec section of the report, reused verbatim (its exact markup + CSS,
    scoped to a wrapper). Returns ``None`` when the section did not render (so the item
    honestly reports no_data instead of a heading over nothing)."""
    full = _full(ctx)
    if not full:
        return None
    frag = _strip_leading_h2(reuse.extract_section(full, key))
    if not frag or not frag.strip():
        return None
    return {'kind': 'html', 'feature': FEATURE,
            'css': reuse.scope_css(reuse.extract_styles(full), f'.{_WRAP}'),
            'html': f'<div class="{_WRAP}">{frag}</div>'}


def _both_present(ctx):
    return ctx.has_xml() and ctx.has_input('original')


def _avail(key):
    """'needs_input' until BOTH revisions are present (the open schedule + the attached
    original), then 'ready' only if this section actually renders — exactly
    complementing produce(), never a 'ready' item that renders empty."""
    def availability(ctx):
        if not _both_present(ctx):
            return 'needs_input'
        try:
            return 'ready' if _section(ctx, key) else 'no_data'
        except Exception:
            return 'no_data'
    return availability


def provide(ctx):
    items = []
    for key, title in SECS:
        items.append(Item(
            f'{FEATURE}:{key}', FEATURE, FEATURE_TITLE, title, 'section',
            (lambda ctx, k=key: _section(ctx, k) or P.NO_DATA),
            _avail(key), ORIGINAL_REQ))
    return items
