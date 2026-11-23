"""Classify every costed activity — no "Unclassified" anywhere in the Narrative Report.

Ibrahim (Nov 2026 concerns round, approved):

* Contract Value is split by an ORDERED LIST of activity codes. Code 1 is the planner's scope
  code; Controlyx suggests codes 2, 3 … until every costed activity is covered, and the planner
  can edit the list. Each activity takes the value of the FIRST listed code it carries.
* Cost that carries none of the listed codes is named by its WBS in P6 (its own WBS folder).
* The lines always add up to 100 % of the total contract value.

The same mechanism fills every level of the Scope of Work description (type of work → building
→ element), see :mod:`p6_narrative.scope_detail`.

Pure logic, generic across any P6 coding scheme: every name comes from the imported file.
"""
from collections import Counter, OrderedDict, defaultdict

NON_WORK = {'StartMilestone', 'FinishMilestone', 'LOE', 'WBSSummary'}

# A WBS folder that names a floor / a trade / a kind of work — not the building itself.
_NOT_BUILDING = ('work', 'floor', 'ground', 'first', 'second', 'secound', 'third', 'roof',
                 'basement', 'interior', 'exterior', 'external', 'internal', 'facade', 'mep',
                 'elec', 'mech', 'plumb', 'plump', 'sanitar', 'drain', 'hvac', 'fire', 'finish',
                 'fix', 'scope', 'proposal', 'civil', 'arch', 'structur', 'concrete', 'steel',
                 'phase', 'stage', 'level')


def codes_of(act):
    return act.get('activity_codes') or {}


def first_value(act, codes):
    """The value of the FIRST code in ``codes`` the activity carries, else None."""
    cd = codes_of(act)
    for k in codes or []:
        v = cd.get(k)
        if v:
            return v
    return None


class WbsNames:
    """Own WBS folder name and the chain of parent folder names for an activity."""

    def __init__(self, wbs):
        self.wbs = wbs or {}

    def _name(self, wid):
        n = self.wbs.get(wid)
        if isinstance(n, dict):
            return n.get('name') or ''
        return getattr(n, 'name', '') or ''

    def _parent(self, wid):
        n = self.wbs.get(wid)
        if isinstance(n, dict):
            return n.get('parent_object_id') or n.get('parent_id')
        return getattr(n, 'parent_object_id', None) or getattr(n, 'parent_id', None)

    def own(self, act):
        wid = act.get('wbs_id')
        if wid in self.wbs:
            return self._name(wid) or 'No WBS'
        path = act.get('wbs_path') or ''
        return path.split(' > ')[-1].strip() if path else 'No WBS'

    def chain(self, act):
        """Parent folder names, nearest first (the activity's own folder excluded)."""
        out, seen = [], set()
        wid = self._parent(act.get('wbs_id'))
        while wid in self.wbs and wid not in seen and len(out) < 15:
            seen.add(wid)
            out.append(self._name(wid))
            wid = self._parent(wid)
        if not out and act.get('wbs_path'):
            out = [x.strip() for x in act['wbs_path'].split(' > ')[:-1]][::-1]
        return out

    def building(self, act):
        """No building code: the nearest WBS folder ABOVE the activity's own folder that names a
        building / area — not a floor, a trade or a kind of work."""
        chain = self.chain(act)
        for n in chain[:-1] if len(chain) > 1 else chain:      # never the project root
            low = (n or '').lower()
            if n and not any(k in low for k in _NOT_BUILDING):
                return n
        return chain[0] if chain else self.own(act)


def suggest_codes(items, first, code_types=None, exclude=(), min_values=1, min_specific=0.0,
                  accept=None):
    """Ordered code list that covers ``items`` [(act, weight)]: starts with ``first`` (a code or a
    list of codes), then greedily adds the code that covers the most still-uncovered weight AND is
    specific to that gap (a code whose value sits on nearly every activity — "Main WBS =
    Construction", "Cost loading = Cost" — scores low). A copy of a code already in use (same
    values on the same activities) is never suggested. Stops when everything is covered or no
    useful code is left."""
    chosen = [c for c in ([first] if isinstance(first, str) else list(first or [])) if c]
    allowed = set(code_types) if code_types else None
    exclude = set(exclude or ())
    total_v = Counter()
    nvals = defaultdict(set)
    for a, w in items:
        for k, v in codes_of(a).items():
            if v:
                total_v[(k, v)] += w
                nvals[k].add(v)
    left = [(a, w) for a, w in items if not first_value(a, chosen)]
    guard = 0
    while left and guard < 12:
        guard += 1
        cand = defaultdict(Counter)
        for a, w in left:
            for k, v in codes_of(a).items():
                if v and k not in chosen and k not in exclude and (allowed is None or k in allowed):
                    cand[k][v] += w
        cand = {k: c for k, c in cand.items() if len(nvals[k]) >= min_values}

        def duplicate(k):
            for u in chosen + list(exclude):
                both = [(codes_of(a).get(u), codes_of(a).get(k)) for a, _ in items
                        if codes_of(a).get(k) and codes_of(a).get(u)]
                if both and all(x == y for x, y in both) and nvals[k] <= nvals[u]:
                    return True
            return False

        cand = {k: c for k, c in cand.items() if not duplicate(k)}
        if accept is not None:
            cand = {k: c for k, c in cand.items() if accept(k)}
        if not cand:
            break

        def score(k):
            cov = sum(cand[k].values()) or 1e-9
            spec = sum(min(1.0, cv / (total_v[(k, v)] or 1e-9)) * cv for v, cv in cand[k].items()) / cov
            return cov * spec, spec
        k = max(sorted(cand), key=lambda c: score(c)[0])
        if score(k)[1] < min_specific:
            break
        chosen.append(k)
        left = [(a, w) for a, w in left if not first_value(a, chosen)]
    return chosen


def clean_codes(codes, code_types):
    """Keep only real code types, in order, no repeats."""
    ct = set(code_types or [])
    return list(OrderedDict.fromkeys(c for c in (codes or []) if c and c in ct))


def costed_items(data):
    bac = data.bac_by_activity or {}
    return [(a, float(bac.get(a.get('object_id')) or 0.0)) for a in data.activities.values()
            if (bac.get(a.get('object_id')) or 0) > 0]


def value_codes(data, setup, first_code):
    """The Contract Value code list: the planner's own list (setup['value_codes']) when given,
    else ``first_code`` followed by Controlyx's suggestions."""
    setup = setup or {}
    own = clean_codes(setup.get('value_codes'), data.activity_code_types)
    if own:
        return own, False
    if not first_code:
        return [], True
    return suggest_codes(costed_items(data), first_code, data.activity_code_types), True


def shares_to_100(values, total, decimals=1):
    """Percent shares rounded to ``decimals`` that add up to EXACTLY 100 (largest remainder) —
    Ibrahim: "to give the total finally 100%"."""
    if not total or not values:
        return [0.0 for _ in values]
    unit = 10 ** decimals
    raw = [100.0 * unit * v / total for v in values]
    floors = [int(r) for r in raw]
    short = 100 * unit - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: -(raw[i] - floors[i]))
    for i in order[:max(0, short)]:
        floors[i] += 1
    return [f / unit for f in floors]


def building_like(values):
    """True when most values read like places (a building / area / zone), not a kind of work —
    so a BOQ or trade code is never suggested as the building level."""
    vals = [v for v in values if v]
    if not vals:
        return False
    bad = sum(1 for v in vals if any(k in v.lower() for k in _NOT_BUILDING))
    return bad <= 0.4 * len(vals)


def value_split(data, codes):
    """Split the full contract value by ``codes`` (first listed code each activity carries);
    what carries none of them is named by its own WBS folder. Rows add up to the total.

    Returns {'total', 'rows': [{name, amount, pct, source}], 'coverage': [{code, pct}],
             'wbs_pct'} — ``source`` is the code that named the line, or 'WBS'."""
    items = costed_items(data)
    total = round(sum(w for _, w in items), 2)
    names = WbsNames(data.wbs)
    amount = OrderedDict()
    source = {}
    cov = Counter()
    for a, w in items:
        cd = codes_of(a)
        hit = next((k for k in codes if cd.get(k)), None)
        if hit:
            name = cd[hit]
            cov[hit] += w
        else:
            name = names.own(a)
            hit = 'WBS'
            cov['WBS'] += w
        amount[name] = amount.get(name, 0.0) + w
        source.setdefault(name, hit)
    ordered = sorted(amount.items(), key=lambda kv: -kv[1])
    pcts = shares_to_100([v for _, v in ordered], total)
    rows = [{'name': n, 'amount': round(v, 2), 'pct': p, 'source': source[n]}
            for (n, v), p in zip(ordered, pcts)]
    coverage = [{'code': k, 'pct': round(100.0 * cov[k] / total, 1) if total else 0.0}
                for k in codes if cov.get(k)]
    return {'total': total, 'rows': rows, 'coverage': coverage,
            'wbs_pct': round(100.0 * cov.get('WBS', 0) / total, 1) if total else 0.0}
