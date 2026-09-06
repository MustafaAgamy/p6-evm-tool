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
# A signature word must NAME a type, not describe construction in general. Words
# claimed by more than this share of the KB ('fire', 'water', 'testing', 'handover',
# 'core', 'structural') are dropped outright — without the cut, a schedule scores on
# vocabulary every project shares and the longest wordlist wins, not the right type.
_SIG_DF_MAX_FRAC = 0.12
_SIG_DF_MIN_KEEP = 2

# How the two signals are blended, and where the evidence saturates. Calibrated
# against the resolver validation battery (tests/test_kb_resolve_validation.py) —
# 28 schedules across the whole project range, not tuned to any one of them.
_W_VOCAB = 0.75
_W_SYSTEMS = 0.25
_SYS_SATURATION = 3.0

# Confidence thresholds. Both score terms are bounded, so the blended score lives in
# [0, 1] and these are honest bands rather than arbitrary cut-offs.
_CONF_HIGH = 0.30
_CONF_MED = 0.15
_MARGIN_CLEAR = 0.15    # …and it must beat the runner-up by this much to be 'high'
_MARGIN_AMBIG = 0.05    # below this the two types are effectively tied


def _stem(w):
    """Minimal, deterministic singular/plural folding so the KB's wording and the
    planner's wording meet: 'Escalator Installation' must match an archetype that
    says 'escalators', 'Retail Unit' must match 'units'. No stemming library, no
    language model — just the plural rules, applied identically to both sides."""
    if len(w) > 4:
        if w.endswith('ies'):
            return w[:-3] + 'y'
        if w.endswith(('ses', 'xes', 'zes', 'ches', 'shes')):
            return w[:-2]
        if w.endswith('s') and not w.endswith(('ss', 'us', 'is')):
            return w[:-1]
    return w


def _system_vocabulary(patterns):
    """Words that name a SYSTEM (from the System Patterns' own names and aliases) —
    'sprinkler', 'chiller', 'escalator', 'busbar'. These are excluded from archetype
    signature vocabulary on purpose: systems are already scored by the system term,
    and a word every building's MEP shares cannot tell one project type from another.
    Keeps the two signals independent instead of double-counting the same evidence."""
    out = set()
    for pat in (patterns or {}).values():
        blob = ' '.join([pat.get('name', ''), pat.get('system', '')] + list(pat.get('aliases', []))).lower()
        out |= {_stem(w) for w in _SIG_RX.findall(blob)}
    return out


def _archetype_signatures(archetypes, patterns=None):
    """Distinctive vocabulary per archetype — the type words that identify a project
    even when it has almost no MEP (asphalt/pavement→roads, pier/viaduct→bridge,
    apron/runway→airside, tenant/shopfront→mall). Drawn from the archetype name +
    applicability + civil_interfaces + commissioning_focus, IDF-weighted, with the
    shared construction vocabulary cut out (see _SIG_DF_MAX_FRAC).

    Returns (tokens per archetype, idf per token, vector norm per archetype). The
    norm is what stops a verbosely-written archetype out-scoring a precise one.
    """
    sysvocab = _system_vocabulary(patterns)
    raw = {}
    df = Counter()
    for aid, arc in archetypes.items():
        blob = ' '.join([arc.get('name', ''), arc.get('applicability', '')]
                        + arc.get('civil_interfaces', []) + arc.get('commissioning_focus', [])).lower()
        t = {_stem(w) for w in _SIG_RX.findall(blob) if w not in _SIG_STOP}
        t -= sysvocab
        raw[aid] = t
        for w in t:
            df[w] += 1

    n = max(len(archetypes), 1)
    cap = max(_SIG_DF_MIN_KEEP, int(n * _SIG_DF_MAX_FRAC))
    idf = {w: math.log((n + 1) / (c + 1)) for w, c in df.items() if c <= cap}
    toks = {aid: {w for w in t if w in idf} for aid, t in raw.items()}
    norms = {aid: math.sqrt(sum(idf[w] ** 2 for w in t)) for aid, t in toks.items()}
    return toks, idf, norms


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
    sig_toks, sig_idf, sig_norm = _archetype_signatures(archetypes, patterns)
    sched_tokens = {_stem(w) for w in _SIG_RX.findall(_schedule_text(view))}
    sched_sig = {w: sig_idf[w] for w in sched_tokens if w in sig_idf}
    sched_sig_norm = math.sqrt(sum(v ** 2 for v in sched_sig.values()))

    def _strength(s):
        return math.log(1 + present.get(s, 0))   # how MUCH of the system is present

    def _system_fit(prim, sec):
        """How much distinctive system evidence the archetype's focus systems have in
        this schedule, saturated into [0, 1). Deliberately NOT a cosine: a schedule
        where only two systems were detected would otherwise hand a near-perfect score
        to whichever archetype happens to list just those two (an airport terminal
        showing only steel + HVAC scored as a jetty). Absolute evidence, capped."""
        ev = (sum(weight.get(s, 0.6) * _strength(s) for s in (prim & confident))
              + 0.25 * sum(weight.get(s, 0.6) * _strength(s) for s in (sec & confident)))
        return ev / (ev + _SYS_SATURATION)

    def _vocab_fit(aid):
        """Same cosine over distinctive TYPE vocabulary — what identifies civil-led,
        low-MEP projects (roads, bridges, airside) that carry almost no systems."""
        if not sig_norm.get(aid) or not sched_sig_norm:
            return 0.0, set()
        hits = sig_toks.get(aid, set()) & sched_tokens
        if not hits:
            return 0.0, hits
        dot = sum(sig_idf[w] ** 2 for w in hits)
        # Corroboration: one incidental word is not an identification. A single rare
        # token ('connection' in a chiller schedule) could otherwise carry a whole
        # archetype on the strength of a small vocabulary; two or more agreeing terms
        # are evidence. Damping, not a hard gate — a lone strong term still counts.
        corroboration = len(hits) / (len(hits) + 1.0)
        return corroboration * dot / (sig_norm[aid] * sched_sig_norm), hits

    # Both terms are bounded in [0, 1], so the blend is bounded and the confidence
    # thresholds below mean something. Vocabulary carries most of the weight: system
    # detection says WHAT is in the project (many types share the same systems), the
    # distinctive vocabulary says WHICH TYPE it is — a kiln, a bogie drop and a
    # baggage carousel each name their project, a chilled-water pump does not.
    ranked = []
    for aid, arc in archetypes.items():
        prim = set(arc.get('primary_systems', []))
        sec = set(arc.get('secondary_systems', []))
        sysfit = _system_fit(prim, sec)
        vocfit, hits = _vocab_fit(aid)
        ranked.append({'arc': arc, 'score': _W_SYSTEMS * sysfit + _W_VOCAB * vocfit, 'prim': prim,
                       'sec': sec, 'system_fit': sysfit, 'vocabulary_fit': vocfit,
                       'terms': sorted(hits, key=lambda w: -sig_idf.get(w, 0))[:8]})
    ranked.sort(key=lambda r: -r['score'])
    best = ranked[0] if ranked else None
    if not best or best['score'] <= 0:
        return None

    # An archetype that only just beats the runner-up is a guess, not an answer —
    # say so rather than presenting a coin-flip as a confident classification.
    runner = ranked[1]['score'] if len(ranked) > 1 else 0.0
    margin = (best['score'] - runner) / best['score'] if best['score'] else 0.0
    if best['score'] >= _CONF_HIGH and margin >= _MARGIN_CLEAR:
        confidence = 'high'
    elif best['score'] >= _CONF_MED and margin >= _MARGIN_AMBIG:
        confidence = 'medium'
    else:
        confidence = 'low'

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
        'confidence': confidence,
        'match_score': round(best['score'], 3),
        'match_basis': {'system_fit': round(best['system_fit'], 3),
                        'vocabulary_fit': round(best['vocabulary_fit'], 3),
                        'margin': round(margin, 3)},
        'signature_terms': best['terms'],       # the type words that identified it
        'alternatives': [{'archetype': r['arc'].get('archetype'),
                          'archetype_name': r['arc'].get('name'),
                          'match_score': round(r['score'], 3)}
                         for r in ranked[1:3] if r['score'] > 0],
        'ambiguous': margin < _MARGIN_AMBIG,
        'primary_systems': arc.get('primary_systems', []),
        'commissioning_focus': arc.get('commissioning_focus', []),
        'present_systems': sorted(present_set, key=lambda s: -present[s]),
        'relevant_patterns': rel_info,
        'expected_but_absent': absent,
        'civil_interfaces': arc.get('civil_interfaces', []),
    }
