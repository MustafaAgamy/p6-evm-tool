"""Schedule Intelligence layer (Slice 1 foundation).

Deterministic, pure, project-agnostic indexing over an already-parsed schedule.
Nothing here re-parses or re-computes; it only reads what ``p6_evm`` produced and the
existing ``p6_audit``/``p6_narrative`` engines already offer.

Public API:
  * ``build_context(data)``          -> IntelContext   (one-pass index)
  * ``build_profile(context)``       -> dict           (JSON-serialisable fingerprint)
  * ``discipline_of`` / ``package_of`` / ``disciplines`` / ``packages``  (grouping)
"""
from p6_narrative.intel.context import IntelContext, build_context
from p6_narrative.intel.profile import build_profile
from p6_narrative.intel.grouping import (
    discipline_of, package_of, disciplines, packages,
)

__all__ = [
    'IntelContext', 'build_context', 'build_profile',
    'discipline_of', 'package_of', 'disciplines', 'packages',
]
