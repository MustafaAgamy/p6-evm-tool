"""Baseline Revision Comparison — scope-by-code view (neutral, progress-free).

Groups the *added* and *removed* activities of a revision by each activity-code
dimension the export carries (``data.activity_code_types``) and by WBS top-branch,
so a planner can see **where** the scope moved — which building, discipline, trade
or WBS branch gained or lost work — without any judgement about whether the change
is right. It also lists every matched activity whose activity-code tagging changed
between the two revisions (``recoded``).

Pure and side-effect free: reads the two parsed ``ScheduleData`` objects and the
``match`` dict from :func:`p6_revcompare.matching.match_activities`, returns a
plain JSON-serialisable dict. Every path is guarded — a file with no activity
codes simply yields empty groupings, never an exception.

Public API:
    build_codes(rev0, rev1, match) -> dict  (report['codes'])
"""

_WBS_SEP = ' > '

# Dimension-name hints used to pick a "building" and a "scope/discipline" tag for
# an activity out of whatever activity-code dimensions the export happens to carry.
_BUILDING_HINTS = ('build',)
_SCOPE_HINTS = ('discipline', 'scope', 'trade')


def _codes_of(act):
    """The activity's ``{dimension: value}`` map, guarded to an empty dict."""
    return (act.get('activity_codes') or {}) if act else {}


def _pick_by_hint(codes, hints):
    """Return the code value whose dimension name contains any hint (case-insensitive),
    falling back to the first available code value, or None when the activity has none."""
    if not codes:
        return None
    for dim, val in codes.items():
        low = str(dim).lower()
        if any(h in low for h in hints) and val not in (None, ''):
            return val
    # Fall back to the first non-empty code value in a stable order.
    for dim in sorted(codes):
        val = codes[dim]
        if val not in (None, ''):
            return val
    return None


def _wbs_top(path):
    """Top-level WBS branch of a full ``a > b > c`` path (or None when absent)."""
    if not path:
        return None
    return str(path).split(_WBS_SEP, 1)[0].strip() or None


def _dimensions(rev0, rev1):
    """Union of activity-code dimension names across both revisions, order-stable."""
    out = []
    for data in (rev1, rev0):
        for dim in (getattr(data, 'activity_code_types', None) or []):
            if dim not in out:
                out.append(dim)
    return out


def _category_for(act, dim):
    """The activity's value in one dimension, or an explicit uncoded label."""
    val = _codes_of(act).get(dim)
    if val in (None, ''):
        return '(uncoded)'
    return val


def _wbs_category(act):
    top = _wbs_top(act.get('wbs_path') if act else None)
    return top or '(no WBS)'


def _scope_by_code(dimensions, added, removed):
    """{dim: [{category, added, removed}]} counting added/removed activities per code
    value, plus a synthetic 'WBS' dimension keyed on the WBS top-branch."""
    out = {}

    def tally(categoriser, key):
        counts = {}   # category -> [added, removed]
        for a in added:
            c = categoriser(a)
            counts.setdefault(c, [0, 0])[0] += 1
        for a in removed:
            c = categoriser(a)
            counts.setdefault(c, [0, 0])[1] += 1
        rows = [{'category': cat, 'added': n[0], 'removed': n[1]}
                for cat, n in counts.items()]
        # Biggest scope movements first; stable tie-break on the category name.
        rows.sort(key=lambda r: (-(r['added'] + r['removed']), str(r['category'])))
        out[key] = rows

    for dim in dimensions:
        tally(lambda a, _dim=dim: _category_for(a, _dim), dim)
    tally(_wbs_category, 'WBS')
    return out


def _itemise(activities):
    """[{id, name, building, wbs, scope}] for a list of activities (added or removed)."""
    rows = []
    for a in activities:
        codes = _codes_of(a)
        rows.append({
            'id': a.get('id'),
            'name': a.get('name') or a.get('id'),
            'building': _pick_by_hint(codes, _BUILDING_HINTS),
            'wbs': a.get('wbs_path') or None,
            'scope': _pick_by_hint(codes, _SCOPE_HINTS),
            # full code map (incl. a synthetic 'WBS' top branch) so the scope analysis can
            # filter added/removed by any activity-code dimension, live + in the PDF.
            'codes': {**codes, 'WBS': _wbs_top(a.get('wbs_path'))},
        })
    return rows


def _recoded(pairs):
    """[{id, name, code_type, before, after}] — one row per matched activity + dimension
    whose activity-code value changed (added, removed or altered value)."""
    rows = []
    for p in pairs or []:
        a0, a1 = p.get('act0') or {}, p.get('act1') or {}
        c0, c1 = _codes_of(a0), _codes_of(a1)
        code = p.get('canonical') or a1.get('id') or a0.get('id')
        name = a1.get('name') or a0.get('name') or code
        for dim in sorted(set(c0) | set(c1)):
            b, af = c0.get(dim), c1.get(dim)
            bn = b if b not in ('',) else None
            an = af if af not in ('',) else None
            if bn == an:
                continue
            rows.append({'id': code, 'name': name, 'code_type': dim,
                         'before': bn, 'after': an})
    return rows


def build_codes(rev0, rev1, match):
    """Scope-by-code evidence for one baseline→baseline comparison.

    Returns ``report['codes']``:
        dimensions    [dim names carried by either revision]
        scope_by_code {dim: [{category, added, removed}]}  (+ a 'WBS' pseudo-dim)
        added         [{id, name, building, wbs, scope}]   (newly-present activities)
        removed       [{id, name, building, wbs, scope}]   (dropped activities)
        recoded       [{id, name, code_type, before, after}]  (matched, code value changed)
    """
    match = match or {}
    added_acts = match.get('added') or []
    removed_acts = match.get('removed') or []
    dimensions = _dimensions(rev0, rev1)
    return {
        'dimensions': dimensions,
        'scope_by_code': _scope_by_code(dimensions, added_acts, removed_acts),
        'added': _itemise(added_acts),
        'removed': _itemise(removed_acts),
        'recoded': _recoded(match.get('pairs')),
    }
