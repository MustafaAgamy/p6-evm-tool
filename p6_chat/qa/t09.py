"""Theme 9 — Manpower, Productivity & Resources.

Whether the plan can be *manned*, what productivity it assumes, and whether the labour
curve is real. The grounded FACTS dict does NOT carry a man-hour histogram, per-activity
quantities, resource assignments or productivity rates — those live in dedicated features
(Productivity & Resource Intelligence, Baseline Revision Comparison's resource layer,
Duration & Resource Calculation). So every answer here leads with the schedule signal it
CAN ground (SPI, the weighted driver discipline, out-of-sequence, driving-path count) and
then routes the manpower/productivity specifics to the feature that computes them — never
inventing a man-hour, a crew count or an output rate the file doesn't hold. Cost is derived
from percent-complete in these schedules, so CPI sits near 1.0 by construction and is not
an independent labour signal; SPI is the signal that moves.
"""
from . import _kit as K


# ── shared helpers ──────────────────────────────────────────────────────────────

def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can answer this "
              "from your own numbers — offline, nothing leaves your PC."])


def _delay_chip(F):
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


def _driver_chip(F):
    """Evidence chip naming the weighted driver discipline, or None."""
    d = K.main_driver(F)
    if not d:
        return None
    return K.ev('EVM', f"Driver — {d.get('name')}",
                f"{d.get('actual')}% vs {d.get('planned')}% planned")


def _aud(F, name):
    """One stored audit module dict for `name`, or {} — always guarded."""
    a = (F.get('audit') or {}).get(name)
    return a if isinstance(a, dict) else {}


def _heaviest(F, n=2):
    """The n heaviest disciplines by weight (the bulk of the man-hours if loaded)."""
    ds = [d for d in (F.get('disciplines') or []) if (d.get('weight') or 0) > 0]
    return sorted(ds, key=lambda d: (d.get('weight') or 0), reverse=True)[:n]


def _bulk_line(F):
    """A clause naming where the bulk of the effort sits, by weight, or ''."""
    top = _heaviest(F, 2)
    if not top:
        return ''
    return ' and '.join(f"**{d.get('name')}** (~{round((d.get('weight') or 0) * 100)}% of the project by weight)"
                        for d in top)


def _on_plan_names(F):
    """Disciplines on or ahead of plan that are still IN PROGRESS — the only ones with effort to smooth off.
    A 100%-complete discipline has nobody left on it."""
    return [d.get('name') for d in (F.get('disciplines') or [])
            if (d.get('gap') or 0) <= 2 and (d.get('actual') or 0) < 100]


def _cpi_note(F):
    """The honest CPI clause — near 1.0 by construction, not a labour signal (rule 4)."""
    cpi = F.get('cpi')
    if cpi is None:
        return ("Cost performance isn't independently derivable in this file — and even where it is, in these "
                f"schedules cost tracks percent-complete, so it won't stand in for a labour read. **SPI ≈ "
                f"{K.ratio(F.get('spi'))}** is the signal that moves.")
    return ("On cost, read **CPI ≈ " + K.ratio(cpi) + "** carefully: in these schedules cost is **derived from "
            "percent-complete**, so CPI sits near 1.0 by construction and is *not* an independent labour-cost signal. "
            f"Don't build a manpower story off it — **SPI ≈ {K.ratio(F.get('spi'))}** is the number that actually "
            "moves, and man-hours (where they're loaded) are the real labour read.")


def _seq_line(F):
    """A grounded read of whether the slip looks like sequencing, from out-of-sequence."""
    oos = F.get('oos_count')
    if oos is None:
        return ("On sequencing, the out-of-sequence count isn't stored in this snapshot — run the **Out-of-Sequence "
                "review** to confirm whether logic, not production, is the problem.")
    oosp = F.get('oos_pct')
    coos = F.get('critical_oos')
    if not oos:
        sound = "no activities are progressing out of sequence"
        verdict = "so the logic is being honoured — this is not a sequencing failure"
    elif (oosp or 0) < 5:
        sound = f"only **{oos}** activities ({K.pct(oosp)}) are progressing out of sequence"
        verdict = "a low count, so sequencing is broadly sound and unlikely to be the driver"
    else:
        sound = f"**{oos}** activities ({K.pct(oosp)}) are progressing out of sequence"
        verdict = "high enough that logic quality is worth interrogating alongside production"
    tail = f", {coos} of them on the critical path" if coos else ""
    return f"On sequencing, {sound}{tail} — {verdict}."


GROUNDS = {
    't09q00': "Baseline Revision Comparison, Productivity & Resource Intelligence, Critical Path Analyzer",
    't09q01': "Baseline Revision Comparison, Productivity & Resource Intelligence",
    't09q02': "Productivity & Resource Intelligence, EVM",
    't09q03': "Productivity & Resource Intelligence",
    't09q04': "Productivity & Resource Intelligence, Baseline Revision Comparison",
    't09q05': "Productivity & Resource Intelligence, What-if / scenario engine, Update Analysis",
    't09q06': "EVM, Update Analysis, Productivity & Resource Intelligence",
    't09q07': "Update Analysis, Productivity & Resource Intelligence",
    't09q08': "Productivity & Resource Intelligence",
    't09q09': "Baseline Revision Comparison, Productivity & Resource Intelligence",
    't09q10': "Duration & Resource Calculation, Productivity & Resource Intelligence, What-if / scenario engine",
    't09q11': "GAP — what-if adds crews but does not detect conflicts or level to a limit",
}


# ── answers ───────────────────────────────────────────────────────────────────

def t09q00(F, role):
    """Peak manpower, when it hits, and whether it lines up with the key milestones."""
    if not F.get('ok'):
        return _no_project(F)
    _, pace = K.spi_verdict(F)
    bulk = _bulk_line(F)
    behind = bool((F.get('delay_days') or 0) > 0)
    head = "Read the peak off the man-hour histogram — and treat it as man-hours, not heads."
    body = [
        "The peak labour figure and the week it lands are read straight off the manpower histogram in "
        "**Productivity & Resource Intelligence**, with the before/after picture in the **Baseline Revision "
        "Comparison** resource layer. One thing to hold onto before you quote it: those are **man-hours, not people** "
        "— turning a peak into a crew count needs a crew-size and shift-length assumption you supply, so don't put a "
        "headcount on the report off the bare number.",
    ]
    if bulk:
        body.append(f"Where the peak *should* sit is over your heaviest work front — on this schedule that's {bulk}. "
                    "That is the bulk of the effort by weight, and the labour peak belongs over it while it is on the "
                    "governing path — not before the work is released, and not after it has already passed.")
    dl = K.driver_line(F)
    if behind and dl:
        body.append("Timing is my real worry here. " + dl + " When you're behind and you load a recovery — extra "
                    "crews, an added shift — the peak both **sharpens and moves right**: it gets taller and it lands "
                    "later, often just as the next front loads on top of it. That is exactly the point at which a "
                    "peak stops being manageable.")
    else:
        body.append("Timing is the thing to verify even when the finish is holding: confirm the peak lands **while** "
                    "the governing work is live and **before** your key milestones — a peak that arrives after the "
                    "milestone it feeds is a date you have already missed.")
    body.append(f"On pace, {pace}. So put the histogram next to the milestone dates in the **Critical Path "
                "Analyzer** and confirm the peak clears each key date with room, rather than piling up against it.")
    return K.A(head, body,
               advice=["Line the man-hour peak up against your key milestone dates and confirm it lands before each "
                       "one, not on top of it.",
                       "Quote the peak as man-hours plus your stated crew-size assumption — never as a raw headcount.",
                       K.go_deeper(GROUNDS['t09q00'], 'For the dated peak')],
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay', _delay_chip(F)),
                         _driver_chip(F)])


def t09q01(F, role):
    """Is the manpower histogram realistic, or does it spike unrealistically week to week."""
    if not F.get('ok'):
        return _no_project(F)
    behind = bool((F.get('delay_days') or 0) > 0)
    head = "Look for saw-tooth week-to-week jumps — that's the tell of a curve nobody will ever man."
    body = [
        "The week-by-week manpower curve is read in **Productivity & Resource Intelligence** and, revision-to-revision, "
        "in the **Baseline Revision Comparison**. What you're hunting for is the **saw-tooth**: labour that jumps up "
        "and collapses week on week. Bodies don't move like that. A curve that roughly doubles man-hours in a single "
        "week won't get staffed — it will get flattened by reality, and the plan will slip to whatever the site could "
        "actually crew.",
    ]
    if behind:
        body.append("One caveat before you red-pen every spike: the recovery levers you're weighing (extra crews, an "
                    "added shift) will add **genuine** spikes — that is a real push, not an artefact. Don't confuse a "
                    "deliberate recovery ramp with an unstaffable curve; judge each spike by whether the trade can "
                    "actually be recruited into it.")
    onplan = _on_plan_names(F)
    if onplan:
        names = ', '.join(f"**{n}**" for n in onplan[:3])
        body.append(f"Where you *do* need to shed a spike, take it off the fronts that carry float rather than "
                    f"ramping bodies. On this schedule {names} are on or ahead of plan — effort can be shifted off "
                    "them to smooth the curve without touching the governing work.")
    else:
        body.append("Where you need to shed a spike, smooth by shifting effort onto the fronts that carry float "
                    "rather than by ramping bodies onto the critical work — the histogram shows you which weeks are "
                    "over-loaded and which have room.")
    body.append("Bottom line: a labour curve is only as good as the site's ability to man it. Flatten the "
                "saw-tooth **before** you commit to the plan, not after the update proves it couldn't be built.")
    return K.A(head, body,
               advice=["Flag any week that steps man-hours up sharply then drops them straight back — smooth it "
                       "before you commit the plan.",
                       "Smooth by moving effort onto float-carrying fronts, not by inventing bodies on the critical "
                       "path.",
                       K.go_deeper(GROUNDS['t09q01'], 'To see the week-by-week curve')],
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t09q02(F, role):
    """Is the schedule resource-loaded at all, and the man-hour split by discipline."""
    if not F.get('ok'):
        return _no_project(F)
    bulk = _bulk_line(F)
    head = "First confirm it's genuinely resource-loaded — the tool reads P6 resources, it never invents them."
    body = [
        "**Productivity & Resource Intelligence** reads the man-hour and resource assignments straight out of the P6 "
        "file, **read-only**. So the honest first step is to confirm the schedule actually carries **real resource "
        "assignments** and isn't a bare logic network with cost painted on top. If a package was never resource-loaded, "
        "the tool shows **zero for it — it does not guess a figure** to fill the gap. That's the whole basis of any "
        "manpower read: no assignments, no honest histogram.",
        _cpi_note(F),
    ]
    if bulk:
        body.append(f"By weight, the bulk of the work — and therefore most of the man-hours where it *is* loaded "
                    f"consistently — sits in {bulk}. That's where I'd expect the resource curve to be heaviest, and "
                    "it's where a missing load would hurt the read the most.")
    body.append("For the actual man-hour split line by line, that's the discipline table in **Productivity & Resource "
                "Intelligence** — it shows which packages are loaded and which read zero, so you know exactly how far "
                "you can trust the manpower picture before you brief off it.")
    if role == 'planning':
        body.append("Planner's note: check that man-hours are genuine P6 resource *units* on the activities, not a "
                    "cost field re-labelled — the tool won't manufacture units from a cost value, and a schedule that "
                    "only cost-loads will read light on labour.")
    return K.A(head, body,
               advice=["Confirm the schedule carries genuine P6 resource assignments before quoting any man-hour "
                       "figure from it.",
                       "Treat any package reading zero as *not loaded*, not as *no work* — the tool won't guess it.",
                       K.go_deeper(GROUNDS['t09q02'], 'For the loaded man-hour split')],
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'CPI (percent-derived)', K.ratio(F.get('cpi'))),
                         K.ev('EVM', 'Activities', F.get('activity_count'))])


def t09q03(F, role):
    """Given the quantities, are these durations achievable at normal productivity."""
    if not F.get('ok'):
        return _no_project(F)
    head = "Run it through Productivity & Resource Intelligence — it back-calculates the output each duration assumes."
    body = [
        "The clean way to answer this isn't to eyeball durations — it's to let **Productivity & Resource Intelligence** "
        "**back-calculate the implied daily output** behind each duration (m³ of concrete, tonnes of rebar per day) "
        "and check it against the built-in productivity norm library. Anything that beats a credible norm gets "
        "flagged as over-optimistic, with the norm and its source shown so you can argue it on the evidence rather "
        "than by feel.",
        "The honest limit is data: it needs the **quantities loaded on the activities**. Where P6 carries no quantity "
        "for a line, the tool **can't check that line and won't invent a quantity** to force an answer — it will tell "
        "you it couldn't assess it rather than bluff.",
    ]
    driver = K.main_driver(F)
    worst = F.get('worst_discipline')
    focus = driver or worst
    if focus:
        body.append(f"Where I'd scrutinise first on this schedule: **{focus.get('name')}**. It's already running "
                    f"**{focus.get('actual')}%** against **{focus.get('planned')}%** planned (a {focus.get('gap')}-point "
                    "gap), and when a front is falling behind, the usual root cause is that its **baseline output rate "
                    "was optimistic to begin with** — the concrete/rebar lines feeding it are the first place to look "
                    "for a rate the crew can't actually hit.")
    else:
        body.append("With no single front standing out as behind, I'd still spot-check the concrete and rebar-heavy "
                    "lines — bulk pours and slipform are where an optimistic assumed output most often hides.")
    body.append("Treat any flag as *challenge the assumption*, not *proof of failure*: a duration can beat the norm "
                "for a good reason (a bigger crew, easier access). The value is that you're now arguing a specific "
                "rate against a referenced norm instead of arguing in the dark.")
    return K.A(head, body,
               advice=["Back-check the concrete and rebar-heavy activities first — that's where an optimistic assumed "
                       "output does the most damage.",
                       "Where a line has no quantity loaded, load it in P6 and re-import — the tool won't assess a "
                       "duration it can't quantify.",
                       K.go_deeper(GROUNDS['t09q03'], 'For the implied-output check')],
               evidence=[_driver_chip(F),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t09q04(F, role):
    """Can this plan be manned — peak, ramp-up and demobilisation feasibility."""
    if not F.get('ok'):
        return _no_project(F)
    behind = bool((F.get('delay_days') or 0) > 0)
    head = "Judge it against real recruitment, not a smooth curve on a screen."
    body = [
        "There are three things to test in the labour curve, and the histogram in **Productivity & Resource "
        "Intelligence** (with the before/after in **Baseline Revision Comparison**) gives you all three. First the "
        "**ramp**: it shouldn't need labour doubling week-on-week — real crews mobilise on lead times, not on a "
        "spreadsheet's say-so. Second the **peak**: a peak you can't recruit to is a paper peak, and the plan will "
        "quietly slip to whatever you could actually crew.",
    ]
    if behind:
        body.append("Your recovery is exactly where I'd push. Clawing time back tends to lean on **specialist trades** "
                    "— the specialist crews and plant you can't just conjure at a week's notice. Before you "
                    "bank any recovery on the finish, confirm those trades are **sourceable** in the window you need "
                    "them; a what-if that assumes them into existence is optimistic, not real.")
    else:
        body.append("Even with the finish holding, sanity-check that the assumed ramp matches your real mobilisation "
                    "lead times — the schedule can draw a vertical ramp the labour market can't deliver.")
    body.append("Third — the **tail**. Watch the demobilisation: it should **taper into commissioning**, not fall off "
                "a cliff. A curve that dumps its labour the moment structural work ends will leave **punch, testing "
                "and handover under-manned**, and that's where projects lose their last weeks. A sensible plan sheds "
                "bodies in step with the remaining scope, not in one drop.")
    return K.A(head, body,
               advice=["Check the ramp against real recruitment lead times, and confirm any specialist trades in the "
                       "recovery are actually sourceable before banking them.",
                       "Confirm the tail tapers into commissioning so punch and handover aren't left under-manned.",
                       K.go_deeper(GROUNDS['t09q04'], 'For the manning profile')],
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay', _delay_chip(F)),
                         _driver_chip(F)])


def t09q05(F, role):
    """Is the finish limited by logic or by manpower — is any of the delay resource-driven."""
    if not F.get('ok'):
        return _no_project(F)
    _, pace = K.spi_verdict(F)
    behind = bool((F.get('delay_days') or 0) > 0)
    dl = K.driver_line(F)
    if behind:
        head = "Likely **part resource-driven** — and that matters, because the fix is nothing like a logic fix."
    else:
        head = "The finish is holding — but here's how to tell a resource-limited finish from a logic-limited one."
    body = []
    if behind and dl:
        body.append("The slip is being carried on the work front, not in the network. " + dl + " That reads as a "
                    "**site-execution / production** problem — output below plan on the governing work — rather than a "
                    "logic error.")
    body.append(_seq_line(F))
    body.append("Here's the clean test, and it's exactly what the **What-if / scenario engine** is for: if **adding "
                "capacity moves the finish**, the finish was **resource-limited** — production was the constraint. If "
                "you throw a second crew or a shift at it and F9 barely moves, the finish is **logic-limited** and more "
                "bodies won't help — you'd re-sequence instead. The what-if gives you an instant estimate, then the "
                "exact P6 figure via a build → F9 round-trip, so you can see which lever actually pays.")
    body.append("Why it's worth separating: a resource-limited slip is fixed by manning and productivity on the "
                "driving front; a logic-limited one is fixed by re-sequencing. Spend the recovery money on the wrong "
                "one and the date won't move.")
    if role == 'planning':
        body.append("Planner's cut: confirm on the driving path in the **Critical Path Analyzer** that the governing "
                    "activities are duration/production-driven (not constraint- or lag-pinned) before you call it "
                    "resource-limited — a date pinned by a hard constraint won't respond to crews either.")
    return K.A(head, body,
               advice=["Test it in the what-if: add a crew or a shift and see whether F9 actually moves — that tells "
                       "you resource-limited from logic-limited.",
                       "Spend the recovery on the lever the what-if proves out, not on the one that feels obvious.",
                       K.go_deeper(GROUNDS['t09q05'], 'To prove the lever')],
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay', _delay_chip(F)),
                         K.ev('Out-of-sequence', 'Activities', F.get('oos_count'))])


def t09q06(F, role):
    """Behind on SPI — manpower shortfall or sequencing, and which discipline is worst."""
    if not F.get('ok'):
        return _no_project(F)
    _, pace = K.spi_verdict(F)
    behind = bool((F.get('delay_days') or 0) > 0)
    below = (F.get('pace_pct') or 100) < 90
    dl = K.driver_line(F)
    wl = K.worst_line(F)
    if behind or below:
        head = "It reads as **production, not sequencing** — the pace is being dragged by a front under-performing."
    else:
        head = "You're not materially behind on pace — but here's how I'd split production from sequencing."
    body = [f"On pace, {pace}."]
    if dl:
        body.append(dl)
    body.append(_seq_line(F) + " A schedule slipping on **logic** shows a lot of out-of-sequence work and manipulated "
                "lags; a schedule slipping on **production** shows it in the discipline gaps instead — which is what "
                "we're seeing.")
    if wl and (not dl or True):
        body.append("Naming the worst trade: " + wl + " That's where the manpower and productivity pressure lives "
                    "this week — the front to put a recovery crew on, not a re-logic exercise.")
    body.append("So the honest attribution: the pressure is **manpower / productivity on the driving front**, not bad "
                "sequencing. Confirm the man-hours on that front in **Productivity & Resource Intelligence** and, if "
                "you want the period-over-period movement, read it in **Update Analysis**.")
    return K.A(head, body,
               advice=["Put the recovery effort on the worst-performing driving front — that's where the SPI is being "
                       "lost, not in re-sequencing.",
                       "Confirm the man-hours behind that front are real and sufficient before you promise a recovery "
                       "date.",
                       K.go_deeper(GROUNDS['t09q06'], 'For the attribution')],
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         _driver_chip(F),
                         K.ev('Out-of-sequence', 'Activities', F.get('oos_count'))])


def t09q07(F, role):
    """How many concurrent work-fronts does the driving path assume — can I man them all."""
    if not F.get('ok'):
        return _no_project(F)
    dpc = F.get('driving_path_count')
    cc = F.get('cpli_critical_count')
    head = "Count the concurrent fronts on the driving path first, then test whether the peak of all of them at once is staffable."
    body = []
    if dpc:
        body.append(f"The tool reads **{dpc}** driving path{'s' if dpc != 1 else ''} through this schedule "
                    "(**Critical Path Analyzer** / CPLI"
                    + (f", across roughly {cc} critical activities" if cc else "")
                    + "). The fewer the governing fronts, the less the labour is spread at source: a single governing "
                    "chain is essentially **one front at a time** and hard to over-spread; several parallel driving "
                    "chains mean several specialist crews needed **simultaneously**.")
    else:
        body.append("The number of concurrent driving fronts is read in **Update Analysis** and the **Critical Path "
                    "Analyzer** — that's the count of work faces the governing logic expects live at the same time. "
                    "Start there: a single governing chain is hard to over-spread; parallel critical chains are the "
                    "ones that demand crews at once.")
    body.append("The risk usually isn't the baseline plan — it's the **recovery**. The moment you add a shift or a "
                "second crew to claw back time, you create a second (or third) simultaneous front. Two specialist "
                "operations running at once only works if you can genuinely crew **both** in the same period — and "
                "specialist trades don't stretch on demand.")
    body.append("This is where the man-hour histogram earns its keep: **Update Analysis** shows how many activities "
                "run concurrently in each period, and **Productivity & Resource Intelligence** tells you whether the "
                "**aggregate man-hours across all those fronts** is staffable in that period — or only on paper. "
                "Concurrency the network can draw isn't the same as concurrency the labour market can deliver.")
    return K.A(head, body,
               advice=["Map every concurrent front the recovery creates and confirm you can crew each specialist trade "
                       "in the same period — not just in total.",
                       "Test the aggregate man-hour peak across all live fronts, not each front on its own.",
                       K.go_deeper(GROUNDS['t09q07'], 'For the concurrency and the peak')],
               evidence=[K.ev('Critical Path Analyzer', 'Driving paths', dpc),
                         K.ev('Critical Path Analyzer', 'Critical activities', cc),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi')))])


def t09q08(F, role):
    """What productivity rates did the planner assume, and are they credible."""
    if not F.get('ok'):
        return _no_project(F)
    head = "Productivity & Resource Intelligence surfaces exactly that — the output rate each duration implies, against the norm and its source."
    body = [
        "You don't have to argue this blind. **Productivity & Resource Intelligence** **back-derives the output rate "
        "implied by each duration** — the m³/day, tonnes/day or m²/day a line quietly assumes — and shows it next to "
        "the built-in norm with its **provenance**. So instead of debating a planner's gut feel, you're comparing a "
        "specific assumed rate to a referenced norm and asking him to defend the difference.",
    ]
    driver = K.main_driver(F)
    worst = F.get('worst_discipline')
    focus = driver or worst
    behind = bool((F.get('delay_days') or 0) > 0)
    if focus and (behind or (focus.get('gap') or 0) > 0):
        body.append(f"The rate I'd interrogate first here is the one behind **{focus.get('name')}** — it's running "
                    f"**{focus.get('actual')}%** against **{focus.get('planned')}%** planned. If the baseline assumed "
                    "an output you're now missing, there are only two honest explanations: the **norm was optimistic**, "
                    "or the **site conditions are harder** than the plan assumed. Either way the number to challenge is "
                    "that front's assumed daily output.")
    else:
        body.append("With no single front visibly behind, I'd still pressure-test the rates on the bulk-quantity work "
                    "— concrete, rebar, earthworks — because that's where an over-stated output rate compounds into "
                    "the most schedule risk if it's wrong.")
    body.append("The one honesty guarantee: it **shows the source and won't fabricate a rate** for you. Where a line "
                "has no quantity to derive a rate from, it says so rather than inventing an output — so every rate you "
                "challenge is one you can actually stand behind in a meeting.")
    return K.A(head, body,
               advice=["Pull the implied output rate for the worst-performing front and make the planner defend it "
                       "against the referenced norm.",
                       "Decide explicitly whether a missed rate is an optimistic norm or genuinely harder conditions — "
                       "the recovery differs.",
                       K.go_deeper(GROUNDS['t09q08'], 'For the assumed rates and their source')],
               evidence=[_driver_chip(F),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t09q09(F, role):
    """Did resource loading change between revisions — flatten the peak or just postpone it."""
    if not F.get('ok'):
        return _no_project(F)
    head = "The Baseline Revision Comparison shows it — and the tell is whether total man-hours held while the peak slid right."
    body = [
        "This needs two revisions loaded, so it's a **Baseline Revision Comparison** question — with the resource "
        "layer on, it shows the **added, removed and changed** resource assignments between the two baselines, and "
        "whether the man-hour peak **genuinely dropped** or merely **slid to the right**. I can't answer it from a "
        "single snapshot — there's no second revision in this file to difference against — but here's exactly what to "
        "read when you put the two side by side.",
        "The tell is simple and it's the one people miss: **if total man-hours are unchanged but the peak has moved "
        "later, they didn't relieve the problem — they postponed it.** That's a slip dressed up as a re-plan. A real "
        "re-plan **lowers** the peak (by genuinely re-sequencing or extending the window); a cosmetic one keeps the "
        "same labour and just shows it arriving later.",
        "Read it **alongside the finish-slip driver bridge** in the same comparison — the before/after on the finish "
        "date and what moved it. That lets you see whether the resequence actually **bought time** or only "
        "**reprofiled the labour** to look calmer while the completion date quietly moved.",
    ]
    if bool((F.get('delay_days') or 0) > 0):
        body.append("Given this update is already carrying a slip, I'd be especially sceptical of a revision that "
                    "claims a smoother curve without a lower peak — check the total man-hours held, not just the "
                    "shape.")
    return K.A(head, body,
               advice=["Compare **total** man-hours across the two revisions, not just the curve shape — a flatter "
                       "curve with the same total is a postponement, not a fix.",
                       "Read the manpower change next to the finish-slip bridge to see whether the resequence actually "
                       "bought time.",
                       K.go_deeper(GROUNDS['t09q09'], 'To difference the two revisions')],
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t09q10(F, role):
    """Remaining quantities → how many crews and how long — can that beat the plan. (in-progress)"""
    if not F.get('ok'):
        return _no_project(F)
    head = "Honest answer: the true bottom-up crew-and-duration calc is still in build, so I won't hand you a hard number off it yet."
    body = [
        "The proper way to answer this — **remaining quantities → crews → duration** from the ground up — is the "
        "**Duration & Resource Calculation** module, and that one is **still being built**. So I'm not going to give "
        "you a hard crew count and a firm remaining-duration off it, because it isn't computing them yet and I won't "
        "dress an estimate up as that calc.",
        "What I *can* do today is **approximate** it: the **What-if / scenario engine** lets me add crews and re-run "
        "F9 to see how the remaining plan responds, and **Productivity & Resource Intelligence** gives the norm-based "
        "output rates as a sense-check. Between them you get a **reasoned estimate** of whether a given crewing can "
        "beat the plan — but treat it as an estimate, not the quantity-driven answer.",
        "Once **Duration & Resource Calculation** lands, you'll get exactly what you're asking for: **quantity-driven "
        "crew sizes and durations** for the remaining work that you can set directly against the remaining plan and "
        "the current forecast finish — a genuine bottom-up, not a top-down read.",
    ]
    behind = bool((F.get('delay_days') or 0) > 0)
    if behind:
        body.append("Given where the finish sits ({}), that bottom-up is exactly what you'll want to prove any "
                    "recovery is real rather than hoped-for — so it's worth waiting for the calc rather than "
                    "committing to a crew count I can't yet ground.".format(K.delay_phrase(F)))
    return K.A(head, body,
               advice=["For now, use the what-if + productivity norms as a sense-check on any proposed crewing — and "
                       "label it an estimate.",
                       "Hold off promising a firm remaining-duration off quantities until Duration & Resource "
                       "Calculation ships.",
                       K.go_deeper(GROUNDS['t09q10'], 'For the interim estimate')],
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay', _delay_chip(F)),
                         _driver_chip(F)])


def t09q11(F, role):
    """Over-allocation + level to a crew cap → finish slip. (gap)"""
    if not F.get('ok'):
        return _no_project(F)
    head = "I can't ground this one honestly yet — the tool doesn't detect over-allocation or level to a crew cap."
    body = [
        K.gap_note(GROUNDS['t09q11']),
        "Concretely: the **What-if / scenario engine** can *add* crews and re-run F9, but it does **not** scan for "
        "over-allocation conflicts and it does **not** level the schedule down to a resource limit. So there's no "
        "honest **leveled finish date** I can hand you — anything I quoted would be invented, and I won't do that.",
        "To answer this properly the tool would need two things it doesn't have: **over-allocation detection** (which "
        "resources are demanded beyond their cap, and when) and **automatic leveling to a resource limit** (push work "
        "until no period exceeds the cap, then read the finish that falls out). Both are real gaps, not oversights I "
        "can paper over.",
    ]
    behind = bool((F.get('delay_days') or 0) > 0)
    body.append("The honest workaround: **level in P6 against your real crew caps and re-import**. Once you've leveled "
                "to the limits you actually have, I'll read the finish that comes out and tell you how much it slipped "
                "versus today"
                + (f" ({K.delay_phrase(F)} right now)" if behind else "")
                + " — a measured slip off your own leveled schedule, not a number I made up.")
    return K.A(head, body,
               advice=["Level to your real crew caps in P6, re-import, and I'll measure the finish slip that results.",
                       "Until then, treat any 'leveled' date from the what-if as unlevelled — it adds crews, it "
                       "doesn't enforce a cap.",
                       "Flag over-allocation detection + resource leveling as the feature this needs — it isn't built "
                       "yet."],
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


ANSWERS = {
    't09q00': t09q00, 't09q01': t09q01, 't09q02': t09q02, 't09q03': t09q03,
    't09q04': t09q04, 't09q05': t09q05, 't09q06': t09q06, 't09q07': t09q07,
    't09q08': t09q08, 't09q09': t09q09, 't09q10': t09q10, 't09q11': t09q11,
}
