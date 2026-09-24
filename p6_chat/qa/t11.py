"""Theme 11 — Commissioning, Handover & Close-out.

The final phase, where jobs quietly overrun: testing and commissioning (T&C), systems
completion, punch-listing, handover and the paperwork close-out (as-builts, O&M manuals,
demobilisation, retention release). F9 will happily schedule a handover milestone straight
off the last construction activity with no T&C chain in between and no close-out logic behind
it — and the plan then reads finished when it can't be handed over. Every answer is grounded
in FACTS: the finish position and its weighted driver (so we can say honestly whether
commissioning is governing the date yet or still hanging off the construction tail), the
progress-by-category roll-up (the tool's proxy for a commissioning / close-out package), and
the logic-quality audit — open ends and dangling links, which is exactly where a floating
close-out shows itself. Where the schedule genuinely can't ground the thing asked — the
mechanical-completion → handover working-day window, or which activities literally sit on the
critical path — the answer says so plainly and points at the Critical Path Analyzer, Calendar
Audit, Constructability Review, Schedule Audit and Health Review, and never invents a number
the file doesn't hold. Cost is derived from percent-complete in these schedules, so CPI sits
near 1.0 by construction and is not the signal — SPI and the finish are.
"""
from . import _kit as K


# ── grounds per question (drives the go-deeper pointers) ──────────────────────────
GROUNDS = {
    't11q00': 'EVM, Critical Path Analyzer, Update Analysis',
    't11q01': 'Constructability Review + Construction Knowledge Base, Schedule Audit',
    't11q02': 'Critical Path Analyzer, Calendar Audit',
    't11q03': 'Schedule Audit, Schedule Health Review, '
              'Constructability Review + Construction Knowledge Base',
}


# ── shared, None-safe helpers (run at call time, no import side effects) ───────────

def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can tell you "
              "how the commissioning tail is tracking and whether close-out is tied into the logic "
              "— from your own numbers, offline, nothing leaves your PC."])


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _behind(F):
    d = _num(F.get('delay_days'))
    return d is not None and d > 0


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
    return d.get('name') if d else 'the driving construction front'


# Keyword sets used to spot a commissioning / close-out CATEGORY in the weighted
# roll-up. This is grounded — it reads the discipline names the file actually carries,
# never invents one.
_TC_KEYS = ('commiss', 't&c', 't & c', 'testing', 'pre-comm', 'precomm', 'pre comm',
            'start-up', 'startup', 'start up', 'energis', 'energiz', 'system completion',
            'systems completion', 'no-load', 'no load', 'performance test',
            'performance trial', 'functional test')
_CLOSEOUT_KEYS = ('close-out', 'closeout', 'close out', 'as-built', 'asbuilt', 'as built',
                  'o&m', 'o & m', 'handover', 'hand-over', 'hand over', 'demob',
                  'documentation', 'retention', 'punch', 'snag')


def _match_disc(F, keys):
    """The heaviest discipline whose name contains any keyword, or None. Weighted so a
    real T&C branch wins over an incidental line that happens to match."""
    best, best_w = None, -1.0
    for d in (F.get('disciplines') or []):
        name = str(d.get('name') or '').lower()
        if any(k in name for k in keys):
            w = _num(d.get('weight')) or 0
            if w > best_w:
                best, best_w = d, w
    return best


def _disc_phrase(d):
    """Grounded one-clause read of a category's progress."""
    if not d:
        return ''
    wpct = round((_num(d.get('weight')) or 0) * 100)
    gap = d.get('gap')
    gap_txt = f", a {gap}-point gap" if gap is not None else ""
    return (f"**{d.get('name')}** is at **{d.get('actual')}%** done against **{d.get('planned')}%** "
            f"planned by now (~{wpct}% of the job by weight{gap_txt})")


def _continuity_signal(F, home):
    """The network's own tell that a tail is thin — open ends / dangling — or an honest
    'clean' line. `home` names where those loose ends most likely belong."""
    oe = F.get('open_ends')
    dang = F.get('dangling_count')
    parts = []
    if oe:
        parts.append(f"**{oe} open end{'s' if oe != 1 else ''}** — activities with no predecessor "
                     "or successor at all")
    if dang:
        dpct = F.get('dangling_pct')
        tail = f" ({K.pct(dpct)})" if dpct is not None else ""
        parts.append(f"**{dang} dangling link{'s' if dang != 1 else ''}**{tail} tied at only one end")
    if parts:
        return ("You don't have to take this on faith — the logic audit already shows the loose ends "
                "you'd expect if the tail is thin: " + " and ".join(parts) + f". {home} is the usual "
                "home for every one of them.")
    return ("The structural checks — open ends and dangling links — come back clean on this file, so a "
            f"thin {home.lower()} would show as a *missing step* rather than a torn link. That's the "
            "completeness check's job, not the logic audit's — run it before you trust the tail.")


# ── answers ────────────────────────────────────────────────────────────────────

def t11q00(F, role):
    """How is T&C tracking, and is it now on the critical path to handover?"""
    if not F.get('ok'):
        return _no_project(F)
    _, pace = K.spi_verdict(F)
    dn = _driver_name(F)
    dl = K.driver_line(F)
    driver = K.main_driver(F)
    comm = _match_disc(F, _TC_KEYS)
    driver_is_comm = bool(driver and comm and driver.get('name') == comm.get('name'))
    dpc = F.get('driving_path_count')

    if driver_is_comm:
        head = ("**Commissioning is already what's governing the date** — the T&C tail has moved onto "
                "the driving path, so from here the handover milestone tracks testing, not construction.")
    elif driver:
        head = (f"**Right now the handover date isn't being driven by commissioning — it's {dn} on the "
                "governing path.** But don't relax: the whole T&C tail hangs off that chain.")
    else:
        head = ("**Nothing is dragging the finish right now** — so read commissioning as the front to "
                "protect, because the T&C tail is what governs once construction closes out.")

    body = [
        (f"Start with the honest whole-job read: {pace}. In date terms the finish is {K.delay_phrase(F)}. "
         "That's the number the handover milestone is ultimately tracking, so the question is really "
         "*which* work is carrying it — construction or the commissioning tail."),
    ]
    if dl and not driver_is_comm:
        body.append(dl + " Every day that front loses pushes the commissioning start right into the "
                    "handover milestone, because T&C sits downstream of it — so a construction slip today "
                    "is a commissioning problem tomorrow, not a separate issue.")
    elif dl and driver_is_comm:
        body.append("And the tail is already the driver: " + dl + " That's the phase you manage day by "
                    "day from here — construction is no longer the story.")

    if comm:
        body.append("On the tail itself, your own roll-up gives me a read: " + _disc_phrase(comm) +
                    ". Track that as its **own front** now — pull it out of the aggregate and watch its "
                    "planned-vs-actual curve on its own, because a commissioning slip hidden inside a "
                    "healthy overall percentage is the classic way a job that 'looks 95% done' misses "
                    "handover by weeks.")
    else:
        body.append("One thing I can't do from the roll-up: I don't see a distinct commissioning / T&C "
                    "category in the weighted breakdown at all. That's a warning in its own right — if "
                    "T&C isn't a line you can point to, it can't be tracked against plan and it can't be "
                    "seen to move onto the path. Confirm the schedule actually carries the commissioning "
                    "scope (that's the next question) before you trust any handover date off it.")

    body.append("Whether the T&C activities are *literally* on the critical path today is a "
                "**Critical Path Analyzer** read — per-activity path membership isn't in the snapshot I "
                "hold" + (f", though the tool does read **{dpc}** driving path"
                          f"{'s' if dpc != 1 else ''} through this schedule" if dpc else "") +
                ". EVM gives you the category progress, Update Analysis the period-over-period movement, "
                "and the CPA confirms whether the tail is already governing. Put those three together and "
                "you have the real answer, not a feel.")

    if role == 'planning':
        body.append("Planner's cut: isolate the commissioning WBS branch, check its total float against "
                    "the driving construction front, and watch for the crossover — the update where T&C "
                    "float goes to zero is the update the path hands over to the tail, and it usually "
                    "happens quietly.")

    advice = [
        "Pull the commissioning / T&C category out of the aggregate and track it as its own front now, "
        "before construction hands it the path.",
        f"Confirm in the Critical Path Analyzer whether the T&C chain is already governing behind **{dn}** "
        "— that's the trigger to switch your weekly focus to the tail.",
        K.go_deeper(GROUNDS['t11q00']),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Delay to completion', _delay_chip(F)),
                         K.ev('EVM', 'Commissioning progress',
                              (f"{comm.get('actual')}% vs {comm.get('planned')}% planned" if comm else None)),
                         K.ev('Critical Path Analyzer', 'Driving paths', dpc)])


def t11q01(F, role):
    """Does the schedule contain the T&C / punch / handover chain, or jump to completion?"""
    if not F.get('ok'):
        return _no_project(F)
    comm = _match_disc(F, _TC_KEYS)
    close = _match_disc(F, _CLOSEOUT_KEYS)
    head = ("**Run the Constructability completeness check against your project-type playbook before you "
            "trust the tail — that's the only honest way to know.**")

    body = [
        "The check reads your logic against the Construction Knowledge Base for your project type and "
        "flags the T&C and handover steps that ought to be there and aren't. For a job of this kind the "
        "standard chain I'd expect to see — and the order the playbook holds — is roughly: energisation "
        "and loop checks, no-load then loaded functional runs, system-by-system commissioning, a "
        "performance or throughput trial, punch-listing, then the handover milestone. Not construction "
        "straight into a completion flag.",
    ]

    if comm:
        body.append("Your schedule isn't starting from nothing — I can see a " + _disc_phrase(comm) +
                    " in the weighted breakdown, so at least some T&C scope is carried as real work. But "
                    "a category line isn't proof the *sub-steps* are all there: you can have a "
                    "'Commissioning' branch that's really just one summary activity with no loop checks, "
                    "no functional runs and no performance trial underneath it. The completeness check is "
                    "what confirms the chain, step by step.")
    else:
        body.append("Here's the first flag, straight from your own roll-up: I can't see a distinct "
                    "commissioning / testing / handover category in the weighted breakdown at all. That "
                    "is the classic 'construction straight into completion' signature. It's possible the "
                    "scope is buried inside a construction branch — but if it isn't a line you can point "
                    "to and track, it's effectively living in someone's head, not in the logic.")

    body.append(_continuity_signal(F, 'The T&C and handover tail'))

    body.append("One scope note I'll be straight about, because it's deliberate: the missing-activity "
                "check stays on **construction and execution** work — it flags absent T&C, punch and "
                "handover steps, it does **not** invent engineering, design or procurement lines. That's "
                "not where a builder loses continuity, and guessing there would just be noise. So treat "
                "it as a *build-completeness* check, not a whole-project one.")

    if _behind(F):
        body.append(f"And mind the direction of the fix. The job is already {K.delay_phrase(F)}; if the "
                    "check adds a real T&C chain back that was never in the plan, the honest finish moves "
                    "**later, not earlier** — you've been quoting a date off a schedule that skipped the "
                    "tail. Better to find that now than at mechanical completion.")

    advice = [
        "Run the Constructability Review against your project-type playbook and adopt every T&C / punch / "
        "handover step it flags as missing.",
        "Then re-run F9 on the completed logic before you quote a handover date — an added tail usually "
        "pushes the finish out, and that's the honest number.",
        K.go_deeper(GROUNDS['t11q01']),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Commissioning category in file',
                              (comm.get('name') if comm else 'none found in roll-up')),
                         K.ev('Open ends', 'Loose ends', F.get('open_ends')),
                         K.ev('Dangling', 'One-ended links', F.get('dangling_count')),
                         K.ev('Schedule', 'Activities in file', F.get('activity_count'))])


def t11q02(F, role):
    """Enough time MC → handover for T&C, or has the tail been compressed to hold the date?"""
    if not F.get('ok'):
        return _no_project(F)
    dn = _driver_name(F)
    cc = F.get('calendar_count')
    head = ("**That mechanical-completion-to-handover window is exactly where these jobs bleed — measure "
            "it, don't assume it.**")

    body = [
        ("The clean test is a two-step measurement, and neither step is a feel. First, read the "
         "**working-days window between mechanical completion and the handover milestone** in the "
         "Critical Path Analyzer. Then read that window against your calendar in the Calendar Audit — "
         + (f"your file carries **{cc} calendar{'s' if (cc or 0) != 1 else ''}**, and " if cc else "") +
         "weather, reduced-hours periods and single-shift working all eat into a commissioning window "
         "that looks fine on a 5-day office calendar. A window that reads adequate in raw days can be "
         "genuinely tight in *workable* days."),
        ("Here's the tell you're looking for. The job is currently " + K.delay_phrase(F) +
         (f", with **{dn}** carrying the slip" if _behind(F) else "") + ". When construction runs late, "
         "the almost-automatic move is to **crush the T&C tail to hold the handover date on paper** — "
         "the milestone stays put while mechanical completion slides toward it. If the handover date "
         "hasn't moved but MC has, commissioning has been compressed, full stop. That's not recovery, "
         "it's borrowing from the one phase you can't afford to shortchange."),
        ("And commissioning is the wrong phase to compress, because most of it **can't be parallelised**. "
         "You can't run loaded functional tests before the no-load runs, or the performance trial before "
         "the systems are individually commissioned — the chain is largely sequential, so squeezing it "
         "doesn't buy time, it just moves the failure to the trial. Protect the window; don't borrow from "
         "it to flatter a date."),
        ("Honest limit: the MC→handover window isn't a stored number I can hand you from this snapshot — "
         "it's a Critical Path Analyzer measurement between those two points, and the workable-days "
         "correction is a Calendar Audit read. I'm giving you the method and the tell, and pointing you at "
         "the two features that put the actual days on it."),
    ]

    if role == 'planning':
        body.append("Planner's cut: compare the current-update MC→handover gap against the baseline gap. "
                    "If the baseline allowed, say, a comfortable window and the current update shows the "
                    "same handover date with a later MC, the difference is exactly the compression — and "
                    "the total float on the T&C activities will already be near zero or negative to prove "
                    "it.")

    advice = [
        "Measure the MC→handover window in working days in the Critical Path Analyzer, then net off the "
        "weather / reduced-hours effect in the Calendar Audit before you call it adequate.",
        "Watch for a handover milestone that stayed put while mechanical completion slipped — that's "
        "compression dressed as a held date, and the T&C float will show it.",
        K.go_deeper(GROUNDS['t11q02']),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Delay to completion', _delay_chip(F)),
                         K.ev('Forecast', 'Finish', F.get('forecast_finish')),
                         K.ev('Calendar Audit', 'Calendars in file', cc),
                         K.ev('Critical Path Analyzer', 'Front carrying the slip',
                              (dn if _behind(F) else None))])


def t11q03(F, role):
    """Close-out activities — in the schedule and tied into logic, or left floating?"""
    if not F.get('ok'):
        return _no_project(F)
    oe = F.get('open_ends')
    dang = F.get('dangling_count')
    oeg = F.get('open_ends_grade')
    dg = F.get('dangling_grade')
    close = _match_disc(F, _CLOSEOUT_KEYS)

    if oe or dang:
        head = ("**Check this now — close-out is where your open ends almost certainly live.** As-builts, "
                "O&M manuals, final documentation, demob and retention release get routinely left "
                "floating at the end with no driving logic.")
    else:
        head = ("**Your structural logic reads clean — so the close-out risk here is a *missing* step, "
                "not a torn one.** As-builts, O&M manuals, documentation, demob and retention release are "
                "the scope most often left out entirely rather than left dangling.")

    body = [
        "This is the phase that quietly outlasts the job. Close-out — as-builts, O&M manuals, final "
        "documentation, demobilisation, retention release — is where scope gets either dropped or dumped "
        "at the end with no logic on it. If those activities are unsequenced or missing, they don't "
        "calculate through, and **final account and retention release slip well past handover even after "
        "the construction front has caught up**. That's real money and a real programme obligation, not "
        "housekeeping.",
    ]

    flags = []
    if oe:
        tail = f" (graded **{oeg}**)" if oeg else ""
        flags.append(f"**{oe} open end{'s' if oe != 1 else ''}**{tail} — activities with a loose start "
                     "or finish, driven on one side only")
    if dang:
        dpct = F.get('dangling_pct')
        tail = f" ({K.pct(dpct)}" + (f", graded {dg}" if dg else "") + ")" if (dpct is not None or dg) else ""
        flags.append(f"**{dang} dangling link{'s' if dang != 1 else ''}**{tail} tied at only one end")
    if flags:
        body.append("Your own logic audit already points the finger: " + " and ".join(flags) +
                    ". Filter those findings to your close-out activities and I'd expect a large share of "
                    "them to land there — a retention-release or as-built line with a predecessor but no "
                    "successor is the textbook floating close-out. That's the list to fix first.")
    else:
        body.append("The mechanical checks are clean here — no open ends or dangling links flagged — which "
                    "is good news but not the whole story: 'clean logic' doesn't prove the close-out scope "
                    "*exists*. A schedule that simply never modelled O&M manuals or retention release "
                    "raises no dangling flag, because there's nothing there to dangle. That's why this "
                    "needs the completeness check as well as the logic audit.")

    if close:
        body.append("For what it's worth, I can see a " + _disc_phrase(close) + " in your roll-up, so some "
                    "close-out scope is carried as real work — worth confirming its activities are tied "
                    "on both sides rather than parked as a summary line.")

    body.append("The fix is the same in every case: tie each close-out activity into logic **on both "
                "sides** — a real driving predecessor and a driven successor — and sequence the chain "
                "**behind the handover milestone, not beside it**, so it calculates through to final "
                "account and retention. A close-out that floats free won't move when the work around it "
                "moves, and that's precisely how the commercial tail slips unnoticed.")

    body.append("Honest split of the tools: the named rows come from the **Schedule Audit** open-end / "
                "dangling findings (each with two suggested fixes), the graded logic quality from the "
                "**Schedule Health Review**, and whether a close-out step is missing *entirely* from the "
                "**Constructability** completeness check. Between the three you get the full picture — "
                "what's floating, how bad, and what isn't there at all.")

    advice = [
        "Run the Schedule Audit open-end / dangling check and fix every close-out line that's tied at only "
        "one end — both ends, driver and successor.",
        "Sequence the close-out chain behind the handover milestone so as-builts, O&M, demob and retention "
        "release calculate through to final account instead of floating.",
        K.go_deeper(GROUNDS['t11q03']),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Open ends', 'Loose ends', oe),
                         K.ev('Open ends', 'Grade', oeg),
                         K.ev('Dangling', 'One-ended links', dang),
                         K.ev('Schedule Health Review', 'Float grade', F.get('float_grade'))])


ANSWERS = {
    't11q00': t11q00,
    't11q01': t11q01,
    't11q02': t11q02,
    't11q03': t11q03,
}
