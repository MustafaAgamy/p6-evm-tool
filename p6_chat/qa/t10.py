"""Theme 10 — Subcontractor, Interface & Coordination.

Managing the job by package and handoff rather than by discipline alone: who is furthest
behind and needs the pressure this week, whether the interface milestones (access handover,
free-issue, permits, trade-to-trade handoffs) are network-driven on BOTH sides, and where
trades collide in the same area. Every answer is grounded in FACTS — the weighted
progress-by-category roll-up (the tool's proxy for packages), the DCMA-style logic flags
(open ends, dangling links, out-of-sequence) that expose a one-sided interface, and the
critical-path density. Where the schedule genuinely can't ground the question — spatial
occupancy is the honest example — the answer says so plainly and gives the planning read,
never a fabricated figure. It points to Update Analysis, the Schedule Audit / Health Review
and the Construction Knowledge Base for the exact per-activity detail.
"""
from . import _kit as K


def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can rank your "
              "packages, check the interface logic and read the coordination risk from your own "
              "numbers — offline, nothing leaves your PC."])


def _ranked_behind(F):
    """Disciplines/categories that are behind, ranked by weight × gap (the real drag on the
    finish, not the largest raw gap). Returns a list of discipline dicts, worst first."""
    behind = []
    for d in (F.get('disciplines') or []):
        gap = d.get('gap')
        wgt = d.get('weight')
        try:
            if gap is not None and float(gap) > 0:
                behind.append(d)
        except (TypeError, ValueError):
            continue
    return sorted(behind, key=lambda d: (float(d.get('gap') or 0) * float(d.get('weight') or 0)),
                  reverse=True)


def t10q00(F, role):
    """Rank subcontractors / scope packages by how far behind plan — who to push this week."""
    if not F.get('ok'):
        return _no_project(F)

    driver = K.main_driver(F)
    ranked = _ranked_behind(F)
    _, pace = K.spi_verdict(F)

    if driver:
        head = (f"Push **{driver.get('name')}** first this week — on the weighted read it's the "
                f"package carrying the delay, and pressure anywhere else moves the finish less.")
    elif ranked:
        head = (f"**{ranked[0].get('name')}** is the one to lean on this week — it's the widest "
                "shortfall against plan, though nothing yet dominates the finish.")
    else:
        head = ("No package is dragging the finish right now — everything is broadly on or ahead "
                "of plan. Keep the pressure even and protect the driving path.")

    body = [
        "Manage this one by **package and handoff**, not just by the engineering / procurement / "
        "construction split — a PM chases the sub that's slipping, not the discipline. The nearest "
        "thing the tool holds to a package ranking is the weighted progress-by-category roll-up, so "
        "I've ranked each category planned-vs-actual and weighted it by its share of the job. That "
        "tells you where the days are actually being lost.",
    ]

    if ranked:
        body.append("Worst-performer order, most drag on the finish first:")
        for i, d in enumerate(ranked[:4], start=1):
            wpct = round((d.get('weight') or 0) * 100)
            tag = "push first" if i == 1 else ("push second" if i == 2 else "watch")
            body.append(
                f"**{i}. {d.get('name')}** — {d.get('actual')}% done against {d.get('planned')}% "
                f"planned by now ({d.get('gap')}-point gap, {wpct}% of the job by weight) — *{tag}*.")
        dline = K.driver_line(F)
        if dline:
            body.append("Why that order: " + dline + " A wide gap on a 1%-weight design line is "
                         "noise next to a moderate gap on the main construction front — so I rank by "
                         "weight × gap, not by the raw gap alone.")
    else:
        body.append("Every category is sitting on or ahead of its planned curve, so there's no "
                     "single sub to single out — which is the good news you can report.")

    body.append(f"For the whole-job backdrop: {pace}, with **{K.pct(F.get('actual_pct'))}** physically "
                f"complete against **{K.pct(F.get('planned_pct'))}** planned. That's the pressure you're "
                "sharing out across the packages above.")

    body.append("One honesty note: this is a **category** roll-up, not a true sub-by-sub split by "
                "activity code and WBS. Two subs inside one category can be moving in opposite "
                "directions and this roll-up would average them. To rank the actual subcontractors — "
                "their own activities, planned-vs-actual by activity code and WBS branch — that's "
                "**Update Analysis**, where each package is measured against the baseline on its own "
                "activities.")

    if role == 'planning':
        body.append("For the pre-meeting pack, cross the ranking with total float: a package that's "
                     "behind **and** sitting on the driving path (negative or near-zero float) is a "
                     "harder push than one behind but with float to absorb it.")

    advice = [
        (f"Put **{driver.get('name')}** at the top of the look-ahead and the sub meeting this week; "
         f"give the second package a recovery target, not just a nudge." if driver else
         "Set a recovery target per behind-plan package in the look-ahead, worst first."),
        "Rank by weight × gap, not raw gap — chase the front that actually moves the date.",
        K.go_deeper('Update Analysis', 'For the true package-by-package ranking by activity code'),
    ]

    top_gap = ranked[0].get('gap') if ranked else None
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Overall SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Actual vs planned',
                              f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('Update Analysis', 'Worst package (weighted)',
                              (f"{driver.get('name')} · {driver.get('gap')}-pt gap" if driver else
                               (f"{ranked[0].get('name')} · {top_gap}-pt gap" if ranked else None)))])


def t10q01(F, role):
    """Interface handoffs (sub-to-sub, client free-issue/access/permits) — tied to logic both sides?"""
    if not F.get('ok'):
        return _no_project(F)

    oe = F.get('open_ends')
    dcount = F.get('dangling_count')
    oos = F.get('oos_count')
    coos = F.get('critical_oos')

    flags = []
    if oe:
        flags.append(f"**{oe} open end{'s' if oe != 1 else ''}**")
    if dcount:
        flags.append(f"**{dcount} dangling logic link{'s' if dcount != 1 else ''}**")
    if oos:
        flags.append(f"**{oos} out-of-sequence item{'s' if oos != 1 else ''}**")

    if flags:
        head = ("The schedule doesn't label which activities are interfaces — but it flags the "
                "one-sided logic where a one-sided interface hides, and there are "
                + ", ".join(flags) + " to walk through.")
    else:
        head = ("No open-end or dangling-logic flags on this file — the network looks tied down — "
                "but the interface milestones still need eyeballing by hand, because the tool can't "
                "tell an access-handover milestone from any other activity.")

    body = [
        "A properly tied-down interface — an **access handover, a client free-issue, a permit, or a "
        "trade-to-trade handoff** — has a real driving **predecessor feeding it** and a driven "
        "**successor coming off it**. Network-driven on *both* sides. If one side is missing, the "
        "milestone floats free: it won't move when the work around it moves, and that is exactly "
        "where accountability and claims exposure hide when a handoff is late.",
    ]

    if flags:
        parts = []
        if oe:
            parts.append(f"the **{oe} open end{'s' if oe != 1 else ''}** are activities with a loose "
                         "start or finish — no driver on one side (DCMA logic checks 4/5)")
        if dcount:
            parts.append(f"the **{dcount} dangling link{'s' if dcount != 1 else ''}** are tied at one "
                         "end only — a start with no finish driver, or the reverse")
        if oos:
            crit = (f", **{coos}** of them on the driving path" if coos else "")
            parts.append(f"the **{oos} out-of-sequence item{'s' if oos != 1 else ''}** are progressing "
                         f"against their logic{crit} — a sign the planned handoff order isn't holding")
        body.append("Reading them: " + "; ".join(parts) + ". Any one of these sitting on a handover, "
                     "free-issue or permit milestone **is** a one-sided interface — that's the list to "
                     "chase, both ends.")
    else:
        body.append("With no logic flags raised, the mechanical checks are clean — but 'clean logic' "
                     "isn't the same as 'every interface tied down', because the schedule carries no "
                     "'interface' attribute for the tool to test against. You still have to identify the "
                     "handoff milestones by name and confirm each has a driver on both sides.")

    body.append("Honest limit: I can't hand you a labelled interface list — the P6 file doesn't carry "
                "an interface flag, so the tool sees these as ordinary activities. What it *can* do is "
                "give you the per-activity open-end / dangling / out-of-sequence findings in the "
                "**Schedule Audit** (each with two suggested fixes) and the graded logic quality in the "
                "**Schedule Health Review**. Filter those findings to your handover, free-issue and "
                "permit milestones and you have your one-sided-interface list.")

    body.append("Then let the **Construction Knowledge Base / Constructability** view confirm the "
                "handoff sequence is actually buildable in that order — a tied-down but wrong sequence "
                "is still a problem.")

    if role == 'planning':
        oeg, dg, og = F.get('open_ends_grade'), F.get('dangling_grade'), F.get('oos_grade')
        gline = ", ".join(g for g in [
            (f"open ends **{oeg}**" if oeg else None),
            (f"dangling **{dg}**" if dg else None),
            (f"out-of-sequence **{og}**" if og else None)] if g)
        if gline:
            body.append("Graded logic quality on these checks: " + gline +
                        " — that's the health scores the audit assigns, so you can see whether the "
                        "one-sided logic is a handful of items or a systemic gap.")

    advice = [
        "Pull every access-handover, free-issue and permit milestone into one filter and confirm each "
        "has a driving predecessor AND a driven successor — tie down any that don't, both ends.",
        "Protect the trade-to-trade handoff chains first — a one-sided interface on the driving path "
        "is where a late handover turns straight into a claim.",
        K.go_deeper('Schedule Audit', 'For the flagged activities to work from'),
    ]

    return K.A(head, body, advice=advice,
               evidence=[K.ev('Open ends', 'Loose ends', oe),
                         K.ev('Dangling', 'One-sided links', dcount),
                         K.ev('Out-of-sequence', 'Against logic', oos),
                         K.ev('Out-of-sequence', 'On driving path', coos)])


def t10q02(F, role):
    """Trade-stacking / spatial congestion on the driving path — a genuine gap."""
    if not F.get('ok'):
        return _no_project(F)

    head = ("Honestly, the tool can't ground this one — it reads **logic and dates**, not who "
            "occupies which area when, so I can't compute trade-stacking or spatial congestion for you.")

    body = []
    gap = K.gap_note('GAP — schedule has no area-by-time occupancy model; trade-stacking / '
                     'spatial congestion not computed')
    if gap:
        body.append(gap)

    body.append("To answer it properly the schedule would need a **zone / area code on every activity** "
                "and an **area-by-time occupancy model** run over the driving path — the tool would then "
                "flag where more crews are planned in one area than the area can physically carry at "
                "once. That data model isn't in the P6 file today, so there's no honest number I can "
                "give you here.")

    body.append("The planning read in the meantime is by eye, and it's a real risk: spatial congestion "
                "and trade-stacking are one of the biggest quiet causes of lost productivity and "
                "interface clashes, and they never show up in the logic — the network can be perfectly "
                "sound and still be un-buildable because three trades are booked into the same slab in "
                "the same week.")

    dpc = F.get('driving_path_count')
    nfc = F.get('neg_float_count')
    where = []
    if K.chain_facts(F):
        where.append(K.chain_name(F))
    elif dpc:
        where.append(f"the **{dpc} activities P6 flags as driving**")
    if nfc:
        where.append(f"the **{nfc} activities on negative float**")
    if where:
        body.append("Where to look first: walk " + " and ".join(where) + " and find the stretches where "
                     "several of them run **concurrently in the same physical area**. That overlap is "
                     "the pinch-point — same slab, same shaft, same deck, same week. It ties straight "
                     "into the interface question: the handoff between one trade finishing and the next "
                     "starting in that area is exactly where stacking bites.")
    else:
        body.append("Where to look first: take the driving path and find the stretches where several "
                     "activities run **concurrently in the same physical area** — that overlap is the "
                     "pinch-point, and it's the same place the trade-to-trade handoffs live.")

    body.append("So walk the busiest area with the sub and confirm the space can actually carry the "
                "crews the plan assumes working there at once. If it can't, the fix is to **sequence** "
                "the trades through that area — which is a logic change the tool *can* then check for "
                "you.")

    if role == 'planning':
        body.append("If you want a first-cut congestion proxy today, add an area code as an activity "
                     "code, filter the driving path by area, and eyeball concurrent activity counts per "
                     "area per week in a resource/usage profile — it's manual, but it approximates the "
                     "occupancy model until a proper zone-by-time view is built.")

    advice = [
        "Add a zone / area code to your activities now — it's the one piece of data that would let this "
        "be computed later, and it costs nothing to start coding it.",
        "Walk the busiest area on the driving path with the sub and confirm it can carry the planned "
        "crews at once; if not, re-sequence the trades through it rather than stacking them.",
    ]

    return K.A(head, body, advice=advice,
               evidence=[K.ev('Critical Path Analyzer', 'Driving-path activities', dpc),
                         K.ev('Float', 'Negative-float activities', nfc)])


ANSWERS = {
    't10q00': t10q00,
    't10q01': t10q01,
    't10q02': t10q02,
}
