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
_TRADE_HINTS = ('discipline', 'trade', 'craft')
_AREA_HINTS = ('area', 'building', 'zone', 'location', 'unit', 'facility',
               'block', 'sector', 'silo', 'structure', 'system')
_ELEMENT_HINTS = ('type of work', 'work type', 'worktype', 'element', 'scope',
                  'work package', 'activity type', 'work')
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
    for dim in code_types or []:
        if dim in used:
            continue
        low = (dim or '').lower()
        if any(h in low for h in hints):
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


def scope_sections(activities, wbs, bac_by_activity=None, code_types=None, setup=None):
    """Reshaped Scope of Work for the redesigned narrative (§7).

    Returns ``{'disciplines': [...], 'sections': [...]}`` where

      * ``disciplines`` = ``[{name, pct, cost}]`` — a %-by-cost split for the top
        horizontal bar chart, grouped by the setup-picked Type-of-Works code
        (``setup['tow_code_scope']``), falling back to a discipline code hint, then to
        the top-level WBS branch.
      * ``sections``    = ``[{discipline, buildings:[{name, elements:[str]}]}]`` — one
        block per discipline; buildings come from the setup Building code
        (``setup['building_code']``, WBS work-package fallback) and elements from that
        discipline's Element/System code (``setup['element_codes'][discipline]``, then a
        global element hint, then the activity names).

    Pure logic, generic across any file — no client names hardcoded. Always returns a
    usable structure (never ``None``) so §7 renders even on code-less files.
    """
    setup = setup or {}
    bac = bac_by_activity or {}
    used = set()
    tow_dim = setup.get('tow_code_scope') or _pick_dim(code_types, _TRADE_HINTS, used)
    if not tow_dim:
        tow_dim = pick_discipline_dim(code_types)
    if tow_dim:
        used.add(tow_dim)
    bld_dim = setup.get('building_code') or _pick_dim(code_types, _AREA_HINTS, used)
    if bld_dim:
        used.add(bld_dim)
    elem_map = setup.get('element_codes') or {}
    global_elem = _pick_dim(code_types, _ELEMENT_HINTS, used)

    def code(act, dim):
        return (act.get('activity_codes') or {}).get(dim) if dim else None

    def cost_of(acts):
        return sum(bac.get(a.get('object_id'), 0.0) or 0.0 for a in acts)

    work = [a for a in activities if a.get('task_type') not in _NON_WORK]

    groups = OrderedDict()
    for act in work:
        disc = code(act, tow_dim) or top_wbs_name(act.get('wbs_id'), wbs) or 'General'
        groups.setdefault(disc, []).append(act)

    total_cost = cost_of(work)
    ordered = sorted(groups,
                     key=lambda d: (-cost_of(groups[d]), _trade_rank(d), _first_index(groups, d)))

    disciplines = []
    for disc in ordered:
        acts = groups[disc]
        cost = round(cost_of(acts), 2)
        if total_cost > 0:
            pct = round(100 * cost / total_cost, 1)
        else:
            pct = round(100 * len(acts) / len(work), 1) if work else 0.0
        disciplines.append({'name': disc, 'pct': pct, 'cost': cost})

    sections = []
    for disc in ordered:
        acts = groups[disc]
        edim = elem_map.get(disc) or global_elem
        buildings = OrderedDict()
        for a in acts:
            bld = code(a, bld_dim) or (wbs.get(a.get('wbs_id')) or {}).get('name') or 'General'
            buildings.setdefault(bld, []).append(a)
        ordered_builds = sorted(
            buildings, key=lambda b: min(_start_key(x.get('planned_start')) for x in buildings[b]))
        blist = []
        for bld in ordered_builds[:_BUILDING_CAP]:
            elements, seen = [], set()
            for a in sorted(buildings[bld], key=lambda x: _start_key(x.get('planned_start'))):
                el = code(a, edim) or a.get('name') or 'General'
                if el and el not in seen:
                    seen.add(el)
                    elements.append(el)
            blist.append({'name': bld, 'elements': elements[:_ELEMENTS_PER_BUILDING]})
        sections.append({'discipline': disc, 'buildings': blist})

    return {'disciplines': disciplines, 'sections': sections}


def _describe(discipline, packages, count):
    if not packages:
        return f"The {discipline} scope comprises {count} scheduled activities."
    shown = ', '.join(packages[:8])
    more = '' if len(packages) <= 8 else f", and {len(packages) - 8} more"
    pkg_word = 'work-package' if len(packages) == 1 else 'work-packages'
    return (f"The {discipline} scope comprises {count} activities across "
            f"{len(packages)} {pkg_word}: {shown}{more}.")
