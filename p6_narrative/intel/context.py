"""Schedule Intelligence — the shared, pre-computed context.

``build_context(data)`` walks an already-parsed :class:`ScheduleData` exactly once
and returns an :class:`IntelContext` that every later intelligence slice reads from.
Nothing here re-parses or re-computes the schedule: it only indexes what the parser
already produced (``p6_evm.parser`` / ``p6_evm.xer`` both yield the same activity-dict
shape) and wraps the existing :class:`p6_audit.graph.ScheduleGraph` for adjacency.

Everything is keyed on ``object_id`` — P6 exports can carry duplicate activity codes
(the ``id`` field), so ``id``/code are never used for uniqueness.

Pure and deterministic: identical input yields identical indices.
"""
import re

from p6_audit.graph import ScheduleGraph
from p6_narrative.util import wbs_grouping
from p6_narrative.sequence import pick_discipline_dim

# Milestones are kept aside as schedule *anchors* (start/finish markers), never steps.
_MILESTONE_TYPES = frozenset({'StartMilestone', 'FinishMilestone'})
# Not real construction "step" activities — dropped from ``steps`` entirely.
_NON_STEP_TYPES = frozenset({'StartMilestone', 'FinishMilestone', 'LOE', 'WBSSummary'})

_TOKEN_RE = re.compile(r'[A-Za-z]+|\d+')


def _tokenize(name):
    """Split an activity name into word / number tokens, once. Case preserved."""
    return _TOKEN_RE.findall(name or '')


class IntelContext:
    """Pre-computed, deterministic view over one parsed schedule.

    Attributes
    ----------
    data : ScheduleData
        The original parse (never mutated, never re-parsed).
    steps : dict[str, dict]
        Real "step" activities by object_id (task_type not milestone/LOE/summary).
    milestones : dict[str, dict]
        Milestone anchors by object_id (Start/Finish milestones).
    tokens : dict[str, list[str]]
        object_id -> name tokens (words + numbers), tokenized once.
    durations_days : dict[str, float]
        object_id -> planned duration in WORKING DAYS (raw hours / calendar day_hours).
    graph : ScheduleGraph
        Wrapped adjacency engine (already drops dangling relationships, object_id-keyed).
    forward / back : dict[str, list[str]]
        object_id -> successor / predecessor object_ids (from ``graph``).
    children_of_wbs : dict[str, list[str]]
        WBS object_id -> child WBS object_ids (schedule order of appearance).
    acts_by_wbs : dict[str, list[str]]
        WBS object_id -> step object_ids directly under that node.
    wbs_ancestors : dict[str, tuple[str, ...]]
        WBS object_id -> root-first ancestor chain (including itself).
    group_of / branch_ids : dict, list
        Adaptive WBS major-branch grouping (from ``util.wbs_grouping``).
    discipline_dim : str | None
        The Type-of-Works / discipline activity-code dimension, if the file has one.
    """

    __slots__ = (
        'data', 'steps', 'milestones', 'tokens', 'durations_days', 'graph',
        'forward', 'back', 'children_of_wbs', 'acts_by_wbs', 'wbs_ancestors',
        'group_of', 'branch_ids', 'discipline_dim',
    )

    def __init__(self, **kw):
        for name in self.__slots__:
            setattr(self, name, kw[name])

    # -- convenience accessors (thin, deterministic) -----------------------------
    def succ_ids(self, oid):
        """Successor object_ids of ``oid`` (empty list if none/unknown)."""
        return self.forward.get(oid, [])

    def pred_ids(self, oid):
        """Predecessor object_ids of ``oid`` (empty list if none/unknown)."""
        return self.back.get(oid, [])

    def ancestor_at_level(self, wbs_id, level):
        """The ancestor WBS id ``level`` steps below the root (0 = root), or None.

        Levels beyond the node's own depth clamp to the node itself is NOT done —
        out-of-range levels return None so callers can detect shallow branches.
        """
        chain = self.wbs_ancestors.get(wbs_id)
        if not chain or level < 0 or level >= len(chain):
            return None
        return chain[level]

    def wbs_depth_of(self, wbs_id):
        """Depth of a WBS node (root = 1), or 0 if unknown."""
        return len(self.wbs_ancestors.get(wbs_id, ()))


def _day_hours_for(data, act):
    cal = data.calendars.get(act.get('calendar_id'))
    dh = cal.day_hours if cal else 8.0
    return dh or 8.0


def _wbs_ancestor_chain(wbs_id, wbs):
    """Root-first ancestor ids for a WBS node, including itself. Cycle-guarded."""
    up = []
    seen = set()
    cur = wbs_id
    while cur and cur in wbs and cur not in seen:
        seen.add(cur)
        up.append(cur)
        cur = wbs[cur].get('parent_object_id')
    up.reverse()  # root first
    return tuple(up)


def build_context(data) -> IntelContext:
    """Index a parsed :class:`ScheduleData` into an :class:`IntelContext`.

    One deterministic pass. Filters steps vs. milestone anchors, converts raw-hour
    durations to working days, tokenizes names, and builds the WBS + adjacency
    indices. Never re-parses.
    """
    activities = data.activities
    wbs = data.wbs

    steps = {}
    milestones = {}
    tokens = {}
    durations_days = {}
    acts_by_wbs = {}

    for oid, act in activities.items():
        tt = act.get('task_type')
        tokens[oid] = _tokenize(act.get('name'))
        durations_days[oid] = (act.get('planned_duration') or 0.0) / _day_hours_for(data, act)
        if tt in _MILESTONE_TYPES:
            milestones[oid] = act
        if tt not in _NON_STEP_TYPES:
            steps[oid] = act
            acts_by_wbs.setdefault(act.get('wbs_id'), []).append(oid)

    # WBS tree indices
    children_of_wbs = {}
    for wid, node in wbs.items():
        parent = node.get('parent_object_id')
        if parent and parent in wbs:
            children_of_wbs.setdefault(parent, []).append(wid)
    wbs_ancestors = {wid: _wbs_ancestor_chain(wid, wbs) for wid in wbs}

    group_of, branch_ids = wbs_grouping(wbs) if wbs else ({}, [])
    discipline_dim = pick_discipline_dim(data.activity_code_types)

    # Adjacency — reuse the audit graph (drops dangling rels, object_id-keyed)
    graph = ScheduleGraph(data)
    forward = {oid: [e['other'] for e in graph.succs_of(oid)] for oid in activities}
    back = {oid: [e['other'] for e in graph.preds_of(oid)] for oid in activities}

    return IntelContext(
        data=data, steps=steps, milestones=milestones, tokens=tokens,
        durations_days=durations_days, graph=graph, forward=forward, back=back,
        children_of_wbs=children_of_wbs, acts_by_wbs=acts_by_wbs,
        wbs_ancestors=wbs_ancestors, group_of=group_of, branch_ids=branch_ids,
        discipline_dim=discipline_dim,
    )
