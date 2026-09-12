"""Semantic Mapping Layer — map one messy schedule activity to a normalized
construction-knowledge *concept* (a ``system_pattern`` id).

Edition 1 is deterministic and fully offline: it resolves the concept through an
ordered list of *stage* callables and takes the first stage that returns a match.
The stages are the pluggable seam of this layer — a future offline-embedding or
cloud-LLM matcher is added simply by writing another ``(activity, patterns) ->
dict|None`` callable and inserting it into ``_STAGES`` (callers of
``map_activity`` never change). Order matters: cheap/high-precision stages come
first, expensive/low-precision ones last, so today's list is::

    _STAGES = [_stage_tagger, _stage_alias, _stage_fuzzy]

To add, say, an embedding stage you would write ``_stage_embed(activity,
patterns)`` returning the same normalized dict (``concept``/``discipline``/
``confidence``/``method``/``ambiguous``/``signals``/``alternatives``) and place
it *after* the deterministic tagger but before ``_stage_fuzzy``::

    _STAGES = [_stage_tagger, _stage_alias, _stage_embed, _stage_fuzzy]

No stage may mutate ``activity`` or ``patterns``. Stdlib only (``re``,
``difflib``); no randomness — the same activity always maps the same way.
"""
import difflib
import re

from .patterns import load_system_patterns
from .tagging import tag_activity

# ── confidence → coarse UI status ───────────────────────────────────────────
_STATUS_BY_CONFIDENCE = {
    'high': 'knowledge_available',
    'medium': 'knowledge_available',
    'low': 'potentially_relevant',
}

_FUZZY_THRESHOLD = 0.55


def status_for(confidence):
    """'high'/'medium' -> knowledge_available; 'low' -> potentially_relevant;
    'none' or anything unrecognised -> not_assessed."""
    return _STATUS_BY_CONFIDENCE.get(confidence, 'not_assessed')


# ── text helpers ────────────────────────────────────────────────────────────
def _clean(text):
    return re.sub(r'\s+', ' ', (text or '').strip().lower())


def _phrase_hit(phrase, haystack):
    """True when ``phrase`` appears in ``haystack`` on token boundaries."""
    phrase = _clean(phrase)
    if len(phrase) < 3:
        return False
    pattern = r'(?<![a-z0-9])' + re.escape(phrase) + r'(?![a-z0-9])'
    return re.search(pattern, haystack) is not None


def _candidate_phrases(pattern):
    """Phrases that name a pattern: its aliases, its display name, and its
    system id spelled out (``process_piping`` -> ``process piping``)."""
    phrases = [str(a) for a in (pattern.get('aliases') or []) if a]
    if pattern.get('name'):
        phrases.append(str(pattern['name']))
    phrases.append(str(pattern.get('system', '')).replace('_', ' '))
    return phrases


# ── stages: each is (activity, patterns) -> normalized dict | None ──────────
def _stage_tagger(activity, patterns):
    """Multi-signal identity tagger (code values + name + WBS). Wins whenever it
    resolves a system that the knowledge base actually curates."""
    tag = tag_activity(activity)
    sysid = tag.get('system')
    if not sysid or sysid not in patterns:
        return None
    source = tag.get('source') or ''
    method = 'code' if 'code' in source else 'name'
    signals = list(tag.get('signals') or [])
    signals.append('tagger:' + (source or 'name'))
    return {
        'concept': sysid,
        'discipline': tag.get('discipline'),
        'confidence': tag.get('confidence') or 'medium',
        'method': method,
        'ambiguous': bool(tag.get('ambiguous')),
        'signals': signals,
        'alternatives': [],
    }


def _stage_alias(activity, patterns):
    """Whole-word alias / name / system-id hits in the activity name. The pattern
    with the most and longest hits wins; up to 3 runners-up are kept."""
    name = _clean(activity.get('name'))
    if not name:
        return None
    scored = []
    for sysid, pat in patterns.items():
        hits = [c for c in _candidate_phrases(pat) if _phrase_hit(c, name)]
        if hits:
            scored.append({
                'sysid': sysid,
                'chars': sum(len(_clean(h)) for h in hits),
                'count': len(hits),
                'hits': hits,
            })
    if not scored:
        return None
    # deterministic: longest total match, then most hits, then id (alphabetical)
    scored.sort(key=lambda s: (s['chars'], s['count'], _rev(s['sysid'])), reverse=True)
    best = scored[0]
    alts = [
        {'concept': s['sysid'],
         'concept_name': patterns[s['sysid']].get('name'),
         'confidence': 'low'}
        for s in scored[1:4]
    ]
    return {
        'concept': best['sysid'],
        'discipline': patterns[best['sysid']].get('discipline'),
        'confidence': 'low',
        'method': 'alias',
        'ambiguous': True,
        'signals': ['alias:' + _clean(h) for h in best['hits'][:3]],
        'alternatives': alts,
    }


def _stage_fuzzy(activity, patterns):
    """Last resort: difflib similarity between the activity name and each
    pattern's name+aliases. Only fires above ``_FUZZY_THRESHOLD``."""
    name = _clean(activity.get('name'))
    if not name:
        return None
    ranked = []
    for sysid, pat in patterns.items():
        texts = [_clean(pat.get('name'))]
        texts += [_clean(a) for a in (pat.get('aliases') or [])]
        ratio = max((difflib.SequenceMatcher(None, name, t).ratio()
                     for t in texts if t), default=0.0)
        ranked.append((ratio, sysid))
    if not ranked:
        return None
    ranked.sort(key=lambda r: (r[0], _rev(r[1])), reverse=True)
    best_ratio, best_id = ranked[0]
    if best_ratio < _FUZZY_THRESHOLD:
        return None
    alts = [
        {'concept': sid, 'concept_name': patterns[sid].get('name'), 'confidence': 'low'}
        for ratio, sid in ranked[1:4] if ratio >= _FUZZY_THRESHOLD
    ]
    return {
        'concept': best_id,
        'discipline': patterns[best_id].get('discipline'),
        'confidence': 'low',
        'method': 'fuzzy',
        'ambiguous': True,
        'signals': ['fuzzy:%.2f' % best_ratio],
        'alternatives': alts,
    }


def _rev(text):
    """Reverse-alphabetical helper so ``sort(reverse=True)`` keeps ids ascending
    as a deterministic tiebreak."""
    return tuple(-ord(c) for c in str(text))


# stages run in order; the first to return a non-None result wins. Add a future
# embedding/LLM matcher by inserting another callable here (see module docstring).
_STAGES = [_stage_tagger, _stage_alias, _stage_fuzzy]


def map_activity(activity, patterns=None):
    """Map one activity dict to a normalized construction concept.

    ``activity`` uses the same shape as the tagger: ``.get('name')``,
    ``.get('wbs_path')``, ``.get('activity_codes')`` (dict {dim: value}).
    ``patterns`` defaults to :func:`p6_kb.patterns.load_system_patterns`.

    Returns a dict with keys ``concept`` (system id | None), ``concept_name``
    (str | None), ``discipline`` (str | None), ``phase`` (str | None),
    ``confidence`` ('high'|'medium'|'low'|'none'), ``method``
    ('code'|'name'|'alias'|'fuzzy'|'none'), ``ambiguous`` (bool), ``signals``
    (list[str]) and ``alternatives`` (list of up to 3 {concept, concept_name,
    confidence}).
    """
    if patterns is None:
        patterns = load_system_patterns()

    base = tag_activity(activity)          # phase + baseline discipline/signals
    phase = base.get('phase')

    match = None
    for stage in _STAGES:
        match = stage(activity, patterns)
        if match:
            break

    if not match:
        return {
            'concept': None,
            'concept_name': None,
            'discipline': None,
            'phase': phase,
            'confidence': 'none',
            'method': 'none',
            'ambiguous': True,
            'signals': list(base.get('signals') or []),
            'alternatives': [],
        }

    concept = match['concept']
    discipline = match.get('discipline') or base.get('discipline')
    if discipline == 'UNKNOWN':
        discipline = None
    return {
        'concept': concept,
        'concept_name': patterns[concept].get('name'),
        'discipline': discipline,
        'phase': phase,
        'confidence': match['confidence'],
        'method': match['method'],
        'ambiguous': bool(match.get('ambiguous', match['confidence'] in ('low', 'none'))),
        'signals': list(match.get('signals') or base.get('signals') or []),
        'alternatives': match.get('alternatives') or [],
    }
