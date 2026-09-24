"""Scope-of-Work discussion, derived from the schedule.

Two shapes, primary first:

* :func:`scope_prose` — the target (Ibrahim, Comment 6): a BRIEF prose outline,
  per **trade** x per **building/area**, read from the activity codes. Each area
  reads "<Area> <Trade> works consist of: e1; e2; …" and, when several areas decode
  to the SAME element set, only the first is described in full — the rest collapse to
  one line "<Areas>: same scope as <first>". Returns ``None`` (so the caller falls
  back to the block prose below) when the file has no usable trade/area codes.

* :func:`scope_blocks` — the fallback: one block per discipline (the Type-of-Works /
  trade code when the file has one, else the top-level WBS branch), listing that
  discipline's WBS work-packages with a short factual paragraph from the real counts.

Pure logic; generic across any construction project — no client names hardcoded.
"""
import re
from collections import OrderedDict
from datetime import datetime

from p6_narrative.sequence import pick_discipline_dim
from p6_narrative.util import top_wbs_name

_NON_WORK = {'StartMilestone', 'FinishMilestone', 'LOE', 'WBSSummary'}

# Code-dimension pickers for the per-trade x per-area prose. Substring hints, matched
# case-insensitively against whatever the file happens to call its dimensions.
_TRADE_HINTS = ('type of works', 'type of work', 'discipline', 'trade', 'craft')
_AREA_HINTS = ('area', 'building', 'zone', 'location', 'unit', 'facility',
               'block', 'sector', 'silo', 'structure', 'system')
_ELEMENT_HINTS = ('type of work', 'work type', 'worktype', 'element', 'scope',
                  'work package', 'activity type', 'work')
# The work-type cascade level (§6 per-discipline breakdown): more specific than the
# discipline code — e.g. "Type of Civil Work" (Pile Works / Elevated Raft / Columns).
_WORKTYPE_HINTS = ('type of civil work', 'type of work', 'work type', 'element',
                   'activity name', 'structure', 'work')
# Trade display order (Ibrahim): Civil, Mechanical, Steel, EQP, Cable, then the rest.
_TRADE_ORDER = (('civil',), ('mechanical', 'mech'), ('steel',),
                ('eqp', 'equipment'), ('cable', 'electric'))
_ELEMENT_CAP = 14


def _start_key(dt):
    """Sort key that pushes activities with no start date to the end."""
    if dt is None:
        return (1, datetime.max)
    if isinstance(dt, datetime):
        return (0, dt)
    try:
        return (0, datetime.fromisoformat(str(dt)[:19]))
    except ValueError:
        return (1, datetime.max)


def _pick_dim(code_types, hints, used):
    # Hints are tried in priority order (a more specific hint wins): e.g. "type of works"
    # must match a "Type of Works" code before the generic "trade" matches "Trade Design".
    avail = [d for d in (code_types or []) if d not in used]
    for h in hints:
        for dim in avail:
            if h in (dim or '').lower():
                return dim
    return None


def _trade_rank(trade):
    low = (trade or '').lower()
    for i, group in enumerate(_TRADE_ORDER):
        if any(k in low for k in group):
            return i
    return len(_TRADE_ORDER)


def _compact_areas(names):
    """Compact a run of area labels: contiguous numeric ones fold to "A2-A10",
    everything else joins with ", ". Generic across any naming convention."""
    if len(names) == 1:
        return names[0]
    parsed = []
    for n in names:
        m = re.match(r'^(.*?)(\d+)$', (n or '').strip())
        if not m:
            return ', '.join(names)
        parsed.append((m.group(1), int(m.group(2)), n))
    if len({p[0] for p in parsed}) == 1:
        parsed.sort(key=lambda p: p[1])
        nums = [p[1] for p in parsed]
        if nums == list(range(nums[0], nums[0] + len(nums))):
            return f'{parsed[0][2]}-{parsed[-1][2]}'
    return ', '.join(names)


def _sentence(trade, area, elements):
    if trade and area:
        label = f'{area} {trade} works'
    elif trade:
        label = f'{trade} works'
    elif area:
        label = f'{area} works'
    else:
        label = 'The works'
    return f"{label} consist of: {'; '.join(elements)}."


def scope_prose(activities, wbs, code_types=None, bac_by_activity=None):
    """Return ``{'trades': [...]}`` — the per-trade x per-area prose outline — or
    ``None`` when the file has no usable trade/area codes (caller falls back).

    Each trade: ``{trade, activity_count, areas: [entry, …]}`` where a described entry
    is ``{area, elements:[str], activity_count, sentence}`` and a collapsed entry is
    ``{areas, members:[str], same_as, sentence}``.
    """
    used = set()
    trade_dim = _pick_dim(code_types, _TRADE_HINTS, used)
    if trade_dim:
        used.add(trade_dim)
    area_dim = _pick_dim(code_types, _AREA_HINTS, used)
    if area_dim:
        used.add(area_dim)
    element_dim = _pick_dim(code_types, _ELEMENT_HINTS, used)
    if element_dim:
        used.add(element_dim)

    if not trade_dim and not area_dim:
        return None                      # nothing to build the axes from → fallback

    def code(act, dim):
        return (act.get('activity_codes') or {}).get(dim) if dim else None

    def element_of(act):
        if element_dim:
            val = code(act, element_dim)
            if val:
                return val
        # fall back to the activity's WBS work-package name
        return (wbs.get(act.get('wbs_id')) or {}).get('name') or 'General'

    # trade -> area -> ordered list of activities (schedule order within each)
    trades = OrderedDict()
    for act in activities:
        if act.get('task_type') in _NON_WORK:
            continue
        trade = code(act, trade_dim)
        area = code(act, area_dim)
        if trade is None and area is None:
            continue                     # no axis value at all — can't place it
        areas = trades.setdefault(trade, OrderedDict())
        areas.setdefault(area, []).append(act)

    if not trades:
        return None

    out_trades = []
    for trade in sorted(trades, key=lambda t: (_trade_rank(t), _first_index(trades, t))):
        areas = trades[trade]
        # order areas by earliest scheduled activity (representative = earliest)
        ordered_areas = sorted(
            areas, key=lambda a: min(_start_key(x.get('planned_start')) for x in areas[a]))
        count = sum(len(areas[a]) for a in ordered_areas)

        signatures = OrderedDict()       # frozenset(elements) -> {rep, elements, members}
        for area in ordered_areas:
            acts = sorted(areas[area], key=lambda x: _start_key(x.get('planned_start')))
            elements, seen = [], set()
            for a in acts:
                el = element_of(a)
                if el and el not in seen:
                    seen.add(el)
                    elements.append(el)
            if not elements:
                continue
            sig = frozenset(elements)
            if sig in signatures:
                signatures[sig]['members'].append(area)
            else:
                signatures[sig] = {'rep': area, 'elements': elements[:_ELEMENT_CAP],
                                   'extra': max(0, len(elements) - _ELEMENT_CAP),
                                   'members': [], 'count': len(areas[area])}

        entries = []
        for sig in signatures.values():
            els = list(sig['elements'])
            if sig['extra']:
                els.append(f"and {sig['extra']} more")
            entries.append({
                'area': sig['rep'],
                'elements': sig['elements'],
                'activity_count': sig['count'],
                'sentence': _sentence(trade, sig['rep'], els),
            })
            if sig['members']:
                label = _compact_areas(sig['members'])
                entries.append({
                    'areas': label,
                    'members': list(sig['members']),
                    'same_as': sig['rep'],
                    'sentence': f'{label}: same scope as {sig["rep"]}.',
                })
        if entries:
            out_trades.append({'trade': trade, 'activity_count': count, 'areas': entries})

    return {'trades': out_trades} if out_trades else None


def _first_index(ordered_dict, key):
    for i, k in enumerate(ordered_dict):
        if k == key:
            return i
    return len(ordered_dict)


def scope_blocks(activities, wbs, code_types=None, bac_by_activity=None, discipline_dim=None):
    """Return ``[{discipline, packages, activity_count, cost, paragraph}]`` — one
    block per discipline, ordered by first appearance."""
    if discipline_dim is None:
        discipline_dim = pick_discipline_dim(code_types)
    bac = bac_by_activity or {}
    groups = OrderedDict()
    for act in activities:
        if act.get('task_type') in _NON_WORK:
            continue
        disc = (act.get('activity_codes') or {}).get(discipline_dim) if discipline_dim else None
        disc = disc or top_wbs_name(act.get('wbs_id'), wbs) or 'General'
        grp = groups.setdefault(disc, {'packages': OrderedDict(), 'cost': 0.0, 'count': 0})
        pkg = (wbs.get(act.get('wbs_id')) or {}).get('name') or 'General'
        grp['packages'][pkg] = grp['packages'].get(pkg, 0) + 1
        grp['cost'] += bac.get(act.get('object_id'), 0.0) or 0.0
        grp['count'] += 1

    blocks = []
    for disc, grp in groups.items():
        pkgs = list(grp['packages'].keys())
        blocks.append({
            'discipline': disc,
            'packages': pkgs,
            'activity_count': grp['count'],
            'cost': round(grp['cost'], 2),
            'paragraph': _describe(disc, pkgs, grp['count']),
        })
    return blocks


_BUILDING_CAP = 10
_ELEMENTS_PER_BUILDING = 16


def default_scope_codes(code_types, setup=None):
    """The auto-detected ORDERED cascade of activity codes (discipline → area → work type),
    used when the planner has not picked their own list. Also surfaced to the setup UI so the
    picker opens pre-populated with these sensible defaults (which the planner can then edit)."""
    setup = setup or {}
    used = set()
    codes = []
    for key, hints, allow_fallback in (('tow_code_scope', _TRADE_HINTS, True),
                                       ('building_code', _AREA_HINTS, False),
                                       ('worktype_code', _WORKTYPE_HINTS, False)):
        dim = setup.get(key) or _pick_dim(code_types, hints, used)
        if not dim and allow_fallback:
            dim = pick_discipline_dim(code_types)
        if dim and dim not in used:
            used.add(dim)
            codes.append(dim)
    return codes


def scope_sections(activities, wbs, bac_by_activity=None, code_types=None, setup=None,
                   currency=''):
    """Flexible, cost-weighted Scope of Work (§7).

    The planner picks — before running — an ORDERED list of activity codes in
    ``setup['scope_codes']`` (any number, chosen from all the file's codes). The analysis
    cross-filters through them IN ORDER: level 1 is the primary split (drives the §7.1 chart),
    and each deeper picked code nests inside the level above it, cost-weighted. Sibling
    branches that share the same sub-structure are grouped (e.g. "Silos 1–10"). When no list
    is given, the discipline / building / work-type codes are auto-detected as a default.

    Returns::

        {'total', 'unit', 'codes': [code names, in order],
         'disciplines': [{name, cost, pct}],           # level-1 split → §7.1 chart (pct of total)
         'cascade':     [ {name, cost, pct, count?, each?, children?:[…]} ],  # N-level tree, grouped
         'narrative':   str}

    Generic across any P6 coding scheme; always returns a usable structure.
    """
    setup = setup or {}
    bac = bac_by_activity or {}

    def code(act, dim):
        return (act.get('activity_codes') or {}).get(dim) if dim else None

    def cost_of(acts):
        return sum(bac.get(a.get('object_id'), 0.0) or 0.0 for a in acts)

    # ── the ordered cascade of activity codes (planner pick, else auto-detected default) ──
    codes = [c for c in (setup.get('scope_codes') or []) if c and c in (code_types or [])]
    if not codes:
        codes = default_scope_codes(code_types, setup)
    # defend the engine: keep only real code types, in order, with no repeats — a duplicate pick
    # would nest a code inside itself, and a stale override key could name a code absent from the file
    codes = list(dict.fromkeys(c for c in codes if c and c in (code_types or [])))

    work = [a for a in activities if a.get('task_type') not in _NON_WORK]
    total_cost = cost_of(work)

    # ── level-1 split for the §7.1 chart (uncoded → "Unclassified", to match §6 doughnut) ──
    disciplines = []
    if codes:
        g1 = OrderedDict()
        for a in work:
            g1.setdefault(code(a, codes[0]) or 'Unclassified', []).append(a)
        for d in sorted(g1, key=lambda x: (-cost_of(g1[x]), _trade_rank(x), _first_index(g1, x))):
            c = round(cost_of(g1[d]), 2)
            disciplines.append({'name': d, 'cost': c,
                                'pct': round(100 * c / total_cost, 1) if total_cost > 0 else 0.0})

    # ── the N-level cross-filtered cascade tree (each deeper picked code nested; siblings
    #    with an identical sub-structure grouped; pct is share of the PARENT level) ──
    def build(acts, level, base):
        dim = codes[level]
        grp = OrderedDict()
        for a in acts:
            v = code(a, dim)
            if not v:
                continue
            grp.setdefault(v, []).append(a)
        raw = []
        for v, g in grp.items():
            c = round(cost_of(g), 2)
            if c <= 0:
                continue
            node = {'name': v, 'cost': c}
            if level + 1 < len(codes):
                kids = build(g, level + 1, c)
                if kids:
                    node['children'] = kids
            raw.append(node)
        raw.sort(key=lambda n: -n['cost'])
        grouped = _group_identical(raw)
        for n in grouped:
            n['pct'] = round(100 * n['cost'] / base, 1) if base > 0 else 0.0
        return grouped

    cascade = build(work, 0, total_cost) if codes else []

    payload = {
        'total': round(total_cost, 2),
        'codes': list(codes),
        'disciplines': disciplines,
        'cascade': cascade,
    }
    if currency:
        payload['unit'] = currency
    payload['narrative'] = _scope_narrative(payload, currency)
    return payload


def _node_sig(node):
    """Structural signature of a cascade node by its descendant NAMES (ignoring cost), so two
    siblings with the same sub-tree (e.g. Silo 1 and Silo 2) can be grouped."""
    return (node.get('name'),
            tuple(_node_sig(k) for k in (node.get('children') or [])))


def _group_identical(nodes):
    """Merge sibling cascade nodes whose sub-structure is identical into one grouped node
    (label = compact range like "Silos 1–10", cost = per-item when equal else the total)."""
    buckets = OrderedDict()
    singles = []
    for n in nodes:
        kids = n.get('children') or []
        if not kids:
            singles.append(n)          # a leaf is a distinct scope item — never grouped
            continue
        # group key = the sub-tree shape (children names) — NOT the node's own name
        key = tuple(_node_sig(k) for k in kids)
        buckets.setdefault(key, []).append(n)
    out = list(singles)
    for members in buckets.values():
        if len(members) == 1:
            out.append(members[0])
            continue
        names = [m['name'] for m in members]
        costs = [m['cost'] for m in members]
        each = len(set(costs)) == 1
        merged = dict(members[0])                      # keep the first member's children shape
        merged['name'] = _area_label(names)
        merged['count'] = len(names)
        merged['each'] = each
        # cost is ALWAYS the GROUP TOTAL — it drives this node's share of its parent (pct) and its
        # rank among siblings, so a large group of identical items (e.g. 10 equal silos) never
        # ranks or reports as if it were a single item. Per-item cost is kept only for display.
        merged['cost'] = round(sum(costs), 2)
        if each:
            merged['each_cost'] = round(costs[0], 2)
        out.append(merged)
    out.sort(key=lambda n: -n['cost'])
    return out


def _money(v, currency=''):
    try:
        s = '{:,.0f}'.format(float(v))
    except (TypeError, ValueError):
        return ''
    return ('%s %s' % (currency, s)) if currency else s


def _area_label(names):
    """A compact display label for a group of areas that share the same scope signature:
    a contiguous "Prefix a–b" range when they are numbered (Silo 1..Silo 10 → "Silos 1–10"),
    else a short comma list."""
    import re
    if len(names) == 1:
        return names[0]
    ms = [re.match(r'^(.*?)(\d+)\s*$', n) for n in names]
    if all(ms) and len({m.group(1).strip() for m in ms}) == 1:
        nums = sorted(int(m.group(2)) for m in ms)
        if nums == list(range(nums[0], nums[-1] + 1)):
            pre = ms[0].group(1).strip()
            pre = pre + ('' if pre.endswith('s') else 's')     # Silo → Silos
            return '%s %d–%d' % (pre, nums[0], nums[-1])
    if len(names) <= 3:
        return ', '.join(names)
    return '%s, %s … (+%d more)' % (names[0], names[1], len(names) - 2)


def _scope_narrative(payload, currency=''):
    """A plain-language paragraph generated from the cost-weighted split — so §6 explains
    the scope, not just charts it."""
    disc = payload.get('disciplines') or []
    if not disc:
        return 'The scope could not be split by activity code — no cost-loaded codes were found.'
    total = payload.get('total') or 0
    lead = disc[0]
    parts = ['The scope, valued at %s, is delivered predominantly as %s (%s%%)'
             % (_money(total, currency), lead['name'], _fmt_pct(lead['pct']))]
    rest = disc[1:5]
    if rest:
        tail = ', '.join('%s (%s%%)' % (d['name'], _fmt_pct(d['pct'])) for d in rest)
        parts.append(', supported by %s' % tail)
    sent = ''.join(parts) + '.'
    # mention the second cascade level (e.g. the areas/structures) when the planner picked one
    top = payload.get('cascade') or []
    kids = (top[0].get('children') if top else None) or []
    if kids:
        egs = ', '.join(k['name'] for k in kids[:3])
        sent += ' Within %s it spans %s%s.' % (
            top[0]['name'], egs, ', …' if len(kids) > 3 else '')
    return sent


def _fmt_pct(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return '0'
    return str(int(f)) if f == int(f) else ('%.1f' % f)


def _describe(discipline, packages, count):
    if not packages:
        return f"The {discipline} scope comprises {count} scheduled activities."
    shown = ', '.join(packages[:8])
    more = '' if len(packages) <= 8 else f", and {len(packages) - 8} more"
    pkg_word = 'work-package' if len(packages) == 1 else 'work-packages'
    return (f"The {discipline} scope comprises {count} activities across "
            f"{len(packages)} {pkg_word}: {shown}{more}.")
