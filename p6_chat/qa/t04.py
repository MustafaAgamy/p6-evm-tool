"""Theme 4 — Recovery & Acceleration.

How much time can be clawed back, by which lever, and at what cost — all resolved through
the P6 F9 keystone. Every answer is grounded in FACTS: the recovery gap is the signed
``delay_days`` measured against the baseline finish; the front any acceleration must land on
is the weighted driver (weight × gap, via ``K.main_driver`` / ``K.driver_line``), never the
largest raw gap; the near-critical front waiting behind it is the second-ranked driver.

The honest spine of the whole theme: the schedule holds the *gap*, but the *day-gain of any
individual lever* (night shift, extra crew, crash, 6-day week) is a finish-sensitivity result
— it comes from building the change in the What-if and running F9, not from a number sitting
in the file. So these answers quantify the gap and name the front, then route the exact
lever figures to the What-if / Critical Path Analyzer / Productivity Intelligence rather than
inventing a day-gain. Costs-per-day and market availability aren't in the P6 file at all and
are called out as honest gaps.
"""
from . import _kit as K


# ── shared, None-safe helpers (run at call time, no import side effects) ─────────

def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can size the "
              "recovery gap and tell you which front to accelerate — offline, nothing leaves your PC."])


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _behind(F):
    d = _num(F.get('delay_days'))
    return d is not None and d > 0


def _ranked_drivers(F):
    """Disciplines dragging the finish, ranked by weight × gap (the real recovery order),
    not by raw gap. Returns a list of discipline dicts, biggest driver first."""
    scored = []
    for d in (F.get('disciplines') or []):
        gap = _num(d.get('gap')) or 0
        wgt = _num(d.get('weight')) or 0
        if gap <= 0:
            continue
        scored.append((gap * wgt, d))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [d for _, d in scored]


def _driver_name(F):
    d = K.main_driver(F)
    return d.get('name') if d else None


def _driver_phrase(F):
    return _driver_name(F) or "the driving work front"


def _second_line(F):
    """A sentence naming the near-critical front waiting behind the driver, or ''."""
    ranked = _ranked_drivers(F)
    if len(ranked) < 2:
        return ''
    d = ranked[1]
    return (f"Waiting right behind it is **{d.get('name')}** ({d.get('actual')}% done vs "
            f"{d.get('planned')}% planned, ~{round((d.get('weight') or 0)*100)}% of the project by "
            f"weight) — the front most likely to take over the path once the driver is pulled in.")


def _gap_value(F):
    """Signed recovery-gap chip value."""
    d = _num(F.get('delay_days'))
    if d is None:
        return None
    d = round(d)
    if d > 0:
        return f"{d} wd to claw back"
    if d < 0:
        return f"{abs(d)} wd of float in hand"
    return "on the date"


def _gap_sentence(F):
    """One paragraph sizing the recovery gap, straight from the signed delay."""
    d = _num(F.get('delay_days'))
    if d is None:
        return ("The size of the recovery gap isn't derivable from this file — there's no finish "
                "milestone I can measure against a baseline. Load a schedule with a finish milestone "
                "(or read the driving path directly) and I'll put a working-day number on what has to "
                "be clawed back.")
    d = round(d)
    if d > 0:
        tail = ''
        if F.get('forecast_finish') and F.get('baseline_finish'):
            tail = (f" — the forecast finish sits at about **{F['forecast_finish']}** against a "
                    f"**{F['baseline_finish']}** baseline")
        return (f"The gap to close is about **{K.wd(d)}** (~{K.weeks(d)}){tail}. That is the number "
                "any recovery plan has to erase — everything else is means to that end.")
    if d < 0:
        return (f"There's no recovery gap on this schedule — the forecast finish is about "
                f"**{K.wd(d)}** ahead of the baseline. So this is about protecting the margin you "
                "have, not clawing time back.")
    return ("You're sitting **on the planned finish date** — no gap to recover. The job here is to "
            "hold the date, not chase it.")


def _whatif_open():
    f = K.FEATURE['What-if / scenario engine']
    return f"**{f['open']}** — it gives you {f['does']}"


def _neg_float_corroboration(F):
    nf = F.get('neg_float_count')
    if not nf:
        return ''
    return (f"The network backs this up: **{nf} activities** ({K.pct(F.get('neg_float_pct'))}) are on "
            "negative total float, and the chain that sets the finish is among them with no spare float left — "
            "so every week that chain waits adds straight onto the gap.")


# ── answers ──────────────────────────────────────────────────────────────────────

def t04q00(F, role):
    """Recovery gap in days, and whether the milestone is still reachable if we start now."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    if _behind(F):
        head = (f"You need to claw back about **{K.wd(F.get('delay_days'))}** — and no single lever "
                "closes a gap that size, so recovery has to start this week.")
    elif _num(F.get('delay_days')) is not None and _num(F.get('delay_days')) < 0:
        head = "There's no gap to claw back — the finish is forecasting ahead of the baseline."
    elif _num(F.get('delay_days')) == 0:
        head = "You're on the finish date — nothing to recover, everything to protect."
    else:
        head = "I can't size the recovery gap from this file yet — the finish milestone needs confirming."
    body = [
        _gap_sentence(F),
        ("Can you still hit it if you move now — that's the real question, and here's the honest read: "
         "the *day-gain of each lever* (night shift, an extra crew, crashing, a 6-day week) isn't a "
         "number sitting in the file. It comes from building the change onto the driving activities and "
         "running **F9** in the What-if. What the numbers do tell me plainly is that a gap this size is "
         "not closed by one lever — you stack levers on the governing front and re-run.")
        if _behind(F) else
        ("Because the finish is holding, the task is to keep it there: protect the driving path and watch "
         "the near-critical fronts so none of them turns the clock against you."),
        (K.driver_line(F) + " That is where every recovered day has to come from — a day bought on a "
         "floated front is a day the finish never sees.") if K.driver_line(F) else
        (f"Acceleration only counts on the governing path — today that runs through {_driver_phrase(F)}; "
         "buy time anywhere else and the finish won't move."),
    ]
    ncf = _neg_float_corroboration(F)
    if ncf:
        body.append(ncf)
    if tech and _behind(F):
        tr = (F.get('trend') or {}).get('direction')
        body.append("Planner's note: " + (
            "the gap grew since the last update — the recovery has to out-run that drift, not just match today's "
            "number." if tr == 'worse' else
            "one update can't show whether the gap is growing — but while the chain that sets the finish isn't "
            "moving, every week it waits adds to it. The next update will show the rate; plan the recovery to "
            "out-run it, not just match today's number."))
    advice = []
    if _behind(F):
        advice.append(f"Build the recovery scenario now: stack levers on **{_driver_phrase(F)}** in the "
                      "What-if and re-run F9 before you commit to any date in a meeting.")
    else:
        advice.append(f"Keep the driving path ({_driver_phrase(F)}) protected and re-check the near-critical "
                      "fronts each update so the margin doesn't quietly erode.")
    advice.append(K.go_deeper(
        'What-if / scenario engine, Critical Path Analyzer', 'For the exact days each lever buys'))
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Recovery gap', _gap_value(F)),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish')),
                         K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('Float', 'Negative-float activities', F.get('neg_float_count'))])


def t04q01(F, role):
    """Fastest lever to pull the finish back — crashing, extra crews, or a 6-day week."""
    if not F.get('ok'):
        return _no_project(F)
    head = (f"The fastest lever is whichever one lands on the driving front — **{_driver_phrase(F)}** — "
            "and nowhere else." if _behind(F) or K.main_driver(F) else
            "With the finish holding, the fastest lever is the one you keep in reserve for the front that slips first.")
    body = [
        ("The finish is controlled by the driving path, so the head-to-head only matters on the "
         "governing chain. Crashing (piling on hours/resources to shorten a duration) and a second "
         "crew both attack duration directly; a 6-day week or a night shift add calendar time. Any of "
         "them buys days **only** on the driving front — a day gained on a floated activity is invisible "
         "to the finish."),
        (K.driver_line(F) if K.driver_line(F) else
         f"Today the governing work runs through {_driver_phrase(F)} — that's where any of the three has to bite."),
        ("Which of the three is fastest is a What-if result, not something I read off the loaded numbers: "
         "each lever gets built onto the driving activities and run through F9, then compared by days "
         "gained. I won't quote you a day-count I haven't actually computed on your schedule."),
        ("One caveat that decides the calendar levers: a 6-day week or night shift only computes if the "
         "driving activities actually sit on a 6-day / shift calendar in P6 — otherwise F9 never sees the "
         f"extra hours and you accelerate on paper only. Your file carries {F.get('calendar_count')} "
         "calendars; the Calendar Audit shows which pattern each front is on."
         if F.get('calendar_count') else
         "One caveat that decides the calendar levers: a 6-day week or night shift only computes if the "
         "driving activities sit on a 6-day / shift calendar in P6 — otherwise F9 never sees the extra "
         "hours and you accelerate on paper only."),
    ]
    return K.A(head, body,
               advice=[f"Rank all three against **{_driver_phrase(F)}** specifically in the What-if — build "
                       "each, run F9, take the biggest day-gain for the least disruption.",
                       "Edit the P6 calendar first for any 6-day / shift lever (Calendar Audit), or the gain won't compute.",
                       K.go_deeper('What-if / scenario engine', 'For the day-by-day comparison')],
               evidence=[K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('EVM', 'Recovery gap', _gap_value(F)),
                         K.ev('Calendar Audit', 'Calendars in file', F.get('calendar_count'))])


def t04q02(F, role):
    """Crashing the concrete works by two weeks — how many days the finish actually moves."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("It moves the finish only if that concrete sits on the governing path — and today the "
            f"driver is **{_driver_phrase(F)}**, not general concrete.")
    body = [
        (K.driver_line(F) if K.driver_line(F) else
         f"The governing work currently runs through {_driver_phrase(F)}."),
        ("So the honest answer is conditional: crash concrete that carries float and the finish won't "
         "move a single day, however hard you compress it. The exception is any concrete activity that "
         "sits **on** the driving chain — a deck pour or a foundation feeding the critical front — where "
         "two weeks off the duration does flow through to completion."),
        ("The exact day-move from a two-week compression is a finish-sensitivity result, and I don't "
         "eyeball those. Give me the specific activity IDs and I'll compress them by two weeks in the "
         "What-if and hand you the **F9-exact** finish move — including whether the path then jumps to "
         "another front."),
        ("Worth stating plainly: the delay figure I hold is P6's own (the finish milestone after your F9); "
         "the crash-response figure has to come from a new F9 run too, not from my estimate, before you put "
         "it in front of the client."),
    ]
    return K.A(head, body,
               advice=["Send me the concrete activity IDs and I'll model the two-week crash to the exact day.",
                       K.go_deeper('What-if / scenario engine, Critical Path Analyzer',
                                   'To confirm those activities are even on the driving path')],
               evidence=[K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('EVM', 'Recovery gap', _gap_value(F))])


def t04q03(F, role):
    """Activities with the most recovery per day, and the minimum set to accelerate."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    head = (f"Recovery-per-day only comes off the governing path — so the minimum set starts with "
            f"**{_driver_phrase(F)}**." if K.main_driver(F) else
            "With no front dragging the finish, there's no acceleration set to build — this is a protect-the-path job.")
    body = [
        ("Only activities on the driving chain hand days back to the finish. Everything with float can be "
         "left alone — accelerating it spends money and moves nothing. So the ranking is by finish "
         "sensitivity, not by how far behind an activity looks in isolation."),
        (K.driver_line(F) if K.driver_line(F) else
         f"Start on {_driver_phrase(F)} — that's the front carrying the finish today."),
    ]
    sec = _second_line(F)
    if sec:
        body.append(sec + " That's why the minimum set is two-deep: the driver first, the next front right "
                          "behind it — accelerate the driver alone and this one takes over the delay.")
    ncf = _neg_float_corroboration(F)
    if ncf:
        body.append(ncf)
    body.append("The exact rank — each driving activity by how many finish-days it returns per day pulled "
                "in — is a What-if / Critical Path Analyzer output. That's the tool for a least-effort plan: "
                "accelerate the fewest activities for the most days back.")
    if tech:
        body.append("Planner's note: rank on total-float sensitivity, not raw variance — an activity at "
                    "TF 0 with a small slip returns more finish-days than one deep in negative variance but "
                    "off the longest path.")
    return K.A(head, body,
               advice=[f"Rank the driving activities on **{_driver_phrase(F)}** by finish sensitivity in the "
                       "What-if, then work the top handful — not the whole front.",
                       K.go_deeper('Critical Path Analyzer, What-if / scenario engine',
                                   'For the sensitivity ranking')],
               evidence=[K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('EVM', 'Recovery gap', _gap_value(F)),
                         K.ev('Float', 'Negative-float activities', F.get('neg_float_count'))])


def t04q04(F, role):
    """Second crew on steel erection — days gained and whether it's realistic vs norms."""
    if not F.get('ok'):
        return _no_project(F)
    head = (f"First confirm steel is even on the driving path — today the driver is **{_driver_phrase(F)}**, "
            "not steel — then reality-check the crew against the norms.")
    body = [
        ("Two parts, and the first decides whether the second matters. Steel erection only moves the "
         "finish if it sits on the governing chain. " +
         (K.driver_line(F) if K.driver_line(F) else
          f"Right now that chain runs through {_driver_phrase(F)}.") +
         " If steel carries float, a second crew shortens steel and moves the finish not at all — you'd be "
         "paying for acceleration the milestone never sees."),
        ("If it is critical, the day-gain from a second crew is a What-if result — built onto the steel "
         "activities and run through F9. I won't put a day-count on it off the file."),
        ("Then the norms check, which is where crews get oversold: a second crew rarely doubles output. "
         "Access, crane time and a congested work-face eat into the second crew's productivity, so one "
         "plus one is usually well under two. Give me the steel quantities and Productivity Intelligence "
         "tests the split against the norm instead of assuming a clean doubling."),
    ]
    return K.A(head, body,
               advice=["Confirm steel is on the driving path first — if it carries float, don't buy the crew.",
                       "Send the steel quantities and I'll test the crew split against the productivity norms.",
                       K.go_deeper('What-if / scenario engine, Productivity & Resource Intelligence',
                                   'For the crew-driven day-gain')],
               evidence=[K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('EVM', 'Recovery gap', _gap_value(F))])


def t04q05(F, role):
    """6-day week vs night shift — days each, and whether the P6 calendar must change first."""
    if not F.get('ok'):
        return _no_project(F)
    head = "Both are calendar levers — and neither computes until you edit the P6 calendar first."
    body = [
        ("The day-gain of a night shift versus a 6-day week is a What-if result on the driving front — I "
         "build each onto the driving activities and run F9, then compare. I won't quote one I haven't "
         "modelled on your schedule."),
        ("The load-bearing point comes before the numbers, though: the activities you want to accelerate "
         "must already sit on a 6-day or shift calendar in P6. If they're on a 5-day calendar and you "
         "don't change it, F9 never sees the extra hours — you accelerate on paper, the finish doesn't "
         "move, and the plan quietly lies to you." +
         (f" Your file carries **{F.get('calendar_count')} calendars**; the Calendar Audit shows which "
          "pattern each front is on so you change the right one." if F.get('calendar_count') else "")),
        (f"And both only help if they land on the governing front — {_driver_phrase(F)}. A longer week on "
         "a floated activity buys nothing. So the order is: change the calendar for the *driving* "
         "activities, then re-run F9 and compare the two levers head-to-head."),
    ]
    return K.A(head, body,
               advice=["Edit the P6 calendar for the driving activities first (Calendar Audit), then model both levers.",
                       K.go_deeper('What-if / scenario engine, Calendar Audit',
                                   'For the days each calendar lever buys')],
               evidence=[K.ev('Calendar Audit', 'Calendars in file', F.get('calendar_count')),
                         K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('EVM', 'Recovery gap', _gap_value(F))])


def t04q06(F, role):
    """Fast-track by overlapping engineering/procurement with construction — and is it constructable."""
    if not F.get('ok'):
        return _no_project(F)
    oos = F.get('oos_count')
    head = (f"Overlapping engineering and procurement won't move a finish driven by **{_driver_phrase(F)}** "
            "— the delay is on site, not in the office.")
    body = [
        (K.driver_line(F) if K.driver_line(F) else
         f"The governing work runs through {_driver_phrase(F)} — site execution, not the front end."),
        ("Engineering and procurement usually carry little schedule weight here, so fast-tracking the "
         "front end buys little when the driver is site work. Where overlap genuinely helps a downstream "
         "front, I'll model it in the What-if — but it has to earn its place on the governing path, not "
         "just look busy."),
        (f"Then the constructability catch: forcing overlap manufactures out-of-sequence work, and you "
         f"already carry **{oos} out-of-sequence activities**"
         + (f" ({K.pct(F.get('oos_pct'))})" if F.get('oos_pct') is not None else "")
         + (f", including {F.get('critical_oos')} on the critical path" if F.get('critical_oos') else "")
         + ". Pile more overlap on and a paper gain turns into rework — which loses more time than it saves. "
           "The Constructability review has to clear any re-sequence before it goes in the plan."
         if oos else
         "Then the constructability catch: forcing overlap manufactures out-of-sequence work, so any "
         "re-sequence has to clear the Constructability review before it goes in the plan — a paper gain "
         "that turns into rework loses more time than it saves."),
        f"Blunt version: fix the driving front ({_driver_phrase(F)}); don't re-sequence the office to chase a date it doesn't control.",
    ]
    return K.A(head, body,
               advice=["Model any overlap in the What-if, then clear it through the Constructability review before committing.",
                       K.go_deeper('What-if / scenario engine, Constructability Review',
                                   'To test the overlap and its buildability')],
               evidence=[K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('Out-of-sequence', 'Activities', oos),
                         K.ev('Out-of-sequence', 'On critical path', F.get('critical_oos'))])


def t04q07(F, role):
    """Does crashing just shove the delay downstream, and where does the critical path jump next."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    ranked = _ranked_drivers(F)
    nxt = ranked[1].get('name') if len(ranked) > 1 else None
    head = (f"Good instinct — that's exactly the trap. Crash **{_driver_phrase(F)}** far enough and the "
            f"path jumps to **{nxt}**." if nxt else
            "Good instinct — that's the trap: crash one front and the path can simply reappear on the next.")
    body = [
        ("Local acceleration doesn't always remove the bottleneck; sometimes it just relocates it. Pull "
         "the current driver in and the finish only improves until the next front runs out of float — "
         "then that front becomes the new critical path and your recovered days evaporate."),
        (_second_line(F) if _second_line(F) else
         f"On this schedule the front waiting behind {_driver_phrase(F)} is the one to watch — the What-if "
         "names it the moment you model the first cut."),
    ]
    ncf = _neg_float_corroboration(F)
    if ncf:
        body.append(ncf + " Several fronts under pressure is exactly the setup where the path hops.")
    body.append("That's why I never accelerate one front in isolation. When I run the What-if I look at "
                "where the next controlling chain appears after each cut — so you're spending money to "
                "*remove* the bottleneck, not to move it one activity down the network.")
    if tech:
        body.append("Planner's note: watch the near-zero total-float band, not just TF 0 — the fronts a "
                    "few days off the longest path are the ones that go critical first when you crash the driver.")
    return K.A(head, body,
               advice=["Name the activity you'd crash and I'll show you where the path lands next before you spend a rupee.",
                       K.go_deeper('What-if / scenario engine, Critical Path Analyzer',
                                   'For the path after each cut')],
               evidence=[K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('Critical Path Analyzer', 'Next front', nxt),
                         K.ev('Float', 'Negative-float activities', F.get('neg_float_count'))])


def t04q08(F, role):
    """Days recoverable before hitting a resource ceiling or overtime fatigue."""
    if not F.get('ok'):
        return _no_project(F)
    head = "The schedule models the time gain — but the ceiling itself is half a judgment call the plan can only part-ground."
    body = [
        ("Straight answer, in two halves. The half the tool grounds: the What-if shows diminishing "
         "returns directly — each added crew returns fewer finish-days than the last as the work-face "
         "congests, so there's a point where a third crew barely beats a second. And Productivity "
         "Intelligence flags where the *implied* output has run past the norms — that's the paper ceiling, "
         "the point where the plan is assuming a productivity nobody actually achieves."),
        ("The half the plan can't ground: sustained-overtime fatigue and the true crew cap on this site "
         "are field knowledge, not numbers in the P6 file. A 6-day week for eight weeks doesn't hold the "
         "output of week one — but by how much is a call you and the CM make, not the schedule."),
        (f"So the honest maximum recovery is: push levers on {_driver_phrase(F)} until the What-if shows "
         "the day-gain flattening and Productivity Intelligence flags the norm breach — that's the "
         "schedule's ceiling. Give me the manpower limit you can genuinely hold on site and I'll find "
         "where the extra hours stop paying inside that limit."),
        ("I'd rather hand you that honest boundary than a confident number the site can't deliver — a "
         "recovery plan built on unachievable output just moves the bad news to the next update."),
    ]
    return K.A(head, body,
               advice=["Tell me the crew / man-hour cap you can actually sustain and I'll find the point of diminishing returns inside it.",
                       K.go_deeper('What-if / scenario engine, Productivity & Resource Intelligence',
                                   'For the diminishing-returns curve')],
               evidence=[K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('EVM', 'Recovery gap', _gap_value(F))])


def t04q09(F, role):
    """A resourced recovery scenario that hits the milestone, with its manpower peak stress-tested."""
    if not F.get('ok'):
        return _no_project(F)
    head = "I can build it — but be clear on the honest limit first: manpower here is man-hours, not headcount."
    body = [
        ("The peak I can stress-test is an hours curve, not a body count. The P6 resources are loaded in "
         "man-hours, so I can show you where the hours spike — but converting that peak into actual bodies "
         "on site is a call you make with the CM, because the file doesn't hold crew sizes."),
        (f"The scenario I'd assemble: stack the strongest levers on the governing front — {_driver_phrase(F)} "
         "— then re-run F9 against the gap. " +
         (f"On a gap of about **{K.wd(F.get('delay_days'))}** one pass rarely closes it, so I'd add "
          "measures on the second front and re-run until the forecast finish lands on the milestone."
          if _behind(F) else
          "With the finish already holding, the scenario is a reserve plan — pre-built levers ready to fire "
          "on whichever front slips first.")),
        (_second_line(F) if _second_line(F) else
         "Where a second front surfaces after the first is accelerated, the What-if names it and I fold it into the same scenario."),
        ("Then Productivity Intelligence flags where the man-hour peak of that scenario runs past the "
         "norms — that's the staffability warning. The deliverable is a resourced What-if that hits the "
         "milestone on paper with its peak flagged; whether that peak is staffable is the field decision."),
    ]
    return K.A(head, body,
               advice=[f"Let me assemble the stacked scenario on **{_driver_phrase(F)}** and re-run F9 to the milestone, then flag the man-hour peak.",
                       K.go_deeper('What-if / scenario engine, Critical Path Analyzer',
                                   'To build and F9 the scenario')],
               evidence=[K.ev('EVM', 'Recovery gap', _gap_value(F)),
                         K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish'))])


def t04q10(F, role):
    """Rank recovery options by days-per-dollar, and what acceleration does to CPI."""
    if not F.get('ok'):
        return _no_project(F)
    cpi = F.get('cpi')
    head = ("I can rank the levers by days recovered — but true days-per-dollar needs crash rates the P6 "
            "file doesn't carry, so the cost side stays qualitative until you feed me those.")
    body = [
        (f"The days side I can rank: build each lever on {_driver_phrase(F)} in the What-if, run F9, and "
         "order them by finish-days gained. The schedule is cost-loaded, so I can also show the discipline "
         "budgets to size where the money already sits. What's missing is the *crash cost per day* of each "
         "lever — the overtime premium, the extra crew rate, the plant hire — none of which lives in the "
         "P6 export. Without it, a genuine days-per-dollar ranking would be a guess, so I keep the cost "
         "ranking qualitative until you load the rates."),
        (f"On CPI: you're reading **{K.ratio(cpi)}**." if cpi is not None else
         "On CPI: it isn't derivable from this file.") +
        (" In this file actual cost is set equal to earned value, so CPI is 1.00 by construction — it doesn't "
         "move with anything and says nothing about money. Don't hang a cost-efficiency story on it; SPI and "
         "the delay are the signals." if F.get('cost_derived') else
         " It's measured from real actual cost here, so it can show whether acceleration is eroding efficiency "
         "— read it next to SPI."),
        ("What is genuinely true about acceleration and money: overtime, extra crews and extra plant spend "
         "cash faster than they earn value, so a real recovery costs more per unit of work than the base "
         "plan. That trade — money for time — only becomes a number once crash rates are loaded; until "
         "then, treat it as a direction, not a figure."),
        ("So the go / no-go: rank by days now in the What-if, price it when you have rates, and read CPI as "
         "a schedule echo — not the cost verdict on the recovery."),
    ]
    return K.A(head, body,
               advice=["Feed me the crash rates (overtime premium, crew and plant costs) and I'll turn the days ranking into days-per-dollar.",
                       K.go_deeper('What-if / scenario engine, EVM, Reporting Studio',
                                   'To rank the levers and compose the go/no-go')],
               evidence=[K.ev('EVM', 'CPI', K.ratio(cpi)),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Recovery gap', _gap_value(F))])


def t04q11(F, role):
    """GAP — automatic least-cost crash optimisation across the network isn't implemented."""
    if not F.get('ok'):
        return _no_project(F)
    head = "I can't ground an automatic cheapest-crash plan — the tool doesn't do least-cost optimisation across the network."
    gn = K.gap_note('GAP — manual what-ifs only, no time-cost optimization')
    body = [
        gn or ("The tool runs manual what-ifs — it doesn't compute a least-cost crash across the network. "
               "Here's the planning read instead."),
        (f"What it does do today gets you most of the way by hand: rank the driving activities on "
         f"{_driver_phrase(F)} by finish sensitivity, then test levers one at a time and keep the ones "
         "that buy days cheapest. Worked in that order — biggest finish-mover first — you converge on a "
         "near least-effort plan without an optimiser."),
        ("A true automatic cheapest-crash is the classic CPM time-cost trade-off algorithm, and it needs "
         "two things this file hasn't got: a crash-cost-per-day loaded on every activity, and the "
         "optimiser itself to walk the network. Neither is built, so I'd be inventing the answer — and I "
         "won't hand you a plan I haven't actually computed."),
        ("If you load crash costs per activity later, that's the input the optimiser would need — worth "
         "capturing now even while the ranking is manual."),
    ]
    return K.A(head, body,
               advice=[f"Work it by hand for now: rank {_driver_phrase(F)} by finish sensitivity in the "
                       "What-if and test one lever at a time, cheapest-effective first.",
                       f"For the manual ranking, open {_whatif_open()}."],
               evidence=[K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('EVM', 'Recovery gap', _gap_value(F))])


def t04q12(F, role):
    """GAP — labour/plant market availability is outside the schedule."""
    if not F.get('ok'):
        return _no_project(F)
    head = "That's outside what the schedule can answer — labour and plant market availability isn't in the P6 file."
    gn = K.gap_note('GAP — labour/plant market data outside the schedule')
    body = [
        gn or ("The P6 file doesn't hold market availability, so anything I gave you on sourcing would be a "
               "guess. Here's what the schedule can and can't tell you."),
        ("What the model *can* give you: how many man-hours and which trades a recovery needs, and — "
         "critically — the latest date each resource would have to be on site to still bite the finish. "
         "Mobilise a second crew after that date and it accelerates nothing, so that date is the real "
         "procurement deadline, and the schedule pins it exactly."),
        (f"What it can't judge: whether the local market can actually deliver that crew and the plant by "
         "that date. That's your procurement and CM call — market depth, lead times and rates are field "
         "and commercial knowledge, not schedule data."),
        (f"So the division of labour is clean: tell me what you can realistically source and by when, and "
         f"I'll test exactly that in the What-if against {_driver_phrase(F)} — you own the market read, I "
         "own the finish impact."),
    ]
    return K.A(head, body,
               advice=["Give me the crews/plant you can realistically get and their earliest on-site dates, and I'll test them in F9.",
                       f"To size the man-hours and the on-site-by date, open {_whatif_open()}."],
               evidence=[K.ev('Critical Path Analyzer', 'Driving front', _driver_name(F)),
                         K.ev('EVM', 'Recovery gap', _gap_value(F))])


ANSWERS = {
    't04q00': t04q00, 't04q01': t04q01, 't04q02': t04q02, 't04q03': t04q03,
    't04q04': t04q04, 't04q05': t04q05, 't04q06': t04q06, 't04q07': t04q07,
    't04q08': t04q08, 't04q09': t04q09, 't04q10': t04q10, 't04q11': t04q11,
    't04q12': t04q12,
}
