"""Theme 14 — Claims, EOT & FIDIC.

Delay-entitlement *indicators*, forensic method selection and but-for analysis — never a
statement of entitlement. This is the theme where honesty matters most: the P6 file reads
schedule dates and critical-path movement, it does NOT read cause. So every answer here draws
a hard line — the schedule can show *where* the finish is slipping, *which* front is carrying
it and *when* the slip accrued, but whether a delay is owner-caused or your own, excusable or
culpable, compensable or time-only, is a causation and contract judgement that belongs to your
claims consultant, contracts manager and commercial team against your correspondence and the
signed contract. Two more standing caveats run through the theme: the delay figure the tool
holds is an EVM-side re-derivation (day-accurate on a progressed plan, but the claim-grade
quantum is the P6 F9 critical-path position from the Consultant Review but-for run), and CPI
here is a schedule echo, never an independent money signal. Everything is grounded in FACTS
(the finish position, the weighted driving front, progress-by-discipline, the logic-quality
audit) and routes the deep dive to the feature that carries it. The word 'entitled' never
appears as a verdict — only ever as the thing the tool deliberately does NOT decide.
"""
from . import _kit as K


def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can give you the "
              "schedule-based delay indicators — offline, nothing leaves your PC. I'll be clear about "
              "what's an indicator and what's a causation call only you and your claims consultant can make."])


# ── shared, F-grounded helpers (None-safe, no import side effects) ────────────────

def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _behind(F):
    d = _num(F.get('delay_days'))
    return d is not None and d > 0


def _ahead(F):
    d = _num(F.get('delay_days'))
    return d is not None and d < 0


def _delay_chip(F):
    """Signed delay chip value, e.g. '+60 wd (behind)' / '-12 wd (ahead)' / 'on date'."""
    d = _num(F.get('delay_days'))
    if d is None:
        return None
    d = round(d)
    if d > 0:
        return f"+{d} wd (behind)"
    if d < 0:
        return f"{d} wd (ahead)"
    return "on date"


def _driver_name(F):
    d = K.main_driver(F)
    return d.get('name') if d else None


def _driver_phrase(F):
    return _driver_name(F) or "the driving work front"


def _finish_is(F):
    """Clause '<subject> is <finish position>' that stays grammatical even when the finish
    milestone can't be derived — safe after a subject noun or a dash."""
    if F.get('delay_days') is None:
        return "the finish milestone isn't derivable from this file yet"
    return f"the finish is {K.delay_phrase(F)}"


def _ranked_drivers(F):
    """Disciplines dragging the finish, ranked by weight × gap (not raw gap)."""
    scored = []
    for d in (F.get('disciplines') or []):
        gap = _num(d.get('gap')) or 0
        wgt = _num(d.get('weight')) or 0
        if gap <= 0:
            continue
        scored.append((gap * wgt, d))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [d for _, d in scored]


def _second_front_line(F):
    """A sentence naming the near-critical front behind the driver, or ''."""
    ranked = _ranked_drivers(F)
    if len(ranked) < 2:
        return ''
    d = ranked[1]
    return (f"The nearest front behind it is **{d.get('name')}** ({d.get('actual')}% done vs "
            f"{d.get('planned')}% planned, ~{round((d.get('weight') or 0) * 100)}% of the project by "
            "weight) — near-critical, not yet co-critical, the one to watch for a second overlapping delay.")


def _gap_points(F):
    p, a = _num(F.get('planned_pct')), _num(F.get('actual_pct'))
    if p is None or a is None:
        return None
    return round(p - a)


def _no_delay_line(F, what):
    """Honest baseline sentence when the schedule shows no critical slip to work from."""
    d = _num(F.get('delay_days'))
    if d is None:
        return ("First, the honest baseline: I can't derive a finish slip from this file — there's no finish "
                "milestone I can measure against a baseline — so there's no schedule indicator to "
                f"{what} yet. Load a progressed update with a finish milestone and it falls out here.")
    if d <= 0:
        return (f"First, the honest baseline: on today's update {_finish_is(F)}, so the schedule isn't "
                f"showing a critical slip to {what}. Everything below is how the tool would read one the "
                "moment a front goes negative and the finish starts moving past the baseline.")
    return ''


def _both_sides(F):
    """When the file carries late client inputs, the schedule shows evidence on BOTH sides — never call the
    slip contractor-side on the schedule face. '' when the file shows no late client input."""
    if not K.late_inputs(F):
        return ''
    c = K.chain_facts(F)
    own = ("the chain that sets the finish hasn't started yet" if c and c[1] == 0 else
           "the work that sets the finish is behind its plan")
    return ("The file shows evidence on **both sides**. **Employer side:** " + K.inputs_line(F) + " Each is a "
            f"potential delay event that needs a notice on record. **Contractor side:** {own}. What one update "
            "can't show is which of the two actually held the finish — that takes a time-impact analysis.")


def _indicator_caveat():
    return ("Stated plainly, because it's the whole point of this theme: this is a schedule-based "
            "**indicator**, never a statement of entitlement. The file reads dates and critical-path "
            "movement — it cannot see cause. Cause lives in your drawings, RFIs, access records and "
            "correspondence, and turning an indicator into a claim is your claims consultant's call, not "
            "the schedule's.")


# ── answers ───────────────────────────────────────────────────────────────────────

def t14q00(F, role):
    """EOT indicators present, and are they owner-caused or my own?"""
    if not F.get('ok'):
        return _no_project(F)
    if _behind(F):
        head = ("The tool shows schedule-based EOT **indicators**, never entitlement — and today there is a "
                f"real slip to look at: {_finish_is(F)}.")
    else:
        head = ("The tool shows schedule-based EOT **indicators**, never entitlement — and today the "
                "schedule isn't showing a critical slip to build one on.")
    body = []
    if _behind(F):
        dl = K.driver_line(F)
        both = _both_sides(F)
        body.append(f"The headline indicator is genuine — {_finish_is(F)} — a measured slip on the work that sets "
                    "the finish, not yet a claim." + (" " + dl if dl else ''))
        if both:
            body.append("Here's the split you asked for — owner-caused versus your own. " + both)
        else:
            body.append(
                "Here's the split you asked for — owner-caused versus your own — and the honest answer is that "
                "the schedule can't settle it. It shows *where* the finish is slipping and *which* front carries "
                "it; it can't see *why*. Late drawings, RFI turnaround, access, permits and free-issue materials "
                "only show in P6 if they're programmed as activities — this file doesn't show any of them late, so "
                "on the schedule face the slip sits with the front doing the work.")
        body.append(
            "So treat this as an indicator to test, not a claim to file. Overlay your causation record against "
            "these dates with your claims consultant: where an employer event held the work that sets the "
            "finish, that part is excusable — possibly compensable; where nothing did, it's your own slip.")
    else:
        body.append(_no_delay_line(F, 'support an EOT indicator'))
        body.append(
            "No delay on the driving path means no schedule-based entitlement indicator today — which is "
            "the honest read, not a negative one. If a front goes negative and the finish starts moving "
            "past the baseline, the tool will surface the indicator here.")
        body.append(
            "The responsibility question — owner-caused versus your own — is the same causation call in "
            "either case: the schedule points at the front carrying the slip, your claims consultant "
            "decides cause against your correspondence. The file never decides that on its own.")
        dl = K.driver_line(F)
        if dl:
            body.append("The front to keep an eye on, if the picture turns, is the one already showing the "
                         "most pressure: " + dl)
    advice = [
        "Before anything goes to the client, line your causation evidence (drawings, RFIs, access, permits, "
        "free-issue) up against these schedule dates with your claims consultant.",
        K.go_deeper('Claims / TIA reference, Consultant Review',
                    'For the finish-slip decomposition and the delay-method reference'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Delay indicator', _delay_chip(F)),
                         K.ev('Critical Path Analyzer', 'Front carrying the slip', _driver_name(F)),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish'))])


def t14q01(F, role):
    """Which delay-analysis method fits — TIA, windows, as-planned vs as-built."""
    if not F.get('ok'):
        return _no_project(F)
    ap = _num(F.get('actual_pct'))
    dd = F.get('data_date')
    prog = K.pct(F.get('actual_pct'))
    if ap is None:
        state, method = ('unreadable',
                         "I can't read how far progressed this update is, so I can't match a method to the "
                         "as-built completeness yet — load a progressed update and the fit falls straight out.")
    elif ap < 15:
        state, method = ('very early',
                         "you're early, with little as-built to work with, so a retrospective as-planned vs "
                         "as-built isn't available yet. The fit for anything unfolding now is a **prospective "
                         "Time-Impact Analysis (TIA)** — an impacted-as-planned fragnet run through P6 F9 for "
                         "the expected impact of a live event.")
    elif ap < 85:
        state, method = ('mid-execution',
                         "you're mid-execution — real as-built to the data date, but the job isn't finished, "
                         "so a full as-planned vs as-built can't be completed. The natural fit is a **windows "
                         "/ time-slice** analysis, update-to-update, retrospective on the periods already run, "
                         "with a **prospective TIA fragnet** for any event still live.")
    else:
        state, method = ('near complete',
                         "you're near complete — enough as-built now that a **retrospective as-planned vs "
                         "as-built** becomes viable as the primary method, with a windows analysis over the "
                         "updates to place *when* each slice of the slip accrued.")
    head = (f"On progress alone you're **{state}** (about **{prog}** complete"
            + (f" at the {dd} data date" if dd else "") + f") — so {method}")
    body = [
        "The method follows the data, and the single biggest driver is how much genuine as-built you have. "
        "A method that needs a finished job (a clean as-planned vs as-built) can't be run mid-execution; a "
        "purely prospective method wastes the real progress you've already recorded. Matching the two is "
        "what keeps the analysis defensible.",
        ("The windows approach is usually the workhorse mid-job: each update becomes a slice, and you "
         "measure the critical-path movement inside each one, so you isolate *when* the slip accrued instead "
         "of arguing it as one global lump. A prospective TIA fragnet then handles anything still unfolding "
         "at the data date — you model the event and read the finish impact before it fully lands."
         if (ap is not None and 15 <= ap < 85) else
         "Whatever the fit, the tool grounds the schedule evidence the method needs — the update-to-update "
         "movement for windows, the impacted-as-planned run for a TIA, the planned/earned/actual overlay for "
         "an as-planned vs as-built."),
        "Honest boundary: the tool selects the method to the *data*, not to your *contract*. Some contracts "
        "or Particular Conditions specify or favour a method, and forums have their preferences — confirm "
        "the final choice with your claims consultant against the contract. The tool then grounds the "
        "schedule evidence for whichever they pick.",
    ]
    return K.A(head, body,
               advice=[
                   "Fix the method with your claims consultant against the contract first; then let the tool "
                   "assemble the schedule evidence it needs.",
                   K.go_deeper('Consultant Review', 'For the forensic but-for run behind whichever method'),
                   K.go_deeper('Claims / TIA reference', 'For the method reference (AACE 29R-03 / FIDIC)'),
               ],
               evidence=[K.ev('EVM', 'Progress', prog),
                         K.ev('EVM', 'Data date', dd),
                         K.ev('EVM', 'Delay indicator', _delay_chip(F))])


def t14q02(F, role):
    """Excusable versus culpable — attribute the driving delay."""
    if not F.get('ok'):
        return _no_project(F)
    both = _both_sides(F)
    if _behind(F):
        head = ("It can't be called either way from this file: there's excusable (employer-side) evidence and a "
                "contractor-side shortfall — splitting them needs a time-impact analysis." if both else
                "On the schedule alone this reads **culpable** (contractor-side) — but that's an indicator, "
                "not a verdict, because the file can't see cause.")
    else:
        head = "There's no driving delay on today's schedule to classify — so nothing to call excusable or culpable yet."
    body = []
    if _behind(F):
        dl = K.driver_line(F)
        body.append(
            (dl + " " + both) if both else
            (dl + " With the shortfall concentrated on the governing work front and no late client input in the "
             "file, the schedule face points to a contractor-side, culpable read."
             if dl else
             f"The slip sits on the governing work front — {_finish_is(F)} — with no late client input in the "
             "file, so the schedule face points to a contractor-side, culpable read."))
        body.append(
            "How it resolves: for each late client input, show when it actually held the work that sets the "
            "finish. The days it held are **excusable**; the days the chain lost for other reasons are "
            "**culpable**; where both ran at once it's concurrent — the dates don't change, the attribution does."
            if both else
            "But read the label carefully: 'culpable on the schedule face' is not 'culpable in fact'. The "
            "file reads dates, not reasons. If late employer information, permits, access or free-issue "
            "actually drove that front, the same slip is **excusable** — the schedule dates don't change, "
            "the attribution does.")
        body.append(
            "That's the causation overlay only you can supply: line your records against these dates. A "
            "neutral event — exceptional weather, for instance — reads excusable too but points nowhere near "
            "contractor fault; the Weather tab tests that share against the site-type norms."
            + ("" if both else " Everything else needs your correspondence to move the label off the front doing "
               "the work."))
    else:
        body.append(_no_delay_line(F, 'attribute to an excusable or culpable cause'))
        body.append(
            "When a driving delay does appear, the tool will point at the front carrying it and whether an "
            "employer event sits on that path — that's the excusable/culpable *indicator*. The label itself "
            "is a causation judgement your claims consultant makes against your records, never one the "
            "schedule can settle.")
        body.append(
            "Keep the principle ready for when it turns: the same schedule dates read culpable or excusable "
            "depending only on cause. A neutral event like exceptional weather is excusable but nobody's "
            "fault; an employer act is excusable and points at the employer; a shortfall you couldn't staff "
            "is culpable. The dates don't move — the attribution does, and only your causation record moves it.")
    return K.A(head, body,
               advice=[
                   "Overlay your causation record (employer information, permits, access, free-issue) against "
                   "the driving-front dates before you attach any label.",
                   K.go_deeper('Consultant Review', 'For the forensic but-for read of the driving path'),
                   K.go_deeper('Weather Impact', 'To carve out any neutral (weather) share'),
               ],
               evidence=[K.ev('Critical Path Analyzer', 'Front carrying the delay', _driver_name(F)),
                         K.ev('EVM', 'Delay indicator', _delay_chip(F)),
                         K.ev('EVM', 'Finish', F.get('forecast_finish'))])


def t14q03(F, role):
    """Money claim or just time — compensable versus excusable."""
    if not F.get('ok'):
        return _no_project(F)
    both = _both_sides(F)
    if _behind(F):
        head = ("That split turns on **cause type**. This file shows compensable candidates — late client inputs "
                "(employer risk: time *and* money) — but whether they held the finish needs a time-impact analysis."
                if both else
                "That split turns entirely on **cause type**, and the tool only indicates — today nothing on "
                "the schedule face points to a compensable (employer-risk) cause.")
    else:
        head = "There's no driving delay on today's schedule, so there's nothing yet that's either compensable or excusable."
    body = []
    if _behind(F):
        dl = K.driver_line(F)
        body.append(
            "Three buckets, and cause decides which one you're in. **Compensable** = employer-risk event "
            "(time *and* money). **Excusable, non-compensable** = neutral event like exceptional weather "
            "(time, no money). **Culpable** = your own (neither). The schedule can flag which front is "
            "slipping; only the cause behind it decides the bucket.")
        body.append(
            both if both else
            (dl + " That slip traces to your own execution front with no late client input in the file, so on "
             "the schedule face nothing points to a compensable cause — it reads as contractor performance, "
             "which is time-and-money-on-you, not on the employer."
             if dl else
             f"The slip traces to the governing work front — {_finish_is(F)} — with no late client input in the "
             "file, so on the schedule face nothing points to a compensable cause."))
        body.append(
            "It moves if the evidence moves it: prove an employer act (late access, a variation, "
            "late free-issue) drove that front and it shifts toward **compensable**; a neutral event like "
            "exceptional weather reads **excusable-only** — time relief, not money. The schedule supports "
            "the *time* picture; the *money* picture is your commercial and claims team's call.")
        body.append(
            ("And ignore CPI for this — in this file actual cost equals earned value, so CPI is 1.00 by "
             "construction and says nothing about money. " if F.get('cost_derived') else
             "And keep CPI out of this — ") +
            "Compensability is a cause-and-contract question, not a cost-ratio one.")
    else:
        body.append(_no_delay_line(F, 'test for compensable versus excusable'))
        body.append(
            "When a driving delay appears, the tool indicates whether an employer event sits on the path — "
            "that's the compensable-versus-excusable *hint*. The actual compensability call is your "
            "commercial and claims team's, against the contract's risk allocation.")
        body.append(
            "One steady caveat either way: don't read money into CPI here. Cost is derived from "
            "percent-complete, so CPI tracks the schedule rather than standing as its own cost verdict.")
    return K.A(head, body,
               advice=[
                   "Take the *time* picture from the schedule to your commercial and claims team; let them "
                   "decide compensability against the contract's risk allocation.",
                   K.go_deeper('Consultant Review', 'For the but-for read of what sits on the driving path'),
                   K.go_deeper('Claims / TIA reference', 'For the cause-type / FIDIC reference'),
               ],
               evidence=[K.ev('Critical Path Analyzer', 'Front carrying the delay', _driver_name(F)),
                         K.ev('EVM', 'Delay indicator', _delay_chip(F)),
                         K.ev('EVM', 'CPI (schedule echo)', K.ratio(F.get('cpi')))])


def t14q04(F, role):
    """How many working days are defensible, and does the but-for schedule back the number."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    if _behind(F):
        head = ("The defensible number comes off the **P6 F9 critical-path position from the corrected "
                "but-for run** — not off EVM, and not off the whole slip you're carrying today.")
    elif _ahead(F):
        head = "There's no delay to justify — the finish is forecasting ahead of the baseline, so there's no positive quantum to defend."
    else:
        head = "The finish is on the baseline date, so there's no net delay quantum to justify from this schedule."
    body = []
    if _behind(F):
        body.append(
            f"Start with what I actually hold and what it is: about **{K.wd(F.get('delay_days'))}** to "
            "completion. " + K.delay_source(F) + " But it's the **gross** slip — not the claim-grade figure.")
        body.append(
            "The claim-grade quantum is narrower than that whole figure. It's only the critical delay "
            "*attributable to specific events*, isolated in a corrected but-for run — the whole slip mixes "
            "your own execution shortfall in with anything the employer or a neutral event caused. Claim the "
            "lot and you're claiming your own slip; a reviewer strips that out on day one.")
        body.append(
            "So the method is: run the Consultant Review's but-for, insert (or remove) the events, and read "
            "the finish movement on **P6 F9** dates. Whatever "
            "remains on the driving path after your own slip is taken out is the number you can stand behind. "
            + K.driver_line(F))
        if tech:
            body.append(
                "Planner's note: reconcile the F9 but-for finish to P6 to the day before you quote it — the "
                "tool's forward pass matches P6 on progressed logic but can diverge on unprogressed or "
                "heavily constrained networks, and a claim number has to be the F9-exact one.")
    else:
        body.append(_no_delay_line(F, 'quantify as claimable delay'))
        body.append(
            "If a slip does open up, the defensible number is never the raw EVM figure I hold — it's the P6 "
            "F9 critical-path delay attributable to specific events, isolated in a corrected but-for run. "
            "The tool holds the indicator; the Consultant Review produces the claim-grade quantum.")
        body.append(
            "And the same discipline applies whenever it does open: claim only the critical delay tied to "
            "specific events, never the whole finish slip — the raw figure always carries your own execution "
            "slippage inside it, and a reviewer strips that out on day one. The but-for run is what separates "
            "the two; entitlement is then agreed with the engineer or DAB, never asserted by the tool.")
    return K.A(head, body,
               advice=[
                   "Run the but-for to strip out your own execution slip; the days left on the driving path "
                   "are the defensible quantum.",
                   "Quote the F9-exact finish, not the EVM re-derivation, when it goes in front of the client.",
                   K.go_deeper('Consultant Review', 'For the corrected but-for critical-path run'),
               ],
               evidence=[K.ev('EVM', 'Delay indicator (not quantum)', _delay_chip(F)),
                         K.ev('Consultant Review', 'Claim-grade figure', 'P6 F9 but-for critical path'),
                         K.ev('Critical Path Analyzer', 'Front carrying the slip', _driver_name(F))])


def t14q05(F, role):
    """Late employer drawings — pushed the critical path, or just ate float?"""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Test it, don't assume it — impact the drawing dates in the What-if and re-run F9. Only an "
            "event that moves the F9 finish carried a time impact; anything float absorbed did not.")
    dl = K.driver_line(F)
    body = [
        "This is the exact question a windows or TIA analysis exists to answer, and it has a clean binary "
        "shape: either the late drawing sat on the chain that controls the finish, in which case its delay "
        "flows straight through to completion, or it sat on a chain with float, in which case the float "
        "soaked it up and the finish never moved. The schedule decides which — not the fact that the "
        "drawing was late.",
        ((dl + " So unless those drawings feed *that* front directly, a late drawing most likely landed on a "
          "floated chain and was absorbed rather than pushing the finish. If it did feed the driving work, "
          "it shows up as movement at completion when you impact it.")
         if dl else
         f"On today's picture the governing work runs through {_driver_phrase(F)}. Unless those drawings "
         "feed that front directly, a late drawing most likely landed on a floated chain and was absorbed; "
         "if it fed the driving work, it shows as movement at the finish when you impact it."),
        "The mechanics matter for the claim: you insert the *actual* late-drawing dates into the "
        "impacted-as-planned network, re-run F9, and read the net finish movement. That net movement — and "
        "only that — is the time impact. A drawing that was late but never touched the driving path is real "
        "frustration with zero schedule entitlement, and it's better you know that before you argue it.",
        _indicator_caveat(),
    ]
    return K.A(head, body,
               advice=[
                   "Impact the real drawing dates in the What-if and re-run F9 — read the net finish move, "
                   "not the raw lateness.",
                   K.go_deeper('What-if / scenario engine', 'To model the drawing impact to the exact day'),
                   K.go_deeper('Critical Path Analyzer', 'To confirm whether the drawings even feed the driving path'),
               ],
               evidence=[K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('EVM', 'Delay indicator', _delay_chip(F)),
                         K.ev('Float', 'Negative-float activities', F.get('neg_float_count'))])


def t14q06(F, role):
    """Split the slip into weather, employer and me — and were the weather days beyond a competent allowance."""
    if not F.get('ok'):
        return _no_project(F)
    both = _both_sides(F)
    if _behind(F):
        head = ("This file already shows two of the three shares: employer-side (late client inputs) and your own "
                "(the work that sets the finish is behind). Weather isn't measured in it — and how the days split "
                "needs a time-impact analysis." if both else
                "On the schedule the slip concentrates on your own execution front — so the *visible* split "
                "is heavily contractor; the weather and employer shares have to be carved out deliberately.")
    else:
        head = "There's no net slip on today's schedule to split — so nothing yet to apportion across weather, employer and you."
    body = []
    if _behind(F):
        dl = K.driver_line(F)
        body.append(
            both if both else
            (dl + " That's the part the schedule sees on its own face — a shortfall on the governing front, "
             "with no late client input in the file — so before any carve-out, the visible split leans "
             "contractor/execution."
             if dl else
             f"The slip sits on the governing work front — {_finish_is(F)} — so before any carve-out, the "
             "visible split leans contractor/execution."))
        body.append(
            "To carve out a **weather** share, run the Weather tab for *your* site type. It compares your "
            "actual adverse days against the site-type norm — and the excusability test is precise: only days "
            "**beyond what a competent contractor should have allowed for** read as potentially excusable. "
            "The days inside the normal allowance are risk you priced, not a claim.")
        body.append(
            ("The **employer** share starts from the late client inputs above: for each one, show from your "
             "records when it actually held the work that sets the finish. " if both else
             "The **employer** share needs your causation record overlaid on these dates — late information, "
             "permits, access, free-issue. The schedule can only tell you whether, once you point to an "
             "employer event, that event sat on the driving path. ") +
            "What's left after weather and employer come out is the **contractor** share — and that's the honest "
            "arithmetic of an apportionment, not an agreed one.")
    else:
        body.append(_no_delay_line(F, 'split across weather, employer and contractor cause'))
        body.append(
            "When a slip does open, the split is the same three-way carve: the Weather tab tests the weather "
            "share against site-type norms, your records supply the employer share, and the residual is "
            "yours. The schedule grounds the *dates*; the apportionment is a claims judgement.")
    body.append(
        "One caution on the number: this is an **indicator split**, not an agreed apportionment. Concurrency, "
        "pacing and float can each move a day from one bucket to another, and that's argued between the "
        "parties — the tool sets up the evidence, it doesn't settle the share.")
    return K.A(head, body,
               advice=[
                   "Run the Weather tab on your correct site type first — coastal/marine, arid, monsoon all "
                   "carry very different norms, and the wrong preset understates the excusable share.",
                   K.go_deeper('Weather Impact', 'For the adverse-days-versus-norm comparison'),
                   K.go_deeper('Consultant Review', 'For the driving-path attribution of the residual'),
               ],
               evidence=[K.ev('Critical Path Analyzer', 'Front carrying the slip', _driver_name(F)),
                         K.ev('EVM', 'Delay indicator', _delay_chip(F)),
                         K.ev('Calendar Audit', 'Calendars in file', F.get('calendar_count'))])


def t14q07(F, role):
    """Concurrent delay, and pacing versus genuinely behind."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    ranked = _ranked_drivers(F)
    head = ("Concurrency needs **two independent critical delays in the same window** — and on today's "
            "schedule I can only see one chain truly controlling the finish, so there isn't genuine "
            "concurrency yet.")
    body = [
        "Get the definition straight first, because it's where concurrency claims are won and lost: it isn't "
        "'two things running late at once'. It's two *independent* delays, each of which would be critical "
        "on its own, overlapping in the same period. One critical chain plus a floated chain that happens to "
        "be behind is not concurrency — the floated one isn't controlling anything.",
        (K.driver_line(F) + " That's the one chain carrying the finish today."
         if K.driver_line(F) else
         f"Today the governing work runs through {_driver_phrase(F)} — the one chain carrying the finish."),
        (_second_front_line(F) + " So watch it rather than bank on it: if the driving front slips further "
         "and that near-critical front tips onto the longest path, you could get genuine overlapping "
         "delay — and *then* the concurrency question is live."
         if _second_front_line(F) else
         "There isn't a clear second front sitting right on the edge of critical in this file — so if a "
         "concurrency argument is being made, ask which second *independent* critical chain it rests on, "
         "because the schedule isn't showing one today."),
        "Pacing versus genuinely-behind is the other half, and it's a causation judgement the schedule "
        "flatly can't settle. If you slowed a front deliberately because an employer delay elsewhere gave "
        "you the room, that's *pacing* — a defence, not a delay you caused. If you slowed because you "
        "couldn't keep up, that's genuinely behind. Same dates on the schedule, opposite meaning — only "
        "your records and your consultant decide which.",
    ]
    if tech:
        body.append(
            "Planner's note: watch the near-zero total-float band, not just TF 0 — a front a few days off "
            "the longest path is the one that goes co-critical first and creates the concurrency window when "
            "the driver slips.")
    return K.A(head, body,
               advice=[
                   "If someone's arguing concurrency, make them name the second *independent* critical chain "
                   "and the overlapping window — the schedule has to show both.",
                   "Flag any pacing decision to your claims consultant with the reason you paced; don't let it "
                   "be read as your own delay.",
                   K.go_deeper('Consultant Review', 'For the but-for test of independent critical delays'),
               ],
               evidence=[K.ev('Critical Path Analyzer', 'Critical chain', _driver_name(F)),
                         K.ev('Float', 'Negative-float activities', F.get('neg_float_count')),
                         K.ev('EVM', 'Delay indicator', _delay_chip(F))])


def t14q08(F, role):
    """As-planned versus as-built on the critical path — where the time went."""
    if not F.get('ok'):
        return _no_project(F)
    p, a = _num(F.get('planned_pct')), _num(F.get('actual_pct'))
    gp = _gap_points(F)
    planned, actual = K.pct(F.get('planned_pct')), K.pct(F.get('actual_pct'))
    # No planned/actual split in this file → can't place the divergence honestly.
    if p is None or a is None:
        head = ("The as-planned versus as-built overlay is the right exhibit — but I can't place the "
                "divergence point without the planned/actual split, and this file isn't giving it to me.")
        body = [
            "The overlay lays the planned (baseline) curve, the earned (actual-progress) curve and the "
            "as-built dates over each other on the critical path, so the eye lands on the week they "
            "separate — that separation point is where the time started going. It needs a progressed, "
            "percent- or cost-loaded update to draw, and this snapshot doesn't carry the planned/actual "
            "figures I'd plot.",
            "Load a progressed update and the tool draws all three lines; the Consultant Review then runs "
            "the same comparison specifically on the critical path, which is the version that matters for a "
            "claim.",
            "The caveat holds whatever the data: the overlay is descriptive — it shows where and when "
            "slippage happened, never who caused it. Pair it with your causation record before it goes "
            "anywhere near a claim.",
        ]
        return K.A(head, body,
                   advice=[K.go_deeper('Consultant Review', 'For the critical-path as-planned versus as-built'),
                           K.go_deeper('Update vs Update', 'To place when each slice of the slip accrued')],
                   evidence=[K.ev('Consultant Review', 'Exhibit', 'planned / earned / as-built overlay'),
                             K.ev('Critical Path Analyzer', 'Front to read on the curve', _driver_name(F))])
    # At or ahead of the planned curve → there is no 'lost time' divergence to explain.
    if gp is not None and gp <= 0:
        head = ("On the curve you're at or ahead of plan, so there's no 'lost time' divergence to explain — "
                "the as-built overlay would show the actual line holding on or above the planned one.")
        body = [
            (f"At the data date the planned curve stands at **{planned}** and actual sits at **{actual}**"
             + (f", about **{abs(gp)} points ahead of** the curve" if gp < 0 else ", right on the curve")
             + ". The overlay is still worth drawing — it's the clean exhibit that shows you held the "
               "programme — but 'where did I lose the time' has no schedule answer here, because the curves "
               "haven't diverged against you."),
            "Keep it in reserve, though: the moment the actual line starts trailing the planned one, that "
            "separation week is exactly where a later analysis will say the slip began. Same exhibit, read "
            "the other way.",
            "And the standing caveat for when it does turn: the overlay is descriptive — it shows where and "
            "when, never who caused it. That stays a causation call for your records and your consultant.",
        ]
        return K.A(head, body,
                   advice=[
                       "Bank the overlay now as the exhibit that shows you held the programme; watch the two "
                       "lines each update for the first sign of separation.",
                       K.go_deeper('Consultant Review', 'For the critical-path overlay'),
                       K.go_deeper('Update vs Update', 'To watch the curves period by period'),
                   ],
                   evidence=[K.ev('EVM', 'Planned vs actual', f"{planned} vs {actual}"),
                             K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F))])
    # Behind the curve — the real 'where did I lose the time' case.
    head = ("The tool overlays planned, earned and actual on one curve — the divergence point is where the "
            "time went, and that's a strong client exhibit, but a **descriptive** one.")
    body = [
        (f"At the data date the planned curve stands at **{planned}** while actual sits at **{actual}** — "
         f"about a **{gp}-point** gap. That gap didn't open all at once; it opened from the point where the "
         "driving front started earning slower than planned, and the S-curve makes that inflection visible "
         "— the week the two lines began to separate is the week the slip started accruing."),
        (K.driver_line(F) + " On the overlay, that's the front pulling the actual line away from plan — so "
         "the divergence you see is that front's story told as a curve."
         if K.driver_line(F) else
         "On the overlay, the front pulling the actual line away from plan is the driving work front — the "
         "divergence you see is that front's story told as a curve."),
        (f"For a claim, the honest read on the *quantum* still matters: the EVM position ({actual} vs "
         f"{planned}) shows the **volume** gap, but the defensible **time** number is the F9 critical-path "
         "delay from the but-for run, not the percentage gap on the curve. Use the S-curve to show *where "
         "and when*; use the but-for to prove *how many days*."),
        "And the load-bearing caveat: the overlay is descriptive. It shows where and when slippage happened, "
        "not **who caused it**. Two projects with identical curves can have opposite causation stories. Pair "
        "the exhibit with your causation record or it proves the slip exists without proving whose it is.",
    ]
    return K.A(head, body,
               advice=[
                   "Use the three-way S-curve as the 'where and when' exhibit; pair it with the but-for run "
                   "for the 'how many days'.",
                   K.go_deeper('Consultant Review', 'For the critical-path as-planned versus as-built'),
                   K.go_deeper('Update vs Update', 'To place when each slice of the slip accrued'),
               ],
               evidence=[K.ev('EVM', 'Planned vs actual', f"{planned} vs {actual}"),
                         K.ev('EVM', 'Curve gap', f"{gp} pts"),
                         K.ev('Critical Path Analyzer', 'Front driving the divergence', _driver_name(F))])


def t14q09(F, role):
    """Model a prospective time impact as a TIA fragnet if piling/RFI slips N days."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Yes — build the fragnet in the What-if and run it through P6 F9. Only the portion that moves "
            "the finish counts as impact; anything float absorbs doesn't.")
    body = [
        "That's textbook impacted-as-planned: you take the accepted network, insert the delay event as a "
        "fragnet — a duration extension on the affected activity, or a hold with its own logic — and re-run "
        "the forward pass. The net movement of the completion milestone is the prospective time impact, read "
        "on P6-exact dates, the same F9 keystone the tool already uses.",
        ((f"Whether it bites depends on where the event lands. {K.driver_line(F)} Put the delay on that "
          "front and it flows to the finish; put it on a floated chain and F9 shows little or no movement, "
          "however many days you insert.")
         if K.driver_line(F) else
         f"Whether it bites depends on where the event lands — today the governing work runs through "
         f"{_driver_phrase(F)}. Put the delay on that front and it flows to the finish; put it on a floated "
         "chain and F9 shows little or no movement, however many days you insert."),
        "One discipline point that keeps the exhibit defensible: model the fragnet on the *current accepted* "
        "logic, insert one event at a time, and note the net finish move for each. Stack several events into "
        "one run and you can't say which one caused which day — reviewers pull that apart immediately. One "
        "event, one fragnet, one net impact.",
        "Keep it as a **prospective indicator** exhibit for the claim — a well-built impacted-as-planned run "
        "is persuasive, but the agreed quantum is still your claims consultant's call once entitlement and "
        "concurrency are argued. The tool gives you the F9-exact schedule number; it doesn't award the days.",
    ]
    return K.A(head, body,
               advice=[
                   "Insert the delay as a fragnet one event at a time, re-run F9, and record the net finish "
                   "move per event.",
                   K.go_deeper('What-if / scenario engine', 'To build the fragnet and read the F9 impact'),
                   K.go_deeper('Critical Path Analyzer', 'To confirm the event lands on the driving path'),
               ],
               evidence=[K.ev('What-if', 'Method', 'impacted-as-planned fragnet → F9'),
                         K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('EVM', 'Delay indicator', _delay_chip(F))])


def t14q10(F, role):
    """Slicing into windows, and whether events isolate or it's a global claim."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    head = ("Slice on your **actual update data dates** — each monthly update becomes a window, measured "
            "update-to-update — so you isolate *when* the slip accrued instead of arguing it globally.")
    body = [
        "The window boundaries are the least-arguable ones you already have: your real update data dates. "
        "Every planner recognises them, so nobody can accuse you of drawing the windows to suit the answer. "
        "Inside each window you measure the critical-path movement and the progress achieved — that period's "
        "contribution to the total slip — using Update vs Update.",
        "Doing it that way turns one big number into a dated sequence: this much moved in this window, that "
        "much in the next. That's far stronger than a single global figure, because a reviewer can see the "
        "slip accrue period by period rather than being asked to accept a lump at the end.",
        ((f"Whether the events isolate cleanly depends on the driving path holding steady. Today it runs "
          f"through {_driver_phrase(F)}; if it stays there across the windows, each window's movement is "
          "attributable to that front and its events isolate well. If it re-routes to another front "
          "mid-analysis, that window needs separate treatment — the driver changed, so the attribution "
          "changes with it.")
         if _driver_name(F) else
         "Whether the events isolate cleanly depends on the driving path holding steady across the windows. "
         "If it stays on one front, each window's movement attributes to that front; if it re-routes "
         "mid-analysis, that window needs separate treatment."),
        "And the honest fallback: if the events genuinely won't isolate per window — too many overlapping "
        "causes, a path that keeps jumping — the analysis defaults toward a **weaker global claim**, and "
        "reviewers discount those. That's a reason to slice tightly, not loosely. Your claims consultant "
        "sets the final window boundaries against the contract and the events register.",
    ]
    if tech:
        body.append(
            "Planner's note: watch for a path re-route inside a window as the tell that the window is doing "
            "two jobs — when the longest path shifts fronts mid-period, split the window at the shift so each "
            "sub-window carries one driver.")
    return K.A(head, body,
               advice=[
                   "Set the windows on your real update data dates, then measure each with Update vs Update — "
                   "don't invent boundaries to fit the answer.",
                   "Split any window where the driving path re-routes, so each carries a single driver.",
                   K.go_deeper('Update vs Update', 'For the per-window critical-path movement'),
               ],
               evidence=[K.ev('Update vs Update', 'Window basis', 'actual update data dates'),
                         K.ev('Critical Path Analyzer', 'Driving front to track across windows', _driver_name(F)),
                         K.ev('EVM', 'Total delay indicator', _delay_chip(F))])


def t14q11(F, role):
    """Which FIDIC clause covers this kind of event."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("The tool gives a FIDIC **reference map**, not legal advice — and the exact clause depends "
            "entirely on the real cause, your contract edition and the Particular Conditions.")
    body = [
        "Broadly, and only as a reference: EOT for events such as exceptional adverse weather or employer "
        "acts sits under the **time clauses** — 8.4/8.5 in the older Red and Yellow Books, consolidated at "
        "**8.5** in the 2017 editions — while the notice and claims machinery runs under **Clause 20** "
        "(20.1 in the older forms, split across 20.1/20.2 in 2017). That's the frame; the limb that "
        "actually applies is set by *what caused the delay*.",
        "So the clause follows the cause, which is exactly what the schedule can't tell you. Exceptional "
        "weather, late employer information, a variation, unforeseeable ground conditions, a suspension — "
        "each maps to a different sub-clause, and each carries its own notice period and evidence test. "
        "Identify the cause first (that's the earlier excusable-versus-compensable question), then the "
        "clause is a lookup, not a judgement.",
        "The Particular Conditions are the catch. Employers routinely amend the standard time and claims "
        "clauses — tightening notice periods, changing the weather test, adding conditions precedent — so "
        "the printed General Conditions clause number can be misleading on your specific contract. The "
        "signed document governs, not the standard form.",
        "Treat the map as orientation for the schedule evidence, and confirm the operative clause and its "
        "notice requirements with your contracts manager against the actual contract before you rely on a "
        "number in a submission.",
    ]
    return K.A(head, body,
               advice=[
                   "Pin down the *cause* first, then read the clause off it — don't reason from the clause "
                   "back to the cause.",
                   "Check the Particular Conditions for amended notice periods and conditions precedent before "
                   "you rely on the standard-form numbering.",
                   K.go_deeper('Claims / TIA reference', 'For the delay-method and FIDIC reference'),
               ],
               evidence=[K.ev('Claims / TIA', 'Time clauses', '8.4 / 8.5 (2017: 8.5)'),
                         K.ev('Claims / TIA', 'Notice & claims', 'Clause 20 (20.1)'),
                         K.ev('Claims / TIA', 'Governs', 'Particular Conditions + signed contract')])


def t14q12(F, role):
    """Assemble the EOT claim with schedule evidence and S-curve exhibits (in-progress feature)."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Honest answer: the dedicated **EOT Claim Builder** — the one that produces the impacted XML and "
            "a FIDIC-structured claim pack — is still in development, so I can't hand you the finished "
            "assembled claim today.")
    planned, actual = K.pct(F.get('planned_pct')), K.pct(F.get('actual_pct'))
    body = [
        "I'd rather tell you that straight than fake a claim pack. What the Builder will eventually do — "
        "insert the delay events into the network, write out the impacted XML, and wrap the result in a "
        "FIDIC-structured narrative with the notice and clause references — isn't wired yet, and a claim is "
        "the last place to bluff a feature that isn't there.",
        "What I *can* give you now are all the ingredients, from tools that already work. The **Consultant "
        "Review** but-for run gives the corrected critical-path position; the **F9 critical-path delay** is "
        "the claim-grade quantum (not the raw EVM figure); and the **baseline-vs-impacted-vs-actual "
        "S-curve** is the headline exhibit"
        + (f" — planned at {planned} against actual at {actual} tells that story at a glance." if
           (F.get('planned_pct') is not None and F.get('actual_pct') is not None) else "."),
        "Compose those into one pack in **Reporting Studio** — pick the results you want, order and name "
        "them, and export a single PDF, Word or Excel evidence bundle. That gives your claims consultant a "
        "coherent schedule-evidence pack to stitch into the formal claim: the quantum, the driving-path "
        "story and the exhibits, all in one document, until the Builder ships.",
        "So the division of labour today: the tool supplies grounded schedule evidence and exhibits; the "
        "formal FIDIC claim — notices, clause pleading, entitlement argument — is assembled by your claims "
        "consultant. When the EOT Claim Builder lands, that assembly step comes inside the tool.",
    ]
    return K.A(head, body,
               advice=[
                   "Build the interim pack now in Reporting Studio — but-for quantum plus the three-way "
                   "S-curve — and hand it to your claims consultant to formalise.",
                   K.go_deeper('Consultant Review', 'For the but-for quantum and critical-path exhibits'),
                   K.go_deeper('Reporting Studio', 'To compose the evidence pack as PDF / Word / Excel'),
               ],
               evidence=[K.ev('EOT Claim Builder', 'Status', 'in development'),
                         K.ev('Consultant Review', 'Available now', 'but-for + F9 quantum'),
                         K.ev('Reporting Studio', 'Output', 'composed PDF / Word / Excel pack')])


def t14q13(F, role):
    """When the delay first became foreseeable — notice-window timing (indicator only)."""
    if not F.get('ok'):
        return _no_project(F)
    has_hist = bool(F.get('has_history'))
    head = ("The schedule can date the *earliest evidence* of the delay — an indicator of when it became "
            "foreseeable — but whether you're still inside your notice window is a contractual call, not a "
            "schedule one.")
    body = []
    if has_hist:
        body.append(
            "You've got update history loaded, which is what this needs. Baseline Revision Comparison and "
            "the update run let you find the **first update** where the driving chain went negative and the "
            "finish started moving past the baseline. That update's data date is your indicator for when the "
            "delay first showed in the schedule — roughly when a competent planner would have seen it "
            "coming.")
    else:
        body.append(
            "To date it properly I need the earlier updates or the prior baseline loaded — with a single "
            "snapshot I can tell you the finish is slipping now, but not the *first* update where it "
            "appeared. Load the update history (or the previous baseline) and Baseline Revision Comparison "
            "will pin the update where the driving chain first went negative and the finish started moving "
            "past the baseline.")
    body.append(
        "That 'first appeared' date is the whole point for notice: most forms start the clock when you "
        "became aware, or ought to have become aware, of the event or its effect. The schedule gives you an "
        "evidence-based, dated answer to 'when ought a competent contractor to have seen this' — which is a "
        "far stronger footing than arguing it from memory.")
    body.append(
        "But read the hard limit: the tool reads schedule dates, not your contract's notice period and not "
        "your correspondence. It can't tell you the length of your notice window, when you actually gave "
        "notice, or whether a condition precedent has bitten. Whether you're still inside the window is your "
        "contracts manager's call against the contract and the notice record — the schedule only times the "
        "*trigger*, not the *deadline*.")
    return K.A(head, body,
               advice=[
                   "Take the first-negative update date to your contracts manager as the foreseeability "
                   "indicator; let them measure it against the contract's notice period.",
                   K.go_deeper('Baseline Revision Comparison', 'To date the first update the finish slipped'),
                   K.go_deeper('Claims / TIA reference', 'For the notice / foreseeability reference'),
               ],
               evidence=[K.ev('Baseline Revision', 'History loaded', ('yes' if has_hist else 'not yet')),
                         K.ev('EVM', 'Finish now', F.get('forecast_finish')),
                         K.ev('EVM', 'Delay indicator', _delay_chip(F))])


def t14q14(F, role):
    """GAP — notice-deadline tracking and prolongation cost per day are outside the schedule."""
    if not F.get('ok'):
        return _no_project(F)
    grounds = ('GAP — no contract-date ingest, correspondence, or monetary prolongation model')
    head = ("This one the tool can't ground yet — it tracks schedule dates and critical-path movement, but "
            "not contract notice periods, correspondence, or prolongation cost.")
    body = [
        K.gap_note(grounds),
        "The two things you're asking for both live outside the P6 file. **Which events are near a notice "
        "deadline** needs the contract's notice periods ingested and an events/correspondence register with "
        "the date each event (or its effect) became known — none of which is in a schedule export. **Your "
        "prolongation cost per day** needs a preliminaries/time-related-cost model — your daily site "
        "overhead, staff, plant standing and facilities — which is a commercial figure, not a schedule one.",
        "What the schedule *does* give you feeds straight into both, so you're not starting cold. The "
        "foreseeability timing (the first update a delay appeared) is the input to the notice-deadline "
        "clock, and the critical-path delay quantum is what the daily prolongation rate gets multiplied by. "
        "The tool supplies the *days*; your contracts and commercial teams supply the *deadlines* and the "
        "*rate*.",
        "To close this properly the tool would need three things loaded: the contract dates and notice "
        "clauses, an events/correspondence register, and a daily preliminaries rate. Until that exists, "
        "track notice deadlines in your contracts register and get the daily prolongation rate from your "
        "commercial team — then apply it to the F9 critical-path days the tool does give you.",
    ]
    return K.A(head, body,
               advice=[
                   "Keep a live notice-deadline register in your contract admin system — the schedule can't "
                   "watch those dates for you yet.",
                   "Get the daily prolongation rate from your commercial team, then multiply it by the F9 "
                   "critical-path delay quantum, not the raw EVM figure.",
               ],
               evidence=[K.ev('EVM', 'Delay indicator (days input)', _delay_chip(F)),
                         K.ev('Claims', 'Not ingested', 'contract dates + notice clauses'),
                         K.ev('Commercial', 'Not modelled', 'daily prolongation rate')])


ANSWERS = {
    't14q00': t14q00, 't14q01': t14q01, 't14q02': t14q02, 't14q03': t14q03,
    't14q04': t14q04, 't14q05': t14q05, 't14q06': t14q06, 't14q07': t14q07,
    't14q08': t14q08, 't14q09': t14q09, 't14q10': t14q10, 't14q11': t14q11,
    't14q12': t14q12, 't14q13': t14q13, 't14q14': t14q14,
}
