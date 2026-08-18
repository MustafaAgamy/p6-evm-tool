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
_INSTALL = {'ERECTION_INSTALL', 'MECHANICAL_COMPLETION', 'ROUGH_IN'}
_STRENGTH = {'strong': 3, 'moderate': 2, 'weak': 1, 'insufficient': 0}
_MEP_DISC = {'MECH', 'ELEC', 'ELV', 'PIPING', 'INSTR', 'PLUMB', 'FIRE', 'PROCESS', 'UTIL'}
# interface requirements that gate testing/commissioning (the high-value checks)
_PREREQ_HINT = ('commission', 'test', 'energi', 'power', 'control', 'mechanical completion',
                'prerequisite', 'before', 'available', 'live', 'complete')

# ── coarse, FP-safe phase groups (from the tagger's ranked PHASES) ───────────
# Deliberately coarse: an inversion between two GROUPS is unambiguous construction
# nonsense on any project; a swap between two adjacent phases within a group can be
# legitimate scheduling detail, so we never flag on raw phase rank. INSULATION is
# left OUT of every group on purpose — its true position is system-dependent
# (after hydrotest for piping, around MC elsewhere), so R6 handles piping insulation
# specifically and the generic inversion rule never touches it.
_GROUP_PRE = {'DESIGN', 'PROCUREMENT', 'FABRICATION', 'DELIVERY'}
_GROUP_INSTALL = {'CIVIL_INTERFACE', 'ROUGH_IN', 'ERECTION_INSTALL', 'MECHANICAL_COMPLETION'}
_GROUP_COMMISSION = {'POWER_AVAILABLE', 'PRE_COMMISSIONING', 'TESTING', 'COMMISSIONING'}
_GROUP_INTEGRATION = {'INTEGRATED_TESTING', 'PERFORMANCE', 'STARTUP', 'HANDOVER'}
_PHASE_GROUP = {}
for _gi, _grp in enumerate((_GROUP_PRE, _GROUP_INSTALL, _GROUP_COMMISSION, _GROUP_INTEGRATION)):
    for _ph in _grp:
        _PHASE_GROUP[_ph] = _gi

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
_REINSTATE_KW = ('reinstat', 'in-line', 'in line', 'box-up', 'box up', 'final bolt', 'reassembl')


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

    findings = []
    for pinfo in resolution.get('relevant_patterns', []):
        if not pinfo['present']:
            continue
        sysid = pinfo['system']
        pat = patterns.get(sysid, {})
        acts = sys_acts.get(sysid, [])
        if not acts:
            continue
        late = [a for a in acts if (a.get('identity') or {}).get('phase') in _LATE]

        # ── Rule 1: MEP testing/commissioning not tied to permanent power ──
        # Power/energization is the ONE universal commissioning prerequisite (nothing
        # commissions before it is energised). Deliberately narrow: only electrical
        # power, and only when power IS in the project (absent ⇒ N/A, never a defect).
        if late and pinfo['discipline'] in _MEP_DISC and sysid != 'electrical_power' and 'electrical_power' in present:
            linked_power = any(
                (by_oid.get(p, {}).get('identity') or {}).get('system') == 'electrical_power'
                for a in late for p in _preds(view, a['object_id']))
            if not linked_power:
                findings.append({
                    'kind': 'missing_interface', 'system': sysid, 'discipline': pinfo['discipline'],
                    'title': f"{pat.get('name', sysid)} testing/commissioning not tied to permanent power",
                    'existing': f"{len(late)} {sysid} testing/commissioning activities; none has an electrical / energization predecessor.",
                    'actual': f"No Finish-to-Start link from electrical power into the {sysid} testing/commissioning.",
                    'expected': "Permanent power / energization precedes equipment testing and commissioning.",
                    'reason': "Equipment cannot be functionally tested or commissioned before power is available.",
                    'evidence': pat.get('evidence', '') or "Commissioning requires the system to be energised first.",
                    'strength': 'strong',
                    'impact': f"{sysid} may be commissioned before power is available — an unbuildable sequence.",
                    'recommendation': "Add an electrical energization / permanent-power predecessor to the testing & commissioning, or confirm power is provided another way.",
                    'activities': [_label(a) for a in late[:6]],
                })

        # ── Rule 2: within-system out-of-sequence — a late-phase activity DRIVES an
        #    install-phase activity of the same system (testing before installation) ──
        install_oids = {a['object_id'] for a in acts if (a.get('identity') or {}).get('phase') in _INSTALL}
        late_oids = {a['object_id'] for a in late}
        for r in view.get('relationships_oid', []):
            if r['pred_oid'] in late_oids and r['succ_oid'] in install_oids:
                pa, sa = by_oid.get(r['pred_oid'], {}), by_oid.get(r['succ_oid'], {})
                findings.append({
                    'kind': 'out_of_sequence', 'system': sysid, 'discipline': pinfo['discipline'],
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
    sys_present = set(sys_acts)
    preceded_by = _system_precedence(view, by_oid)
    pred_map = {}
    for r in view.get('relationships_oid', []):
        pred_map.setdefault(r['succ_oid'], set()).add(r['pred_oid'])

    def _disc(sysid):
        return patterns.get(_to_pattern(sysid), {}).get('discipline', '')

    def _pat(sysid):
        return patterns.get(_to_pattern(sysid), {})

    # ── Rule 3: cross-system enabler INVERSION. The KB records that system S requires
    #    enabler W (strong). If an explicit link has an S activity DRIVING a W activity
    #    at a strictly-earlier construction stage, the enabler has been pushed behind
    #    the very work that needs it. Inversion-based on purpose: an *absent* cross-
    #    system link is normal on real schedules (the enabler is often implicit or
    #    wired via a third system), so only wrong-DIRECTION logic is flagged — never a
    #    missing one. Mutual couplings and power (R1) / civil (R5) are excluded. ──
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
        gp, gw = _group_of(pa), _group_of(sa)
        if gp is None or gw is None or gp <= gw:
            continue                                   # only a strictly-later dependent → earlier enabler
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

    # ── Rule 4: within-system phase-GROUP inversion (generalises R2 to every system
    #    and every group jump). A later-group activity driving an earlier-group one of
    #    the SAME system is physically impossible. Coarse groups ⇒ no false positives
    #    from adjacent-phase scheduling detail. ──
    for r in view.get('relationships_oid', []):
        pa, sa = by_oid.get(r['pred_oid'], {}), by_oid.get(r['succ_oid'], {})
        ps, ss = _sys_of(pa), _sys_of(sa)
        if not ps or ps != ss:
            continue
        gp, gs = _group_of(pa), _group_of(sa)
        if gp is None or gs is None or gp <= gs:
            continue
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

    # ── Rule 5: equipment set with NO foundation/support interface (MEP↔civil). An
    #    equipment system with installation work but nothing from civil (foundation/
    #    grouting) OR structural steel driving it — set on nothing. Steel-mounted
    #    equipment is legitimate, so EITHER a civil OR a steel predecessor clears it.
    #    Graded moderate: the support may be implicit. Absent equipment ⇒ N/A. ──
    for e in (_EQUIP_SYS & sys_present):
        installs = [a for a in sys_acts.get(e, [])
                    if _phase_of(a) in ('CIVIL_INTERFACE', 'ERECTION_INSTALL', 'MECHANICAL_COMPLETION')]
        if not installs:
            continue                                   # N/A — no setting work for this equipment
        anc = preceded_by.get(e, set())
        if 'civil_interface' in anc or 'structural_steel' in anc:
            continue                                   # a foundation or steel support precedes it — silent
        findings.append({
            'kind': 'missing_interface', 'system': e, 'discipline': _disc(e),
            'title': f"{_pat(e).get('name', e)} set with no foundation or supporting-steel interface",
            'existing': f"{len(installs)} {e} setting/installation activities, with no civil "
                        f"foundation and no structural-steel activity driving them.",
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
            'activities': [_label(a) for a in installs[:4]],
        })

    # ── Rule 6: piping insulation / in-line reinstatement scheduled BEFORE the
    #    hydrotest (piping test-ordering). The global phase rank puts INSULATION before
    #    TESTING, so the generic inversion rule can't see this — but a line must be
    #    pressure-tested BEFORE it is insulated, painted or its in-line valves boxed up.
    #    No hydrotest in the piping scope ⇒ N/A. ──
    pipe = sys_acts.get('piping', [])
    hydro_oids = {a['object_id'] for a in pipe
                  if any(k in _nm(a) for k in _TESTING_KW) or _phase_of(a) == 'TESTING'}
    if hydro_oids:
        cover_oids = {a['object_id'] for a in pipe
                      if _phase_of(a) == 'INSULATION' or any(k in _nm(a) for k in _INSULATION_KW)
                      or any(k in _nm(a) for k in _REINSTATE_KW)}
        for r in view.get('relationships_oid', []):
            if r['pred_oid'] in cover_oids and r['succ_oid'] in hydro_oids:
                pa, sa = by_oid.get(r['pred_oid'], {}), by_oid.get(r['succ_oid'], {})
                findings.append({
                    'kind': 'out_of_sequence', 'system': 'piping', 'discipline': _disc('piping'),
                    'title': "Piping insulated / boxed up before it was pressure-tested",
                    'existing': f"'{pa.get('name', '')}' drives '{sa.get('name', '')}' — cover/reinstatement "
                                f"before the hydrotest.",
                    'expected': "Hydrotest → flush/clean → reinstate in-line items → insulate/paint.",
                    'reason': "A pipe joint must be pressure-tested before it is covered; insulating or "
                              "boxing up first hides the joints the test must reach.",
                    'evidence': _pat('piping').get('evidence', ''),
                    'strength': 'strong',
                    'impact': "Insulation/reinstatement would have to be stripped to test — rework, or an "
                              "untested line.",
                    'recommendation': "Sequence the hydrotest before insulation, painting and in-line "
                                      "reinstatement.",
                    'activities': [_label(pa), _label(sa)],
                })

    # ── Rule 7: integrated / performance / start-up test with NO commissioning behind
    #    it. Systems are proven individually (commissioning) before they are run
    #    together (integrated testing). An integration-group activity with no
    #    commissioning-group predecessor anywhere is the classic 'test the plant before
    #    the parts work' gap. No integration activities ⇒ N/A. ──
    # NB: iterate ALL activities, not sys_acts — integrated/performance/start-up work
    # is usually plant-wide and tags to no single system (system=None), so it never
    # enters sys_acts. Scanning sys_acts here would make R7 silently un-fireable.
    all_acts = view.get('activities_oid', [])
    commission_exists = any(_group_of(a) == 2 for a in all_acts)
    for a in all_acts:
        if _group_of(a) == 3:
            if _has_ancestor_group(view, by_oid, pred_map, a['object_id'], 2):
                continue                               # a commissioning activity precedes it — silent
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
                                 f['discipline'] not in _MEP_DISC, f['system']))
    return findings
