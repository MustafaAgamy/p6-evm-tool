"""§7 Scope of Work written the way a planner writes it (Ibrahim, Nov 2026 — approved):

    7.2.1) Detailed Civil Works Scope of Work includes:
      ➢ Silos for 10 Silos (Silos 1–10) consist of:
          1. Pile Works.  2. Columns Works.  …
      ➢ Towers for 6 Towers consist of:
          The Towers are divided into 5 categories:
          1. Towers On Quay consists of:  ✓ Pedestals.
          2. Towers 35–36 consist of:     ✓ Pile Works ✓ Foundation …

* Code 1 (type of work) → one "Detailed … Scope of Work includes:" heading per value, with a bar
  chart of its buildings (every building shown — nothing grouped as "Other").
* Code 2 (building) → the ➢ lines. Buildings sharing the same first word form one family
  ("Towers"); members with the same elements are merged, and a family whose members differ is
  divided into categories (more than 6 → each building listed on its own).
* Code 3+ (element) → the numbered / ✓ elements, in P6 order: earliest planned start (by day);
  elements starting the same day follow construction logic (earth → piles → … → T&C).
* Every level is a code combination (the planner's code + Controlyx's suggestions, the same
  mechanism as Contract Value); an activity with no code is named by its WBS in P6 — the building
  by the WBS folder that names the building, the element by its own WBS folder. No "Unclassified".

Pure logic; generic across any P6 coding scheme.
"""
import re
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime

from p6_narrative.classify import (NON_WORK, WbsNames, codes_of, first_value, suggest_codes,
                                   clean_codes, building_like, shares_to_100)

# construction sequence for elements that start on the SAME day in P6 (Ibrahim: "Earth work,
# Pile work, Columns, Raft and so on")
_LADDER = (
    (1, ('mobili', 'site prep', 'dismantl', 'demoli', 'removal', 'de-water', 'dewater', 'survey')),
    (2, ('earth', 'excavat', 'soil replace', 'soil improve', 'grading', 'levelling', 'leveling')),
    (3, ('pile', 'piling')),
    (4, ('pc ', 'p.c', 'plain concrete', 'blinding', 'lean concrete')),
    (5, ('foundation', 'footing', 'pile cap', 'ground beam', 'tie beam', 'raft', 'pit')),
    (6, ('column', 'wall', 'vertical', 'pedestal', 'core', 'shaft')),
    (7, ('beam', 'slab', 'elevated', 'roof', 'stair')),
    (8, ('backfill', 'back fill')),
    (9, ('sog', 's.o.g', 'slab on grade', 'ground floor', 'stamp', 'stambed', 'hardscape',
         'paving', 'interlock', 'curb')),
    (10, ('steel', 'catwalk', 'precast', 'slipform', 'slip form')),
    (11, ('block', 'masonry', 'plaster', 'facade', 'finish', 'floor', 'tiling', 'tilling',
          'ceiling', 'paint', 'door', 'window', 'cladding', 'restoration')),
    (12, ('1st fix', 'first fix', 'conduit', 'cable tray', 'sleeve')),
    (13, ('2nd fix', 'second fix', 'wiring', 'cable pull', 'installation')),
    (14, ('3rd fix', 'third fix', 'fixture', 'equipment', 'landscape')),
    (15, ('testing', 'commission', 't&c', 'handover', 'handing over', 'snag')),
)

_STOP = {'all', 'the', 'of', 'and', 'for', 'under', 'on', 'from', 'main', 'works', 'work',
         'building', 'buildings', 'area', 'no', 'zone', 'phase'}
_ADJ = {'old', 'new', 'male', 'female', 'big', 'small', 'upper', 'lower', 'reinforced', 'royal'}
MAX_CATEGORIES = 6


def ladder_phase(name):
    n = ' %s ' % (name or '').lower()
    for ph, keys in _LADDER:
        if any(k in n for k in keys):
            return ph
    return 99


def _sing(w):
    w = w.lower()
    return w[:-1] if w.endswith('s') and not w.endswith('ss') and len(w) > 3 else w


def _words(name):
    return [_sing(w) for w in re.split(r'[\s\-:&,()/.\[\]_]+', name or '')
            if w and not re.match(r'^[a-z]?\d+[a-z]?$', w.lower()) and _sing(w) not in _STOP
            and len(w) > 1]


def _head(name):
    """First meaningful word of a building name (adjectives and 'Building NO.(xx)' ignored)."""
    base = re.sub(r'(?i)building\s*no\.?.*$', '', name or '')
    ws = [w for w in _words(base) if w not in _ADJ]
    return ws[0] if ws else None


def plural(word):
    w = (word or '').title()
    return w if w.endswith('s') else w + 's'


def natkey(s):
    return [(0, int(t), '') if t.isdigit() else (1, 0, t.lower()) for t in re.split(r'(\d+)', s or '') if t]


def compact(names):
    """'Silo 1'…'Silo 10' → 'Silos 1–10'; otherwise a natural-sorted list."""
    names = sorted(set(n for n in names if n), key=natkey)
    if not names:
        return ''
    ms = [re.match(r'^(.*?)(\d+)\s*$', n) for n in names]
    if len(names) > 1 and all(ms) and len({m.group(1).strip() for m in ms}) == 1:
        nums = sorted(int(m.group(2)) for m in ms)
        if nums == list(range(nums[0], nums[-1] + 1)):
            pre = ms[0].group(1).strip()
            return '%s%s %d–%d' % (pre, '' if pre.endswith('s') else 's', nums[0], nums[-1])
    if len(names) == 1:
        return names[0]
    return ', '.join(names[:-1]) + ' & ' + names[-1]


def clean_element(el, building):
    """'Pile Works - Main Silos' under 'Silo 1' → 'Pile Works'; 'Towers on Quay Pedestals' → 'Pedestals'."""
    s = el or ''
    bw = set(_words(building))
    m = re.match(r'^(.*?)\s+-\s+(.+)$', s)
    if m and (set(_words(m.group(2))) & bw or len(_words(m.group(2))) <= 2):
        s = m.group(1)
    if building and s.lower().startswith(building.lower()):
        s = s[len(building):].strip(' -')
    return s.strip() or el


def _start(act):
    v = act.get('planned_start') or act.get('remaining_early_start') or act.get('actual_start')
    if isinstance(v, datetime):
        return v.date().isoformat()
    return str(v)[:10] if v else '9999-12-31'


def _family_groups(buildings):
    """buildings: [{name, amount, acts, elements}] → ordered list of ➢ groups."""
    heads = {b['name']: _head(b['name']) for b in buildings}
    cnt = Counter(h for h in heads.values() if h)
    fams = OrderedDict()
    for b in buildings:
        h = heads[b['name']]
        key = h if (h and cnt[h] >= 2) else '§' + b['name']
        fams.setdefault(key, []).append(b)
    out = []
    for key, mem in fams.items():
        amount = sum(b['amount'] for b in mem)
        acts = sum(b['acts'] for b in mem)
        real = [b for b in mem if not b['name'].lower().startswith('all ')]
        cats = OrderedDict()
        for b in mem:
            cats.setdefault(tuple(b['elements']), []).append(b)
        if key.startswith('§') or len(mem) == 1:
            b = mem[0]
            out.append({'kind': 'single', 'label': b['name'], 'amount': amount, 'acts': acts,
                        'elements': list(b['elements'])})
        elif len(cats) > MAX_CATEGORIES:
            for b in sorted(mem, key=lambda x: natkey(x['name'])):
                out.append({'kind': 'single', 'label': b['name'], 'amount': b['amount'],
                            'acts': b['acts'], 'elements': list(b['elements'])})
        else:
            fam = plural(key)
            g = {'kind': 'family', 'label': fam, 'count': len(real) or len(mem),
                 'members': compact([b['name'] for b in mem]), 'amount': amount, 'acts': acts}
            if len(cats) == 1:
                g['elements'] = list(next(iter(cats)))
            else:
                g['categories'] = [
                    {'label': compact([b['name'] for b in bs]), 'count': len(bs),
                     'elements': list(es)}
                    for es, bs in sorted(cats.items(), key=lambda kv: -sum(b['amount'] for b in kv[1]))]
            out.append(g)
    out.sort(key=lambda g: (-g['amount'], -g['acts']))
    return out


def describe(data, codes, level1_codes=None):
    """One scope description (the planner's ordered codes) → the 'consists of' structure.

    ``level1_codes`` — the Contract Value code list, used for level 1 when this description starts
    with the same code, so §6 and §7 name the types of work identically.

    Returns {'codes', 'levels': [[…], […], […]], 'basis': 'cost'|'count', 'total',
             'types': [{name, amount, acts, pct, groups: [...]}]} or None."""
    codes = clean_codes(codes, data.activity_code_types)
    if not codes:
        return None
    bac = data.bac_by_activity or {}
    names = WbsNames(data.wbs)
    work = [a for a in data.activities.values() if a.get('task_type') not in NON_WORK]
    first_cost = sum(float(bac.get(a.get('object_id')) or 0) for a in work if codes_of(a).get(codes[0]))
    basis = 'cost' if first_cost > 0 else 'count'
    if basis == 'cost':
        # every costed activity — the SAME set §6 Contract Value splits, so a type of work reads
        # the same amount and % in §6, §7.1 and here
        items = [(a, float(bac.get(a.get('object_id')) or 0)) for a in data.activities.values()
                 if (bac.get(a.get('object_id')) or 0) > 0]
    else:   # a code with no cost (e.g. Engineering) describes its own activities, by count
        items = [(a, 1.0) for a in work if codes_of(a).get(codes[0])]
    if not items:
        return None
    ct = data.activity_code_types
    l1 = list(level1_codes) if (level1_codes and level1_codes[0] == codes[0] and basis == 'cost') \
        else suggest_codes(items, codes[0], ct)
    base2 = codes[1:2]
    base3 = codes[2:]
    used = set(l1) | set(base2) | set(base3)
    values_of = defaultdict(set)
    for a, _ in items:
        for k, v in codes_of(a).items():
            if v:
                values_of[k].add(v)
    # a building-level suggestion must name places, not kinds of work (no BOQ / trade codes)
    l2 = suggest_codes(items, base2, ct, exclude=used - set(base2), min_values=2, min_specific=0.6,
                       accept=lambda k: building_like(values_of[k])) if base2 else []
    used |= set(l2)

    def element_like(k):
        """Not a per-building label code (each value on one building only, e.g. 'Silo 1.Mech…')."""
        on = defaultdict(set)
        for a, _ in items:
            v = codes_of(a).get(k)
            if v:
                on[v].add(first_value(a, l2) or names.building(a))
        if len(on) >= 3 and all(len(b) == 1 for b in on.values()):
            return False
        # numbered crew / path labels ('Path 1', 'Machine 2') are not elements of work
        ms = [re.match(r'^(.*?)[\s.\-]*\d+\s*$', v) for v in on]
        if ms and all(ms) and len({m.group(1).strip().lower() for m in ms}) == 1:
            return False
        return True
    l3 = suggest_codes(items, base3, ct, exclude=used - set(base3), min_values=2, min_specific=0.6,
                       accept=element_like) if base3 else []

    total = sum(w for _, w in items)
    tree = OrderedDict()
    for a, w in items:
        t = first_value(a, l1) or names.own(a)
        node = tree.setdefault(t, {'amount': 0.0, 'acts': 0, 'b': OrderedDict()})
        node['amount'] += w
        node['acts'] += 1
        if len(codes) < 2:
            continue
        b = first_value(a, l2) or names.building(a)
        bn = node['b'].setdefault(b, {'amount': 0.0, 'acts': 0, 'e': {}})
        bn['amount'] += w
        bn['acts'] += 1
        e = first_value(a, l3) or names.own(a)
        e = clean_element(e, b)
        if not e or e == b or e.lower() in b.lower():
            continue
        st = _start(a)
        bn['e'][e] = min(bn['e'].get(e, st), st)

    types = []
    ordered = sorted(tree.items(), key=lambda kv: (-kv[1]['amount'], -kv[1]['acts']))
    tpcts = shares_to_100([n['amount'] for _, n in ordered], total)
    for (t, node), tpct in zip(ordered, tpcts):
        blds = [{'name': b, 'amount': v['amount'], 'acts': v['acts'],
                 'elements': [e for e, _ in sorted(v['e'].items(),
                                                   key=lambda kv: (kv[1], ladder_phase(kv[0]), kv[0].lower()))]}
                for b, v in node['b'].items()]
        groups = _family_groups(blds) if blds else []
        tamt = node['amount']
        for g, gp in zip(groups, shares_to_100([g['amount'] for g in groups], tamt)):
            g['pct'] = gp
            g['amount'] = round(g['amount'], 2)
        types.append({'name': t, 'amount': round(tamt, 2), 'acts': node['acts'],
                      'pct': tpct, 'groups': groups})
    return {'codes': list(codes), 'levels': [l1, l2, l3], 'basis': basis,
            'total': round(total, 2), 'types': types}
