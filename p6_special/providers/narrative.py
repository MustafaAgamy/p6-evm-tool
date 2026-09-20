"""Baseline Narrative provider — the rich Baseline Narrative Report.

The full "Baseline Narrative Report" feature (package ``p6_narrative``) is the tool's
actual Baseline Narrative: the server's ``/api/narrative`` handler parses the open
schedule, builds the ~10-section document with
``p6_narrative.report.build_report(data, path=…, setup=…)`` and renders it to HTML with
``p6_narrative.html.render_narrative_html`` (the same HTML the on-screen tab and the PDF
export draw from). This provider REUSES that renderer end-to-end: it builds the doc ONCE
(memoized), renders it, then exposes ONE ``section``-type Item per section — each sliced
verbatim (its exact markup + CSS, scoped to a wrapper) so a picked narrative result renders
byte-for-byte like that section of the feature's own report, with no table hand-rebuilt.

Build inputs mirror the server handler exactly: ``data = ctx.parsed()`` (the open schedule),
``path = ctx.xml_path`` (so §Activity Codes can read the full code catalog, as the handler's
``path=resolved`` does), and ``setup=None`` — the feature's DEFAULT output with no before-run
setup form, which is what the screen shows on first open. ``build_report`` itself pulls the
Calendar feature's audit (``p6_calendar.audit.calendar_audit``) and the activity-code catalog
internally, so nothing else needs assembling; no EVM number is recomputed and no ``records``
key is carried.

The redesigned report (``p6_narrative.html``) wraps each section as
``<section class="sec" data-section="N">…</section>`` — sliceable exactly like the
update/critpath/period providers slice ``data-sec``, but keyed on ``data-section``. The
``data-section`` value is the section's POSITION NUMBER (1..N); ``build_report`` can drop a
section (e.g. Project Calendars when no calendar audit is available), which renumbers the
rest, so :func:`_section` resolves the live ``data-section`` key by matching the section
TITLE in the built doc rather than assuming a fixed number — the Item ids stay stable
whatever the numbering. Availability exactly complements ``produce()``: an item is ``ready``
only when its section actually renders real content for the current schedule, otherwise
``no_data`` (the whole feature is gated on ``ctx.has_xml()`` — the narrative re-parses the
XML, so the file must be on disk).
"""
import re

from p6_special import payloads as P
from p6_special import reuse
from p6_special.registry import Item

FEATURE = 'narrative'
FEATURE_TITLE = 'Baseline Narrative'
_WRAP = 'srf-narrative'

# The canonical sections of the Baseline Narrative Report (p6_narrative.report.build_report),
# in report order: (stable slug for the Item id, the section's exact title). The Item id is
# built from the slug so it never moves; the live data-section key (the section number) is
# resolved from the built doc at produce time by matching the title.
SECS = [
    ('overview',   'Project Overview'),
    ('layout',     'Project Layout'),
    ('brief',      'Project Brief'),
    ('milestones', 'Major Milestones'),
    ('keydates',   'Key Dates'),
    ('value',      'Contract Value'),
    ('scope',      'Scope of Work'),
    ('calendars',  'Project Calendars & Holidays'),
    ('wbs',        'Work Breakdown Structure'),
    ('codes',      'Activity Codes'),
    ('sequence',   'Sequence of Work'),
]
_TITLE_BY_SLUG = dict(SECS)


# ── build the feature's OWN report once (memoized), exactly as the server does ──────────
def _full(ctx):
    """The whole Baseline Narrative Report, built + rendered ONCE (memoized), exactly as
    ``server._handle_narrative`` does: parse the open schedule, ``build_report(data,
    path=ctx.xml_path, setup=None)`` (default output — no user setup form), then
    ``render_narrative_html(doc_dict)``. Returns ``{'sections': [...], 'html': str}`` so
    every sliced section auto-tracks the feature, or ``None`` when there is no schedule to
    narrate."""
    def build():
        data = ctx.parsed()
        if data is None:
            return None
        from p6_narrative.report import build_report
        from p6_narrative.html import render_narrative_html
        doc = build_report(data, path=ctx.xml_path, setup=None)
        doc_dict = doc.to_dict()
        return {'sections': doc_dict.get('sections') or [],
                'html': render_narrative_html(doc_dict)}
    return ctx.memo('narrative:full', build)


def _section_number(full, title):
    """The live ``data-section`` key (the section number) for a section TITLE in the built
    doc, or ``None`` when that section did not appear (e.g. Calendars dropped)."""
    for s in full['sections']:
        if s.get('title') == title:
            n = s.get('number')
            return None if n is None else str(n)
    return None


def _extract_section(html, key):
    """Inner HTML of ``<section … data-section="KEY">…</section>`` (brace-safe on nested
    <section> tags). The self-contained twin of :func:`p6_special.reuse.extract_section`,
    which keys on ``data-sec``; the narrative renderer tags each section with
    ``data-section`` (the section number), so this keys on that attribute. The trailing
    quote in the pattern stops ``"1"`` matching ``"11"``. Returns '' when not found."""
    if not html:
        return ''
    start = re.search(r'<section[^>]*\bdata-section="%s"[^>]*>' % re.escape(str(key)),
                      html, re.I)
    if not start:
        return ''
    i = start.end()
    depth = 1
    tag = re.compile(r'<(/?)section\b', re.I)
    pos = i
    while depth and pos < len(html):
        m = tag.search(html, pos)
        if not m:
            break
        depth += -1 if m.group(1) else 1
        pos = m.end()
        if depth == 0:
            return html[i:m.start()]
    return html[i:]


def _strip_leading_h1(frag):
    """Drop the section's own leading ``<h1 class="sec">N) Title</h1>`` heading — the
    Studio already wraps each section in its own numbered badge (the picked item's title),
    so keeping the section's heading would stack two titles (mirrors
    ``feature_reports._strip_leading_h2`` / ``revcompare._strip_leading_h2``)."""
    return re.sub(r'^\s*<h1\b[^>]*>.*?</h1>', '', frag or '', count=1, flags=re.S | re.I)


def _section(ctx, slug):
    """One section of the narrative, reused verbatim (its exact markup + CSS, scoped to a
    wrapper). Returns ``None`` when the schedule can't be narrated, the section didn't
    appear, or it rendered empty — so the item honestly reports no_data instead of a
    heading over nothing."""
    full = _full(ctx)
    if not full:
        return None
    number = _section_number(full, _TITLE_BY_SLUG[slug])
    if number is None:
        return None
    frag = _strip_leading_h1(_extract_section(full['html'], number))
    if not frag or not frag.strip():
        return None
    css = reuse.scope_css(reuse.extract_styles(full['html']), f'.{_WRAP}')
    # The narrative is a FIXED-appearance report (navy headings + dark body text on white
    # A4 pages, not theme-aware). Its <body> backing is the off-page grey, which scope_css
    # would paint onto the wrapper; force the wrapper to the report's own white surface so
    # the reused section reads exactly as it does on the feature's page, in any Studio mode.
    css += f'\n.{_WRAP}{{background:#fff}}'
    return {'kind': 'html', 'feature': FEATURE, 'css': css,
            'html': f'<div class="{_WRAP}">{frag}</div>'}


# ── availability — exactly complements produce() ───────────────────────────────────────
def _avail(slug):
    """Gate the whole feature on ``ctx.has_xml()`` (the narrative re-parses the XML), then
    'ready' only if this section actually renders real content — exactly complementing
    :func:`_section`/produce(), never a 'ready' item that renders empty."""
    def availability(ctx):
        if not ctx.has_xml():
            return 'no_data'
        try:
            return 'ready' if _section(ctx, slug) else 'no_data'
        except Exception:
            return 'no_data'
    return availability


def provide(ctx):
    items = []
    for slug, title in SECS:
        items.append(Item(
            f'{FEATURE}:{slug}', FEATURE, FEATURE_TITLE, title, 'section',
            (lambda ctx, s=slug: _section(ctx, s) or P.NO_DATA),
            _avail(slug)))
    return items
