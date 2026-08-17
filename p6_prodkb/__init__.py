"""Productivity & Resource Knowledge Base engine (offline, rule-based).

Turns a quantity + an activity template into a duration and a typed resource load
(labor man-hours + MNP, equipment, material), selecting the calculation model per
activity. Sibling of ``p6_kb`` (which stays the source of truth for execution logic);
``p6_kb`` and ``p6_evm`` are never modified by this package.
"""
from p6_prodkb.calc import compute, DRIVERS
from p6_prodkb.kb import load_templates, by_id

__all__ = ["compute", "DRIVERS", "load_templates", "by_id"]
