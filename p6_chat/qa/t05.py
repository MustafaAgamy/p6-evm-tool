"""Theme 5 — Short-term Control & Look-ahead.

The next few weeks up close: what has already quietly slipped inside the current window, what
is blocked and not ready to start, and what the three-week look-ahead should be built around.
These three questions are one conversation — the overdue list is last week's un-cleared
blockers surfacing as slipped starts, the readiness check is next week's overdue list caught
early, and the look-ahead is the spine you hang both on — so each answer leads with its own
direct read and then folds in the sibling material it depends on, rather than repeating a thin
one-liner three times.

Every answer is grounded in FACTS: the data date the window is measured from, the signed delay
to completion, the weighted work front driving it (weight x gap, via ``K.main_driver`` /
``K.driver_line`` — never the largest raw gap), and the audit-side logic quality
(out-of-sequence, open ends, dangling links, negative float, driving-path size). The
per-activity time-status, readiness and dated look-ahead LISTS are computed in Update Analysis
and the Critical Path Analyzer; these answers give the honest network-level read and point
there for the line-by-line detail, and never invent an activity, a date, or a recovery figure
the single loaded file can't carry.
"""
from . import _kit as K


# ── shared, None-safe helpers (run at call time, no import side effects) ─────────

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


def _driver_name(F):
    d = K.main_driver(F)
    return d.get('name') if d else 'the driving work front'


def _acts(F):
    """Activity count as an int, or None."""
    n = F.get('activity_count')
    try:
        return int(n) if n is not None else None
    except (TypeError, ValueError):
        return None


def _logic_caveats(F):
    """A clause listing the logic-quality flags that distort a near-term readiness / look-ahead
    read, built from whichever facts are present. '' when the schedule is clean of them."""
    bits = []
    oos = F.get('oos_count')
    if oos:
        crit = F.get('critical_oos')
        bits.append(f"**{oos} out-of-sequence** activit{'y' if oos == 1 else 'ies'}"
                    + (f" ({crit} on the critical path)" if crit else ""))
    if F.get('open_ends'):
        oe = F.get('open_ends')
        bits.append(f"**{oe} open end{'s' if oe != 1 else ''}**")
    if F.get('dangling_count'):
        dc = F.get('dangling_count')
        bits.append(f"**{dc} dangling** logic link{'s' if dc != 1 else ''}")
    if not bits:
        return ''
    if len(bits) == 1:
        return bits[0]
    return ", ".join(bits[:-1]) + " and " + bits[-1]


def _pressure_line(F):
    """The network's own read on near-term risk, from negative total float. '' if none."""
    nf = F.get('neg_float_count')
    if not nf:
        return ''
    pct = F.get('neg_float_pct')
    tail = f" ({K.pct(pct)} of the schedule)" if pct is not None else ""
    return (f"The network's own pressure signal is already flashing: **{nf} activit{'y' if nf == 1 else 'ies'}**"
            f"{tail} carry **negative total float** — they're past due to the finish by the logic itself, so "
            "an overdue start on any of them is exactly what turns a quiet slip into a critical one.")


# ── answers ──────────────────────────────────────────────────────────────────────

def t05q00(F, role):
    """Overdue starts/finishes in the current window — the earliest slip signal."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    dd = F.get('data_date')
    head = ("Treat this as your early-warning list, not a status read — it's where the current window "
            "is already leaking days, before the slip ever reaches the critical path.")
    body = [
        (f"The line-by-line list — every activity that was due to start or finish by the **{dd}** data "
         "date and hasn't — is the earliest signal you get on this schedule. It's produced by "
         "**Update Analysis** (this update measured against the baseline) and cross-checked in the "
         "**Schedule Audit**. Catch a slip here, inside the window, and you fix it before it migrates "
         "onto the driving path and hardens into a finish slip."
         if dd else
         "The line-by-line list — every activity that was due to start or finish by the data date and "
         "hasn't — is the earliest signal you get. It's produced by **Update Analysis** (this update vs "
         "the baseline) and cross-checked in the **Schedule Audit**. Catch a slip inside the window and "
         "you fix it before it migrates onto the driving path and hardens into a finish slip."),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append("Where the overdue work is already concentrating: " + dl + " Chase that front first — "
                    "overdue items there aren't a side issue, they're literally what the finish slip is "
                    "made of.")
    else:
        body.append("No single discipline stands out as the driver in this file, so read the overdue list "
                    "front by front rather than assuming one area carries it.")
    pl = _pressure_line(F)
    if pl:
        body.append(pl)
    if F.get('delay_days') is not None:
        body.append("In date terms the finish is currently " + K.delay_phrase(F) + " — the overdue items "
                    "in this window are the leading edge of that number, not something separate from it.")
    else:
        body.append("A finish-milestone slip isn't derivable from this file, so treat the overdue list "
                    "itself as your leading indicator — it's the earliest read you have of where the date "
                    "is heading.")
    # merge-in: these overdue rows ARE last week's un-cleared blockers, and they seed the look-ahead
    body.append("Read this list alongside its two companions — the **readiness check** (what's blocked "
                "and not ready to start) and the **three-week look-ahead**. Most overdue starts are simply "
                "last week's blockers that never got cleared, and every overdue item carries straight into "
                "the look-ahead as work you're already chasing — so clearing this list is the first move in "
                "building the next one.")
    body.append("Honest caveat: I'm giving you the network-level read, not the named rows. The "
                "per-activity time-status view — overdue starts against overdue finishes, each with its "
                "own dates — is built in Update Analysis and the Schedule Audit; open those for the exact "
                "activities.")
    advice = [
        f"Chase **{_driver_name(F)}** first — that's where the overdue work concentrates and where a slip "
        "becomes a finish slip.",
        ("For the planner: sort the overdue list by total float ascending — the negative- and low-float "
         "lines are the ones already eating the completion date, so they clear before anything comfortable."
         if tech else
         "Clear this list at every weekly review, before it becomes a month of quiet drift nobody flagged."),
        K.go_deeper('Update Analysis, Schedule Audit'),
    ]
    evidence = [
        K.ev('Update Analysis', 'Data date', dd),
        K.ev('EVM', 'Delay to completion', _delay_chip(F)),
        K.ev('Float', 'Negative-float activities', F.get('neg_float_count')),
        K.ev('Out-of-sequence', 'Activities', F.get('oos_count')),
    ]
    return K.A(head, body, advice=advice, evidence=evidence)


def t05q01(F, role):
    """Readiness / blocked-work check on near-term activities."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    head = ("This is your weekly work-front management: clear the blockers a week ahead, not on the "
            "morning of the start.")
    body = [
        ("The readiness check is easy to state and easy to skip — near-term activities whose "
         "predecessors aren't finished, or whose constraints aren't cleared, are **not ready**, and "
         "pushing crews to a front that isn't ready is how you burn a week. The per-activity predecessor "
         "and constraint status is built in **Update Analysis** and the logic view of the **Critical "
         "Path Analyzer**; here's the read that tells you how far to trust it and where to point it."),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append("Point it at the front that moves the date first: " + dl + " A blocker there costs "
                    "you the finish; a blocker on a high-float front costs you very little — so readiness "
                    "on the driving chain is the check that actually matters.")
    else:
        body.append("With no single dominant driver in this file, run the readiness check across each "
                    "active front and confirm the driving chain in the **Critical Path Analyzer** first, "
                    "so you know which fronts a blocker would actually hurt.")
    cav = _logic_caveats(F)
    if cav:
        body.append("The catch is logic quality. This schedule carries " + cav + " — and each of those "
                    "can make a front look **ready when it isn't**: a missing predecessor link shows no "
                    "blocker where there really is one, and an out-of-sequence line hides an unfinished "
                    "predecessor behind work that's already been progressed. Don't trust a green 'ready' "
                    "flag until these are cleaned.")
    else:
        body.append("Helpfully, the logic is largely clean of the flags that usually distort a readiness "
                    "read — no material out-of-sequence, open-end or dangling issues — so the predecessor "
                    "status here can be taken more or less at face value.")
    body.append("And the real blockers are often not in the schedule at all: site access, free-issue "
                "material, permits, drawings, inspection sign-off. The logic tells you the sequence; you "
                "still have to confirm the physical readiness of each front yourself, a week out." +
                (" For the planner, the tell is a near-term activity with an unfinished driving "
                 "predecessor or a Start-On/After constraint that hasn't been met." if tech else ""))
    # merge-in: readiness sits between the overdue list (behind it) and the look-ahead (ahead of it)
    body.append("Tie this to its neighbours: the **overdue list** is exactly the blockers you didn't "
                "clear last week showing up as slipped starts, and the **three-week look-ahead** is where "
                "you act on this — a ready front goes into the plan, a blocked one gets its blocker worked "
                "before a crew is anywhere near it.")
    advice = [
        "Resolve the real blockers — access, free-issue, predecessor completion — a week ahead, not on "
        "the morning of the start.",
        (f"Clean the {F.get('oos_count')} out-of-sequence and {F.get('open_ends')} open-end items first — "
         "until they're fixed a 'ready' flag can't be trusted."
         if (F.get('oos_count') or F.get('open_ends')) else
         "Keep the logic clean so the readiness read stays trustworthy week to week."),
        K.go_deeper('Update Analysis, Critical Path Analyzer, Schedule Audit'),
    ]
    evidence = [
        K.ev('Out-of-sequence', 'Activities', F.get('oos_count')),
        K.ev('Open ends', 'Count', F.get('open_ends')),
        K.ev('Dangling', 'Links', F.get('dangling_count')),
        K.ev('EVM', 'Delay to completion', _delay_chip(F)),
    ]
    return K.A(head, body, advice=advice, evidence=evidence)


def t05q02(F, role):
    """Three-week look-ahead built around the driving path."""
    if not F.get('ok'):
        return _no_project(F)
    tech = (role == 'planning')
    n = _acts(F)
    listsize = f"the whole {n:,}-activity list" if n else "the whole activity list"
    head = f"I'd filter the look-ahead to what governs the date — the driving chain — not {listsize}."
    body = []
    dl = K.driver_line(F)
    if dl:
        body.append("The spine of the next three weeks is the driving chain. " + dl + " Build the "
                    "look-ahead around that front — it's the sequence the finish date is tracking, so it's "
                    "the sequence your crews, materials and inspections have to be lined up against.")
    else:
        body.append("Build the look-ahead around the driving chain — the sequence that governs the finish "
                    "— rather than the flat activity list. No single discipline dominates here, so confirm "
                    "the driving path in the **Critical Path Analyzer** first, then filter to it.")
    if F.get('delay_days') is not None:
        body.append("In date terms the finish is " + K.delay_phrase(F) + ", so read the three-week window "
                    "against that position: is the driving front gaining days back or still losing them? "
                    "That's the question the look-ahead exists to answer, week by week.")
    nf = F.get('neg_float_count')
    dpc = F.get('driving_path_count')
    second = []
    if dpc:
        second.append(f"a driving path of about **{dpc} activit{'y' if dpc == 1 else 'ies'}**")
    if nf:
        second.append(f"**{nf} activit{'y' if nf == 1 else 'ies'}** on negative total float")
    if second:
        body.append("The second front to protect is the near-critical work — " + " and ".join(second) +
                    ". Treat it as the next thing to watch, because it flips onto the critical path the "
                    "moment the current driver slips further, and a look-ahead that only tracks today's "
                    "driver gets overtaken.")
    # merge-in: the look-ahead is WHERE the overdue list and the readiness check get actioned
    body.append("This is where the other two short-term reads land: every item off the **overdue list** "
                "carries into the window as work you're already chasing, and the **readiness check** "
                "decides which upcoming fronts actually go into the plan versus which need their blocker "
                "worked first. The look-ahead is the spine; those two are what you hang on it.")
    body.append("Honest caveat: the dated line list — what actually starts and finishes inside the "
                "three-week window — is filtered in **Update Analysis**, and the driving path behind it is "
                "confirmed in the **Critical Path Analyzer**. I'm giving you the spine and the fronts to "
                "hang it on, not the dated rows." +
                (" For the planner, confirm the chain with CPLI / lowest-total-float rather than "
                 "eyeballing the bars." if tech else ""))
    advice = [
        "Use the driving chain as your look-ahead spine and hang the recovery levers off it — night "
        "shift, extra crews, re-sequencing — rather than spreading effort across the whole list.",
        "For the day-count of any recovery lever, run it through the What-if before you commit to it — I "
        "won't put a number on a scenario the schedule hasn't been re-run for.",
        K.go_deeper('Update Analysis, Critical Path Analyzer'),
    ]
    evidence = [
        K.ev('Schedule', 'Activities in file', (f"{n:,}" if n else None)),
        K.ev('EVM', 'Delay to completion', _delay_chip(F)),
        K.ev('Forecast', 'Finish', F.get('forecast_finish')),
        K.ev('CPLI', 'Driving-path activities', dpc),
    ]
    return K.A(head, body, advice=advice, evidence=evidence)


ANSWERS = {
    't05q00': t05q00,
    't05q01': t05q01,
    't05q02': t05q02,
}
