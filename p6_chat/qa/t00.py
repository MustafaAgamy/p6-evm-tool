"""Theme 0 — Headline Status & KPIs.

The one-glance read: where the project stands right now, in plain terms, including the
finish date and the contractual dates at risk. Every answer is grounded in FACTS (EVM +
delay + progress + audit) and speaks as a senior planning engineer; where the exact figure
lives in a dedicated feature (Critical Path Analyzer, Consultant Review, Update vs Update)
the answer says so and points there, and it never invents a number the file doesn't hold.
"""
from . import _kit as K


def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can answer this "
              "from your own numbers — offline, nothing leaves your PC."])


def t00q00(F, role):
    """Ahead or behind, over or under budget, SPI + CPI."""
    if not F.get('ok'):
        return _no_project(F)
    _, pace = K.spi_verdict(F)
    cpi = F.get('cpi')
    cpi_txt = (f"CPI is **{K.ratio(cpi)}** — every unit spent is buying about {round((cpi or 0)*100)}% of its "
               "planned work" + (", a modest overspend" if cpi and cpi < 0.98 else
                                 (", a slight underrun" if cpi and cpi > 1.02 else ", essentially on budget")) + ".") if cpi is not None else \
              "Cost performance (CPI) isn't derivable in this file."
    behind = F.get('behind')
    head = (f"{F['project_name']} is **{'behind' if behind else ('ahead' if F.get('ahead') else 'on schedule')}** "
            f"on time" + (", and cost is holding" if cpi and cpi >= 0.97 else (", and modestly over on cost" if cpi else "")) + ".")
    body = [
        f"On schedule: {pace}. In date terms the finish is {K.delay_phrase(F)}.",
        cpi_txt,
        ("The story is **schedule, not money** — don't let a near-1.0 CPI reassure anyone while SPI sits below plan."
         if (cpi and cpi >= 0.9 and (F.get('pace_pct') or 100) < 90) else
         "Read time and cost together: SPI is the schedule signal, CPI the cost signal."),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append(dl)
    return K.A(head, body,
               advice=["Lead the report with the schedule position and the single work front driving it.",
                       K.go_deeper('EVM', 'For the full breakdown')],
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'CPI', K.ratio(cpi)),
                         K.ev('EVM', 'Delay', _kit_delay(F))])


def t00q01(F, role):
    """Plain-English status."""
    if not F.get('ok'):
        return _no_project(F)
    head = f"Plainly: {F['project_name']} is {_state_word(F)}."
    body = [
        (f"We've physically completed **{K.pct(F.get('actual_pct'))}** against a planned **{K.pct(F.get('planned_pct'))}** "
         f"by the {F.get('data_date')} data date" + _gap_points(F) + "."),
        f"In date terms the finish is {K.delay_phrase(F)}.",
    ]
    dl = K.driver_line(F)
    if dl:
        body.append(dl + " Engineering and procurement, where they carry little weight, aren't the headline.")
    cpi = F.get('cpi')
    if cpi is not None:
        body.append(f"Cost is {'holding' if cpi >= 0.97 else 'running modestly over'} (CPI {K.ratio(cpi)}).")
    body.append("Bottom line: " + _bottom_line(F))
    return K.A(head, body,
               advice=[K.go_deeper('Reporting Studio', 'To issue this as a one-pager')],
               evidence=[K.ev('EVM', 'Actual vs planned', f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('EVM', 'Delay', _kit_delay(F))])


def t00q02(F, role):
    """% complete overall and by discipline."""
    if not F.get('ok'):
        return _no_project(F)
    head = f"Overall **{K.pct(F.get('actual_pct'))}** complete against **{K.pct(F.get('planned_pct'))}** planned{_gap_points(F)}."
    body = ["The split by discipline is where the story is:"]
    ds = sorted(F.get('disciplines') or [], key=lambda d: (d.get('weight') or 0), reverse=True)
    for d in ds[:8]:
        state = 'behind' if (d.get('gap') or 0) > 2 else ('ahead' if (d.get('gap') or 0) < -2 else 'on plan')
        body.append(f"• **{d.get('name')}** — {d.get('actual')}% done vs {d.get('planned')}% planned "
                    f"({round((d.get('weight') or 0)*100)}% of the project by weight): {state}.")
    dl = K.driver_line(F)
    if dl:
        body.append("So the single headline number hides the concentration: " + dl)
    return K.A(head, body,
               advice=["Read the category bars discipline by discipline — the aggregate hides where the gap really sits.",
                       K.go_deeper('EVM', 'For the weighted roll-up')],
               evidence=[K.ev('EVM', 'Overall actual', K.pct(F.get('actual_pct'))),
                         K.ev('EVM', 'Overall planned', K.pct(F.get('planned_pct')))])


def t00q03(F, role):
    """Working days behind — real number or approximation?"""
    if not F.get('ok'):
        return _no_project(F)
    d = F.get('delay_days')
    if d is None:
        return K.A("I can't derive a finish-milestone slip from this file.",
                   body=["There's no finish milestone I can measure against a baseline here. Load a schedule "
                         "with a finish milestone, or read the driving path directly."],
                   advice=[K.go_deeper('Critical Path Analyzer')])
    behind = d > 0
    head = (f"About **{K.wd(d)} {'behind' if behind else 'ahead'}** to completion." if d != 0
            else "On the planned finish date — no slip.")
    body = [
        (f"This is the finish milestone measured in its own calendar's working days: forecast finish "
         f"~{F.get('forecast_finish') or 'n/a'} against the {F.get('baseline_finish') or 'baseline'} baseline."),
        ("It's re-derived by the tool from the schedule (an EVM-side reconstruction), which matches P6 to the day on "
         "progressed schedules. For a claim-grade, F9-exact figure, run it through the dedicated engine — I won't "
         "dress an approximation up as the contractual number."),
    ]
    nf = F.get('neg_float_count')
    if nf:
        body.append(f"Corroborating it: **{nf} activities** ({K.pct(F.get('neg_float_pct'))}) carry negative total float — "
                    "the network itself is showing the pressure on the finish, not just the EVM conversion.")
    return K.A(head, body,
               advice=[K.go_deeper('Consultant Review', 'For the F9-exact, dated figure')],
               evidence=[K.ev('EVM', 'Delay', _kit_delay(F)),
                         K.ev('Float', 'Negative-float activities', F.get('neg_float_count'))])


def t00q04(F, role):
    """Forecast completion date."""
    if not F.get('ok'):
        return _no_project(F)
    ff = F.get('forecast_finish')
    d = F.get('delay_days')
    if not ff:
        return K.A("The forecast finish isn't derivable from this file.",
                   body=["I can't read a forecast finish date here. Run the retained-logic forward pass to get it."],
                   advice=[K.go_deeper('Critical Path Analyzer')])
    head = f"Forecast completion is about **{ff}**" + (f", ~{K.wd(d)} {'late' if d>0 else 'early'} vs the {F.get('baseline_finish')} baseline." if d else ".")
    body = [
        "That's the retained-logic forecast off this update, not an extrapolation of the trend.",
    ]
    dl = K.driver_line(F)
    if dl:
        body.append("It's driven by " + dl.split('The shortfall is being carried by ')[-1])
    body.append(f"Treat {ff} as the honest current landing point — it holds only if the driving work stops losing "
                "days and no second front turns critical behind it.")
    return K.A(head, body,
               advice=[K.go_deeper('Critical Path Analyzer', 'To confirm the driving path behind this date')],
               evidence=[K.ev('Forecast', 'Finish', ff), K.ev('EVM', 'Delay', _kit_delay(F))])


def t00q05(F, role):
    """Will we hit the contract completion date?"""
    if not F.get('ok'):
        return _no_project(F)
    d = F.get('delay_days')
    if d is None:
        return K.A("I can't judge the contract date from this file.",
                   body=["There's no finish milestone to measure against, and formal contract-date ingest is a known "
                         "gap — I measure against the finish milestone in the P6 file."],
                   advice=[K.go_deeper('Critical Path Analyzer')])
    hit = d <= 0
    head = ("On today's logic, **yes** — we're on or ahead of the finish milestone." if hit
            else f"On today's logic, **no** — we land about **{K.wd(d)}** past the {F.get('baseline_finish')} baseline finish (~{F.get('forecast_finish')}).")
    body = []
    if not hit:
        body.append("If your contractual completion date is that baseline date, you're that far into exposure. "
                     "Confirm the actual contract date — formal contract-date ingest is a known gap, so right now "
                     "I'm measuring against the finish milestone in the file.")
        if 'Weather' in str(_grounds('t00q05')):
            body.append("Marine/weather-exposed work can widen this further — check the weather effect for the site type.")
        body.append("Recovery is achievable, but only by acting on the driving front now, not next month.")
    else:
        body.append("Keep the driving path protected and watch the near-critical chains so the margin doesn't erode.")
    return K.A(head, body,
               advice=[K.go_deeper('Weather Impact', 'For the weather exposure on the exposed work')],
               evidence=[K.ev('EVM', 'Delay vs baseline finish', _kit_delay(F)),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish'))])


def t00q06(F, role):
    """Every sectional/interim milestone slip."""
    if not F.get('ok'):
        return _no_project(F)
    return K.A("Here's how I'd read the sectional dates at risk.",
               body=[
                   "I can flag the milestones under pressure from the finish slip, but a per-milestone slip table with "
                   "each sectional date against its own obligation needs the driving-path engine — that's where each "
                   "milestone's forecast vs its constraint date is computed.",
                   "One honest caveat: formal contract-date ingest is a known gap, so those margins are measured "
                   "against the milestone/constraint dates in the schedule — reconcile them to the actual contract. "
                   "Each sectional date past its obligation carries its own LD exposure, not just final completion.",
                   ("On this schedule, with " + (K.wd(F.get('delay_days')) + " of slip to completion" if (F.get('delay_days') or 0) > 0 else "the current finish position")
                    + ", I'd flag the milestones fed by the driving work front first."),
               ],
               advice=[K.go_deeper('Critical Path Analyzer', 'For the per-milestone slip table')],
               evidence=[K.ev('EVM', 'Delay to completion', _kit_delay(F))])


def t00q07(F, role):
    """Trend since last update."""
    if not F.get('ok'):
        return _no_project(F)
    tr = F.get('trend')
    if tr and tr.get('prev_delay') is not None and (tr.get('delta') is not None):
        delta = tr.get('delta')
        direction = tr.get('direction')
        head = (f"The trend is **{'worsening' if direction=='worse' else ('improving' if direction=='better' else 'flat')}** "
                f"since the previous update.")
        body = [
            (f"Delay to completion moved from {K.wd(tr.get('prev_delay'))} to {K.wd(F.get('delay_days'))} "
             f"— {'a further ' + K.wd(delta) + ' lost' if (delta or 0) > 0 else ('a recovery of ' + K.wd(delta) if (delta or 0) < 0 else 'no change')} "
             "between the two updates."),
            f"Pace this update is SPI ≈ {K.ratio(F.get('spi'))} ({K.pct(F.get('pace_pct'))} of plan).",
        ]
        adv = [K.go_deeper('Update vs Update', 'For the full period-over-period movement')]
    else:
        head = "I need the previous update loaded to call the trend."
        body = [
            "Update vs Update reads the SPI and forecast-finish movement between two snapshots — I won't invent a "
            "prior figure I don't have.",
            (f"On this single snapshot: SPI ≈ {K.ratio(F.get('spi'))} with the finish {K.delay_phrase(F)}. "
             + ("A hole this deep doesn't self-correct — without an intervention the next update almost certainly reads worse."
                if (F.get('pace_pct') or 100) < 90 and (F.get('delay_days') or 0) > 0 else
                "Load the previous update and I'll quantify the direction properly.")),
        ]
        adv = ["Load last month's update, then ask again — I'll quantify the direction to the day."]
    return K.A(head, body, advice=adv,
               evidence=[K.ev('EVM', 'SPI now', K.ratio(F.get('spi'))),
                         K.ev('Trend', 'Delay now', _kit_delay(F))])


def t00q08(F, role):
    """Single most important message for the week."""
    if not F.get('ok'):
        return _no_project(F)
    d = F.get('delay_days')
    driver = K.main_driver(F)
    dn = driver.get('name') if driver else 'the driving work front'
    if d and d > 0:
        head = (f"One line: {F['project_name']} is forecasting **~{K.wd(d)} late** "
                f"(finish ~{F.get('forecast_finish')} vs the {F.get('baseline_finish')} baseline), the driver is "
                f"**{dn}**, and recovery needs a decision this week.")
    elif d is not None and d <= 0:
        head = (f"One line: {F['project_name']} is holding its finish date "
                f"(SPI ≈ {K.ratio(F.get('spi'))}) — keep the driving path protected.")
    else:
        head = f"One line: {F['project_name']} is at SPI ≈ {K.ratio(F.get('spi'))}; the finish milestone needs confirming."
    body = [
        "That's the message — a dated position, a single named cause, and a clear call to act.",
        (f"Cost is stable (CPI {K.ratio(F.get('cpi'))}), so don't bury the schedule story in financials."
         if F.get('cpi') and F['cpi'] >= 0.95 else
         "Pair it with the cost position so the report reads straight."),
        "Lead with the date and the cause; everything else is supporting detail.",
    ]
    return K.A(head, body,
               advice=[K.go_deeper('Update Analysis', 'For the numbers behind the headline')],
               evidence=[K.ev('EVM', 'Delay', _kit_delay(F)), K.ev('EVM', 'SPI', K.ratio(F.get('spi')))])


def t00q09(F, role):
    """Confidence in the forecast; is the schedule reliable enough to report off?"""
    if not F.get('ok'):
        return _no_project(F)
    oos = F.get('oos_count')
    oe = F.get('open_ends')
    fl_grade = F.get('float_grade')
    issues = []
    if oos:
        issues.append(f"{oos} out-of-sequence activities")
    if oe:
        issues.append(f"{oe} open ends")
    if F.get('dangling_count'):
        issues.append(f"{F.get('dangling_count')} dangling logic links")
    conf = ('Moderate' if issues else 'Reasonable')
    head = f"**{conf} confidence** in the forecast, with the logic caveats below."
    body = [
        (f"The delay reads as genuine and the finish is derivable, but the schedule carries "
         + ", ".join(issues) + " — these can let the forecast drift, so I'd clean them before staking the date on it.")
        if issues else
        "The logic is largely clean — no out-of-sequence or open-end flags that would let the forecast drift.",
        (f"Float health is graded **{fl_grade}**" + (f", with {F.get('neg_float_count')} activities on negative float"
         if F.get('neg_float_count') else "") + " — that's the network's own read on how much room is left.")
        if fl_grade else "",
        "What could blow the date: any near-critical front turning critical behind the current driver, and — on "
        "weather-exposed work — the season. It's reliable enough to report off with those flags stated, but not clean "
        "enough to bank without the fixes.",
    ]
    return K.A(head, body,
               advice=["Clean the out-of-sequence and open-end items, re-run, then bank the date.",
                       K.go_deeper('Schedule Health Review', 'For the graded logic quality')],
               evidence=[K.ev('Out-of-sequence', 'Activities', oos),
                         K.ev('Open ends', 'Count', oe),
                         K.ev('Float', 'Grade', fl_grade)])


# ── small shared bits used above ────────────────────────────────────────────────

def _kit_delay(F):
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


def _state_word(F):
    d = F.get('delay_days')
    if d is None:
        return "in progress; the finish milestone needs confirming"
    if d > 0:
        return "behind and losing ground on the finish date"
    if d < 0:
        return "ahead of its finish date"
    return "holding its finish date"


def _gap_points(F):
    a, p = F.get('actual_pct'), F.get('planned_pct')
    if a is None or p is None:
        return ""
    diff = round(p - a)
    if diff > 0:
        return f" — about {diff} points behind the curve"
    if diff < 0:
        return f" — about {abs(diff)} points ahead of the curve"
    return " — on the curve"


def _bottom_line(F):
    d = F.get('delay_days')
    driver = K.main_driver(F)
    dn = driver.get('name') if driver else 'the driving front'
    if d and d > 0:
        return f"this is an execution problem on **{dn}**, and it needs a recovery decision now, not next month."
    if d is not None and d <= 0:
        return "the finish is holding — protect the driving path and keep the near-critical work honest."
    return "confirm the finish milestone, then judge the position against the baseline."


def _grounds(qid):
    """The grounds string for one of this theme's questions (for weather/feature hints)."""
    return _GROUNDS.get(qid, '')


_GROUNDS = {
    't00q05': 'Critical Path Analyzer, EVM, Weather Impact',
}


ANSWERS = {
    't00q00': t00q00, 't00q01': t00q01, 't00q02': t00q02, 't00q03': t00q03, 't00q04': t00q04,
    't00q05': t00q05, 't00q06': t00q06, 't00q07': t00q07, 't00q08': t00q08, 't00q09': t00q09,
}
