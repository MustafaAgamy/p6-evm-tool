"""Schedule Intelligence — repeated work-front detection (Slice 2).

``detect_repeats(context)`` finds **repeated work fronts** — 10 silos, the typical
building floor, road chainage segments, identical equipment trains, repeated bridge
spans — that share the same internal work sequence, so the narrative can say
*"repeated across N fronts; the typical sequence is A -> B -> C"* instead of printing
the same paragraph N times. **One logical scope = one narrative treatment.**

Grouping is deliberately **not** name equality; name equality is one signal among seven.
Real P6 files sit at opposite ends of the naming spectrum: one export repeats activity
names verbatim and puts the instance marker in the WBS node / activity ID, the next bakes
the instance into the name as a suffix so every name is unique. Both must work, so the
axis of repetition is *measured* from the file (WBS position, activity codes, ID
segmentation, name tokens) and scored, never assumed.

The engine, in order:

1. **Axis selection** — four candidate axes partition the step activities into
   comparably-sized *units* (work fronts). Every axis is scored on coverage, evenness,
   plurality, unit size and **internal logic cohesion**; the highest score wins, ties
   broken by the fixed order
   ``wbs_siblings`` > ``code_dimension`` > ``id_segment`` > ``name_token``. Every
   score is reported for traceability.
2. **Token classification** — each name token is corpus-constant (*noise*), constant
   within a unit but varying between units (*instance label* — the ``7`` in "Silo 7"),
   or varying within a unit (*step* token). A step key is the multiset of a step's
   step tokens; when names carry nothing repeatable the key falls back down the ladder
   name tokens -> discipline code -> leaf WBS node -> activity-ID segment.
3. **Unit fingerprint** — the set of step keys, the topological step order derived from
   the unit's *internal* relationships (cycle-safe, never from dates), the internal
   logic shape (relationship type + lag bucket), per-step working days **with the
   activity count behind them**, per-step cost, and the neighbourhood (what feeds the
   unit and what it feeds).
4. **Clustering** — union-find over units, joined when similarity (Jaccard on step-key
   sets plus order agreement) reaches ``params['sim_threshold']``, guarded so unrelated
   work never merges.
5. **Evidence** — each candidate group is scored on all seven signals, each weighted by
   how reliable that signal is *in this file* (``intel.signals``). A group needs at
   least two independent supporting signals to survive: no single signal, name equality
   included, can establish a work front on its own.
6. **Output** — the five-level hierarchy (activity -> family -> front -> typical
   sequence -> exception, see ``intel.hierarchy``), the dimension report (duplicate code
   dimensions collapsed, discipline dimension picked by measured coverage, location axis
   detected structurally), the signal report, and a **verified** coverage proof.

Pure, deterministic and JSON-serialisable — no datetimes, no sets, no tuple keys, and
every collection explicitly sorted so parse order can never leak into the result.
Everything is keyed on ``object_id``; a P6 export can carry the same activity *code*
twice, so codes are never identities.

Not covered by this slice, deliberately: **quantities and units do not exist in the
parsed data** (no resource table) and are never inferred — see
``intel.signals.quantity_signal``. Cost is reported under its own name only.
"""
import heapq
from collections import Counter

from p6_narrative.intel.common import (
    clamp01, median, modal, num, uniq,
)
from p6_narrative.intel.dimensions import (
    code_values_by_dimension, dimension_report, location_labels, select_location_axis,
)
from p6_narrative.intel.grouping import discipline_label, package_of
from p6_narrative.intel.hierarchy import (
    LEVEL_NAMES, assert_coverage, build_hierarchy, prove_coverage,
)
from p6_narrative.intel.profile import build_profile
from p6_narrative.intel.signals import (
    MIN_SIGNALS, SIGNAL_NAMES, cost_signal, evidence_block, group_support,
    measure_reliability, quantity_signal,
)
from p6_narrative.intel.structure import (
    id_segment_maps, name_affix_maps, repetition_stats, step_links, subtree_steps,
)
from p6_narrative.sequence import _start_key

SCHEMA_VERSION = 2

# Axis kinds, in tie-break priority order.
_AXIS_ORDER = ('wbs_siblings', 'code_dimension', 'id_segment', 'name_token')
# Step-key bases, in fallback-ladder order.
_BASIS_ORDER = ('name_tokens', 'discipline_code', 'wbs_leaf', 'id_segment')
_MAX_KEY_TOKENS = 8            # length guard: prose "milestone sentences" must not
#                                dominate a step key (real files carry such names)
_MIN_UNIT_MEAN = 2.0           # a unit averaging < 2 steps is not a work front
# Compute budget for outcome-based selection, counted in UNITS assembled (see
# :func:`_shortlist`), never in candidates. It bounds time, it does not bias the answer:
# the best-shaped candidate of every axis is assembled whatever the budget, so no axis can
# be silenced by it. Raising it costs seconds and changes nothing else.
_ASSEMBLE_UNIT_BUDGET = 2000

# Axis score weights (every term is in 0..1 and the weights sum to 1, so is the score).
# Cohesion carries real weight on purpose: the other four terms are all statistics of
# the partition's *shape*, and shape alone is symmetric under transposition — splitting
# a regular grid of fronts x trades by row scores exactly the same as splitting it by
# column. Only internal logic tells a work FRONT (a chain of different operations) from
# a TRADE bucket (the same operation repeated in parallel across fronts).
_W_COVERAGE, _W_EVENNESS, _W_PLURALITY, _W_SIZEFIT = 0.30, 0.15, 0.15, 0.10
_W_COHESION = 0.30
# Fingerprint similarity weights.
_W_JACCARD, _W_ORDER = 0.70, 0.30
# Step-key basis gates.
_BASIS_COVER_GATE, _BASIS_GATE = 0.99, 0.5
# Outlier sensitivity: 1.5x is the generic "half again as much" break point, applied to
# the PER-ACTIVITY value so a front holding two activities of a step is never reported as
# an outlier merely for holding two.
_OUTLIER_RATIO, _OUTLIER_MIN_DAYS = 1.5, 0.5
# Structural confidence weights (blended 50/50 with the evidence score).
_W_SIM, _W_INSTANCES, _W_COMPLETE = 0.50, 0.20, 0.30
_W_STRUCTURAL, _W_EVIDENCE = 0.50, 0.50


# ── 1. axis selection ───────────────────────────────────────────────────────
def _cohesion(units, links):
    """Share of covered steps that are driven by another step of their OWN unit.

    A work front is *internally sequential* — its first operation hands over to its
    second, which hands over to its third — so nearly every member has a predecessor or
    successor in the same unit. Transpose the same grid and the units instead hold one
    single operation repeated across every front, whose members are mutually parallel
    and carry no internal logic at all. That difference is what makes this term
    decisive, and it is read entirely from the file's own relationships (never dates,
    never names, never a word list).

    Relationship *direction* is irrelevant here, so ``links`` is symmetric; a unit of
    one member can have no internal logic and contributes only to the denominator.
    """
    total = connected = 0
    for u in units:
        members = u['members']
        if not members:
            continue
        total += len(members)
        if len(members) < 2:
            continue
        inside = set(members)
        for oid in members:
            if links.get(oid) and (links[oid] & inside):
                connected += 1
    return (connected / float(total)) if total else 0.0


def _score_partition(units, n_steps, min_instances, max_items, links):
    """Score how cleanly ``units`` partition the corpus into comparable work fronts.

    Five terms, each in 0..1: how much of the corpus is covered, how even the unit
    sizes are, whether there are enough units, whether a unit is a narratable size, and
    whether each unit is held together by its own internal logic.
    A partition whose units average fewer than two steps is not a set of work fronts at
    all (that is what a P6 sequence number looks like) and scores zero.
    """
    sizes = [len(u['members']) for u in units if u['members']]
    k = len(sizes)
    if k < min_instances or n_steps <= 0:
        return 0.0
    covered = sum(sizes)
    if covered <= 0:
        return 0.0
    mean = covered / float(k)
    if mean < _MIN_UNIT_MEAN:
        return 0.0
    coverage = covered / float(n_steps)
    mad = sum(abs(s - mean) for s in sizes) / float(k)
    evenness = max(0.0, 1.0 - mad / mean)
    plurality = min(1.0, k / float(2 * max(1, min_instances)))
    hi = float(max_items or 15)
    size_fit = 1.0 if mean <= hi else hi / mean
    cohesion = _cohesion(units, links)
    return round(_W_COVERAGE * coverage + _W_EVENNESS * evenness
                 + _W_PLURALITY * plurality + _W_SIZEFIT * size_fit
                 + _W_COHESION * cohesion, 6)


def _axis_wbs_siblings(context, min_instances, subtree):
    """Units = subtrees under the children of a common WBS parent.

    Families are claimed deepest-first so the finest real front wins (a building's
    floors rather than the whole building), and a family only counts when at least
    ``min_instances`` of its children still hold two or more unclaimed steps.
    The bucket is the parent's *name*, not its id: a repeated subtree template that
    recurs under several branches is the same repetition, which is exactly the signal
    real baselines carry. (WBS node names are not unique either — the same name can sit
    at two depths — which is why every *node* is still keyed on object_id.)
    """
    wbs = context.data.wbs
    candidates = []
    for parent, kids in context.children_of_wbs.items():
        if len(kids) < min_instances:
            continue
        if sum(1 for k in kids if len(subtree.get(k, [])) >= 2) < min_instances:
            continue
        candidates.append(parent)
    candidates.sort(key=lambda p: (-context.wbs_depth_of(p), p))

    units, claimed, families = [], set(), 0
    for parent in candidates:
        pending = []
        for kid in sorted(context.children_of_wbs.get(parent, [])):
            members = [o for o in subtree.get(kid, []) if o not in claimed]
            if members:
                pending.append((kid, members))
        if sum(1 for _, m in pending if len(m) >= 2) < min_instances:
            continue
        families += 1
        pname = (wbs.get(parent) or {}).get('name') or parent
        for kid, members in pending:
            claimed.update(members)
            units.append({
                'unit_id': 'wbs:%s' % kid,
                'unit_label': (wbs.get(kid) or {}).get('name') or kid,
                'bucket': 'wbs-parent:%s' % pname,
                'members': sorted(members),
                'wbs_parent_id': parent,
            })
    if not units:
        return []
    return [(units, 'families=%d' % families)]


def _units_from_keys(keys, kind, bucket):
    """Build units from an ``object_id -> unit value`` map. Explicitly sorted."""
    buckets = {}
    for oid, value in keys.items():
        buckets.setdefault(value, []).append(oid)
    return [{
        'unit_id': '%s:%s' % (kind, value),
        'unit_label': value,
        'bucket': bucket,
        'members': sorted(buckets[value]),
        'wbs_parent_id': None,
    } for value in sorted(buckets)]


def _axis_code_dimension(context, representatives):
    """Units = the values of one activity-code dimension.

    Only *representative* dimensions are offered: an exactly duplicated dimension would
    otherwise produce an identical partition twice and win the tie-break by name order.
    """
    out = []
    for dim in sorted(representatives):
        keys = {}
        for oid, act in context.steps.items():
            value = (act.get('activity_codes') or {}).get(dim)
            if value:
                keys[oid] = value
        if keys:
            out.append((_units_from_keys(keys, 'code', 'code-dim:%s' % dim), 'dim=%s' % dim))
    return out


def _axis_id_segment(context):
    """Units = one positional segment of the delimited activity ID."""
    oids = sorted(context.steps)
    return [(_units_from_keys(keys, 'id', 'id-seg:%s' % detail), detail)
            for detail, keys in id_segment_maps(context, oids)]


def _axis_name_token(context):
    """Units = a leading/trailing run of name tokens (the instance marker in the name)."""
    oids = sorted(context.steps)
    return [(_units_from_keys(keys, 'name', 'name-affix:%s' % detail), detail)
            for detail, keys in name_affix_maps(context, oids)]


def candidate_partitions(context, min_instances, max_items, links, subtree,
                         representatives):
    """Every partition on offer, each with its SHAPE score. Deterministic order.

    One row per ``(axis, detail)`` pair: ``axis`` / ``axis_rank`` / ``detail`` /
    ``units`` / ``shape_score``. Rows are emitted in axis tie-break order and then in
    ``detail`` order, so the enumeration itself never depends on dict iteration.

    Shape is the CHEAP filter, nothing more — see :func:`_judge` for what actually picks
    the winner. Keeping the enumeration public is deliberate: the selector and any
    measurement harness must look at exactly the same candidate set.
    """
    n_steps = len(context.steps)
    builders = {
        'wbs_siblings': lambda: _axis_wbs_siblings(context, min_instances, subtree),
        'code_dimension': lambda: _axis_code_dimension(context, representatives),
        'id_segment': lambda: _axis_id_segment(context),
        'name_token': lambda: _axis_name_token(context),
    }
    out = []
    for rank, name in enumerate(_AXIS_ORDER):
        rows = sorted(builders[name](), key=lambda t: t[1])
        for units, detail in rows:
            out.append({
                'axis': name,
                'axis_rank': rank,
                'detail': detail,
                'units': units,
                'shape_score': _score_partition(units, n_steps, min_instances,
                                                max_items, links),
            })
    return out


def _shape_scores(candidates):
    """Best shape score per axis — the traceability record, reported unchanged."""
    scores = {name: 0.0 for name in _AXIS_ORDER}
    for cand in candidates:
        if cand['shape_score'] > scores[cand['axis']]:
            scores[cand['axis']] = cand['shape_score']
    return scores


def _select_axis_by_shape(candidates):
    """The pre-outcome selector, kept for reference: highest shape score wins.

    No longer decides anything (see :func:`_judge`); retained because the shape score is
    still the shortlisting filter and this is the one place that documents what shape
    alone would have chosen.
    """
    best = []
    for cand in candidates:
        if cand['shape_score'] > 0.0:
            best.append((-cand['shape_score'], cand['axis_rank'], cand['axis'],
                         cand['detail'], cand['units']))
    if not best:
        return None, None, []
    # NOTE (measured, unresolved): this picks the axis by the SHAPE of its partition and
    # never by the OUTCOME. On a real baseline the highest-scoring code dimension is a
    # 6-value phase bucket that scores 0.7548 and then yields ZERO groups, while the
    # dimension a planner would call the work fronts (14 buildings, 1058 activities)
    # scores 0.6646 and loses. Two independent signals agree on ~13-14 building fronts,
    # so the answer is in the candidate set; the selector cannot see it because it judges
    # evenness and coverage rather than "does this actually explain the schedule as
    # repeated fronts".
    #
    # Two fixes have been tried here, measured, and REJECTED — recorded so they are not
    # re-invented:
    #
    # 1. A 2% evidence-priority tie-band. Measured worse: it hands the file to the WBS
    #    axis, which emits duplicate Approval/Submittal groups over the same fronts.
    # 2. Outcome-based selection scored by "sequence-explained work per treatment":
    #    assemble every shortlisted partition, discount each group by how far its
    #    consensus sits from one-activity-per-front-per-step, divide by the group count.
    #    The discount half WORKS and is worth reusing — it collapses every transposed
    #    answer (a 3-front trade bucket explaining 809 activities scores 9; a 102-front
    #    "Engineering" bucket explaining 2,416 scores 303) while leaving the real answers
    #    intact. Dividing by the group count, however, PAYS FOR LUMPING, and
    #    test_two_different_work_types_under_different_parents_are_never_merged caught it
    #    at once: two work types under different parents merged into one 3-front group.
    #    Rejected rather than patched around the failing fixture.
    #
    # What both attempts establish: the discount identifies a genuine work front, and the
    # missing piece is an anti-fragmentation term that is neither a division nor a weight.
    best.sort(key=lambda t: (t[0], t[1]))
    _, _, name, detail, units = best[0]
    return name, detail, units


def _select_axis_shape(context, prep, budget=None):
    """The validated baseline selector: the single best-shaped partition, assembled.

    This is the clean, pre-``_judge`` path — the axis with the highest shape score wins,
    and its partition is assembled once through the shared ``assemble`` closure. It is the
    default selector and the baseline every candidate rule is measured against. It does
    NOT use the rejected outcome scoring (:func:`_judge`); that path stays in the file for
    side-by-side measurement only and is never the default.

    Returns the same ``(axis, detail, units, shape_scores, outcomes, built)`` tuple as
    :func:`_select_axis`, so the public entry point is selector-agnostic.
    """
    candidates = candidate_partitions(
        context, prep['min_instances'], prep['max_items'], prep['links'],
        prep['subtree'], prep['dim_report']['representatives'])
    shape_scores = _shape_scores(candidates)
    axis, detail, units = _select_axis_by_shape(candidates)
    if axis is None:
        return None, None, [], shape_scores, [], None
    built = prep['assemble']([dict(u) for u in units])
    return axis, detail, built['units'], shape_scores, [], built


# ── 2. token classification + the step-key fallback ladder ──────────────────
def _informative(tokens, doc_count, limit):
    """The ``limit`` most *matchable* tokens of one name, independent of word order.

    A step key only earns its keep if it matches the same step in another front, so the
    tokens worth keeping are the ones that recur most across the corpus; ties are broken
    by the token text. The interim engine truncated in name order, which made the key
    depend on how the planner happened to word the name — not evidence of anything.
    Names that are really prose (real files carry contract sentences as activity names)
    contribute almost nothing here, because their words occur once and are already gone.
    """
    ranked = sorted(tokens, key=lambda t: (-doc_count.get(t, 0), t))
    return sorted(ranked[:limit])


def _classify_tokens(context, units):
    """Split every name token into noise / instance-label / step token.

    * *noise* — present in every activity of the corpus, so it discriminates nothing.
    * *instance label* — wherever it appears it appears in **all** of that unit's
      members, and it does not appear in every unit (the ``7`` in "Silo 7"). Only
      multi-member units carry within-unit evidence, so singleton units are ignored
      for this test.
    * *step token* — everything else that occurs in two or more activities (a token
      unique to one activity cannot signal repetition).
    """
    oids = sorted({o for u in units for o in u['members']})
    n = len(oids)
    per = {o: {t.lower() for t in (context.tokens.get(o) or [])} for o in oids}

    doc_count = Counter()
    for o in oids:
        doc_count.update(per[o])
    noise = {t for t, c in doc_count.items() if n and c == n}

    unit_any, unit_all = Counter(), Counter()
    n_units = 0
    for u in units:
        members = u['members']
        if len(members) < 2:
            continue
        n_units += 1
        sets = [per[o] for o in members]
        unit_any.update(set().union(*sets))
        unit_all.update(set.intersection(*sets))
    instance = {t for t in unit_any
                if unit_any[t] >= 1 and unit_any[t] == unit_all[t]
                and unit_any[t] < n_units and t not in noise}

    step_tokens = {}
    for o in oids:
        toks = uniq([t.lower() for t in (context.tokens.get(o) or [])])
        keep = [t for t in toks
                if t not in noise and t not in instance and doc_count[t] >= 2]
        step_tokens[o] = _informative(keep, doc_count, _MAX_KEY_TOKENS)
    return noise, instance, step_tokens, doc_count


def _basis_metrics(keys, units):
    """``(coverage, discrimination, alignment)`` of one step-key basis.

    * coverage — share of steps that get a non-empty key.
    * discrimination — does the key tell one step of a unit from another?
    * alignment — share of keyed steps whose key also occurs in another unit.
    """
    oids = [o for u in units for o in u['members']]
    if not oids:
        return 0.0, 0.0, 0.0
    keyed = [o for o in oids if keys.get(o)]
    coverage = len(keyed) / float(len(oids))
    ratios = []
    for u in units:
        members = [o for o in u['members'] if keys.get(o)]
        if members:
            ratios.append(len({keys[o] for o in members}) / float(len(members)))
    discrimination = (sum(ratios) / len(ratios)) if ratios else 0.0
    seen_in = {}
    for idx, u in enumerate(units):
        for o in u['members']:
            k = keys.get(o)
            if k:
                seen_in.setdefault(k, set()).add(idx)
    shared = sum(1 for o in keyed if len(seen_in[keys[o]]) >= 2)
    alignment = (shared / float(len(keyed))) if keyed else 0.0
    return coverage, discrimination, alignment


def _pick_step_keys(context, units, step_tokens):
    """Walk the fallback ladder and return ``(basis_name, detail, {oid: key})``.

    The first rung that covers every step, tells steps within a unit apart, *and*
    aligns across units is taken. If no rung clears the gates the best-scoring rung
    wins (ties broken by ladder order), so a schedule with meaningless names still
    produces step keys.
    """
    oids = sorted({o for u in units for o in u['members']})
    candidates = []

    candidates.append(('name_tokens', 'tokens',
                       {o: ' '.join(step_tokens.get(o) or []) for o in oids}))
    candidates.append(('discipline_code', 'discipline',
                       {o: discipline_label(context, context.steps[o])[0] for o in oids}))
    candidates.append(('wbs_leaf', 'wbs-node',
                       {o: package_of(context, context.steps[o]) for o in oids}))
    best_id = None
    for detail, keys in id_segment_maps(context, oids):
        cov, dis, ali = _basis_metrics(keys, units)
        score = 0.4 * ali + 0.3 * dis + 0.3 * cov
        if best_id is None or score > best_id[0] or (score == best_id[0]
                                                     and detail < best_id[1]):
            best_id = (score, detail, keys)
    if best_id is not None:
        candidates.append(('id_segment', best_id[1], best_id[2]))

    scored = []
    for rank, name in enumerate(_BASIS_ORDER):
        for cand_name, detail, keys in candidates:
            if cand_name != name:
                continue
            cov, dis, ali = _basis_metrics(keys, units)
            if cov >= _BASIS_COVER_GATE and dis >= _BASIS_GATE and ali >= _BASIS_GATE:
                return name, detail, keys
            scored.append((-(0.4 * ali + 0.3 * dis + 0.3 * cov), rank, name, detail, keys))
    if not scored:
        return None, None, {}
    scored.sort(key=lambda t: (t[0], t[1]))
    _, _, name, detail, keys = scored[0]
    return name, detail, keys


# ── 3. unit fingerprint ─────────────────────────────────────────────────────
def _lag_bucket(lag):
    if lag is None:
        return '0'
    if lag < 0:
        return '-'
    if lag > 0:
        return '+'
    return '0'


def _handoff_label(context, keys, oid):
    """Short factual label for an activity outside the unit that hands work over."""
    k = keys.get(oid)
    if k:
        return k
    act = context.data.activities.get(oid)
    if act:
        return package_of(context, act)
    return oid


def _first_ranks(order, keys):
    """step key -> its first (0-based) position in the unit's internal order."""
    ranks = {}
    for i, oid in enumerate(order):
        k = keys.get(oid)
        if k and k not in ranks:
            ranks[k] = i
    return ranks


def _norm_ranks(unit):
    """step key -> position normalised to 0..1 so units of different length compare."""
    span = max(1, len(unit['order']) - 1)
    return {k: v / float(span) for k, v in unit['ranks'].items()}


def _wbs_parent_name(context, unit):
    """The unit's WBS parent template name — its position in the breakdown.

    For the WBS axis this is the claimed parent; for every other axis it is the modal
    parent of its members' own WBS nodes, so the WBS signal still has something to say
    when the axis came from a code, an ID segment or a name affix.
    """
    wbs = context.data.wbs
    if unit.get('wbs_parent_id'):
        return (wbs.get(unit['wbs_parent_id']) or {}).get('name') or ''
    names = []
    for oid in unit['members']:
        wid = (context.data.activities.get(oid) or {}).get('wbs_id')
        chain = context.wbs_ancestors.get(wid) or ()
        if len(chain) >= 2:
            names.append((wbs.get(chain[-2]) or {}).get('name') or '')
        elif chain:
            names.append((wbs.get(chain[-1]) or {}).get('name') or '')
    return modal(names) or ''


def _fingerprint(context, unit, keys, cost_by_activity):
    """Step keys, internal order, logic shape, per-step days/cost and neighbourhood.

    ``duration_days`` is the per-step **total** and ``duration_count`` the number of
    activities behind it, kept apart on purpose: the interim engine summed working days
    per step key, so a front holding two activities of one step reported twice the
    duration of a front holding one and then tripped the "duration outlier" test on an
    activity-count difference rather than on genuinely longer work.
    """
    members = unit['members']
    inside = set(members)
    edges, pairs = [], set()
    for pred in members:
        for e in context.graph.succs_of(pred):
            succ = e['other']
            if succ in inside:
                edges.append((pred, succ, e.get('type') or 'FS',
                              e.get('lag_days') or 0.0))
                if pred != succ:
                    pairs.add((pred, succ))

    indeg = {o: 0 for o in members}
    succs = {o: [] for o in members}
    for pred, succ in sorted(pairs):
        succs[pred].append(succ)
        indeg[succ] += 1
    has_internal_pred = {o: indeg[o] > 0 for o in members}
    has_internal_succ = {o: bool(succs[o]) for o in members}

    def sortkey(oid):
        return (keys.get(oid) or '', oid)

    heap = [(sortkey(o), o) for o in members if indeg[o] == 0]
    heapq.heapify(heap)
    order, placed = [], set()
    while heap:
        _, oid = heapq.heappop(heap)
        order.append(oid)
        placed.add(oid)
        for succ in sorted(set(succs[oid])):
            indeg[succ] -= 1
            if indeg[succ] == 0:
                heapq.heappush(heap, (sortkey(succ), succ))
    cyclic = len(order) < len(members)
    if cyclic:                       # a logic cycle: emit the rest deterministically
        order.extend(sorted((o for o in members if o not in placed), key=sortkey))

    shape = Counter('%s%s' % (t, _lag_bucket(lag)) for _, _, t, lag in edges)

    duration_days, duration_count = {}, {}
    cost_total, cost_count = {}, {}
    for oid in members:
        k = keys.get(oid)
        if not k:
            continue
        duration_days[k] = round(duration_days.get(k, 0.0)
                                 + (context.durations_days.get(oid) or 0.0), 4)
        duration_count[k] = duration_count.get(k, 0) + 1
        cost = cost_by_activity.get(oid) or 0.0
        if cost:
            cost_total[k] = round(cost_total.get(k, 0.0) + cost, 4)
            cost_count[k] = cost_count.get(k, 0) + 1

    externals_in, externals_out = set(), set()
    for oid in members:
        for e in context.graph.preds_of(oid):
            other = e['other']
            if other not in inside:
                externals_in.add(_handoff_label(context, keys, other))
        for e in context.graph.succs_of(oid):
            other = e['other']
            if other not in inside:
                externals_out.add(_handoff_label(context, keys, other))

    starts = [context.data.activities[o].get('planned_start') for o in members
              if o in context.data.activities and context.data.activities[o].get('planned_start')]
    unit['order'] = order
    unit['cyclic'] = cyclic
    unit['step_keys'] = sorted({keys[o] for o in members if keys.get(o)})
    unit['ranks'] = _first_ranks(order, keys)
    unit['shape'] = dict(shape)
    unit['duration_days'] = duration_days
    unit['duration_count'] = duration_count
    unit['cost_total'] = cost_total
    unit['cost_count'] = cost_count
    unit['externals_in'] = tuple(sorted(externals_in))
    unit['externals_out'] = tuple(sorted(externals_out))
    unit['neighbour_labels'] = (['in:%s' % x for x in sorted(externals_in)]
                                + ['out:%s' % x for x in sorted(externals_out)])
    unit['entry'] = sorted(o for o in members if not has_internal_pred[o]) or sorted(members)
    unit['exit'] = sorted(o for o in members if not has_internal_succ[o]) or sorted(members)
    unit['wbs_parent_name'] = _wbs_parent_name(context, unit)
    unit['min_start'] = min(starts) if starts else None
    return unit


# ── 4. clustering ───────────────────────────────────────────────────────────
def _make_metrics():
    """Memoised pairwise fingerprint comparison — one implementation, shared.

    ``jaccard`` on the step-key sets, ``order`` agreement over the keys both units carry
    (concordant pair fraction, so it is invariant to unit length), and the blended
    ``similarity`` the clustering threshold applies. Symmetric and cached, so the
    evidence layer re-reads exactly the numbers the clustering acted on.

    ``order`` is 1.0 when fewer than two keys are shared — there is nothing to disagree
    about. That cannot inflate anything on its own: ``similarity`` is 0 when the key sets
    are disjoint, and the ``logic`` signal is scored 0 unless some front really has
    internal relationships.
    """
    cache = {}

    def metrics(a, b):
        ka, kb = a['unit_id'], b['unit_id']
        key = (ka, kb) if ka <= kb else (kb, ka)
        hit = cache.get(key)
        if hit is not None:
            return hit
        sa, sb = set(a['step_keys']), set(b['step_keys'])
        union = sa | sb
        if not union:
            out = {'jaccard': 0.0, 'order': 0.0, 'similarity': 0.0}
            cache[key] = out
            return out
        jac = len(sa & sb) / float(len(union))
        shared = sorted(sa & sb)
        if len(shared) < 2:
            order = 1.0
        else:
            ra, rb = a['ranks'], b['ranks']
            total = concordant = 0
            for i in range(len(shared)):
                for j in range(i + 1, len(shared)):
                    x, y = shared[i], shared[j]
                    total += 1
                    if (ra[x] - ra[y]) * (rb[x] - rb[y]) > 0:
                        concordant += 1
                    elif ra[x] == ra[y] and rb[x] == rb[y]:
                        concordant += 1
            order = (concordant / float(total)) if total else 1.0
        sim = 0.0 if jac <= 0.0 else round(_W_JACCARD * jac + _W_ORDER * order, 6)
        out = {'jaccard': round(jac, 6), 'order': round(order, 6), 'similarity': sim}
        cache[key] = out
        return out

    return metrics


def _compatible(a, b):
    """Guardrail: may these two units be compared at all?

    Units must share the axis bucket (always structural). The discipline label is only
    allowed to *veto* when both units derive it from the same basis: on a file whose best
    code dimension covers half the schedule, the other half is labelled from its WBS
    branch instead, and comparing a code label against a WBS-branch label is comparing
    two different things — that mixed-basis comparison is what used to split real groups
    in half. When the bases differ the bucket alone guards the merge.
    """
    if a['bucket'] != b['bucket']:
        return False
    if a['discipline_basis'] == b['discipline_basis']:
        return a['discipline'] == b['discipline']
    return True


def _cluster(units, threshold, metrics):
    """Union-find over units; only compatible units sharing a step key are compared.

    Union-find makes the merge relation the transitive closure of the pairwise test, so
    the result is independent of comparison order. Candidate pairs come from an inverted
    step-key index: units sharing no step key have Jaccard 0 and therefore similarity 0,
    so skipping them cannot change the outcome — it only avoids the quadratic blow-up on
    an axis with hundreds of units.
    """
    parent = {u['unit_id']: u['unit_id'] for u in units}
    by_id = {u['unit_id']: u for u in units}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        lo, hi = (ra, rb) if ra <= rb else (rb, ra)
        parent[hi] = lo

    buckets = {}
    for u in units:
        buckets.setdefault(u['bucket'], []).append(u['unit_id'])

    pairs = set()
    for bucket in sorted(buckets):
        members = sorted(buckets[bucket])
        index = {}
        for uid in members:
            for key in by_id[uid]['step_keys']:
                index.setdefault(key, []).append(uid)
        for key in sorted(index):
            ids = sorted(index[key])
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    pairs.add((ids[i], ids[j]))

    sims = {}
    for ka, kb in sorted(pairs):
        a, b = by_id[ka], by_id[kb]
        if not _compatible(a, b):
            continue
        sim = metrics(a, b)['similarity']
        sims[(ka, kb)] = sim
        if sim >= threshold:
            union(ka, kb)

    components = {}
    for u in units:
        components.setdefault(find(u['unit_id']), []).append(u['unit_id'])
    return components, sims


def _sim_lookup(sims):
    """Symmetric similarity reader; a pair that was never compared has similarity 0."""
    def sim(a, b):
        if a == b:
            return 1.0
        return sims.get((a, b), sims.get((b, a), 0.0))
    return sim


def _refine_component(member_ids, threshold, sim):
    """Split one connected component into clusters that are COHESIVE, not merely linked.

    Union-find makes membership transitive, and transitivity is the wrong answer to this
    question. Front A can resemble B, B resemble C, and A not resemble C at all — on a
    real baseline that chained 27 different trades into a single "repeated front" whose
    own mean pairwise similarity sat *below* the bar that admitted any one pair. A planner
    reading that group is told the same work repeats 27 times when in truth 27 different
    trades each happen once.

    So a cluster is emitted only when the WHOLE cluster clears the same
    ``sim_threshold`` that admits a pair — no second constant is introduced. Merging is
    agglomerative average-linkage: start one cluster per unit, repeatedly join the closest
    pair, refuse any join whose merged cluster would fall below the bar. Whatever cannot
    be joined stays on its own and, being under ``min_instances``, falls through to the
    singleton list, so coverage is untouched.

    Sums are carried incrementally, so a component of a few hundred units costs cubic
    cheap arithmetic rather than cubic similarity evaluations. Ties break on the members'
    own sorted ids, so the outcome never depends on iteration order.
    """
    clusters = [(m,) for m in sorted(member_ids)]
    internal = {c: 0.0 for c in clusters}
    cross = {}
    for i, a in enumerate(clusters):
        for b in clusters[i + 1:]:
            cross[(a, b)] = sim(a[0], b[0])

    while len(clusters) > 1:
        best = None
        for i, a in enumerate(clusters):
            for b in clusters[i + 1:]:
                joined = internal[a] + internal[b] + cross[(a, b)]
                size = len(a) + len(b)
                if joined / (size * (size - 1) / 2.0) < threshold:
                    continue
                link = cross[(a, b)] / float(len(a) * len(b))
                key = (-round(link, 9), a[0], b[0])
                if best is None or key < best[0]:
                    best = (key, a, b, joined)
        if best is None:
            break
        _, a, b, joined = best
        merged = tuple(sorted(a + b))
        rest = [c for c in clusters if c != a and c != b]
        for c in rest:
            pair = (merged, c) if merged < c else (c, merged)
            cross[pair] = (cross.get((a, c), cross.get((c, a), 0.0))
                           + cross.get((b, c), cross.get((c, b), 0.0)))
        internal[merged] = joined
        clusters = sorted(rest + [merged])

    return [list(c) for c in sorted(clusters)]


def _cohesive_components(components, sims, threshold):
    """Refine every component so no emitted group is a chain; report what was split."""
    sim = _sim_lookup(sims)
    out, splits = {}, []
    for root in sorted(components):
        member_ids = sorted(components[root])
        if len(member_ids) < 3:
            out[root] = member_ids
            continue
        parts = _refine_component(member_ids, threshold, sim)
        if len(parts) == 1:
            out[root] = member_ids
            continue
        n = len(member_ids)
        mean_before = (sum(sim(member_ids[i], member_ids[j])
                           for i in range(n) for j in range(i + 1, n))
                       / (n * (n - 1) / 2.0))
        splits.append({
            'front_ids': member_ids,
            'mean_similarity': round(mean_before, 4),
            'threshold': round(threshold, 4),
            'split_into': [sorted(p) for p in parts],
            'reason': ('linked only through intermediate fronts — the whole set averages '
                       '%.4f similarity, below the %.2f needed to call it one repeated '
                       'work front' % (mean_before, threshold)),
        })
        for part in parts:
            out['%s|%s' % (root, part[0])] = sorted(part)
    return out, splits


# ── 5. output assembly ──────────────────────────────────────────────────────
def _compact_shape(shape):
    if not shape:
        return 'none'
    return ','.join('%sx%d' % (k, shape[k]) for k in sorted(shape))


def _display_tokens(context, member_oids, wanted):
    """Render lower-cased label tokens back in the file's own casing."""
    casing = {}
    for oid in member_oids:
        for tok in (context.tokens.get(oid) or []):
            casing.setdefault(tok.lower(), tok)
    return [casing.get(t, t) for t in wanted]


def _group_label(context, member_oids, instance_tokens, noise_tokens, wbs_parent_id,
                 discipline):
    """Label from the tokens a MAJORITY of members share. Never a hardcoded word.

    The interim rule intersected the tokens of every member, which on a large group is
    almost always empty — one oddly-named activity was enough to lose the label — so it
    silently fell through to the WBS node name. A strict majority is robust to that and
    still entirely file-derived. Instance tokens are excluded (they name one front, not
    the group) and so are corpus-constant *noise* tokens: a token every activity in the
    file carries is identical for every group and therefore cannot identify this one.

    Token order follows the median position the token holds inside the names it appears
    in, so the label reads the way the file writes it. ``label_source`` is reported
    alongside, so a fallback to the WBS parent node or the discipline is visible rather
    than silent.
    """
    n = len(member_oids)
    counts, positions = Counter(), {}
    for oid in member_oids:
        toks = uniq([t.lower() for t in (context.tokens.get(oid) or [])])
        for i, tok in enumerate(toks):
            counts[tok] += 1
            positions.setdefault(tok, []).append(i)
    keep = [t for t in counts
            if t not in instance_tokens and t not in noise_tokens and counts[t] * 2 > n]
    if keep:
        keep.sort(key=lambda t: (median(positions[t]), -counts[t], t))
        label = ' '.join(_display_tokens(context, member_oids, keep))
        if label:
            return label, 'shared_tokens'
    node = (context.data.wbs.get(wbs_parent_id) or {}).get('name')
    if node:
        return node, 'wbs_parent'
    return discipline, 'discipline'


def _exc(kind, detail, activity_ids, step, evidence, front):
    return {
        'kind': kind,
        'detail': detail,
        'step': step,
        'front_id': front['unit_id'],
        'front_label': front['unit_label'],
        'evidence': evidence,
        'activity_ids': sorted(activity_ids),
    }


def _front_exceptions(unit, keys, consensus, med_days, med_cost, ids_by_key,
                      modal_shape, modal_in, modal_out):
    """Level 5 — every way this front differs from the typical sequence.

    Each exception carries the object_ids it refers to so it stays traceable to the
    underlying activities. A *missing* step has no activities in this front, so it is
    evidenced by the activities that perform it in the other fronts
    (``evidence='other_fronts'``); everything else is evidenced by this front's own.
    """
    out = []
    own_keys = set(unit['step_keys'])
    own_by_key = {}
    for oid in unit['order']:
        k = keys.get(oid)
        if k:
            own_by_key.setdefault(k, []).append(oid)

    for key in consensus:
        if key not in own_keys:
            others = [o for o in ids_by_key.get(key, []) if o not in unit['order']]
            out.append(_exc('missing_step', 'missing step: %s' % key,
                            others or list(unit['order']), key, 'other_fronts', unit))
    for key in sorted(own_keys - set(consensus)):
        out.append(_exc('extra_step', 'extra step: %s' % key,
                        own_by_key.get(key, []), key, 'front', unit))

    for key in consensus:
        if key not in unit['duration_days']:
            continue
        count = unit['duration_count'].get(key) or 1
        per_act = unit['duration_days'][key] / float(count)
        med = med_days.get(key, 0.0)
        if med <= 0 or abs(per_act - med) < _OUTLIER_MIN_DAYS:
            continue
        if per_act >= med * _OUTLIER_RATIO or per_act <= med / _OUTLIER_RATIO:
            out.append(_exc('duration_outlier',
                            'duration outlier: %s %s d vs typical %s d'
                            % (key, num(per_act), num(med)),
                            own_by_key.get(key, []), key, 'front', unit))

    for key in consensus:
        med = med_cost.get(key, 0.0)
        if med <= 0 or key not in unit['cost_total']:
            continue
        count = unit['cost_count'].get(key) or 1
        per_act = unit['cost_total'][key] / float(count)
        if per_act >= med * _OUTLIER_RATIO or per_act <= med / _OUTLIER_RATIO:
            out.append(_exc('cost_outlier',
                            'cost outlier: %s %s vs typical %s'
                            % (key, num(per_act), num(med)),
                            own_by_key.get(key, []), key, 'front', unit))

    if modal_shape is not None and unit['shape'] != modal_shape:
        out.append(_exc('internal_logic', 'internal logic %s vs typical %s'
                        % (_compact_shape(unit['shape']), _compact_shape(modal_shape)),
                        unit['order'], None, 'front', unit))
    for label, own, typical, ids in (
            ('predecessor', unit['externals_in'], modal_in, unit['entry']),
            ('successor', unit['externals_out'], modal_out, unit['exit'])):
        if typical is None or own == typical:
            continue
        diff = sorted(set(own) ^ set(typical))
        if not diff:
            continue
        shown = ', '.join(diff[:3])
        if len(diff) > 3:
            shown += ' (+%d more)' % (len(diff) - 3)
        out.append(_exc('different_%s_handoff' % label,
                        'different %s hand-off: %s' % (label, shown),
                        ids, None, 'front', unit))
    if unit.get('cyclic'):
        out.append(_exc('logic_cycle', 'internal logic contains a cycle',
                        unit['order'], None, 'front', unit))
    out.sort(key=lambda e: (e['detail'], e['kind']))
    return out


def _build_group(context, members, metrics, min_instances, keys, instance_tokens,
                 noise_tokens, code_values, location_of, reliability):
    """Assemble one repeat group: levels 2-5, its evidence, and its confidence."""
    fronts = sorted(members, key=lambda u: (_start_key(u['min_start']), u['unit_id']))
    n = len(fronts)

    counts, ranks = Counter(), {}
    per_act_days, total_days, per_act_cost, ids_by_key = {}, {}, {}, {}
    for u in fronts:
        norm = _norm_ranks(u)
        for key in u['step_keys']:
            counts[key] += 1
            ranks.setdefault(key, []).append(norm.get(key, 1.0))
        for key in sorted(u['duration_days']):
            cnt = u['duration_count'].get(key) or 1
            per_act_days.setdefault(key, []).append(u['duration_days'][key] / float(cnt))
            total_days.setdefault(key, []).append(u['duration_days'][key])
        for key in sorted(u['cost_total']):
            cnt = u['cost_count'].get(key) or 1
            per_act_cost.setdefault(key, []).append(u['cost_total'][key] / float(cnt))
        for oid in u['order']:
            k = keys.get(oid)
            if k:
                ids_by_key.setdefault(k, []).append(oid)

    med_days = {k: round(median(per_act_days.get(k, [0.0])), 4) for k in counts}
    med_total = {k: round(median(total_days.get(k, [0.0])), 4) for k in counts}
    med_cost = {k: round(median(per_act_cost.get(k, [0.0])), 4) for k in counts}

    consensus_keys = [k for k in counts if counts[k] * 2 >= n]
    consensus_keys.sort(key=lambda k: (median(ranks[k]), -counts[k], k))
    consensus_set = set(consensus_keys)
    family_keys = sorted(counts, key=lambda k: (median(ranks[k]), -counts[k], k))

    families = []
    for idx, key in enumerate(family_keys):
        ids = sorted(ids_by_key.get(key, []))
        families.append({
            'family_index': idx,
            'family_id': None,
            'step': key,
            'label': key,
            'activity_ids': ids,
            'activity_count': len(ids),
            'front_count': counts[key],
            'median_days': med_days[key],
            'median_total_days': med_total[key],
            'median_cost': med_cost[key],
            'in_typical_sequence': key in consensus_set,
        })

    typical_sequence = [{
        'step': key,
        'family_id': None,
        'median_days': med_days[key],
        'median_total_days': med_total[key],
        'median_cost': med_cost[key],
        'fronts': counts[key],
        'instances': counts[key],           # back-compat alias of ``fronts``
        'activity_count': len(ids_by_key.get(key, [])),
    } for key in consensus_keys]

    modal_shape = modal([tuple(sorted(u['shape'].items())) for u in fronts])
    modal_shape = dict(modal_shape) if modal_shape is not None else None
    modal_in = modal([u['externals_in'] for u in fronts])
    modal_out = modal([u['externals_out'] for u in fronts])

    front_rows, all_exceptions = [], []
    for u in fronts:
        exceptions = _front_exceptions(u, keys, consensus_keys, med_days, med_cost,
                                       ids_by_key, modal_shape, modal_in, modal_out)
        all_exceptions.extend(exceptions)
        front_rows.append({
            'front_id': u['unit_id'],
            'unit_id': u['unit_id'],
            'unit_label': u['unit_label'],
            'wbs_parent_name': u['wbs_parent_name'],
            'activity_ids': list(u['order']),
            'steps': [(keys.get(o) or '') for o in u['order']],
            'step_keys': list(u['step_keys']),
            'family_ids': [],
            'cyclic': bool(u['cyclic']),
            'deviations': sorted(e['detail'] for e in exceptions),
            'exceptions': exceptions,
        })

    member_oids = [o for u in fronts for o in u['order']]
    discipline = modal([u['discipline'] for u in fronts])
    bases = {u['discipline_basis'] for u in fronts}
    parents = {u['wbs_parent_id'] for u in fronts}
    wbs_parent_id = parents.pop() if len(parents) == 1 else None
    label, label_source = _group_label(context, member_oids, instance_tokens,
                                       noise_tokens, wbs_parent_id, discipline)

    pair_sims = []
    for i in range(n):
        for j in range(i + 1, n):
            pair_sims.append(metrics(fronts[i], fronts[j])['similarity'])
    mean_sim = (sum(pair_sims) / len(pair_sims)) if pair_sims else 0.0
    completeness = ((sum(counts[k] for k in consensus_keys) / float(n * len(consensus_keys)))
                    if consensus_keys else 0.0)
    inst_factor = min(1.0, n / float(2 * max(1, min_instances)))
    structural = (_W_SIM * mean_sim + _W_INSTANCES * inst_factor
                  + _W_COMPLETE * completeness)

    supports = group_support(fronts, code_values, location_of, metrics)
    evidence = evidence_block(reliability, supports)
    confidence = round(clamp01(_W_STRUCTURAL * structural
                               + _W_EVIDENCE * evidence['score']), 4)

    return {
        'group_id': None,
        'label': label,
        'label_source': label_source,
        'front_count': n,
        'instance_count': n,                # back-compat alias of ``front_count``
        'activity_count': len(member_oids),
        'family_count': len(families),
        'discipline': discipline,
        'discipline_basis': bases.pop() if len(bases) == 1 else 'mixed',
        'wbs_parent_id': wbs_parent_id,
        'confidence': confidence,
        'structural_score': round(clamp01(structural), 4),
        'mean_similarity': round(mean_sim, 4),
        'evidence': evidence,
        'families': families,
        'typical_sequence': typical_sequence,
        'consensus_sequence': typical_sequence,   # back-compat alias
        'fronts': front_rows,
        'instances': front_rows,                  # back-compat alias of ``fronts``
        'exceptions': all_exceptions,
    }


def _stamp_ids(groups):
    """Assign the stable public ids once the group order is final."""
    for index, group in enumerate(groups):
        gid = 'grp%d' % (index + 1)
        group['group_id'] = gid
        family_id = {}
        for fam in group['families']:
            fam['family_id'] = '%s.fam%d' % (gid, fam.pop('family_index'))
            family_id[fam['step']] = fam['family_id']
        order = [fam['step'] for fam in group['families']]
        for step in group['typical_sequence']:
            step['family_id'] = family_id.get(step['step'])
        for front in group['fronts']:
            own = set(front['step_keys'])
            front['family_ids'] = [family_id[k] for k in order if k in own]
        for exc in group['exceptions']:
            exc['family_id'] = family_id.get(exc.get('step'))
    return groups


def prepare(context, params=None):
    """Compute everything every candidate partition shares, once, and return it.

    The outcome-based selector has to build *finished groups* for several partitions
    before it can judge any of them, so the expensive per-file facts (code-dimension
    de-duplication, discipline labels, the location axis, step links, repetition) must
    not be recomputed per candidate. They are measured here once and closed over by the
    single ``assemble(units)`` callable that both the selector and the final output run
    through — so a partition can never be judged by one code path and reported by
    another.

    Returns a dict of the measured facts plus ``assemble``. Public because the
    measurement harness that chose the judging rule must see exactly what the engine
    sees.
    """
    profile = build_profile(context)
    if params is None:
        params = profile['params']
    params = dict(params)
    min_instances = max(2, int(params.get('min_instances') or 2))
    threshold = float(params.get('sim_threshold') or 0.55)
    max_items = int(params.get('max_chart_items') or 15)

    n_steps = len(context.steps)
    steps_sorted = sorted(context.steps)
    links = step_links(context)
    subtree = subtree_steps(context)
    repetition = profile.get('repetition') or repetition_stats(context)

    # -- dimensions: de-duplicate, pick the discipline axis, find the location axis --
    dim_report = dimension_report(context)
    discipline_dim = dim_report['discipline']['selected']
    disc_pairs = {o: discipline_label(context, context.steps[o]) for o in steps_sorted}
    discipline_labels = {o: v[0] for o, v in disc_pairs.items()}
    location_axis, location_candidates = select_location_axis(
        context, discipline_labels, dim_report, discipline_dim)
    location_of = location_labels(context, location_axis)

    usable_dims = {s['dimension'] for s in dim_report['stats'] if s['usable']}
    class_reps = [c['representative'] for c in dim_report['classes']
                  if c['representative'] in usable_dims]
    code_values = code_values_by_dimension(context, class_reps, steps_sorted)
    cover_by_dim = {s['dimension']: s['coverage'] for s in dim_report['stats']}
    code_coverages = [cover_by_dim[d] for d in sorted(class_reps)]
    cost_by_activity = context.data.bac_by_activity or {}

    def assemble(units):
        """Run identity -> fingerprints -> clustering -> groups for one partition."""
        groups, rejected, in_group, chain_splits = [], [], set(), []
        basis = basis_detail = None
        keys = {}
        reliability = measure_reliability(context, units, {}, links, repetition,
                                          code_coverages, location_axis)
        if units:
            noise_tokens, instance_tokens, step_tokens, _ = _classify_tokens(context, units)
            basis, basis_detail, keys = _pick_step_keys(context, units, step_tokens)
            for u in units:
                labels = [disc_pairs[o] for o in u['members'] if o in disc_pairs]
                u['discipline'] = modal([lab for lab, _ in labels])
                u['discipline_basis'] = modal([b for _, b in labels]) or 'wbs'
                _fingerprint(context, u, keys, cost_by_activity)
            reliability = measure_reliability(context, units, keys, links, repetition,
                                              code_coverages, location_axis)
            metrics = _make_metrics()
            components, _sims = _cluster(units, threshold, metrics)
            components, chain_splits = _cohesive_components(components, _sims, threshold)
            by_id = {u['unit_id']: u for u in units}
            for root in sorted(components):
                member_ids = sorted(components[root])
                if len(member_ids) < min_instances:
                    continue
                members = [by_id[m] for m in member_ids]
                # A set of one-activity units is not a set of work fronts, whatever the axis
                # thinks: a front is a sequence of operations, so it holds more than one step.
                # The axis-level guard reads the average over ALL units, which a handful of
                # thin units hides; this reads the group actually about to be emitted. On a
                # real file this is what separates a repeated front from activities merely
                # individuated by a trailing P6 sequence number.
                unit_mean = sum(len(u['members']) for u in members) / float(len(members))
                if unit_mean < _MIN_UNIT_MEAN:
                    rejected.append({
                        'label': _group_label(
                            context,
                            sorted(o for u in members for o in u['members']),
                            instance_tokens, noise_tokens,
                            modal([u.get('wbs_parent_id') for u in members]),
                            modal([u.get('discipline') for u in members]))[0],
                        'front_count': len(members),
                        'activity_count': sum(len(u['members']) for u in members),
                        'front_ids': member_ids,
                        'supporting_signals': [],
                        'evidence_score': 0.0,
                        'reason': ('its fronts average %.2f activities — a work front is a '
                                   'sequence of operations, not a single activity carrying a '
                                   'sequence number' % unit_mean),
                    })
                    continue
                group = _build_group(context, members, metrics, min_instances, keys,
                                     instance_tokens, noise_tokens, code_values,
                                     location_of, reliability)
                # A repeated work front repeats a SEQUENCE. When the consensus comes to a
                # single step, what repeats is one operation across parallel members —
                # the transpose of a work front, i.e. a trade bucket. Measured on a
                # fixture holding no repetition whatsoever, this is what let six unrelated
                # activities ("Mobilise", "Survey", "Demolish"...) be reported as a
                # repeated front. Same principle as ``_MIN_UNIT_MEAN``, applied to the
                # consensus instead of the members: one step is not a sequence.
                if len(group.get('typical_sequence') or []) < 2:
                    rejected.append({
                        'label': group['label'],
                        'front_count': group['front_count'],
                        'activity_count': group['activity_count'],
                        'front_ids': sorted(m['unit_id'] for m in members),
                        'supporting_signals': group['evidence']['supporting_signals'],
                        'evidence_score': group['evidence']['score'],
                        'reason': ('its fronts share a single common step — one operation '
                                   'repeated in parallel is a trade bucket, not a repeated '
                                   'work front'),
                    })
                    continue
                if group['evidence']['supporting_count'] < MIN_SIGNALS:
                    rejected.append({
                        'label': group['label'],
                        'front_count': group['front_count'],
                        'activity_count': group['activity_count'],
                        'front_ids': sorted(m['unit_id'] for m in members),
                        'supporting_signals': group['evidence']['supporting_signals'],
                        'evidence_score': group['evidence']['score'],
                        'reason': ('fewer than %d signals support this grouping — one signal '
                                   'is never sufficient' % MIN_SIGNALS),
                    })
                    continue
                groups.append(group)
                for u in members:
                    in_group.update(u['members'])
            groups.sort(key=lambda g: (-g['activity_count'], -g['front_count'],
                                       g['label'], g['fronts'][0]['front_id']))
            _stamp_ids(groups)
            rejected.sort(key=lambda r: (r['label'], r['front_ids'][0]))
        return {
            'groups': groups, 'rejected': rejected, 'in_group': in_group,
            'chain_splits': chain_splits, 'basis': basis, 'basis_detail': basis_detail,
            'reliability': reliability, 'units': units, 'keys': keys,
        }
    return {
        'profile': profile, 'params': params, 'min_instances': min_instances,
        'threshold': threshold, 'max_items': max_items, 'n_steps': n_steps,
        'steps_sorted': steps_sorted, 'links': links, 'subtree': subtree,
        'repetition': repetition, 'dim_report': dim_report,
        'discipline_dim': discipline_dim, 'discipline_labels': discipline_labels,
        'location_axis': location_axis, 'location_candidates': location_candidates,
        'location_of': location_of, 'code_values': code_values,
        'assemble': assemble,
    }


# ── public entry point ──────────────────────────────────────────────────────
def detect_repeats(context, params=None, selector=None) -> dict:
    """Detect repeated work fronts in one parsed schedule.

    Parameters
    ----------
    context : IntelContext
        From ``p6_narrative.intel.build_context``. Never mutated.
    params : dict | None
        ``min_instances`` / ``sim_threshold`` / ``max_chart_items`` — defaults to
        ``build_profile(context)['params']``, where ``min_instances`` is capped by the
        repetition actually measured in the file (never by the activity count alone).
    selector : callable | None
        The axis-selection strategy, ``select(context, prep) -> (axis, detail, units,
        shape_scores, outcomes, built)``. Defaults to :func:`_select_axis_shape`, the
        validated shape-based baseline. The measurement harness passes :func:`_select_axis`
        to score the rejected ``_judge`` path side-by-side; it is never the default.

    Returns
    -------
    dict
        The full public contract. Top-level keys:

        ``schema_version``
            Contract version of this dict.
        ``axis`` / ``axis_detail`` / ``axis_scores`` / ``unit_count``
            Which axis of repetition was measured to win, and every axis's score.
        ``step_key_basis`` / ``step_key_detail``
            Which rung of the identity ladder produced the step keys.
        ``dimensions``
            Activity-code dimensions: every dimension, the de-duplicated evidence
            classes, what was collapsed into what, per-dimension measurements, the
            discipline dimension chosen **by measured coverage**, and the location axis
            found **structurally** (``None`` when the file carries none).
        ``signals``
            Per-signal in-file reliability, plus the ``quantity`` slot (always
            unavailable — never inferred) and the ``cost`` slot under its own name.
        ``hierarchy``
            The five levels, flat and addressable: ``activities`` (level 1, every step),
            ``families`` (2), ``fronts`` (3), ``typical_sequences`` (4), ``exceptions``
            (5, each carrying its object_ids).
        ``groups``
            One row per repeated work front group, each carrying its own nested
            ``families`` / ``fronts`` / ``typical_sequence`` / ``exceptions`` /
            ``evidence`` / ``confidence``.
        ``rejected_groups``
            Candidate groups dropped because fewer than two signals supported them —
            recorded, not silently discarded.
        ``singletons``
            Step object_ids that belong to no group.
        ``coverage``
            The **verified** proof that every step object_id appears exactly once across
            groups and singletons (multiset check; see ``intel.hierarchy``).
        ``params`` / ``repetition``
            The parameters used and the repetition measured in the file behind them.
    """
    prep = prepare(context, params)
    params = prep['params']
    min_instances, max_items = prep['min_instances'], prep['max_items']
    links, subtree = prep['links'], prep['subtree']
    dim_report = prep['dim_report']
    discipline_dim = prep['discipline_dim']
    location_axis = prep['location_axis']
    location_candidates = prep['location_candidates']
    repetition = prep['repetition']
    assemble = prep['assemble']

    select = selector or _select_axis_shape
    axis, axis_detail, units, axis_scores, axis_outcomes, built = select(context, prep)
    if built is None:                    # no partition produced a single group
        built = assemble([])

    groups = built['groups']
    rejected = built['rejected']
    in_group = built['in_group']
    chain_splits = built['chain_splits']
    basis, basis_detail = built['basis'], built['basis_detail']
    reliability = built['reliability']

    singletons = sorted(o for o in context.steps if o not in in_group)
    coverage = assert_coverage(prove_coverage(context, groups, singletons))
    hierarchy = build_hierarchy(context, groups, singletons)

    return {
        'schema_version': SCHEMA_VERSION,
        'axis': axis,
        'axis_detail': axis_detail,
        'axis_scores': {name: axis_scores.get(name, 0.0) for name in _AXIS_ORDER},
        'step_key_basis': basis,
        'step_key_detail': basis_detail,
        'unit_count': len(units),
        'dimensions': {
            'code_dimensions': dim_report['code_dimensions'],
            'representatives': dim_report['representatives'],
            'classes': dim_report['classes'],
            'collapsed': dim_report['collapsed'],
            'near_duplicate_pairs': dim_report['near_duplicate_pairs'],
            'stats': dim_report['stats'],
            'discipline': dim_report['discipline'],
            'discipline_dim': discipline_dim,
            'location_axis': location_axis,
            'location_candidates': location_candidates,
        },
        'signals': {
            'names': list(SIGNAL_NAMES),
            'contract_levels': dict(LEVEL_NAMES),
            'reliability': reliability,
            'quantity': quantity_signal(context),
            'cost': cost_signal(context),
        },
        'hierarchy': hierarchy,
        'groups': groups,
        'rejected_groups': rejected,
        'chain_splits': chain_splits,
        'singletons': singletons,
        'coverage': coverage,
        'params': params,
        'repetition': repetition,
    }


# ── 6. outcome-based axis selection ─────────────────────────────────────────
def _scope_purity(context, units):
    """Share of units confined to ONE major WBS branch of the schedule's own breakdown.

    A repeated work front is a *place in the breakdown*: whatever axis names it, its
    activities belong to one scope. A unit straddling two major branches is not one
    front, it is two fronts glued together by a naming or numbering coincidence — which
    is precisely how a transposed or lumped partition looks from the WBS.

    Read from ``context.group_of`` (the adaptive major-branch grouping the whole layer
    already shares), so it needs no code dimension, no location axis and no keyword list.
    Units carrying no branch at all are skipped rather than counted as impure; a file
    whose steps all sit in one branch scores 1.0 for every candidate, which correctly
    makes the term say nothing on a single-branch schedule.
    """
    activities = context.data.activities
    total = pure = 0
    for u in units:
        branches = set()
        for oid in u['members']:
            wid = (activities.get(oid) or {}).get('wbs_id')
            branch = context.group_of.get(wid)
            if branch is not None:
                branches.add(branch)
        if not branches:
            continue
        total += 1
        if len(branches) == 1:
            pure += 1
    return round(pure / float(total), 4) if total else 1.0


def _sequence_components(context, group, keys):
    """Connected components of one group's typical sequence under the file's own logic.

    A repeated work front hands its first operation over to its second, so the consensus
    steps the narrative prints should form ONE connected component. Two components mean
    two unrelated chains were printed as a single sequence. Direction is irrelevant —
    this asks "is this sequence wired together at all", never "which came first" (order
    still comes from the topological pass, never from dates).
    """
    steps = [s['step'] for s in group['typical_sequence']]
    if len(steps) < 2:
        return 1
    idx = {step: i for i, step in enumerate(steps)}
    own = set()
    for front in group['fronts']:
        own.update(front['activity_ids'])
    parent = list(range(len(steps)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for oid in sorted(own):
        a = idx.get(keys.get(oid))
        if a is None:
            continue
        for e in context.graph.succs_of(oid):
            other = e['other']
            if other not in own:
                continue
            b = idx.get(keys.get(other))
            if b is None or b == a:
                continue
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    return len({find(i) for i in range(len(steps))})


def _outcome(context, cand, built, n_steps):
    """Measure what one assembled partition actually PRODUCED. JSON-serialisable.

    ``sequence_explained`` is the proven per-front-per-step discount: a group is credited
    with the work its typical sequence really accounts for, ``fronts x steps``, capped by
    the activities it holds. A transposed partition — one operation repeated in parallel
    across every front — collapses under it (measured: a 3-front trade bucket holding 809
    activities scores 9; a 102-front bucket holding 2,416 scores 303) while a genuine set
    of work fronts is left untouched.
    """
    groups = built['groups']
    keys = built['keys'] or {}
    explained = sum(g['activity_count'] for g in groups)
    seq_explained = 0
    chained = 0
    labels = Counter()
    for group in groups:
        steps = len(group['typical_sequence'])
        seq_explained += min(group['activity_count'], group['front_count'] * steps)
        if _sequence_components(context, group, keys) == 1:
            chained += 1
        labels[group['label']] += 1
    return {
        'axis': cand['axis'],
        'axis_rank': cand['axis_rank'],
        'detail': cand['detail'],
        'shape_score': cand['shape_score'],
        'unit_count': len(cand['units']),
        'group_count': len(groups),
        'activities_explained': explained,
        'coverage': round(explained / float(n_steps), 4) if n_steps else 0.0,
        'sequence_explained': seq_explained,
        'chained_groups': chained,
        'duplicate_labels': sum(c - 1 for c in labels.values() if c > 1),
        'scope_purity': _scope_purity(context, cand['units']),
    }


def _shortlist(candidates, budget):
    """Which partitions get assembled, within the compute budget. Deterministic.

    Assembling a partition costs a clustering pass over its units, and the cohesion
    refinement inside it is cubic in the size of a connected component, so the total cost
    is driven by how many UNITS get assembled — that is what the budget counts, rather
    than a candidate count that would say nothing about the work involved.

    The best-shaped candidate of **every** axis is always assembled, whatever the budget:
    a budget that can silence a whole axis would reintroduce exactly the failure this
    selector exists to fix (the answer sitting in a candidate nobody looked at). Measured
    on the largest real file available, the per-axis seeds cost 572 units / 0.31 s, and
    the winning partition is one of them. The remaining candidates are then assembled in
    shape order until the budget is spent. Measured on the largest file available at all
    (13,000 activities, 650 fronts) this holds the whole selection to ~2 s, where
    assembling every candidate costs ~14 s — the excluded ones are the 500-800-unit
    name-affix partitions whose refinement dominates that difference.
    """
    seeds, best_of_axis = [], {}
    for cand in candidates:
        if cand['shape_score'] <= 0.0:
            continue
        key = cand['axis']
        rank = (-cand['shape_score'], cand['detail'])
        if key not in best_of_axis or rank < best_of_axis[key][0]:
            best_of_axis[key] = (rank, cand)
    for name in _AXIS_ORDER:
        if name in best_of_axis:
            seeds.append(best_of_axis[name][1])

    chosen = list(seeds)
    seen = {(c['axis'], c['detail']) for c in seeds}
    spent = sum(len(c['units']) for c in seeds)
    rest = sorted((c for c in candidates
                   if c['shape_score'] > 0.0 and (c['axis'], c['detail']) not in seen),
                  key=lambda c: (-c['shape_score'], c['axis_rank'], c['detail']))
    for cand in rest:
        if spent + len(cand['units']) > budget:
            continue
        chosen.append(cand)
        spent += len(cand['units'])
    chosen.sort(key=lambda c: (-c['shape_score'], c['axis_rank'], c['detail']))
    return chosen


def _judge(outcomes):
    """Rank assembled partitions by what they PRODUCED. Returns the ranked outcomes.

    Lexicographic, so no term is ever traded against another by a weight and nothing is
    divided by a group count:

    1. **Scope purity, gated at the best value any candidate achieves.** This is the
       anti-fragmentation / anti-lumping criterion, and it is a criterion rather than a
       term: a work front is a place in the breakdown, so a partition whose units
       straddle major WBS branches is not competing for the same question. Gating at the
       observed maximum (rather than at a constant) means the gate can never empty the
       shortlist and never needs a threshold fitted to a file.
    2. **Sequence-explained work** — the per-front-per-step discount. Coverage alone is
       explicitly not allowed to decide: on a real baseline a name-affix partition
       explains 54% of the schedule against the correct answer's 34% and every one of its
       "fronts" is a step name ("Details", "Dimension", "Handrails"), which the discount
       collapses from 468 raw activities to 174 while leaving the correct answer at 251.
    3. **Chained groups** — how many emitted groups have a typical sequence that is
       actually one connected chain of hand-overs. This is the front test, used to break
       a tie rather than to gate, because a legitimate front can be a set of parallel
       operations (a building's ten submittal approvals repeat across eight buildings and
       are wired to nothing inside the front).
    4. **Shape score, then the fixed axis order, then the detail** — the pre-outcome
       ordering, kept as the final tie-break so the result stays deterministic when two
       partitions produce genuinely indistinguishable outcomes.

    RULES MEASURED AND REJECTED HERE — recorded so they are not re-invented:

    a. *Dividing the discounted work by the group count* (the second half of the
       originally rejected rule). Pays for lumping;
       ``test_two_different_work_types_under_different_parents_are_never_merged``
       caught it immediately.
    b. *Requiring emitted groups to be maximal under the similarity relation*, read as
       "no two emitted groups may share a label and a typical sequence". Measured
       vacuous: ``duplicate_labels`` is non-zero on real files but the (label, sequence)
       pair never repeats on ANY candidate of ANY fixture or baseline, because clustering
       already refuses to emit two groups with the same step-key set. A criterion that
       never fires cannot be the anti-fragmentation term.
    c. *Disqualifying any partition that emits two groups with the same label.* Directly
       the stated "no duplicate-labelled groups" criterion, and measured actively
       harmful: on one baseline it disqualifies the correct 15-group answer (which
       repeats a label across two different WBS parents, legitimately) and hands the file
       to the name-affix partition whose fronts are step names. Duplicate labels are
       therefore REPORTED per candidate, never gated on.
    d. *Making the typical-sequence chain test a gate instead of a tie-break.* Measured:
       it destroys legitimate fronts whose operations are parallel — an eight-front
       approval group with ten parallel steps drops from 89 activities of credit to 8.
    e. *Restricting the step-key fallback ladder to bases that clear the discrimination
       gate.* The ladder's fallback score rewards ``alignment``, which is trivially 1.0
       exactly when a basis is maximally uninformative (one key for all 194 activities of
       a front), so it can pick a basis that provably yields a one-step consensus. The
       fix is right in principle and measured NEUTRAL-to-harmful: it recovered no answer
       and removed four viable candidates on one baseline, because the coarse partitions
       it unblocks share no step keys across fronts anyway (alignment 0.15). Left alone;
       the discount already collapses the affected partitions.
    """
    if not outcomes:
        return []
    best_purity = max(o['scope_purity'] for o in outcomes)
    ranked = sorted(outcomes, key=lambda o: (
        0 if o['scope_purity'] >= best_purity else 1,
        -o['sequence_explained'],
        -o['chained_groups'],
        -o['shape_score'],
        o['axis_rank'],
        o['detail'],
    ))
    for position, outcome in enumerate(ranked):
        outcome['rank'] = position + 1
        outcome['gated'] = outcome['scope_purity'] < best_purity
    return ranked


def _select_axis(context, prep, budget=None):
    """Pick the axis by the OUTCOME its partition produces, not by its shape.

    Shape is only the cheap shortlisting filter now (see :func:`_shortlist`); every
    shortlisted partition is assembled to finished groups through the single ``assemble``
    closure the final output also runs through, and judged by :func:`_judge`. Returns
    ``(axis, detail, units, shape_scores, outcomes, built)`` — ``built`` is the winner's
    already-assembled result, so the winning partition is never assembled twice.
    """
    candidates = candidate_partitions(
        context, prep['min_instances'], prep['max_items'], prep['links'],
        prep['subtree'], prep['dim_report']['representatives'])
    shape_scores = _shape_scores(candidates)
    if budget is None:
        budget = _ASSEMBLE_UNIT_BUDGET

    outcomes, built_by = [], {}
    for cand in _shortlist(candidates, budget):
        built = prep['assemble']([dict(u) for u in cand['units']])
        if not built['groups']:
            continue                     # produced nothing: it cannot be the answer
        key = (cand['axis'], cand['detail'])
        built_by[key] = (cand, built)
        outcomes.append(_outcome(context, cand, built, prep['n_steps']))

    ranked = _judge(outcomes)
    if not ranked:
        return None, None, [], shape_scores, [], None
    winner = ranked[0]
    cand, built = built_by[(winner['axis'], winner['detail'])]
    return (cand['axis'], cand['detail'], built['units'], shape_scores, ranked, built)
