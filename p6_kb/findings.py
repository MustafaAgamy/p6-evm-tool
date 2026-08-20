"""Phase 3 — the evidence-graded constructability rule engine.

Turns the Phase 1 activity tags + the Phase 2 System Patterns / archetype
resolution into FINDINGS, each carrying the full chain:
    existing → expected → reason → evidence → strength → impact → recommendation.

Deterministic and offline. Designed to AVOID false positives (binding condition):
a rule fires only when the schedule actually contains the systems and activities
the pattern is about, the evidence is strong enough, and the resolved archetype /
systems-present make the expectation real. When a required system simply isn't in
the project, that is treated as "not applicable", never a defect; genuinely
uncertain cases are graded 'insufficient' (planner review), not forced.

MEP-first: rules run over the MEP / industrial / commissioning systems; civil
enters only as a named interface (equipment foundations, embeds, trenches…).
"""
from p6_kb.patterns import load_system_patterns
from p6_kb.tagging import tag_view

_LATE = {'TESTING', 'PRE_COMMISSIONING', 'COMMISSIONING', 'INTEGRATED_TESTING', 'PERFORMANCE', 'STARTUP'}
# Power-gated late phases (R1): only FUNCTIONAL commissioning/running needs permanent
# power. A hydrotest / pressure test / flush / megger / watertightness test is hydraulic
# or passive pre-commissioning and needs NO power, so TESTING and PRE_COMMISSIONING are
# deliberately excluded — including them made R1 fire on every hydrostatic test.
_R1_POWER_LATE = {'COMMISSIONING', 'INTEGRATED_TESTING', 'PERFORMANCE', 'STARTUP'}
_INSTALL = {'ERECTION_INSTALL', 'MECHANICAL_COMPLETION', 'ROUGH_IN'}
_STRENGTH = {'strong': 3, 'moderate': 2, 'weak': 1, 'insufficient': 0}
_MEP_DISC = {'MECH', 'ELEC', 'ELV', 'PIPING', 'INSTR', 'PLUMB', 'FIRE', 'PROCESS', 'UTIL'}
# KB pattern disciplines are free text ('MECHANICAL / BULK MATERIAL HANDLING',
# 'MECHANICAL_PIPING', …), so an exact-set test misses most systems. Match on roots.
_MEP_ROOTS = ('MECH', 'ELEC', 'ELV', 'PIP', 'INSTR', 'PLUMB', 'FIRE', 'PROCESS', 'UTIL',
              'HVAC', 'MATERIAL HANDLING', 'BULK', 'CONVEY')


def _is_mep_disc(d):
    d = (d or '').upper()
    return any(root in d for root in _MEP_ROOTS)
# interface requirements that gate testing/commissioning (the high-value checks)
_PREREQ_HINT = ('commission', 'test', 'energi', 'power', 'control', 'mechanical completion',
                'prerequisite', 'before', 'available', 'live', 'complete')

# ── coarse, FP-safe phase groups (from the tagger's ranked PHASES) ───────────
# Deliberately coarse: an inversion between two GROUPS is unambiguous construction
# nonsense on any project; a swap between two adjacent phases within a group can be
# legitimate scheduling detail, so we never flag on raw phase rank. INSULATION sits in
# the commission group (2): insulating/lagging/painting comes after erection & MC, so
# INSULATION driving an install/earlier activity is a real inversion (R4 catches it);
# the ONE ambiguous pair — insulation vs the pipe's own hydrotest, both group 2 — is
# owned by R6, which knows a line is tested before it is covered.
_GROUP_PRE = {'DESIGN', 'PROCUREMENT', 'FABRICATION', 'DELIVERY'}
_GROUP_INSTALL = {'CIVIL_INTERFACE', 'ROUGH_IN', 'ERECTION_INSTALL', 'MECHANICAL_COMPLETION'}
_GROUP_COMMISSION = {'INSULATION', 'POWER_AVAILABLE', 'PRE_COMMISSIONING', 'TESTING', 'COMMISSIONING'}
_GROUP_INTEGRATION = {'INTEGRATED_TESTING', 'PERFORMANCE', 'STARTUP', 'HANDOVER'}
_PHASE_GROUP = {}
for _gi, _grp in enumerate((_GROUP_PRE, _GROUP_INSTALL, _GROUP_COMMISSION, _GROUP_INTEGRATION)):
    for _ph in _grp:
        _PHASE_GROUP[_ph] = _gi

# R7 targets genuine plant integration only — HANDOVER is NOT a test. A construction
# handover / snagging / close-out legitimately has no commissioning behind it, so it
# must never trip R7 even though it shares the integration group for inversion checks.
_R7_INTEGRATION = {'INTEGRATED_TESTING', 'PERFORMANCE', 'STARTUP'}
# COMMISSIONING is the unambiguous LAST phase of the commission group; it driving any
# earlier commission-group phase (power-on / pre-comm / testing) is a real same-group
# inversion the coarse groups miss.
_PRE_COMMISSION = {'INSULATION', 'POWER_AVAILABLE', 'PRE_COMMISSIONING', 'TESTING'}
# FACTORY / works / shop testing legitimately precedes delivery & site install — it is
# NOT a site-testing-before-install defect. Kept narrow: only OFF-SITE markers. A bare
# 'witness test' is often on-site (witnessed by the client) and must stay a real driver.
_OFFSITE_KW = ('factory acceptance', 'factory test', 'works test', 'shop test', ' fat ',
               '(fat', 'fat)', 'f.a.t', 'ex-works', 'ex works', 'at works', 'at the works',
               'at factory', 'at vendor', "vendor's works", 'string test at works')
# Leading install/procurement verbs — if a name STARTS with one but tagged to a late
# phase (a downstream noun like 'Flushing Bypass' hijacked the phase), it is a mis-phased
# install. Matched at the START only: 'Pressure test of ERECTED piping' is a test, not an
# install, so an install word mid-name must not silence it.
_INSTALL_VERB = ('install', 'erect', 'fabricat', 'deliver', 'procure', 'supply', 'mount',
                 'lay ', 'laying', 'set ', 'setting')
# Strength / pressure tests only (R6): the STRENGTH test is what must precede a cover. A
# later 'service leak test' / 'flow test' / 'tightness test' happens AFTER reinstatement
# and is not what R6 protects, so those are deliberately absent.
_R6_STRENGTH_KW = ('hydrotest', 'hydro test', 'pressure test', 'strength test', 'pneumatic test')
# Foundation-SPECIFIC name tokens (R5). Curated to exclude ambiguous words — bare 'grout'
# ('tile grouting') and 'pad' ('crane hardstand pad') are NOT here; steel support is
# handled by the structural_steel system tag instead.
_FOUNDATION_KW = ('foundation', 'plinth', 'pedestal', 'anchor bolt', 'baseplate', 'base plate',
                  'sole plate', 'soleplate', 'pile', 'pier', 'raft', 'inertia', 'concrete pour',
                  'concrete cast', 'concrete works', 'concrete for', 'concrete base', 'substructure',
                  'sub-structure', 'base slab', 'bearing slab', 'ground bearing', 'reinforced concrete',
                  'rc base', 'r.c base', 'footing', 'mat foundation', 'skid base', 'pump base',
                  'equipment base', 'isolation base', 'rail beam', 'housekeeping')
_CIVIL_STRUCT_DISC = {'CIVIL', 'STRUCT', 'STRUCTURAL'}
# Civil elements that tag civil_interface but are NOT a machine's foundation — a cable
# trench, duct bank, manhole or sleeve carries services, not equipment. They must not
# clear R5 on their own; a name that ALSO reads as a real foundation still clears (checked
# first). Kept to items that genuinely tag civil_interface — 'excavation' is deliberately
# absent ('pump foundation excavation' is real foundation work).
_NON_FOUNDATION_CIVIL = ('trench', 'duct bank', 'manhole', 'sleeve', 'drainage', 'cable')
# Finishing / FF&E functional tests are not plant integration — a door/turnstile/AV
# 'functional test' tags INTEGRATED_TESTING but must not trip R7.
_R7_EXCLUDE_KW = ('door', 'window', 'sanitary', 'joinery', 'furniture', 'ff&e', 'ff & e',
                  'signage', 'turnstile', 'barrier', 'gate ', 'shutter', 'partition', 'ceiling',
                  'flooring', 'fixture', 'louvre', 'blind', 'curtain wall', 'balustrade')
_ZONE_RX = __import__('re').compile(
    r'\b(?:line|loop|riser|zone|unit|train|area|sector|phase|section|bay|grid|block|no\.?|#)\s*'
    r'([a-z0-9]{1,4})\b')

# The tagger collapses all piping patterns into one system id 'piping'; the KB stores
# them as separate patterns. Normalise BOTH ways so a rule reads the right pattern and
# checks presence against what the tagger actually tags — without this, piping rules
# silently never fire (a false-negative trap, not a visible error).
_SYS_TO_PATTERN = {'piping': 'process_piping'}
_PATTERN_TO_SYS = {'process_piping': 'piping', 'utility_piping': 'piping',
                   'pipe_racks': 'piping', 'pipe_spool_fabrication': 'piping'}
_EQUIP_SYS = {'mechanical_equipment', 'rotating_equipment', 'process_equipment', 'tanks_vessels'}
# electrical_power is owned by R1; civil_interface is owned by R5 — the generic
# cross-system rule R3 skips both so findings don't double-report.
_R3_SKIP_REQUIRED = {'electrical_power', 'civil_interface'}

_TESTING_KW = ('hydrotest', 'hydro test', 'pressure test', 'leak test', 'pneumatic test', 'strength test')
_INSULATION_KW = ('insulation', 'lagging', 'painting', 'coating', 'wrapping')
# NB: 'final bolt'/'bolt-up' removed — bolt-up is a REQUIRED pre-test make-up of the
# joint, not a post-test reinstatement; keeping it here false-flagged bolt-up→hydrotest.
_REINSTATE_KW = ('reinstat', 'in-line item', 'in line item', 'box-up', 'box up', 'reassembl',
                 'valve reinstall', 'de-blind', 'de blind', 'remove blind')
# piping-like systems whose lines are pressure-tested before being covered (R6)
_PIPING_LIKE = {'piping', 'chilled_water', 'plumbing', 'utilities', 'fire_fighting'}


def _ensure_tagged(view):
    rows = view.get('activities_oid') or []
    if rows and 'identity' not in rows[0]:
        tag_view(view)


def _preds(view, oid):
    return [r['pred_oid'] for r in view.get('relationships_oid', []) if r['succ_oid'] == oid]


def _label(a):
    return a.get('id') or a.get('name') or a.get('object_id')


def _to_sys(pid):
    return _PATTERN_TO_SYS.get(pid, pid)


def _to_pattern(sysid):
    return _SYS_TO_PATTERN.get(sysid, sysid)


def _sys_of(a):
    return (a.get('identity') or {}).get('system')


def _phase_of(a):
    return (a.get('identity') or {}).get('phase')


def _group_of(a):
    return _PHASE_GROUP.get(_phase_of(a))


def _nm(a):
    return (a.get('name') or '').lower()


def _disc_of(a):
    return ((a.get('identity') or {}).get('discipline') or '').upper()


def _zone(a):
    """A physical line / zone / loop / unit token from the activity name, or None. Two
    activities with DIFFERENT explicit tokens are different physical lines — a dependency
    between them is crew/area sequencing, not a technical constraint, so a phase inversion
    across it is not a defect."""
    m = _ZONE_RX.search(_nm(a))
    return m.group(1) if m else None


def _diff_zone(a, b):
    za, zb = _zone(a), _zone(b)
    return za is not None and zb is not None and za != zb


def _is_offsite(a):
    """Factory / works / shop / FAT testing — vendor testing that legitimately precedes
    delivery and site installation, so it must not read as 'site testing before install'."""
    return any(k in _nm(a) for k in _OFFSITE_KW)


def _mis_phased_install(a):
    """An install/procurement-named activity that tagged to a late phase because a
    downstream noun in its name (e.g. 'Install CHW Flushing Bypass') hijacked the phase.
    Matched at the START of the name only: 'Pressure test of erected piping' is a genuine
    test whose mid-name 'erected' must NOT silence it."""
    if (_group_of(a) or 0) < 2:
        return False
    n = _nm(a).lstrip()
    return any(n.startswith(v) for v in _INSTALL_VERB)


def _bad_inversion_driver(a):
    """Predecessors that must never be treated as the 'later work' in an inversion."""
    return _is_offsite(a) or _mis_phased_install(a)


def _any_ancestor(pred_map, by_oid, oid, ok, limit=6000):
    """True if any transitive predecessor of `oid` satisfies predicate ok(activity).
    Bounded BFS — safe on very large schedules."""
    seen, stack = set(), list(pred_map.get(oid, ()))
    while stack and len(seen) < limit:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        a = by_oid.get(p, {})
        if ok(a):
            return True
        stack.extend(pred_map.get(p, ()))
    return False


def _has_support(pred_map, by_oid, oid):
    """Does the equipment install at `oid` have its OWN foundation/steel support behind
    it? Activity-level so it survives the tagger demoting an '<equipment> foundation' /
    'grouting' activity to system=None. Clears on:
      • a DIRECT predecessor that is civil / steel / a CIVIL_INTERFACE-phase activity —
        the foundation right before the setting; OR
      • a foundation/support-NAMED or structural-steel activity anywhere upstream.
    An unrelated civil activity several hops away (e.g. a cable trench reached through
    the cabling chain) does NOT clear it — that is not the machine's foundation."""
    for p in pred_map.get(oid, ()):                    # direct predecessors
        a = by_oid.get(p, {})
        nm = _nm(a)
        if any(k in nm for k in _FOUNDATION_KW):        # a real foundation right before the setting
            return True
        if any(k in nm for k in _NON_FOUNDATION_CIVIL):  # a trench/duct/cable is not the machine's base
            continue
        if _sys_of(a) in ('civil_interface', 'structural_steel') or _phase_of(a) == 'CIVIL_INTERFACE':
            return True
    return _any_ancestor(pred_map, by_oid, oid,       # or clearly-foundation-named / steel activity upstream
                         lambda x: _sys_of(x) == 'structural_steel'
                         or any(k in _nm(x) for k in _FOUNDATION_KW))


def _system_precedence(view, by_oid):
    """Transitive system-level precedence closure. Returns preceded_by[s] = the set of
    systems that have a scheduling path INTO system s. Computed on the ~22 tagged
    systems (tiny), so cross-system enabler checks are cheap and never need per-activity
    graph walks. A system pair is 'linked' iff one appears in the other's set."""
    adj_rev = {}   # system -> systems immediately before it
    for r in view.get('relationships_oid', []):
        ps = _sys_of(by_oid.get(r['pred_oid'], {}))
        ss = _sys_of(by_oid.get(r['succ_oid'], {}))
        if ps and ss and ps != ss:
            adj_rev.setdefault(ss, set()).add(ps)
    out = {}
    for s in adj_rev:
        seen, stack = set(), list(adj_rev.get(s, ()))
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend(adj_rev.get(x, ()))
        out[s] = seen
    return out


def _has_ancestor_group(view, by_oid, pred_map, oid, group, limit=4000):
    """Does any transitive predecessor of `oid` sit in the given phase group?
    Bounded BFS (capped) so it stays safe on very large schedules."""
    seen, stack = set(), list(pred_map.get(oid, ()))
    while stack and len(seen) < limit:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        if _PHASE_GROUP.get(_phase_of(by_oid.get(p, {}))) == group:
            return True
        stack.extend(pred_map.get(p, ()))
    return False


def _strong_enabler_edges(patterns):
    """Every strong 'requires'/'enabler' interface across the KB, normalised into
    tagger-system space as (dependent_system, required_system, iface, pattern_id).
    Mutual pairs (A needs B and B needs A — the bms/hvac/chilled/fire integration
    cluster) are dropped by the caller: a mutual coupling is coordination, not a hard
    predecessor, and enforcing it as one would false-positive in both directions."""
    edges = []
    for pid, pat in patterns.items():
        s = _to_sys(pid)
        for i in pat.get('interfaces', []):
            if i.get('type') in ('requires', 'enabler') and i.get('strength') == 'strong':
                w = _to_sys((i.get('with') or '').strip().lower())
                if w and w != s:
                    edges.append((s, w, i, pid))
    return edges


def _iface_required_systems(iface, patterns):
    """The authored interface 'with' field is inconsistent (sometimes a system id,
    sometimes prose like 'MEP - electrical first fix'). Resolve it to actual system
    ids by matching the pattern aliases against the interface text, plus a few
    canonical prerequisite phrases. Returns a set of system ids."""
    w = (iface.get('with') or '').strip().lower()
    text = w + ' ' + (iface.get('requirement') or '').lower()
    req = set()
    for sid, pat in patterns.items():
        if sid == w or sid.replace('_', ' ') in w:
            req.add(sid)
            continue
        for al in pat.get('aliases', []):
            a = (al or '').lower().strip()
            if len(a) >= 4 and a in text:
                req.add(sid)
                break
    if any(k in text for k in ('permanent power', 'energiz', 'power available', 'temporary power', 'live power')):
        req.add('electrical_power')
    if 'control system' in text or ('control' in text and 'live' in text) or ' bms' in text:
        req.add('bms')
    return req


def generate_findings(view, resolution, patterns=None):
    """Return a list of evidence-graded findings (may be empty). Read-only."""
    if not resolution:
        return []
    patterns = patterns if patterns is not None else load_system_patterns()
    _ensure_tagged(view)
    by_oid = view.get('by_oid', {})
    present = {p['system'] for p in resolution.get('relevant_patterns', []) if p['present']}

    # index activities by their tagged system
    sys_acts = {}
    for a in view.get('activities_oid', []):
        s = (a.get('identity') or {}).get('system')
        if s:
            sys_acts.setdefault(s, []).append(a)
    # what is ACTUALLY in the schedule (tagged), independent of which systems the
    # archetype lists as relevant — R1's power gate must key off this, else a project
    # whose archetype doesn't list electrical_power (e.g. a silo) goes N/A even though
    # MV switchgear is plainly in the schedule.
    sys_present = set(sys_acts)

    # predecessor adjacency, built once — used by the transitive checks in R1/R5/R6/R7
    pred_map = {}
    for r in view.get('relationships_oid', []):
        pred_map.setdefault(r['succ_oid'], set()).add(r['pred_oid'])

    def _powered(a):
        """The activity's power enabler — a permanent-power/energization predecessor,
        transitively. Accept an ancestor tagged electrical_power, OR a POWER_AVAILABLE
        activity of the SAME system (a system's own energization often tags to that
        system — 'Fire pump energization' tags fire_fighting). A POWER_AVAILABLE activity
        of a DIFFERENT system (an unrelated 'AHU energization' upstream) does NOT count —
        that would wrongly clear a genuinely-unpowered system."""
        s = _sys_of(a)
        return _any_ancestor(pred_map, by_oid, a['object_id'],
                             lambda x: _sys_of(x) == 'electrical_power'
                             or (_phase_of(x) == 'POWER_AVAILABLE' and _sys_of(x) == s))

    findings = []
    # Iterate what is ACTUALLY tagged in the schedule, not the archetype's relevant-
    # patterns list — otherwise R1/R2 skip a system (e.g. a chiller) whenever the
    # resolved archetype happens not to list it.
    for sysid, acts in sys_acts.items():
        pat = patterns.get(_to_pattern(sysid), {})
        disc = pat.get('discipline', '')
        if not acts:
            continue
        late = [a for a in acts if (a.get('identity') or {}).get('phase') in _LATE]

        # ── Rule 1: functional commissioning not tied to permanent power ──
        # Power/energization is the ONE universal commissioning prerequisite (nothing runs
        # before it is energised). Deliberately narrow: only FUNCTIONAL commissioning /
        # running (not hydraulic tests, which need no power), only electrical power, only
        # when power IS in the project (absent ⇒ N/A). Evaluated PER activity — one powered
        # AHU does not vouch for an unpowered AHU beside it. Transitive; a same-system or
        # electrical energization anywhere upstream counts.
        commissioning = [a for a in acts if _phase_of(a) in _R1_POWER_LATE]
        if commissioning and _is_mep_disc(disc) and sysid != 'electrical_power' \
                and 'electrical_power' in sys_present:
            unpowered = [a for a in commissioning if not _powered(a)]
            if unpowered:
                findings.append({
                    'kind': 'missing_interface', 'system': sysid, 'discipline': disc,
                    'title': f"{pat.get('name', sysid)} commissioning not tied to permanent power",
                    'existing': f"{len(unpowered)} {sysid} commissioning / performance / start-up "
                                f"activit{'y has' if len(unpowered) == 1 else 'ies have'} no electrical "
                                f"energization predecessor.",
                    'actual': f"No path from electrical power into the {sysid} commissioning.",
                    'expected': "Permanent power / energization precedes equipment commissioning and running.",
                    'reason': "Equipment cannot be functionally commissioned or run before power is available.",
                    'evidence': pat.get('evidence', '') or "Commissioning requires the system to be energised first.",
                    'strength': 'strong',
                    'impact': f"{sysid} may be commissioned before power is available — an unbuildable sequence.",
                    'recommendation': "Add an electrical energization / permanent-power predecessor to the "
                                      "commissioning, or confirm power is provided another way.",
                    'activities': [_label(a) for a in unpowered[:6]],
                })

        # ── Rule 2: within-system out-of-sequence — a late-phase activity DRIVES an
        #    install-phase activity of the same system (testing before installation) ──
        install_oids = {a['object_id'] for a in acts if (a.get('identity') or {}).get('phase') in _INSTALL}
        # exclude off-site / mis-phased-install drivers: a Factory Acceptance Test or a
        # 'Install … Test Station' legitimately precedes site installation.
        late_oids = {a['object_id'] for a in late if not _bad_inversion_driver(a)}
        for r in view.get('relationships_oid', []):
            if r['pred_oid'] in late_oids and r['succ_oid'] in install_oids:
                pa, sa = by_oid.get(r['pred_oid'], {}), by_oid.get(r['succ_oid'], {})
                if _phase_of(pa) == 'PRE_COMMISSIONING' and any(k in _nm(sa) for k in _REINSTATE_KW):
                    continue                           # flush → reinstate in-line items is correct (R6)
                if _diff_zone(pa, sa):
                    continue                           # different physical lines — crew handover, not an inversion
                findings.append({
                    'kind': 'out_of_sequence', 'system': sysid, 'discipline': disc,
                    'title': f"{pat.get('name', sysid)} testing precedes installation",
                    'existing': f"'{pa.get('name','')}' (testing/commissioning) drives '{sa.get('name','')}' (installation).",
                    'expected': "Installation/mechanical completion precedes testing and commissioning.",
                    'reason': "A system cannot be tested or commissioned before it is installed.",
                    'evidence': pat.get('evidence', ''),
                    'strength': 'strong',
                    'impact': "The sequence is not physically buildable and will not survive F9.",
                    'recommendation': "Reverse the dependency: install → test → pre-commission → commission.",
                    'activities': [_label(pa), _label(sa)],
                })

    # ── shared structure for the generalized rules R3–R7 ──────────────────────
    preceded_by = _system_precedence(view, by_oid)

    def _disc(sysid):
        return patterns.get(_to_pattern(sysid), {}).get('discipline', '')

    def _pat(sysid):
        return patterns.get(_to_pattern(sysid), {})

    # ── Rule 3: cross-system enabler INVERSION. The KB records that system S requires
    #    enabler W (strong). If an explicit link has the COMMISSIONING of S driving a W
    #    activity at install-or-earlier, the enabler has been pushed behind the very work
    #    that needs it. Narrowed to a COMMISSIONING driver on purpose: a standalone TEST
    #    of S (e.g. an API-650 tank hydrotest before its piping tie-in, or fitting tank
    #    instruments after the test) legitimately precedes the enabler's install and must
    #    NOT fire. Inversion-based (an absent cross-system link is normal); mutual
    #    couplings and power (R1) / civil (R5) excluded. ──
    edges = _strong_enabler_edges(patterns)
    edge_pairs = {(s, w) for s, w, _i, _p in edges}
    live_edges = [(s, w, i, p) for (s, w, i, p) in edges
                  if s in sys_present and w in sys_present
                  and w not in _R3_SKIP_REQUIRED and (w, s) not in edge_pairs]
    edge_by_pair = {(s, w): (i, p) for (s, w, i, p) in live_edges}
    seen_r3 = set()
    for r in view.get('relationships_oid', []):
        pa, sa = by_oid.get(r['pred_oid'], {}), by_oid.get(r['succ_oid'], {})
        s, w = _sys_of(pa), _sys_of(sa)               # S drives W  (dependent drives enabler)
        if (s, w) not in edge_by_pair or (s, w) in seen_r3:
            continue
        if _phase_of(pa) not in ('COMMISSIONING', 'STARTUP') or _bad_inversion_driver(pa):
            continue                                   # only a commissioning/start-up driver, never a bare test
        gw = _group_of(sa)
        if gw is None or gw > 1:
            continue                                   # enabler must be at install-or-earlier
        seen_r3.add((s, w))
        iface, _pid = edge_by_pair[(s, w)]
        req_name = _pat(w).get('name', w)
        findings.append({
            'kind': 'out_of_sequence', 'system': s, 'discipline': _disc(s),
            'title': f"{_pat(s).get('name', s)} scheduled ahead of its required {req_name}",
            'existing': f"'{pa.get('name', '')}' ({_phase_of(pa)}, {s}) drives "
                        f"'{sa.get('name', '')}' ({_phase_of(sa)}, {w}) — the enabler comes after "
                        f"the work that needs it.",
            'expected': (iface.get('requirement')
                         or f"{req_name} is in place before {_pat(s).get('name', s)} proceeds."),
            'reason': f"The KB records a strong '{iface.get('type', 'requires')}' interface: "
                      f"{s} depends on {w}, so {w} must come first.",
            'evidence': _pat(s).get('evidence', '') or iface.get('requirement', ''),
            'strength': 'strong',
            'impact': f"{s} is sequenced ahead of the {w} it depends on — an unbuildable interface.",
            'recommendation': f"Reverse the dependency so {w} enables {s}.",
            'activities': [_label(pa), _label(sa)],
        })

    # ── Rule 4: within-system phase inversion (generalises R2). Fires on a later-GROUP
    #    activity driving an earlier-group one of the SAME system, PLUS the one safe
    #    within-group case: COMMISSIONING (the unambiguous last phase of the commission
    #    group) driving an earlier commission phase (power-on / pre-comm / testing).
    #    Guards: a Factory Acceptance Test or a mis-phased install is not a real driver;
    #    and post-flush REINSTATEMENT of in-line items is the correct order (per R6), not
    #    an inversion. ──
    for r in view.get('relationships_oid', []):
        pa, sa = by_oid.get(r['pred_oid'], {}), by_oid.get(r['succ_oid'], {})
        ps, ss = _sys_of(pa), _sys_of(sa)
        if not ps or ps != ss:
            continue
        gp, gs = _group_of(pa), _group_of(sa)
        if gp is None or gs is None:
            continue
        group_inversion = gp > gs
        commission_inversion = (_phase_of(pa) == 'COMMISSIONING' and _phase_of(sa) in _PRE_COMMISSION)
        if not (group_inversion or commission_inversion):
            continue
        if _bad_inversion_driver(pa):
            continue                                   # FAT / mis-phased install — not a real driver
        if _phase_of(pa) == 'PRE_COMMISSIONING' and any(k in _nm(sa) for k in _REINSTATE_KW):
            continue                                   # flush → reinstate in-line items is correct (R6)
        if _diff_zone(pa, sa):
            continue                                   # different physical lines — a crew handover, not an inversion
        findings.append({
            'kind': 'out_of_sequence', 'system': ps, 'discipline': _disc(ps),
            'title': f"{_pat(ps).get('name', ps)}: later work drives earlier work",
            'existing': f"'{pa.get('name', '')}' ({_phase_of(pa)}) drives "
                        f"'{sa.get('name', '')}' ({_phase_of(sa)}) in the same system.",
            'expected': "Earlier construction phases precede later ones within a system.",
            'reason': "A later phase cannot be a predecessor of an earlier phase of the same system.",
            'evidence': _pat(ps).get('evidence', ''),
            'strength': 'strong',
            'impact': "The sequence is not physically buildable and will not survive F9.",
            'recommendation': "Reverse the dependency so the earlier phase drives the later one.",
            'activities': [_label(pa), _label(sa)],
        })

    # ── Rule 5: equipment set with NO foundation/support interface (MEP↔civil).
    #    Evaluated PER install activity (not system-wide): each setting activity must
    #    have its OWN foundation/steel support behind it — a foundation for one pump does
    #    not carry a second pump beside it. The support check is activity-level and name-
    #    aware, so it survives the tagger demoting an '<equipment> foundation' / grouting
    #    activity to system=None. Either a foundation OR supporting steel clears it
    #    (steel-mounted equipment is legitimate). Graded moderate. Absent equipment ⇒ N/A. ──
    for e in (_EQUIP_SYS & sys_present):
        unsupported = [a for a in sys_acts.get(e, [])
                       if _phase_of(a) in ('ERECTION_INSTALL', 'MECHANICAL_COMPLETION')
                       and not _has_support(pred_map, by_oid, a['object_id'])]
        if not unsupported:
            continue                                   # every setting activity has support (or none exists) — silent
        findings.append({
            'kind': 'missing_interface', 'system': e, 'discipline': _disc(e),
            'title': f"{_pat(e).get('name', e)} set with no foundation or supporting-steel interface",
            'existing': f"{len(unsupported)} {e} setting/installation activit"
                        f"{'y has' if len(unsupported) == 1 else 'ies have'} no foundation, "
                        f"grouting or supporting-steel predecessor.",
            'expected': "Equipment is set on a cured foundation (surveyed, grouted) or on erected "
                        "supporting steel before installation.",
            'reason': "Equipment cannot be set, levelled and grouted before its foundation or "
                      "support steel exists.",
            'evidence': _pat(e).get('evidence', '')
                        or "Setting requires the foundation at strength with anchors to template.",
            'strength': 'moderate',
            'impact': "Equipment installation may be sequenced ahead of the civil/steel interface "
                      "that carries it.",
            'recommendation': "Add the equipment-foundation (or supporting-steel) predecessor to the "
                              "setting activities, or confirm the support interface.",
            'activities': [_label(a) for a in unsupported[:6]],
        })

    # ── Rule 6: a pipe insulated / covered BEFORE its STRENGTH test. INSULATION and the
    #    pipe's hydrotest both land in the commission group, so R4 can't tell them apart —
    #    R6 knows a line is strength-tested before it is covered. Deliberately tight to
    #    avoid the cross-line traps a transitive/broad rule fell into:
    #      • the test must be a STRENGTH/pressure test by name — a later 'service leak
    #        test' / 'flow test' after reinstatement is legitimate and never the gate;
    #      • the cover must DIRECTLY drive the test — a transitive path from line A's
    #        insulation to line B's test is crew sequencing, not a covered-before-tested
    #        defect;
    #      • and the two must not name DIFFERENT physical lines/zones.
    #    Runs on every piping-like system (process piping, chilled water, plumbing,
    #    utilities, fire water). No strength test / no cover ⇒ N/A. ──
    for psys in (_PIPING_LIKE & sys_present):
        pipe = sys_acts.get(psys, [])
        hydro_oids = {a['object_id'] for a in pipe if any(k in _nm(a) for k in _R6_STRENGTH_KW)}
        cover_oids = {a['object_id'] for a in pipe
                      if _phase_of(a) == 'INSULATION' or any(k in _nm(a) for k in _INSULATION_KW)
                      or any(k in _nm(a) for k in _REINSTATE_KW)}
        if not hydro_oids or not cover_oids:
            continue                                   # N/A — no strength test, or nothing that covers the line
        for r in view.get('relationships_oid', []):
            if r['pred_oid'] in cover_oids and r['succ_oid'] in hydro_oids:
                cover, h = by_oid.get(r['pred_oid'], {}), by_oid.get(r['succ_oid'], {})
                if _diff_zone(cover, h):
                    continue                           # different lines/zones — sectional test/insulate, correct
                findings.append({
                    'kind': 'out_of_sequence', 'system': psys, 'discipline': _disc(psys),
                    'title': "Pipe insulated / boxed up before it was pressure-tested",
                    'existing': f"'{cover.get('name', '')}' directly precedes the strength test "
                                f"'{h.get('name', '')}' — the line is covered before it is tested.",
                    'expected': "Hydrotest → flush/clean → reinstate in-line items → insulate/paint.",
                    'reason': "A pipe joint must be pressure-tested before it is covered; insulating or "
                              "boxing up first hides the joints the test must reach.",
                    'evidence': _pat(psys).get('evidence', ''),
                    'strength': 'strong',
                    'impact': "Insulation/reinstatement would have to be stripped to test — rework, or an "
                              "untested line.",
                    'recommendation': "Sequence the hydrotest before insulation, painting and in-line "
                                      "reinstatement.",
                    'activities': [_label(cover), _label(h)],
                })

    # ── Rule 7: integrated / performance / start-up test with NO commissioning behind
    #    it. Systems are proven individually (commissioning) before they are run
    #    together (integrated testing). An integration-group activity with no
    #    commissioning-group predecessor anywhere is the classic 'test the plant before
    #    the parts work' gap. No integration activities ⇒ N/A. ──
    # NB: iterate ALL activities, not sys_acts — integrated/performance/start-up work
    # is usually plant-wide and tags to no single system (system=None), so it never
    # enters sys_acts. Scanning sys_acts here would make R7 silently un-fireable.
    # Target genuine plant-integration tests ONLY — HANDOVER is excluded: a construction
    # handover / snagging / close-out legitimately has no commissioning behind it.
    all_acts = view.get('activities_oid', [])
    # 'Commissioned' means an ACTUAL testing/commissioning phase — not merely group 2,
    # which now also holds INSULATION (pipe lagging must not count as commissioning).
    _proved = {'TESTING', 'PRE_COMMISSIONING', 'COMMISSIONING'}
    commission_exists = any(_phase_of(a) in _proved for a in all_acts)
    for a in all_acts:
        if _phase_of(a) in _R7_INTEGRATION and not any(k in _nm(a) for k in _R7_EXCLUDE_KW):
            if _any_ancestor(pred_map, by_oid, a['object_id'], lambda x: _phase_of(x) in _proved):
                continue                               # an individual-system test/commissioning precedes it — silent
            findings.append({
                'kind': 'sequence_gap', 'system': _sys_of(a), 'discipline': _disc(_sys_of(a)),
                'title': "Integrated / performance test not preceded by commissioning",
                'existing': f"'{a.get('name', '')}' ({_phase_of(a)}) has no commissioning / "
                            f"pre-commissioning predecessor.",
                'expected': "Individual systems are commissioned before integrated, performance or "
                            "start-up testing runs them together.",
                'reason': "Integrated and performance testing exercises systems that must each be "
                          "commissioned and proven first.",
                'evidence': patterns.get('commissioning', {}).get('evidence', '')
                            or "Integrated testing follows individual system commissioning.",
                'strength': 'strong' if commission_exists else 'moderate',
                'impact': "The plant would be run as a whole before its parts are proven — an "
                          "unsafe, unbuildable sequence.",
                'recommendation': "Tie the integrated/performance test to the commissioning of the "
                                  "systems it exercises.",
                'activities': [_label(a)],
            })

    # ── dedup: rules deliberately overlap (R2⊂R4, R1 vs R3); collapse findings that
    #    are the same defect on the same activities, keeping the strongest grade. ──
    deduped, seen_key = [], {}
    for f in findings:
        key = (f['kind'], frozenset(f.get('activities') or []))
        if key in seen_key:
            j = seen_key[key]
            if _STRENGTH.get(f['strength'], 1) > _STRENGTH.get(deduped[j]['strength'], 1):
                deduped[j] = f
            continue
        seen_key[key] = len(deduped)
        deduped.append(f)
    findings = deduped

    # stable, MEP-first, strong-first ordering
    findings.sort(key=lambda f: (-_STRENGTH.get(f['strength'], 1),
                                 not _is_mep_disc(f['discipline']), f['system']))
    return findings
