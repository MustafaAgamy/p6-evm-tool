"""Theme 2 — Delay: Root Cause & Forensics.

How far behind, what's driving it, and whether the slip is real or manufactured. These are the
questions a planning manager fields when a client — or a claims consultant — starts probing the
programme. Every answer is grounded in FACTS (EVM + delay + progress + the stored audit modules)
and speaks as a senior planning engineer: it states what the schedule itself shows (negative
float, out-of-sequence, constraints, open ends), separates genuine execution slip from schedule
manipulation using the audit evidence that IS in the file, and routes the forensic, cross-file
work (Consultant Review but-for, Baseline Revision windows, Update-vs-Update) to those engines —
honestly, never fabricating a but-for number the snapshot can't produce.
"""
from . import _kit as K


def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can trace what's "
              "driving the delay and whether the slip is genuine — offline, nothing leaves your PC."])


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _behind(F):
    d = _num(F.get('delay_days'))
    return d is not None and d > 0


def _akpi(F, name):
    """One stored audit module's kpis dict, or {} — None-safe."""
    return ((F.get('audit') or {}).get(name) or {}).get('kpis') or {}


def _neg_float_line(F):
    nf = F.get('neg_float_count')
    if not nf:
        return ''
    return (f"**{nf} activities** ({K.pct(F.get('neg_float_pct'))}) are sitting on negative total float — "
            "the network is showing the pressure on the finish openly, in the numbers.")


# ── answers ──────────────────────────────────────────────────────────────────────

def t02q00(F, role):
    """What's driving the finish date — the driving path and top activities."""
    if not F.get('ok'):
        return _no_project(F)
    if not _behind(F):
        return K.A(
            "Nothing is pushing the finish out right now — the date is holding.",
            body=[f"The finish is {K.delay_phrase(F)}, so there's no live slip to trace to a driving front. "
                  "The job here is to keep it that way.",
                  (K.driver_line(F) or "No single discipline is dragging the programme on the weighted read."),
                  "Keep the driving path protected and watch the near-critical chains so none of them turns the "
                  "clock against you."],
            advice=[K.go_deeper('Critical Path Analyzer', 'To see the longest path in full')],
            evidence=[K.ev('EVM', 'Delay', _sd(F)), K.ev('Critical path', 'Driving activities', F.get('driving_path_count'))])
    head = f"The finish is being driven by your critical chain — about **{K.wd(F.get('delay_days'))} behind** to completion."
    body = [
        ((K.dates(F, "The forecast finish sits at about **{ff}** against the **{bf}** baseline. ") or
          f"The finish is {K.delay_phrase(F)}. ") +
         "That slip is owned by the activities on the longest (driving) path, not by the project as a whole."),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append(dl + " That is where the driving chain almost certainly runs — the recovery has to land there.")
    cc = F.get('cpli_critical_count')
    logic = ' '.join(x for x in (K.chain_line(F), K.driving_note(F)) if x)
    if logic or cc:
        body.append("On the logic: " + (logic + " " if logic else "")
                    + (f"**{cc}** activities ({K.pct(F.get('cpli_critical_pct'))}) sit at critical (near-zero or "
                       f"negative) float — a "
                       f"{('dense' if (F.get('cpli_density_grade') or '').lower().startswith('high') else 'broad')} "
                       "critical front, so other paths sit close behind the one that sets the date." if cc else ""))
    nfl = _neg_float_line(F)
    if nfl:
        body.append(nfl + " Negative float is measured against the baseline finish: a path moves the forecast "
                    "finish only once its float is as deep as the finish chain's; a shallower one has that much slack "
                    "left before it drives the date.")
    body.append("The main answer above lists that chain activity by activity, so you can see exactly which work "
                "carries the slip." if K.chain_facts(F) else
                "The tool can't name the individual top activities from this snapshot — that ranked driving-path "
                "list comes from the Critical Path Analyzer — but it can tell you which work front carries the slip "
                "and that the path is real.")
    return K.A(head, body,
               advice=["Put every recovery move on the front named above first — nothing off the driving path moves the date.",
                       K.go_deeper('Critical Path Analyzer', 'For the ranked driving-path activities')],
               evidence=[K.ev('EVM', 'Delay', _sd(F)),
                         K.ev('Critical path', 'Driving activities', F.get('driving_path_count')),
                         K.ev('Critical path', 'CPLI grade', F.get('cpli_grade'))])


def t02q01(F, role):
    """Is the slip genuine or manufactured by logic/lag/constraint edits?"""
    if not F.get('ok'):
        return _no_project(F)
    lag = _akpi(F, 'lag_lead')
    rel = _akpi(F, 'relationship_types')
    head = ("The slip reads as **genuine** — the network shows it openly, and nothing points to it being "
            "manufactured by editing logic, lags or constraints." if _behind(F) else
            "There's no slip to explain — the finish is holding.")
    body = []
    if _behind(F):
        body.append(f"The finish is {K.delay_phrase(F)}, and the network shows that delay honestly: "
                    + (_neg_float_line(F) or "the driving path is carrying it in the open."))
        lags = lag.get('lagged_count') or lag.get('lag_count') or lag.get('total_lags')
        non_fs = rel.get('non_fs') or rel.get('non_fs_count')
        found = ' and '.join(x for x in (f"{K.money(lags)} lagged links" if K._n(lags) else '',
                                         f"{K.money(non_fs)} non-FS relationships" if K._n(non_fs) else '') if x)
        body.append("Two things a forensic reviewer looks for as signs of a *manufactured* slip — wholesale "
                    "logic re-sequencing and padded lags — aren't jumping out of the audit"
                    + (f": it flags {found}, which is logic to tidy, not evidence the delay was engineered." if found
                       else ".")
                    + " The definitive but-for test belongs to the Consultant Review / Baseline Revision engines.")
        dl = K.driver_line(F)
        if dl:
            body.append("Where the slip sits: " + dl + " " + K.cause_line(F))
        body.append("Report it straight — a real slip, not a paper one. That honesty also *strengthens* your "
                    "position if this ever becomes a delay claim; a slip you can defend beats a number someone can pick apart.")
    else:
        body.append(f"The finish is {K.delay_phrase(F)}, so there's nothing to test for manipulation. If a slip "
                    "appears in a later update, come back and I'll read the audit for the manipulation tells.")
    return K.A(head, body,
               advice=[K.go_deeper('Consultant Review', 'For the definitive but-for proof the slip is genuine'),
                       "Tidy the flagged lags/relationships so no one can argue the delay is a logic artefact."],
               evidence=[K.ev('EVM', 'Delay', _sd(F)),
                         K.ev('Out-of-sequence', 'Activities', F.get('oos_count')),
                         K.ev('Float', 'Negative-float activities', F.get('neg_float_count'))])


def t02q02(F, role):
    """But-for true delay with logic/lag changes stripped out."""
    if not F.get('ok'):
        return _no_project(F)
    body = [
        ("The 'true' but-for delay — the slip with any logic and lag edits stripped out — is a **Consultant Review** "
         "result: it corrects the schedule, re-runs the P6 forward pass (F9), and reads the collapsed number. That "
         "cross-file, corrected run isn't computed at import, so I won't quote a but-for figure the snapshot can't produce."),
        (f"What I can give you from this file is the live position: the finish is {K.delay_phrase(F)}. If the update "
         "carries no logic/lag manipulation (see the genuine-vs-manufactured check), the but-for collapses to close to "
         "this same number — there's nothing to strip out."),
    ]
    if _behind(F):
        body.append("Treat the live figure as the working number, but have the Consultant Review confirm it before "
                    "you put a but-for delay in front of a client or consultant — that F9-verified figure is the "
                    "claim-grade one, never an estimate.")
    return K.A("Here's the honest read on the but-for delay.",
               body,
               advice=[K.go_deeper('Consultant Review', 'To compute the F9-verified but-for delay')],
               evidence=[K.ev('EVM', 'Live delay', _sd(F))])


def t02q03(F, role):
    """Window-by-window delay attribution."""
    if not F.get('ok'):
        return _no_project(F)
    tr = F.get('trend')
    body = []
    if tr and tr.get('prev_delay') is not None:
        body.append(f"Between the previous update and this one, the delay moved from {K.wd(tr.get('prev_delay'))} to "
                    f"{K.wd(F.get('delay_days'))} — {('a further ' + K.wd(tr.get('delta')) + ' lost' if (tr.get('delta') or 0) > 0 else ('a recovery of ' + K.wd(tr.get('delta')) if (tr.get('delta') or 0) < 0 else 'no net change'))} "
                    "this window. That's the most recent slice; the full window-by-window breakdown needs the intermediate updates.")
    else:
        body.append(f"With only this data date ({F.get('data_date')}) loaded I can give you the **net** position — "
                    f"the finish is {K.delay_phrase(F)} — but not each period's share of it.")
    body.append("A proper windows / time-slice analysis (the shape your claims consultant will want) is what **Update "
                "vs Update** produces: how far the forecast finish moved each period and which activities drove each "
                "move. Load the intermediate updates and I'll attribute the slip window by window.")
    if _behind(F):
        dl = K.driver_line(F)
        if dl:
            body.append("The recurring cause across windows is almost certainly the same front driving it now: " + dl)
    return K.A("Delay by window — what I can do now, and what needs the earlier updates.",
               body,
               advice=[K.go_deeper('Update vs Update', 'For the per-window slip attribution'),
                       "Load each intermediate update so the analysis can slice the delay by period."],
               evidence=[K.ev('EVM', 'Net delay', _sd(F)),
                         K.ev('Trend', 'Direction', (tr or {}).get('direction'))])


def t02q04(F, role):
    """Has the critical path shifted since baseline / float migration?"""
    if not F.get('ok'):
        return _no_project(F)
    nf = F.get('neg_float_count')
    body = [
        ("Float has clearly migrated in this update: " + (_neg_float_line(F) or
         f"the critical density is graded {F.get('cpli_grade')}") +
         " Work that once had slack is now controlling — that's what a shifted critical path looks like in the numbers."),
        (f"The driving front today is where the shortfall concentrates: " + (K.driver_line(F) or
         "spread across the works in progress.") + " If that isn't where the baseline critical path ran, the "
         "controlling chain has moved."),
        ("Confirming that the *specific* chain differs from baseline — and by how much float — is a Critical Path "
         "Analyzer / Baseline Revision Comparison job (it needs both schedules side by side); that comparison isn't "
         "computed at import, so run it there for the exact migration."),
    ]
    if F.get('cpli_critical_count'):
        body.append(f"Scale of it: about **{F.get('cpli_critical_count')}** activities ({K.pct(F.get('cpli_critical_pct'))}) "
                    "are now at critical float — a wide front for a single controlling path, so watch for a second chain "
                    "turning critical behind the first.")
    return K.A("Yes — the numbers show float has migrated onto the current driving front.",
               body,
               advice=[K.go_deeper('Critical Path Analyzer', 'To compare the driving path against baseline'),
                       "Watch the second-ranked front — a few more days lost and you'll be recovering two critical paths."],
               evidence=[K.ev('Float', 'Negative-float activities', nf),
                         K.ev('Critical path', 'Critical activities', F.get('cpli_critical_count'))])


def t02q05(F, role):
    """Which phase carries the slip — engineering, procurement or construction?"""
    if not F.get('ok'):
        return _no_project(F)
    dl = K.driver_line(F)
    head = ("The slip is concentrated in **construction / site execution**, not the office."
            if (K.main_driver(F) and _behind(F)) else "Here's where the programme stands by discipline.")
    body = [
        (f"Overall you're at **{K.pct(F.get('actual_pct'))}** actual against **{K.pct(F.get('planned_pct'))}** planned"
         + _gap_points(F) + " — and that shortfall isn't spread evenly."),
    ]
    ds = sorted(F.get('disciplines') or [], key=lambda d: (_num(d.get('weight')) or 0), reverse=True)
    for d in ds[:6]:
        gap = _num(d.get('gap')) or 0
        state = 'behind plan' if gap > 2 else ('ahead of plan' if gap < -2 else 'on plan')
        body.append(f"• **{d.get('name')}** — {d.get('actual')}% done vs {d.get('planned')}% planned "
                    f"(~{round((_num(d.get('weight')) or 0)*100)}% of the project by weight): {state}.")
    if dl:
        body.append("So the concentration is clear: " + dl + " Engineering and procurement carry little weight, so "
                    "they don't move the finish much on their own — but a design line far behind can still hold "
                    "the construction work it releases, which the engineering & procurement answer checks.")
    body.append("Read that as a direction for management attention: the slip is on site, on the front named above. "
                + K.cause_line(F))
    return K.A(head, body,
               advice=["Point recovery and management attention at the weighted driver first — it moves the date most.",
                       K.go_deeper('Update Analysis', 'For the per-discipline detail against baseline')],
               evidence=[K.ev('EVM', 'Actual vs planned', f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('Progress', 'Driver', (K.main_driver(F) or {}).get('name'))])


def t02q06(F, role):
    """Is out-of-sequence progress flattering the status?"""
    if not F.get('ok'):
        return _no_project(F)
    oos = F.get('oos_count')
    head = (f"Only at the margins — **{oos} activities** are progressing out of sequence."
            if oos else "No — there's no out-of-sequence progress flattering the status.")
    body = []
    if oos:
        body.append(f"The audit flags **{oos}** out-of-sequence activities ({K.pct(F.get('oos_pct'))} of the schedule, "
                    f"graded **{F.get('oos_grade')}**"
                    + (f", of which {F.get('critical_oos')} are on the critical path" if F.get('critical_oos') else "")
                    + "). Out-of-sequence work is statused ahead of its logic, which can inflate percent-complete and "
                    "make a front look healthier than it is, because retained-logic F9 still holds the successors back.")
        if _behind(F):
            body.append(f"But it's nowhere near enough to explain the slip — the finish is {K.delay_phrase(F)}, and "
                        f"{oos} activities can't manufacture that. The delay is real; the OOS is a data-quality flag, "
                        "not the cause.")
        body.append("Still, clean it before you trust the progress line: confirm those activities were genuinely "
                    "worked (not force-statused), fix the logic or the actuals, and re-run so earned value reflects "
                    "real, in-sequence progress.")
    else:
        body.append("Out-of-sequence progress is effectively nil here, so your percent-complete isn't being propped "
                    "up by work statused ahead of its logic. The progress line can be trusted on that count.")
    return K.A(head, body,
               advice=[K.go_deeper('Out of Sequence', 'To review and correct each flagged activity'),
                       "Confirm the flagged activities were really executed before relying on the earned value."],
               evidence=[K.ev('Out-of-sequence', 'Activities', oos),
                         K.ev('Out-of-sequence', 'On critical path', F.get('critical_oos')),
                         K.ev('Out-of-sequence', 'Grade', F.get('oos_grade'))])


def t02q07(F, role):
    """Is a constraint holding the finish artificially and hiding the slip?"""
    if not F.get('ok'):
        return _no_project(F)
    hc = _akpi(F, 'hard_constraints')
    nf = F.get('neg_float_count')
    computable = F.get('hard_constraints_computable')
    head = ("No sign of a constraint burying the slip — your negative float is showing honestly."
            if nf else "Here's how to tell whether a constraint is masking the finish.")
    body = [
        ("The tell is simple: if a hard *finish-on* or *finish-no-later-than* constraint were suppressing the delay, "
         "float would be pinned at zero and the finish would look artificially safe. Instead " +
         (_neg_float_line(F).rstrip('.') or "the schedule is calculating float openly") +
         ", and the finish is calculating right through"
         + (f" to about {F['forecast_finish']}" if F.get('forecast_finish') else '') + " — the delay isn't being masked."),
    ]
    if computable is False:
        body.append("One honest caveat: the contract-milestone constraint check needs your contract dates, which "
                    "aren't ingested here, so I can't audit each mandatory constraint against its obligation — run "
                    "the DCMA constraint check / Schedule Audit for that.")
    body.append("Best practice regardless: run the hard-constraint check every update. A late-added mandatory finish "
                "is the classic way a real slip gets buried, and it's cheap to rule out.")
    return K.A(head, body,
               advice=[K.go_deeper('Schedule Audit', 'For the hard-constraint / mandatory-date check'),
                       "Re-run the constraint audit every period so a newly-added finish constraint can't hide a slip."],
               evidence=[K.ev('Float', 'Negative-float activities', nf),
                         K.ev('Constraints', 'Contract-date check', 'needs contract dates' if computable is False else None)])


def t02q08(F, role):
    """Did a calendar change absorb the slip?"""
    if not F.get('ok'):
        return _no_project(F)
    body = [
        (f"Nothing in this file points to a hidden calendar inflation — the delay reads cleanly as {K.delay_phrase(F)}, "
         "which it wouldn't if someone had quietly widened the working calendar to soak the slip up."),
        (f"The schedule carries **{F.get('calendar_count') or 'several'} calendars**; whether any of them gained extra "
         "working days or shifts versus baseline is a **Calendar Audit** (baseline-vs-update) question — that calendar "
         "comparison isn't computed at import, so run it there to confirm no capacity was slipped in."),
        ("Keep the distinction clear: a *declared* night shift or 6-day week as a deliberate recovery lever is "
         "legitimate and shows up in the what-if; what you're guarding against is an *undeclared* calendar change that "
         "masks the delay — and there's no sign of that here."),
    ]
    return K.A("Not detected — the delay isn't being absorbed by a quiet calendar change.",
               body,
               advice=[K.go_deeper('Calendar Audit', 'To compare the working calendars against baseline')],
               evidence=[K.ev('Calendars', 'In the schedule', F.get('calendar_count')),
                         K.ev('EVM', 'Delay (reads cleanly)', _sd(F))])


def t02q09(F, role):
    """SPI says one thing, the finish date another — why?"""
    if not F.get('ok'):
        return _no_project(F)
    spi = F.get('spi')
    head = "They measure different things — that's why SPI and the finish date can disagree."
    body = [
        (f"**SPI ≈ {K.ratio(spi)}** ({K.pct(F.get('pace_pct'))} of plan) is a weighted average across **all "
         f"{F.get('activity_count') or 'the'} activities** — it blends your on-track fronts in with the lagging ones, "
         "so it's a whole-project *performance* number."),
        (f"The **finish date** is driven only by the **critical chain**. The finish is {K.delay_phrase(F)}, because "
         "that's what the driving path is doing — regardless of how well the non-critical work is progressing."),
        ("So non-critical progress can prop SPI up while the date still slips (or, less often, the reverse). They're "
         "not in conflict — they're answering different questions."),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append("Here, the gap between them is exactly the concentration of the slip: " + dl +
                    " Good progress elsewhere lifts SPI without moving the finish.")
    body.append("Rule of thumb: for the **completion date**, trust the critical path; use **SPI** for overall "
                "performance and cost-earned pace, not for timing.")
    return K.A(head, body,
               advice=[K.go_deeper('Critical Path Analyzer', 'To see the chain that actually sets the date')],
               evidence=[K.ev('EVM', 'SPI', K.ratio(spi)),
                         K.ev('EVM', 'Delay (critical path)', _sd(F))])


def t02q10(F, role):
    """Open ends / dangling logic / stale data date understating the slip?"""
    if not F.get('ok'):
        return _no_project(F)
    oe = F.get('open_ends')
    dg = F.get('dangling_count')
    body = [
        (f"Here the delay **is** calculating through — the finish is {K.delay_phrase(F)}, so nothing is swallowing it "
         "in a broken forward pass."),
        ((("Logic gaps to close as housekeeping: "
           + " and ".join(x for x in (f"**{oe} open ends**" if oe else '', f"**{dg} dangling logic links**" if dg else '')
                          if x)
           + ". Open ends and danglers let a chain fail to drive its successors, which *can* understate a slip — so "
             "close them off so every path is carried through the forward pass — but at these counts they aren't "
             "hiding the delay in this update.") if (oe or dg) else
          "No open ends or dangling links to close — every path is carried through the forward pass.")),
        (f"On the data date: it's at **{F.get('data_date')}**. If that were stale the slip would read low; a current "
         "data date means the delay isn't being understated by an old cutoff."),
    ]
    return K.A("The delay is propagating correctly — the open ends are housekeeping, not a hidden slip.",
               body,
               advice=[K.go_deeper('Schedule Audit', 'To close the open ends and dangling links'),
                       "Fix the open ends so every chain drives its successors, then re-run and re-check the finish."],
               evidence=[K.ev('Open ends', 'Count', oe),
                         K.ev('Dangling', 'Links', dg),
                         K.ev('Update', 'Data date', F.get('data_date'))])


def t02q11(F, role):
    """Are the actuals realistic, or back-dated / force-fed?"""
    if not F.get('ok'):
        return _no_project(F)
    oos = F.get('oos_count')
    wd = _akpi(F, 'whole_day')
    head = "Mostly realistic — and tellingly, the numbers aren't flattering, which itself argues against force-feeding."
    body = [
        (f"If progress had been force-fed to look on track, you'd expect the finish to read better than it does. "
         f"Instead it's {K.delay_phrase(F)} — an honest, if painful, picture."),
        (f"The one fingerprint to chase is out-of-sequence progress — **{oos} activities** flagged. OOS is the classic "
         "tell of work statused to look started when the logic says it couldn't be; have the responsible team confirm "
         "those were genuinely executed."
         if oos else "Out-of-sequence progress is effectively nil, so there's no sign of work statused ahead of its logic."),
    ]
    whole = wd.get('whole_day_count') or wd.get('count')
    if whole:
        body.append(f"Also worth a glance: **{whole}** activities show suspiciously round whole-day actuals — sometimes "
                    "a sign of estimated rather than measured progress. Spot-check a few against site records.")
    body.append("Beyond those, watch for any actual dates sitting beyond the data date (impossible actuals). Nothing "
                "in the headline suggests systematic back-dating here.")
    return K.A(head, body,
               advice=[K.go_deeper('Schedule Audit', 'For the whole-day and out-of-sequence tells'),
                       "Have the site team confirm the out-of-sequence activities were really worked."],
               evidence=[K.ev('Out-of-sequence', 'Activities', oos),
                         K.ev('Actuals', 'Whole-day actuals', whole)])


def t02q12(F, role):
    """Which baseline revision is where the finish first blew out?"""
    if not F.get('ok'):
        return _no_project(F)
    body = [
        ("Pinpointing the revision where the finish first moved — and what pushed it — is exactly what the **Baseline "
         "Revision Comparison** finish-slip driver bridge does, run across your successive approved baselines. That "
         "cross-baseline trace needs those earlier baselines loaded; it isn't computed from a single snapshot."),
        (f"With just the current baseline and this update, what I can tell you is that the "
         f"{('slip of ' + K.wd(F.get('delay_days')) if _behind(F) else 'current position')} is **live-progress "
         "movement against the baseline finish"
         + (f" of {F['baseline_finish']}" if F.get('baseline_finish') else '') + "** — not a baseline change in this file."),
        ("Load the earlier approved baselines (REV.00, REV.01, …) and I'll show exactly which revision introduced the "
         "movement and how much each one added — the trace your claims consultant will want."),
    ]
    return K.A("To trace when the slip entered, I need the earlier baselines — here's what this file shows.",
               body,
               advice=[K.go_deeper('Baseline Revision Comparison', 'To trace the slip revision by revision'),
                       "Load the successive approved baselines so the driver bridge can pinpoint the revision."],
               evidence=[K.ev('EVM', 'Slip vs baseline finish', _sd(F)),
                         K.ev('Baseline', 'Baseline finish', F.get('baseline_finish'))])


def t02q13(F, role):
    """Assemble it all into one forensic delay report."""
    if not F.get('ok'):
        return _no_project(F)
    body = [
        ("Yes — **Reporting Studio** composes this into one pack (PDF/Word plus an Excel export) from the results you "
         "pick. Here's the spine I'd assemble for a client / claims-consultant delay report:"),
        (f"• **Headline** — SPI ≈ {K.ratio(F.get('spi'))}, finish {K.delay_phrase(F)}"
         + K.dates(F, " (forecast ~{ff} vs baseline {bf})") + "."),
        ("• **Driving path** — " + (K.driver_line(F) or "the controlling chain and its float") +
         f", with about {F.get('cpli_critical_count') or '—'} activities at critical float."),
        ("• **Root-cause / but-for** — the Consultant Review confirming the slip is genuine (no logic or lag "
         "manipulation), and the Baseline Revision trace of when it entered."),
        ("• **Recovery options** — the what-if scenarios you've tested, each with its modelled day-gain."),
    ]
    body.append("Frame the whole pack as **delay indicators and evidence** for your claims consultant — the schedule "
                "supports the narrative; it does not, and should not, assert entitlement. That framing is what keeps "
                "the report credible.")
    return K.A("Yes — here's the forensic delay pack I'd build, and where it comes from.",
               body,
               advice=[K.go_deeper('Reporting Studio', 'To compose and export the pack'),
                       "Pull the Consultant Review and Critical Path results in as sections so the narrative is evidenced."],
               evidence=[K.ev('EVM', 'Headline delay', _sd(F)),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi')))])


# ── shared bits ────────────────────────────────────────────────────────────────

def _sd(F):
    """Signed delay chip value."""
    d = _num(F.get('delay_days'))
    if d is None:
        return None
    d = round(d)
    return f"+{d} wd (behind)" if d > 0 else (f"{d} wd (ahead)" if d < 0 else "on date")


def _gap_points(F):
    a, p = _num(F.get('actual_pct')), _num(F.get('planned_pct'))
    if a is None or p is None:
        return ""
    diff = round(p - a)
    if diff > 0:
        return f", about {diff} points behind the curve"
    if diff < 0:
        return f", about {abs(diff)} points ahead of the curve"
    return ", right on the curve"


ANSWERS = {
    't02q00': t02q00, 't02q01': t02q01, 't02q02': t02q02, 't02q03': t02q03, 't02q04': t02q04,
    't02q05': t02q05, 't02q06': t02q06, 't02q07': t02q07, 't02q08': t02q08, 't02q09': t02q09,
    't02q10': t02q10, 't02q11': t02q11, 't02q12': t02q12, 't02q13': t02q13,
}
