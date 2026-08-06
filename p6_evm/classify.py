"""Construction-knowledge classification, shared by the schedule (WBS) and the E1 Log.

One meaning-based matcher used everywhere so a project's own vocabulary doesn't matter:
  * classify_wbs_name / auto_categories  — tag WBS branches as Construction / Engineering
    / Design / Procurement and build the default-weighted category set for any project.
  * is_design_drawing                    — a drawing type is Design (Concept/Schematic/
    Detailed/IFC/…); everything else (Shop, as-built, coordination, unknown) is Engineering.
  * match_e1_field                       — map an E1 Log column heading to a known field by
    meaning, so any format reads (Discipline == Descipline == Trade == Division == …).

Matching is case/space/punctuation-insensitive and matches when the text CONTAINS an
accepted phrase. See vault: 01 Scope — Auto Project Setup, 07 Calculation Rules.
"""

# ── Categories (priority order — first match wins; Construction is the fallback) ──
CATEGORY_RULES = [
    ('Procurement', ['procure', 'supply', 'purchase', 'vendor', 'supplier']),
    ('Design',      ['design', 'ifc', 'ifa', 'schematic', 'concept',
                     'preliminary', 'issued for construction', 'issued for approval']),
    ('Engineering', ['engineer', 'shop drawing', 'shop', 'submittal', 'approval',
                     'technical', 'detailing', 'coordination', 'fabricat']),
    ('Construction', ['construct', 'civil', 'structural', 'structure', 'works',
                      'erection', 'installation', 'concrete', 'mep', 'execution', 'site work']),
]
DEFAULT_CATEGORY = 'Construction'
CATEGORY_ORDER = ['Construction', 'Engineering', 'Design', 'Procurement']

DESIGN_DRAWING_KW = ['design', 'ifc', 'ifa', 'schematic', 'detailed', 'concept',
                     'preliminary', 'basic', 'issued for']

E1_FIELD_SYNONYMS = {
    'trade':          ['descipline', 'discipline', 'trade', 'division', 'system', 'speciality', 'specialty'],
    'submittal_type': ['type of submittal', 'submittal type', 'drawing type', 'document type', 'deliverable', 'type'],
    'building':       ['building', 'area', 'zone', 'location', 'block'],
    'description':    ['description', 'drawing title', 'document title', 'drawing name', 'title', 'subject'],
    'submitted':      ['date submitted', 'submitted', 'submission', 'sent date', 'sent', 'transmittal date'],
    'planned':        ['planned submission', 'planned', 'target', 'baseline', 'forecast'],
    'action_code':    ['action code', 'action', 'review code', 'disposition', 'status', 'code', 'response'],
}


def _norm(s):
    return ' '.join(str(s or '').lower().replace('_', ' ').replace('-', ' ').replace('.', ' ').split())


def classify_wbs_name(name):
    """Category for a single WBS/branch name, or None if nothing matches."""
    n = _norm(name)
    if not n:
        return None
    for cat, kws in CATEGORY_RULES:
        if any(k in n for k in kws):
            return cat
    return None


def classify_branch_names(names):
    """Category for an activity given its WBS ancestor names (leaf → root order).
    Decided by the TOP-MOST branch that carries a meaning (the phase), so a leaf word
    like 'Approval' under a Construction phase doesn't steal it into Engineering.
    Falls back to Construction so every activity lands somewhere."""
    for name in reversed(names):   # root/phase first
        cat = classify_wbs_name(name)
        if cat:
            return cat
    return DEFAULT_CATEGORY


def default_weights(present):
    """Construction 95%, the rest share 5% (all editable later). `present` is the set
    of category names that actually occur in the schedule."""
    cats = [c for c in CATEGORY_ORDER if c in present]
    if not cats:
        return {}
    if 'Construction' in cats and len(cats) > 1:
        others = [c for c in cats if c != 'Construction']
        share = 0.05 / len(others)
        w = {'Construction': 0.95}
        for c in others:
            w[c] = share
        return w
    # no Construction, or Construction only → split evenly
    share = 1.0 / len(cats)
    return {c: share for c in cats}


def build_wbs_classifier(data):
    """Return a classifier(names)->category that puts each activity under its top-level WBS
    PHASE (Construction, Mobilization, Engineering, Procurement, …) — so each cost-loaded WBS
    is its own category (Ibrahim's rule). The phase is the root-most named WBS branch, unless
    every activity shares one project-root node, in which case it is one level below it."""
    from p6_evm.metrics import wbs_ancestor_names
    tops = set()
    for a in data.activities.values():
        ch = [n for n in wbs_ancestor_names(a['wbs_id'], data.wbs) if n and n.strip()]
        if ch:
            tops.add(ch[-1])
    single_root = len(tops) == 1     # a shared project-root node sits above the phases

    def classify(names):
        ch = [n for n in (names or []) if n and n.strip()]
        if not ch:
            return DEFAULT_CATEGORY
        if single_root and len(ch) >= 2:
            return ch[-2]
        return ch[-1]
    return classify


def auto_categories(data, saved_weights=None):
    """Category config for compute(): one category per top-level WBS phase, with a default
    weight = its share of the total budget (cost-loaded WBS get weight by their cost; the
    non-cost phases like Engineering/Procurement default to 0 and are weighted by the user).
    Saved user weights override the defaults."""
    from p6_evm.metrics import wbs_ancestor_names
    classify = build_wbs_classifier(data)
    bac = {}
    for a in data.activities.values():
        cat = classify(wbs_ancestor_names(a['wbs_id'], data.wbs))
        bac[cat] = bac.get(cat, 0.0) + (data.bac_by_activity.get(a['object_id'], 0.0) or 0.0)
    total = sum(bac.values())
    cats = []
    for cat, b in bac.items():
        w = (b / total) if total else 0.0
        if saved_weights and cat in saved_weights:
            w = saved_weights[cat]
        cats.append({'name': cat, 'weight': w, 'wbs_match': None})
    cats.sort(key=lambda c: -c['weight'])   # heaviest first
    return cats


def classify_action_code(raw):
    """Read an E1 approval status by MEANING, not one fixed coding scheme — different
    projects use A/B/C/P, or words ('Approved', 'Rejected', 'Under Review'), or 'AAN'
    (approved as noted), 'RNS' (revise & resubmit). Returns
    'approved' | 'not_approved' | 'under_review' | None."""
    c = _norm(raw)
    if not c:
        return None
    # order matters: "not approved" contains "approv"
    if 'not approv' in c or 'reject' in c or 'resubmit' in c or 'revise' in c or c in ('c', 'rns', 'rr'):
        return 'not_approved'
    if 'under' in c or 'review' in c or 'pend' in c or 'progress' in c or c in ('p', 'ur'):
        return 'under_review'
    if 'approv' in c or 'as noted' in c or 'accepted' in c or c in ('a', 'b', 'aan', 'aab'):
        return 'approved'
    # standalone letter-code fallback (A/B = approved, C = not, P = pending) — token-based
    # so "Code A" reads as A, not as a word starting with C
    toks = set(c.split())
    for letter, verdict in (('a', 'approved'), ('b', 'approved'), ('c', 'not_approved'), ('p', 'under_review')):
        if letter in toks:
            return verdict
    return None


def e1_file_bucket(filename):
    """Which engineering bucket a whole log file belongs to, from its file name:
    'engineering' if the name says Shop, 'design' if it says Design, else None
    (a combined log — split it row-by-row by drawing type instead)."""
    n = _norm(filename)
    if 'shop' in n:
        return 'engineering'
    if 'design' in n:
        return 'design'
    return None


def is_design_drawing(submittal_type):
    d = _norm(submittal_type)
    return any(k in d for k in DESIGN_DRAWING_KW)


def match_e1_field(header):
    """Map an E1 column heading to a field name by the LONGEST matching synonym
    (so 'Type of Submittal' beats the generic 'type'). None if nothing matches."""
    h = _norm(header)
    if not h:
        return None
    best_field, best_len = None, 0
    for field, syns in E1_FIELD_SYNONYMS.items():
        for s in syns:
            if s in h and len(s) > best_len:
                best_field, best_len = field, len(s)
    return best_field
