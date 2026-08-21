"""Schedule Intelligence — structural decompositions measured from the file.

Three kinds of structure live here, so that every slice reads them from one place:

* **WBS subtrees** — :func:`subtree_steps` maps a WBS node to every step activity in its
  whole subtree (walked once, deepest-first, explicitly sorted).
* **Repetition** — :func:`repetition_stats` measures how deeply the file *actually*
  repeats: repeatable WBS siblings, and identical activity names. Analysis thresholds
  are derived from this, never from the activity count alone — two real baselines of 896
  and 2502 activities land in the same size class, yet one repeats 14 deep and the other
  6, so the size class cannot set the evidence bar.
* **Identifier decompositions** — :func:`id_segment_maps` (every delimited position of
  the activity ID) and :func:`name_affix_maps` (leading / trailing runs of name tokens).
  Both are only ever *candidates*: they are scored elsewhere, and no positional scheme is
  assumed. In real files the same position means different things — one file's ID
  position 1 is P6's sequence number (1000, 1010, 1020) and carries no grouping
  information at all.

Also here: :func:`step_links`, the step-to-step adjacency used by every cohesion and
logic measurement, computed once instead of per candidate partition.

Everything is keyed on ``object_id``. Activity *codes* (``act['id']``) are not unique in
P6 exports and are never used as identities. Pure, deterministic, no keyword lists.
"""
from collections import Counter

from p6_narrative.intel.common import median, uniq

# Activity-ID delimiters to probe (structure only — no project-specific strings).
DELIMS = ('-', '.', '_', '/', ':', '|', '#', ' ')
MAX_ID_SEGMENTS = 10
# How many leading/trailing name tokens may mark an instance.
MAX_AFFIX_TOKENS = 4
# A WBS child holding a single step is not a repeatable work front.
_MIN_SUBTREE_STEPS = 2


def subtree_steps(context):
    """WBS ``object_id`` -> step ``object_id``s in its whole subtree. Deterministic.

    Deepest-first so each parent simply concatenates its children's already-computed
    lists; duplicates cannot arise because a WBS node has one parent, but the walk is
    de-duplicated anyway to stay safe on malformed exports.
    """
    subtree = {}
    for wid in sorted(context.data.wbs, key=lambda w: (-context.wbs_depth_of(w), w)):
        own = list(context.acts_by_wbs.get(wid, []))
        for child in sorted(context.children_of_wbs.get(wid, [])):
            own.extend(subtree.get(child, []))
        subtree[wid] = uniq(own)
    return subtree


def repeatable_parents(context, subtree=None, min_children=2):
    """WBS parents whose children look like repeated instances of one template.

    A parent qualifies when at least ``min_children`` of its children hold two or more
    step activities in their subtree — the structural signature of "the same package
    done N times". Returns ``{parent_id: [child_id, ...]}`` with sorted children.
    """
    sub = subtree if subtree is not None else subtree_steps(context)
    out = {}
    for parent in sorted(context.children_of_wbs):
        kids = [k for k in sorted(context.children_of_wbs[parent])
                if len(sub.get(k, [])) >= _MIN_SUBTREE_STEPS]
        if len(kids) >= min_children:
            out[parent] = kids
    return out


def _name_key(context, oid):
    """Lower-cased token join of an activity name — a spelling-agnostic identity.

    Tokens, not the raw string, so punctuation and spacing differences do not split an
    otherwise identical name. No dictionary, no spell correction: a misspelling is simply
    its own key, exactly as the file wrote it.
    """
    return ' '.join(t.lower() for t in (context.tokens.get(oid) or []))


def repetition_stats(context):
    """Measure how much this schedule actually repeats. JSON-serialisable.

    Reported (over the *step* population — milestones/LOE/summary excluded):

    ``wbs_sibling_repeat_max`` / ``wbs_sibling_repeat_median``
        How many sibling instances the deepest / typical repeated WBS template carries.
    ``repeating_parents`` / ``steps_in_repeating_parents`` / ``wbs_repeat_share``
        How much of the schedule sits inside such a template.
    ``name_repeat_max`` / ``name_repeat_share``
        How often the *same activity name* recurs — the signal that is 14 deep in one
        real baseline and effectively absent in the next.
    ``deepest_repeat``
        The larger of the two maxima: the most instances any evidence in this file can
        supply, and therefore the highest instance count it is honest to demand.
    """
    sub = subtree_steps(context)
    parents = repeatable_parents(context, sub)
    counts = sorted(len(kids) for kids in parents.values())

    in_repeating = set()
    for kids in parents.values():
        for kid in kids:
            in_repeating.update(sub.get(kid, []))
    steps = set(context.steps)
    in_repeating &= steps
    n_steps = len(steps)

    name_counts = Counter(_name_key(context, oid) for oid in sorted(steps))
    name_counts.pop('', None)
    name_repeat_max = max(name_counts.values()) if name_counts else 0
    shared_named = sum(c for c in name_counts.values() if c >= 2)

    wbs_max = counts[-1] if counts else 0
    return {
        'steps': n_steps,
        'wbs_sibling_repeat_max': wbs_max,
        'wbs_sibling_repeat_median': round(median(counts), 4),
        'repeating_parents': len(parents),
        'steps_in_repeating_parents': len(in_repeating),
        'wbs_repeat_share': round(len(in_repeating) / float(n_steps), 4) if n_steps else 0.0,
        'name_repeat_max': name_repeat_max,
        'name_repeat_share': round(shared_named / float(n_steps), 4) if n_steps else 0.0,
        'distinct_name_keys': len(name_counts),
        'deepest_repeat': max(wbs_max, name_repeat_max),
    }


def step_links(context):
    """``object_id`` -> the set of *step* object_ids it is linked to, either direction.

    Computed once per analysis. Direction is deliberately dropped: every measurement
    built on this asks "is this activity wired to that one", never "which came first"
    (order comes from the topological pass, never from dates). Relationships to
    milestones / LOE / summary activities are excluded so a shared start milestone cannot
    make two unrelated fronts look internally cohesive.
    """
    steps = set(context.steps)
    links = {oid: set() for oid in steps}
    for oid in steps:
        for e in context.graph.succs_of(oid):
            other = e['other']
            if other in steps and other != oid:
                links[oid].add(other)
                links[other].add(oid)
        for e in context.graph.preds_of(oid):
            other = e['other']
            if other in steps and other != oid:
                links[oid].add(other)
                links[other].add(oid)
    return links


def id_segment_maps(context, oids, delims=DELIMS, max_segments=MAX_ID_SEGMENTS):
    """All plausible ``(delimiter, position)`` segmentations of the activity ID.

    Returns ``[(detail, {object_id: segment}), ...]``, sorted by construction. Real IDs
    are delimited, but the segment *count* varies inside one file, so every position is
    offered and scored rather than a fixed scheme being assumed.

    Positions are offered **per ID shape** (per segment count), never across shapes,
    because a fixed position only means the same thing inside one shape. On a real
    baseline whose building IDs carry one segment more than its fence IDs, position 4 is
    the trade code on the buildings and a bare running number on the fences; mixing the
    two produced the file's highest-confidence "repeated fronts" out of nine unrelated
    single activities. A file whose IDs all share one shape — the common case — is
    unaffected: it has exactly one shape class and the candidates are the same as before.
    """
    out = []
    activities = context.data.activities
    for delim in delims:
        split = {o: ((activities[o].get('id') or '').split(delim))
                 for o in oids if o in activities}
        widths = [len(p) for p in split.values()]
        if not widths or max(widths) < 2:
            continue                     # this delimiter does not occur at all
        shapes = {}
        for oid, parts in split.items():
            shapes.setdefault(len(parts), []).append(oid)
        for width in sorted(shapes):
            if width < 2:
                continue                 # undelimited ids carry no positional signal
            members = sorted(shapes[width])
            for pos in range(min(max_segments, width)):
                keys = {o: split[o][pos] for o in members if split[o][pos]}
                if keys:
                    out.append(('delim=%s,seg=%d,pos=%d' % (delim, width, pos), keys))
    return out


def name_affix_maps(context, oids, max_len=MAX_AFFIX_TOKENS):
    """Leading / trailing runs of name tokens — the instance marker baked into a name.

    Returns ``[(detail, {object_id: affix}), ...]``. At least one token is always left
    over for the step itself, so an affix can never swallow the whole name.
    """
    out = []
    for side in ('suffix', 'prefix'):
        for length in range(1, max_len + 1):
            keys = {}
            for oid in sorted(oids):
                toks = context.tokens.get(oid) or []
                if len(toks) <= length:
                    continue
                keys[oid] = ' '.join(toks[-length:] if side == 'suffix' else toks[:length])
            if keys:
                out.append(('%s,len=%d' % (side, length), keys))
    return out
