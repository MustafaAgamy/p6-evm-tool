"""Theme 12 — Engineering & Procurement.

Design deliverables and long-lead items: how the upstream office and the supply chain are
tracking, whether they actually govern the finish, and where the procure → deliver → install
chain is broken or faked. The trap this theme exists to defuse is misattribution — a poor
overall SPI blamed on "late drawings" or "slow vendors" when the weighted driver is a field
front. Every answer is grounded in FACTS: the overall EVM position, the per-discipline
planned/actual split (from which the design and procurement categories are isolated when the
file carries them), the weighted driver of the shortfall, and the logic-quality audit signals
(out-of-sequence, open ends, dangling links, lags/leads, hard constraints). The per-activity
IFC list, the driving path, the back-calculated required-on-site dates and the F9-exact slip
impacts live in Update Analysis, the Critical Path Analyzer and the What-if engine; these
answers give the honest network-level read and point there for the line-by-line detail. They
never invent an activity, a delivery date or a recovery figure the file doesn't hold, and the
submittal/PO question is answered as the deliberate gap it is.
"""
from . import _kit as K


def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can answer this "
              "from your own numbers — offline, nothing leaves your PC."])


# ── shared, F-grounded helpers (None-safe) ──────────────────────────────────────

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
    return d.get('name') if d else 'the driving work front'


# Keyword locators for the upstream categories, in priority order so the strongest match wins.
_ENG_KW = ('design', 'engineer', 'ifc', 'drawing', 'detailing', 'detail', 'shop drawing')
_PROC_KW = ('procure', 'purchas', 'long lead', 'long-lead', 'supply', 'delivery', 'deliver',
            'fabricat', 'manufactur', 'material')


def _find_disc(F, keywords):
    """The first discipline whose name contains a keyword, testing keywords in priority order
    (so 'procure' wins over 'material'). None when the file carries no such category."""
    ds = F.get('disciplines') or []
    for kw in keywords:
        for d in ds:
            if kw in (d.get('name') or '').lower():
                return d
    return None


def _eng_disc(F):
    return _find_disc(F, _ENG_KW)


def _proc_disc(F):
    return _find_disc(F, _PROC_KW)


def _implied_spi(d):
    """A category's own schedule ratio, re-derived as actual/planned (the same %-driven basis the
    tool uses for the headline SPI). None when it can't be formed."""
    if not d:
        return None
    try:
        p = float(d.get('planned'))
        a = float(d.get('actual'))
    except (TypeError, ValueError):
        return None
    return (a / p) if p > 0 else None


def _state(d):
    g = (d.get('gap') or 0) if d else 0
    return 'behind plan' if g > 2 else ('ahead of plan' if g < -2 else 'essentially on plan')


def _disc_read(d, weighted=True):
    """A grounded one-line read of a discipline: done vs planned, weight, state, implied ratio."""
    if not d:
        return ''
    w = d.get('weight')
    wtxt = f" (~{round((w or 0) * 100)}% of the project by weight)" if (weighted and w is not None) else ''
    isp = _implied_spi(d)
    itxt = f", an implied schedule ratio of about **{K.ratio(isp)}**" if isp is not None else ''
    return (f"**{d.get('name')}** is at **{K.pct(d.get('actual'))}** done against "
            f"**{K.pct(d.get('planned'))}** planned{wtxt} — {_state(d)}{itxt}.")


def _kpi(F, module, key):
    a = (F.get('audit') or {}).get(module) or {}
    return (a.get('kpis') or {}).get(key)


def _grade(F, module):
    a = (F.get('audit') or {}).get(module) or {}
    return a.get('grade')


def _logic_bits(F):
    """The structural logic-quality flags that distort a procure→deliver→install read. '' if clean."""
    bits = []
    oos = F.get('oos_count')
    if oos:
        crit = F.get('critical_oos')
        bits.append(f"**{oos} out-of-sequence activities**" + (f" ({crit} on the critical path)" if crit else ""))
    if F.get('open_ends'):
        bits.append(f"**{F.get('open_ends')} open ends**")
    if F.get('dangling_count'):
        bits.append(f"**{F.get('dangling_count')} dangling logic links** ({K.pct(F.get('dangling_pct'))})")
    if not bits:
        return ''
    if len(bits) == 1:
        return bits[0]
    return ", ".join(bits[:-1]) + " and " + bits[-1]


def _upstream_verdict(F):
    """One honest sentence on whether the upstream office/supply chain is the headline, from the
    weighted driver and (when present) the design/procurement categories' own gaps."""
    eng, proc = _eng_disc(F), _proc_disc(F)
    driver = K.main_driver(F)
    dn = driver.get('name') if driver else None
    up_is_driver = bool(driver and dn in {(eng or {}).get('name'), (proc or {}).get('name')})
    if up_is_driver:
        return (f"On this file the weighted driver actually **is** an upstream category (**{dn}**), so the "
                "'it's the field' reflex doesn't hold here — chase it upstream.")
    if eng or proc:
        near = []
        if eng:
            near.append(f"design at {_state(eng)}")
        if proc:
            near.append(f"procurement at {_state(proc)}")
        return ("The upstream categories in this file (" + "; ".join(near) + ") are not the weighted driver — "
                f"that's **{dn or 'the field work front'}** — so the headline problem is downstream of the "
                "office, not in it.")
    return ("I can't see a discrete design or procurement branch in this file's category split, so I can't "
            "isolate their numbers here — the weighted driver of the shortfall is "
            f"**{dn or 'the field work front'}**, which is where the finish is being lost.")


# ── answers ─────────────────────────────────────────────────────────────────────

def t12q00(F, role):
    """Isolate the design category's SPI and % complete, separate from construction."""
    if not F.get('ok'):
        return _no_project(F)
    eng = _eng_disc(F)
    _, pace = K.spi_verdict(F)
    head = ("**Split it out — don't let the design office wear the field's delay.** The headline SPI is a "
            "weighted blend of every front; read engineering on its own and the story changes.")
    body = [
        (f"Overall the job is SPI ≈ **{K.ratio(F.get('spi'))}** with **{K.pct(F.get('actual_pct'))}** actual "
         f"against **{K.pct(F.get('planned_pct'))}** planned — {pace}. That single number is not engineering's "
         "number; it's dominated by whichever front carries the most weight."),
        (("Isolated, " + _disc_read(eng) + " That's the design office read the client should see, not the "
          "blended headline.")
         if eng else
         "This file's category split doesn't expose a discrete design/engineering branch, so I can't recite "
         "its isolated SPI from the numbers I hold. Filter **EVM / Update Analysis** to your design WBS and "
         "you'll get its own Schedule% and Performance% — read that, not the aggregate."),
        _upstream_verdict(F),
        ("One honesty note on the isolated figure: a category's own schedule ratio here is re-derived as its "
         "actual ÷ planned on the same %-complete basis the tool uses for the headline SPI — it matches P6's "
         "read of that branch, but for the exact filtered EVM number open the category in the EVM tab."),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append("For contrast, where the delay actually lives: " + dl)
    advice = [
        "Report engineering's SPI and % complete as their own line in the weekly, separate from the field — "
        "so the client reads the real cause, not an averaged one.",
        ("For the planner: filter the EVM category roll-up to the design branch and quote its Schedule% vs "
         "Performance%; don't let a 95%-weight field front set the design office's headline."
         if role == 'planning' else
         "Say plainly in the report whether the drawings are on plan — a near-plan design line reassures the "
         "client that the fix is on site, not in the office."),
        K.go_deeper('EVM', 'For the exact filtered design SPI'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Overall SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Overall actual vs planned',
                              f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
                         K.ev('EVM', 'Design category',
                              (f"{K.pct(eng.get('actual'))} vs {K.pct(eng.get('planned'))} planned" if eng else None)),
                         K.ev('EVM', 'Delay to completion', _delay_chip(F))])


def t12q01(F, role):
    """Which discipline is dragging overall SPI — upstream design/procurement or the field?"""
    if not F.get('ok'):
        return _no_project(F)
    driver = K.main_driver(F)
    dn = driver.get('name') if driver else None
    eng, proc = _eng_disc(F), _proc_disc(F)
    up_is_driver = bool(driver and dn in {(eng or {}).get('name'), (proc or {}).get('name')})
    if up_is_driver:
        head = f"**Upstream — it's {dn}.** The weighted driver here is an office/supply front, not the field."
    elif dn:
        head = f"**The field — specifically {dn}.** Design and procurement aren't dragging your SPI; the field is."
    else:
        head = "**The field carries it.** No upstream category stands out as the weighted driver here."
    body = [
        (f"The overall SPI ≈ **{K.ratio(F.get('spi'))}** and the ~"
         f"{abs(round((F.get('planned_pct') or 0) - (F.get('actual_pct') or 0)))}-point gap "
         f"(**{K.pct(F.get('actual_pct'))}** vs **{K.pct(F.get('planned_pct'))}**) don't spread evenly. "
         "The real driver is the largest **weight × gap** front — a big-weight construction front a few "
         "points behind moves the finish far more than a tiny-weight design line miles behind."),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append("Ranked that way: " + dl)
    reads = [r for r in (_disc_read(eng), _disc_read(proc)) if r]
    if reads:
        body.append("Meanwhile the upstream categories sit here — " + " ".join(reads)
                    + " — so they're not what's setting the headline.")
    else:
        body.append("This file doesn't carry discrete design/procurement branches to isolate, so rank the "
                    "per-category SPI in EVM yourself; on the weighted read the office isn't the headline.")
    body.append("This is the same split as the design-isolation question above — I'm just answering it from "
                "the other side: point recovery at the driver, and don't let a 'late drawings' story survive "
                "if the drawings are near plan.")
    advice = [
        (f"Direct recovery at **{dn}**, not upstream — that's the front the finish is tracking."
         if dn else "Rank the per-category SPI weighted by cost/weight, then aim recovery at the top line."),
        ("For the planner: sort categories by weight × gap, not raw gap — a 1%-weight design line with a huge "
         "gap is noise against the governing field front." if role == 'planning' else
         "Tell the client the cause in one name so the conversation stays on the front that matters."),
        K.go_deeper('EVM', 'For the ranked per-category SPI'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('EVM', 'Overall SPI', K.ratio(F.get('spi'))),
                         K.ev('EVM', 'Weighted driver', dn),
                         K.ev('EVM', 'Delay to completion', _delay_chip(F))])


def t12q02(F, role):
    """Planned vs actual for every IFC drawing activity + which engineering deliverables are critical."""
    if not F.get('ok'):
        return _no_project(F)
    eng = _eng_disc(F)
    head = ("**Two lists, cross-referenced.** Pull planned-vs-actual for every IFC package in Update "
            "Analysis, then cross it against the driving path in the Critical Path Analyzer — a late drawing "
            "only matters if it feeds the chain that governs the finish.")
    body = [
        "The per-activity view — every IFC/design package by activity code, planned date and % against "
        "actual — is built in **Update Analysis** (this update measured against the baseline). Filter it to "
        "the design category and you get the late-package list by code. That's where the line-by-line detail "
        "lives; I hold the category-level read, not the individual rows.",
        (("At category level, " + _disc_read(eng) + " so before you chase any single package, that's the "
          "office's overall position.")
         if eng else
         "This file's split doesn't expose a discrete design branch, so filter Update Analysis to your design "
         "WBS to get the isolated planned-vs-actual by package."),
        _upstream_verdict(F) + " So expect **few or no engineering deliverables actually governing "
        "completion** — cross each late package against the Critical Path Analyzer's driving path and judge it "
        "by whether it feeds that chain.",
        (f"The network's own read backs this up where it's present: a driving path of "
         f"**{F.get('driving_path_count')} activities** is what completion is tracking — a late drawing that "
         "feeds high-float work is not on it, and isn't your problem this week."
         if F.get('driving_path_count') else
         "Confirm the driving path in the Critical Path Analyzer first, then only the design packages that "
         "feed it are this week's problem — the rest are feeding float."),
    ]
    advice = [
        "Flag every late IFC package, but triage by one test: does it feed the driving chain? If not, it's "
        "uncomfortable, not governing.",
        ("For the planner: tag each design package with the total float of its first construction successor — "
         "that's the honest priority order, not the drawing's own date." if role == 'planning' else
         "Give the client the short list of drawings that actually touch the critical work, not the full "
         "register — it keeps the pressure where it counts."),
        K.go_deeper('Update Analysis, Critical Path Analyzer'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Update Analysis', 'Late-package list', 'by activity code, filtered to design'),
                         K.ev('CPLI', 'Driving-path activities', F.get('driving_path_count')),
                         K.ev('EVM', 'Design category',
                              (f"{K.pct(eng.get('actual'))} vs {K.pct(eng.get('planned'))} planned" if eng else None)),
                         K.ev('EVM', 'Delay to completion', _delay_chip(F))])


def t12q03(F, role):
    """Is design late enough to threaten construction start, or still inside float?"""
    if not F.get('ok'):
        return _no_project(F)
    eng = _eng_disc(F)
    head = ("**Test it against logic, not gut.** Whether late design bites depends on one thing only — is the "
            "late package on the driving path to first construction, or does it feed work that still has float?")
    body = [
        "Run the late design packages through the **Critical Path Analyzer**. If a package feeds the chain "
        "that's governing completion, any slip on it bites the finish day-for-day. If it feeds work carrying "
        "float, it's uncomfortable but not governing — the construction start it feeds has room to absorb it.",
        _upstream_verdict(F),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append("The finish position confirms where the pressure really is: the job is "
                    + K.delay_phrase(F) + ", and " + dl + " That's execution on a field front, not the "
                    "drawing office — so on current reads engineering isn't sitting on the driving path.")
    else:
        body.append("In date terms the finish is " + K.delay_phrase(F) + " — measure the late design against "
                    "that, not against its own due date.")
    nf = F.get('neg_float_count')
    if nf:
        body.append(f"Watch the pressure gauge: **{nf} activities** ({K.pct(F.get('neg_float_pct'))}) already "
                    "carry negative total float — they're past due to the finish. Any late design feeding one "
                    "of those is already governing, not merely uncomfortable, so check that overlap first.")
    else:
        body.append("The network isn't showing negative float, so most late design is more likely inside "
                    "float than on the driving path — but confirm each package's first successor before you "
                    "relax about it.")
    advice = [
        "Trace each late package to its first construction successor and read that successor's total float — "
        "negative or near-zero = it threatens the start; comfortable = it doesn't.",
        ("For the planner: don't judge a drawing by its own late finish — judge it by the float on the "
         "activity it releases." if role == 'planning' else
         "Tell the team which drawings genuinely hold up a start so effort goes there, not to the whole "
         "register."),
        K.go_deeper('Critical Path Analyzer, Update Analysis'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Float', 'Negative-float activities', nf),
                         K.ev('CPLI', 'Driving-path activities', F.get('driving_path_count')),
                         K.ev('EVM', 'Delay to completion', _delay_chip(F))])


def t12q04(F, role):
    """Which long-lead items are on the critical path — rank by remaining float."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("**Filter to your delivery activities, tag the long-lead items, and sort by total float.** "
            "Anything already in the hole expedites first; positive-float items can wait.")
    body = [
        "The Critical Path Analyzer gives you the total float on every activity; the Schedule Health Review "
        "grades the float distribution. Filter to your procurement/delivery lines, flag the long-lead items, "
        "and rank ascending by total float — negative first, then near-zero. That order is your expediting "
        "queue.",
    ]
    fg = F.get('float_grade')
    if fg or F.get('max_float') is not None:
        body.append(f"The float health here is graded **{fg or '—'}**"
                    + (f", with the widest slack about {K.wd(F.get('max_float'))} and the average around "
                       f"{K.wd(F.get('avg_float'))}" if F.get('max_float') is not None else "")
                    + ". That spread tells you how much room the non-critical deliveries have before they "
                    "start governing.")
    nf = F.get('neg_float_count')
    if nf:
        body.append(f"The ones already in trouble: **{nf} activities** ({K.pct(F.get('neg_float_pct'))}) are "
                    "on negative total float — past due to the finish. Any long-lead delivery among those is "
                    "your top expedite, because it's already eating the completion date, not just at risk of it.")
    dl = K.driver_line(F)
    if dl:
        body.append("Prioritise deliveries feeding the driver: " + dl + " A fabricated-steel, plant or "
                    "equipment delivery feeding that front outranks a delivery feeding floated work every time.")
    oe = F.get('open_ends')
    if oe:
        body.append(f"One integrity check before you trust the ranking: **{oe} open ends** in this schedule. "
                    "A long-lead item floating on a bare date instead of logic-tied to its install will show "
                    "fake float and drop down the list when it shouldn't — verify each delivery is actually "
                    "linked to what it feeds.")
    advice = [
        "Sort long-lead deliveries by total float ascending and expedite top-down; don't spend a premium on a "
        "positive-float item.",
        ("For the planner: confirm each long-lead line is logic-tied to its install (no dangling / open end) "
         "before ranking — an untied item lies about its float." if role == 'planning' else
         "Keep the expediting log ordered by float, not by PO value — the cheapest item can be the one "
         "holding the date."),
        K.go_deeper('Critical Path Analyzer, Schedule Health Review'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Float', 'Grade', fg),
                         K.ev('Float', 'Negative-float activities', nf),
                         K.ev('Open ends', 'Untied count', oe),
                         K.ev('CPLI', 'Driving-path activities', F.get('driving_path_count'))])


def t12q05(F, role):
    """Required-on-site date per long-lead item + F9-exact finish impact of a 30-day delivery slip."""
    if not F.get('ok'):
        return _no_project(F)
    head = ("**Back-calculate the ROS date from the install, then model the slip.** Required-on-site is the "
            "install start less rigging and prep; the 30-day slip's finish impact comes out P6 F9-exact from "
            "the What-if, not as a guess.")
    body = [
        "For each long-lead item, read its install start in the **Critical Path Analyzer** and subtract the "
        "on-site prep/rigging lead — that's the required-on-site date the delivery has to beat. Do it per "
        "item; a single blanket ROS hides which deliveries are genuinely date-critical.",
        "Then drop a 30-day delivery slip into the **What-if engine**. It gives an instant estimate and then "
        "the exact figure via a build → F9 round-trip, so the finish move is P6-accurate, not extrapolated.",
        ("How the slip lands depends entirely on float. For an item feeding the driving front expect close to "
         "day-for-day pain on the finish — the job is already " + K.delay_phrase(F) + ", so there's no "
         "cushion there. For a float-cushioned item the finish may not move at all until the 30 days have "
         "eaten its slack."),
    ]
    nf = F.get('neg_float_count')
    if nf:
        body.append(f"With **{nf} activities** already on negative float, several delivery paths have no slack "
                    "left to give — model those individually, because a 30-day slip on any of them is a "
                    "30-day slip on the finish.")
    body.append("This is the quantified version of the ranking question above: the float sort tells you which "
                "deliveries are critical; the What-if tells you exactly what each one costs the finish if it "
                "slips.")
    advice = [
        "Run each delivery's 30-day slip through the What-if individually — a blanket assumption over-states "
        "the pain on floated items and under-states it on critical ones.",
        ("For the planner: pull the ROS from install-start minus the prep lag in P6, don't eyeball it — the "
         "rigging/offload window is often the bit that gets forgotten." if role == 'planning' else
         "Give procurement a dated required-on-site per item, not a vague 'as soon as possible' — the "
         "schedule sets the deadline, not the vendor."),
        K.go_deeper('Critical Path Analyzer, What-if / scenario engine'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('What-if', 'Method', 'estimate → build → F9 (P6-exact)'),
                         K.ev('Float', 'Negative-float activities', nf),
                         K.ev('EVM', 'Finish now', _delay_chip(F))])


def t12q06(F, role):
    """If I air-freight the long-lead item and cut 20 days, does it pull the finish in?"""
    if not F.get('ok'):
        return _no_project(F)
    head = ("**Only if that item is on the governing path — otherwise you're paying to create float you never "
            "use.** Model the 20-day pull before you authorise the freight.")
    body = [
        "Drop the 20-day delivery pull into the **What-if engine**: instant estimate, then the P6 F9-exact "
        "finish via a build → F9 round-trip. The engine tells you whether the finish actually moves — the "
        "airfreight decision should turn on that number, not on the fact that faster feels better.",
        ("The logic is simple. If the item feeds the chain driving the current slip, pulling its delivery in "
         "can claw days back off the finish. If it feeds work that already carries float, the finish holds and "
         "the 20 days just become extra slack on a path that didn't need it — the premium buys nothing."),
    ]
    dl = K.driver_line(F)
    if dl:
        body.append("So the test is whether the item is on the driver: " + dl + " An airfreight on a delivery "
                    "feeding that front is worth pricing; one feeding a floated front is money for nothing.")
    body.append("This is the mirror of the delivery-slip question: there a slip on a critical item cost the "
                "finish day-for-day; here a pull on that same critical item is what recovers it. Same lever, "
                "opposite sign — and the What-if quantifies both to the day.")
    if F.get('delay_days') is not None:
        body.append("Anchor it to where you stand: the finish is currently " + K.delay_phrase(F)
                    + ", so measure any airfreight gain against that position and confirm it survives the "
                    "next update before you bank it.")
    advice = [
        "Model the 20-day pull in the What-if first; authorise the airfreight only if the finish actually "
        "moves — never on principle.",
        ("For the planner: check the item's successor float before you even model it — a positive-float "
         "successor tells you the freight won't touch the finish without running anything." if role == 'planning'
         else "Put the number in front of the client: 'this airfreight buys N days off the finish' or 'it buys "
              "zero' — that's a clean spend decision."),
        K.go_deeper('What-if / scenario engine'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('What-if', 'Method', 'estimate → build → F9 (P6-exact)'),
                         K.ev('EVM', 'Weighted driver', _driver_name(F)),
                         K.ev('EVM', 'Finish now', _delay_chip(F))])


def t12q07(F, role):
    """Installs scheduled before delivery finishes, and does every major item have a delivery feeding install?"""
    if not F.get('ok'):
        return _no_project(F)
    head = ("**Run the Schedule Audit for out-of-sequence, then check the procure→deliver→install chain in "
            "the Constructability Review.** Two failure modes: an install statused ahead of its delivery, and "
            "an install hanging off a bare date with no delivery feeding it at all.")
    oos = F.get('oos_count')
    body = [
        (f"The audit already flags **{oos} out-of-sequence activities**"
         + (f" ({F.get('critical_oos')} on the critical path)" if F.get('critical_oos') else "")
         + f" ({K.pct(F.get('oos_pct'))}). Read through them and see whether any are **installs progressed "
           "ahead of their material delivery** — that's the classic one, and it flatters your progress: the "
           "install shows earned value the site can't actually have without the material on the ground."
         if oos else
         "The out-of-sequence check comes back clean here, so you're unlikely to have installs statused ahead "
         "of delivery — but eyeball the material-heavy fronts anyway, because a clean audit only proves the "
         "logic order, not that every delivery link exists."),
        ("Then the completeness side: confirm every major item — structural steel, precast, "
         "mechanical and electrical plant — has an actual **delivery activity feeding its install**, not an install linked "
         "straight to a date. A missing delivery link is invisible risk: the install looks ready in the logic "
         "while the material is still on a truck somewhere."),
        _logic_bits_line(F),
        ("The **Constructability Review** is what checks the procure→deliver→install chain per package "
         "against build reality, and where the audit finds a genuine out-of-sequence install it can hand you a "
         "**corrected XER** with the type/logic fix applied — so this isn't just a flag, it's a fix you can "
         "download and re-import."),
    ]
    advice = [
        "Work the out-of-sequence list first for install-before-delivery — those are inflating your % "
        "complete right now.",
        ("For the planner: for each major item confirm a Delivery → Install FS tie exists; an install with no "
         "delivery predecessor is an open end pretending to be ready." if role == 'planning' else
         "Ask the site for one thing per major item — 'is the material here?' — and reconcile it to what the "
         "schedule claims is installed."),
        K.go_deeper('Schedule Audit, Constructability Review'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Out-of-sequence', 'Activities out of order', oos),
                         K.ev('Out-of-sequence', 'On the critical path', F.get('critical_oos')),
                         K.ev('Open ends', 'Untied activities', F.get('open_ends')),
                         K.ev('Dangling', 'One-ended links', F.get('dangling_count'))])


def _logic_bits_line(F):
    """A grounded sentence pointing open-ends/dangling at the 'missing delivery link' symptom."""
    oe = F.get('open_ends')
    dang = F.get('dangling_count')
    parts = []
    if oe:
        parts.append(f"**{oe} open ends** — activities with no predecessor or successor at all")
    if dang:
        parts.append(f"**{dang} dangling links** ({K.pct(F.get('dangling_pct'))}) tied at only one end")
    if parts:
        return ("The logic audit already shows where a delivery link may be missing: " + " and ".join(parts)
                + ". An install with no delivery predecessor lands in exactly that list — start there.")
    return ("The open-end and dangling checks come back clean, so you're unlikely to have an install with a "
            "missing delivery predecessor — but confirm the big-ticket items by eye, since a clean structural "
            "check doesn't prove the delivery is the *right* predecessor.")


def t12q08(F, role):
    """Are lead times real durations or hidden in FS lags, and are delivery dates logic-driven or constrained?"""
    if not F.get('ok'):
        return _no_project(F)
    head = ("**Ask this before you trust a single delivery date.** Lead time buried in a long FS lag is "
            "invisible work, and a delivery pinned by a constraint shows fake float — both hide slip.")
    lagged = _kpi(F, 'lag_lead', 'lagged_count')
    longc = _kpi(F, 'lag_lead', 'long_positive_count')
    if longc is None:
        longc = _kpi(F, 'lag_lead', 'long_count')
    leads = _kpi(F, 'lag_lead', 'leads_count')
    lag_grade = _grade(F, 'lag_lead')
    hardc = _kpi(F, 'hard_constraints', 'hard_count')
    hard_grade = _grade(F, 'hard_constraints')
    body = [
        ("**Lead time hidden as lag.** Run **Schedule Audit** for lags. "
         + (f"It flags **{lagged} lagged relationships**"
            + (f" ({K.pct(_kpi(F, 'lag_lead', 'lagged_pct'))})" if _kpi(F, 'lag_lead', 'lagged_pct') is not None else "")
            + (f", of which **{longc} are long positive lags**" if longc else "")
            + f" — graded **{lag_grade}**. " if (lagged is not None) else "")
         + "A procurement lead time modelled as a long FS lag between PO and install is the problem case: it "
           "can't be progressed, resourced or expedited, and it quietly absorbs slip because nothing reports "
           "against it. Pull each one out as a real **delivery activity** with a duration you can track."),
        ("**Delivery dates faked by constraints.** Run **Schedule Health**/the constraints check. "
         + (f"There are **{hardc} hard constraints** in this schedule (graded **{hard_grade}**). "
            if hardc else
            ("The constraint check is available here — read it before trusting the dates. "
             if F.get('hard_constraints_computable') else
             "Constraint counts aren't computable from this file, so inspect the delivery lines directly. "))
         + "A delivery pinned by a Must-Finish-On or mandatory constraint instead of PO → fabricate → ship "
           "logic shows float it hasn't earned and won't move when the upstream logic says it should — so the "
           "true position is masked."),
        ("Why it matters together: a lead time you can't see plus a date that can't move equals a "
         "procurement chain that looks healthy and reports nothing until the material simply doesn't turn up. "
         "The overall delay reads genuine on this file, but clean the procurement logic so it *stays* honest "
         "as the job progresses."),
    ]
    if leads:
        body.append(f"Side flag while you're in there: **{leads} negative lags (leads)** — a lead pulls a "
                    "successor back before its driver finishes, which on a delivery chain usually means an "
                    "install is allowed to start before the material is really there. Worth scrubbing.")
    advice = [
        "Convert every long procurement FS lag into a real delivery activity with a trackable duration — no "
        "lead time should live inside a lag.",
        ("For the planner: replace mandatory/finish constraints on deliveries with PO → fabricate → ship "
         "logic so the dates float honestly off the network." if role == 'planning' else
         "Insist procurement dates come from logic, not from a typed-in date — a constrained delivery can't "
         "warn you when it's about to be late."),
        K.go_deeper('Schedule Audit, Schedule Health Review'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Schedule Audit', 'Lagged relationships', lagged),
                         K.ev('Schedule Audit', 'Long positive lags', longc),
                         K.ev('Schedule Health', 'Hard constraints', hardc),
                         K.ev('Schedule Audit', 'Lag/lead grade', lag_grade)])


def t12q09(F, role):
    """Delay blamed on late vendor drawings — verify baseline vs update; EOT indicators for late information."""
    if not F.get('ok'):
        return _no_project(F)
    eng = _eng_disc(F)
    head = ("**Don't accept the blame line at face value — test it.** A 'late vendor drawings' narrative only "
            "holds if the late deliverables actually sit on the path that moved the finish.")
    body = [
        "Run the **Consultant Review** — the forensic, but-for read of a progressed schedule. It measures "
        "baseline against update and tells you whether removing the late-drawing delay actually pulls the "
        "finish back, or whether the finish moved for another reason entirely. That's the difference between "
        "a defensible position and an assertion.",
        _upstream_verdict(F) + " So on this schedule a 'late drawings' story may not survive the but-for test "
        "— the finish is being lost on the field front, and blaming the office won't stand up when the "
        "logic is examined.",
        (("The design category's own read supports the caution: " + _disc_read(eng) + " If the drawings are "
          "near plan, they can't be the thing that moved a finish this far.") if eng else
         "This file doesn't isolate a design branch, so confirm the drawings' actual position in EVM before "
         "anyone signs off on a late-information narrative."),
        ("If the deliverables **do** turn out to drive the finish, the **Claims / TIA reference** surfaces "
         "the late-information EOT indicators and the delay-method reference (AACE / FIDIC). One firm caveat: "
         "those are **indicators, not an entitlement** — the tool's forward-pass read can draft and point, it "
         "can't prove critical-path causation to a contractual standard. Either way you hand the client "
         "evidence, not opinion."),
    ]
    body.append("Honesty on scope: a proper but-for needs the baseline and the progressed update as a matched "
                "pair. If only this snapshot is loaded, run the Consultant Review with the baseline alongside "
                "it — I won't call causation off a single snapshot.")
    advice = [
        "Run the but-for before you concede or assert anything — let the logic say whether late drawings moved "
        "the finish.",
        ("For the planner: isolate the late-information fragnet and re-run — if the finish doesn't recover "
         "when you remove it, the drawings aren't the driver." if role == 'planning' else
         "Take the but-for result to the client, not the field's opinion — 'the schedule shows the delay is "
         "here' ends the argument faster."),
        K.go_deeper('Consultant Review, Claims / TIA reference'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Consultant Review', 'Method', 'baseline-vs-update but-for'),
                         K.ev('EVM', 'Weighted driver', _driver_name(F)),
                         K.ev('EVM', 'Design category',
                              (f"{K.pct(eng.get('actual'))} vs {K.pct(eng.get('planned'))} planned" if eng else None)),
                         K.ev('EVM', 'Delay to completion', _delay_chip(F))])


def t12q10(F, role):
    """Completed engineering not flowing into procurement — stalled handoff; chain vs KB sequence."""
    if not F.get('ok'):
        return _no_project(F)
    eng, proc = _eng_disc(F), _proc_disc(F)
    head = ("**Look for design marked complete whose downstream procurement hasn't started — that's your "
            "stalled handoff.** Then check each package's full chain against the Knowledge Base sequence: "
            "design → procure → fabricate → deliver → install.")
    body = [
        "Use **Update Analysis** to find design packages statused complete whose next step — the PO, the "
        "procurement activity — still hasn't started. A completed drawing that isn't triggering its purchase "
        "is float you're quietly burning: the office did its bit and the baton is sitting on the ground.",
        ("Then run each package's chain against the **Construction Knowledge Base** reference sequence and "
         "flag any broken link — a design with no procurement successor, a procurement with no fabricate/"
         "deliver step, a delivery with no install. Those are the handoffs that fail silently."),
        _logic_bits_line(F),
    ]
    reads = [r for r in (_disc_read(eng), _disc_read(proc)) if r]
    if reads:
        body.append("On this file the upstream categories read: " + " ".join(reads) + " — broadly on track, "
                    "so expect **few stalls**. But even one completed drawing not releasing its PO is worth "
                    "chasing, because that delay compounds all the way down to the install at the field front.")
    else:
        body.append("This file doesn't isolate design/procurement branches, so filter Update Analysis to "
                    "those WBS paths to spot the stalls; where engineering is broadly on track the stalls are "
                    "few, but each one delays everything downstream of it.")
    advice = [
        "For every completed design package, confirm its PO/procurement successor has actually started — an "
        "idle handoff is recoverable now and expensive later.",
        ("For the planner: the stalled handoff usually shows as a completed activity with an unstarted "
         "successor and slack still positive — catch it before that slack turns critical." if role == 'planning'
         else "Chase the handoffs at the weekly — 'drawing done, PO not raised' is the cheapest delay you'll "
              "ever fix."),
        K.go_deeper('Update Analysis, Construction Knowledge Base'),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Open ends', 'Broken-chain candidates', F.get('open_ends')),
                         K.ev('EVM', 'Design category',
                              (f"{K.pct(eng.get('actual'))} vs {K.pct(eng.get('planned'))} planned" if eng else None)),
                         K.ev('EVM', 'Procurement category',
                              (f"{K.pct(proc.get('actual'))} vs {K.pct(proc.get('planned'))} planned" if proc else None)),
                         K.ev('EVM', 'Delay to completion', _delay_chip(F))])


def t12q11(F, role):
    """GAP — submittal register / PO-expediting log ingest, and missing procurement/submittal activities."""
    if not F.get('ok'):
        return _no_project(F)
    grounds = ('GAP — reads P6 activities, not submittal/PO systems; missing-activity is construction-only')
    head = ("**I can't ground this one honestly — and I'd rather say so than fake it.** The tool reads your "
            "P6 activities, not your submittal register or PO/expediting log.")
    body = [
        K.gap_note(grounds),
        "Two hard limits, both deliberate. First, there's **no ingest** for a submittal register or a "
        "PO/expediting log — those live in your document-control and procurement systems, and the tool has no "
        "way to read them, so I can't report submittal or PO status against them. Second, missing-activity "
        "detection is **construction/execution-only by design** — it flags absent site steps like cure times "
        "and commissioning, and it deliberately won't invent absent procurement or submittal activities, "
        "because guessing upstream would just be noise.",
        "To do this properly the tool would need a submittal/PO-log import mapped onto schedule activities — "
        "each submittal and PO tied to the activity it feeds — so it could reconcile register status against "
        "the logic and flag a PO with no matching schedule line. That's a real feature, not a today answer.",
        "For now, keep the submittal register and expediting log where they belong — in document control and "
        "procurement — and tie the **key PO and delivery milestones into P6 by hand**, so at least the "
        "date-critical items live inside the logic and show up on the driving-path and float reads the rest of "
        "this theme runs on.",
    ]
    advice = [
        "Manually add the date-critical PO/delivery milestones to the schedule and logic-tie them to their "
        "installs — that's the one place the tool can then help.",
        ("For the planner: model the long-lead items as delivery activities (not lags) so the register's "
         "critical items at least get float and driving-path visibility." if role == 'planning' else
         "Run the submittal/PO tracking in your procurement system and reconcile the milestones into P6 "
         "weekly — the schedule shouldn't try to be your register."),
    ]
    return K.A(head, body, advice=advice,
               evidence=[K.ev('Scope', 'Submittal / PO ingest', 'not supported — no external-log import'),
                         K.ev('Scope', 'Missing-activity check', 'construction/execution only, by design'),
                         K.ev('Schedule', 'Activities read', F.get('activity_count'))])


ANSWERS = {
    't12q00': t12q00, 't12q01': t12q01, 't12q02': t12q02, 't12q03': t12q03,
    't12q04': t12q04, 't12q05': t12q05, 't12q06': t12q06, 't12q07': t12q07,
    't12q08': t12q08, 't12q09': t12q09, 't12q10': t12q10, 't12q11': t12q11,
}
