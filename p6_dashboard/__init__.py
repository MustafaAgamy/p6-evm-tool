"""
Professional Dashboard — a user-composed aggregation/visualisation layer.

This package is a *presentation* layer only. It never recomputes a metric that a
feature already produces: each feature exposes a **provider** that maps its own
results into dashboard components, and the dashboard renders whatever providers
are registered. Adding a future feature needs no change here — it registers a
provider (or ships a ``p6_<feature>/dashboard.py`` that :func:`registry.discover`
auto-imports) and its results appear in the catalog automatically.

Public surface:
  * ``registry.catalog(ctx)``  — every available component descriptor (no data)
  * ``registry.render(ctx, ids)`` — payloads for the selected component ids
  * ``context.DashboardContext`` — parse-free access to a project's stored results
"""

from . import registry, context  # noqa: F401
