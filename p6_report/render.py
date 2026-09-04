"""The single assembler — the one source of truth for Preview == PDF == Print.

``manifest(spec, report)`` returns the component list the Report-Contents selector is
built from. ``build_document(spec, report, selected_ids, order)`` turns a selection
into exactly one self-contained HTML document. The preview iframe is fed this string;
the PDF is Chrome printing this same string. They cannot diverge because there is only
one function that lays out the page.

Selection rules (binding Global Reporting standard):
  * only ticked components appear — unticked ones are ABSENT, not hidden;
  * a ticked component whose data is empty shows "No data available", never dropped;
  * sections are auto-numbered 1..N in the chosen order, with a page footer counter.
"""
import html as _html
from typing import List, Optional

import report_theme
from p6_report.registry import ReportSpec

_NO_DATA = ('summary', 'chart', 'table', 'text', 'findings', 'recommendations')


def _e(v) -> str:
    return _html.escape(str(v if v is not None else ''))


def manifest(spec: ReportSpec, report: dict) -> List[dict]:
    """The selector's view of the report: one row per component, in spec order."""
    report = report or {}
    return [{
        'id': c.id,
        'title': c.title,
        'type': c.type if c.type in _NO_DATA else 'text',
        'description': c.description,
        'default': bool(c.default),
        'has_data': c.data_available(report),
    } for c in spec.components]


def _resolve_selection(spec: ReportSpec, selected_ids, order) -> List[str]:
    """Turn (selected_ids, order) into the final ordered list of component ids.

    selected_ids is None  -> the spec's default set (first open, no saved selection).
    order, when given, sets the sequence; any selected id missing from order keeps its
    spec position after the ordered ones. Unknown ids are dropped.
    """
    known = spec.by_id()
    if selected_ids is None:
        chosen = spec.default_ids()
    else:
        chosen = [i for i in selected_ids if i in known]

    if not order:
        # keep spec order for the chosen set
        return [c.id for c in spec.components if c.id in set(chosen)]

    chosen_set = set(chosen)
    ordered = [i for i in order if i in chosen_set]
    ordered += [c.id for c in spec.components if c.id in chosen_set and c.id not in set(ordered)]
    return ordered


def _section(n: int, comp, report: dict) -> str:
    """One numbered section: heading + the component fragment (or a No-data note)."""
    if comp.data_available(report):
        body = comp.render_fragment(report)
        if not body.strip():
            body = '<div class="rf-nodata">No data available.</div>'
    else:
        label = 'No findings.' if comp.type in ('findings', 'recommendations') else 'No data available.'
        body = f'<div class="rf-nodata">{label}</div>'
    return (f'<section class="rf-section" data-cid="{_e(comp.id)}">'
            f'<h2 class="rf-h2"><span class="rf-num">{n}.</span> {_e(comp.title)}</h2>'
            f'{body}</section>')


def build_document(spec: ReportSpec, report: dict,
                   selected_ids: Optional[List[str]] = None,
                   order: Optional[List[str]] = None,
                   theme: Optional[str] = None) -> str:
    """Assemble the selected components into one print-ready HTML document.

    ``theme`` is one of the shared appearance modes (report_theme.MODES). Its
    ``--rpt-*`` token palette is injected at the end of <head>, so this ONE
    assembler themes every print-preview report — and the frame + every feature
    that reads the tokens gets all six modes for free. Unknown/None → light."""
    report = report or {}
    ids = _resolve_selection(spec, selected_ids, order)
    by_id = spec.by_id()

    sections = ''.join(_section(i + 1, by_id[cid], report) for i, cid in enumerate(ids))
    if not sections:
        sections = '<section class="rf-section"><div class="rf-nodata">No sections selected.</div></section>'

    size = 'A4 landscape' if spec.orientation == 'landscape' else 'A4 portrait'
    meta = f'<div class="rf-meta">{_e(spec.meta_line)}</div>' if spec.meta_line else ''
    sub = f'<div class="rf-sub">{_e(spec.subtitle)}</div>' if spec.subtitle else ''
    foot = f'<div class="rf-foot">{_e(spec.footer)}</div>' if spec.footer else ''

    # Sections are numbered in-flow (1., 2., …) so they read as a numbered report in
    # every engine. The @bottom-right page counter below is standards-compliant paged
    # media, but Chromium (the current HTML→PDF pipeline) does not render margin-box
    # content, so it is dormant there and lights up only if the pipeline moves to a
    # paged-media renderer. Section numbering is the numbering the reader actually sees.
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: {size}; margin: 11mm; }}
      @page {{ @bottom-right {{ content: "Page " counter(page) " of " counter(pages); }} }}
      * {{ box-sizing: border-box; }}
      html, body {{ margin: 0; }}
      body {{ font-family: system-ui, -apple-system, Arial, sans-serif; color: var(--rpt-ink); font-size: 11.5px; }}
      .rf-title {{ font-size: 19px; font-weight: 800; margin: 0 0 2px; color: var(--rpt-ink); }}
      .rf-sub {{ color: var(--rpt-ink-soft); font-size: 11px; margin-bottom: 2px; }}
      .rf-meta {{ color: var(--rpt-muted); font-size: 10px; margin-bottom: 10px; }}
      .rf-h2 {{ font-size: 13px; margin: 15px 0 7px; color: var(--rpt-ink);
                border-bottom: 2px solid var(--rpt-th-ink); padding-bottom: 3px; }}
      .rf-num {{ color: var(--rpt-accent); font-weight: 800; margin-right: 4px; }}
      .rf-section {{ break-inside: avoid-page; }}
      .rf-section:first-of-type .rf-h2 {{ margin-top: 6px; }}
      .rf-nodata {{ color: var(--rpt-muted); font-style: italic; font-size: 11px; padding: 4px 0; }}
      .rf-foot {{ margin-top: 14px; font-size: 9.5px; color: var(--rpt-muted); font-style: italic;
                  border-top: 1px solid var(--rpt-hair); padding-top: 6px; }}
      {spec.css}
    </style>{report_theme.theme_style_tag(theme)}</head><body>
      <div class="rf-title">{_e(spec.title)}</div>
      {sub}
      {meta}
      {sections}
      {foot}
    </body></html>'''
