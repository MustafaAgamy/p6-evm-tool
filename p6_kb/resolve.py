"""Archetype resolver — the Phase 2 bridge from a real schedule to the relevant
System Patterns, MEP-first and project-agnostic.

Given a parsed schedule view, it: (1) detects which System Patterns are PRESENT by
matching each pattern's own generalized aliases against the activity names (so it
never depends on clean discipline codes OR on the tagger's system vocabulary);
(2) resolves the best-fitting project archetype by how well its focus systems
overlap what's present; (3) returns the relevant patterns (present + expected) and
the expected-but-absent systems — candidate constructability signals for the
Phase 3 rule engine. Read-only: it computes nothing that changes the v1 score.

If nothing resolves confidently it returns None, and the v1 review is unaffected.
"""
import math
from collections import Counter

from p6_kb.patterns import load_archetypes, load_system_patterns
from p6_kb.tagging import detect_systems

_MEP_DISC = {'MECH', 'ELEC', 'ELV', 'PIPING', 'INSTR', 'PLUMB', 'FIRE', 'PROCESS', 'UTIL'}
_MIN_HITS = 2   # a system counts as confidently present once ≥2 of its aliases appear

# the tagger's system ids mostly equal the pattern ids; a few fan out
_TAGGER_TO_PATTERN = {'piping': ('process_piping', 'utility_piping')}


def _tagger_present(view, patterns):
    """Systems the multi-signal tagger found — its simple keywords catch common
    activity names the verbose pattern aliases miss (e.g. 'Chiller Installation')."""
    out = {}
    try:
        det = detect_systems(view)
    except Exception:
        return out
    for s in det.get('systems_present', []):
        for tid in _TAGGER_TO_PATTERN.get(s['system'], (s['system'],)):
            if tid in patterns:
                # carry the ACTIVITY COUNT as presence strength (a silo has hundreds
                # of conveying activities; a control building a handful of plumbing)
                out[tid] = max(out.get(tid, 0), s.get('count', 2))
    return out


def _distinctiveness(archetypes):
    """IDF-style weight per system: a system that is a primary focus of FEW
    archetypes discriminates strongly (conveying, spool fab); one present in many
    (plumbing, BMS, finishing) barely tells us the project type."""
    df = Counter()
    n = 0
    for arc in archetypes.values():
        n += 1
        for s in set(arc.get('primary_systems', [])):
            df[s] += 1
    return {s: math.log((n + 1) / (c + 1)) + 0.1 for s, c in df.items()}, n


_SIG_STOP = {'works', 'work', 'system', 'systems', 'foundation', 'foundations', 'installation',
             'structure', 'structures', 'construction', 'building', 'buildings', 'general',
             'interface', 'interfaces', 'network', 'services', 'concrete', 'slab', 'slabs',
             'drainage', 'preparation', 'layers', 'layer', 'yard', 'pits', 'pit', 'ducts',
             'duct', 'bank', 'banks', 'and', 'the', 'for', 'with', 'area', 'areas', 'civil'}
_SIG_RX = __import__('re').compile(r'[a-z]{4,}')


def _archetype_signatures(archetypes):
    """Distinctive vocabulary per archetype — the civil/type words that identify a
    project even when it has almost no MEP (asphalt/pavement→roads, pier/viaduct→
    bridge, apron/runway→airside, mall/retail→mall). Drawn from the archetype name +
    civil_interfaces + commissioning_focus, IDF-weighted so generic words don't sway."""
    toks = {}
    df = Counter()
    for aid, arc in archetypes.items():
        blob = ' '.join([arc.get('name', ''), arc.get('applicability', '')]
                        + arc.get('civil_interfaces', []) + arc.get('commissioning_focus', [])).lower()
        t = {w for w in _SIG_RX.findall(blob) if w not in _SIG_STOP}
        toks[aid] = t
        for w in t:
            df[w] += 1
    n = max(len(archetypes), 1)
    idf = {w: math.log((n + 1) / (c + 1)) for w, c in df.items()}
    return toks, idf


def _schedule_text(view):
    rows = view.get('activities_oid') or view.get('activities') or []
    return '\n'.join((a.get('name') or '').lower() for a in rows)


def present_systems(view, patterns):
    """{system_id: alias-hit-count} for every pattern whose aliases appear."""
    text = _schedule_text(view)
    out = {}
    for sysid, pat in patterns.items():
        hits = 0
        for al in pat.get('aliases', []):
            a = (al or '').lower().strip()
            if len(a) >= 3 and a in text:
                hits += 1
        if hits:
            out[sysid] = hits
    return out


def _pattern_info(sysid, patterns, present):
    p = patterns.get(sysid, {})
    return {
        'system': sysid, 'name': p.get('name', sysid), 'discipline': p.get('discipline', ''),
        'present': sysid in present, 'alias_hits': present.get(sysid, 0),
        'stages': len(p.get('sequence', [])),
        'relationships': len(p.get('typical_relationships', [])),
        'interfaces': len(p.get('interfaces', [])),
        'is_mep': p.get('discipline', '').upper() in _MEP_DISC,
    }


def resolve(view, patterns=None, archetypes=None):
    """Return the resolved archetype + relevant patterns, or None (v1 fallback)."""
    patterns = patterns if patterns is not None else load_system_patterns()
    archetypes = archetypes if archetypes is not None else load_archetypes()
    if not patterns or not archetypes:
        return None

    present = present_systems(view, patterns)
    for sid, h in _tagger_present(view, patterns).items():   # union the tagger's simpler keywords
        present[sid] = max(present.get(sid, 0), h)
    present_set = set(present)
    # NOTE: no early return on an empty system set — civil-led types (roads, bridges)
    # carry almost no MEP and are identified purely by their signature vocabulary below.
    confident = {s for s, h in present.items() if h >= _MIN_HITS} or present_set

    weight, _n = _distinctiveness(archetypes)
    sig_toks, sig_idf = _archetype_signatures(archetypes)
    sched_tokens = set(_SIG_RX.findall(_schedule_text(view)))
    _SIG_WEIGHT = 1.5   # lets distinctive civil/type vocabulary identify low-MEP types

    def _strength(s):
        return math.log(1 + present.get(s, 0))   # how MUCH of the system is present

    best = None
    for aid, arc in archetypes.items():
        prim = set(arc.get('primary_systems', []))
        sec = set(arc.get('secondary_systems', []))
        # distinctiveness × presence-strength of the archetype's focus systems present…
        score = sum(weight.get(s, 0.6) * _strength(s) for s in (prim & confident)) \
            + 0.25 * sum(weight.get(s, 0.6) * _strength(s) for s in (sec & confident))
        # …plus distinctive type/civil vocabulary (identifies roads/bridges/malls etc.)
        score += _SIG_WEIGHT * sum(sig_idf.get(w, 0) for w in (sig_toks.get(aid, set()) & sched_tokens))
        if best is None or score > best['score']:
            best = {'arc': arc, 'score': round(score, 2), 'prim': prim, 'sec': sec}
    if not best or best['score'] == 0:
        return None

    arc, prim, sec = best['arc'], best['prim'], best['sec']
    relevant = prim | sec
    absent = [s for s in arc.get('primary_systems', []) if s not in present_set]
    # focus the MEP/commissioning story: relevant patterns that are present, MEP first
    rel_info = [_pattern_info(s, patterns, present) for s in relevant]
    rel_info.sort(key=lambda x: (not x['present'], not x['is_mep'], x['system']))

    return {
        'archetype': arc.get('archetype'),
        'archetype_name': arc.get('name'),
        'category': arc.get('category'),
        'confidence': 'high' if best['score'] >= 4 else ('medium' if best['score'] >= 2 else 'low'),
        'match_score': best['score'],
        'primary_systems': arc.get('primary_systems', []),
        'commissioning_focus': arc.get('commissioning_focus', []),
        'present_systems': sorted(present_set, key=lambda s: -present[s]),
        'relevant_patterns': rel_info,
        'expected_but_absent': absent,
        'civil_interfaces': arc.get('civil_interfaces', []),
    }
