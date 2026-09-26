"""Theme 13 — Constructability & Knowledge Base.

Whether the plan is buildable, safe to build, and complete — judged against construction
reality and the project-type playbooks, not just P6 arithmetic. F9 will happily schedule a
slab before its formwork; only a read against real build logic exposes it. Every answer is
grounded in FACTS (the finish position, the weighted driving front, and the logic-quality
audit signals — out-of-sequence, dangling links, open ends) and points to the feature that
carries the detail (the Constructability Review and the Construction Knowledge Base). Where
the tool genuinely can't compute a thing — HSE hold-points, permit-to-work windows — the
answer says so plainly and gives the manual planning read instead of inventing a number.
"""
from . import _kit as K


def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can answer this "
              "from your own numbers — offline, nothing leaves your PC."])


# ── shared, F-grounded helpers (None-safe) ──────────────────────────────────────

def _delay_chip(F):
    """Signed delay chip value, e.g. '+60 wd (behind)' / '-12 wd (ahead)' / 'on date'."""
    d = F.get('delay_days')
    if d is None:
        return None
    d = round(d)
    if d > 0:
        return f"+{d} wd (behind)"
    if d < 0:
        return f"{d} wd (ahead)"
    return "on date"


def _driver_name(F):
    driver = K.main_driver(F)
    return driver.get('name') if driver else None


def _finish_is(F):
    """Clause '<subject> is <finish position>' that stays grammatical even when the finish
    milestone can't be derived — safe to drop after a subject noun or a dash. Never yields the
    broken 'the project is the finish milestone isn't derivable' form."""
    if F.get('delay_days') is None:
        return "the finish milestone isn't derivable from this file yet"
    return f"the project is {K.delay_phrase(F)}"


def _disc_count(F):
    ds = F.get('disciplines') or []
    return len(ds) if ds else None


def _logic_signal_line(F):
    """Corroborating logic-audit signals for the 'illogical ties' read — honest when clean."""
    bits = []
    oos = F.get('oos_count')
    if oos:
        bits.append(f"**{oos} activities** progressed out of sequence ({K.pct(F.get('oos_pct'))})")
    dang = F.get('dangling_count')
    if dang:
        bits.append(f"**{dang} dangling links** tied at only one end")
    oe = F.get('open_ends')
    if oe:
        bits.append(f"**{oe} open ends** with no predecessor or successor")
    if not bits:
        return ("Your logic-quality audit is clean on the structural checks, so the constructability "
                "flags will be about build *sequence* — a tie in the wrong physical order — rather than "
                "broken links. Read them on their own merit.")
    return ("You don't have to take this on faith — the logic audit already shows the network straining "
            "where build reality bites: " + ", ".join(bits) + ". Out-of-sequence in particular is often "
            "a tie that doesn't match how the crews actually built it, so treat those as the first "
            "constructability suspects.")


def _continuity_signal_line(F):
    """The network's own tell that continuity is broken (open ends / dangling)."""
    oe = F.get('open_ends')
    dang = F.get('dangling_count')
    parts = []
    if oe:
        parts.append(f"**{oe} open ends** — activities with no predecessor or successor at all")
    if dang:
        parts.append(f"**{dang} dangling links** ({K.pct(F.get('dangling_pct'))}) tied at only one end")
    if parts:
        return ("The logic audit already shows continuity holes you can see today: " + " and ".join(parts)
                + ". Each one is a spot where the sequence hands off to nothing — the classic fingerprint "
                "of an activity that should be sitting in the gap.")
    return ("The structural continuity checks (open ends, dangling links) come back clean, so any gap the "
            "review finds will be a *missing real-world step* rather than a torn link — still worth adding, "
            "but the network isn't obviously broken.")


def _wbs_structure_line(F):
    """Reflect the schedule's current top-level split back so the WBS read is grounded."""
    ds = sorted(F.get('disciplines') or [], key=lambda d: (d.get('weight') or 0), reverse=True)
    if not ds:
        return ("I can't see a discipline/category breakdown in this file, so I can't judge how your "
                "branches roll up — load a WBS-coded schedule and the review can map it to the reference.")
    top = ds[:5]
    listed = "; ".join(f"**{d.get('name')}** ~{round((d.get('weight') or 0) * 100)}% by weight" for d in top)
    tail = "" if len(ds) <= 5 else f" (plus {len(ds) - 5} more)"
    return ("Your current top-level split reads as: " + listed + tail + ". Sanity-check that each of those "
            "is one buildable work front and not two glued together — that gluing is where roll-up quietly "
            "lies.")


# ── answers ─────────────────────────────────────────────────────────────────────

def t13q00(F, role):
    """Relationships that make no construction sense — each flagged with a reason."""
    if not F.get('ok'):
        return _no_project(F)
    dn = _driver_name(F) or 'your driving work front'
    dl = K.driver_line(F)
    head = ("**Yes — that's exactly what the Constructability Review is for.** It reads your logic against "
            "the Construction Knowledge Base and flags ties that calculate fine but can't be built that "
            "way, each with a plain reason.")
    body = [
        "The distinction is the whole point. The **Schedule Audit** catches links that are *structurally* "
        "wrong — a start-to-finish tie, a circular loop, an excessive lead that pulls a successor back "
        "before its driver. The **Constructability Review** catches links that are *valid in P6 but "
        "physically impossible* — a slab poured before its formwork, a finish trailing a start it can't "
        "overlap, two trades stacked in one footprint. F9 will happily schedule every one of those; only a "
        "read against real build logic exposes them.",
        ((f"Scrub the driving chain first. {dl} A single wrong overlap or SS lag on that front is the one "
          f"flattering your finish — {_finish_is(F)}, so a tie that shortens the driver "
          "by mistake is hiding real slip, not saving it.")
         if dl else
         (f"Scrub the driving chain first — {_finish_is(F)}, so any tie that shortens "
          "the driving work by mistake is hiding real slip, not saving it.")),
        _logic_signal_line(F),
        "Honest limit: the per-relationship flags and their reasons come out of the Constructability "
        "feature, not the numbers I'm holding in this read — I can tell you where to point it and which "
        "chain to start on, not recite each tie for you.",
    ]
    advice = [
        f"Start the review on the **{dn}** chain — that's where a bad tie does the most damage to the "
        "finish.",
        K.go_deeper('Constructability Review', 'To get each illogical tie with its reason'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Constructability', 'Driving front to scrub first', dn),
                         K.ev('Out-of-sequence', 'Activities out of order', F.get('oos_count')),
                         K.ev('Dangling', 'One-ended logic links', F.get('dangling_count'))])


def t13q01(F, role):
    """Missing construction activities that break the continuity of the logic."""
    if not F.get('ok'):
        return _no_project(F)
    ac = F.get('activity_count')
    head = ("**It flags gaps in the build sequence — construction and execution steps only, never "
            "engineering or procurement.** Those connective activities are the ones planners quietly "
            "drop, and they're what makes a path look shorter than it really is.")
    body = [
        "Think of the steps that never earn their own line but still take time on site: cure-and-strip "
        "before the next lift, testing and commissioning checks, setting-out and survey, temporary works "
        "struck before follow-on trades, protection and handover. When those are missing the logic "
        "*reads* continuous but the crews can't actually flow that way.",
        _continuity_signal_line(F),
        (f"This matters before you trust any date — {_finish_is(F)}. If the completeness check adds "
         "real steps back, the honest finish moves the wrong way — later, not earlier. Add them, then "
         "re-run F9 so the date reflects the full build and not a trimmed one."),
        "Scope caveat, deliberately: the missing-activity check stays on construction and execution work. "
        "It won't invent design or procurement lines — that isn't where a builder loses continuity, and "
        "guessing there would just be noise.",
    ]
    advice = [
        "Add the flagged steps, then re-run the forward pass before you quote the finish to anyone.",
        "Pair this with the recovery question — the same missing steps can eat the very float your "
        "acceleration levers think they're buying.",
        K.go_deeper('Constructability Review', 'To list the missing steps on your own schedule'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Open ends', 'Activities with a loose end', F.get('open_ends')),
                         K.ev('Dangling', 'One-ended links', F.get('dangling_count')),
                         K.ev('Schedule', 'Activities in the file', ac)])


def t13q02(F, role):
    """Is the WBS sound for this project type?"""
    if not F.get('ok'):
        return _no_project(F)
    dl = K.driver_line(F)
    head = ("The Constructability Review checks your WBS against the project-type structure in the "
            "Knowledge Base — and the real test isn't tidiness, it's whether progress and cost roll up "
            "cleanly, branch by branch, so each work front can be read on its own.")
    body = [
        ("A sound WBS on a cost-loaded EVM job is what lets the numbers tell the truth. If two different "
         "work fronts share a branch, their progress averages together and the category read blurs. Your "
         f"headline is **{K.pct(F.get('actual_pct'))}** actual against **{K.pct(F.get('planned_pct'))}** "
         "planned — and that split is only trustworthy if the branches underneath it are clean."),
        _wbs_structure_line(F),
        ((f"Here's the practical test on this schedule: {dl} If that front isn't its own clean branch, you "
          "can't isolate it from the work that's on plan — and isolating it is the whole diagnosis this "
          "week.")
         if dl else
         "The practical test: can you point to the single branch carrying your slip without other work "
         "diluting it? If not, the WBS is fighting your diagnosis rather than supporting it."),
        "What the review won't do is redesign your WBS for you — it tells you where your structure "
        "diverges from the reference and where the roll-up will mislead, and you make the call.",
    ]
    advice = [
        "Keep each major work front on its own branch so weight × gap points at one owner, not an average.",
        K.go_deeper('Construction Knowledge Base', 'For the reference WBS to compare against'),
        K.go_deeper('Constructability Review', 'To check your structure against it'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Overall actual vs planned',
                              f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('EVM', 'Categories in the roll-up', _disc_count(F))])


def t13q03(F, role):
    """KB Project-Type Playbook — sequence, suggested WBS, and a starter baseline for P6."""
    if not F.get('ok'):
        return _no_project(F)
    ac = F.get('activity_count')
    head = ("The **Knowledge Base Project-Type Playbook** gives you exactly that: the standard "
            "construction sequence for your project type, a suggested WBS, and a downloadable starter "
            "XER/XML you copy straight into P6.")
    body = [
        "The playbook is type-first. You pick the project type and it lays out the reference build order "
        "— the physical dependencies a seasoned builder would never break — with a WBS shaped so progress "
        "and cost roll up sensibly, and a skeleton schedule you can import and flesh out.",
        ((f"The best use of it here isn't a blank-page start — you already have a schedule of about "
          f"**{int(ac):,} activities**. Lay the playbook alongside your logic as a *completeness "
          "checklist*: it's how you catch the missing construction steps and the out-of-real-order ties "
          "that the other two checks flag.")
         if ac else
         "Lay the playbook alongside your own logic as a completeness checklist — it's the fastest way to "
         "see which reference steps and physical dependencies your schedule is missing."),
        "One honest note on scope: the playbook is a reference *skeleton* keyed to the project type, not a "
        "bespoke baseline for your contract. It won't know your quantities, your calendars or your "
        "sectional dates — treat it as the frame, then hang your real durations and resources on it.",
    ]
    advice = [
        "Import the starter, then reconcile it against your live logic step by step — adopt what's "
        "missing, keep what's yours.",
        K.go_deeper('Construction Knowledge Base', 'For the sequence, WBS and starter baseline'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Knowledge Base', 'Starter output', 'sequence + WBS + XER/XML'),
                         K.ev('Schedule', 'Activities to check against', ac)])


def t13q04(F, role):
    """Re-sequence to overlap Area B before Area A finishes — is it constructable?"""
    if not F.get('ok'):
        return _no_project(F)
    dn = _driver_name(F) or 'the driving front'
    dl = K.driver_line(F)
    head = ("**Answer it in two moves, in this order.** First model the overlap in the What-if engine to "
            "see the days it actually buys; then run that re-sequenced logic back through the "
            "Constructability Review to confirm it can physically be built. Time first, then buildability "
            "— never the other way round.")
    body = [
        "The What-if gives you an instant estimate and then the P6-exact figure via a build → F9 "
        "round-trip, so the days you'd save are real, not a guess. But days on paper mean nothing if the "
        "overlap can't be built: two fronts in one footprint means shared access, crane positioning and "
        "trade stacking — the constructability check is what tells you whether Area B can start while "
        "Area A is still live, or whether the crews would simply foul each other.",
        ((f"Set expectations on the payback. Overlapping only helps if you overlap the work that actually "
          f"drives the finish. On this schedule that's **{dn}** — {dl} If Area A/B isn't on that chain, "
          "the re-sequence buys you float on a path that already has some, and the finish barely moves.")
         if dl else
         "Set expectations: overlapping only helps if you overlap the work that actually drives the "
         "finish. If these areas aren't on the driving chain, you'll buy float on a path that already has "
         "it and the finish barely moves."),
        "And it has to survive real constraints — single-front working, one crane, one laydown. That's "
        "usually why an aggressive overlap returns far less than the arithmetic promises: the resource or "
        "access limit caps it. Prove it's buildable before you commit it to the recovery plan.",
    ]
    advice = [
        "Model it in the What-if first, read the P6-exact days, THEN constructability-check the winning "
        "option — don't commit an overlap you haven't proven buildable.",
        K.go_deeper('What-if / scenario engine', 'To size the days the overlap buys'),
        K.go_deeper('Constructability Review', 'To confirm the overlap is physically buildable'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('What-if', 'Method', 'estimate → build → F9 (P6-exact)'),
                         K.ev('Constructability', 'Front to overlap', dn),
                         K.ev('EVM', 'Finish now', _delay_chip(F))])


def t13q05(F, role):
    """Missing activities that, once added, would eat the recovery you think you have."""
    if not F.get('ok'):
        return _no_project(F)
    dn = _driver_name(F) or 'the driving front'
    dl = K.driver_line(F)
    head = ("**This is the one that catches teams out.** Every recovery lever you test — night shift, "
            "extra crew, an overlap — assumes the schedule is complete. If the completeness check finds "
            "missing construction steps, adding them back can swallow part of that recovery before you "
            "even start.")
    body = [
        "The trap is sequencing your own analysis wrong. Test the levers first and they'll show a gain; "
        "then you add the missing cure times, pre-assembly and commissioning checks, and "
        "half the gain evaporates because those steps sit right on the path you were accelerating. You "
        "end up reporting a recovery you can't actually deliver.",
        _continuity_signal_line(F),
        ((f"So do it in order: run the constructability completeness check, add the real activities, "
          f"re-run F9 for the honest finish, and *then* test the levers against that. On this schedule the "
          f"levers have to move **{dn}** to matter — {dl} Accelerating a schedule that's already "
          "optimistic just moves the disappointment to the next update.")
         if dl else
         "So do it in order: run the completeness check, add the real activities, re-run F9 for the honest "
         "finish, and *then* test the levers against that. Accelerating a schedule that's already "
         "optimistic just moves the disappointment to the next update."),
        "It ties straight back to the earlier checks: the missing-activity flag (continuity) and the "
        "what-if buildability test are the same discipline applied *before* you promise a date, not "
        "after.",
    ]
    advice = [
        "Complete the schedule first, re-baseline the forecast, THEN test recovery — never the reverse.",
        "Re-test each lever against the *completed* logic so the reported gain is one you can hold.",
        K.go_deeper('Constructability Review', 'To find the missing steps before you plan recovery'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Open ends', 'Continuity gaps', F.get('open_ends')),
                         K.ev('Dangling', 'One-ended links', F.get('dangling_count')),
                         K.ev('Constructability', 'Front recovery must move', dn)])


def t13q06(F, role):
    """GAP — safety-critical sequencing and permit hold-points (no HSE-aware analysis)."""
    if not F.get('ok'):
        return _no_project(F)
    grounds = ('Constructability Review + Construction Knowledge Base (partial) '
               '— GAP: no HSE-aware / hold-point analysis')
    dn = _driver_name(F) or 'your driving fronts'
    head = ("**I won't fake a number on this one.** The Constructability Review will catch missing or "
            "out-of-order safety *sequencing* — scaffold used before its inspection, say — but there's no "
            "HSE-aware model of hold-points, permit-to-work windows, confined-space entry or heavy-lift "
            "exclusions in the tool yet.")
    body = [
        K.gap_note(grounds),
        "Why it matters: these are real schedule drivers, not paperwork. A scaffold has to be erected, "
        "then inspected and tagged before anyone works off it; a confined-space entry needs its permit "
        "and standby; a heavy lift closes an exclusion zone that stops the trades around it. Under "
        "schedule pressure these are exactly the durations that get quietly compressed toward zero — and "
        "the plan then reads buildable when it isn't.",
        (f"Until the tool models it, check it by hand where the pressure is highest — the **{dn}** chain, "
         f"because {_finish_is(F)} and that's the front where someone will be tempted to squeeze an "
         "inspection or a permit window to claw days back. Walk that path activity by activity and confirm "
         "each hold-point still has its time."),
        "To close the gap properly the tool would need a permit-and-hold-point model tied to activity "
        "types — erect-then-inspect pairs, permit lead times, exclusion windows — so it could flag a "
        "safety sequence that's been compressed away. That's a real feature, not a today answer, and I'd "
        "rather say so than dress up a guess.",
    ]
    advice = [
        f"Manually walk the **{dn}** path for erect-then-inspect, permits and lift exclusions before you "
        "sign off the sequence.",
        K.go_deeper('Constructability Review', 'For the safety-sequencing checks it can do today'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Constructability', 'Path to check by hand', dn),
                         K.ev('EVM', 'Finish pressure', _delay_chip(F))])


ANSWERS = {
    't13q00': t13q00, 't13q01': t13q01, 't13q02': t13q02, 't13q03': t13q03,
    't13q04': t13q04, 't13q05': t13q05, 't13q06': t13q06,
}
