"""p6_report — the tool-wide Global Print-Preview / Reporting framework.

One reusable component registry + one assembler that Preview, PDF and Print all
consume, so what the user ticks in *Report Contents* is exactly what the preview
shows and exactly what the PDF contains — Preview == PDF == Print, never diverging.

Public surface:
    from p6_report import registry, render
    registry.register(feature, spec_builder)      # a feature contributes its report
    render.manifest(spec, report)                 # the selector's component list
    render.build_document(spec, report, selected_ids, order)   # the one document

Each feature registers a ``ReportSpec`` (title + CSS + an ordered list of
``ReportComponent``). A component names one reportable output — a table, a chart, a
summary, a findings list — with a ``render(report) -> html_fragment`` and an optional
``has_data(report)``. Adding a new module's report is just registering its spec; the
same Report-Contents selector, preview and PDF then work for it automatically.
"""
from p6_report import features as _features  # noqa: F401  (registers built-in specs)
from p6_report.registry import ReportComponent, ReportSpec, get_spec, register
from p6_report.render import build_document, manifest

__all__ = ['ReportComponent', 'ReportSpec', 'register', 'get_spec',
           'manifest', 'build_document']
