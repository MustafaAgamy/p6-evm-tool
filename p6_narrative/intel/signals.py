"""Schedule Intelligence — the evidence signals behind a repeated work front.

A repeated work front is **never** established by one signal, and above all never by
name equality: one real baseline repeats 501 distinct names across 896 activities (57% of
its activities share a name with another), the next carries 2453 distinct names for 2502
activities because the instance is baked into a name suffix. Name equality finds 431
groupable activities in the first file and literally none in the second, so a
single-signal engine passes one file and does nothing on the other.

So a front is established by **combining** the evidence the file actually carries, each
weighted by how reliable it is *in that file*. The seven signals are exactly the seven
the engine contract names:

===================  ============================================================
``identity``         activity identity / name, name affixes, and — when names carry
                     nothing repeatable — the ID-segment or WBS-leaf fallback that
                     the step-key ladder actually used.
``wbs``              WBS context: position, parent template, sibling set.
``codes``            activity-code context, counted once per *evidence class* so a
                     doubly-coded file cannot inflate its own confidence.
``location``         location / zone / area context, detected structurally.
``logic``            relationship / sequence context: internal order and logic shape.
``quantity``         quantity / unit — **not available** (see :func:`quantity_signal`).
``neighbourhood``    similarity of the surrounding activities: what feeds this front
                     and what it feeds.
===================  ============================================================

Two numbers are reported per signal per group:

* **support** (0..1) — how strongly *this group's* fronts agree on that signal.
* **reliability** (0..1) — how much that signal is worth *in this file*, measured from
  the file (coverage, repetition, logic density). A signal the file does not carry has
  reliability 0 and cannot contribute, however strongly it appears to "agree": five
  fronts that all have no internal logic agree vacuously, and that is scored as no
  evidence rather than as perfect evidence.

``evidence_block`` reports both, plus which signals actually supported the group, so a
planner can see *why* the engine believes these are the same front. No single signal can
carry a group: :data:`MIN_SIGNALS` independent signals must clear
:data:`SUPPORT_FLOOR`.

Pure, deterministic, JSON-serialisable. No keyword lists anywhere.
"""
from p6_narrative.intel.common import (
    clamp01, concentration, jaccard, mean, modal, rescale, spread,
)

# Sorted, so the emitted signal list has a fixed order independent of anything.
SIGNAL_NAMES = ('codes', 'identity', 'location', 'logic', 'neighbourhood',
                'quantity', 'wbs')

# A signal "supports" a group when its fronts agree more than they disagree, and a group
# needs two independent supporting signals. Both encode the contract directly ("no single
# signal may be sufficient on its own") rather than being fitted to any file.
SUPPORT_FLOOR = 0.5
MIN_SIGNALS = 2

# Attributes a future parser would expose once P6 resource/quantity parsing lands. The
# quantity signal is wired to activate on them; nothing consumes them yet and nothing in
# this layer ever derives a quantity from cost, duration or activity count.
QUANTITY_SOURCES = ('qty_by_activity', 'quantity_by_activity', 'units_by_activity',
                    'resource_assignments', 'resources')
QUANTITY_UNAVAILABLE_REASON = 'P6 resource/QTY parsing not implemented'


# ── availability signals ────────────────────────────────────────────────────
def quantity_signal(context):
    """The quantity / unit signal — explicitly **not available**.

    The parser exposes no resource table: only rolled-up cost per activity. True
    quantities and units therefore do not exist in the parsed data, and this layer must
    never estimate, derive or proxy one (not from cost, not from duration, not from an
    activity count). The slot is reported honestly and is wired to flip to available the
    moment a parser exposes one of :data:`QUANTITY_SOURCES`; even then this slice reports
    presence only and computes no quantity number.
    """
    data = context.data
    for attr in QUANTITY_SOURCES:
        value = getattr(data, attr, None)
        if value:
            return {
                'available': True,
                'source': attr,
                'reason': None,
                'consumed': False,
                'note': ('quantity data is present but this slice does not consume it; '
                         'no quantity is ever derived from cost or duration'),
            }
    return {
        'available': False,
        'source': None,
        'reason': QUANTITY_UNAVAILABLE_REASON,
        'consumed': False,
        'note': 'cost is reported separately under its own name and is never a quantity',
    }


def cost_signal(context):
    """The cost signal, under its own honest name — never a quantity proxy."""
    bac = context.data.bac_by_activity or {}
    steps = context.steps
    with_cost = sorted(o for o in steps if (bac.get(o) or 0.0) > 0.0)
    return {
        'available': bool(with_cost),
        'source': 'bac_by_activity',
        'activities_with_cost': len(with_cost),
        'coverage': round(len(with_cost) / float(len(steps)), 4) if steps else 0.0,
        'note': 'rolled-up planned cost per activity; NOT a quantity',
    }


# ── reliability: what each signal is worth in THIS file ─────────────────────
def measure_reliability(context, units, keys, links, repetition,
                        code_coverages, location_axis):
    """Measure, from the file, how much each signal can be trusted here. 0..1 each.

    ``code_coverages`` must already be one coverage figure per *evidence class* — passing
    one per dimension would let a duplicated dimension raise the weight of the code
    signal, which is exactly what the de-duplication step exists to prevent.
    """
    steps = sorted(context.steps)
    n_steps = len(steps)
    unit_of = {}
    for u in units:
        for oid in u['members']:
            unit_of[oid] = u['unit_id']

    # identity: does the identity basis actually repeat across units in this file?
    seen_in = {}
    for oid in steps:
        key = keys.get(oid)
        if key:
            seen_in.setdefault(key, set()).add(unit_of.get(oid, oid))
    keyed = [o for o in steps if keys.get(o)]
    aligned = sum(1 for o in keyed if len(seen_in.get(keys[o], ())) >= 2)
    identity = (aligned / float(n_steps)) if n_steps else 0.0

    linked = sum(1 for o in steps if links.get(o))
    logic = (linked / float(n_steps)) if n_steps else 0.0

    external = 0
    for oid in steps:
        own = unit_of.get(oid)
        if any(unit_of.get(other) != own for other in links.get(oid, ())):
            external += 1
    neighbourhood = (external / float(n_steps)) if n_steps else 0.0

    codes = mean(code_coverages) if code_coverages else 0.0
    location = float(location_axis['coverage']) if location_axis else 0.0

    return {
        'codes': round(clamp01(codes), 4),
        'identity': round(clamp01(identity), 4),
        'location': round(clamp01(location), 4),
        'logic': round(clamp01(logic), 4),
        'neighbourhood': round(clamp01(neighbourhood), 4),
        # Structurally unavailable, so it can never contribute weight. See item E.
        'quantity': 0.0,
        'wbs': round(clamp01(repetition.get('wbs_repeat_share') or 0.0), 4),
    }


# ── support: how strongly THIS group's fronts agree, per signal ─────────────
def _mean_pairwise(units, fn):
    vals = []
    ids = sorted(range(len(units)), key=lambda i: units[i]['unit_id'])
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            vals.append(fn(units[ids[a]], units[ids[b]]))
    return mean(vals) if vals else 0.0


def _code_support(units, code_values):
    """Front-level coding consistency, one figure per evidence class.

    A dimension is evidence for "these fronts are one repeated family" in two structurally
    opposite ways, and both count: either every front carries the **same** value (the
    dimension names the family — a trade, a work type), or every front carries a
    **different** value (the dimension names the instance — the front marker). Random
    partial agreement is what carries no information, and that is what scores near zero.
    """
    per_dim = []
    for dim in sorted(code_values):
        assigned = code_values[dim]
        front_values = []
        for u in units:
            vals = [assigned[o] for o in sorted(u['members']) if assigned.get(o)]
            if vals:
                front_values.append(modal(vals))
        if len(front_values) < 2:
            continue
        n = len(front_values)
        same = rescale(concentration(front_values), 1.0 / n)
        distinct = spread(front_values)
        per_dim.append(max(same, distinct))
    return mean(per_dim) if per_dim else 0.0, len(per_dim)


def group_support(units, code_values, location_of, pair_metrics):
    """Per-signal support for one candidate group. ``{signal: (support, detail)}``.

    ``pair_metrics(a, b)`` returns the fingerprint comparison (``jaccard`` on step keys,
    ``order`` agreement) so the similarity formula has exactly one implementation, in the
    dedup engine that owns the fingerprint.
    """
    n = len(units)
    out = {}

    identity = _mean_pairwise(units, lambda a, b: pair_metrics(a, b)['jaccard'])
    out['identity'] = (identity, 'mean step-key overlap across %d fronts' % n)

    parents = [u.get('wbs_parent_name') or '' for u in units]
    if any(parents):
        wbs = rescale(concentration(parents), 1.0 / n)
        detail = 'fronts under one WBS parent template' if wbs >= 1.0 else \
            '%d of %d fronts share the modal WBS parent template' % (
                int(round(concentration(parents) * n)), n)
    else:
        wbs, detail = 0.0, 'no WBS parent context'
    out['wbs'] = (wbs, detail)

    codes, n_dims = _code_support(units, code_values)
    out['codes'] = (codes, 'consistent across %d code dimension(s)' % n_dims
                    if n_dims else 'no usable code dimension covers these fronts')

    loc_values = []
    for u in units:
        vals = sorted({location_of[o] for o in u['members'] if location_of.get(o)})
        if vals:
            loc_values.append(vals[0] if len(vals) == 1 else '|'.join(vals))
    if len(loc_values) >= 2:
        loc = spread(loc_values)
        out['location'] = (loc, '%d distinct location values across %d fronts'
                           % (len(set(loc_values)), len(loc_values)))
    else:
        out['location'] = (0.0, 'no location axis covers these fronts')

    if any(u.get('shape') for u in units):
        order = _mean_pairwise(units, lambda a, b: pair_metrics(a, b)['order'])
        shapes = ['|'.join('%s=%d' % (k, u['shape'][k]) for k in sorted(u['shape']))
                  for u in units]
        shape_agree = rescale(concentration(shapes), 1.0 / n)
        logic = 0.5 * order + 0.5 * shape_agree
        out['logic'] = (logic, 'internal order + logic shape agreement')
    else:
        # No front has any internal relationship: agreement here would be vacuous.
        out['logic'] = (0.0, 'no internal logic inside these fronts')

    ext = [u.get('neighbour_labels') or [] for u in units]
    if any(ext):
        nb = _mean_pairwise(units, lambda a, b: jaccard(a.get('neighbour_labels') or [],
                                                        b.get('neighbour_labels') or []))
        out['neighbourhood'] = (nb, 'mean overlap of what feeds/follows each front')
    else:
        out['neighbourhood'] = (0.0, 'these fronts have no external relationships')

    out['quantity'] = (0.0, QUANTITY_UNAVAILABLE_REASON)
    return {k: (round(clamp01(v), 4), d) for k, (v, d) in out.items()}


def evidence_block(reliability, supports):
    """Combine support x in-file reliability into the group's evidence record.

    The weight of a signal is its reliability normalised across the signals this file
    carries, so a file with no activity codes simply redistributes that weight rather
    than being penalised for it.
    """
    total = sum(reliability.get(name, 0.0) for name in SIGNAL_NAMES
                if reliability.get(name, 0.0) > 0.0)
    signals, score, supporting = [], 0.0, []
    for name in SIGNAL_NAMES:
        rel = float(reliability.get(name, 0.0))
        support, detail = supports.get(name, (0.0, ''))
        weight = (rel / total) if total else 0.0
        score += weight * support
        available = rel > 0.0
        if available and support >= SUPPORT_FLOOR:
            supporting.append(name)
        signals.append({
            'signal': name,
            'support': round(support, 4),
            'reliability': round(rel, 4),
            'weight': round(weight, 4),
            'available': available,
            'detail': detail,
        })
    return {
        'score': round(clamp01(score), 4),
        'supporting_signals': sorted(supporting),
        'supporting_count': len(supporting),
        'required_signals': MIN_SIGNALS,
        'support_floor': SUPPORT_FLOOR,
        'signals': signals,
    }
