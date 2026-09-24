"""Theme 3 — Critical Path & Float.

What controls the finish date, how much slack is left, and where it is eroding. Every answer
is grounded in FACTS: the stored audit modules (CPLI / critical-path density, float, negative
float, out-of-sequence, open ends) plus the EVM delay and the weighted progress-by-discipline
read. This file never names an individual driving activity out of thin air — the P6 file behind
F doesn't hand the chat the activity-level chain; the Critical Path Analyzer draws it — so where
a question asks *which* activities or *which* chain, the answer gives the grounded shape of the
path (how many activities drive it, how deep the negative float runs, where the weighted delay
concentrates) and points to the feature that names the chain. Numbers are the tool's own; caveats
are stated plainly (re-derived vs F9-exact, logic quality, single-snapshot limits).
"""
from . import _kit as K


# ── local guards / accessors (data only — phrasing stays in _kit) ───────────────

def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can answer this "
              "from your own numbers — offline, nothing leaves your PC. For the critical path and float "
              "I also read the Schedule Health Review / Schedule Audit results if you've run them on the "
              "import; without them I can still give you the finish position, just not the graded logic."])


def _kpi(F, module, key):
    """One stored audit KPI, or None. Guards every level so a missing module never raises."""
    try:
        return ((F.get('audit') or {}).get(module) or {}).get('kpis', {}).get(key)
    except Exception:
        return None


def _delay_chip(F):
    d = F.get('delay_days')
    if d is None:
        return None
    d = round(d)
    if d > 0:
        return f"+{d} wd (behind)"
    if d < 0:
        return f"{d} wd (ahead)"
    return "on date"


def _crit_tf(F):
    """Total float on the driving/critical path (the finish milestone's TF), signed. None-safe."""
    return _kpi(F, 'cpli', 'project_total_float_days')


def _cpli_ratio(F):
    return _kpi(F, 'cpli', 'cpli')


def _audit_missing(F):
    """True when none of the logic-audit numbers this theme needs were stored for the snapshot."""
    return (F.get('cpli_grade') is None and F.get('neg_float_count') is None
            and F.get('float_grade') is None and F.get('driving_path_count') is None)


def _run_audit_note():
    return ("I don't see the logic-audit results stored against this import, so I can't give you the "
            "graded float / CPLI / critical-path density yet — run the **Schedule Health Review** (and the "
            "**Schedule Audit**) on this file and re-ask, and I'll read the numbers straight off them.")


# ── believability / driver: the sanity-check the critical-path questions reuse ──

def _driver_read(F):
    """Where the weighted delay actually concentrates — the believability test for the path.
    Returns a sentence, or '' if there's no shortfall driver."""
    dl = K.driver_line(F)
    if not dl:
        return ''
    return ("Believability check — the weighted delay concentrates here: " + dl +
            " If the driving path runs through that front, it's a genuine execution path, not a logic "
            "artefact. If it instead runs through a low-weight design or admin line, treat it as suspect.")


def _logic_caveat(F):
    """The standing 'clean these before you trust the path' line, from the stored logic flags.
    Distinguishes 'not checked' (None) from 'checked and clean' (0) — never claims clean logic
    off an audit that wasn't run."""
    oos = F.get('oos_count')
    oe = F.get('open_ends')
    dg = F.get('dangling_count')
    if oos is None and oe is None and dg is None:
        return ("I don't hold the out-of-sequence / open-end / dangling-link flags for this import, so I can't "
                "fully vet the path's honesty yet — run the Schedule Audit and I'll fold them into the trust check.")
    bits = []
    if oos:
        bits.append(f"**{oos} out-of-sequence** activities")
    if oe:
        bits.append(f"**{oe} open ends**")
    if dg:
        bits.append(f"**{dg} dangling links**")
    if not bits:
        return ("The logic reads clean on the flags I hold — no out-of-sequence, open-end or dangling-link "
                "problems that would distort the path — so I'd trust the shape of it.")
    return ("One caveat before I fully trust the path: the schedule carries " + ", ".join(bits) +
            ". Out-of-sequence progress and open ends both let a driving path drift or hide, so I'd clean "
            "these and re-run before I stake the date on the chain the tool shows.")


# ── answers ─────────────────────────────────────────────────────────────────────

def t03q00(F, role):
    """What's on the critical path right now — and is it believable?"""
    if not F.get('ok'):
        return _no_project(F)
    dpc = F.get('driving_path_count')
    dens = F.get('cpli_density_grade') or F.get('cpli_grade')
    ctf = _crit_tf(F)
    head = ("Here's the honest read: I can tell you the **shape** of the critical path and whether it's "
            "believable, but the individual activities are drawn by the Critical Path Analyzer, not carried "
            "in this snapshot.")
    body = []
    if dpc is not None:
        body.append(f"The driving path runs through about **{dpc} activities** (including its milestones)"
                    + (f", and the critical-path density grades **{dens}**" if dens else "") + ". That's the "
                    "size of the chain controlling your finish.")
    if ctf is not None:
        if ctf < 0:
            body.append(f"It's carrying **{K.wd(ctf)} of negative total float** — the network is genuinely "
                        "pushing the finish, which is exactly what a real, live critical path looks like.")
        elif ctf == 0:
            body.append("It's sitting at **zero total float** — a clean, logic-driven critical path with no "
                        "cushion left.")
        else:
            body.append(f"It's carrying about **{K.wd(ctf)} of total float** at the finish — some room left, "
                        "so the date isn't yet being crushed.")
    if dpc is None and ctf is None:
        body.append("This import doesn't carry the critical-path metrics — the driving-path size, the density "
                    "grade and the total float on the path all come from the Schedule Health Review / Critical "
                    "Path Analyzer. Run them and I'll read the shape straight off.")
    dr = _driver_read(F)
    if dr:
        body.append(dr)
    body.append(_logic_caveat(F))
    body.append("So: believable in shape as far as I can see it, but I'd confirm the named chain and clean the "
                "logic flags before reporting it as the path.")
    adv = ["Open the Critical Path Analyzer and check the driving chain runs through the work you'd expect on "
           "this project type — the hardest, most sequence-locked front — not through a soft or administrative line.",
           K.go_deeper('Critical Path Analyzer', 'For the named driving chain')]
    if F.get('oos_count') or F.get('open_ends'):
        adv.insert(1, "Clean the out-of-sequence and open-end items first, then re-run — those are what let a "
                       "path lie.")
    return K.A(head, body, advice=adv,
               evidence=[K.ev('Critical path', 'Driving-path activities', dpc),
                         K.ev('Critical path', 'Total float on path', K.wd(ctf) if ctf is not None else None),
                         K.ev('Critical path', 'Density grade', dens),
                         K.ev('Out-of-sequence', 'Activities', F.get('oos_count')),
                         K.ev('Open ends', 'Count', F.get('open_ends'))])


def t03q01(F, role):
    """Real logic or a constraint holding the finish in place?"""
    if not F.get('ok'):
        return _no_project(F)
    nf = F.get('neg_float_count')
    ctf = _crit_tf(F)
    hc = F.get('hard_constraints_computable')
    if _audit_missing(F) and nf is None:
        return K.A("I need the Schedule Health Review run to answer this cleanly.",
                   body=[_run_audit_note(),
                         f"What I can say from the finish position alone: the schedule is {K.delay_phrase(F)}. "
                         "Whether that's honest network behaviour or a hard date pinning it is exactly what the "
                         "health review's float and constraint checks settle."],
                   advice=[K.go_deeper('Schedule Health Review', 'To confirm logic vs constraint')],
                   evidence=[K.ev('EVM', 'Delay', _delay_chip(F))])
    real = (nf or 0) > 0 or (ctf is not None and ctf < 0)
    head = ("**Real logic.** The finish is being pushed by the network, not pinned by a hard date."
            if real else
            "**Can't call it real logic outright** — the network isn't showing the pressure a live driving "
            "path would, so a constraint may be holding the date. Worth a direct check.")
    body = []
    if real:
        if nf:
            body.append(f"The tell is the negative float: **{nf} activities** ({K.pct(F.get('neg_float_pct'))}) "
                        "carry negative total float, and negative float only appears when the logic genuinely "
                        "drives the date — a mandatory or finish-on constraint would suppress it, not create it.")
        if ctf is not None and ctf < 0:
            body.append(f"The critical path itself is at **{K.wd(ctf)} of negative float**, which is authentic "
                        "network behaviour — the chain is longer than the time left, so the date moves.")
        body.append(f"Read with the finish being {K.delay_phrase(F)}, that slip is honest, not a lag or "
                    "constraint artefact.")
    else:
        body.append(f"Float isn't negative on the counts I hold ({K.wd(F.get('max_float')) or 'the max float'} "
                    "at the top end), so the finish could be genuine near-zero-float logic **or** a date "
                    "constraint sitting on the completion milestone. The two look similar from the outside.")
        body.append("The clean way to separate them is the constraint check — a mandatory-finish or finish-on-or-"
                    "before constraint pinning the milestone is what you're ruling in or out.")
    if hc:
        body.append("Good news: hard-constraint detection **is** computable on this file, so the Schedule Health "
                    "Review can confirm whether any mandatory/finish-on constraint is suppressing float on the path.")
    else:
        body.append("Honest caveat: hard-constraint detection isn't fully computable on this file, so I'd confirm "
                    "the completion milestone has no mandatory/finish-on constraint directly in the Health Review.")
    if F.get('open_ends'):
        body.append(f"Close the **{F.get('open_ends')} open ends** so nothing quietly understates the driving "
                    "logic — an open end can hide the very chain we're trying to trust.")
    return K.A(head, body,
               advice=[K.go_deeper('Schedule Health Review', 'For the graded logic and the constraint check'),
                       "Close the open ends and re-run so the driving chain can't be understated."
                       if F.get('open_ends') else None],
               evidence=[K.ev('Negative float', 'Activities', nf),
                         K.ev('Critical path', 'Total float on path', K.wd(ctf) if ctf is not None else None),
                         K.ev('Open ends', 'Count', F.get('open_ends')),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t03q02(F, role):
    """Longest path to completion vs the zero-float critical path."""
    if not F.get('ok'):
        return _no_project(F)
    nf = F.get('neg_float_count')
    ctf = _crit_tf(F)
    dpc = F.get('driving_path_count')
    head = ("On this schedule the longest path and the true critical path are effectively the same chain — "
            "but which set defines 'critical' depends on your float position, and that's the subtlety.")
    body = [
        "The distinction matters. The **longest continuous path** is the physical chain of work from the data "
        "date to completion. The **zero-total-float path** is the classic critical path — activities with no "
        "slack. They only coincide when the finish is at exactly zero float.",
    ]
    if (nf or 0) > 0 or (ctf is not None and ctf < 0):
        body.append(f"Here you're in **negative float** ({(str(nf) + ' activities') if nf else 'the path is below zero'}"
                    + (f", the path at {K.wd(ctf)}" if ctf is not None and ctf < 0 else "") + "), so there is no "
                    "zero-float path — the true critical path is the **negative-float set**, and the longest path "
                    "runs through it. Filtering on TF = 0 would show you nothing; you have to read the most-negative "
                    "chain as critical.")
    elif ctf is not None and ctf == 0:
        body.append("Here the finish is at **zero float**, so the zero-float critical path and the longest path "
                    "line up — the classic case.")
    elif ctf is not None and ctf > 0:
        body.append(f"Here the finish carries about **{K.wd(ctf)}** of positive float, so a 'TF = 0' filter may "
                    "show nothing and the longest continuous path is what actually governs — read the longest "
                    "chain, not a zero-float set.")
    else:
        body.append("I don't hold the finish's total-float position on this import, so I can't tell you whether "
                    "you're on a zero-float or a negative-float path — the Critical Path Analyzer settles it. Read "
                    "the longest continuous chain regardless; on a slipped schedule that's what governs, not a "
                    "TF = 0 filter.")
    if dpc is not None:
        body.append(f"The driving set the tool holds spans about **{dpc} activities** — that's the chain to trace "
                    "end-to-end for the longest path.")
    body.append("One thing to watch either way: a **near-parallel** longest-path candidate. If a second chain is "
                "only a few days behind the governing one, it becomes co-controlling the moment the leader slips — "
                "manage both as driving, not just the top chain.")
    return K.A(head, body,
               advice=["In the Critical Path Analyzer, view the **longest path** and the **negative-float** set "
                       "together — on a slipped schedule they're the same chain, and TF = 0 will mislead you.",
                       K.go_deeper('Critical Path Analyzer', 'For the drawn longest path')],
               evidence=[K.ev('Critical path', 'Driving-path activities', dpc),
                         K.ev('Critical path', 'Total float on path', K.wd(ctf) if ctf is not None else None),
                         K.ev('Negative float', 'Activities', nf)])


def t03q03(F, role):
    """CPLI above/below 1.0 and its trend."""
    if not F.get('ok'):
        return _no_project(F)
    ratio = _cpli_ratio(F)
    ctf = _crit_tf(F)
    grade = F.get('cpli_grade')
    rule_met = _kpi(F, 'cpli', 'baseline_rule_met')
    if ratio is None and ctf is None and grade is None:
        return K.A("I need the CPLI computed to answer this.",
                   body=[_run_audit_note(),
                         "CPLI (Critical Path Length Index) compares the critical-path length to the time left to "
                         "the finish — above 1.0 means the remaining plan is achievable, below means it isn't."],
                   advice=[K.go_deeper('Schedule Health Review', 'For CPLI and its grade')],
                   evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi')))])
    below = (ratio is not None and ratio < 1.0) or (ctf is not None and ctf < 0)
    if ratio is not None:
        head = (f"CPLI is **{K.ratio(ratio)}** — **{'below' if ratio < 1.0 else ('above' if ratio > 1.0 else 'at')}** 1.0. "
                + ("The remaining plan isn't achievable as-is." if ratio < 1.0 else
                   "The remaining plan is achievable on today's logic." if ratio > 1.0 else
                   "The plan is right on the line."))
    else:
        head = ("**Below 1.0.** With the critical path in negative float the index is under one — the remaining "
                "plan isn't achievable as-is." if below else
                "**At or above 1.0** on the float position — the plan is achievable on today's logic.")
    body = []
    if ctf is not None and ctf < 0:
        body.append(f"The driver is the float: the critical path sits at **{K.wd(ctf)} of negative float**, so I "
                    f"need to buy back roughly **{K.wd(ctf)}** on the driving chain just to lift CPLI back to 1.0.")
    body.append("An honesty note on what this grade means in the tool: the Schedule Health Review **grades "
                "critical-path density** (how much of the network is critical — a DCMA-style baseline-health read)"
                + (f" — currently **{grade}**" if grade else "") + "; the CPLI **ratio** and the baseline-float "
                "rule (non-negative total float means CPLI at or above 1.0) sit alongside it as the pass/fail "
                "context indicator"
                + (", and that rule is **" + ("met" if rule_met else "not met") + "** here." if rule_met is not None else "."))
    body.append("On the trend — one snapshot only gives me today's value, not a direction. Load two or three "
                "consecutive updates and I'll show you whether CPLI is clawing back or eroding.")
    _, pace = K.spi_verdict(F)
    if (F.get('pace_pct') or 100) < 90:
        body.append(f"Given {pace}, I'd assume it's still deteriorating until an update proves otherwise — a hole "
                    "this size doesn't self-correct.")
    return K.A(head, body,
               advice=["Load consecutive updates so CPLI can be trended — a single value can't tell you if the "
                       "plan is recovering.",
                       K.go_deeper('Critical Path Analyzer', 'For the critical-path length behind CPLI')],
               evidence=[K.ev('Critical path', 'CPLI', K.ratio(ratio) if ratio is not None else None),
                         K.ev('Critical path', 'Total float on path', K.wd(ctf) if ctf is not None else None),
                         K.ev('Critical path', 'Density grade', grade),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi')))])


def t03q04(F, role):
    """How much negative float, on which chain, how deep the hole."""
    if not F.get('ok'):
        return _no_project(F)
    nf = F.get('neg_float_count')
    nfp = F.get('neg_float_pct')
    ctf = _crit_tf(F)
    grade = F.get('neg_float_grade')
    if nf is None and ctf is None:
        return K.A("I need the negative-float check run to size the hole.",
                   body=[_run_audit_note(),
                         f"The finish is {K.delay_phrase(F)}, so I'd expect negative float on the driving chain — "
                         "but I won't put a number on it that the audit hasn't computed."],
                   advice=[K.go_deeper('Schedule Health Review', 'For the negative-float count and depth')],
                   evidence=[K.ev('EVM', 'Delay', _delay_chip(F))])
    if not nf and not (ctf is not None and ctf < 0):
        head = "**No negative float** on the counts I hold — the schedule isn't underwater right now."
        body = ["Nothing is carrying negative total float, so there's no recovery hole to dig out of on the logic. "
                f"Float health grades **{F.get('float_grade') or 'n/a'}**.",
                f"That said, the finish is {K.delay_phrase(F)} — if that slip is real, watch that the next update "
                "doesn't push the driving chain below zero."]
        return K.A(head, body,
                   advice=[K.go_deeper('Schedule Audit', 'For the float distribution')],
                   evidence=[K.ev('Negative float', 'Activities', nf),
                             K.ev('Float', 'Grade', F.get('float_grade'))])
    head = (f"**{nf} activities** ({K.pct(nfp)}) are on negative total float"
            + (f", and the deepest point on the driving chain is **{K.wd(ctf)}**." if ctf is not None and ctf < 0
               else ".") + " That's the size of the recovery you owe.")
    body = [
        (f"Read straight across: the governing hole is **{K.wd(ctf)}** of negative float on the critical path, "
         f"so you need to claw back around **{K.wd(ctf)}** to pull the finish back to zero float."
         if ctf is not None and ctf < 0 else
         f"**{nf} activities** are underwater — the depth per activity is in the audit's findings, sorted most-"
         "negative first."),
        f"Negative-float health grades **{grade or 'n/a'}** — that's the network's own severity read on how big "
        "the recovery is.",
        "Which chain? This snapshot gives me the extent and the depth, but not the named chain — the Schedule "
        "Audit lists every negative-float activity ranked deepest-first, and the Critical Path Analyzer shows which "
        "chain they belong to. Expect them to cluster on one or two fronts, not scatter evenly.",
        "Watch for a **second** underwater front: if the negative float isn't all on one chain, you're recovering "
        "on two fronts at once, and accelerating only the deepest one won't move the finish.",
    ]
    return K.A(head, body,
               advice=["Sort the Schedule Audit's negative-float findings deepest-first — the top of that list is "
                       "your recovery target list.",
                       K.go_deeper('Schedule Audit', 'For the ranked negative-float activities')],
               evidence=[K.ev('Negative float', 'Activities', nf),
                         K.ev('Negative float', 'Share', K.pct(nfp) if nfp is not None else None),
                         K.ev('Negative float', 'Grade', grade),
                         K.ev('Critical path', 'Deepest on path', K.wd(ctf) if ctf is not None and ctf < 0 else None)])


def t03q05(F, role):
    """Near-critical fronts a few days from becoming critical."""
    if not F.get('ok'):
        return _no_project(F)
    nf = F.get('neg_float_count')
    avg = F.get('avg_float')
    thr = F.get('float_threshold')
    ctf = _crit_tf(F)
    head = ("The near-critical read is a float-distance question, and I'll be straight about what this snapshot "
            "does and doesn't expose.")
    body = [
        "What I can ground: the Schedule Audit ranks every activity by total float, and the Critical Path "
        "Analyzer flags the chains sitting just behind the governing path. Anything within a handful of working "
        "days of the driving path's float is your near-critical set — a short slip on the leader makes it "
        "co-critical.",
    ]
    if (nf or 0) > 0:
        body.append(f"The immediate fronts are the ones already underwater: **{nf} activities** carry negative "
                    "float, and any of those not on the single deepest chain is effectively a second near-critical "
                    "path already — not a future risk, a present one.")
    if ctf is not None and ctf < 0:
        body.append(f"With the governing path at **{K.wd(ctf)} of negative float**, a near-critical chain is one "
                    f"sitting only a little shallower than that — it takes very little drift on the leader to make "
                    "it co-controlling.")
    if avg is not None:
        body.append(f"For context, average total float across the schedule is about **{K.wd(avg)}**"
                    + (f" against a high-float threshold of {K.wd(thr)}" if thr is not None else "") + " — but an "
                    "average hides the low-float tail, which is exactly where the near-critical fronts live, so "
                    "read the ranked list, not the mean.")
    body.append("Manage the nearest challenger **now** — protect its predecessors and hold its crew — rather than "
                "waiting for it to take over the finish. On a weather-exposed job, weather on the leading front is "
                "the most common trigger that tips a near-critical chain into control.")
    return K.A(head, body,
               advice=["In the Schedule Audit, sort by ascending total float and read the top of the list — those "
                       "are your near-critical fronts, in order.",
                       K.go_deeper('Critical Path Analyzer', 'For the near-critical chains behind the driver')],
               evidence=[K.ev('Negative float', 'Activities', nf),
                         K.ev('Float', 'Average float', K.wd(avg) if avg is not None else None),
                         K.ev('Critical path', 'Total float on path', K.wd(ctf) if ctf is not None else None)])


def t03q06(F, role):
    """Where did I lose float since last update — float migration by chain."""
    if not F.get('ok'):
        return _no_project(F)
    tr = F.get('trend')
    nf = F.get('neg_float_count')
    ctf = _crit_tf(F)
    head = ("To show float migration chain-by-chain I need the previous update loaded next to this one — that's an "
            "**Update vs Update** comparison, and it's the honest answer to 'where did the float go'.")
    body = [
        "Float migration is a two-snapshot measurement: I have to compare each chain's float now against its float "
        "last period to see which fronts burned slack and which held. With a single snapshot I can give you today's "
        "standing, not the movement into it.",
    ]
    if tr and tr.get('delta') is not None and tr.get('prev_delay') is not None:
        delta = tr.get('delta')
        moved = ('a further ' + K.wd(delta) + ' lost' if (delta or 0) > 0 else
                 ('a recovery of ' + K.wd(delta) if (delta or 0) < 0 else 'no net change'))
        body.append(f"I do hold a prior data point on the **finish**: delay to completion moved from "
                    f"{K.wd(tr.get('prev_delay'))} to {K.wd(F.get('delay_days'))} — {moved} between updates. That's "
                    "the finish moving; the per-chain float migration behind it still needs the full period compare.")
    stand = ("the negative-float count isn't stored for this import" if nf is None
             else (f"**{nf} activities** on negative float" if nf else "no activities on negative float"))
    body.append("Today's standing, which is what I can ground now: " + stand
                + (f", the driving path at **{K.wd(ctf)}**" if ctf is not None else "")
                + f", float health graded **{F.get('float_grade') or 'n/a'}**.")
    read = K.driver_line(F) or "the weighted driving front is the usual culprit."
    body.append("My working read until you load the prior update: float loss usually concentrates on the front "
                "progressing slowest against plan — " + read + " That's where I'd expect the migration to land "
                "when we run the comparison.")
    return K.A(head, body,
               advice=["Import last month's XER/XML alongside this one and run Update vs Update — I'll quantify "
                       "exactly which chains burned slack.",
                       K.go_deeper('Update vs Update', 'For the period-over-period float movement')],
               evidence=[K.ev('Negative float', 'Activities now', nf),
                         K.ev('Critical path', 'Total float on path', K.wd(ctf) if ctf is not None else None),
                         K.ev('Trend', 'Delay now', _delay_chip(F))])


def t03q07(F, role):
    """Did the critical path change since the last update — a new driving chain?"""
    if not F.get('ok'):
        return _no_project(F)
    tr = F.get('trend')
    dpc = F.get('driving_path_count')
    head = ("Confirming a **path change** needs both updates loaded — **Update vs Update** flags when the driving "
            "chain switches between periods. From one snapshot I can tell you today's driver, not whether it just "
            "jumped.")
    body = [
        "A driving-chain switch is a comparison result: I have to see which chain controlled last period and which "
        "controls now. That's the whole point of the period compare — it catches the migration before it surprises "
        "the team on site.",
    ]
    if dpc is not None:
        body.append(f"Today's controlling chain spans about **{dpc} activities** on the driving path"
                    + (f", density graded **{F.get('cpli_density_grade') or F.get('cpli_grade')}**"
                       if (F.get('cpli_density_grade') or F.get('cpli_grade')) else "") + ". That's your current "
                    "driver; the question is whether it's the same one as last month.")
    if tr and tr.get('direction'):
        direction = tr.get('direction')
        body.append(f"The one directional signal I do hold: the finish is **{'worsening' if direction=='worse' else ('improving' if direction=='better' else 'flat')}** "
                    "period-over-period. If it's worsening, a near-critical challenger closing on the leader is "
                    "exactly how a path migration starts forming — worth confirming.")
    else:
        body.append("If a near-critical front has been closing on the leader update over update, that's a path "
                    "migration forming — but I can't see that closing motion from a single file.")
    body.append("Load the prior update and I'll tell you definitively whether the driver has already jumped to a "
                "new chain or is about to.")
    return K.A(head, body,
               advice=["Run Update vs Update with the previous snapshot — it names a driving-chain switch explicitly.",
                       K.go_deeper('Update vs Update', 'To confirm a driving-chain switch')],
               evidence=[K.ev('Critical path', 'Driving-path activities', dpc),
                         K.ev('Trend', 'Direction', (tr or {}).get('direction')),
                         K.ev('Trend', 'Delay now', _delay_chip(F))])


def t03q08(F, role):
    """Multiple parallel critical paths to worry about?"""
    if not F.get('ok'):
        return _no_project(F)
    nf = F.get('neg_float_count')
    ctf = _crit_tf(F)
    dpc = F.get('driving_path_count')
    if nf is None and ctf is None and dpc is None:
        return K.A("I need the float / critical-path audit run to judge parallel paths.",
                   body=[_run_audit_note(),
                         "Whether you have one critical path or several running in parallel is a negative-float-"
                         "spread question — once the Schedule Health Review is in, I'll tell you if the underwater "
                         "work sits on one chain or fans across several, then point the Critical Path Analyzer at "
                         "it to draw them.",
                         f"For context, the finish is {K.delay_phrase(F)}"
                         + (" — a slip that size on a multi-discipline job usually means more than one front is "
                            "under pressure, not just one." if (F.get('delay_days') or 0) > 0 else
                            " — even so, I'd confirm whether one chain or several govern once the audit is in.")],
                   advice=[K.go_deeper('Critical Path Analyzer', 'To see the parallel chains')],
                   evidence=[K.ev('EVM', 'Delay', _delay_chip(F))])
    head = ("Likely **yes — plan for more than one.** This snapshot doesn't enumerate the parallel chains, but the "
            "negative-float spread tells me whether the finish is controlled by one front or several.")
    body = []
    if (nf or 0) > 0:
        body.append(f"**{nf} activities** are on negative float. If those all sat on a single chain you'd have one "
                    "critical path; when negative float is spread across more than one front, you effectively have "
                    "**parallel critical paths** — and that's the common case on a slipped multi-discipline job.")
    if ctf is not None and ctf < 0:
        body.append(f"The governing path is at **{K.wd(ctf)}**. A second chain sitting only a little shallower is a "
                    "de-facto parallel critical path — close enough that fixing only the leader lets the other one "
                    "quietly take over the finish.")
    if dpc is not None:
        body.append(f"The driving set spans about **{dpc} activities**; the Critical Path Analyzer resolves whether "
                    "that's one continuous chain or two-plus running side by side.")
    body.append("That's the classic terminal trap: accelerate the top front, and the second one controls the date "
                "instead. **Any recovery plan has to hold every underwater front above water at once** — model it "
                "against all of them, not just the deepest.")
    return K.A(head, body,
               advice=["Build the recovery against every negative-float front together — accelerating one path while "
                       "a parallel one still controls the finish buys you nothing.",
                       K.go_deeper('Critical Path Analyzer', 'To see the parallel chains')],
               evidence=[K.ev('Negative float', 'Activities', nf),
                         K.ev('Critical path', 'Driving-path activities', dpc),
                         K.ev('Critical path', 'Total float on path', K.wd(ctf) if ctf is not None else None)])


def t03q09(F, role):
    """Highest-float activities — can I pull crews onto the critical work?"""
    if not F.get('ok'):
        return _no_project(F)
    above = F.get('float_above')
    thr = F.get('float_threshold')
    mx = F.get('max_float')
    head = ("**In principle yes — those are your donor pool** — and I can point you at exactly which activities "
            "carry the spare time, with two cautions that decide whether the crews are actually movable.")
    body = []
    if above is not None and thr is not None:
        head = (f"**Yes — about {above} activities carry more than {K.wd(thr)} of total float** and are your donor "
                "pool for reallocation, with two cautions below.")
        body.append(f"**{above} activities** sit above the high-float threshold of **{K.wd(thr)}**"
                    + (f", the loosest one at about **{K.wd(mx)}** of float" if mx is not None else "") + ". Those "
                    "are the candidates to pull crews off — the Schedule Audit lists them ranked by float, so you "
                    "can work top-down.")
    elif mx is not None:
        body.append(f"The loosest activity carries about **{K.wd(mx)}** of total float, so there is genuine slack "
                    "to redeploy — the Schedule Audit ranks every activity by float so you can pick the donors.")
    else:
        body.append("The Schedule Audit ranks every activity by total float; the top of that list — the high-float "
                    "activities well away from the driving path — is your donor pool. Run it to get the ranked list.")
    body.append("**Caution one — trade match.** Slack is only useful if the freed crew's trade matches the critical "
                "work. You can't move a piling crew's float onto a concrete gang; reallocate within the trade, or "
                "you've moved a number on paper and nothing on site.")
    body.append("**Caution two — spare vs merely time-flexible.** High float means the activity *can* move in time, "
                "not that its crew is idle. Confirm the resource is genuinely available before you commit it to the "
                "critical front.")
    body.append("And validate the move before you bank it: a crew reallocation is exactly the kind of change to run "
                "through the What-if engine — an instant estimate, then the exact P6 figure via a build → F9 "
                "round-trip — so you're accelerating the date, not just relabelling crews.")
    return K.A(head, body,
               advice=["Sort the Schedule Audit by descending total float, then filter to trades that match the "
                       "critical work — that intersection is your real donor list.",
                       K.go_deeper('Schedule Audit', 'For the float-ranked activities'),
                       "Model the reallocation in the What-if before committing — it confirms the day-for-day "
                       "buy-back against P6."],
               evidence=[K.ev('Float', 'High-float activities', above),
                         K.ev('Float', 'Threshold', K.wd(thr) if thr is not None else None),
                         K.ev('Float', 'Max float', K.wd(mx) if mx is not None else None)])


def t03q10(F, role):
    """GAP — rank near-critical paths by probability of becoming critical."""
    if not F.get('ok'):
        return _no_project(F)
    nf = F.get('neg_float_count')
    head = "**I can't ground a probability ranking honestly** — and I'd rather tell you that than dress a guess up as a number."
    body = [
        K.gap_note('GAP — the tool ranks near-critical paths by total float, not by likelihood; there is no '
                   'Monte-Carlo or risk simulation behind it'),
        "What I *can* give you deterministically is the **float ranking**: the Schedule Audit orders chains by how "
        "little slack they have, and by float alone the shallowest near-critical front is the one most likely to "
        "turn critical next. That's a distance measure, not a probability.",
    ]
    if (nf or 0) > 0:
        body.append(f"Concretely, **{nf} activities** are already on negative float — those aren't 'likely to become "
                    "critical', they already are, so they rank first regardless of any probability model.")
    body.append("A true probabilistic ranking would need a risk model with duration uncertainty on each chain — a "
                "Monte-Carlo that isn't built yet. My judgement can tell you which front I'd worry about first from "
                "experience, but I'll flag that as judgement, not a computed likelihood.")
    return K.A(head, body,
               advice=["Use the float ranking as the proxy — shallowest float first — and treat any likelihood call "
                       "on top of it as engineering judgement, stated as such.",
                       K.go_deeper('Schedule Audit', 'For the float-based ranking'),
                       K.go_deeper('Critical Path Analyzer', 'To see which chains those activities sit on')],
               evidence=[K.ev('Negative float', 'Already critical', nf),
                         K.ev('Float', 'Grade', F.get('float_grade'))])


def t03q11(F, role):
    """GAP — auto-alert when critical-path float drops below five days."""
    if not F.get('ok'):
        return _no_project(F)
    nf = F.get('neg_float_count')
    ctf = _crit_tf(F)
    head = "**That's not something I can set up today** — but here's the practical way to catch it, and where you already stand."
    body = [
        K.gap_note('GAP — float is computed on demand each time you import an update; there is no standing monitor '
                   'watching a threshold between updates'),
        "In practice you'd catch a five-day float breach at each **update review** — every time you import a new "
        "XER/XML, the float is recomputed and the Schedule Health Review shows you the position. It's a per-cycle "
        "manual check rather than a live watchdog.",
    ]
    if (ctf is not None and ctf < 5) or (nf or 0) > 0:
        body.append("And right now you're already well past that line: "
                    + (f"the critical path is at **{K.wd(ctf)} of negative float**" if ctf is not None and ctf < 0
                       else (f"**{nf} activities** are on negative float" if nf else "float on the driving path is "
                             "already below five days")) + " — so that alert would be firing the moment you switched "
                    "it on. The threshold question is academic until you've recovered back above zero.")
    body.append("A persistent float-threshold watchdog across snapshots would need to be built — a standing monitor "
                "that re-checks on every import and pings you on a breach. For now, make 'critical-path float' a "
                "fixed line item in your update-review checklist so it never gets missed.")
    return K.A(head, body,
               advice=["Add a critical-path-float check to your standing update-review routine — recompute and read "
                       "it every import, since there's no automatic alert between cycles.",
                       K.go_deeper('Schedule Health Review', 'For the float position each update')],
               evidence=[K.ev('Critical path', 'Total float on path', K.wd(ctf) if ctf is not None else None),
                         K.ev('Negative float', 'Activities', nf)])


ANSWERS = {
    't03q00': t03q00, 't03q01': t03q01, 't03q02': t03q02, 't03q03': t03q03,
    't03q04': t03q04, 't03q05': t03q05, 't03q06': t03q06, 't03q07': t03q07,
    't03q08': t03q08, 't03q09': t03q09, 't03q10': t03q10, 't03q11': t03q11,
}
