"""Theme 7 — Baseline Revision & Update Review.

What changed between two versions of a schedule — revision to revision (the approved
baseline vs a new revision) and update to update (last period vs this one) — and whether the
move is honest re-planning or a slip dressed up to look better.

Grounding note (important and honest): a version-to-version comparison is computed from
**two** schedules by the Baseline Revision Comparison / Consultant Review / Update-vs-Update
features. This chat reads the ONE snapshot the user has loaded, so the FACTS dict carries the
current schedule's position (finish, SPI, progress by discipline) and its own DCMA-style
logic health (out-of-sequence, open ends, dangling, float, critical path) — all grounded —
but not the diff between two baselines. Every answer therefore leads with a direct read of
the question, grounds the current schedule in F, explains how a senior planner reads the
comparison view, and says plainly that the before/after deltas live in the feature (with a
pointer), never inventing a revision-to-revision number the single snapshot can't carry.
"""
from . import _kit as K


# ── shared bits ─────────────────────────────────────────────────────────────────

def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can answer this "
              "from your own numbers — offline, nothing leaves your PC.",
              "For a revision-to-revision or update-to-update comparison, load both versions in the "
              "Baseline Revision Comparison and I'll read the diff from there."])


def _kit_delay(F):
    """Signed delay chip value: '+60 wd (behind)' / '-12 wd (ahead)' / 'on date'."""
    d = F.get('delay_days')
    if d is None:
        return None
    d = round(d)
    if d > 0:
        return f"+{d} wd (behind)"
    if d < 0:
        return f"{d} wd (ahead)"
    return "on date"


def _join(items):
    items = [i for i in items if i]
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    return ', '.join(items[:-1]) + ' and ' + items[-1]


def _position_line(F):
    """Grounded one-liner on where the loaded schedule currently stands (finish + pace)."""
    return (f"On the schedule you've loaded the finish is {K.delay_phrase(F)}, and "
            f"{K.spi_verdict(F)[1]}.")


def _progress_line(F):
    a, p = F.get('actual_pct'), F.get('planned_pct')
    if a is None or p is None:
        return ''
    diff = round((p or 0) - (a or 0))
    tail = (f" — about {abs(diff)} points {'behind' if diff > 0 else 'ahead of'} the curve"
            if diff else " — right on the planned curve")
    return f"Physically it stands at **{K.pct(a)}** complete against **{K.pct(p)}** planned{tail}."


def _dcma_flags_line(F, lead="On the loaded schedule I can already see"):
    """The current schedule's cleanup flags, grounded from F, or '' if clean."""
    bits = []
    if F.get('oos_count'):
        bits.append(f"**{F['oos_count']} out-of-sequence** activit{'y' if F['oos_count'] == 1 else 'ies'}"
                    + (f" ({K.pct(F.get('oos_pct'))})" if F.get('oos_pct') is not None else ""))
    if F.get('open_ends'):
        bits.append(f"**{F['open_ends']} open end{'s' if F['open_ends'] != 1 else ''}**")
    if F.get('dangling_count'):
        bits.append(f"**{F['dangling_count']} dangling** logic link{'s' if F['dangling_count'] != 1 else ''}")
    if F.get('neg_float_count'):
        bits.append(f"**{F['neg_float_count']}** activit{'y' if F['neg_float_count'] == 1 else 'ies'} on **negative float**")
    if not bits:
        return ''
    return f"{lead} " + _join(bits) + " — clean those before any resubmission so no one can argue the finish is an artefact."


def _grades_line(F):
    parts = []
    for label, key in (('logic/float', 'float_grade'), ('out-of-sequence', 'oos_grade'),
                       ('open ends', 'open_ends_grade'), ('dangling logic', 'dangling_grade'),
                       ('critical path / CPLI', 'cpli_grade')):
        g = F.get(key)
        if g:
            parts.append(f"{label} **{g}**")
    if not parts:
        return ''
    return "On this snapshot the DCMA-style quality grades read " + _join(parts) + "."


def _driver_body(F):
    """The weighted-driver sentence for this schedule, framed for a revision review."""
    dl = K.driver_line(F)
    if dl:
        return ("The shortfall on the loaded schedule is concentrated, not spread — that's the front any "
                "honest re-plan has to recover: " + dl)
    return ("The progress split by discipline shows no single dominant shortfall front on this snapshot — "
            "read the category bars to see where the movement sits.")


def _two_schedule_note(verb="the before/after diff"):
    return (f"{verb.capitalize()} itself — the exact date move, the added and removed activities, the logic, "
            "duration and calendar changes — is computed from **both** schedules inside the Baseline Revision "
            "Comparison. This chat is reading the single snapshot you've loaded, so open the approved baseline "
            "and the new revision side by side there for the precise deltas; I won't invent a revision-to-revision "
            "figure this one file can't carry.")


# ── answers ───────────────────────────────────────────────────────────────────

def t07q00(F, role):
    """Headline of everything that changed between approved baseline and new revision."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    head = ("Headline first: run the Baseline Revision Comparison **exec summary** — it buckets every change "
            "into scope, durations, logic, calendar, constraints, milestones and WBS, each with a severity flag, "
            "before you read a single line of detail.")
    body = [
        "Read it top-down. In one screen the summary separates the changes that actually move the finish date "
        "from the cosmetic churn — renames, code tidy-ups, re-decomposition — so you argue only about what "
        "matters and don't get dragged through noise.",
        _position_line(F),
        _progress_line(F),
        _driver_body(F),
        _two_schedule_note(),
    ]
    if tech:
        body.append("As the planner, cross-read each severity flag against total float — a change tagged material "
                    "on a near-zero-float chain is the one that will actually move CPLI and the completion date; "
                    "one on a high-float branch is note-and-move-on.")
    return K.A(head, body,
               advice=["Lead your review with the exec summary's material set; log the cosmetic set but don't debate it.",
                       "Then read the driver bridge — that's the next answer — to see what pushed the date.",
                       K.go_deeper('Baseline Revision Comparison', 'For the full change breakdown')],
               evidence=[K.ev('Baseline Revision', 'Finish position', _kit_delay(F)),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Actual vs planned',
                              (f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"
                               if F.get('actual_pct') is not None else None))])


def t07q01(F, role):
    """Finish-slip driver bridge: added scope vs longer durations vs logic vs calendar."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Use the finish-slip **driver bridge** — it splits the date move across the four causes (added "
            "scope, duration growth, logic edits, calendar changes) so you know whether this is real slippage "
            "or a paper change.")
    body = [
        "That distinction is the whole game. Scope and duration growth are things you can price and claim; a "
        "logic or calendar edit that moves the date without new work is a re-plan you interrogate. The bridge "
        "attributes the days so you're not guessing.",
        _driver_body(F),
        _position_line(F),
        "If the move lands on execution durations and logic on that driving front — not on genuinely new scope — "
        "read it as real site slippage the re-plan must recover, not something engineered onto paper. If it lands "
        "on added scope with no change order behind it, that's a change-claim indicator to pursue.",
        _two_schedule_note("the per-cause attribution"),
    ]
    return K.A(head, body,
               advice=["Recover against the named driver front, not the loudest raw gap — a tiny-weight design line moving is not the driver.",
                       K.go_deeper('Baseline Revision Comparison', 'For the finish-slip driver bridge')],
               evidence=[K.ev('Baseline Revision', 'Finish position', _kit_delay(F)),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('Driver', 'Front',
                              (K.main_driver(F) or {}).get('name'))])


def t07q02(F, role):
    """Added activities (real scope vs re-decomposition), deletions, criticality."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    head = ("Use the added / removed lists — but don't read every addition as new scope. The comparison flags "
            "whether an add is **genuine scope** or just **re-decomposition** (one activity split into several), "
            "and whether any added or deleted activity sits on the **driving path**.")
    body = [
        "That criticality flag is what matters for your claim position: a deleted critical activity or added "
        "critical scope moves the finish and your delay indicators; a re-decomposition off the critical chain "
        "changes the count but not the schedule.",
        ("The loaded schedule carries about **{ac:,} activities** in total, so you have the current denominator "
         "to reconcile the added/removed counts against.".format(ac=int(F['activity_count']))
         if F.get('activity_count') else
         "Reconcile the added/removed counts against your current activity total once both versions are loaded."),
        ("Its critical structure is worth knowing before you look: " + _crit_line(F)) if _crit_line(F) else "",
        _two_schedule_note("the added / removed lists"),
    ]
    if tech:
        body.append("Sort the added and removed sets by total float when you review them — anything at or below "
                    "zero float is the set that re-routes the driving path, and that's where a quiet add or delete "
                    "does real damage.")
    return K.A(head, body,
               advice=["Reconcile the added/removed flags against your change register before you accept the counts.",
                       "Confirm nothing landed on — or was lifted off — the driving chain unnoticed.",
                       K.go_deeper('Baseline Revision Comparison', 'For the added / removed lists')],
               evidence=[K.ev('Baseline Revision', 'Current activities', (f"{int(F['activity_count']):,}" if F.get('activity_count') else None)),
                         K.ev('Critical Path', 'Driving-path activities', F.get('driving_path_count')),
                         K.ev('Critical Path', 'Critical activities', F.get('cpli_critical_count'))])


def t07q03(F, role):
    """Did total scope grow — activities, man-hours, budget?"""
    if not F.get('ok'):
        return _no_project(F)
    head = ("The comparison sizes scope growth three ways — **activity count**, **man-hours** (these are "
            "man-hours, not headcount) and **loaded budget** — and that's your first measure of possible "
            "scope creep.")
    body = [
        "The reasoning to apply: if activities and man-hours jumped with no change order behind them, that's a "
        "change-claim indicator worth pursuing. The tool sizes the growth — it never establishes entitlement; "
        "that stays a contractual determination.",
        ("Today the loaded schedule holds about **{ac:,} activities**; use that as the baseline count the "
         "comparison measures growth against.".format(ac=int(F['activity_count']))
         if F.get('activity_count') else
         "Load both versions and the comparison will give you the activity-count delta directly."),
        "On the money line, one honest caveat that runs through this whole tool: cost here is derived from "
        f"percent-complete, so CPI sits structurally near 1.0 (currently **{K.ratio(F.get('cpi'))}**) — don't "
        "build a cost drama off it. A percentage-only scope change won't move the budget line; keep any budget "
        "growth qualitative unless the cost-loading actually backs it.",
        "For a real man-hour and budget read of the growth you need the resource side, not just the schedule — "
        "that's where Productivity & Resource Intelligence carries the norms and man-hours by component.",
    ]
    return K.A(head, body,
               advice=["Cross-check any man-hour or budget growth against the cost-loading before you call it scope creep.",
                       K.go_deeper('Baseline Revision Comparison', 'For the scope-growth sizing')],
               evidence=[K.ev('Baseline Revision', 'Current activities', (f"{int(F['activity_count']):,}" if F.get('activity_count') else None)),
                         K.ev('EVM', 'CPI', K.ratio(F.get('cpi'))),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi')))])


def t07q04(F, role):
    """Every logic change, filtered to the driving path."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    head = ("Pull the logic-change diff — relationships **added, removed and retyped** — then filter it to the "
            "**driving path**. That filter is the only cut that matters; edits off the critical chain are "
            "housekeeping.")
    body = [
        "The concern behind the question is manipulation: retyping an FS to SS, or removing a link, can pull the "
        "finish in on paper without any work changing. So you scrutinise the changes that touch the governing "
        "chain and treat the rest as genuine re-planning.",
        ("The loaded schedule's critical structure to judge that against: " + _crit_line(F)) if _crit_line(F) else
        "Read the current driving path first so you know which relationships the filter should light up.",
        "Unless the driver bridge says a specific relationship change moved the finish, treat the logic edits as "
        "honest re-sequencing. A change that both sits on the driving path and shortens the date is the one you "
        "raise with the consultant.",
        _two_schedule_note("the logic-change diff"),
    ]
    if tech:
        body.append("Watch specifically for FS→SS/FF retypes and lag introduced on the driving chain — those are "
                    "the edits that compress the path without touching a duration, and they're the classic tell.")
    return K.A(head, body,
               advice=["Filter the logic diff to the driving path; everything off it is note-only.",
                       K.go_deeper('Baseline Revision Comparison', 'For the logic-change diff')],
               evidence=[K.ev('Critical Path', 'Driving-path activities', F.get('driving_path_count')),
                         K.ev('Schedule Health', 'CPLI grade', F.get('cpli_grade')),
                         K.ev('Out-of-sequence', 'On loaded schedule', F.get('oos_count'))])


def t07q05(F, role):
    """Which durations changed; critical-path durations shortened without a reason."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("The duration-change register lists every stretched or shortened activity and specifically flags "
            "**critical-path durations that were cut** — a shortened critical duration with no stated reason is "
            "the classic manipulation tell, so that's where you look hardest.")
    body = [
        "The logic is simple: stretching durations is usually honest (it shows the loss). Quietly cutting a "
        "critical duration to hold the date is how a slip gets dressed up. The register isolates exactly that "
        "case for you.",
        ("The current driving structure the register measures against: " + _crit_line(F)) if _crit_line(F) else
        "Read the current driving path first, so a cut duration on that chain stands out.",
        _position_line(F),
        "If critical durations did move, get the planner's productivity or method justification for each — a "
        "re-sequenced crew, a faster method, more shifts. Absent a stated reason, treat a quiet critical-path cut "
        "as a red flag to raise with the consultant, not as recovery.",
        _two_schedule_note("the duration-change register"),
    ]
    return K.A(head, body,
               advice=["Demand a stated productivity or method reason for any shortened critical-path duration.",
                       K.go_deeper('Baseline Revision Comparison', 'For the duration-change register')],
               evidence=[K.ev('Baseline Revision', 'Finish position', _kit_delay(F)),
                         K.ev('Critical Path', 'Driving-path activities', F.get('driving_path_count')),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi')))])


def t07q06(F, role):
    """Re-sequencing, added constraints, calendar inflation — the manipulation trio."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    head = ("That's a three-part manipulation check and you run all three: **sequence reversals**, **newly added "
            "constraints**, and **calendar inflation** (extra working days or shifts that pull the finish in on "
            "paper). Any one of them can make a date look better without a day of real recovery.")
    body = [
        "How to read each: a reversed sequence that no longer matches how the work is actually built; a hard "
        "constraint quietly holding a date the logic doesn't support; a calendar with added shifts or working "
        "days that shortens the critical chain arithmetically. The comparison surfaces all three between the two "
        "versions.",
        _dcma_flags_line(F) or "On the loaded schedule the logic health flags are clean — no out-of-sequence or "
                               "open-end items jump out — which is a good starting point for a resubmission.",
        (f"Hard-constraint effects are {'computable on this file' if F.get('hard_constraints_computable') else 'not fully computable on this file'}, "
         "so confirm any added constraint's real effect on the date in the health review rather than assuming it."
         if F.get('hard_constraints_computable') is not None else ""),
        "For the calendar leg specifically, the Calendar Audit is the sharper tool — it shows the working-day "
        "pattern and lets you compare two calendars, so you can see if a shift or working-day was added between "
        "versions to buy days.",
    ]
    if tech:
        body.append("Run the sequence-reversal check against total float too: a reversal that also drops float "
                    "to zero on a chain is the one re-routing the driving path, not just tidying logic.")
    return K.A(head, body,
               advice=["Fix the out-of-sequence and open-end items before resubmission so the finish reads as real driving logic.",
                       K.go_deeper('Baseline Revision Comparison', 'For the sequence / constraint / calendar checks'),
                       K.go_deeper('Calendar Audit', 'For the calendar-inflation check')],
               evidence=[K.ev('Out-of-sequence', 'Activities', F.get('oos_count')),
                         K.ev('Open ends', 'Count', F.get('open_ends')),
                         K.ev('Calendar', 'Calendars in file', F.get('calendar_count'))])


def t07q07(F, role):
    """Did the critical path re-route; where did float migrate between the two baselines?"""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    head = ("Use the **criticality-change** and **float-migration** views together — they show whether the "
            "driving chain jumped to a different work front and who lost or gained slack between the two "
            "baselines.")
    body = [
        "This is the view that stops you fixing the wrong thing. If the driver moved fronts, recovering the old "
        "critical path buys you nothing — the bottleneck just shifts sideways to whatever went critical behind "
        "it. You plan recovery against the new driving chain and its nearest rival together.",
        _float_line(F) or "Read the float distribution on the loaded schedule first so you can see which chains "
                          "are near-critical and would turn critical if the driver slips further.",
        _crit_line(F) and ("Current critical structure: " + _crit_line(F)) or "",
        _position_line(F),
        _two_schedule_note("the float-migration view"),
    ]
    if tech:
        body.append("The migration to watch is float draining toward zero on a second front — the moment a "
                    "near-critical chain crosses into negative total float, you're managing two driving paths, "
                    "and any single-front recovery plan is already out of date.")
    return K.A(head, body,
               advice=["Plan recovery against the new driving chain and its nearest near-critical rival, not last version's path.",
                       K.go_deeper('Baseline Revision Comparison', 'For the criticality / float-migration views'),
                       K.go_deeper('Critical Path Analyzer', 'To confirm the driving path in each version')],
               evidence=[K.ev('Float', 'Negative-float activities', F.get('neg_float_count')),
                         K.ev('Float', 'Max total float', (K.wd(F.get('max_float')) if F.get('max_float') is not None else None)),
                         K.ev('Critical Path', 'Driving-path activities', F.get('driving_path_count'))])


def t07q08(F, role):
    """Material vs cosmetic; same work with a new ID or name (traceability)."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("The comparison classifies every change **material vs minor** and reconciles activities that kept the "
            "same work but got a new **ID or name** — so a rename doesn't surface as a false delete-plus-add. "
            "That reconciliation is what keeps the change count honest and traceable.")
    body = [
        "Why it matters: without id/name reconciliation, a tidy-up that renumbered fifty activities would read as "
        "fifty deletes and fifty adds — a fake scope swing that buries the handful of changes that actually move "
        "the date. The tool matches them so your count reflects real change only.",
        "Spend your review time — and the client conversation — on the material set: the changes that touch the "
        "driving path, durations, logic or milestones. The cosmetic churn (renames, code tidy-ups, "
        "re-decomposition) you note for traceability but don't argue over; it carries no schedule effect.",
        ("Tie the material set back to the finish it produced: on the loaded schedule the finish is "
         + K.delay_phrase(F) + "."),
        "This pairs with two neighbours: the added/removed reconciliation (so a rename isn't counted as scope) and "
        "the WBS-structure diff (so activities shuffled between nodes are still traced) — read the three together "
        "and the change count stays trustworthy end to end.",
        _two_schedule_note("the material-vs-minor classification"),
    ]
    return K.A(head, body,
               advice=["Review and challenge only the material set; log the cosmetic set for traceability and move on.",
                       K.go_deeper('Baseline Revision Comparison', 'For the material-vs-minor classification')],
               evidence=[K.ev('Baseline Revision', 'Finish position', _kit_delay(F)),
                         K.ev('Baseline Revision', 'Current activities', (f"{int(F['activity_count']):,}" if F.get('activity_count') else None))])


def t07q09(F, role):
    """Which contract milestones moved and by how many days; renamed-milestone reconciliation."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("The milestone-change table gives each milestone's move in **working days**, with similar-name "
            "reconciliation so a renamed milestone isn't reported as one removed and another added. That's your "
            "sectional-completion exposure — every interim date that slipped carries its own LD risk, not just "
            "final handover.")
    body = [
        "Read it as a risk register, not a curiosity: each sectional or key date past its obligation is a separate "
        "liquidated-damages head, and clients recover on those independently of final completion. The renamed "
        "reconciliation matters here too — a milestone that was relabelled must not read as one deleted and a "
        "brand-new one added, or you'll misstate both the count and the exposure.",
        ("For scale, the whole schedule currently forecasts " + K.delay_phrase(F) +
         " — the milestone table breaks that headline move down date by date."),
        "One caveat I'll always state plainly: the tool reads the **P6 milestone constraint dates**, not the "
        "contract dates themselves — formal contract-date ingest is a known gap. So reconcile every move against "
        "the actual contractual obligation before you report exposure to the client; the schedule date and the "
        "contract date aren't always the same thing.",
        _two_schedule_note("the milestone-change table"),
    ]
    return K.A(head, body,
               advice=["Treat every slipped interim milestone as its own LD exposure, reconciled to the real contract date.",
                       K.go_deeper('Baseline Revision Comparison', 'For the milestone-change table'),
                       K.go_deeper('Critical Path Analyzer', 'To confirm the driving path into each milestone')],
               evidence=[K.ev('Baseline Revision', 'Finish position', _kit_delay(F)),
                         K.ev('Critical Path', 'Driving-path activities', F.get('driving_path_count'))])


def t07q10(F, role):
    """WBS restructure — branches added/removed, activities shuffled between nodes."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("The structure diff shows **branches added or removed** and **activities shuffled between WBS nodes**. "
            "Watch this one closely — reorganising the WBS is a common way to bury added scope or make a "
            "comparison hard to follow.")
    body = [
        "The move to be alert to: activities quietly relocated under a new branch so the eye doesn't catch them, "
        "or a branch renamed so the two versions no longer line up node-for-node. A clean re-plan keeps the WBS "
        "stable or explains every structural move it makes.",
        "If activities did move nodes, the test is that **total scope still reconciles**: tie the structure diff "
        "back to the activity-added/removed counts and the man-hour sizing so nothing was slipped in under cover "
        "of the reorganisation. That cross-check — structure diff against scope-growth counts — is exactly the "
        "reconciliation the scope-growth question is asking for, run from the other direction.",
        ("Against the current schedule that's about **{ac:,} activities** to keep reconciled across the "
         "restructure.".format(ac=int(F['activity_count'])) if F.get('activity_count') else
         "Load both versions and reconcile the activity totals across the restructure."),
        _two_schedule_note("the WBS structure diff"),
    ]
    return K.A(head, body,
               advice=["After any WBS move, confirm the activity and man-hour totals still reconcile — no scope hidden under a new branch.",
                       K.go_deeper('Baseline Revision Comparison', 'For the WBS structure diff')],
               evidence=[K.ev('Baseline Revision', 'Current activities', (f"{int(F['activity_count']):,}" if F.get('activity_count') else None))])


def t07q11(F, role):
    """Manipulation roll-up (evidence, never verdict) plus the DCMA quality delta."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    head = ("The tool rolls up every suspicious signal — quiet critical-path duration cuts, added constraints, "
            "calendar padding, sequence reversals — as **evidence, never a verdict**. The judgement stays yours. "
            "It also gives the **DCMA quality delta** between the two versions.")
    body = [
        "That framing is deliberate and it protects you: you present the consultant indicators, not accusations, "
        "and let the data speak. A rolled-up set of clean signals says the delay reads genuine; a cluster of them "
        "on the driving path says look harder — but the tool never crosses into calling intent.",
        _grades_line(F) or "The stored DCMA-style grades will populate once the schedule's audit has run — those "
                           "are the numbers the version-to-version delta is measured on.",
        _dcma_flags_line(F, lead="Independently of the diff, the loaded schedule itself shows") or
        "Independently of the diff, the loaded schedule's logic health looks clean — no out-of-sequence or "
        "open-end items standing out — which is the honest starting quality for a resubmission.",
        "The quality **delta** — whether this version's logic got better or worse than the last — is the part "
        "computed from both schedules; from a single snapshot I can only give you this version's grades, not the "
        "movement. Load both and the health review reports the change.",
    ]
    if tech:
        body.append("Weight the evidence by where it sits: a shortened duration or added constraint on a "
                    "zero-float chain is worth ten cosmetic ones off the critical path. Rank the signals by their "
                    "float exposure before you take them to the consultant.")
    return K.A(head, body,
               advice=["Present the manipulation signals as indicators for discussion — never as a verdict on intent.",
                       K.go_deeper('Baseline Revision Comparison', 'For the manipulation roll-up'),
                       K.go_deeper('Schedule Health Review', 'For the DCMA quality delta')],
               evidence=[K.ev('Out-of-sequence', 'Grade', F.get('oos_grade')),
                         K.ev('Float', 'Grade', F.get('float_grade')),
                         K.ev('Open ends', 'Count', F.get('open_ends'))])


def t07q12(F, role):
    """Bottom line — genuine recovery re-plan, or a slip dressed up?"""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Read the **exec summary and the driver bridge together** and you get the honest answer: genuine "
            "re-plan or a slip in disguise. The test is whether the finish improved through real logic and "
            "recovery, or through quiet edits — shortened critical durations, added constraints, calendar padding, "
            "reversed sequences.")
    body = [
        "Here's how I'd frame it. " + _position_line(F),
        _progress_line(F),
        _driver_body(F),
        _dcma_flags_line(F, lead="Before you sign it off, note the schedule still carries") or
        "The logic health on this version looks clean, which supports treating the position as honest.",
        "If the comparison's manipulation roll-up comes back with nothing on the driving path, hold that honest "
        "position and don't dress it up — a real slip stated straight is far stronger with a client than a "
        "recovery you can't defend. If the roll-up lights up, the 'recovery' is on paper and you say so. That "
        "genuine-vs-dressed verdict is the one part that needs both schedules loaded; the current position above "
        "is grounded in the file you've given me.",
        "A credible recovery case is built from real, verifiable levers — added crews, extra shifts on the "
        "driving front, re-sequenced work — each proved out on the schedule, not asserted. Anything you can't "
        "verify in P6 doesn't belong in the re-plan.",
    ]
    return K.A(head, body,
               advice=["Hold the honest position: state the real loss and a P6-verified recovery, not a paper improvement.",
                       K.go_deeper('Baseline Revision Comparison', 'For the exec summary and driver bridge')],
               evidence=[K.ev('Baseline Revision', 'Finish position', _kit_delay(F)),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Actual vs planned',
                              (f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"
                               if F.get('actual_pct') is not None else None))])


def t07q13(F, role):
    """Contractor's update: is the delay real by P6 F9, and what logic/lag did they slip in?"""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Run the Consultant Review **before/after but-for**: strip the contractor's logic and lag changes, "
            "re-run the schedule through the P6 **F9** keystone, and see what delay actually survives. That is "
            "the only way to separate real slip from anything engineered into the update.")
    body = [
        "The method matters because it's forensic. You don't argue the contractor's narrative — you rebuild the "
        "network without their changes, let F9 recompute, and read the delay that remains. What survives is real; "
        "what disappears was carried by the edits.",
        _position_line(F),
        "One honesty line on the numbers: the finish position I read here is P6's own — the finish milestone's "
        "exported date against its baseline. What the Consultant Review adds is the but-for: how much of that "
        "slip survives once the contractor's changes are taken out. That surviving figure is the defensible one.",
        "On any logic/lag change table it produces: present it as **indicators** for the claims discussion. The "
        "tool shows cause and concurrency — it never says 'entitled'. Entitlement is a contractual determination, "
        "not a schedule output, and keeping that line clean is what makes your analysis credible.",
        _two_schedule_note("the before/after but-for"),
    ]
    return K.A(head, body,
               advice=["Rebuild without the contractor's changes and re-run F9 — report only the delay that survives.",
                       "Present the logic/lag change table as indicators of cause, never as an entitlement finding.",
                       K.go_deeper('Consultant Review', 'For the F9-exact before/after but-for')],
               evidence=[K.ev('P6', 'Finish slip', _kit_delay(F)),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('Out-of-sequence', 'On loaded schedule', F.get('oos_count'))])


def t07q14(F, role):
    """Update vs update: driving-path change this period and any overstated progress."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Update vs Update gives you the **period delta on the driving path** plus reported progress, and you "
            "cross-check earned value against what the work physically achieved — that's how you catch optimistic "
            "claiming.")
    body = [
        "The overstatement test is concrete: if reported EV ran ahead of what the critical-path activities "
        "actually did this window, that's your flag. Watch the driving front hardest — that's where a claimed "
        "percent that isn't physically there does the most damage to the forecast.",
        _progress_line(F) + " " + f"That leaves the schedule {K.spi_verdict(F)[0]} on pace (SPI ≈ "
        f"{K.ratio(F.get('spi'))}) — so there's little room for optimistic claiming without it showing up here.",
        _trend_line(F),
        (f"Also review the **{F['oos_count']} out-of-sequence** activities on this update — work progressed "
         "against its logic can make period progress read better than it truly is, because earned value lands "
         "before its predecessors are complete."
         if F.get('oos_count') else
         "Out-of-sequence progress is one of the main ways a period can read better than it is; the loaded "
         "update looks clean on that front, which supports the reported numbers."),
        "The period-over-period driving-path delta itself needs **last month's update loaded alongside this one** "
        "— that comparison is what Update vs Update computes; a single snapshot gives me this period's position "
        "but not the movement.",
    ]
    return K.A(head, body,
               advice=["Cross-check reported EV against physical progress on the driving-path activities specifically.",
                       "Load last month's update to quantify the period delta to the day.",
                       K.go_deeper('Update vs Update', 'For the period delta on the driving path')],
               evidence=[K.ev('EVM', 'Actual vs planned',
                              (f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"
                               if F.get('actual_pct') is not None else None)),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('Out-of-sequence', 'Activities', F.get('oos_count'))])


def t07q15(F, role):
    """GAP — change-order authorisation, edit authorship, and schedule-spec compliance."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Honest answer: the tool can't ground this one. It compares **end-states** — what changed between two "
            "schedules — not whether each change was **authorised**, **who** made it, **when**, or whether the "
            "revision meets your **schedule specification**.")
    gap = K.gap_note('GAP — no change-order link, edit attribution, or contract-spec model')
    body = [
        gap or "The schedule file doesn't carry change-order links, per-edit authorship, or a model of the client's "
               "spec, so I won't manufacture any of it.",
        "To answer it properly I'd need three things the P6 export doesn't reliably hold: a **change-order / "
        "approval link per change**, **per-edit author-and-timestamp** audit data (P6 exports don't carry a "
        "dependable edit history), and a **machine-readable model of the client's schedule spec** to test the "
        "revision against. None of those live in the schedule.",
        "What I can still give you is the change set itself. " + _position_line(F),
        "So the workflow is a hybrid: run the Baseline Revision Comparison to get every material change listed, "
        "then reconcile each one **by hand** against your change register and correspondence log — the comparison "
        "tells you *what* changed, and your project records tell you *whether it was allowed*.",
    ]
    return K.A(head, body,
               advice=["Run the comparison for the material changes, then reconcile each against your change register and the spec manually.",
                       K.go_deeper('Baseline Revision Comparison', 'For the list of material changes to reconcile')],
               evidence=[K.ev('Baseline Revision', 'Finish position', _kit_delay(F)),
                         K.ev('Baseline Revision', 'Current activities', (f"{int(F['activity_count']):,}" if F.get('activity_count') else None))])


# ── grounded fragment helpers used above ───────────────────────────────────────

def _crit_line(F):
    """A grounded sentence on the loaded schedule's critical structure, or ''."""
    dp = F.get('driving_path_count')
    cc = F.get('cpli_critical_count')
    g = F.get('cpli_grade')
    bits = []
    if K.chain_facts(F):
        bits.append(f"a **{K.chain_facts(F)[0]}-activity chain** setting the finish")
    elif dp:
        bits.append(f"about **{dp}** activities flagged as driving (a set, not one line)")
    if cc:
        bits.append(f"**{cc}** at critical or negative float")
    if not bits:
        return ''
    tail = f", graded **{g}** for critical-path health" if g else ""
    return "the loaded schedule shows " + _join(bits) + tail + "."


def _float_line(F):
    """A grounded sentence on the loaded schedule's float distribution, or ''."""
    bits = []
    if F.get('neg_float_count'):
        bits.append(f"**{F['neg_float_count']}** activit{'y' if F['neg_float_count'] == 1 else 'ies'} on negative total float"
                    + (f" ({K.pct(F.get('neg_float_pct'))})" if F.get('neg_float_pct') is not None else ""))
    if F.get('max_float') is not None:
        bits.append(f"a maximum total float of about **{K.wd(F.get('max_float'))}**")
    if F.get('avg_float') is not None:
        bits.append(f"an average of about **{K.wd(F.get('avg_float'))}**")
    if not bits:
        return ''
    g = F.get('float_grade')
    tail = f" — float health graded **{g}**" if g else ""
    return "The loaded schedule carries " + _join(bits) + tail + "."


def _trend_line(F):
    tr = F.get('trend')
    if tr and tr.get('prev_delay') is not None and tr.get('delta') is not None:
        delta = tr.get('delta')
        direction = tr.get('direction')
        move = ('a further **' + K.wd(delta) + '** of slip' if (delta or 0) > 0 else
                ('a recovery of **' + K.wd(delta) + '**' if (delta or 0) < 0 else 'no net change'))
        return (f"Where I do have both points, the delay to completion moved from {K.wd(tr.get('prev_delay'))} to "
                f"{K.wd(F.get('delay_days'))} — {move} between the two updates "
                f"({'worsening' if direction == 'worse' else ('improving' if direction == 'better' else 'flat')}).")
    return ("To measure this period against the last I need last month's update loaded too — Update vs Update reads "
            "the movement between two snapshots, and I won't invent a prior figure I don't hold.")


ANSWERS = {
    't07q00': t07q00, 't07q01': t07q01, 't07q02': t07q02, 't07q03': t07q03,
    't07q04': t07q04, 't07q05': t07q05, 't07q06': t07q06, 't07q07': t07q07,
    't07q08': t07q08, 't07q09': t07q09, 't07q10': t07q10, 't07q11': t07q11,
    't07q12': t07q12, 't07q13': t07q13, 't07q14': t07q14, 't07q15': t07q15,
}
