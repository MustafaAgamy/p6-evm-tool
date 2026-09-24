"""Theme 16 — Reporting & Stakeholder Communication.

Turning the analysis into the weekly/monthly story for the team, the client and the board.
Every answer is grounded in FACTS — the EVM headline (SPI/CPI, planned vs actual %, PV/EV/AC),
the finish position (signed delay to completion, forecast vs baseline), the weighted work front
driving the shortfall, and the DCMA-style logic-quality signals — and speaks as a senior
planning engineer composing the report. Where the exact figure or visual lives in a feature
(Reporting Studio, EVM, the in-chat dashboard, Consultant Review, the What-if, Power BI) the
answer says so and points there; it never invents a number, a recovery day-count or a contract
date the file doesn't hold. Cost is read honestly: CPI is structurally near 1.0 on these
%-complete-derived schedules, so SPI carries the schedule story — the answers say so rather
than build a cost drama off CPI. Two asks in this theme are honest gaps: an automatic
red-amber-green scorecard, and a cross-project portfolio view plus liquidated-damages exposure
(no contract-date/penalty ingest) — those are named as gaps, with the planning read given
instead of a fabricated figure.
"""
from . import _kit as K


def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can build the "
              "board summary, the client story and the dashboard from your own numbers — offline, "
              "nothing leaves your PC."])


# ── shared, F-grounded helpers (all None-safe) ──────────────────────────────────

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
    d = K.main_driver(F)
    return d.get('name') if d else None


def _gap_points(F):
    """Signed 'about N points behind/ahead of the curve' clause, or '' when not derivable."""
    a, p = F.get('actual_pct'), F.get('planned_pct')
    if a is None or p is None:
        return ''
    diff = round(p - a)
    if diff > 0:
        return f"about **{diff} points behind** the planned curve"
    if diff < 0:
        return f"about **{abs(diff)} points ahead** of the planned curve"
    return "**on** the planned curve"


def _headline_position(F):
    """One compact 'where we stand' sentence built from actual/planned + finish + SPI."""
    gp = _gap_points(F)
    lead = (f"**{K.pct(F.get('actual_pct'))} complete** against **{K.pct(F.get('planned_pct'))} planned**"
            + (f" — {gp}" if gp else ""))
    return lead + f", SPI ≈ {K.ratio(F.get('spi'))}, and the finish is {K.delay_phrase(F)}."


def _cost_note(F):
    """An honest cost line: CPI is structurally ~1.0 here, so don't hang a cost drama on it."""
    cpi = F.get('cpi')
    if cpi is None:
        return "Cost performance (CPI) isn't derivable in this file, so keep the report on the schedule signal."
    hold = "holding close to budget" if cpi >= 0.97 else ("running modestly over" if cpi < 0.97 else "on budget")
    return (f"Cost is **{hold}** (CPI {K.ratio(cpi)}) — but read it with care: on this schedule cost is "
            "derived from % complete, so CPI sits near 1.0 by construction. **SPI is the real signal**; "
            "don't let a near-1.0 CPI reassure anyone while the schedule is behind.")


def _behind_disciplines(F):
    return sorted([d for d in (F.get('disciplines') or []) if (d.get('gap') or 0) > 2],
                  key=lambda d: (float(d.get('gap') or 0) * float(d.get('weight') or 0)), reverse=True)


def _on_plan_disciplines(F):
    return sorted([d for d in (F.get('disciplines') or []) if (d.get('gap') or 0) <= 2],
                  key=lambda d: (d.get('weight') or 0), reverse=True)


def _recovery_line(F):
    """Consistent, non-fabricated recovery pointer — never a day-count the file hasn't re-run."""
    return ("Table the recovery levers — a night shift, a second crew on the driving front, a "
            "re-sequence — but **size each one in the What-if before you commit a day-count to it**: "
            "it gives an instant estimate, then the P6-exact figure via a build → F9 round-trip. I "
            "won't put a recovered-days number on a scenario the schedule hasn't actually been re-run for.")


def _logic_caveat_line(F):
    """A clause naming the logic-quality flags that keep the numbers from being fully bankable."""
    bits = []
    if F.get('oos_count'):
        crit = F.get('critical_oos')
        bits.append(f"**{F.get('oos_count')} out-of-sequence activities**" + (f" ({crit} on the driving path)" if crit else ""))
    if F.get('open_ends'):
        bits.append(f"**{F.get('open_ends')} open ends**")
    if F.get('dangling_count'):
        bits.append(f"**{F.get('dangling_count')} dangling logic links**")
    if not bits:
        return ''
    if len(bits) == 1:
        joined = bits[0]
    else:
        joined = ", ".join(bits[:-1]) + " and " + bits[-1]
    return joined


# ── answers ─────────────────────────────────────────────────────────────────────

def t16q00(F, role):
    """Create a professional dashboard — the in-chat one-page EVM command board."""
    if not F.get('ok'):
        return _no_project(F)
    head = (f"I'll build you a one-page Earned-Value command board straight from **{F.get('project_name')}** — "
            "every figure computed from your schedule, nothing written by an AI.")
    body = [
        ("Ask me to *create a professional dashboard* and you get a single executive screen: a **health "
         f"verdict** (this file reads {K.delay_phrase(F)}, SPI ≈ {K.ratio(F.get('spi'))}), then a row of "
         "KPI tiles — SPI, CPI, % complete, delay to completion, Earned Value and Planned Value — each one "
         "the same number the EVM tab shows, so the board can never disagree with the analysis."),
        (f"On this schedule those tiles read: **{K.pct(F.get('actual_pct'))}** complete against "
         f"**{K.pct(F.get('planned_pct'))}** planned"
         + (f" ({_gap_points(F)})" if _gap_points(F) else "")
         + f", SPI **{K.ratio(F.get('spi'))}**, CPI **{K.ratio(F.get('cpi'))}**, delay **{_delay_chip(F)}**"
         + (f", EV **{K.money(F.get('ev'))}** against PV **{K.money(F.get('pv'))}**." if (F.get('ev') is not None and F.get('pv') is not None) else ".")),
        ("The visuals do the talking: the **cost-loading S-curve** (Planned Value, Earned Value and the "
         "forecast-to-completion leg), **SPI/CPI gauges**, a **time-status bar**, **planned-vs-actual by "
         "discipline**, and the **EV-vs-PV gap broken down to the activity codes** driving it — so the eye "
         "goes straight to where the money and the days are being lost."),
        (K.driver_line(F) + " That's the bar the dashboard lights up first." if K.driver_line(F) else
         "The discipline bars show where the gap concentrates so the board sees the one front, not an average."),
        (_cost_note(F)),
        ("You can switch between three presentation formats — **Executive**, **Midnight** and **Blueprint** "
         "— to match the audience, and it all runs offline with no model behind it, because the dashboard "
         "is **calculated, not written**."),
    ]
    advice = [
        "Lead the pack with the health verdict and the S-curve; the KPI tiles are the backup, not the story.",
        ("For the planner: read the EV-vs-PV gap-by-code panel — that's where the cost-weighted schedule slip "
         "localises to real activities, not just a headline." if role == 'planning' else
         "Send the Executive format to the board and keep the Blueprint one for the internal review."),
        K.go_deeper('EVM', 'For the underlying figures behind every tile'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'CPI', K.ratio(F.get('cpi'))),
                         K.ev('EVM', 'Actual vs planned',
                              f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t16q01(F, role):
    """One-page summary to drop in front of the board — composed, verdict first."""
    if not F.get('ok'):
        return _no_project(F)
    behind = (F.get('delay_days') or 0) > 0
    head = ("Compose it in **Reporting Studio** and lead with the **verdict, not a data dump** — a board "
            "wants the decision, not every metric.")
    body = [
        ("Here's the one-page skeleton, filled from your live numbers. **Headline:** " + _headline_position(F)
         + (f" We're forecasting {F.get('forecast_finish')} against the {F.get('baseline_finish')} baseline."
            if (behind and F.get('forecast_finish') and F.get('baseline_finish')) else "")),
        ("**One cause line:** " + (K.driver_line(F) if K.driver_line(F) else
                                    "the shortfall isn't concentrated in a single front on this file — read it front by front.")),
        ("**One recovery line:** " + _recovery_line(F)),
        ("**Keep money qualitative.** " + _cost_note(F) + " A board doesn't need PV/EV to two decimals; it "
         "needs to know cost isn't the fire."),
        ("**One ask.** Close on the single decision you need from them — the recovery resource, the "
         "re-sequence sign-off, the client conversation — not a list. One page, one verdict, one ask."),
    ]
    if not behind:
        body[1] = ("**One cause line:** the finish is holding on today's logic — so the board line is about "
                   "protecting it, not recovering it. Name the driving path you're protecting and the "
                   "near-critical front you're watching behind it.")
    advice = [
        "Put the verdict, the forecast date and the one ask above the fold; everything else is an appendix.",
        ("For the planner: keep a one-line logic-quality footnote (" + (_logic_caveat_line(F) or "logic clean")
         + ") so the board knows how bankable the date is." if role == 'planning' else
         "Don't bury the schedule story under financials — cost is holding, so it's a footnote here."),
        K.go_deeper('Reporting Studio', 'To compose and export the one-pager'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Actual vs planned',
                              f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish')),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t16q02(F, role):
    """What to tell the client this month — honest status with the cause behind the numbers."""
    if not F.get('ok'):
        return _no_project(F)
    behind = (F.get('delay_days') or 0) > 0
    head = ("**Be straight — their consultant will run their own P6.** Honesty on the number is what buys "
            "you credibility for the recovery conversation.")
    body = [
        ("Tell them where it stands: " + _headline_position(F)
         + (f" P6 forecasts {F.get('forecast_finish')} versus the {F.get('baseline_finish')} baseline."
            if (behind and F.get('forecast_finish') and F.get('baseline_finish')) else "")),
        ("Then give them the **cause**, because the number without the cause invites the worst reading. "
         + (K.driver_line(F) + " Make clear it's contained to that front — not the whole job."
            if K.driver_line(F) else
            "The slip isn't concentrated in one front on this file, so walk the top movers rather than "
            "naming a single cause.")),
        ("Confirm the slip is **genuine**. Run the **Consultant Review's** but-for check before the meeting "
         "so you can say the slip is real execution loss, not baseline logic or lag manipulation — if their "
         "consultant tests it, you've already tested it yourself."),
        (_recovery_line(F)),
        ("Balance it so it doesn't read as all bad: " + (
            "engineering/procurement and the fronts that are on or ahead of plan are holding — "
            if _on_plan_disciplines(F) else "the exposure is contained rather than across the whole job — ")
         + _cost_note(F)),
    ]
    advice = [
        "Lead with the honest number and the single cause; volunteer the recovery before they ask for it.",
        ("For the planner: bring the Update Analysis run and the Consultant Review to the table so every "
         "claim is evidenced, not asserted." if role == 'planning' else
         "Say the cause in one sentence a non-planner client can repeat back to their board."),
        K.go_deeper('Consultant Review, Update Analysis', 'For the evidence behind the status'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Actual vs planned',
                              f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('EVM', 'Delay', _delay_chip(F)),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('Consultant Review', 'Driving front', _driver_name(F))])


def t16q03(F, role):
    """Top three-to-five focus items this week to protect the end date."""
    if not F.get('ok'):
        return _no_project(F)
    dn = _driver_name(F) or 'the driving work front'
    head = ("Everything onto the **governing path** — the few things that actually move the finish, not the "
            "whole activity list. Here's the week, in priority order.")
    items = []
    dl = K.driver_line(F)
    items.append("**1. The driver — " + dn + ".** " + (
        dl + " This is the front the finish date is tracking; a recovery lever here (a night shift, a "
        "second crew) is the one that moves the date — size it in the What-if before you commit it."
        if dl else
        "Confirm the driving path in the Critical Path Analyzer, then put your best resource on it — it's "
        "the only work where a day saved is a day off the finish."))
    nf = F.get('neg_float_count')
    dpc = F.get('driving_path_count')
    second = []
    if nf:
        second.append(f"**{nf} activities on negative total float**" + (f" ({K.pct(F.get('neg_float_pct'))})" if F.get('neg_float_pct') is not None else ""))
    if dpc:
        second.append(f"a driving path of **{dpc} activities**")
    if second:
        items.append("**2. Protect the near-critical front** — " + " and ".join(second) + ". It turns "
                     "critical the moment the driver slips further, so don't let it drift while you chase item 1.")
    else:
        items.append("**2. Protect the near-critical front.** Watch the chain sitting just behind the driver "
                     "on total float — it becomes the next critical path the moment the driver loses more days.")
    cav = _logic_caveat_line(F)
    if cav:
        items.append("**3. Clean the logic so next update reads true** — close the " + cav + ". Until they're "
                     "fixed the forecast can drift and the client can pick holes in it.")
    else:
        items.append("**3. Keep the logic clean** — no material out-of-sequence or open-end flags right now, "
                     "so protect that: don't status work out of order this period.")
    items.append("**4. Don't leak crews onto float work.** Every hour spent on comfortable, high-float scope "
                 "is an hour not spent on the governing path — that's how a recoverable slip becomes a fixed one.")
    body = ["The rule for the week: " + _headline_position(F) + " so the team's effort has to be spent where "
            "it changes that, not spread evenly."]
    body.extend(items)
    advice = [
        f"Build the three-week look-ahead around the **{dn}** chain and hang the recovery levers off it.",
        ("For the planner: sort the look-ahead by total float ascending — negative and near-zero float first — "
         "so the crew list matches the driving logic, not the bar order." if role == 'planning' else
         "Give each item an owner and a target this week; review them at the next look-ahead, not at month end."),
        K.go_deeper('Critical Path Analyzer, Update Analysis', 'For the driving path and the overdue-work list'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Critical Path Analyzer', 'Driving front', dn),
                         K.ev('Float', 'Negative-float activities', nf),
                         K.ev('CPLI', 'Driving-path activities', dpc),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t16q04(F, role):
    """Key risks this month to flag to management — float, weather, logic, buildability."""
    if not F.get('ok'):
        return _no_project(F)
    dn = _driver_name(F) or 'the driving work front'
    behind = (F.get('delay_days') or 0) > 0
    head = "Four things to escalate — the threats that can move the finish, ranked by what they'd cost."
    body = []
    body.append("**1. The finish date is single-threaded through " + dn + ".** " + (
        f"It's carrying the delay ({K.delay_phrase(F)}), and any further slip on it pushes the forecast out "
        "again — there's no parallel front absorbing it." if behind else
        "It's the governing path, so it's the one place a slip converts straight into a finish slip."))
    nf = F.get('neg_float_count')
    if nf:
        body.append(f"**2. A second front is close to going critical** — **{nf} activities** carry negative "
                    "total float already"
                    + (f" ({K.pct(F.get('neg_float_pct'))} of the schedule)" if F.get('neg_float_pct') is not None else "")
                    + ". They're a short slip away from becoming a second driving path, which is how a "
                    "one-front problem becomes a two-front one.")
    else:
        body.append("**2. Watch the near-critical work.** No mass of negative float on this file, but the "
                    "chain just behind the driver is where a second critical front would appear — flag it as "
                    "the thing to monitor, not yet a fire.")
    body.append("**3. Weather exposure on the driving path.** If any of the governing work is weather-sensitive "
                "(marine, earthworks, external trades), a bad-weather season hits the finish directly — run the "
                "**Calendar Audit's weather check** for the site type before you commit dates, so the exposure "
                "is quantified rather than assumed.")
    cav = _logic_caveat_line(F)
    if cav:
        body.append("**4. Schedule quality.** " + cav + " still to clean up before the numbers are fully "
                    "trustworthy — flag it so management knows the forecast has a known margin of error until "
                    "the logic is scrubbed.")
    else:
        body.append("**4. Buildability.** The logic reads clean, so the residual risk is a valid-but-unbuildable "
                    "sequence — run the Constructability Review on the driving chain so a physically impossible "
                    "overlap isn't flattering the date.")
    advice = [
        f"Escalate the **{dn}** exposure as the headline risk with an owner and a mitigation date, not a RAG dot.",
        ("For the planner: pair each risk with its evidence — float grade, weather day-count, DCMA logic grades — "
         "so management sees the basis, not just the colour." if role == 'planning' else
         "Give management the mitigation you're already running against each risk, so it reads as managed."),
        K.go_deeper('Schedule Health Review, Weather Impact', 'For the graded health and the weather exposure'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Critical Path Analyzer', 'Finish driver', dn),
                         K.ev('Float', 'Negative-float activities', nf),
                         K.ev('Float', 'Float grade', F.get('float_grade')),
                         K.ev('Out-of-sequence', 'Activities', F.get('oos_count'))])


def t16q05(F, role):
    """Good news to lead the client meeting with — the balancing half of the status."""
    if not F.get('ok'):
        return _no_project(F)
    head = "Lead with what's **holding** — a balanced report is a believed report, and there's a real story here."
    body = []
    onp = _on_plan_disciplines(F)
    if onp:
        names = ", ".join(f"**{d.get('name')}**" for d in onp[:3])
        body.append("The problem is **contained, not general**. " + names + " are on or ahead of their planned "
                    "curve — so the exposure is one work front, not the whole job. That's the first thing to say, "
                    "because it reframes the delay from 'the project is failing' to 'one front needs help'.")
    else:
        body.append("The problem is **contained to the driving front**, not spread across every discipline — "
                    "so lead by naming what the delay is *not*: it isn't an across-the-board collapse, it's one "
                    "front carrying it.")
    dn = _driver_name(F)
    if dn:
        body.append(f"Say it plainly: the shortfall lives in **{dn}**, and everything feeding and following it "
                    "is broadly where it should be — the client hears a managed, localised problem instead of a "
                    "runaway one.")
    body.append(_cost_note(F) + " For the client, that's the good-news line on money: it isn't the fire.")
    body.append("And the recovery isn't hypothetical — " + _recovery_line(F) + " So you can promise a credible "
                "route back, on P6-verified dates, rather than a hope.")
    body.append("This is the mirror image of the status you owe them (the honest slip and its cause) — lead the "
                "meeting on this, then land the delay against it, so the room hears 'contained and recoverable' "
                "before it hears the number.")
    advice = [
        "Open on the contained scope and the credible recovery; then give the honest slip — order matters.",
        ("For the planner: back the 'on plan' claim with the discipline bars so it's evidenced, not spin."
         if role == 'planning' else
         "Keep it to two good-news lines — contained scope, cost holding — then move to the ask."),
        K.go_deeper('Update Analysis, EVM', 'For the discipline-by-discipline read behind the good news'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'CPI', K.ratio(F.get('cpi'))),
                         K.ev('EVM', 'On-plan fronts', (", ".join(d.get('name') for d in onp[:3]) if onp else None)),
                         K.ev('EVM', 'Contained driver', dn)])


def t16q06(F, role):
    """Draft the monthly schedule narrative paragraph — plain English from the real numbers."""
    if not F.get('ok'):
        return _no_project(F)
    behind = (F.get('delay_days') or 0) > 0
    dd = F.get('data_date')
    # Compose the paragraph from F only.
    parts = []
    parts.append(f"At data date {dd}, the project is {K.pct(F.get('actual_pct'))} complete against a planned "
                 f"{K.pct(F.get('planned_pct'))}")
    gp = _gap_points(F)
    if gp:
        parts.append("— " + gp.replace("**", ""))
    parts.append(f", SPI {K.ratio(F.get('spi'))}, CPI {K.ratio(F.get('cpi'))}.")
    if behind and F.get('forecast_finish') and F.get('baseline_finish'):
        parts.append(f" P6 forecasts completion {F.get('forecast_finish')} versus the {F.get('baseline_finish')} "
                     f"baseline, {K.wd(F.get('delay_days'))} late.")
    elif not behind and F.get('delay_days') is not None:
        parts.append(f" The forecast finish is holding against the {F.get('baseline_finish') or 'baseline'} baseline.")
    driver = K.main_driver(F)
    if driver:
        parts.append(f" The slip is driven by {driver.get('name')} ({driver.get('actual')}% done against "
                     f"{driver.get('planned')}% planned); the other fronts remain broadly on plan.")
    parts.append(" Recovery options are under evaluation and being sized in the What-if before commitment.")
    paragraph = "“" + "".join(parts).replace("  ", " ").replace(" ,", ",").replace(" .", ".") + "”"

    head = "Here's the monthly narrative paragraph, composed straight from your live numbers."
    body = [
        paragraph,
        ("That's the plain-English version a non-planner can read aloud — a dated position, a single named "
         "cause, and an honest recovery posture. It says nothing the numbers don't support."),
        ("Note the deliberate restraint on two points: the recovery day-count is left to the What-if (I won't "
         "state recovered days the schedule hasn't been re-run for), and cost stays a one-liner because " + _cost_note(F).split(" — but")[0].lower() + "."),
        ("**Reporting Studio** composes and exports this paragraph straight from the same live figures, so the "
         "narrative in the report always matches the KPIs beside it — no hand-typed number to drift out of date."),
    ]
    advice = [
        "Drop this at the top of the monthly report, above the tables — the paragraph is the story, the tables are the proof.",
        ("For the planner: append the logic-quality caveat (" + (_logic_caveat_line(F) or "logic clean")
         + ") so the reader knows how firm the forecast is." if role == 'planning' else
         "Keep it to these three sentences; a longer narrative buries the one cause."),
        K.go_deeper('Reporting Studio', 'To compose and export the narrative with the numbers'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Actual vs planned',
                              f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('EVM', 'SPI / CPI', f"{K.ratio(F.get('spi'))} / {K.ratio(F.get('cpi'))}"),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish')),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t16q07(F, role):
    """S-curve of planned vs actual vs forecast for the client report."""
    if not F.get('ok'):
        return _no_project(F)
    behind = (F.get('delay_days') or 0) > 0
    head = ("**Yes — the three-way curve is the one visual the client actually reads.** It says in a glance "
            "what a table of KPIs says in a page.")
    body = [
        ("The three legs, grounded in your numbers: the **planned** curve rides up to "
         f"**{K.pct(F.get('planned_pct'))}** at the {F.get('data_date')} data date; **actual** sits at "
         f"**{K.pct(F.get('actual_pct'))}**"
         + (f" — the vertical gap between them is your {_gap_points(F)}" if _gap_points(F) else "")
         + "; and the **forecast** leg runs on to "
         + (f"**{F.get('forecast_finish')}**, {K.wd(F.get('delay_days'))} past the {F.get('baseline_finish')} "
            "baseline finish." if (behind and F.get('forecast_finish') and F.get('baseline_finish')) else
            "the forecast finish, holding against the baseline.")),
    ]
    if F.get('has_history'):
        n = len(F.get('history') or [])
        body.append(f"You've got **{n} snapshots** stored, so the actual leg plots as a real trajectory across "
                    "the updates, not a single point — the client sees the shape of the slip developing, which "
                    "is far more persuasive than one month's number.")
    else:
        body.append("This file is a single snapshot, so the actual leg anchors on today's point against the "
                    "planned curve rather than a multi-month trajectory — still the right visual, just import "
                    "the earlier updates when you can and the actual line fills in behind it.")
    body.append("This is the same physical-progress curve that reads the schedule story cleanly here. Keep the "
                "**cost** S-curve (PV/EV) qualitative unless they ask for it — " + _cost_note(F).split(" — but")[0].lower()
                + ", so the physical-progress curve carries the message without a cost sub-plot muddying it.")
    body.append("Pair it with one sentence of interpretation so it isn't left to read itself: the gap is the "
                + (K.driver_line(F).replace("The shortfall is being carried by ", "work on ") if K.driver_line(F)
                   else "shortfall on the driving front") + " — the curve shows the size, the sentence names the cause.")
    advice = [
        "Pull the curve from the EVM / dashboard S-curve panel and drop it straight into the report — don't redraw it by hand.",
        ("For the planner: cross-check the forecast leg against the Consultant Review's dated finish so the "
         "curve's endpoint matches the driving-path analysis." if role == 'planning' else
         "Add the one interpretation sentence under the chart; a curve with no caption gets misread."),
        K.go_deeper('EVM, Consultant Review', 'For the curve data and the dated forecast behind it'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Planned vs actual',
                              f"{K.pct(F.get('planned_pct'))} vs {K.pct(F.get('actual_pct'))}"),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish')),
                         K.ev('EVM', 'Delay', _delay_chip(F)),
                         K.ev('Trend', 'Snapshots on file', (len(F.get('history') or []) or None))])


def t16q08(F, role):
    """Red-amber-green health view for the steering committee — an honest gap."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("**Honestly, the tool can't auto-generate a RAG scorecard yet** — automatic red-amber-green scoring "
            "off the metrics isn't a shipped control. But I can hand you every ingredient that decides the colours.")
    behind = (F.get('delay_days') or 0) > 0
    # The ingredients, grounded.
    sched_colour = "a hard **RED**" if (behind and (F.get('pace_pct') or 100) < 90) else (
        "an **AMBER**" if (behind or (F.get('pace_pct') or 100) < 100) else "a **GREEN**")
    cpi = F.get('cpi')
    cost_colour = "**GREEN**" if (cpi is not None and cpi >= 0.97) else ("**AMBER**" if cpi is not None else "**grey** (not derivable)")
    body = [
        ("**Schedule:** SPI ≈ " + K.ratio(F.get('spi')) + f" and delay {_delay_chip(F)} — that's " + sched_colour
         + " on schedule; the pace and the finish position are both in it."),
        ("**Cost:** CPI " + K.ratio(cpi) + " — " + cost_colour + " on cost, but flag the caveat that cost is "
         "derived from % complete here, so the cost light will almost always sit green/amber and the schedule "
         "light is the one that matters."),
        ("**Logic quality:** the DCMA-style read gives you the third dimension — "
         + (_logic_caveat_line(F) + " (amber until cleaned)" if _logic_caveat_line(F) else "no material logic flags (green)")
         + (f", float graded **{F.get('float_grade')}**" if F.get('float_grade') else "") + ". Colour it from those grades."),
        ("So the committee sheet writes itself from three lights — schedule, cost, logic quality — you just set "
         "the thresholds and colour them by hand for now. A **standing RAG control** keyed off the EVM and "
         "health thresholds (so it's one click and consistent update to update) is exactly the kind of thing "
         "that would need building before it's automatic — I'd rather tell you that than dress a manual read up "
         "as a shipped scorecard."),
    ]
    advice = [
        "Set your own thresholds once (e.g. SPI <0.9 red, <1.0 amber) and reuse them every month so the colours mean the same thing.",
        ("For the planner: drive the logic light off the Schedule Health Review grades so it's defensible, not a feel." if role == 'planning'
         else "Keep it to three lights on one row — schedule, cost, logic — a committee won't read more."),
        K.go_deeper('Schedule Health Review, EVM', 'For the graded health and EVM numbers that set the colours'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay', _delay_chip(F)),
                         K.ev('EVM', 'CPI', K.ratio(cpi)),
                         K.ev('Schedule Health Review', 'Float grade', F.get('float_grade'))])


def t16q09(F, role):
    """Portfolio view across projects + LD exposure — both honest gaps today."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("**Two asks, and I have to be straight — neither is groundable in the tool today.** Here's exactly "
            "where each stands and what I *can* give you instead.")
    behind = (F.get('delay_days') or 0) > 0
    body = [
        ("**The portfolio view** — comparing all your projects side by side — isn't in-app yet. It arrives with "
         "the **Power BI live dashboards** that are in progress; the DB already stores every project and snapshot "
         "for it, but the cross-project comparison surface is still being built. For now this chat is a "
         "**single-project read** of the schedule you've loaded."),
        ("**LD / liquidated-damages exposure** I can't compute at all: the tool reads P6 milestone constraints, "
         "**not your contract completion dates or penalty rates**. Converting a slip into a pounds-per-day LD "
         "figure needs the contract terms ingested — dates, sectional obligations, the rate table — and that "
         "isn't built. I won't manufacture a damages number off data the file doesn't hold."),
        ("What I *can* give you is the **indicator** the LD conversation starts from: this project is currently "
         + (f"forecasting **{K.wd(F.get('delay_days'))} late** ({F.get('forecast_finish')} against the "
            f"{F.get('baseline_finish')} baseline finish)." if (behind and F.get('forecast_finish')) else
            "at " + K.delay_phrase(F) + ".") + " Reconcile that against the actual contract completion date — "
         "if that baseline is your contractual date, that's the exposure window; if it isn't, the real margin "
         "may differ. Formal contract-date ingest is the known gap here."),
        ("So: single-project today, portfolio when Power BI lands, and LD only once contract terms can be read "
         "in. Everything above the LD line is grounded; the damages figure itself is not, and I've said so "
         "rather than guess."),
    ]
    advice = [
        "Take the +delay indicator to the commercial team and let them apply the contract's LD rate — that calculation is theirs, on their terms.",
        ("For the planner: keep exporting each project's snapshots so the portfolio dashboard has the history the day it ships."
         if role == 'planning' else
         "For a portfolio view now, compare the single-project reads by hand until the Power BI export is released."),
        K.go_deeper('Power BI live dashboards', 'For the cross-project view being built'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'This project delay', _delay_chip(F)),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish')),
                         K.ev('Power BI', 'Portfolio view', 'in progress'),
                         K.ev('Contract', 'LD computation', 'not built (no contract-date ingest)')])


ANSWERS = {
    't16q00': t16q00, 't16q01': t16q01, 't16q02': t16q02, 't16q03': t16q03, 't16q04': t16q04,
    't16q05': t16q05, 't16q06': t16q06, 't16q07': t16q07, 't16q08': t16q08, 't16q09': t16q09,
}
