"""The offline knowledge the Copilot reasons from — recognised industry sources, curated
and cited so a Planning answer names the *right* method and the *right* clause:

  • delay-analysis methods  (AACE 29R-03 taxonomy)
  • contract EOT clauses     (FIDIC 1999 / 2017)
  • planning / forensic standards (AACE, SCL, DCMA, PMI)
  • a best-effort read of the local Construction Knowledge Base for the project's likely type

No cloud, no cost. Everything here is general industry practice, not legal advice — the
answers that use it stay carefully worded (indicators, never "you are entitled").
"""

# ── Delay-analysis methods (AACE International RP 29R-03 taxonomy) ───────────
DELAY_METHODS = {
    'tia': {
        'key': 'tia', 'name': 'Time Impact Analysis (TIA)',
        'aace': 'AACE 29R-03 · MIP 3.7 (modelled / additive)', 'timing': 'prospective',
        'plain': ("Model the delay event into the programme that was current just before it, then "
                  "re-run the schedule (P6 F9) to see how the completion date moves. Best for a live, "
                  "forward-looking EOT while the job is still running — it's what this tool's what-if builds.")},
    'windows': {
        'key': 'windows', 'name': 'Windows / Time-Slice Analysis',
        'aace': 'AACE 29R-03 · MIP 3.3–3.5 (observational / dynamic)', 'timing': 'retrospective',
        'plain': ("Split the job into time windows (usually the progress updates) and measure the delay that "
                  "actually became critical in each window. Strong and evidence-based when you have reliable, "
                  "regular updates — best used after the fact.")},
    'iap': {
        'key': 'iap', 'name': 'Impacted As-Planned',
        'aace': 'AACE 29R-03 · MIP 3.6 (modelled / additive, single base)', 'timing': 'prospective',
        'plain': ("Add the delay events onto the original baseline and re-run it. Simple, but the weakest method — "
                  "it ignores actual progress and how the job really unfolded. Use only when proper updates don't exist.")},
    'as_built': {
        'key': 'as_built', 'name': 'Collapsed As-Built (But-For)',
        'aace': 'AACE 29R-03 · MIP 3.8–3.9 (modelled / subtractive)', 'timing': 'retrospective',
        'plain': ("Take the completed as-built programme and remove the delay events to show what would have "
                  "happened but for them. Powerful in a dispute, but needs a reliable, fully-logic-linked as-built "
                  "— this is the method behind the tool's Consultant Review 'but-for' file.")},
}
METHOD_ORDER = ['tia', 'windows', 'iap', 'as_built']

# ── Contract EOT clauses (FIDIC) ────────────────────────────────────────────
CONTRACTS = {
    'fidic_2017': {
        'key': 'fidic_2017', 'name': 'FIDIC 2017 (Red / Yellow / Silver)',
        'eot_clause': 'Sub-Clause 8.5', 'notice_clause': 'Sub-Clause 20.2', 'notice_days': 28, 'detail_days': 84,
        'plain': ("Give notice of the delaying event within 28 days of becoming aware of it, and a fully detailed "
                  "claim within 84 days (Sub-Clause 20.2); the extension of time itself is assessed under Sub-Clause 8.5. "
                  "Miss the 28-day notice and the claim can be time-barred.")},
    'fidic_1999': {
        'key': 'fidic_1999', 'name': 'FIDIC 1999 (Red / Yellow / Silver)',
        'eot_clause': 'Sub-Clause 8.4', 'notice_clause': 'Sub-Clause 20.1', 'notice_days': 28,
        'plain': ("Give notice of the delaying event within 28 days of becoming aware of it (Sub-Clause 20.1); the "
                  "extension of time is assessed under Sub-Clause 8.4. The 28-day notice is a condition precedent — "
                  "late notice can bar the claim.")},
}

# ── Planning / forensic standards the engine leans on ───────────────────────
STANDARDS = {
    'aace_29r03': {
        'name': 'AACE RP 29R-03 — Forensic Schedule Analysis',
        'plain': "the recognised catalogue of delay-analysis methods (nine protocols, observational vs modelled) — used to pick and defend the method."},
    'scl': {
        'name': 'SCL Delay & Disruption Protocol (2nd ed., 2017)',
        'plain': "industry good-practice on EOT, concurrency and float — it prefers a contemporaneous cause-and-effect analysis, and treats float as a shared buffer, not owned by either party until it's used up."},
    'dcma': {
        'name': 'DCMA 14-Point Schedule Assessment',
        'plain': "a schedule-quality health check (logic gaps, leads/lags, hard constraints, high/negative float, the critical-path test) — a weak schedule undermines any claim."},
    'pmi': {
        'name': 'PMI scheduling practice',
        'plain': "general good practice — sound CPM logic, one clear critical path, realistic durations."},
}


def method(key):
    return DELAY_METHODS.get(key)


def contract(edition='fidic_2017'):
    """The FIDIC edition to frame a claim against. 2017 is the current default; 1999 is still
    the most-used in the field, so both are carried."""
    return CONTRACTS.get(edition, CONTRACTS['fidic_2017'])


def contract_line():
    """A plain, edition-safe FIDIC framing. Which edition applies is the *contract's* to say,
    not the schedule's — so both are cited and the planner maps to their own contract."""
    c17, c99 = CONTRACTS['fidic_2017'], CONTRACTS['fidic_1999']
    return (f"under FIDIC the EOT clause is {c17['eot_clause']} (2017 editions) or {c99['eot_clause']} (1999), "
            f"with notice within {c17['notice_days']} days ({c17['notice_clause']} / {c99['notice_clause']}) — "
            "confirm which edition your contract uses (or the equivalent under NEC / a bespoke form).")


def recommend_method(ctx):
    """Pick the delay-analysis method that fits this update, in plain words with the 'why'.
    A live programme with a real slip to completion → a contemporaneous TIA."""
    delay = ctx.get('delay_days')
    if delay and delay > 0:
        why = ("the job is live and completion has already moved, so a contemporaneous Time Impact Analysis on the "
               "current programme is the defensible choice — it's forward-looking and cause-and-effect (SCL Protocol; "
               "AACE MIP 3.7). Windows analysis is the retrospective alternative once the period closes.")
    else:
        why = ("there's no slip to completion in this update, so no formal analysis is needed yet — reach for a Time "
               "Impact Analysis the moment a delay to the finish appears.")
    return {'method': DELAY_METHODS['tia'], 'why': why}


def _kb_text(ctx):
    """The text we offer the Construction KB detector from a DB-only context. Only the
    project *name* is used: it usually carries the type ("… Factory", "Metro …", "… Hospital"),
    whereas discipline names (MEP, Civil, Engineering) are generic to every project and only
    add false matches."""
    return (ctx.get('project_name') or '').strip()


def detect_project_type(ctx):
    """Best-effort read of the local Construction Knowledge Base for this project's likely
    sub-type, from the project + discipline names. Returns a plain dict or None. Fully
    defensive — the KB or its detector may be absent on this branch/build, and a missing
    type must never break an answer.

    {type, category, confident, needs[<=4], issues[<=2]}"""
    text = _kb_text(ctx)
    if len(text) < 3:
        return None
    try:
        from p6_kb.kb import load_kb
        from p6_kb.detect import score_entries
    except Exception:
        return None
    try:
        entries = load_kb()
    except Exception:
        entries = []
    if not entries:
        return None
    # Minimal 'view' the detector understands (it only reads activity/WBS names).
    view = {'activities': [{'name': text, 'wbs_path': ''}], 'wbs': []}
    try:
        scored = score_entries(view, entries)
    except Exception:
        return None
    if not scored or scored[0][1] <= 0:
        return None
    entry, hits = scored[0]
    needs = [a.get('name') for a in (entry.get('activities') or []) if a.get('name')][:4]
    issues = [str(i) for i in (entry.get('common_issues') or [])][:2]
    return {
        'type': entry.get('type'), 'category': entry.get('category'),
        'confident': hits >= 2,            # one keyword is a hint; two+ is a real signal
        'needs': needs, 'issues': issues,
    }
