"""Schedule Intelligence — activity-code dimensions: de-duplication and selection.

Three jobs, all measured from the file and none of them keyed on a dimension's *name*:

1. **De-duplication (redundant coding must never inflate confidence).** Real exports
   carry the same coding twice under two names — one baseline ships eleven dimension
   pairs whose ``(object_id, value)`` assignment sets are byte-identical, plus fourteen
   more that agree on the same values and differ by a couple of assignments.
   :func:`dedupe_dimensions` collapses identical assignment sets onto one representative
   and groups near-identical ones into a single *evidence class*, so a doubly-coded file
   supplies one piece of evidence, not two. The full sorted ``(object_id, value)`` set is
   what gets compared — never a count, never a value set on its own.

2. **Discipline selection by measured coverage (:func:`select_discipline_dim`).** The
   legacy document path picks the first dimension whose *name* contains "type of work" /
   "discipline" / "trade". On real files that mis-picks: it takes a 93.7%-covered
   dimension over a 99%-covered one, and on another baseline a 50.9%-covered one over two
   at 100%, which silently leaves half the schedule labelled from a different basis (a
   mixed-basis label set). Here the pick is the dimension that actually labels the
   schedule and actually partitions it — gates first, then coverage, then partition
   quality. No dimension name is ever inspected.

3. **Location axis detection, structurally (:func:`select_location_axis`).** A location /
   zone / area axis is *not* found by looking for the words "zone" or "area". It is the
   axis that partitions the schedule roughly **orthogonally** to the discipline axis: the
   same location recurs across several disciplines and the same discipline recurs across
   several locations. Candidates are code dimensions *and* name affixes; the answer is
   ``None`` when the file carries no such axis.

Legacy note: ``p6_narrative.sequence.pick_discipline_dim`` and ``scope.py`` keep their
current name-matching behaviour and are deliberately **not** touched here — the document
must render exactly as it does today. The two paths are unified in a later slice; until
then do not assume ``context.discipline_dim`` (the legacy value) and the measured value
below agree.

Pure, deterministic, JSON-serialisable output; everything keyed on ``object_id``.
"""
from collections import Counter

from p6_narrative.intel.common import (
    clamp01, mean, normalised_entropy, signature, spread,
)
from p6_narrative.intel.structure import name_affix_maps

# --- de-duplication -------------------------------------------------------------
# Two dimensions are ONE piece of evidence when they carry the same set of distinct
# values and agree on the overwhelming majority of their assignments. 0.9 is a general
# "overwhelming majority" level, not a value fitted to any file: the real near-duplicate
# pairs observed agree at ~99.8%, far above it, and a genuinely different dimension that
# happens to reuse the same value vocabulary agrees far below it.
_NEAR_DUP_AGREEMENT = 0.9

# --- usability gates ------------------------------------------------------------
# A dimension is a *category* only if it categorises: at least half of the activities it
# labels must share their value with another activity. A dimension with one value per
# activity is an identifier; a dimension with one value for everything partitions
# nothing; a dimension labelling a single activity is noise.
_MIN_SHARED_SHARE = 0.5
_MIN_ASSIGNED = 2
# Coverage is compared at 0.1% granularity so float noise cannot reorder two dimensions
# that cover the same activities. This is a numeric-noise guard, not a tuning band.
_COVER_PRECISION = 3

# --- orthogonality gate for the location axis -----------------------------------
# "The same location recurs across SEVERAL disciplines and the same discipline recurs
# across SEVERAL locations" — the minimal honest reading of "several" is two.
_MIN_CROSS = 2.0

DISCIPLINE_RULE = (
    'usable dimensions ranked by measured step coverage, then by partition quality '
    '(evenness x share-of-activities-in-a-shared-value); dimension NAMES are never '
    'inspected and duplicate dimensions are collapsed first'
)
LOCATION_RULE = (
    'the candidate axis (code dimension or name affix) that partitions the steps most '
    'orthogonally to the discipline axis: >= %g disciplines per location value AND '
    '>= %g locations per discipline value, ranked by cross-product completeness x '
    'coverage' % (_MIN_CROSS, _MIN_CROSS)
)

# Bounded identity cache: the report is derived from a context that is a snapshot by
# design, so it can be memoised per context. A strong reference is kept alongside each
# entry, which is what makes the identity test safe (an id() key could be recycled).
# Four entries is enough for the UI's "compare two files" flows and bounds the memory.
_CACHE_LIMIT = 4
_cache = []


# ── assignment sets ─────────────────────────────────────────────────────────
def dimension_pairs(context, dim, oids=None):
    """Sorted ``[(object_id, value)]`` assignments of one dimension.

    Over **all** activities by default — the identity of a dimension is the whole
    assignment set it carries, not the part of it that happens to fall on step
    activities.
    """
    activities = context.data.activities
    keys = sorted(activities) if oids is None else sorted(oids)
    out = []
    for oid in keys:
        act = activities.get(oid) or {}
        val = (act.get('activity_codes') or {}).get(dim)
        if val:
            out.append((oid, val))
    return out


def code_values_by_dimension(context, dims, oids):
    """``{dimension: {object_id: value}}`` for the given dimensions and activities."""
    out = {}
    for dim in sorted(dims):
        out[dim] = {oid: val for oid, val in dimension_pairs(context, dim, oids)}
    return out


def _representative(members):
    """The least decorated name in an equivalence class: shortest, then alphabetical.

    Deterministic and file-derived — a duplicated dimension in the wild is usually the
    plain name plus a prefix ('RME-WBS' beside 'RME-Project-WBS'), so the shorter name is
    the one a planner recognises. No name content is interpreted.
    """
    return sorted(members, key=lambda d: (len(d), d))[0]


def dedupe_dimensions(context):
    """Collapse duplicate activity-code dimensions. JSON-serialisable report.

    Returns ``{dimensions, representatives, classes, collapsed}``:

    ``dimensions``      every dimension the file declares, sorted.
    ``representatives`` one dimension per *exact*-duplicate class, sorted.
    ``classes``         evidence classes — exact duplicates collapsed, near-duplicates
                        grouped, each with its representative and its members.
    ``collapsed``       one row per dimension that was folded away, naming what it was
                        folded into and whether the match was exact or near. This is the
                        traceability record: nothing disappears silently.
    """
    dims = sorted({d for d in (context.data.activity_code_types or []) if d})
    pairs = {d: dimension_pairs(context, d) for d in dims}
    sigs = {d: signature(pairs[d]) for d in dims}

    by_sig = {}
    for dim in dims:
        by_sig.setdefault(sigs[dim], []).append(dim)

    rep_of, exact_members = {}, {}
    for sig in sorted(by_sig):
        members = sorted(by_sig[sig])
        rep = _representative(members)
        exact_members[rep] = members
        for m in members:
            rep_of[m] = rep
    representatives = sorted(exact_members)

    # Near-duplicates: same value vocabulary + overwhelming assignment agreement.
    pair_sets = {r: set(pairs[r]) for r in representatives}
    value_sets = {r: {v for _, v in pairs[r]} for r in representatives}
    parent = {r: r for r in representatives}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    near_pairs = []
    for i, a in enumerate(representatives):
        for b in representatives[i + 1:]:
            if not value_sets[a] or value_sets[a] != value_sets[b]:
                continue
            union = pair_sets[a] | pair_sets[b]
            if not union:
                continue
            agreement = len(pair_sets[a] & pair_sets[b]) / float(len(union))
            if agreement >= _NEAR_DUP_AGREEMENT:
                near_pairs.append((a, b, round(agreement, 4)))
                ra, rb = find(a), find(b)
                if ra != rb:
                    lo, hi = (ra, rb) if ra <= rb else (rb, ra)
                    parent[hi] = lo

    comps = {}
    for r in representatives:
        comps.setdefault(find(r), []).append(r)

    classes, collapsed = [], []
    ordered_roots = sorted(comps, key=lambda r: _representative(comps[r]))
    for idx, root in enumerate(ordered_roots):
        reps = sorted(comps[root])
        class_rep = _representative(reps)
        members = sorted({m for r in reps for m in exact_members[r]})
        class_id = 'dc%d' % (idx + 1)
        classes.append({
            'class_id': class_id,
            'representative': class_rep,
            'dimensions': members,
            'exact_duplicates': sorted(m for m in exact_members[class_rep]
                                       if m != class_rep),
            'near_duplicates': sorted(m for m in members
                                      if m not in exact_members[class_rep]),
            'assignments': len(pairs[class_rep]),
            'signature': sigs[class_rep][:12],
        })
        for m in members:
            if m == class_rep:
                continue
            relation = 'exact' if rep_of[m] == rep_of[class_rep] else 'near'
            collapsed.append({
                'dimension': m,
                'merged_into': class_rep,
                'class_id': class_id,
                'relation': relation,
                'assignments': len(pairs[m]),
            })
    collapsed.sort(key=lambda r: (r['dimension'], r['merged_into']))

    return {
        'dimensions': dims,
        'representatives': representatives,
        'classes': classes,
        'collapsed': collapsed,
        'near_duplicate_pairs': [{'a': a, 'b': b, 'agreement': ag}
                                 for a, b, ag in sorted(near_pairs)],
    }


# ── per-dimension measurement ───────────────────────────────────────────────
def dimension_stats(context, dims):
    """Measure each dimension over the *step* population. Sorted by dimension name.

    Per dimension: ``assigned`` / ``coverage`` (of the steps), ``distinct_values``,
    ``shared_share`` (activities whose value is shared with another activity),
    ``evenness`` (normalised entropy), ``quality``, and ``usable`` with an explicit
    ``reject_reason`` when it is not.
    """
    steps = sorted(context.steps)
    n = len(steps)
    out = []
    for dim in sorted(dims):
        values = {}
        for oid in steps:
            val = (context.steps[oid].get('activity_codes') or {}).get(dim)
            if val:
                values[oid] = val
        assigned = len(values)
        counts = Counter(values.values())
        distinct = len(counts)
        shared = sum(c for c in counts.values() if c >= 2)
        shared_share = (shared / float(assigned)) if assigned else 0.0
        coverage = (assigned / float(n)) if n else 0.0
        evenness = normalised_entropy(list(counts.values()))
        reject = None
        if assigned < _MIN_ASSIGNED:
            reject = 'labels fewer than %d step activities' % _MIN_ASSIGNED
        elif distinct < 2:
            reject = 'one value for the whole schedule — partitions nothing'
        elif distinct >= assigned:
            reject = 'one value per activity — an identifier, not a category'
        elif shared_share < _MIN_SHARED_SHARE:
            reject = ('most values label a single activity — an identifier, '
                      'not a category')
        out.append({
            'dimension': dim,
            'assigned': assigned,
            'coverage': round(coverage, 4),
            'distinct_values': distinct,
            'shared_share': round(shared_share, 4),
            'evenness': round(evenness, 4),
            'quality': round(0.5 * evenness + 0.5 * shared_share, 4),
            'usable': reject is None,
            'reject_reason': reject,
        })
    return out


def select_discipline_dim(context, dedupe=None, stats=None):
    """Pick the discipline dimension by measured coverage and reliability.

    Coverage leads because the *cost of not covering* is a mixed-basis label set: every
    unlabelled activity has to borrow a label from a different basis (its WBS branch), so
    a dimension that leaves half the schedule unlabelled produces a label set that means
    two different things. Partition quality breaks ties.

    Returns ``{'selected': dim|None, 'rule': str, 'candidates': [...], 'rejected': [...]}``.
    """
    dd = dedupe if dedupe is not None else dedupe_dimensions(context)
    st = stats if stats is not None else dimension_stats(context, dd['representatives'])
    usable = [s for s in st if s['usable']]
    ranked = sorted(usable, key=lambda s: (-round(s['coverage'], _COVER_PRECISION),
                                           -s['quality'], s['dimension']))
    return {
        'selected': ranked[0]['dimension'] if ranked else None,
        'rule': DISCIPLINE_RULE,
        'candidates': ranked,
        'rejected': [s for s in st if not s['usable']],
    }


def dimension_report(context):
    """The de-duplication + discipline-selection report for one context (memoised).

    The location axis is **not** part of this report: it is defined relative to the
    discipline *labels*, which include the WBS fallback for unlabelled activities, so it
    is computed by :func:`select_location_axis` once those labels exist. Keeping the two
    apart is what stops the discipline rule having a second implementation.
    """
    for ctx, report in _cache:
        if ctx is context:
            return report
    dd = dedupe_dimensions(context)
    st = dimension_stats(context, dd['representatives'])
    report = {
        'code_dimensions': dd['dimensions'],
        'representatives': dd['representatives'],
        'classes': dd['classes'],
        'collapsed': dd['collapsed'],
        'near_duplicate_pairs': dd['near_duplicate_pairs'],
        'stats': st,
        'discipline': select_discipline_dim(context, dd, st),
    }
    _cache.append((context, report))
    if len(_cache) > _CACHE_LIMIT:
        del _cache[0]
    return report


def measured_discipline_dim(context):
    """The single source of truth for "which dimension is the discipline axis"."""
    return dimension_report(context)['discipline']['selected']


# ── location axis (structural orthogonality) ────────────────────────────────
def _cross_stats(labels_a, labels_b):
    """How completely two labellings cross each other, over their common activities.

    ``mean_b_per_a`` — how many *b* values a typical *a* value is seen with (and the
    mirror). A location axis crosses the discipline axis: each zone contains several
    trades and each trade appears in several zones. A hierarchical axis (a finer
    breakdown of the same thing) does not: each of its values sits inside exactly one
    value of the other, giving 1.0.
    """
    common = sorted(set(labels_a) & set(labels_b))
    if not common:
        return None
    a_to_b, b_to_a = {}, {}
    for oid in common:
        a, b = labels_a[oid], labels_b[oid]
        a_to_b.setdefault(a, set()).add(b)
        b_to_a.setdefault(b, set()).add(a)
    n_a, n_b = len(a_to_b), len(b_to_a)
    mean_b_per_a = mean(len(v) for v in a_to_b.values())
    mean_a_per_b = mean(len(v) for v in b_to_a.values())
    completeness = 0.0
    if n_a > 1 and n_b > 1:
        completeness = clamp01(0.5 * (mean_b_per_a / float(n_b))
                               + 0.5 * (mean_a_per_b / float(n_a)))
    return {
        'common_activities': len(common),
        'location_values': n_a,
        'discipline_values': n_b,
        'disciplines_per_location': round(mean_b_per_a, 4),
        'locations_per_discipline': round(mean_a_per_b, 4),
        'cross_completeness': round(completeness, 4),
    }


def select_location_axis(context, discipline_labels, report=None, discipline_dim=None):
    """Identify the location / zone / area axis structurally, or report none.

    ``discipline_labels`` is ``{object_id: label}`` for the steps — whatever basis the
    label came from, so this works on files with no usable code dimension at all.

    Returns ``(axis|None, candidates)``. ``axis`` is a dict describing the winner
    (``kind`` is ``'code_dimension'`` or ``'name_affix'``); ``candidates`` lists every
    axis tried with its measurements and rejection reason, so "this file has no location
    axis" is an evidenced answer rather than a silence.
    """
    rep = report if report is not None else dimension_report(context)
    dim = discipline_dim if discipline_dim is not None else rep['discipline']['selected']
    steps = sorted(context.steps)
    labels_b = {o: discipline_labels[o] for o in steps if discipline_labels.get(o)}
    n_steps = len(steps)

    # A dimension in the discipline's own evidence class is the discipline axis again.
    same_class = set()
    for cls in rep['classes']:
        if dim and dim in cls['dimensions']:
            same_class.update(cls['dimensions'])

    usable_dims = {s['dimension'] for s in rep['stats'] if s['usable']}

    # Which evidence class each dimension belongs to, so a candidate is never crossed
    # against a duplicate of itself.
    class_of = {}
    for cls in rep['classes']:
        for member in cls['dimensions']:
            class_of[member] = cls['representative']

    ranked_disciplines = [s['dimension'] for s in rep['discipline']['candidates']]
    _label_cache = {}

    def discipline_labels_for(name):
        if name not in _label_cache:
            _label_cache[name] = {oid: val for oid, val
                                  in dimension_pairs(context, name, steps)}
        return _label_cache[name]

    def discipline_ladder(candidate_dim):
        """Disciplines to test one location candidate against, best first.

        The selected discipline can be COARSER than the candidate's own scope. A
        phase-level code covering the whole file reads the same value ('Construction')
        for every activity a building-level code touches — and *constant* is not the same
        as *not orthogonal*. It means this discipline cannot answer the question at all,
        so the next-ranked discipline that does vary over those activities is asked
        instead. Without this, a file that codes trade only inside its construction phase
        loses its location axis entirely, and with it the anchor that tells a work FRONT
        from a trade bucket.

        A dimension from the candidate's own evidence class is never used: crossing a
        dimension against a duplicate of itself measures nothing.
        """
        ladder = []
        for name in ([dim] if dim else []) + ranked_disciplines:
            if not name or name in ladder:
                continue
            if class_of.get(name) is not None and class_of.get(name) == class_of.get(candidate_dim):
                continue
            ladder.append(name)
        return ladder

    candidates = []
    for cls in rep['classes']:
        cand = cls['representative']
        if cand not in usable_dims:
            continue
        if cand in same_class:
            continue
        labels_a = {oid: val for oid, val
                    in dimension_pairs(context, cand, steps)}
        candidates.append(('code_dimension', cand, cand, labels_a))
    for detail, keys in name_affix_maps(context, steps):
        candidates.append(('name_affix', None, detail, keys))

    rows = []
    for kind, dimension, detail, labels_a in candidates:
        coverage = (len(labels_a) / float(n_steps)) if n_steps else 0.0
        row = {
            'kind': kind,
            'dimension': dimension,
            'detail': detail,
            'coverage': round(coverage, 4),
            'cross_completeness': 0.0,
            'disciplines_per_location': 0.0,
            'locations_per_discipline': 0.0,
            'location_values': len(set(labels_a.values())),
            'discipline_values': len(set(labels_b.values())),
            'score': 0.0,
            'tested_against': dim,
            'reject_reason': None,
        }
        # Walk the discipline ladder: the first discipline that actually VARIES over this
        # candidate's activities is the one that can judge it. Fall back to the first
        # attempt so a genuine rejection still carries its measurements.
        cross, first_try = None, None
        for candidate_discipline in discipline_ladder(dimension):
            labels_disc = (labels_b if candidate_discipline == dim
                           else discipline_labels_for(candidate_discipline))
            attempt = _cross_stats(labels_a, labels_disc)
            if attempt is None:
                continue
            if first_try is None:
                first_try = (candidate_discipline, attempt)
            if attempt['discipline_values'] >= 2:
                cross, row['tested_against'] = attempt, candidate_discipline
                break
        if cross is None and first_try is not None:
            row['tested_against'], cross = first_try
        if cross is None:
            row['reject_reason'] = 'no activity carries both this axis and a discipline'
            rows.append(row)
            continue
        row.update({k: cross[k] for k in (
            'disciplines_per_location', 'locations_per_discipline',
            'cross_completeness', 'location_values', 'discipline_values')})
        row['common_activities'] = cross['common_activities']
        if row['location_values'] < 2:
            row['reject_reason'] = 'a single value — partitions nothing'
        elif row['discipline_values'] < 2:
            row['reject_reason'] = 'the discipline axis has a single value — nothing to cross'
        elif row['disciplines_per_location'] < _MIN_CROSS:
            row['reject_reason'] = ('each value sits inside fewer than %g disciplines — '
                                    'a sub-breakdown of the discipline axis, not a '
                                    'location axis' % _MIN_CROSS)
        elif row['locations_per_discipline'] < _MIN_CROSS:
            row['reject_reason'] = ('each discipline sits inside fewer than %g values — '
                                    'not orthogonal' % _MIN_CROSS)
        else:
            row['score'] = round(row['cross_completeness'] * coverage, 6)
        rows.append(row)

    rows.sort(key=lambda r: (r['kind'], r['detail']))
    passing = [r for r in rows if r['reject_reason'] is None]
    if not passing:
        return None, rows
    # Code dimensions before name affixes on an exact tie: a dimension is an explicit
    # statement by the planner, an affix is inferred from text.
    kind_rank = {'code_dimension': 0, 'name_affix': 1}
    passing.sort(key=lambda r: (-r['score'], kind_rank[r['kind']], r['detail']))
    best = dict(passing[0])
    best['rule'] = LOCATION_RULE
    return best, rows


def location_labels(context, axis):
    """``{object_id: location value}`` for a selected location axis (empty when None)."""
    if not axis:
        return {}
    steps = sorted(context.steps)
    if axis['kind'] == 'code_dimension':
        return {oid: val for oid, val in dimension_pairs(context, axis['dimension'], steps)}
    for detail, keys in name_affix_maps(context, steps):
        if detail == axis['detail']:
            return dict(keys)
    return {}


def axis_spread(values):
    """Convenience re-export used by the signal layer (see ``common.spread``)."""
    return spread(values)
