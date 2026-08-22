"""Instance-primary front detection for the Narrative Intelligence layer.

A work front is a physical/logical INSTANCE (a building, a conveyor, a drawing package)
that recurs, consolidated across the WBS lenses that split it. The identity is
``Trade × Building`` (never merged across a trade); the Submittal/Approval phase collapses
into the front's internal sequence; the sequence is shown at the WBS / major-work-package
altitude, with the P6 activities kept underneath for traceability. Procurement collapses to
its generic cycle per stream. No project/name-specific rules — the roles of the activity
code dimensions are inferred from the schedule's own relationships.

This module is used ONLY for schedules with the rich EPC code structure that supports it
(see :func:`has_matrix_structure`); simpler / code-less schedules fall back to the general
:func:`p6_narrative.intel.dedup.detect_repeats`, which the permanent fixtures gate.
"""
import statistics
from collections import Counter, defaultdict

from p6_narrative.intel.dedup import detect_repeats

MIN_INSTANCES = 2
SINGLE_FRONT_MIN_ACTS = 12     # a lone coherent instance this big is a front on its own
STEP_CROSSF = 0.45
ID_CROSSF = 0.30
FUZZY = 0.60                    # step-set Jaccard to cluster two instances into one front
_STOP = {'the', 'of', 'for', 'and', '&', 'to', 'a', 'works', 'work', 'building', 'area'}


def dedup_dims(ctx):
    maps = {}
    for oid, act in ctx.steps.items():
        for d, v in (act.get('activity_codes') or {}).items():
            maps.setdefault(d, {})[oid] = v
    reps, seen = [], set()
    for d in sorted(maps):
        sig = tuple(sorted(maps[d].items()))
        if sig not in seen:
            seen.add(sig)
            reps.append(d)
    return reps, maps


def world_of(ctx, oid):
    wid = (ctx.data.activities.get(oid) or {}).get('wbs_id')
    b = ctx.group_of.get(wid)
    return ((ctx.data.wbs.get(b) or {}).get('name') or str(b)) if b else '(none)'


def wname(ctx, wid):
    return (ctx.data.wbs.get(wid) or {}).get('name') or str(wid)


def toks(s):
    return {t for t in ''.join(c if c.isalnum() else ' ' for c in (s or '').lower()).split()
            if t not in _STOP and len(t) > 1}


def classify(ctx, maps, reps, acts):
    ident, step = [], []
    for d in reps:
        vals = {o: maps[d][o] for o in acts if o in maps[d]}
        if len(set(vals.values())) < 2:
            continue
        within = cross = 0
        for a in vals:
            for b in ctx.forward.get(a, []):
                if b in vals:
                    within += (vals[a] == vals[b])
                    cross += (vals[a] != vals[b])
        tot = within + cross
        if tot < 3:
            continue
        crossF = cross / tot
        if crossF < ID_CROSSF and len(vals) / len(acts) >= 0.5:
            ident.append((crossF, d))
        elif crossF >= STEP_CROSSF:
            step.append(d)
    ident.sort()
    return [d for _, d in ident], step


def order_steps(ctx, oids):
    inside = set(oids)
    indeg = {o: sum(1 for p in ctx.back.get(o, []) if p in inside) for o in oids}
    ready = sorted([o for o in oids if indeg[o] == 0]) or sorted(oids)
    order, seen = [], set()
    while ready:
        o = ready.pop(0)
        if o in seen:
            continue
        seen.add(o)
        order.append(o)
        for s in sorted(ctx.forward.get(o, [])):
            if s in inside and s not in seen:
                indeg[s] -= 1
                if indeg[s] <= 0:
                    ready.append(s)
    order += [o for o in sorted(oids) if o not in seen]
    return order


def _element_labels(members, step_of):
    """Group step values by their most-specific (lowest document-frequency) token — the
    element noun. Operation words (FW/RFT/RC/Pouring/Formwork/Steel-Fixing) recur across
    many elements so they have high DF and are absorbed; the element (Footing/Columns/Slab)
    is the distinctive residual. Project-agnostic — no activity-name dictionary. Returns
    {oid: element_label} for a flat-WBS front, or {} when there is nothing to infer from."""
    def tok(s):
        return [t for t in ''.join(c if c.isalnum() else ' ' for c in (s or '').lower()).split()
                if len(t) > 1]
    vals = {o: step_of(o) for o in members if step_of(o)}
    if len(set(vals.values())) < 3:
        return {}
    df = Counter()
    for v in set(vals.values()):
        for t in set(tok(v)):
            df[t] += 1
    key = {}
    for o, v in vals.items():
        ts = tok(v)
        if ts:
            # the element noun is the longest word (operations are short abbreviations:
            # FW/RC/RFT/PC), tie-broken toward the rarer token.
            key[o] = max(ts, key=lambda t: (len(t), -df[t]))
    # operation tokens = short abbreviations or high-frequency words (FW/RC/RFT/PC/Works);
    # they are dropped from the package LABEL so the node reads as the element noun.
    nvals = len(set(vals.values()))
    ops = {t for t in df if len(t) <= 3 or df[t] >= max(2, round(0.4 * nvals))}
    groups = defaultdict(list)
    for o, k in key.items():
        groups[k].append(vals[o])
    label = {}
    for k, vs in groups.items():
        common = set(tok(vs[0]))
        for v in vs[1:]:
            common &= set(tok(v))
        rep = max(vs, key=len)
        core = [t for t in tok(rep) if t in common and t not in ops] or \
               [t for t in tok(rep) if t not in ops] or [k]
        label[k] = ' '.join(core).title()
    return {o: label[key[o]] for o in members if o in key}


def phase_flow(ctx, members, step_of, max_nodes=10):
    """WBS-oriented, de-duplicated phase flow: [(phase_label, [qualifiers])]. Picks the
    WBS ancestor level (or the step dim) giving the cleanest 4-8 node monotonic sequence,
    orders phases by median logical position, hangs activity detail as bracket qualifiers.
    Each phase appears once — never repeated because one activity recurs later."""
    order = order_steps(ctx, members)

    def wbs_at(o, d):
        chain = ctx.wbs_ancestors.get(ctx.data.activities[o].get('wbs_id'), ())
        nm = wname(ctx, chain[d]) if 0 <= d < len(chain) else None
        return nm.split(' (')[0].strip() if nm else None      # strip "(Instance)" suffix

    maxd = max((len(ctx.wbs_ancestors.get(ctx.data.activities[o].get('wbs_id'), ()))
                for o in members), default=0)
    cands = {'wbs%d' % d: {o: wbs_at(o, d) for o in members} for d in range(1, maxd)}
    cands['step'] = {o: step_of(o) for o in members}
    elem = _element_labels(members, step_of)
    if elem:
        cands['element'] = elem                 # flat-WBS: lift steps to element packages

    inside = set(members)

    def cross_frac(labels):
        """Fraction of internal relationships that cross between distinct node values.
        A phase level is SEQUENTIAL (work flows between its nodes, high fraction); an
        instance level is PARALLEL (each node self-contained, low fraction)."""
        within = cross = 0
        for a in members:
            la = labels.get(a)
            if la is None:
                continue
            for b in ctx.forward.get(a, []):
                if b in inside and labels.get(b) is not None:
                    within += (labels[b] == la)
                    cross += (labels[b] != la)
        tot = within + cross
        return (cross / tot) if tot else 0.0

    def is_location(labels):
        labs = [v for v in labels.values() if v]
        loc = sum(1 for l in labs if any(c.isdigit() for c in l)
                  or any(w in l.lower() for w in ('floor', 'level', 'zone', '@')))
        return bool(labs) and loc / len(labs) >= 0.5

    def score_level(name, labels, gate, allow_loc):
        seq = [labels[o] for o in order if labels.get(o)]
        distinct = list(dict.fromkeys(seq))
        k = len(distinct)
        if k < 2 or k > 14 or len(seq) < 2:
            return None
        # a phase level must be SEQUENTIAL; a parallel (instance) level is not a phase.
        if name != 'step' and cross_frac(labels) < gate:
            return None
        is_wbs = name.startswith('wbs')
        loc = is_wbs and is_location(labels)
        if loc and not allow_loc:            # floors/levels are a LOCATION, not a work package
            return None
        rank = {p: i for i, p in enumerate(distinct)}
        mono = sum(1 for a, b in zip(seq, seq[1:]) if rank[b] >= rank[a]) / (len(seq) - 1)
        band = 2 if 4 <= k <= 8 else (1 if 3 <= k <= 10 else 0)
        depth = int(name[3:]) if is_wbs else 99
        src = 2.0 if (is_wbs and not loc) else (1.0 if name == 'element' else 0.0)
        return ((band, src, -depth, round(mono, 3), -abs(5 - k)), name, labels, distinct)

    best = None
    # prefer work-package levels (WBS or element) over LOCATION levels (floors); relax the
    # sequentiality gate, and finally allow a location level, only if nothing else qualifies.
    for allow_loc, gate in ((False, 0.25), (False, 0.0), (True, 0.0)):
        for name, labels in cands.items():
            s = score_level(name, labels, gate, allow_loc)
            if s and (best is None or s[0] > best[0]):
                best = s
        if best is not None:
            break
    if best is None:
        return []
    _, name, labels, distinct = best
    pos = {o: i for i, o in enumerate(order)}
    med = {p: statistics.median([pos[o] for o in members if labels.get(o) == p] or [0])
           for p in distinct}
    distinct = sorted(distinct, key=lambda p: med[p])
    quals = defaultdict(list)
    for o in order:
        p, q = labels.get(o), step_of(o)
        if p is not None and q and q not in quals[p]:
            quals[p].append(q)
    distinct = [p for p in distinct if len(str(p).strip()) > 2]   # drop stray abbreviations
    if len(distinct) > max_nodes:
        keep = set(sorted(distinct, key=lambda p: -sum(1 for o in members if labels.get(o) == p))[:max_nodes])
        distinct = [p for p in distinct if p in keep]
    return [(p, quals[p][:5]) for p in distinct]


def stream_cycle_fronts(ctx, acts, step_of, world_branch):
    """Procurement-style cycle world: {stream} × {stage cycle} × {material}. Group by the
    coarse WBS STREAM (1st Patch / Long Lead), show each as the generic stage cycle
    (Submittal → Approval → PO → Delivery), with the materials as instances. Returns front
    tuples, or None when the world is not this shape (e.g. engineering, whose coarse split
    IS the stage, so it stays per-discipline)."""
    steps = sorted(acts)
    order = order_steps(ctx, steps)
    pos = {o: i for i, o in enumerate(order)}

    def stage(o):
        v = step_of(o)
        return v.split()[-1] if v and v.split() else None

    def material(o):
        v = step_of(o)
        tl = v.split() if v else []
        return ' '.join(tl[:-1]) if len(tl) > 1 else None

    def stream(o):
        ch = ctx.wbs_ancestors.get(ctx.data.activities[o].get('wbs_id'), ())
        if world_branch in ch:
            i = ch.index(world_branch)
            if i + 1 < len(ch):
                return (ctx.data.wbs.get(ch[i + 1]) or {}).get('name')
        return None

    stagewords = {stage(o).lower() for o in acts if stage(o)}
    if len(stagewords) < 2:
        return None
    streams = {stream(o) for o in acts if stream(o)}
    if len(streams) < 2:
        return None
    # if the coarse split IS the stage dimension (engineering: Submittal/Approval branches),
    # this is not a stream world — keep it per-discipline.
    if any(s and s.split()[-1].lower() in stagewords for s in streams):
        return None
    # every material must span ≥2 stages (a genuine cycle), and stages recur across materials
    mats = {material(o) for o in acts if material(o)}
    if len(mats) < 2:
        return None

    by_stream = defaultdict(list)
    for o in acts:
        s = stream(o)
        if s:
            by_stream[s].append(o)
    fronts = []
    for st, oids in by_stream.items():
        stg = defaultdict(list)
        for o in oids:
            s = stage(o)
            if s:
                stg[s].append(pos[o])
        if len(stg) < 2:
            continue
        seq = sorted(stg, key=lambda s: statistics.median(stg[s]))
        materials = sorted({material(o) for o in oids if material(o)})
        fronts.append((st, seq, materials, sorted(oids)))
    return fronts or None


def build_world(ctx, maps, reps, acts):
    ident_dims, step_dims = classify(ctx, maps, reps, acts)
    inst_dims = ident_dims[:2]

    units = defaultdict(list)
    for o in acts:
        vals = [maps[d][o] for d in inst_dims if o in maps[d]]
        key = ('code', tuple(vals)) if vals else ('wbs', ctx.data.activities[o].get('wbs_id'))
        units[key].append(o)

    def label(k):
        return ' / '.join(str(x) for x in k[1]) if k[0] == 'code' else wname(ctx, k[1])
    lab = {k: label(k) for k in units}
    core = {k: toks(lab[k]) for k in units}

    # phase merge: coupled + near-identical labels (symmetric diff <= 2 tokens)
    keys = list(units)
    parent = {k: k for k in keys}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    memb = {k: set(units[k]) for k in keys}
    coupling = {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            # NEVER merge across a code identity (Trade × Building). A front is strictly
            # one Trade × Building; only the phase (Submittal/Approval) collapses. Code-keyed
            # units already carry both phases (same code, different step value), so the merge
            # is only for WBS-leaf worlds (engineering/procurement without a building code)
            # where the phase (Submittal/Approval) is a separate sibling WBS node.
            if a[0] != 'wbs' or b[0] != 'wbs':
                continue
            links = sum(1 for o in memb[a] for s in ctx.forward.get(o, []) if s in memb[b]) \
                + sum(1 for o in memb[b] for s in ctx.forward.get(o, []) if s in memb[a])
            if not links:
                continue
            strong = links >= 0.5 * min(len(memb[a]), len(memb[b]))   # ~1:1 phase mirror
            sym = core[a] ^ core[b]
            ov = core[a] & core[b]
            if strong and len(ov) >= 1 and len(sym) <= 2:  # same instance, differ by phase
                parent[find(a)] = find(b)
                coupling[find(b)] = coupling.get(find(b), 0) + links

    # material-core merge (WBS-keyed only): collapse all STAGES of one package/material
    # into one front. The material core = the step value with its trailing stage word(s)
    # stripped (Submittal/Approval/PO/Delivery). Procurement's Electric Submittal + Approval
    # + Purchase Order + Delivery share the core "electric works materials" -> one front;
    # engineering's Structure vs Architecture drawings have different cores -> stay apart.
    def _tok(s):
        return [t for t in ''.join(c if c.isalnum() else ' ' for c in (s or '').lower()).split()]
    # The core comes from the unit's WBS LABEL (which carries building + discipline +
    # material), never the step value alone — else a world whose instance lives in the WBS
    # name (engineering: building in the node name), else every building would collapse.
    trailing = Counter()
    for k in keys:
        if k[0] == 'wbs':
            for t in _tok(lab[k])[-2:]:
                trailing[t] += 1
    stagevocab = {t for t, c in trailing.items() if c >= 3}

    def _corelabel(k):
        tl = _tok(lab[k])
        while tl and tl[-1] in stagevocab:
            tl.pop()
        return ' '.join(tl)
    by_core = defaultdict(list)
    for k in keys:
        if k[0] == 'wbs':
            c = _corelabel(k)
            if c:
                by_core[c].append(k)
    for core, ks in by_core.items():
        for k in ks[1:]:
            parent[find(k)] = find(ks[0])

    merged = defaultdict(list)
    for k in keys:
        merged[find(k)].extend(units[k])

    inst_fronts = []
    for root, oids in merged.items():
        members = sorted(set(oids))
        ordered = order_steps(ctx, members)

        def steplab(o):
            for d in step_dims:
                if o in maps[d]:
                    return maps[d][o]
            return (ctx.data.activities[o].get('name') or '')[:26]
        seq, stepset = [], set()
        for o in ordered:
            s = steplab(o)
            stepset.add(s)
            if not seq or seq[-1] != s:
                seq.append(s)
        inst_fronts.append({
            'instance': lab.get(root, wname(ctx, root[1] if root[0] == 'wbs' else '')),
            'members': members, 'seq': seq, 'stepset': stepset,
            'wbs_parents': sorted({wname(ctx, ctx.data.activities[o].get('wbs_id')) for o in members}),
            'merged_from': len([k for k in keys if find(k) == root]),
            'coupling': coupling.get(root, 0),
        })
    return ident_dims, step_dims, inst_dims, inst_fronts


def fuzzy_cluster(fronts):
    n = len(fronts)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i in range(n):
        for j in range(i + 1, n):
            a, b = fronts[i]['stepset'], fronts[j]['stepset']
            if not a or not b:
                continue
            jac = len(a & b) / len(a | b)
            if jac >= FUZZY:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(fronts[i])
    return list(groups.values())


def common_title(fronts):
    sets = [toks(f['instance']) for f in fronts]
    common = set.intersection(*sets) if sets else set()
    return ' '.join(sorted(common)) if common else (fronts[0]['seq'][0] if fronts[0]['seq'] else '?')


def analyze_context(ctx):
    """Structured version of report(): returns [{world, ident_dims, step_dims, grouped,
    total, fronts:[{title, instances:[...], world, wbs_parents, activities:[{name,id,wbs}],
    sequence:[...], evidence, merged}]}] — for the HTML review."""
    reps, maps = dedup_dims(ctx)
    world_acts = defaultdict(set)
    for o in ctx.steps:
        world_acts[world_of(ctx, o)].add(o)
    out = []
    for world in sorted(world_acts, key=lambda w: -len(world_acts[w])):
        acts = world_acts[world]
        if len(acts) < 8:
            continue
        ident_dims, step_dims, inst_dims, inst_fronts = build_world(ctx, maps, reps, acts)

        def step_of(o):
            for d in step_dims:
                v = maps[d].get(o)
                if v:
                    return v
            return None

        def _acts_list(members):
            rows = []
            for o in members:
                a = ctx.data.activities[o]
                rows.append({'name': a.get('name') or '', 'id': a.get('id') or o,
                             'wbs': wname(ctx, a.get('wbs_id'))})
            return rows

        world_branch = next((b for o in acts
                             for b in [ctx.group_of.get(ctx.data.activities[o].get('wbs_id'))]
                             if b), None)
        cyc = (stream_cycle_fronts(ctx, acts, step_of, world_branch)
               if (not inst_dims and world_branch) else None)
        wfronts = []
        if cyc:                                  # procurement-style: streams × generic cycle
            for st, seq, materials, members in sorted(cyc, key=lambda t: -len(t[3])):
                wfronts.append({
                    'title': st, 'n_instances': len(materials), 'instances': materials,
                    'wbs_parents': sorted({wname(ctx, ctx.data.activities[o].get('wbs_id'))
                                           for o in members}),
                    'activities': _acts_list(members), 'sequence': list(seq),
                    'phase_flow': [(s, []) for s in seq], 'merged': True,
                    'identity': 'Material (procurement stream)',
                })
        else:
            clusters = fuzzy_cluster(inst_fronts)
            fronts = []
            for cl in clusters:
                n_acts = sum(len(f['members']) for f in cl)
                if n_acts / len(cl) < 2:
                    continue
                if len(cl) >= MIN_INSTANCES or (len(cl) == 1 and n_acts >= SINGLE_FRONT_MIN_ACTS and len(cl[0]['seq']) >= 2):
                    fronts.append(cl)
            for cl in sorted(fronts, key=lambda c: -sum(len(f['members']) for f in c)):
                seq = max((f['seq'] for f in cl), key=len)
                rep = max(cl, key=lambda f: len(f['members']))
                flow = phase_flow(ctx, rep['members'], step_of)
                wfronts.append({
                    'title': common_title(cl), 'n_instances': len(cl),
                    'instances': [f['instance'] for f in cl],
                    'wbs_parents': sorted({p for f in cl for p in f['wbs_parents']}),
                    'activities': _acts_list([o for f in cl for o in f['members']]),
                    'sequence': [str(s) for s in seq],
                    'phase_flow': [(p, list(qs)) for p, qs in flow],
                    'merged': any(f['merged_from'] > 1 for f in cl),
                    'identity': ' × '.join(inst_dims) if inst_dims else 'WBS instance',
                })
        grouped = sum(len(f['activities']) for f in wfronts)
        out.append({'world': world, 'ident_dims': inst_dims, 'step_dims': step_dims,
                    'grouped': grouped, 'total': len(acts), 'fronts': wfronts})
    return out


def project_interactions(ctx):
    """Level 3 — how the major fronts interact: the macro flow between WORLDS (Engineering
    → Procurement → Construction …) and the sequence between major BUILDINGS/instances,
    both read from the schedule's own cross-links. Ordered by net logical flow."""
    def world_of(o):
        b = ctx.group_of.get((ctx.data.activities.get(o) or {}).get('wbs_id'))
        return ((ctx.data.wbs.get(b) or {}).get('name') or str(b)) if b else None

    reps, maps = dedup_dims(ctx)
    # instance dim = the code dim that most looks like a physical building/area
    inst_dim = None
    for d in reps:
        vals = {maps[d][o] for o in ctx.steps if o in maps[d]}
        nm = d.lower()
        if ('building' in nm or 'area' in nm) and len(vals) >= 3:
            inst_dim = d
            break

    def flow_order(link_counter, nodes):
        """Order nodes by net downstream flow (out - in)."""
        net = {n: 0 for n in nodes}
        for (a, b), c in link_counter.items():
            if a in net and b in net:
                net[a] += c
                net[b] -= c
        return sorted(nodes, key=lambda n: -net[n])

    wlinks = Counter()
    for a in ctx.steps:
        wa = world_of(a)
        for b in ctx.forward.get(a, []):
            wb = world_of(b) if b in ctx.steps else None
            if wa and wb and wa != wb:
                wlinks[(wa, wb)] += 1
    worlds = {w for pair in wlinks for w in pair}
    world_order = flow_order(wlinks, worlds)
    world_edges = sorted(((a, b, c) for (a, b), c in wlinks.items() if c >= 3),
                         key=lambda e: -e[2])[:12]

    building_order, building_edges = [], []
    if inst_dim:
        def inst_of(o):
            return maps[inst_dim].get(o)
        blinks = Counter()
        for a in ctx.steps:
            ia = inst_of(a)
            for b in ctx.forward.get(a, []):
                ib = inst_of(b) if b in ctx.steps else None
                if ia and ib and ia != ib:
                    blinks[(ia, ib)] += 1
        buildings = {x for pair in blinks for x in pair}
        building_order = flow_order(blinks, buildings)
        building_edges = sorted(((a, b, c) for (a, b), c in blinks.items() if c >= 3),
                                key=lambda e: -e[2])[:14]
    return {'world_order': world_order, 'world_edges': world_edges,
            'inst_dim': inst_dim, 'building_order': building_order,
            'building_edges': building_edges}


# ── router: matrix-WBS EPC files use instance-primary; everything else the general path ──
def has_matrix_structure(ctx):
    """True when the schedule carries a document-control / procurement STAGE CYCLE — an
    activity-code STEP dimension whose values decompose into (prefix, stage) with ≥2 stages
    each shared across ≥2 prefixes (Submittal/Approval across disciplines or materials).
    This is the mirror/matrix signature the instance-primary consolidation exists to handle;
    simple and code-less schedules (the permanent fixtures) do not have it and stay on the
    general detector. Read from the codes + relationships only — no keyword list."""
    reps, maps = dedup_dims(ctx)
    world_acts = defaultdict(set)
    for o in ctx.steps:
        world_acts[world_of(ctx, o)].add(o)
    for world, acts in world_acts.items():
        if len(acts) < 8:
            continue
        _ident, step = classify(ctx, maps, reps, acts)
        for d in step:
            by_stage = defaultdict(set)
            for v in {maps[d][o] for o in acts if o in maps[d]}:
                tl = v.split()
                if tl:
                    by_stage[tl[-1].lower()].add(' '.join(tl[:-1]))
            if sum(1 for prefixes in by_stage.values() if len(prefixes) >= 2) >= 2:
                return True
    return False


def _unify_general(ctx, result):
    """Adapt the general :func:`detect_repeats` output to the same ``worlds`` shape the
    instance-primary path emits, so the Narrative Report renders identically for ANY project
    type (villas, roads, bridges, industrial …), not only matrix-WBS EPC schedules."""
    world_total = Counter(world_of(ctx, o) for o in ctx.steps)
    by_world = defaultdict(list)
    for g in result.get('groups', []):
        oids = [o for fr in g.get('fronts', []) for o in fr.get('activity_ids', [])]
        wn = Counter(world_of(ctx, o) for o in oids).most_common(1)[0][0] if oids else '(project)'
        by_world[wn].append((g, oids))
    worlds = []
    for wn, groups in sorted(by_world.items(), key=lambda kv: -world_total.get(kv[0], 0)):
        fronts = []
        for g, oids in sorted(groups, key=lambda t: -len(t[1])):
            fronts.append({
                'title': g.get('label') or 'front',
                'n_instances': g.get('front_count') or g.get('instance_count') or len(g.get('fronts', [])),
                'instances': [fr.get('unit_label') for fr in g.get('fronts', [])],
                'wbs_parents': sorted({wname(ctx, ctx.data.activities[o].get('wbs_id')) for o in oids}),
                'activities': [{'name': ctx.data.activities[o].get('name') or '',
                                'id': ctx.data.activities[o].get('id') or o,
                                'wbs': wname(ctx, ctx.data.activities[o].get('wbs_id'))} for o in oids],
                'phase_flow': [(s['step'], []) for s in g.get('typical_sequence', [])],
                'merged': False, 'identity': 'work front',
            })
        worlds.append({'world': wn, 'ident_dims': [], 'step_dims': [],
                       'grouped': sum(len(f['activities']) for f in fronts),
                       'total': world_total.get(wn, 0), 'fronts': fronts})
    return worlds


def detect_fronts(context, params=None):
    """Front detection for the Narrative layer, uniform across every project type.

    Matrix-WBS EPC schedules (see :func:`has_matrix_structure`) use instance-primary
    consolidation — ``Trade × Building`` fronts, phase collapse, work-package sequences,
    procurement stream cycles. Every other schedule (villas, roads, bridges, plain
    industrial …) uses the general :func:`p6_narrative.intel.dedup.detect_repeats`, which the
    permanent fixtures gate. Both paths return the SAME ``worlds`` shape plus the Level-3
    interaction map, so the Narrative Report renders identically regardless of project type;
    ``mode`` is reported for honesty about which path produced the result.
    """
    mode = 'instance-primary' if has_matrix_structure(context) else 'general'
    worlds = (analyze_context(context) if mode == 'instance-primary'
              else _unify_general(context, detect_repeats(context, params)))
    return {'mode': mode, 'worlds': worlds, 'interactions': project_interactions(context)}
