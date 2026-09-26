"""Theme 15 — Weather & Calendar.

The working-time reality behind the dates: how many net working days each calendar
actually gives, what exceptions (holidays, reduced-hours spells, imposed shutdowns) are
baked in, and how bad weather eats into the forecast finish for the site type. The grounded
FACTS dict does NOT carry the working-day totals, the exception list or the weather
lost-day count — those are computed live in the Calendar Audit (net-working-days histogram,
two-calendar compare, editable daily-hours note) and its weather tab (workable days lost
against site-type criteria, waterfalled onto the forecast finish). So every answer leads
with the schedule signal it CAN ground (the finish position, the weighted driving front,
the calendar count) and routes the working-day/weather specifics to the feature that
computes them — never inventing a working-day total, an exception or a lost-day figure the
file doesn't hold. Weather Impact and the Calendar Audit both exist today; the What-if
sizes the recovery, and the Consultant Review carries the before/after for a shutdown.
"""
from . import _kit as K


# ── shared, F-grounded helpers (all None-safe) ──────────────────────────────────

def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can answer this "
              "from your own numbers — offline, nothing leaves your PC."])


def _delay_chip(F):
    """Signed finish chip value: '+60 wd (behind)' / '-12 wd (ahead)' / 'on date'."""
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
    dv = K.main_driver(F)
    return dv.get('name') if dv else None


def _driver_chip(F):
    """Evidence chip naming the weighted driver discipline, or None."""
    dv = K.main_driver(F)
    if not dv:
        return None
    return K.ev('EVM', f"Front to check first — {dv.get('name')}",
                f"{dv.get('actual')}% vs {dv.get('planned')}% planned")


def _cal_count(F):
    c = F.get('calendar_count')
    try:
        return int(c) if c is not None else None
    except (TypeError, ValueError):
        return None


def _cal_line(F):
    """Ground the calendar count honestly — the audit's first question is always 'how many, and why'."""
    n = _cal_count(F)
    if n is None:
        return ("I can't see a calendar count in this read, so confirm in the Calendar Audit how many "
                "calendars the file actually carries — that alone tells you whether the working-time model "
                "is one clean site calendar or a sprawl of near-duplicates nobody maintains.")
    if n <= 1:
        return (f"Your file carries **{n} calendar** — a single working-time model across the whole job. "
                "That's simple to audit, but check it's genuinely right for every work front: one calendar "
                "covering office, civils and any weather-exposed work usually means someone's site hours or "
                "lost-day allowance are wrong.")
    return (f"Your file carries **{n:,} calendars**. The first thing the Calendar Audit tells you is whether "
            "that's a deliberate set — office, day-shift site, night-shift, weather-exposed — or a sprawl of "
            "near-duplicates, because every activity inherits its working days and its lost time from "
            "whichever one it's assigned, and a wrong assignment stays invisible until you audit it.")


def _driver_cal_line(F):
    """Tie the working-time question to the front that actually drives the finish."""
    dl = K.driver_line(F)
    if dl:
        return ("Start where it bites: " + dl + " Whatever calendar that front is assigned drives your "
                "completion date, so if it's sitting on a lean office calendar instead of a realistic site "
                f"one, part of the gap is a working-time artefact rather than lost production — and with the "
                f"project {K.delay_phrase(F)}, that distinction is worth getting right before you brief it.")
    return ("Start on whatever front is carrying your finish date: the calendar it's assigned drives the "
            "completion date, so a lean or wrong calendar there quietly distorts the forecast — the project "
            f"is {K.delay_phrase(F)}, and a working-time artefact can hide inside that number.")


def _weather_split_line(F):
    """The binding honesty split — only the weather-attributable slip is a client-facing indicator."""
    d = F.get('delay_days')
    if d is not None and round(d) > 0:
        return ("Keep weather separate from the schedule slip. The project is " + K.delay_phrase(F) + " — and that "
                "figure is **weather-blind**: this P6 file doesn't measure weather, so the weather days the tab finds "
                "come **on top** of it, not out of it. Present the weather effect as its own figure. The slip itself "
                + ("splits between the employer side (the late client inputs) and the contractor side, and that split "
                   "is a time-impact analysis — not a weather question." if K.late_inputs(F) else
                   "is split by cause in a time-impact analysis — not by the weather tab."))
    return ("Keep weather separate: the forecast here doesn't include weather, so any weather days the tab finds come "
            "on top of the current position — present them as their own figure.")


# ── answers ─────────────────────────────────────────────────────────────────────

def t15q00(F, role):
    """Working days per calendar and the exception profile — holidays, reduced hours, shutdowns."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Run the Calendar Audit — it gives you the net working days per calendar and every exception "
            "baked into them: public holidays, reduced-hours spells and any imposed shutdown.")
    body = [
        ("The Calendar Audit lays out a **net-working-days histogram** for each calendar from the data date "
         "forward, and pulls out every exception the calendar carries — **public holidays, reduced-hours "
         "periods and imposed shutdowns** — alongside an editable note for the daily hours each one assumes. "
         "That is the true working time behind your durations, not the raw span you read off a bar. "
         + _cal_line(F)),
        (_driver_cal_line(F) + " Weather-exposed work in particular — marine, external civils, roofing, "
         "external finishes — shouldn't be sitting on a lean five-day office calendar with no allowance for "
         "lost days; that's exactly where hidden working time quietly leaks out."),
        ("Reduced-hours spells (a winter shift, a fasting-month timetable) and imposed shutdowns are where "
         "lost time hides in plain sight: the durations look fine, but the calendar gives fewer real hours "
         "to burn them in. The audit surfaces each one so you can see whether a duration was built on full "
         "days it never actually gets."),
        ("Honest limit: the working-day totals and the exception list themselves come out of the Calendar "
         "Audit screen, not the numbers I'm holding in this read — I can tell you what to look for and which "
         "calendar matters most, not recite each holiday for you."),
    ]
    if role == 'planning':
        body.append("Planner's cut: confirm the daily-hours per calendar are right (8 vs 10 vs 12), not just "
                     "the working-day count — a duration in days hides an hours assumption, and a wrong "
                     "hours figure distorts every resource and productivity read downstream.")
    advice = [
        "Confirm every site and weather-exposed front carries a proper site calendar with realistic daily "
        "hours — not the office calendar inherited by default.",
        K.go_deeper('Calendar Audit', 'For the working-day totals and the full exception list'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Calendar Audit', 'Calendars in the file', F.get('calendar_count')),
                         K.ev('Calendar Audit', 'Activities to map to calendars', F.get('activity_count')),
                         K.ev('EVM', 'Finish position', _delay_chip(F)),
                         _driver_chip(F)])


def t15q01(F, role):
    """Compare two calendars — where working days and daily hours differ."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Use the Calendar Audit's side-by-side compare — it shows exactly where two calendars differ, "
            "in both working days and daily hours.")
    body = [
        ("The two-calendar compare puts working days and daily working hours next to each other, so a "
         "difference that's invisible activity-by-activity — one calendar giving eight-hour, five-day weeks, "
         "another ten-hour days or a six-day week, one carrying a public-holiday set the other doesn't — "
         "shows up as a concrete gap in available time. That gap is what silently shifts dates when two "
         "fronts you assumed were on the same footing actually aren't."),
        ("The pair worth checking first is the calendar on the front carrying your finish against your "
         "general or office calendar. " + (K.driver_line(F) + " " if K.driver_line(F) else "")),
        ("If the governing front runs on the leaner of the two calendars, that difference alone can inflate "
         "the working days it appears to be behind — so reconcile any mismatch on the driving path **before** "
         "you trust the float or the forecast finish. A calendar difference on the governing chain feeds "
         f"straight through F9 into the completion date, and the project is {K.delay_phrase(F)}, so an "
         "apples-to-oranges pair distorts the whole forecast."),
        (_cal_line(F) + " The compare handles two calendars at a time, so start with the pair covering the "
         "most weighted work rather than the near-duplicates — and treat this as the natural next step after "
         "auditing each calendar on its own: it's how you catch the two that should be identical but aren't."),
    ]
    advice = [
        "Compare the driving front's calendar against the office calendar first, and reconcile any difference "
        "before you quote the finish or read the float.",
        K.go_deeper('Calendar Audit', 'For the side-by-side working-day and daily-hours comparison'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Calendar Audit', 'Calendars available to compare', F.get('calendar_count')),
                         K.ev('EVM', 'Finish position', _delay_chip(F)),
                         _driver_chip(F)])


def t15q02(F, role):
    """Weather days lost this month and the effect on the finish."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Run the Bad-Weather Impact analysis with the site-type preset that matches this job — it counts "
            "the workable days lost against your weather criteria and carries them through to the finish.")
    body = [
        ("The weather tab in the Calendar Audit counts the **workable days lost** against the weather "
         "criteria for your **site type** — you pick the preset (coastal/marine, desert, temperate and so "
         "on), it shows the criteria it's testing against and works off a typical or observed year from the "
         "data date. The lost days then flow into a **waterfall onto the forecast finish**, so you see the "
         "milestone effect, not just a raw day count."),
        _weather_split_line(F),
        ("Everything is measured from the data date forward, so it's the *remaining* weather exposure on the "
         "*remaining* work — not a retrospective tally that double-counts days already worked through. That's "
         "what makes the finish effect defensible: it's a forward-looking indicator, not a rear-view "
         "grievance."),
        ("Honest limit: I can't give you the lost-day count or the exact finish effect from this read — those "
         "are computed in the weather tab off your chosen criteria and site type. What I can do is make sure "
         "you present them straight, with the weather effect kept separate from the schedule slip."),
    ]
    if role == 'planning':
        body.append("Planner's cut: check the criteria and the return-period behind the preset before you "
                     "quote a figure — a wind/wave threshold that's too soft under-counts marine downtime, "
                     "and a too-harsh rainfall trigger over-states lost days on civils.")
    advice = [
        "Present the weather effect as its own figure, on top of the schedule slip — never as a slice of it.",
        K.go_deeper('Weather Impact', 'For the lost-day count and the finish effect'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Finish position', _delay_chip(F)),
                         K.ev('Calendar Audit', 'Calendars carrying the site hours', F.get('calendar_count')),
                         _driver_chip(F)])


def t15q03(F, role):
    """Weather-adjusted finish on a typical year, and the recovery that offsets the weather days."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Build the weather-adjusted finish on a typical year for your site type, then offset it in the "
            "What-if — and sequence the two in that order, not as one lump sum.")
    body = [
        ("Do it as a sequence. Start from where the finish sits today — that's " + K.delay_phrase(F) + " — "
         "layer the expected weather downtime from the typical-year model for your site type, and *then* "
         "apply your recovery levers in the **What-if / scenario engine**, which gives you an instant "
         "estimate and then the **P6-exact** days each lever buys via a build → F9 round-trip. That way the "
         "recovery is measured against the weather-adjusted date, not the clean one."),
        ("Set expectations honestly: the levers rarely cover the whole exposure. Adding a shift or a crew "
         "buys real days, but a typical weather year eats some of them straight back, so weather-adjusted "
         "you'll usually still carry residual exposure. I won't quote you a lever's day-count here — that's "
         "exactly what the what-if computes against your own logic, and anything I invented would be a guess."),
        ("The lever that matters most is **timing**. Push weather-sensitive work into the calmer window so "
         "the recovery isn't eaten back by downtime — a night shift or an extra crew run through the worst of "
         "the season pays standby for days it simply can't work."),
        ((K.driver_line(F) + " Load the recovery onto that front, because accelerating work that isn't on the "
          "governing path buys float you already have and barely moves the date.")
         if K.driver_line(F) else
         "Load the recovery onto whatever front actually drives the finish — accelerating work off the "
         "governing path buys float you already have and barely moves the date."),
    ]
    advice = [
        "Sequence it: current finish → typical-year weather downtime → recovery levers in the what-if, each "
        "measured against the adjusted date.",
        "Time the weather-sensitive push for the calm window so downtime doesn't eat the recovery back.",
        K.go_deeper('Weather Impact', 'For the typical-year weather-adjusted finish'),
        K.go_deeper('What-if / scenario engine', 'To size the P6-exact days each recovery lever buys'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Finish position', _delay_chip(F)),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish')),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         _driver_chip(F)])


def t15q04(F, role):
    """How many of the crew-days I'm adding will just be lost to weather."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Right question to ask before you throw a crew at it — cross the weather lost-day profile against "
            "the fronts you're planning to accelerate.")
    body = [
        ("Lay the **Weather Impact** lost-day profile next to the fronts you mean to reinforce. The most "
         "weather-sensitive work — marine, external civils, lifting, external finishes — is where added "
         "crew-days are most likely to land on non-workable days. Cross the two and you see how many of the "
         "crew-days you're paying for are standby, not production."),
        ("The trap is simple: add a crew through a rough window and a chunk of those crew-days can't be "
         "worked, so you pay standby for nothing and the histogram peak you built never converts to progress. "
         + ((K.driver_line(F) + " That's usually the very front you're most tempted to reinforce, which is "
             "exactly why the timing check matters.") if K.driver_line(F) else
            "And it's usually the front carrying your slip that you're most tempted to reinforce, which is "
            "exactly why the timing check matters.")),
        ("Push the extra resources into the calm window, and keep the weather-exposed period for work that's "
         "protected — internal, covered or below-ground. That's how you get the man-hours you're paying for "
         "to actually earn, instead of buying a taller peak that the weather flattens."),
        ("Read the crew and man-hour profile in **Productivity & Resource Intelligence** so you're timing "
         "real man-hours against the lost-day profile rather than a headcount guess — and don't over-man a "
         "weather-exposed front just because the arithmetic says the days are there. The days on paper aren't "
         "the days the sea or the sky will give you."),
    ]
    advice = [
        "Time the extra resources for the dry/calm window; keep weather-protected work for the exposed "
        "period.",
        "Don't over-man a weather-exposed front — crew-days added on non-workable days are standby, not "
        "recovery.",
        K.go_deeper('Weather Impact', 'For the lost-day profile to time the push against'),
        K.go_deeper('Productivity & Resource Intelligence', 'For the crew and man-hour profile'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[_driver_chip(F),
                         K.ev('EVM', 'Finish position', _delay_chip(F)),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi')))])


def t15q05(F, role):
    """Do procurement and shipping durations account for holidays and site shutdowns."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("Check it in the Calendar Audit — put the procurement and shipping activities under the lens and "
            "confirm the **calendar** assigned to them, not just their durations.")
    body = [
        ("A lead time or a sea-freight leg is only as honest as the calendar it runs on. If those activities "
         "sit on a calendar that carries the **holidays and any port or site shutdown**, the delivery dates "
         "are real; if they're on a seven-day continuous calendar with no exceptions — or the wrong regional "
         "holiday set — the dates read optimistically, and everything downstream inherits that optimism."),
        (((K.driver_line(F) + " So procurement isn't your headline right now — ") if K.driver_line(F) else
          "If engineering and procurement are broadly holding on your progress read, don't manufacture a "
          "problem here — ")
         + "but one fabricated or shipped item landing on a shutdown can still clip the very construction "
         "front that is driving the date, so it's worth the ten-minute check rather than assuming the "
         "delivery dates are clean."),
        ("Verify the calendar first, then trust the dates — the order matters. A plausible-looking delivery "
         "date sitting on the wrong calendar is the kind of error that only surfaces when the crate doesn't "
         "clear the port over a holiday you never scheduled, and by then the float it ate is gone."),
        ("Honest limit: the Calendar Audit shows you which calendar each activity is assigned and what "
         "exceptions it carries; it won't re-estimate a lead time for you. That judgement stays yours — but "
         "now it's informed by the right working-time model instead of an optimistic one."),
    ]
    advice = [
        "Put the procurement and shipping lines under the Calendar Audit and confirm each carries a calendar "
        "with the right holidays and any port/site shutdown.",
        K.go_deeper('Calendar Audit', 'To confirm the calendar on the procurement and shipping activities'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Calendar Audit', 'Calendars in the file', F.get('calendar_count')),
                         K.ev('Calendar Audit', 'Activities to check', F.get('activity_count')),
                         _driver_chip(F)])


def t15q06(F, role):
    """How to show the shutdown period wasn't the contractor's delay."""
    if not F.get('ok'):
        return _no_project(F)
    head = "Document it, don't argue it — the record does the work here."
    body = [
        ("The **Calendar Audit** pulls out every **imposed shutdown and holiday exception** as non-working "
         "time already carried in the schedule. Those days were never yours to work — they're baked into the "
         "calendar the schedule was built and approved on — and showing them as calendar-imposed non-working "
         "time is far stronger than asserting it in a letter."),
        ("Pair that with a **Consultant Review** run showing the finish position with and without the "
         "shutdown window — a but-for read that isolates what the imposed non-working time did to the date. "
         "Together they say one thing plainly: this is calendar-imposed non-working time, not contractor "
         "slippage."),
        ("Keep it strictly factual. This **evidences** that the time is non-working and calendar-imposed — "
         "it is a **time-impact indicator, never an entitlement finding**. The tool doesn't ingest your "
         "contract, your correspondence or the monetary side, so it can't and won't 'prove' an EOT for you; "
         "it hands you the dated, reconciled evidence and you build the entitlement argument on top of it. "
         "The project reads " + K.delay_phrase(F) + " today, and the point of this exercise is to show how "
         "much of that was never workable time."),
        ("One honest caveat: formal contract-date ingest is a known gap, so the finish is measured against "
         "the milestone and constraint dates in the P6 file. Reconcile those to your actual contract dates "
         "before you present, so the before/after lands on the right baseline rather than on a milestone that "
         "doesn't match the contract."),
    ]
    advice = [
        "Export the shutdown/holiday exceptions from the Calendar Audit and the with/without-shutdown finish "
        "from the Consultant Review, and present them as fact — non-working time, not slippage.",
        "Reconcile the schedule's milestone dates to the actual contract dates first — the tool measures "
        "against the file, not the contract.",
        K.go_deeper('Calendar Audit', 'To pull the imposed-shutdown and holiday exceptions'),
        K.go_deeper('Consultant Review', 'For the with/without-shutdown finish position'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Calendar Audit', 'Calendars carrying the exceptions', F.get('calendar_count')),
                         K.ev('EVM', 'Finish position', _delay_chip(F))])


ANSWERS = {
    't15q00': t15q00, 't15q01': t15q01, 't15q02': t15q02, 't15q03': t15q03,
    't15q04': t15q04, 't15q05': t15q05, 't15q06': t15q06,
}
