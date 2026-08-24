"""Special Report — user-composed cross-feature report builder.

The user picks detailed results from any feature, orders them, names the report,
and exports it to PDF or Word (identical style). Special Report never recomputes
a metric a feature already produces — it only gathers and presents results.

Architecture: each feature ships a *provider* that returns catalog items whose
``produce(ctx)`` yields a structured **payload** (see :mod:`p6_special.payloads`).
One renderer turns any payload into themed HTML that drives screen preview, PDF
(Chrome) and Word alike. New features appear automatically via the registry's
auto-discovery — no Special Report code changes.
"""
