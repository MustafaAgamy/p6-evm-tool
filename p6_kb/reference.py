"""Reference assembly for the UI — turn the System-Pattern knowledge base into
browsable, display-ready shapes.

Three views sit on top of :mod:`p6_kb.patterns` and :mod:`p6_kb.semantic`:

* :func:`knowledge_index` — the whole KB grouped by discipline, plus the
  archetype list and headline counts, for a "browse the knowledge" screen;
* :func:`pattern_detail` — one system pattern normalized for a detail panel
  (sequence, evidence-graded relationships, resolved interfaces, work
  components, testing/commissioning, provenance);
* :func:`activity_knowledge` — join a schedule activity to its concept via
  :func:`p6_kb.semantic.map_activity` and attach the matching pattern detail.

Plus the small, ordered :data:`STATUS_VOCAB` the UI legend renders, and two
tidy-up helpers (:func:`evidence_grade`, :func:`discipline_label`). Deterministic
and stdlib-only.
"""
import re

from . import semantic
from .patterns import load_archetypes, load_system_patterns

# ── status vocabulary (ordered; drives the UI legend) ───────────────────────
STATUS_VOCAB = [
    {'key': 'knowledge_available', 'label': 'Knowledge available',
     'desc': 'Relevant, evidence-graded knowledge exists for this concept.'},
    {'key': 'potentially_relevant', 'label': 'Potentially relevant',
     'desc': 'Partial or lower-confidence match — read with care.'},
    {'key': 'insufficient_evidence', 'label': 'Insufficient evidence',
     'desc': 'Concept known, but the knowledge is too thin to rely on.'},
    {'key': 'not_assessed', 'label': 'Not assessed',
     'desc': 'No confident match. NOT a statement that the schedule is correct.'},
    {'key': 'planner_review', 'label': 'Planner review required',
     'desc': 'Context-dependent — only the planner can decide if it applies.'},
]

_SUMMARY_LIMIT = 160

# short human labels for the tagger's discipline codes
_DISCIPLINE_LABELS = {
    'MECH': 'Mechanical', 'ELEC': 'Electrical', 'ELV': 'Extra-Low Voltage',
    'PIPING': 'Piping', 'INSTR': 'Instrumentation', 'PLUMB': 'Plumbing',
    'FIRE': 'Fire Protection', 'PROCESS': 'Process', 'UTIL': 'Utilities',
    'STRUCT': 'Structural', 'CIVIL': 'Civil', 'FINISHES': 'Finishes',
    'MECHANICAL_PIPING': 'Mechanical Piping', 'UNKNOWN': 'Unclassified',
}


def evidence_grade(strength):
    """Grade a relationship/interface ``strength`` for display."""
    s = (strength or '').strip().lower()
    if s == 'strong':
        return {'key': 'strong', 'label': 'Strong evidence'}
    if s == 'moderate':
        return {'key': 'moderate', 'label': 'Moderate'}
    return {'key': 'emerging', 'label': 'Emerging'}


def _titlecase(text):
    out = []
    for word in text.split():
        if word.isupper() and len(word) <= 3:
            out.append(word)               # keep short acronyms (MEP, HV)
        else:
            out.append(word.capitalize())
    return ' '.join(out)


def discipline_label(code):
    """Tidy a raw discipline code/label into a short human label. Known tagger
    codes map directly; long parenthetical/slashed labels are trimmed to their
    leading segment. Deterministic."""
    if not code:
        return 'Unclassified'
    raw = str(code).strip()
    known = _DISCIPLINE_LABELS.get(raw.upper())
    if known:
        return known
    head = re.split(r'[/(&,]', raw)[0]      # segment before /, (, &, ,
    head = head.replace('_', ' ').strip()
    if not head:
        head = raw
    return _titlecase(head)


def _summary(text, limit=_SUMMARY_LIMIT):
    t = ' '.join(str(text or '').split())
    if len(t) <= limit:
        return t
    return t[:limit].rstrip() + '…'    # ellipsis


def knowledge_index(patterns=None, archetypes=None):
    """The whole KB as a discipline-grouped index plus archetypes and counts."""
    if patterns is None:
        patterns = load_system_patterns()
    if archetypes is None:
        archetypes = load_archetypes()

    by_discipline = {}
    total_relationships = 0
    for sysid, pat in sorted(patterns.items()):
        disc = pat.get('discipline') or 'UNKNOWN'
        relationships = pat.get('typical_relationships') or []
        total_relationships += len(relationships)
        by_discipline.setdefault(disc, []).append({
            'system': sysid,
            'name': pat.get('name') or sysid,
            'discipline': disc,
            'stage_count': len(pat.get('sequence') or []),
            'relationship_count': len(relationships),
            'interface_count': len(pat.get('interfaces') or []),
            'aliases': list(pat.get('aliases') or []),
            'summary': _summary(pat.get('evidence')),
        })

    disciplines = [
        {'discipline': disc,
         'label': discipline_label(disc),
         'systems': sorted(by_discipline[disc], key=lambda e: e['name'])}
        for disc in sorted(by_discipline)
    ]

    archetype_list = [
        {'archetype': a.get('archetype'),
         'name': a.get('name'),
         'category': a.get('category'),
         'primary_systems': list(a.get('primary_systems') or []),
         'secondary_systems': list(a.get('secondary_systems') or [])}
        for a in sorted(archetypes.values(),
                        key=lambda a: (a.get('name') or a.get('archetype') or ''))
    ]

    return {
        'disciplines': disciplines,
        'archetypes': archetype_list,
        'counts': {
            'disciplines': len(disciplines),
            'systems': len(patterns),
            'relationships': total_relationships,
            'archetypes': len(archetypes),
        },
    }


def pattern_detail(system_id, patterns=None):
    """One system pattern normalized for display, or ``None`` for an unknown id."""
    if patterns is None:
        patterns = load_system_patterns()
    pat = patterns.get(system_id)
    if not pat:
        return None

    disc = pat.get('discipline') or 'UNKNOWN'

    sequence = [
        {'stage': s.get('stage'),
         'activities': list(s.get('activities') or []),
         'note': s.get('note') or ''}
        for s in (pat.get('sequence') or [])
    ]
    relationships = [
        {'before': r.get('before'),
         'after': r.get('after'),
         'reason': r.get('reason'),
         'strength': r.get('strength'),
         'strength_grade': evidence_grade(r.get('strength')),
         'rel': r.get('rel') or ''}
        for r in (pat.get('typical_relationships') or [])
    ]
    interfaces = [
        {'with': i.get('with'),
         'with_name': (patterns.get(i.get('with')) or {}).get('name') or i.get('with'),
         'requirement': i.get('requirement'),
         'type': i.get('type'),
         'phase': i.get('phase'),
         'strength': i.get('strength'),
         'strength_grade': evidence_grade(i.get('strength'))}
        for i in (pat.get('interfaces') or [])
    ]
    work_components = [
        {'wp': w.get('wp'),
         'discipline': w.get('discipline'),
         'interface': bool(w.get('interface')),
         'note': w.get('note') or ''}
        for w in (pat.get('work_packages') or [])
    ]

    status = pat.get('status') or ''
    if status == 'curated':
        provenance_label = 'Curated reference'
    elif status:
        provenance_label = status.title()
    else:
        provenance_label = 'Reference'

    return {
        'system': pat.get('system'),
        'name': pat.get('name') or system_id,
        'discipline': disc,
        'discipline_label': discipline_label(disc),
        'aliases': list(pat.get('aliases') or []),
        'zones': list(pat.get('zones') or []),
        'sequence': sequence,
        'relationships': relationships,
        'interfaces': interfaces,
        'work_components': work_components,
        'testing_requirements': list(pat.get('testing_requirements') or []),
        'commissioning_dependencies': list(pat.get('commissioning_dependencies') or []),
        'typical_exceptions': list(pat.get('typical_exceptions') or []),
        'evidence': pat.get('evidence') or '',
        'provenance': {'source': pat.get('source') or '', 'status': status,
                       'label': provenance_label},
        'status': 'knowledge_available',
    }


def activity_knowledge(activity, patterns=None):
    """Join a schedule activity to its concept and the matching pattern detail.

    Returns ``{'match': <map_activity result>, 'status': <STATUS_VOCAB key>,
    'knowledge': <pattern_detail|None>}``. A confident concept whose pattern is
    too thin (no sequence *and* fewer than 2 relationships) is downgraded to
    ``insufficient_evidence`` — knowing the concept is not the same as having
    enough curated knowledge to rely on.
    """
    if patterns is None:
        patterns = load_system_patterns()

    match = semantic.map_activity(activity, patterns)
    status = semantic.status_for(match['confidence'])
    knowledge = None

    concept = match.get('concept')
    if concept:
        knowledge = pattern_detail(concept, patterns)
        if knowledge is not None:
            thin = (not knowledge['sequence']) and len(knowledge['relationships']) < 2
            if thin:
                status = 'insufficient_evidence'

    return {'match': match, 'status': status, 'knowledge': knowledge}
