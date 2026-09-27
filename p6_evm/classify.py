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
import re

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


def _default_weights(bac):
    """Default weight per category: cost-loaded phases share 95% by their cost; the non-cost
    discipline phases (Engineering / Procurement / Design) share the remaining 5% equally;
    other structural phases (Milestones, Key Dates, Summary) get 0. Degrades sensibly when
    there are no cost phases (disciplines split 100%) or no disciplines (cost takes 100%).

    A zero-cost phase counts as a discipline by MEANING — via the same classify_wbs_name used
    everywhere — so 'IFC Package' or 'Shop Drawings' is caught, not just phases spelled with
    the exact word 'engineering'/'design'. Only these disciplines feed the overall project %."""
    total_bac = sum(bac.values())
    cost = [c for c in bac if (bac[c] or 0) > 0]
    disc = [c for c in bac if (bac[c] or 0) <= 0
            and classify_wbs_name(c) in ('Engineering', 'Design', 'Procurement')]
    cost_share = 0.95 if (cost and disc) else (1.0 if cost else 0.0)
    disc_share = 0.05 if (cost and disc) else (1.0 if disc else 0.0)
    w = {c: 0.0 for c in bac}
    if cost and total_bac:
        for c in cost:
            w[c] = cost_share * (bac[c] / total_bac)
    if disc:
        each = disc_share / len(disc)
        for c in disc:
            w[c] = each
    return w


def auto_categories(data, saved_weights=None):
    """Category config for compute(): one category per top-level WBS phase, with sensible
    default weights (cost phases share 95% by cost; Engineering/Procurement/Design share 5%).
    Saved user weights override the defaults; every weight is editable."""
    from p6_evm.metrics import wbs_ancestor_names
    classify = build_wbs_classifier(data)
    bac = {}
    for a in data.activities.values():
        cat = classify(wbs_ancestor_names(a['wbs_id'], data.wbs))
        bac[cat] = bac.get(cat, 0.0) + (data.bac_by_activity.get(a['object_id'], 0.0) or 0.0)
    weights = _default_weights(bac)
    cats = []
    for cat in bac:
        w = saved_weights[cat] if (saved_weights and cat in saved_weights) else weights.get(cat, 0.0)
        cats.append({'name': cat, 'weight': w, 'wbs_match': None})
    cats.sort(key=lambda c: -c['weight'])   # heaviest first
    return cats


# ── Review codes (the owner-approved rule, Tool-Wide Enhancement scope §2) ──────────────
# Approved     = A, B, Code 1, Code 2, approved (as noted / with comments), no objection,
#                reviewed – no exceptions (taken)
# Not approved = C, D, Code 3, Code 4, revise and resubmit, rejected, not approved
# Under review = W, P, pending, under review, in review (+ submitted with no reply yet —
#                that part is a row rule, applied in e1_log.summarize_e1)
# A legend printed in the log itself overrides these defaults — see
# classify_action_code_with_legend.
VERDICTS = ('approved', 'not_approved', 'under_review')
_CODE_VERDICT = {
    'a': 'approved', 'b': 'approved', '1': 'approved', '2': 'approved',
    'c': 'not_approved', 'd': 'not_approved', '3': 'not_approved', '4': 'not_approved',
    'p': 'under_review', 'w': 'under_review',
}
_EXACT = {
    'aan': 'approved', 'aab': 'approved', 'noc': 'approved',
    'rns': 'not_approved', 'rr': 'not_approved', 'r&r': 'not_approved',
    'ur': 'under_review', 'ua': 'under_review', 'u/a': 'under_review', 'u/r': 'under_review',
}


def _code_text(raw):
    """Lower-case text with punctuation → spaces (keeps '/' and '&', which carry meaning in
    codes like 'B/C' and 'R&R'). Whole-number floats from Excel read as ints ('1.0' → '1')."""
    if raw is None or isinstance(raw, bool):
        return ''
    if isinstance(raw, (int, float)):
        if raw != raw:                       # NaN
            return ''
        return str(int(raw)) if float(raw).is_integer() else str(raw)
    m = _DEC_ZERO.match(str(raw))
    if m:                                    # '2.0' typed as text reads as the number 2
        return m.group(1).lstrip('0') or '0'
    s = re.sub(r'[^a-z0-9/&]+', ' ', str(raw).lower())
    return ' '.join(s.split())


_DEC_ZERO = re.compile(r'^\s*(\d+)\.0+\s*$')


# Statuses that say the drawing has NOT gone to the consultant yet. They are not review
# codes at all: a drawing "under preparation" is required but neither submitted nor under
# review. (The old bare 'under' / 'progress' / 'pend' matches read them as under review.)
_NOT_SENT = re.compile(
    r'\bprep(?:aration|aring)?\b|\bin progress\b|\bwip\b|\bnot started\b'
    r'|^not yet$|\bnot yet (?:been )?(?:submitted|sent|issued|prepared|started|ready)\b'
    r'|\byet to (?:be )?(?:submit|sent|send|issue|prepare)'
    r'|\bnot (?:been )?(?:submitted|sent|issued)\b'
    r'|\bto be (?:submitted|sent|issued|prepared)\b'
    r'|\b(?:pending|awaiting|awaited|waiting(?: for)?) (?:the )?(?:submission|submittal|to submit|issue|issuance)\b'
    r'|\b(?:pending|awaiting|waiting) (?:from|by|on) (?:the )?(?:contractor|sub ?contractor|supplier|vendor)\b')
# Wording that puts the drawing WITH the reviewer — proof it was sent even when the log
# has no date for it. A bare W / P / 'Pending' is not such proof (it can mean "pending
# submission" too).
_WITH_REVIEWER = re.compile(
    r'\b(?:under|in|for|pending|awaiting|awaited|waiting for) (?:review|approval|comments?)\b'
    r'|\bunder approv|\bawaiting (?:reply|response|consultant)\b|\bwith (?:the )?consultant\b'
    r'|\b(?:re ?)?submitted\b|\bsent (?:to|for)\b|\bissued for (?:review|approval|comments?)\b')
# Still with the reviewer — only explicit wording (a bare 'review' / 'reviewed' says nothing
# about the outcome: "Reviewed & approved" is a finished review).
_UNDER_REVIEW = re.compile(
    r'\b(?:under|in|for|pending|awaiting|awaited) review\b|\breviewing\b'
    r'|\bunder (?:approv|consultant)|\bpend(?:ing)?\b|\bawait|\bwaiting\b'
    r'|\bwith (?:the )?consultant\b|\b(?:re ?)?submitted\b|\bissued for (?:review|approval|comments?)\b')
# Waiting for an approval that has not come yet — read BEFORE the word 'approv' itself.
_PENDING_APPROVAL = re.compile(
    r'\b(?:under|for|pending|awaiting|awaited|waiting for|subject to) approv'
    r'|\bnot yet (?:been )?(?:approv|review|repl|return)')
# A consultant's instruction to resubmit ("to be resubmitted") is a rejection; a log entry
# saying it WAS resubmitted means it is back with the reviewer.
_RESUBMIT_ORDER = re.compile(r'\b(?:to|shall|must|should|will|needs? to) be re ?submitted\b')
_RESUBMITTED = re.compile(r'\bre ?submitted\b')
_FINISHED_OK = re.compile(r'\bapprov|\bas noted\b|\bcorrections? noted\b|\baccepted\b'
                          r'|\breviewed\b.*\bcomments?\b')
_CLAUSE = re.compile(r'[,;:\n]|\s[-\u2013\u2014]+\s|\u2014|\.\s')


def is_not_sent_status(raw):
    """True for a status that says the drawing has not been sent yet ('Under preparation',
    'Pending submission', 'Not yet submitted', 'In progress', 'To be submitted')."""
    c = _code_text(raw)
    return bool(c) and bool(_NOT_SENT.search(c))


def status_says_sent(raw):
    """True when the status wording itself shows the drawing is with the reviewer
    ('Under review', 'In review', 'Under approval', 'U.A', 'Awaiting reply', 'Submitted
    for approval'). A bare code (W / P) or 'Pending' is not enough."""
    c = _code_text(raw)
    if not c or _NOT_SENT.search(c):
        return False
    if c.replace(' ', '') in ('ua', 'u/a', 'ur', 'u/r'):
        return True
    return bool(_WITH_REVIEWER.search(c))


def classify_action_code(raw):
    """Read an engineering-log review status by MEANING, not one fixed coding scheme —
    projects use A/B/C/D/W/P, 1/2/3/4, 'Code 2', words ('Approved as noted', 'Revise and
    resubmit', 'Pending'), or short forms ('AAN', 'RNS', 'U.A'). Returns
    'approved' | 'not_approved' | 'under_review' | None (unknown / blank / ambiguous, or a
    status saying the drawing has not been sent yet — see is_not_sent_status)."""
    c = _code_text(raw)
    if not c:
        return None
    words = c.split()
    if len(words) > 8:
        # long free text (a comment): an explicit "status: X" inside it, else its FIRST
        # clause ("Approved as noted, please incorporate …" → "Approved as noted")
        m = re.search(r'\bstatus\b(.*)', c)
        if m and m.group(1).split():
            c = ' '.join(m.group(1).split()[:6])
        else:
            c = _code_text(_CLAUSE.split(str(raw), 1)[0])
            if not c or len(c.split()) > 8:
                return None
        words = c.split()
    compact = c.replace(' ', '')
    if compact in _EXACT:
        return _EXACT[compact]
    if compact in _CODE_VERDICT:
        return _CODE_VERDICT[compact]
    # two codes at once ('B/C', '2/3') — ambiguous, don't guess
    if re.fullmatch(r'[a-d1-4pw](/[a-d1-4pw])+', compact):
        return None
    # not sent yet ('Under preparation', 'Pending submission', 'In progress') — no review
    if _NOT_SENT.search(c):
        return None
    # order matters: "no exceptions" / "no objection" before "not"; "not approved" before
    # "approv"; "resubmitted" (sent again) before "resubmit" (an instruction); "awaiting
    # approval" before "approv"; every finished-review wording before "review"
    if 'no exception' in c or 'no objection' in c:
        return 'approved'
    if 'not approv' in c or 'disapprov' in c or 'unapprov' in c or 'not accepted' in c or 'reject' in c:
        return 'not_approved'
    if _RESUBMIT_ORDER.search(c):
        return 'not_approved'
    if _RESUBMITTED.search(c):
        return 'under_review'
    if 'resubmit' in c or 'revise' in c:
        return 'not_approved'
    if _PENDING_APPROVAL.search(c):
        return 'under_review'
    if _FINISHED_OK.search(c):
        return 'approved'
    if _UNDER_REVIEW.search(c):
        return 'under_review'
    # an explicit code inside the text: "Code 2", "code-c"
    m = re.search(r'\bcode ?([a-d1-4pw])\b', c)
    if m:
        return _CODE_VERDICT[m.group(1)]
    # a short cell holding a standalone letter code ("Code A" style handled above)
    if len(words) <= 3:
        for w in words:
            if w in _CODE_VERDICT and not w.isdigit():
                return _CODE_VERDICT[w]
    return None


def legend_code_candidates(raw):
    """The code(s) a cell could be quoting, upper-case: 'B', '(B)', 'Code B',
    'Approved (Code B)', 'B - approved as noted', 1.0 → ['B'] / ['1']."""
    if raw is None or isinstance(raw, bool):
        return []
    if isinstance(raw, (int, float)):
        if raw != raw:
            return []
        return [str(int(raw)) if float(raw).is_integer() else str(raw)]
    m = _DEC_ZERO.match(str(raw))
    if m:                                    # '2.0' typed as text
        return [m.group(1).lstrip('0') or '0']
    s = ' '.join(str(raw).upper().split())
    out = []
    compact = re.sub(r'[^A-Z0-9]', '', s)
    if 1 <= len(compact) <= 3:
        out.append(compact)
    for m in re.finditer(r'\(\s*(?:CODE\s*)?([A-Z0-9]{1,3})\s*\)', s):
        out.append(m.group(1))
    for m in re.finditer(r'\bCODE\s*[-:]?\s*([A-Z0-9]{1,3})\b', s):
        out.append(m.group(1))
    m = re.match(r'^([A-Z0-9]{1,3})\s*[-–=:]\s*\S', s)
    if m:
        out.append(m.group(1))
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def classify_action_code_with_legend(raw, legend=None):
    """Scheme-aware review code: a legend found in the log ({code: verdict}, verdict one of
    'approved' | 'not_approved' | 'under_review' | 'ignore') wins for any code it lists;
    everything else falls back to the default rule (classify_action_code). 'ignore' → None
    (the planner chose not to count that code)."""
    if legend:
        leg = {str(k).strip().upper(): v for k, v in legend.items() if str(k).strip()}
        for code in legend_code_candidates(raw):
            if code in leg:
                v = leg[code]
                return v if v in VERDICTS else None
    return classify_action_code(raw)


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
