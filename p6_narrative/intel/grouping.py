"""Schedule Intelligence — the single source of truth for grouping activities.

Every slice that asks "what discipline is this activity?" or "what work-package is
it in?" comes here, so the answer is identical everywhere. The rules match the
existing sequence-chart logic (``p6_narrative.sequence``), now centralised:

  * **discipline** = the Type-of-Works / discipline activity-code value when the file
    carries such a dimension (``sequence.pick_discipline_dim``); otherwise the
    adaptive WBS *major branch* (``util.wbs_grouping`` — the children of a single
    root, so a one-root project still gets a real breakdown), falling back to the top
    WBS branch name, then ``'General'``.
  * **package** = the activity's own (leaf) WBS node name, falling back to ``'General'``.

Pure, deterministic, project-agnostic — no hardcoded discipline or sector names.
Reuses ``util`` and ``sequence`` rather than duplicating their logic.
"""
from collections import OrderedDict

from p6_narrative.util import top_wbs_name

_GENERAL = 'General'


def discipline_of(context, act):
    """Stable discipline label for one activity dict. Never empty."""
    dim = context.discipline_dim
    if dim:
        val = (act.get('activity_codes') or {}).get(dim)
        if val:
            return val
    wbs = context.data.wbs
    gid = context.group_of.get(act.get('wbs_id'))
    name = (wbs.get(gid) or {}).get('name')
    if name:
        return name
    return top_wbs_name(act.get('wbs_id'), wbs) or _GENERAL


def package_of(context, act):
    """Stable work-package label = the activity's leaf WBS node name. Never empty."""
    node = context.data.wbs.get(act.get('wbs_id')) or {}
    return node.get('name') or _GENERAL


def disciplines(context):
    """Partition the context's *steps* by discipline.

    Returns an ``OrderedDict`` ``discipline -> [object_id, ...]``, insertion order
    following the parse order of ``context.steps`` (deterministic).
    """
    out = OrderedDict()
    for oid, act in context.steps.items():
        out.setdefault(discipline_of(context, act), []).append(oid)
    return out


def packages(context):
    """Partition the context's *steps* by work-package (leaf WBS node)."""
    out = OrderedDict()
    for oid, act in context.steps.items():
        out.setdefault(package_of(context, act), []).append(oid)
    return out
