"""Productivity & Resource Intelligence — a browsable, evidence-graded knowledge base of
construction productivity norms.

A *norm* is a crew (resource) per unit of work — e.g. "1 t of column reinforcement needs
1 Steel Fixer + 1 Helper, 0.7 t/gang-day = 23 MH/t". Work items decompose into **components**
(RC column = formwork + reinforcement + concrete), each carrying its own norm, resources,
provenance and confidence. Given a quantity the engine converts norms to man-hours, crew and
an indicative duration; with no quantity it is a pure knowledge lookup.

Hard rules (mirrors the Constructability KB `p6_kb`):
- Never invent a rate, record, confidence or resource. A component with no evidence reports
  ``state == "no_reference"`` and no number.
- Context factors adjust a base rate ONLY where evidence exists; otherwise "not adjusted —
  insufficient evidence" (a literal x1.0 pass-through).
- Percentiles (P10/P50/P90) are shown only when enough validated records support them; below
  the threshold the honest range low/likely/high is used instead.

Additive to the app — never import or modify ``p6_evm``.
"""

from .kb import load_items, by_id, build_tree
from .engine import query, item_result, PERCENTILE_MIN_RECORDS

__all__ = ["load_items", "by_id", "build_tree", "query", "item_result", "PERCENTILE_MIN_RECORDS"]
