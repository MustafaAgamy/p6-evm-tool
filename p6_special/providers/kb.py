"""Knowledge Base provider — the reference standard the open schedule maps to.

WHAT THE KB SCREEN SHOWS.  The Knowledge Base nav item (ui/modules/database.js →
``showDatabase``) is a browsable LIBRARY of project-type reference standards. For a
selected type its detail pane (``referenceStandard()``) renders the curated
standard: the standard WBS branches, the standard activities (key / often-missing,
with typical sequence, duration and why-it-matters), the construction logic rules
(before → after, reason, impact), the milestones and the common issues the type
catches — plus the detection keywords. That pane is fed by ``/api/kb`` which is a
straight ``p6_kb.kb.load_kb()`` dump. It is NOT a review of the open schedule and
it computes no score.

WHY THIS IS NOT CONSTRUCTABILITY.  The KB screen's "Review my schedule against
this" button just launches the Constructability feature (construct.js), whose
findings + risk score are already exposed by ``providers/constructability.py``
(via ``feature_reports.kb_v2_report``). The legacy ``feature_reports.kb_full_report``
adapter reuses ``p6_kb.exporters.render_html(run_review(...))`` — that is the OLD
constructability *review* (score/verdict/illogical/missing tables), NOT the KB
library screen, and it duplicates + contradicts the current Constructability
result, so it is deliberately NOT reused here.

WHAT THIS PROVIDER EXPOSES.  A Reporting Studio result is composed into ONE
project's report, so the parity-honest projection of a global library onto a
single project is: the reference standard for the type THIS schedule is auto-
detected as — the exact same curated ``load_kb()`` entry the library detail pane
renders (found with ``detect_subtype``, the same detection the KB review uses).
The items below mirror that detail pane's sections verbatim; none re-derives the
Constructability score/findings.

RENDERER REUSE?  There is no server-side renderer for the reference-standard
detail pane (the KB screen builds it client-side in database.js), so these are
hand-built payloads that match that screen's labels, columns and format — read
from the KB entry exactly as the screen reads ``state.kbStandards[type]``.
"""
from p6_special import payloads as P
from p6_special.registry import Item

FEATURE = 'kb'
FEATURE_TITLE = 'Knowledge Base'


# ── detection (the entry the library detail pane would show for this schedule) ──
def _entry(ctx):
    """The curated KB entry the open schedule is auto-detected as, or None.

    Memoised + exception-safe: it parses once (via ``ctx.parsed()``) and detects
    with the SAME ``detect_subtype(schedule_view, load_kb())`` the KB review uses,
    returning the raw curated entry (no learned blend — the library detail pane
    shows the curated standard, ``/api/kb`` == ``load_kb()``). None when there is
    no file or nothing matches a known type — so availability can gate honestly.
    """
    def build():
        try:
            data = ctx.parsed()
            if data is None:
                return None
            from p6_kb.model import schedule_view
            from p6_kb.kb import load_kb
            from p6_kb.detect import detect_subtype
            entry, _scored = detect_subtype(schedule_view(data), load_kb())
            return entry
        except Exception:
            return None
    return ctx.memo('kb_detected_entry', build)


def _ptype(entry):
    """``Category › Type`` — exactly the KB screen's project_type string."""
    cat, typ = (entry.get('category') or ''), (entry.get('type') or '')
    return f'{cat} › {typ}' if cat else typ


# ── section builders (verbatim mirrors of database.js referenceStandard()) ─────
def _wbs_table(entry):
    """Standard WBS branches — the screen's "Standard WBS · N branches" list."""
    wbs = entry.get('wbs') or []
    if not wbs:
        return None
    return P.table(columns=['Standard WBS branch'],
                   rows=[[w.get('name', '')] for w in wbs], aligns=['l'])


def _activities_table(entry):
    """Standard activities — the screen's "Standard activities" table, same 5
    columns and the same "pred → succ" sequence format (database.js kb-acts)."""
    acts = entry.get('activities') or []
    if not acts:
        return None
    rows = []
    for a in acts:
        seq = a.get('typical_succ') or a.get('name') or ''
        if a.get('typical_pred'):
            seq = f"{a.get('typical_pred')} → {seq}"
        dur = a.get('duration_days')
        rows.append([a.get('name', ''), a.get('wbs', ''), seq,
                     ('—' if dur is None else str(dur)), a.get('why', '')])
    return P.table(
        columns=['Activity', 'WBS', 'Typical sequence', 'Dur (d)', 'Why it matters'],
        rows=rows, aligns=['l', 'l', 'l', 'r', 'l'])


def _logic_rules_table(entry):
    """Construction logic rules — before → after, reason and impact, with the
    critical impact reddened (matches the screen's .kb-imp.c badge)."""
    rules = entry.get('logic_rules') or []
    if not rules:
        return None
    rows = []
    for r in rules:
        before = (r.get('before_keywords') or [''])[0]
        after = (r.get('after_keywords') or [''])[0]
        impact = r.get('impact') or 'Minor'
        tone = 'bad' if 'crit' in impact.lower() else 'neutral'
        rows.append([f'{before} → {after}', r.get('reason', ''),
                     (impact.upper(), tone)])
    return P.table(columns=['Sequence (before → after)', 'Reason', 'Impact'],
                   rows=rows, aligns=['l', 'l', 'l'])


def _milestones_block(entry):
    ms = entry.get('milestones') or []
    if not ms:
        return None
    return P.keyvals([('Milestones', ' · '.join(str(m) for m in ms))])


def _common_issues_block(entry):
    """Common issues it catches — the screen's kb-issues list."""
    issues = entry.get('common_issues') or []
    if not issues:
        return None
    return P.text([f'• {i}' for i in issues])


# ── producers ──────────────────────────────────────────────────────────────
def _reference_standard(ctx):
    """The whole detail pane for the detected type, one section (like the screen)."""
    entry = _entry(ctx)
    # Gate identically to _avail_standard so availability exactly complements
    # produce: a type with neither WBS nor activities has no standard to show.
    if not entry or not (entry.get('wbs') or entry.get('activities')):
        return P.NO_DATA
    ptype = _ptype(entry)
    sigs = [str(s) for s in (entry.get('signatures') or [])]
    blocks = [
        P.note(f'Reference standard for {ptype} — the project type this schedule was '
               f'auto-detected as. Its standard WBS, activities and construction logic '
               f'are the benchmark the schedule is reviewed against (the Constructability '
               f'result shows the findings).'),
        P.keyvals([('Project type', ptype),
                   ('Detected by', f"{len(sigs)} standard keywords")]),
    ]
    if sigs:
        # The KB detail pane shows the actual detection keyword chips (up to 18), not
        # just the count (ui/modules/database.js chips(std.signatures.slice(0, 18))).
        blocks.append(P.text('Detection keywords: ' + ', '.join(sigs[:18])))
    blocks += [
        _wbs_table(entry),
        _activities_table(entry),
        _logic_rules_table(entry),
        _milestones_block(entry),
        _common_issues_block(entry),
    ]
    return P.group(blocks)


def _activities(ctx):
    entry = _entry(ctx)
    return (_activities_table(entry) or P.NO_DATA) if entry else P.NO_DATA


def _wbs(ctx):
    entry = _entry(ctx)
    return (_wbs_table(entry) or P.NO_DATA) if entry else P.NO_DATA


def _logic_rules(ctx):
    entry = _entry(ctx)
    return (_logic_rules_table(entry) or P.NO_DATA) if entry else P.NO_DATA


def _common_issues(ctx):
    entry = _entry(ctx)
    return (_common_issues_block(entry) or P.NO_DATA) if entry else P.NO_DATA


# ── availability — exactly complements each producer ─────────────────────────
# 'ready' ONLY when a type is detected AND the specific slice carries data, so a
# 'ready' item never renders empty (the #1 past defect). Never raises (a raising
# availability would default to 'ready' in registry.descriptor).
def _avail_standard(ctx):
    e = _entry(ctx)
    if not e:
        return 'no_data'
    return 'ready' if (e.get('wbs') or e.get('activities')) else 'no_data'


def _avail_slice(key):
    def _a(ctx):
        e = _entry(ctx)
        return 'ready' if (e and e.get(key)) else 'no_data'
    return _a


def provide(ctx):
    return [
        Item('kb:reference_standard', FEATURE, FEATURE_TITLE,
             'Reference standard — detected project type', 'section',
             _reference_standard, _avail_standard),
        Item('kb:standard_activities', FEATURE, FEATURE_TITLE,
             'Standard activities', 'table', _activities, _avail_slice('activities')),
        Item('kb:standard_wbs', FEATURE, FEATURE_TITLE,
             'Standard WBS branches', 'table', _wbs, _avail_slice('wbs')),
        Item('kb:logic_rules', FEATURE, FEATURE_TITLE,
             'Construction logic rules', 'table', _logic_rules, _avail_slice('logic_rules')),
        Item('kb:common_issues', FEATURE, FEATURE_TITLE,
             'Common issues to check for', 'text', _common_issues, _avail_slice('common_issues')),
    ]
