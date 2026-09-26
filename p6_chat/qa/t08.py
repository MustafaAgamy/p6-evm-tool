"""Theme 8 — Cost & EVM Financials.

The money picture: Earned vs Planned vs Actual, the two variances, the spend S-curve, and
the honest limits of cost forecasting off a P6 file. Every answer is grounded in the FACTS
dict (pv/ev/ac, variance, SPI/CPI, the weighted driver discipline, the delay to completion)
and speaks as a senior planning engineer. Two truths run through the whole theme and are
stated plainly wherever they bite: (1) P6's XML carries no Schedule% or Planned-Value curve,
so the PLANNED side is re-derived — SPI is directional, the delay is the hard number; and
(2) in these schedules cost is derived from percent-complete, so CPI sits near 1.0 by
construction and is an echo of SPI, not an independent cost verdict. Per-discipline BAC/AC
tables, the plotted S-curve, EAC/ETC/TCPI and a monetary prolongation figure live in
dedicated features (or aren't built yet); these answers give the grounded read and route to
the feature — they never invent a dollar figure the file doesn't hold.
"""
from . import _kit as K


# ── shared helpers ──────────────────────────────────────────────────────────────

def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can answer this "
              "from your own numbers — offline, nothing leaves your PC."])


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _delay_chip(F):
    """Signed delay chip value: '+47 wd (behind)' / '-12 wd (ahead)' / 'on date'."""
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


def _cv(F):
    """Cost variance EV - AC, from grounded facts, or None. (Definition, not a guess.)"""
    ev, ac = _num(F.get('ev')), _num(F.get('ac'))
    if ev is None or ac is None:
        return None
    return ev - ac


def _have_costs(F):
    """True if the file carries non-trivial dollar figures (pv/ev/ac), not just percentages."""
    return any((_num(F.get(k)) or 0) != 0 for k in ('pv', 'ev', 'ac'))


def _money_chip(x):
    """A money value for an evidence chip, or None so the chip is dropped when there's no $."""
    return K.money(x) if _num(x) is not None else None


def _prog_gap(F):
    """Whole planned-minus-actual points (positive = behind the curve), or None."""
    a, p = _num(F.get('actual_pct')), _num(F.get('planned_pct'))
    if a is None or p is None:
        return None
    return round(p - a)


def _overrun_pct(F):
    """abs(1/CPI - 1) as a whole percent — the per-unit cost gap implied by CPI, or None."""
    c = _num(F.get('cpi'))
    if not c or c <= 0:
        return None
    return round(abs(1.0 / c - 1.0) * 100.0)


def _cpi_word(F):
    """('over'|'under'|'on', more/less clause) read of CPI, None-safe."""
    c = _num(F.get('cpi'))
    if c is None:
        return None
    if c < 0.98:
        return 'over'
    if c > 1.02:
        return 'under'
    return 'on'


def _derived(F):
    """Actual cost equals earned value — cost is derived from progress, so it isn't measured."""
    return bool(F.get('cost_derived'))


def _not_measured(F):
    return ("In this file actual cost is set equal to earned value — cost is derived from progress, not recorded — "
            "so **CPI is 1.00 by construction** and says nothing about money.")


def _unearned_pct(F):
    """Share of the value planned by now that hasn't been earned: (PV − EV) ÷ PV, whole %, or None."""
    pv, ev = _num(F.get('pv')), _num(F.get('ev'))
    return round((pv - ev) / pv * 100) if pv and ev is not None else None


def _cpi_echo_caveat(F):
    """The honest CPI clause for this file. Always returns a usable sentence."""
    c = _num(F.get('cpi'))
    spi = K.ratio(F.get('spi'))
    if _derived(F):
        return (_not_measured(F) + f" **SPI ≈ {spi}** and the delay to completion are the signals that actually "
                "move.")
    if c is None:
        return (f"Cost performance (CPI) isn't derivable from this file, so **SPI ≈ {spi}** and the delay to "
                "completion carry the story.")
    return (f"**CPI ≈ {K.ratio(c)}** is measured from the actual cost in this file — read it alongside "
            f"**SPI ≈ {spi}** and the delay to completion, which carry the schedule story.")


def _rederived_caveat(F):
    """The re-derivation honesty line (P6 omits PV) — reused wherever confidence in the $ matters."""
    return ("Confidence caveat: P6's XML carries no Schedule% or Planned-Value curve, so the tool "
            f"**re-derives** the planned side from the baseline dates and the loaded budget. That makes "
            f"**SPI ≈ {K.ratio(F.get('spi'))}** directional rather than gospel. The hard schedule position is the "
            f"delay to completion ({K.delay_phrase(F)}) — that is P6's own figure: the finish milestone's exported "
            "forecast date against its baseline, which agrees with its total float.")


def _hist_n(F):
    return len(F.get('history') or [])


# GROUNDS per question, lifted verbatim from the manifest so go_deeper/gap_note route correctly.
GROUNDS = {
    't08q00': 'EVM',
    't08q01': 'EVM',
    't08q02': 'EVM',
    't08q03': 'EVM',
    't08q04': 'EVM, Out of Sequence',
    't08q05': 'EVM',
    't08q06': 'EVM',
    't08q07': 'Baseline Revision Comparison, EVM, Consultant Review',
    't08q08': 'EVM, Update Analysis',
    't08q09': 'Reporting Studio, EVM',
    't08q10': 'Power BI live dashboards',
    't08q11': 'GAP — EVM has CPI but no EAC/ETC/TCPI tiles',
    't08q12': 'GAP — delay_days and baseline S-curve are ingredients only',
    't08q13': ('GAP — delay-in-working-days is the partial time-based counterpart; a formal '
               'earned-schedule SPI(t) index/trend is not produced'),
}


# ── answers ──────────────────────────────────────────────────────────────────────

def t08q00(F, role):
    """EV vs PV — how much value earned vs planned by the data date."""
    if not F.get('ok'):
        return _no_project(F)
    gap = _prog_gap(F)
    have = _have_costs(F)
    dd = F.get('data_date')
    prog = (f"In progress terms that's **{K.pct(F.get('actual_pct'))}** complete against **{K.pct(F.get('planned_pct'))}**"
            " planned" + (f" — a **{gap}-point** hole." if gap and gap > 0 else
                         (f" — about **{abs(gap)} points ahead**." if gap and gap < 0 else " — right on the curve.")))
    head = ((f"By the {dd} data date you've earned **{K.pct(F.get('pace_pct'))}** of the value you planned to earn by "
             f"now (EV {K.money(F.get('ev'))} of PV {K.money(F.get('pv'))} — SPI {K.ratio(F.get('spi'))}). " + prog)
            if have and F.get('pace_pct') is not None else f"By the {dd} data date: " + prog)
    body = [
        ("The two numbers behind that: **Earned Value** is the budgeted cost of the work you've actually "
         "done, **Planned Value** the budgeted cost of the work you should have done by now. "
         f"**SPI ≈ {K.ratio(F.get('spi'))}** ({K.pct(F.get('pace_pct'))} of the planned rate) is just those "
         "two as a ratio — how much of the planned value you're actually banking each period."
         + (f" In money that's EV **{K.money(F.get('ev'))}** against PV **{K.money(F.get('pv'))}**." if have else
            " This file reads in percent terms rather than dollars, so I'm giving you the value read as "
            "progress rather than as a cash figure.")),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append("That hole isn't spread evenly across the job — " + dl + " The missing value sits on that "
                    "front; the disciplines carrying little weight aren't where it sits.")
    else:
        body.append("No single discipline stands out as the driver in this file, so read the value gap "
                    "front by front in the category view rather than pinning it on one area.")
    body.append(_rederived_caveat(F))
    return K.A(head, body,
               advice=["Read the category bars discipline by discipline — the single headline number hides "
                       "where the earned value actually went missing.",
                       K.go_deeper(GROUNDS['t08q00'], 'For the Planned-vs-Earned breakdown')],
               evidence=[K.ev('EVM', 'Earned vs planned', f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'EV', _money_chip(F.get('ev'))),
                         K.ev('EVM', 'PV', _money_chip(F.get('pv'))),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t08q01(F, role):
    """Schedule variance (EV-PV) and cost variance (EV-AC) in dollars."""
    if not F.get('ok'):
        return _no_project(F)
    sv = _num(F.get('variance'))            # EV - PV
    cv = _cv(F)                              # EV - AC
    over = _cpi_word(F)
    orp = _overrun_pct(F)
    un = _unearned_pct(F)
    if _derived(F):
        head = ("The schedule variance is the whole story. Cost variance reads **0** — not because cost is on "
                "track, but because this file sets actual cost equal to earned value.")
    elif sv is not None and sv < 0 and cv is not None and cv < 0:
        head = "Both variances are negative — and the **schedule** variance is the bigger story."
    else:
        head = "Here's the schedule variance and the cost variance, and which one is really driving the report."
    body = [
        ("**Schedule variance (EV − PV)**: "
         + (f"**{K.money(sv)}** in budget terms" if sv is not None else "the planned-vs-earned gap")
         + (f" — **{un}%** of the value planned by now hasn't been earned (SPI ≈ {K.ratio(F.get('spi'))})."
            if un and un > 0 else f" at **SPI ≈ {K.ratio(F.get('spi'))}**.")),
    ]
    if _driver_name(F):
        body.append("Almost all of that schedule variance is being carried by one front — " + K.driver_line(F))
    if _derived(F):
        body.append("**Cost variance (EV − AC)**: **0**. " + _not_measured(F))
        body.append("So report the schedule variance as the headline and show cost as 'not measured' until real "
                    "actuals are loaded. The per-discipline split is in the EVM tab and the Excel export.")
    else:
        body.append(
            "**Cost variance (EV − AC)**: "
            + (f"**{K.money(cv)}**, " if cv is not None else "")
            + ((f"**CPI ≈ {K.ratio(F.get('cpi'))}** — you're spending about **{orp}% "
                f"{'more' if over == 'over' else 'less'}** than you're earning." if over in ('over', 'under') else
                f"**CPI ≈ {K.ratio(F.get('cpi'))}** — spending is in line with what you're earning.")
               if over else "CPI isn't derivable from this file, so there's no cost-variance read."))
        body.append(_cpi_echo_caveat(F))
        body.append("Lead the report with the schedule variance and the delay to completion — that's the number "
                    "moving — and give cost its own one line.")
    return K.A(head, body,
               advice=[("Report the schedule variance as the headline; show cost as 'not measured'." if _derived(F) else
                        "Report the schedule variance as the headline and the cost variance as the secondary line — "
                        "in that order."),
                       K.go_deeper('Reporting Studio, EVM', 'For the exact per-discipline dollar figures')],
               evidence=[K.ev('EVM', 'Schedule variance (EV−PV)', _money_chip(sv)),
                         K.ev('EVM', 'Cost variance (EV−AC)', _money_chip(cv)),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'CPI', K.ratio(F.get('cpi')))])


def t08q02(F, role):
    """AC vs PV, and is percent-spent running ahead of percent-complete (early-overspend warning)."""
    if not F.get('ok'):
        return _no_project(F)
    over = _cpi_word(F)
    orp = _overrun_pct(F)
    have = _have_costs(F)
    ahead = (over == 'over')
    if _derived(F):
        return K.A(
            "This file can't tell you: actual cost is set equal to earned value, so percent-spent equals "
            "percent-complete by construction. There's no burn-rate signal to read — good or bad.",
            [(f"Spend to date: **AC {K.money(F.get('ac'))}** against a planned **PV {K.money(F.get('pv'))}** — "
              f"AC is lower than plan only because less work has been done ({K.pct(F.get('actual_pct'))} against "
              f"{K.pct(F.get('planned_pct'))} planned), not because anything is being saved.") if have else None,
             _not_measured(F),
             "To see real burn, load actual costs (or resource actuals) into P6 before export — then CPI moves "
             "on its own and the percent-spent-vs-complete test means something."],
            advice=["Report cost as 'not measured' until actuals are loaded; track the schedule signal meanwhile.",
                    K.go_deeper(GROUNDS['t08q02'], 'For AC vs PV by discipline')],
            evidence=[K.ev('EVM', 'AC', _money_chip(F.get('ac'))), K.ev('EVM', 'PV', _money_chip(F.get('pv'))),
                      K.ev('EVM', 'CPI', 'not measured (AC = EV)')])
    head = ("Yes, but only slightly — percent-spent is running a few points ahead of percent-complete, a mild "
            "burn-rate warning, not a blow-out." if ahead else
            ("Percent-spent is running **behind** percent-complete — you're earning more than you're spending."
             if over == 'under' else
             "Percent-spent is running essentially **in line** with percent-complete — no burn-rate signal."))
    body = [
        ("Spend to date against plan: "
         + (f"you've spent **AC {K.money(F.get('ac'))}** against a planned **PV {K.money(F.get('pv'))}**. "
            if have else "this file reads in percent terms rather than dollars, so I'll take the burn read off "
            "the ratios rather than the cash figures. ")
         + (f"**CPI ≈ {K.ratio(F.get('cpi'))}** means each unit of value earned cost about "
            f"{K.ratio(1.0/_num(F.get('cpi')) if _num(F.get('cpi')) else None)} to earn — so percent-spent runs "
            + (f"about **{orp}% {'ahead of' if ahead else 'behind'}**" if over in ('over', 'under') else "**in step with**")
            + f" your **{K.pct(F.get('actual_pct'))}** complete." if over else
            "CPI isn't derivable here, so I can't put a burn-rate figure on the spend.")),
    ]
    if ahead:
        body.append(f"That's a **mild** early-overspend warning, not a run-away — a {orp}% per-unit gap is the "
                    "kind of number you monitor, not one you escalate on its own. And because the schedule is "
                    "cost-loaded the figure is real rather than a rounding artefact.")
    body.append(_cpi_echo_caveat(F))
    dl = K.driver_line(F)
    body.append(("Watch it monthly, and watch it where the cost is concentrating: " + dl + " If CPI keeps sliding "
                 "as that front drags on, the percent-spent-vs-complete gap widens with it.") if dl else
                "Watch it monthly — if CPI keeps sliding as the behind work drags on, the percent-spent-vs-complete "
                "gap widens with it.")
    return K.A(head, body,
               advice=["Track percent-spent against percent-complete every month — the trend matters more than "
                       "the single reading.",
                       K.go_deeper(GROUNDS['t08q02'], 'For AC vs PV by discipline')],
               evidence=[K.ev('EVM', 'AC', _money_chip(F.get('ac'))),
                         K.ev('EVM', 'PV', _money_chip(F.get('pv'))),
                         K.ev('EVM', 'CPI', K.ratio(F.get('cpi'))),
                         K.ev('EVM', 'Actual complete', K.pct(F.get('actual_pct')))])


def t08q03(F, role):
    """Which disciplines over/under budget, and the budget split across E/P/C."""
    if not F.get('ok'):
        return _no_project(F)
    ds = sorted([d for d in (F.get('disciplines') or []) if (_num(d.get('weight')) or 0) > 0],
                key=lambda d: (_num(d.get('weight')) or 0), reverse=True)
    head = ("Here's the honest split: I can give you each discipline's **weight** and its progress against plan "
            "straight from this file; the per-discipline over/under-**budget** ranking (BAC vs AC) lives in the EVM "
            "category view" + (" — and in this file cost isn't measured, so no discipline can show over or under "
                               "budget yet." if _derived(F) else "."))
    body = []
    if ds:
        top = ds[:6]
        body.append("**Weight by discipline** — the share of the project each carries in the progress "
                    "calculation (a weight, not a budget):")
        for d in top:
            state = ('behind plan' if (_num(d.get('gap')) or 0) > 2 else
                     ('ahead of plan' if (_num(d.get('gap')) or 0) < -2 else 'on plan'))
            body.append(f"• **{d.get('name')}** — ~{round((_num(d.get('weight')) or 0) * 100)}% of the project by "
                        f"weight; {d.get('actual')}% done vs {d.get('planned')}% planned ({state}).")
        body.append("Weight tells you where schedule pressure moves the finish; it isn't where the money sits. The "
                    "budget (BAC) per discipline is in the EVM category view.")
    else:
        body.append("I can't read a discipline breakdown from this file, so I can't give you the budget split — "
                    "load a WBS/cost-coded schedule and the category view fills in.")
    body.append("What I'm giving above is over/under **plan** (the schedule gap per discipline), which is grounded "
                "in this file. Over/under **budget** — each discipline's BAC against its AC — is the per-category "
                "table in the EVM tab and the Excel export; that's where you rank who's genuinely over or under on cost.")
    dl = K.driver_line(F)
    if dl:
        body.append("Where I'd point the review first: " + dl + " That's where the unearned value sits — focus the "
                    "conversation on that front, not evenly across every discipline.")
    return K.A(head, body,
               advice=[("Focus the cost review on the heaviest, most-behind construction front — that's where budget "
                        "and schedule pressure coincide.")
                       if dl else "Pull the per-category BAC/AC table before ranking anyone over or under budget.",
                       K.go_deeper(GROUNDS['t08q03'], 'For the per-discipline BAC-vs-AC ranking')],
               evidence=[K.ev('EVM', 'CPI', K.ratio(F.get('cpi'))),
                         K.ev('EVM', 'Heaviest front', ds[0].get('name') if ds else None),
                         K.ev('EVM', 'Driver', _driver_name(F))])


def t08q04(F, role):
    """Over-claiming — where EV is higher than AC, by discipline."""
    if not F.get('ok'):
        return _no_project(F)
    over = _cpi_word(F)
    orp = _overrun_pct(F)
    if _derived(F):
        oos = F.get('oos_count')
        dn = _driver_name(F)
        return K.A(
            "The cost data can't show an over-claim in this file — and that's not reassurance. Actual cost is set "
            "equal to earned value, so earned value can never run above cost here.",
            [_not_measured(F),
             "So the over-claim test has to be done on **progress**, not money: is the percent-complete booked on "
             "each activity physically installed and inspected?",
             (f"Start with the **{oos} out-of-sequence activities**" + (f" ({K.pct(F.get('oos_pct'))} of the schedule)"
              if F.get('oos_pct') is not None else "") + " — work progressed ahead of its predecessors. Progress "
              "booked there can be real on paper but not yet installed in the right order.") if oos else None,
             (f"Then check **{dn}** — it carries most of the project's weight, so an optimistic percent-complete "
              "there moves earned value the most.") if dn else None],
            advice=["Reconcile the booked percent-complete against physically installed, inspected work before it "
                    "reaches a valuation.",
                    K.go_deeper(GROUNDS['t08q04'], 'For the out-of-sequence activities')],
            evidence=[K.ev('EVM', 'CPI', 'not measured (AC = EV)'), K.ev('Out-of-sequence', 'Activities', oos),
                      K.ev('EVM', 'Front to check', dn)])
    head = ("Overall you're the **opposite** of over-claiming — spend is slightly ahead of earned, so there's no "
            "global over-claim." if over == 'over' else
            ("Overall, earned value is running **ahead** of spend — worth a discipline-by-discipline check for "
             "optimistic claims." if over == 'under' else
             "Overall earned value and spend are broadly in balance — check for over-claims front by front."))
    body = [
        ("The global read comes straight from CPI: **CPI ≈ " + K.ratio(F.get('cpi')) + "**"
         + (f" means for every unit earned you've spent about {orp}% more — so on the whole job you're not "
            "claiming progress you haven't paid for; if anything it's the reverse." if over == 'over' else
            (f" means earned value sits about {orp}% above spend — a pattern worth scrutinising, because that's "
             "what an over-optimistic progress claim looks like in aggregate." if over == 'under' else
             " sits close to 1.0 — no global signal either way."))) if over else
        "CPI isn't derivable from this file, so I can't give the global over-claim read — check it discipline by "
        "discipline in the category view.",
        "But the aggregate hides it — **check it discipline by discipline** in the EVM tab's EV-vs-AC view. Any "
        "front showing earned value well above the cost actually spent is claiming progress it hasn't paid for, "
        "and that's exactly what inflates a valuation before it's earned in the field.",
    ]
    oos = F.get('oos_count')
    if oos:
        body.append(f"There's a specific reason to scrutinise the claims: this file carries **{oos} out-of-sequence "
                    f"activities**" + (f" ({K.pct(F.get('oos_pct'))} of the schedule)" if F.get('oos_pct') is not None else "")
                    + " — work progressed ahead of its predecessors. Earned value booked against those can be real "
                    "on paper but not yet installed in the right order, so reconcile it against physical progress "
                    "before you report it.")
    dn = _driver_name(F)
    body.append((f"I'd scrutinise **{dn}** especially — it's the front carrying the shortfall and the most likely "
                 "place a claim runs ahead of installation.") if dn else
                "Reconcile every front's earned value against physical installation before it goes into a valuation.")
    return K.A(head, body,
               advice=["Reconcile any EV-above-AC discipline against physically installed, inspected work before it "
                       "reaches a valuation.",
                       K.go_deeper(GROUNDS['t08q04'], 'For the per-discipline EV-vs-AC view')],
               evidence=[K.ev('EVM', 'CPI', K.ratio(F.get('cpi'))),
                         K.ev('Out-of-sequence', 'Activities', oos),
                         K.ev('EVM', 'Front to scrutinise', dn)])


def t08q05(F, role):
    """Is the schedule cost-loaded or percent-only, and which scope has zero BAC?"""
    if not F.get('ok'):
        return _no_project(F)
    c = _num(F.get('cpi'))
    have = _have_costs(F)
    near_one = (c is not None and abs(c - 1.0) <= 0.03)
    head = ("This file looks **genuinely cost-loaded**, so CPI is a real spend-efficiency figure — you can trust "
            "the money read." if (have and not near_one) else
            "Treat the money read with care here — the signals point to a largely **percent-driven** schedule "
            "rather than an independently cost-loaded one.")
    body = [
        ("Start with how the numbers are built: P6's XML doesn't export a Planned-Value curve, so the tool "
         "re-derives the planned side from the baseline dates and whatever budget is loaded. If a real budget "
         "is loaded, cost moves independently and CPI is a genuine efficiency figure. If it isn't, cost simply "
         "tracks percent-complete and CPI sits pinned on 1.0 — a percent-only proxy dressed as a cost number."),
        ("The tell in **this** file: " + (f"**CPI ≈ {K.ratio(c)}**. " if c is not None else "CPI isn't derivable. ")
         + ("Sitting right on 1.0, that's almost certainly a percent-driven schedule — read CPI as an echo of SPI, "
            "not an independent cost verdict." if near_one else
            ("Because it departs from 1.0, there's real budget loading behind it and the efficiency read carries "
             "weight — but confirm it in the category view before you bank it." if c is not None else
             "Without a CPI I'd assume percent-only until the category view shows loaded budgets."))),
        ("Then check for **zero-BAC scope**. Milestones, level-of-effort and late-added activities often carry no "
         "budget and silently drop out of the EV/AC totals. Open the EVM category view and look for any package "
         "showing zero BAC — if a big construction package is zero-loaded, your CPI is being computed on a partial "
         "base and the whole money read is understated. Flag and load it before the next client report."),
    ]
    body.append("Whatever the cost picture, the schedule signal is unaffected: **SPI ≈ " + K.ratio(F.get('spi')) +
                "** and the delay to completion (" + K.delay_phrase(F) + ") don't depend on the budget being loaded, "
                "so report off those with confidence either way.")
    return K.A(head, body,
               advice=["Scan the category view for any zero-BAC package — especially in construction — and load it "
                       "before the CPI goes into a report.",
                       K.go_deeper(GROUNDS['t08q05'], 'To see BAC by category and spot the gaps')],
               evidence=[K.ev('EVM', 'CPI', K.ratio(c)),
                         K.ev('EVM', 'Cost-loaded?', 'yes' if (have and not near_one) else 'percent-driven / check'),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi')))])


def t08q06(F, role):
    """Is Planned Value from P6 or re-derived?"""
    if not F.get('ok'):
        return _no_project(F)
    head = "**Re-deriving it** — and that's the single most important thing to know about the money figures."
    body = [
        ("P6's XML export simply doesn't contain a Schedule% or a Planned-Value curve — the data isn't in the "
         "file. So the tool rebuilds the planned side from the **baseline dates and the loaded budget**: a sound, "
         "standard reconstruction, but an approximation, not a number lifted straight out of P6. Actual Cost and "
         "Earned Value come from the loaded costs directly, where they exist."),
        ("The practical consequence: treat **SPI ≈ " + K.ratio(F.get('spi')) + "** as **directional** — it tells "
         "you the shape and size of the gap, not a contract-grade figure. Don't quote it to two decimals in a "
         "dispute; quote it as 'about two-thirds of planned pace' and move on to the hard number."),
        ("The hard number is the delay: the finish is " + K.delay_phrase(F) + ". That is P6's own figure — the "
         "finish milestone's exported forecast date (after your F9) against its baseline, which agrees with its "
         "total float — not something re-derived from a budget curve. So it's the figure to lead a report with."),
    ]
    body.append("So in one line: the EVM percentages and SPI are a good approximation for steering; the **delay to "
                "completion** is the number you report and defend.")
    return K.A(head, body,
               advice=["Lead reports with the delay to completion; use SPI/PV as the supporting trend, labelled as "
                       "a re-derived approximation.",
                       K.go_deeper('EVM', 'For the planned-vs-earned read behind SPI')],
               evidence=[K.ev('EVM', 'SPI (directional)', K.ratio(F.get('spi'))),
                         K.ev('P6', 'Delay (finish milestone)', _delay_chip(F)),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish'))])


def t08q07(F, role):
    """The spend S-curve — planned vs actual cumulative cost — and am I burning faster than planned?"""
    if not F.get('ok'):
        return _no_project(F)
    n = _hist_n(F)
    over = _cpi_word(F)
    orp = _overrun_pct(F)
    gap = _prog_gap(F)
    hist = (f"You have **{n} updates** stored (different data dates), so the actual curve can be plotted against the "
            "baseline and the slope compared." if n >= 2 else
            "Right now only this one update is stored, so the baseline curve is there but you need a couple of updates "
            "before the actual line means anything — one point isn't a curve.")
    if _derived(F):
        return K.A(
            "In this file the actual-cost curve is the earned-value curve — cost is derived from progress — so the "
            "S-curve shows **progress**, not spending. It can't tell you whether you're burning faster than planned.",
            ["What the S-curve is: cumulative planned value (the baseline curve) against what's been earned, period by "
             "period. " + hist,
             (f"Read it as progress: you're about **{gap} points** behind the planned curve" if gap and gap > 0 else
              "Read it as progress against the planned curve") + f" (SPI ≈ {K.ratio(F.get('spi'))}). The line sits "
             "below plan because less work is done, not because money is being saved.",
             _not_measured(F)],
            advice=["Plot it as a progress S-curve and label it that way — don't present it as a cost curve.",
                    K.go_deeper('EVM', 'To plot the planned-vs-earned curve')],
            evidence=[K.ev('EVM', 'Earned vs planned', f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                      K.ev('EVM', 'CPI', 'not measured (AC = EV)'),
                      K.ev('History', 'Updates to plot', n if n else None)])
    head = ("Your actual-cost curve will sit **below** the planned line — but don't read that as underspending; "
            "you're below plan because you're behind on work, not because you're saving money.")
    body = [
        ("What the S-curve is: cumulative planned cost (the baseline curve) against cumulative actual cost, period "
         "by period. " + hist),
        ("The trap in the picture: the actual line below the planned line looks like an underrun, but with "
         + (f"about **{gap} points** of work still to earn" if gap and gap > 0 else "the current progress gap")
         + " it's simply the cost of work you haven't done yet. The honest metric is **cost per unit of "
           "progress**: "
         + ((f"**CPI ≈ {K.ratio(F.get('cpi'))}** says each bit of work is costing about {orp}% "
             f"{'more' if over == 'over' else 'less'} than budgeted." if over in ('over', 'under') else
             f"**CPI ≈ {K.ratio(F.get('cpi'))}** says each bit of work is costing about what was budgeted.")
            if over else "CPI isn't derivable here, so read the curve as a progress story, not a savings one.")),
        ("So you're burning **slower in total** (less work done) but "
         + ("**less efficiently per unit** (each unit costs more). " if over == 'over' else
            ("**more efficiently per unit**. " if over == 'under' else "at about the budgeted unit rate. "))
         + "As the driving front recovers, expect the actual-cost line to climb **steeply** back toward the plan — "
           "the spend you've deferred doesn't disappear, it arrives late."),
    ]
    body.append(_cpi_echo_caveat(F))
    return K.A(head, body,
               advice=["Read the curve as cost-per-unit-of-progress, not total cash — the gap below plan is deferred "
                       "spend, not savings.",
                       K.go_deeper('EVM', 'To plot the planned-vs-actual curve')],
               evidence=[K.ev('EVM', 'Earned vs planned', f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('EVM', 'CPI (per-unit cost)', K.ratio(F.get('cpi'))),
                         K.ev('History', 'Updates to plot', n if n else None)])


def t08q08(F, role):
    """Which work fronts are burning budget but not showing progress."""
    if not F.get('ok'):
        return _no_project(F)
    dn = _driver_name(F)
    if _derived(F):
        dl = K.driver_line(F)
        tg = [d for d in (F.get('top_gaps') or []) if (_num(d.get('gap')) or 0) > 0 and d.get('name') != dn]
        return K.A(
            "Nothing in this file can show budget burning without progress: actual cost is set equal to earned value, "
            "so cost only rises when progress does. The real question is which front is **stalled**"
            + (f" — and that's **{dn}**." if dn else "."),
            [_not_measured(F),
             ("The stalled front: " + dl + " " + K.chain_line(F)) if dl else None,
             (f"The next front to watch is **{tg[0].get('name')}** — {tg[0].get('actual')}% done against "
              f"{tg[0].get('planned')}% planned, a {tg[0].get('gap')}-point gap.") if tg else None,
             "To see crews and plant costing money without output, the file would need real actual costs or "
             "resource actuals loaded — then this test works."],
            advice=[(f"Find out on site what's holding **{dn}** — that's the delay in the making." if dn else
                     "Find out on site which fronts are stalled — that's where the delay is building."),
                    K.go_deeper(GROUNDS['t08q08'], 'For the overdue / stalled activities')],
            evidence=[K.ev('EVM', 'Driver front', dn), K.ev('EVM', 'Delay', _delay_chip(F)),
                      K.ev('EVM', 'CPI', 'not measured (AC = EV)')])
    head = ("Cross the per-category **AC-vs-actual%** view with the **Update Analysis** overdue list — the front "
            "where cost is climbing but percent-complete is flat is the one to grab"
            + (f". On this job that's **{dn}**." if dn else "."))
    body = [
        ("The signature to hunt for: **AC rising while actual% stays flat**. That's plant on hire, crews clocked "
         "on and preliminaries ticking over against slow physical output — budget leaving the account without "
         "earned value coming back. The per-category AC-vs-actual% numbers are in the EVM tab; the overdue-start "
         "and overdue-finish list that confirms which fronts are stalled is in Update Analysis."),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append("The front to check first: " + dl + " It sits on the governing path, so any burn without "
                    "progress there is the finish slip, not a side issue.")
    tg = [d for d in (F.get('top_gaps') or []) if (_num(d.get('gap')) or 0) > 0]
    second = next((d for d in tg if d.get('name') != dn), None)
    if second:
        body.append(f"The second front to watch is **{second.get('name')}** — {second.get('actual')}% done against "
                    f"{second.get('planned')}% planned, a {second.get('gap')}-point gap. It's next in line to turn "
                    "critical and start soaking budget the same way if it isn't pulled back.")
    body.append(_cpi_echo_caveat(F))
    return K.A(head, body,
               advice=[(f"Grab **{dn}** first — cost climbing on a stalled front on the governing path is the delay "
                        "in the making.") if dn else "Grab the stalled fronts on the governing path first — that's "
                       "where burn-without-progress becomes the delay.",
                       K.go_deeper(GROUNDS['t08q08'], 'To cross cost against progress by front')],
               evidence=[K.ev('EVM', 'Driver front', dn),
                         K.ev('EVM', 'Delay', _delay_chip(F)),
                         K.ev('EVM', 'CPI', K.ratio(F.get('cpi'))),
                         K.ev('Out-of-sequence', 'Activities', F.get('oos_count'))])


def t08q09(F, role):
    """Build a one-page cost/EVM dashboard for the client and export to Excel."""
    if not F.get('ok'):
        return _no_project(F)
    dn = _driver_name(F)
    gap = _prog_gap(F)
    over = _cpi_word(F)
    head = "**Reporting Studio** does this in one pass — the one-pager and the Excel export come off the same numbers."
    body = [
        ("Compose the one-pager from what's already on this snapshot: the KPI tiles — "
         f"**SPI {K.ratio(F.get('spi'))}**, "
         + ("**Cost: not measured** (CPI would read 1.00 only because actual cost equals earned value), "
            if _derived(F) else f"**CPI {K.ratio(F.get('cpi'))}**, ") +
         f"**{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}**, delay **{_delay_chip(F) or 'n/a'}** — "
         "the planned-vs-actual S-curve, and the per-discipline BAC/AC table beneath them."),
        ("Then export the **same content** to Excel — one row per category — so the client's cost team can pivot "
         "it their own way rather than retyping off a PDF. Same registry, same figures on the page and in the "
         "workbook, so the two can't drift apart."),
        ("Lead the page with a single line so nobody has to hunt for the message: "
         + (f"*{gap} points behind" if gap and gap > 0 else "*On or ahead of the value curve")
         + (f", driven by {dn}" if dn else "")
         + (", cost not measured in this file.*" if _derived(F) else
            ", cost in line with the work done.*" if over == 'on' else
            ", cost running over on the work done.*" if over == 'over' else
            ", cost running under on the work done.*" if over == 'under' else ".*")),
    ]
    body.append(_rederived_caveat(F))
    return K.A(head, body,
               advice=["Put the one-line verdict at the top of the page — dated position, single cause, cost read — "
                       "and let the tiles and curve support it.",
                       K.go_deeper(GROUNDS['t08q09'], 'To compose the page and export the workbook')],
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'CPI', K.ratio(F.get('cpi'))),
                         K.ev('EVM', 'Earned vs planned', f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t08q10(F, role):
    """Is CPI trending better or worse over the last few updates? (in-progress — Power BI)"""
    if not F.get('ok'):
        return _no_project(F)
    n = _hist_n(F)
    if _derived(F):
        return K.A(
            "There's no CPI trend to read in this file: actual cost is set equal to earned value, so CPI will show "
            "1.00 in every update, however the job is doing.",
            [_not_measured(F),
             ("Only this one update is stored anyway (re-imports of the same file don't count as history)." if n < 2
              else f"You have {n} updates stored — but each will show CPI 1.00 for the same reason."),
             "The trend worth watching is the **SPI and forecast-finish movement** between updates — Update vs "
             "Update gives you that today, and it's the leading indicator a real CPI trend would only confirm."],
            advice=["Track the SPI / forecast-finish movement in Update vs Update; load actual costs to make CPI mean "
                    "something.",
                    K.go_deeper('Update vs Update', 'For the period-by-period movement')],
            evidence=[K.ev('EVM', 'CPI', 'not measured (AC = EV)'), K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                      K.ev('History', 'Updates stored', n if n else None)])
    head = (f"Right now I can give you today's CPI — **{K.ratio(F.get('cpi'))}** — but not the trend line yet; "
            "the CPI-over-time view is still in build.")
    body = [
        ("The data is there — **every import stores CPI in the snapshot history** — but the view that plots it "
         "over time is landing with the **Power BI live dashboards**, which are still being built. So I won't draw "
         "you a trend I can't yet compute; that would be inventing a shape."),
        ("The interim by hand: open the last "
         + (f"**{min(n, 3)}** updates" if n >= 2 else "two or three updates once you have them")
         + " and read the CPI off each. A CPI falling below 1.0 from one update to the next is early cost-efficiency "
           "erosion and worth calling out now, before the trend view exists to make it obvious."),
        _cpi_echo_caveat(F),
    ]
    body.append("Meanwhile the sharpest trend to watch is the **SPI and forecast-finish movement** between updates — "
                "Update vs Update gives you that today.")
    return K.A(head, body,
               advice=["Read CPI off the last few snapshots by hand until the Power BI trend view ships.",
                       "For a live trend you can act on now, use the SPI / forecast-finish movement in Update vs Update.",
                       K.go_deeper('Power BI live dashboards, Update vs Update', 'For the CPI trend once it lands')],
               evidence=[K.ev('EVM', 'CPI today', K.ratio(F.get('cpi'))),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('History', 'Snapshots stored', n if n else None)])


def t08q11(F, role):
    """EAC / ETC / TCPI — cost at completion. (gap — no forecasting module)"""
    if not F.get('ok'):
        return _no_project(F)
    c = _num(F.get('cpi'))
    orp = _overrun_pct(F)
    try:
        from p6_chat.merged.q08 import implied_bac
        ib = implied_bac(F)
    except Exception:
        ib = None
    if ib and c:
        bac, ac, ev = ib['bac'], _num(F.get('ac')) or 0, _num(F.get('ev')) or 0
        eac = bac / c
        tcpi = (bac - ev) / (bac - ac) if bac > ac else None
        body = [
            f"**Budget at completion (BAC) ≈ {K.money(bac)}** — worked out from the planned and earned value against "
            "each discipline's progress (the same figure the cost answer above shows).",
            f"• **EAC ≈ BAC ÷ CPI ≈ {K.money(eac)}** — cost at completion if today's efficiency holds.",
            f"• **ETC = EAC − AC ≈ {K.money(eac - ac)}** — what's left to spend from here.",
            (f"• **TCPI = (BAC − EV) ÷ (BAC − AC) ≈ {K.ratio(tcpi)}** — the efficiency the remaining work needs to "
             "land on budget." if tcpi else None),
            ("These simply restate the budget: " + _not_measured(F) + " They'll become a real forecast once actual "
             "costs are loaded." if _derived(F) else
             "Treat them as a first-order forecast — they assume today's CPI holds for the rest of the job."),
            ("For steering today, lean on the schedule position: **SPI ≈ " + K.ratio(F.get('spi')) + "** and the "
             "delay to completion (" + K.delay_phrase(F) + ")."),
        ]
        return K.A(
            (f"On this file's budget of about **{K.money(bac)}**, EAC ≈ **{K.money(eac)}**, ETC ≈ **{K.money(eac - ac)}**"
             + (f" and TCPI ≈ **{K.ratio(tcpi)}**" if tcpi else "") + "."
             + (" With cost not measured, they only restate the budget — they're not a cost forecast yet."
                if _derived(F) else "")),
            body,
            advice=["Load actual costs into P6 before export to turn these into a real cost forecast."
                    if _derived(F) else "Re-run these each update — the trend in EAC matters more than one reading.",
                    K.go_deeper('EVM', 'For the planned and earned value they build on')],
            evidence=[K.ev('EVM', 'BAC (implied)', K.money(bac)), K.ev('EVM', 'EAC', K.money(eac)),
                      K.ev('EVM', 'CPI', 'not measured (AC = EV)' if _derived(F) else K.ratio(c))])
    head = ("Honestly, the tool can't ground **EAC, ETC or TCPI** yet — it computes CPI but carries no "
            "cost-forecasting module, so I won't quote a figure it hasn't produced.")
    body = [
        K.gap_note(GROUNDS['t08q11']) or ("The tool computes CPI but has no EAC/ETC/TCPI tiles yet — here's the "
                                          "planning read and the mechanics."),
        ("The mechanics are simple once a forecast module exists, and I'll lay them out so you can do it by hand:\n"
         "• **EAC ≈ BAC ÷ CPI** — cost at completion if today's efficiency holds"
         + (f". At **CPI ≈ {K.ratio(c)}** that's roughly a **{orp}% "
            f"{'overrun' if (c and c < 1) else ('underrun' if (c and c > 1) else 'variance')}** on the budget."
            if c else ".")
         + "\n• **ETC = EAC − AC** — what's left to spend from here.\n"
           "• **TCPI = (BAC − EV) ÷ (BAC − AC)** — the efficiency you'd need on the *remaining* work to still land "
           "on budget; if that's much above 1.0, recovery to budget isn't realistic."),
        ("What I can't do is put a number on any of them, because I don't hold your **BAC** as a stored figure "
         "here — and even if I did, remember the CPI caveat: in these schedules cost tracks percent-complete, so a "
         "CPI-based EAC would inherit that softness. Give me your BAC and I'll walk all three by hand; I just won't "
         "manufacture the total."),
    ]
    body.append("For steering today, lean on the schedule position rather than a cost forecast: **SPI ≈ " +
                K.ratio(F.get('spi')) + "** and the delay to completion (" + K.delay_phrase(F) + "). Those are "
                "grounded; EAC is not, yet.")
    return K.A(head, body,
               advice=["Send me your BAC (budget at completion) and I'll compute EAC, ETC and TCPI with you by hand.",
                       "Flag a cost-forecasting module (EAC/ETC/TCPI) as the feature this needs — it isn't built yet.",
                       K.go_deeper(GROUNDS['t08q11'], 'For the CPI the forecast would build on')],
               evidence=[K.ev('EVM', 'CPI', K.ratio(c)),
                         K.ev('EVM', 'CPI-implied overrun', (f"~{orp}%" if orp is not None else None)),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t08q12(F, role):
    """Cost of delay / prolongation + month-by-month forward cashflow. (gap)"""
    if not F.get('ok'):
        return _no_project(F)
    head = ("The tool can't put a **money figure on the delay** yet — it gives you the delay in hard terms and the "
            "baseline cost curve, but not a priced prolongation or a forward monthly cashflow.")
    body = [
        K.gap_note(GROUNDS['t08q12']) or ("Monetary prolongation and a forward month-by-month cash forecast aren't "
                                          "produced yet — here's how a planner grounds them."),
        ("What it does give you is the delay itself — **" + (K.delay_chip if False else (_delay_chip(F) or 'the finish position'))
         + "** by P6 F9, finish " + (F.get('forecast_finish') or 'as forecast') + " against the "
         + (F.get('baseline_finish') or 'baseline') + " baseline — plus the baseline cost curve. Those are the "
           "ingredients; what's missing is the arithmetic that turns days into money."),
        ("**Prolongation** is roughly your time-related preliminaries / extended-overheads rate **per day × the "
         "delay days**. Give me that daily rate and I'll multiply it across the "
         + (K.wd(F.get('delay_days')) if F.get('delay_days') else "delay") + " — but I won't invent a rate, so "
           "until you supply it this stays an exposure indicator, not a claimed sum."),
        ("**Forward monthly cashflow** needs the remaining work distributed across the coming months — the baseline "
         "S-curve is an ingredient, but the tool doesn't yet roll it into month buckets. That's a real feature, not "
         "a today answer."),
    ]
    body.append("Keep this as a read on **exposure**, not a number to put in a claim — and note it's exactly what "
                "the **EOT Claim Builder** (still in build) is designed to formalise once you feed it the rates.")
    return K.A(head, body,
               advice=["Send me your time-related preliminaries rate per day and I'll size the prolongation against "
                       "the F9 delay — labelled an estimate, not a claim.",
                       "Treat any prolongation figure as exposure until it's built up from real, evidenced rates.",
                       K.go_deeper('EOT Claim Builder', 'For the prolongation and EOT build (in progress)')],
               evidence=[K.ev('EVM', 'Delay (F9)', _delay_chip(F)),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish')),
                         K.ev('Baseline', 'Finish', F.get('baseline_finish'))])


def t08q13(F, role):
    """Time-based / earned-schedule read instead of cost-based SPI. (gap)"""
    if not F.get('ok'):
        return _no_project(F)
    head = ("You're right, and it's the correct instinct — a **cost-based SPI always creeps back toward 1.0** near "
            "the end even on a late job, so **" + K.ratio(F.get('spi')) + "** will flatter you later in the programme.")
    body = [
        K.gap_note(GROUNDS['t08q13']) or ("A formal earned-schedule SPI(t) index and trend isn't produced yet — "
                                          "here's the counterpart the tool does give."),
        ("What the tool gives as the **time-based counterpart** is the delay itself — **" + (_delay_chip(F) or 'the finish position')
         + "** by P6 F9, forecast finish " + (F.get('forecast_finish') or 'as forecast') + " against the "
         + (F.get('baseline_finish') or 'baseline') + " baseline. That's measured in working days on the network, "
           "so it doesn't drift back to zero the way a cost-based SPI does — it's the honest time read."),
        ("Why the distinction matters: cost-based SPI is EV ÷ PV in **budget** units, and as the remaining budget "
         "shrinks toward the end, EV closes on PV whatever the calendar is doing — so it reads healthy on a job "
         "that's finishing late. **Earned Schedule** fixes this by measuring on the **time** axis: you find the "
         "point on the baseline curve where planned value equals today's EV, and SPI(t) = earned time ÷ actual "
         "time. The tool holds the ingredients — the baseline curve and today's EV — but doesn't compute the "
         "SPI(t) index or its trend yet."),
    ]
    body.append("So the practical instruction as you move into the back end of the job: **report off the delay in "
                "working days, not off SPI.** The delay is the number that stays honest to completion; SPI is the "
                "one that will quietly reassure people it shouldn't.")
    return K.A(head, body,
               advice=["From here on, lead the schedule story with the working-day delay to completion, not the "
                       "cost-based SPI.",
                       K.go_deeper('EVM, Critical Path Analyzer', 'For the delay and the driving path behind it')],
               evidence=[K.ev('EVM', 'SPI (cost-based)', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay (time-based)', _delay_chip(F)),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish'))])


ANSWERS = {
    't08q00': t08q00, 't08q01': t08q01, 't08q02': t08q02, 't08q03': t08q03, 't08q04': t08q04,
    't08q05': t08q05, 't08q06': t08q06, 't08q07': t08q07, 't08q08': t08q08, 't08q09': t08q09,
    't08q10': t08q10, 't08q11': t08q11, 't08q12': t08q12, 't08q13': t08q13,
}
