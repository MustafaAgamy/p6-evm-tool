"""§11 Sequence of Work — dependency-derived execution-sequence charts.

The planner picks, before running, one or more "sequence analyses". Each analysis is
**1 or 2 activity codes** (fully flexible, the same spirit as §7's code picker):

* **1 code C** — a single chevron flow of C's values in the order the schedule's own
  DEPENDENCIES dictate (net-dominant predecessor→successor between values; earliest
  planned start breaks ties / cycles). A "general sequence".
* **2 codes [G, S]** — GROUP by G's value; for each G value a chevron flow of S's values
  in dependency order; groups whose ordered step list is IDENTICAL collapse into one
  labelled entry (reuse the range labeller, e.g. "Silos 1–10"). The per-building chart.

The algorithm is the one validated in the approved standalone mock-up (``mock_s11.py``):
value→value edges from the relationships, net-dominant direction per unordered pair, a
Kahn topological sort with an earliest-start tie-break, and the range-label grouping.
Pure logic, generic across any P6 coding scheme; never crashes on odd data and always
returns a usable dict.
"""
import re
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime

from p6_narrative.scope import _area_label, default_scope_codes

# Milestones / summary / level-of-effort activities are not work steps.
_NON_STEP = {'StartMilestone', 'FinishMilestone', 'LOE', 'WBSSummary'}
_FAR = datetime.max


# ── small helpers ───────────────────────────────────────────────────────────────
def _rel_pair(r):
    """(predecessor object-id, successor object-id) from a relationship dict, tolerant of
    the two key spellings the parsers use (``pred_id``/``succ_id`` and the long forms)."""
    if not isinstance(r, dict):
        return None, None
    p = (r.get('pred_id') or r.get('predecessor_id')
         or r.get('pred') or r.get('predecessor'))
    s = (r.get('succ_id') or r.get('successor_id')
         or r.get('succ') or r.get('successor'))
    return p, s


def _base_value(v):
    """Aggregate a STEP value to its BASE by stripping any trailing ' - <area>' suffix
    (so 'Pile Works - Main Silos' → 'Pile Works'); mirrors the §7 area-suffix strip."""
    if not v:
        return None
    try:
        return re.split(r'\s*[-–]\s', str(v), 1)[0].strip() or None
    except (TypeError, ValueError):
        return str(v).strip() or None


def _as_dt(v):
    if isinstance(v, datetime):
        return v
    if v in (None, ''):
        return None
    try:
        return datetime.fromisoformat(str(v)[:19])
    except (TypeError, ValueError):
        return None


def _skey(act):
    """Sortable earliest-start key for one activity — dated activities first (chronological),
    undated last, so ``min``/``sort`` over these keys never compares ``datetime`` with ``None``."""
    d = _as_dt((act or {}).get('planned_start'))
    return (0, d) if d is not None else (1, _FAR)


def _code_of(act, dim):
    return (act.get('activity_codes') or {}).get(dim) if dim else None


# ── core dependency ordering (the mock's _sequence_for_building, generalised) ─────
def _order_values(oids, by_oid, val_of, rel_pairs):
    """Order the distinct values present among ``oids`` by DEPENDENCY.

    A topological order of the net-dominant value→value edges derived from the relationships
    among ``oids`` (an activity of value X predecessor of an activity of value Y, X≠Y), ties
    and cycle remainders broken by earliest planned start (then name). ``val_of`` maps an
    activity object-id → its (already normalised) value, or ``None``. Falls back to pure
    earliest-start order when there is no usable link."""
    oidset = set(oids)

    # earliest-start key + presence per value, in first-seen order
    est = OrderedDict()
    for oid in oids:
        v = val_of.get(oid)
        if not v:
            continue
        k = _skey(by_oid.get(oid))
        if v not in est or k < est[v]:
            est[v] = k
    values = list(est.keys())
    if len(values) <= 1:
        return values

    def skey(v):
        return (est.get(v, (1, _FAR)), v)

    # raw directed edge counts between DIFFERENT values among this scope's relationships
    edge = Counter()
    for p, s in rel_pairs:
        if p in oidset and s in oidset:
            vp, vs = val_of.get(p), val_of.get(s)
            if vp and vs and vp != vs:
                edge[(vp, vs)] += 1

    # net-dominant direction per unordered pair (a tie leaves no edge → start decides)
    net = {}
    seen = set()
    for (a, b) in edge:
        pair = frozenset((a, b))
        if pair in seen:
            continue
        seen.add(pair)
        fwd, rev = edge.get((a, b), 0), edge.get((b, a), 0)
        if fwd > rev:
            net[(a, b)] = fwd - rev
        elif rev > fwd:
            net[(b, a)] = rev - fwd

    # Kahn topological sort, earliest-start (then name) tie-break
    succ = defaultdict(list)
    indeg = {v: 0 for v in values}
    for (a, b) in net:
        succ[a].append(b)
        indeg[b] += 1

    avail = [v for v in values if indeg[v] == 0]
    order, placed = [], set()
    while avail:
        avail.sort(key=skey)
        v = avail.pop(0)
        if v in placed:
            continue
        order.append(v)
        placed.add(v)
        for nb in succ[v]:
            indeg[nb] -= 1
            if indeg[nb] == 0 and nb not in placed:
                avail.append(nb)
    leftover = [v for v in values if v not in placed]      # any cycle remainder
    leftover.sort(key=skey)
    order.extend(leftover)
    return order


# ── narratives ───────────────────────────────────────────────────────────────────
def _names_sentence(names):
    names = [str(n) for n in names if n]
    if not names:
        return ''
    if len(names) == 1:
        return names[0]
    return ', '.join(names[:-1]) + ' and ' + names[-1]


def _single_narrative(code, steps):
    names = [s['name'] for s in steps]
    if not names:
        return ('No general sequence could be derived for %s — the activities carry no values '
                'for this code, or none are linked.' % code)
    if len(names) == 1:
        return ('All work classified by %s falls under a single stage, %s, so no ordered '
                'sequence applies.' % (code, names[0]))
    chain = ' → '.join(names)
    return ('Read from the baseline logic, the work classified by %s runs in the order %s. '
            'This order is taken from the dependency links between the activities rather than '
            'assumed, so it reflects how the schedule is actually built.' % (code, chain))


def _grouped_narrative(gcode, scode, groups):
    if not groups:
        return ('No per-%s sequence could be derived — the activities carry no %s values, or '
                'none are linked.' % (gcode, scode))
    dom = max(groups, key=lambda g: (g['count'], len(g['steps'])))
    chain = ' → '.join(s['name'] for s in dom['steps'])
    if dom['count'] > 1:
        return ('The sequence below is built per %s from the baseline dependencies — each %s '
                'value placed in the order the schedule runs it. Structures whose order is '
                'identical are grouped into one entry: for example %s share the sequence %s.'
                % (gcode, scode, dom['label'], chain))
    return ('The sequence below is built per %s from the baseline dependencies. The leading '
            'structure, %s, runs %s.' % (gcode, dom['label'], chain))


# ── one analysis (single code) ────────────────────────────────────────────────────
def _single(code, activities, by_oid, rel_pairs):
    val_of = {}
    counts = Counter()
    for a in activities:
        if a.get('task_type') in _NON_STEP:
            continue
        v = _base_value(_code_of(a, code))
        if v:
            val_of[a.get('object_id')] = v
            counts[v] += 1
    order = _order_values(list(val_of.keys()), by_oid, val_of, rel_pairs)
    steps = [{'name': v, 'count': counts[v]} for v in order]
    return {
        'codes': [code],
        'kind': 'single',
        'title': 'General sequence — %s' % code,
        'steps': steps,
        'narrative': _single_narrative(code, steps),
    }


# ── one analysis (two codes: group-by G → sequenced S) ────────────────────────────
def _grouped(gcode, scode, activities, by_oid, rel_pairs):
    by_group = OrderedDict()          # G value (NOT base-stripped) → [object-ids]
    sval_of = {}                      # object-id → base-normalised S value
    for a in activities:
        if a.get('task_type') in _NON_STEP:
            continue
        oid = a.get('object_id')
        sval_of[oid] = _base_value(_code_of(a, scode))
        gval = _code_of(a, gcode)     # group values are kept verbatim (not stripped)
        if gval:
            by_group.setdefault(gval, []).append(oid)

    per_group = OrderedDict()         # G value → (ordered S steps, start-key)
    for gval, oids in by_group.items():
        order = _order_values(oids, by_oid, sval_of, rel_pairs)
        start = min((_skey(by_oid.get(o)) for o in oids), default=(1, _FAR))
        per_group[gval] = (order, start)

    # collapse groups whose ordered step list is IDENTICAL into one entry
    buckets = OrderedDict()
    for gval, (order, start) in per_group.items():
        b = buckets.setdefault(tuple(order), {'members': [], 'starts': []})
        b['members'].append(gval)
        b['starts'].append(start)

    groups, no_code = [], []
    for key, b in buckets.items():
        if not key:                   # no S value at all → a one-line note, not a chevron
            no_code.extend(b['members'])
            continue
        groups.append({
            'label': _area_label(b['members']),
            'count': len(b['members']),
            'members': list(b['members']),
            'steps': [{'name': v} for v in key],
            '_start': min(b['starts']),
        })
    groups.sort(key=lambda g: g['_start'])
    for g in groups:
        g.pop('_start', None)
    no_code.sort(key=lambda gv: per_group[gv][1])

    result = {
        'codes': [gcode, scode],
        'kind': 'grouped',
        'title': '%s → %s' % (gcode, scode),
        'groups': groups,
        'narrative': _grouped_narrative(gcode, scode, groups),
    }
    if no_code:
        result['no_code'] = list(no_code)
    return result


# ── validation of the planner's picks + a sensible default ────────────────────────
def _normalise_analyses(analyses, code_types, setup):
    """Turn the raw ``setup['sequence_codes']`` into a clean list of 1-or-2-code picks.

    Each pick is validated against the file's code types, deduped within itself, and capped
    at two codes. An analysis whose FIRST code is missing/invalid is ignored entirely. When
    nothing usable is given, a sensible default is built from the auto-detected scope cascade
    (general sequence on the discipline code, plus a per-building area→work-type pair)."""
    valid = set(code_types or [])

    def _default_src():
        dsc = default_scope_codes(code_types, setup or {})
        out = []
        if dsc:
            out.append({'codes': [dsc[0]]})
        if len(dsc) >= 3:
            out.append({'codes': [dsc[1], dsc[2]]})
        return out

    def _pick(src):
        picks = []
        for item in (src or []):
            if isinstance(item, dict):
                raw = item.get('codes')
            elif isinstance(item, (list, tuple)):
                raw = list(item)
            else:
                raw = [item]
            raw = [c for c in (raw or [])]
            if not raw or not raw[0] or raw[0] not in valid:
                continue              # ignore an analysis whose first code is missing/invalid
            codes, seen = [], set()
            for c in raw:
                if c and c in valid and c not in seen:
                    seen.add(c)
                    codes.append(c)
            picks.append(codes[:2])   # 1 or 2 codes only
        return picks

    # Validate the planner's picks; if NONE survive (empty, or all stale codes from another
    # file) fall back to the auto-detected default — mirroring §6/§7, so §11 never goes blank.
    picks = _pick(analyses) if analyses else _pick(_default_src())
    if not picks:
        picks = _pick(_default_src())
    return picks


# ── public entry point ────────────────────────────────────────────────────────────
def sequence_analyses(activities, wbs, relationships, code_types=None, analyses=None,
                      setup=None):
    """Return the §11 payload — ``{'analyses': [ {…}, … ]}``.

    ``activities``     — the parsed activity dicts (``list(data.activities.values())``).
    ``relationships``  — the parsed relationship dicts (``pred_id``/``succ_id``).
    ``analyses``       — ``setup['sequence_codes']``: a list of ``{'codes': [A]}`` or
                         ``{'codes': [G, S]}`` (code-type names). Empty/None → a sensible
                         default (general sequence + per-building pair) from the scope cascade.

    Never raises; always returns a usable dict (an empty ``analyses`` list when truly nothing
    can be built)."""
    activities = list(activities or [])
    code_types = list(code_types or [])
    setup = setup or {}

    by_oid = {}
    for a in activities:
        oid = a.get('object_id')
        if oid is not None:
            by_oid[oid] = a

    rel_pairs = []
    for r in (relationships or []):
        p, s = _rel_pair(r)
        if p is not None and s is not None:
            rel_pairs.append((p, s))

    picks = _normalise_analyses(analyses, code_types, setup)

    out = []
    for codes in picks:
        try:
            if len(codes) == 1:
                out.append(_single(codes[0], activities, by_oid, rel_pairs))
            else:
                out.append(_grouped(codes[0], codes[1], activities, by_oid, rel_pairs))
        except Exception:             # pragma: no cover — one bad pick never breaks the rest
            continue
    return {'analyses': out}
