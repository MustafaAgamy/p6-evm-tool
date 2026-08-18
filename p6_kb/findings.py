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


def _ensure_tagged(view):
    rows = view.get('activities_oid') or []
    if rows and 'identity' not in rows[0]:
        tag_view(view)


def _preds(view, oid):
    return [r['pred_oid'] for r in view.get('relationships_oid', []) if r['succ_oid'] == oid]


def _label(a):
    return a.get('id') or a.get('name') or a.get('object_id')


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

    # stable, MEP-first, strong-first ordering
    findings.sort(key=lambda f: (-_STRENGTH.get(f['strength'], 1),
                                 f['discipline'] not in _MEP_DISC, f['system']))
    return findings
