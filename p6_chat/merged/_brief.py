"""The short, plain answer that opens each of the 15 chat answers (owner comment 14).

The planner's rule: every answer must be simple, clear and easy to understand — put a hand on
the problem and give advice. So each answer now OPENS with a brief of four parts, in plain words,
and the long analysis sits underneath for whoever wants it:

    {'problem': str,        # what is wrong, in one or two short sentences
     'where':   [str],      # where exactly: the activity (name + ID), the area, the dates, the numbers
     'why':     [str],      # what the file shows as the reason
     'do':      [str]}      # what to do first — at most four concrete steps

Writing rules (binding — tests enforce the measurable ones):
  * Short sentences. No planner shorthand: write "working days", "the critical path", "total float"
    — never "wd", "chain", "trunk", "ladder", "tells", "bipolar".
  * Name the thing: activity name AND ID, its area, its planned and forecast dates.
  * Every number comes from F (the stored results) or N (the schedule file re-read). Nothing is
    invented; when the file cannot show something, say so and name the tool that can.
  * An action says WHAT to do and to WHICH activity — not "aim recovery at the chain".
"""
import re

from p6_chat.qa import _kit as K

MAX_WHERE, MAX_WHY, MAX_DO = 4, 3, 4

# ── small helpers ───────────────────────────────────────────────────────────────


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _days(n):
    n = abs(int(round(_num(n) or 0)))
    return f"{n:,} working day{'' if n == 1 else 's'}"


def _act(x):
    """'Drilling For Piles (CONS.PL.S9.1000)'"""
    name, aid = (x.get('name') or '').strip(), (x.get('id') or '').strip()
    return f"**{name}** ({aid})" if name and aid else (f"**{name}**" if name else aid)


def _area(x, depth=2):
    """The last WBS levels of an activity, read naturally: 'Phase C, Silo 9'."""
    parts = [p.strip() for p in (x.get('wbs') or '').split(' / ') if p.strip()]
    return ', '.join(parts[-depth:]) if parts else ''


def _money(v):
    v = _num(v)
    if v is None:
        return ''
    a = abs(v)
    if a >= 1e6:
        return f"{a / 1e6:,.1f} million"
    if a >= 1e3:
        return f"{a / 1e3:,.0f} thousand"
    return f"{a:,.0f}"


def _nok(N):
    return bool(N and N.get('ok'))


def _chain(N):
    return (N.get('chain') or []) if _nok(N) else []


def _fronts(chain, limit=3):
    """The areas the critical path runs through, in order, with how many activities in each."""
    out = []
    for x in chain:
        a = _area(x) or 'no WBS'
        hit = next((o for o in out if o[0] == a), None)
        if hit:
            hit[1] += 1
        else:
            out.append([a, 1])
    if len(out) > limit:                       # many areas: name the ones holding most of the path
        out.sort(key=lambda o: -o[1])
    return out[:limit], max(0, len(out) - limit)


def plain(text):
    """Planner shorthand → plain words (used on any sentence taken from the long analysis)."""
    t = str(text or '')
    for pat, rep in (
            (r'(?<=\d)\s?wd\b', ' working days'), (r'\bwd\b', 'working days'),
            (r'\bsingle chain\b', 'single line of activities'),
            (r'\bfinish chain\b', 'critical path'), (r'\bdriving chain\b', 'critical path'),
            (r'\bdriving path\b', 'critical path'), (r'\bthe chain\b', 'the critical path'),
            (r'(?<!supply )\bchain\b', 'critical path'), (r'\btrunk\b', 'main sequence'),
            (r'\bdanglers\b', 'activities with a missing link'), (r'\bTIA\b', 'time impact analysis'),
            (r'\bEOT\b', 'extension of time')):
        # the words are matched in any case ("Driving path" in a heading); the replacement keeps a
        # leading capital. The abbreviations (wd / TIA / EOT) are matched as written.
        if pat.isupper() or 'wd' in pat or 'TIA' in pat or 'EOT' in pat:
            t = re.sub(pat, rep, t)
        else:
            t = re.sub(pat, lambda m, r=rep: (r[0].upper() + r[1:]) if m.group(0)[0].isupper() else r, t, flags=re.I)
    return t


# ── the facts, said plainly ─────────────────────────────────────────────────────

def f_finish(F, N):
    """Where the finish date stands."""
    d = _num(F.get('delay_days'))
    fm = ((N or {}).get('finish_milestone') or {}) if _nok(N) else {}
    ms = fm.get('name')
    name = f"the finish milestone, {ms}," if ms else 'the project finish'
    bf, ff = _dates(F, N)
    if d is None:
        return "The finish date cannot be read from this file (no finish milestone was found)."
    if d > 0:
        s = f"{name[0].upper() + name[1:]} is forecast for **{ff}**" if ff else f"{name[0].upper() + name[1:]} is late"
        return s + (f". The baseline date was {bf}." if bf else '.') + f" That is **{_days(d)} late** (about {K.weeks(d)})."
    if d < 0:
        return f"{name[0].upper() + name[1:]} is forecast for {ff}, {_days(d)} EARLIER than the baseline date of {bf}."
    return f"{name[0].upper() + name[1:]} is forecast for {ff}, on its baseline date."


def _dates(F, N):
    """(baseline finish, forecast finish) — the finish milestone's own dates when the schedule file
    was re-read (the same dates the long analysis quotes), else the stored ones."""
    fm = ((N or {}).get('finish_milestone') or {}) if _nok(N) else {}
    return (fm.get('baseline_finish') or F.get('baseline_finish'), fm.get('finish') or F.get('forecast_finish'))


def f_progress(F):
    a, p = F.get('actual_pct'), F.get('planned_pct')
    if a is None or p is None:
        return ''
    return f"**{K.pct(a)}** of the work is done. The plan was {K.pct(p)} by the data date ({F.get('data_date')})."


def f_head(N):
    """The first activity on the critical path — where the delay starts."""
    ch = _chain(N)
    if not ch:
        return ''
    h = ch[0]
    state = 'has not started' if not h.get('pct') else f"is {h['pct']}% done"
    s = f"The critical path starts at {_act(h)}" + (f", in {_area(h)}" if _area(h) else '') + '.'
    if h.get('baseline_finish'):
        s += f" It was planned to finish on {h['baseline_finish']}. It {state} and is now forecast to finish on {h.get('finish')}."
    else:
        s += f" It {state}."
    return s


def f_path(N):
    ch = _chain(N)
    if not ch:
        return ''
    n = N.get('chain_count') or len(ch)
    ns = sum(1 for x in ch if not x.get('pct'))
    fr, more = _fronts(ch)
    started = ('None of them has started.' if ns == len(ch) else 'All of them have started.' if ns == 0
               else f"{ns} of them have not started.")
    s = f"**{n} activities** decide the finish date (the critical path). {started}"
    if fr:
        s += ' They are in: ' + '; '.join(f"{a} ({c})" for a, c in fr) + (f"; and {more} more area{'s' if more != 1 else ''}" if more else '') + '.'
    return s


def f_driver(F):
    d = K.main_driver(F)
    if not d:
        return ''
    return (f"**{d['name']}** is {round((_num(d.get('weight')) or 0) * 100)}% of the project. "
            f"It is {d.get('actual')}% done against {d.get('planned')}% planned.")


def f_inputs(N):
    """Items the client / employer owes that are late and still open."""
    if not _nok(N):
        return ''
    lo = N.get('client_inputs_late_open') or []
    if not lo:
        return ''
    worst = max(lo, key=lambda x: _num(x.get('slip_wd')) or 0)
    return (f"**{len(lo)} item{'s' if len(lo) != 1 else ''} the client must provide** "
            f"{'are' if len(lo) != 1 else 'is'} late and still open. The latest is {_act(worst)}: "
            f"due {worst.get('baseline_finish')}, now {_days(worst.get('slip_wd'))} late.")


def f_late_milestones(N, limit=3):
    if not _nok(N):
        return []
    ms = sorted([m for m in (N.get('milestones_open_late') or []) if (_num(m.get('slip_wd')) or 0) > 0],
                key=lambda m: (0 if m.get('type') == 'FinishMilestone' else 1, -(_num(m.get('slip_wd')) or 0)))
    return [f"{_act(m)}: planned {m.get('baseline_finish')}, now {m.get('finish')} — {_days(m.get('slip_wd'))} late."
            for m in ms[:limit]]


def f_no_file(N):
    if _nok(N):
        return ''
    return ("I could not re-read the schedule file, so I cannot name the activities. Import the file again and "
            "ask once more.")


# ── the advice, said plainly ────────────────────────────────────────────────────

def a_start_head(N):
    ch = _chain(N)
    if not ch:
        return ''
    h = ch[0]
    if not h.get('pct'):
        return (f"Start {_act(h)} now. Ask the team responsible why it has not started and get a firm start date. "
                "Each day it waits adds a day to the finish.")
    return (f"Finish {_act(h)} ({h['pct']}% done). Ask the team responsible what is holding it and agree a finish date. "
            "Each day it runs over adds a day to the finish.")


def a_inputs(N):
    if not _nok(N):
        return ''
    lo = N.get('client_inputs_late_open') or []
    if not lo:
        return ''
    first = max(lo, key=lambda x: _num(x.get('slip_wd')) or 0)
    rest = len(lo) - 1
    return (f"Write to the client today about {_act(first)}" + (f" and the other {rest} late item{'s' if rest != 1 else ''}" if rest else '')
            + ". Give the date each was due and keep the letter on file — you will need it for an extension of time.")


def a_compare(F):
    if F.get('has_history'):
        return ''
    return ("Load your previous update and open **Update vs Update**. It shows whether the delay is growing or "
            "shrinking, and which activities lost time this period.")


def a_whatif(N):
    ch = _chain(N)
    if not ch:
        return ''
    fr, _ = _fronts(ch, 99)
    area = max(fr, key=lambda x: x[1])[0] if fr else 'the critical path'
    return (f"Test one change at a time in the **What-if** tool — a second crew or an extra working day on {area}. "
            "Keep only the days P6 confirms when you reschedule (F9).")


def _keep(items, n):
    out = []
    for s in items:
        s = (s or '').strip()
        if s and s not in out:
            out.append(s)
    return out[:n]


def _mk(problem, where=(), why=(), do=()):
    return {'problem': (problem or '').strip(), 'where': _keep(where, MAX_WHERE),
            'why': _keep(why, MAX_WHY), 'do': _keep(do, MAX_DO)}


def _why_default(F, N):
    """What the file shows as the reason for a delay — never more than it can prove."""
    out = []
    ch = _chain(N)
    if ch and not ch[0].get('pct'):
        out.append(f"The first critical activity, {_act(ch[0])}, has not started. Everything after it waits.")
    if f_inputs(N):
        out.append("The client's late items hold work that cannot start without them.")
    elif _nok(N):
        out.append("No late client item is in the file, so the delay reads as our own execution. Confirm this on site.")
    out.append("The file cannot split the delay between the client and the contractor. **Consultant Review** does that.")
    return out


def _behind(F):
    return (_num(F.get('delay_days')) or 0) > 0


def _on_time_brief(F, N, topic):
    d = _num(F.get('delay_days'))
    if d is None:
        return None
    if d < 0:
        return _mk(f"The project is ahead: the finish is {_days(d)} earlier than the baseline. {topic}",
                   [f_finish(F, N), f_progress(F), f_path(N)], [],
                   ["Keep the critical activities on their dates — the time in hand is lost as soon as one slips.",
                    a_compare(F)])
    if d == 0:
        return _mk(f"The project is on its baseline finish date. {topic}", [f_finish(F, N), f_progress(F), f_path(N)], [],
                   ["Watch the critical activities each update — there is no time in hand.", a_compare(F)])
    return None


# ── one brief per question ──────────────────────────────────────────────────────

def b01(a, F, N):          # where do we stand
    d = _num(F.get('delay_days'))
    if d is None:
        return _mk(f"I can measure progress but not the finish date. {f_progress(F)}", [f_driver(F)], [],
                   ["Add a finish milestone to the schedule in P6 and export it again."])
    if d <= 0:
        return _on_time_brief(F, N, f_progress(F))
    cost = ("Do not report the cost as on budget. This file has no real actual cost, so its CPI of 1.00 means nothing."
            if F.get('cost_derived') else '')
    return _mk(f"The project is **{_days(d)} late**. {f_progress(F)}",
               [f_finish(F, N), f_driver(F), f_head(N) or f_no_file(N)],
               _why_default(F, N),
               [a_start_head(N), a_inputs(N), cost, a_compare(F)])


def b02(a, F, N):          # when will we finish
    d = _num(F.get('delay_days'))
    if d is not None and d <= 0:
        return _on_time_brief(F, N, '')
    late = (N.get('milestones_open_late') or []) if _nok(N) else []
    allm = [m for m in ((N.get('milestones') or []) if _nok(N) else []) if not m.get('done')]
    extra = f" {len(late)} of the {len(allm)} open milestones are late." if late and allm else ''
    return _mk(f"{f_finish(F, N)}{extra}",
               f_late_milestones(N) or [f_no_file(N)],
               [f_head(N)] + _why_default(F, N)[1:2],
               [a_start_head(N), a_inputs(N),
                "For each late milestone, agree a new date with the site and enter it in P6, so the forecast is one you can defend.",
                a_compare(F)])


def b03(a, F, N):          # is the delay real
    d = _num(F.get('delay_days'))
    if d is not None and d <= 0:
        return _on_time_brief(F, N, 'There is no delay to explain.')
    fin = ((N or {}).get('finish_milestone') or {}) if _nok(N) else {}
    agree = (" Its total float in P6 is the same number, so the delay is real and not a calendar effect."
             if fin and _num(fin.get('tf')) is not None and d is not None and abs(abs(_num(fin['tf'])) - d) <= 1 else '')
    return _mk(f"Yes, the delay is real: **{_days(d)}** on the finish date.{agree}",
               [f_finish(F, N), f_head(N) or f_no_file(N), f_inputs(N)],
               _why_default(F, N),
               [(f"Find out why {_act(_chain(N)[0])} has not started — a client hold, or our own crews and equipment. "
                 "Write the answer down: it decides who owns the delay.") if _chain(N) and not _chain(N)[0].get('pct') else a_start_head(N),
                a_inputs(N),
                ("Open **Consultant Review** and enter the client's late items as delay events. It shows how many days each one cost."
                 if f_inputs(N) else
                 "If a client action held this work — a late drawing, access or approval — find the letter and its date. "
                 "Without one, the delay is the contractor's."),
                a_compare(F)])


def b04(a, F, N):          # critical path & float
    ch = _chain(N)
    if not ch:
        return _mk("I cannot trace the critical path without the schedule file.", [f_no_file(N)],
                   [], ["Import the file again, then ask this question again."])
    tail = ch[-1]
    tf = abs(int(round(_num(N.get('finish_tf')) or 0)))
    neg = F.get('neg_float_count')
    return _mk((f"One critical path decides the finish date. Its {N.get('chain_count') or len(ch)} activities are all about "
                f"**{_days(tf)} behind**." if tf else
                f"One critical path of {N.get('chain_count') or len(ch)} activities decides the finish date."),
               [f"It runs from {_act(ch[0])} to {_act(tail)}.", f_path(N).split('(the critical path). ', 1)[-1],
                (f"**{neg:,} activities** ({K.pct(F.get('neg_float_pct'), 1)}) have negative total float — they are behind their latest allowed dates."
                 if neg else ''),
                (f"{F.get('float_above'):,} activities have more than {F.get('float_threshold')} days of total float. Check they have a successor."
                 if F.get('float_above') else '')],
               [f_head(N), "Work that is not on this path can be finished early and the finish date still will not move."],
               [a_start_head(N), a_whatif(N),
                (f"Close the {F.get('dangling_count')} activities with a missing link (Schedule Health ▸ Dangling). Until then some float figures are not reliable."
                 if F.get('dangling_count') else '')])


def b05(a, F, N):          # recover the delay
    d = _num(F.get('delay_days'))
    if d is not None and d <= 0:
        return _on_time_brief(F, N, 'There is no delay to recover.')
    ch = _chain(N)
    return _mk(f"To recover the **{_days(d)}** you must shorten the critical path. Speeding up other work does not move the finish date.",
               [f_path(N) or f_no_file(N), f_head(N), f_inputs(N)],
               ["Only the critical path sets the finish. A day saved on it is a day saved on the finish — until another path becomes critical.",
                "The client's late items must be closed as well, or their paths become the new critical path." if f_inputs(N) else ''],
               [a_start_head(N), a_whatif(N), a_inputs(N), a_compare(F)])


def b06(a, F, N):          # schedule health
    issues, where = [], []
    co, dg = F.get('critical_oos') or 0, F.get('dangling_count') or 0
    lag = ((F.get('audit') or {}).get('lag_lead') or {}).get('kpis') or {}
    long_lags, crit_lags = lag.get('need_justification_count') or 0, lag.get('critical_count') or 0
    neg = F.get('neg_float_count') or 0
    if co:
        issues.append(f"{co} critical out-of-sequence")
        where.append(f"**{co} activities on the critical path** were progressed out of sequence — work started before its predecessor finished.")
    if dg:
        issues.append(f"{dg} missing links")
        where.append(f"**{dg} activities** have a missing predecessor or successor link ({K.pct(F.get('dangling_pct'), 1)} of the schedule).")
    if long_lags:
        issues.append(f"{long_lags} long lags")
        where.append(f"**{long_lags} lags** are longer than {lag.get('long_threshold_days') or 14} days with no written reason"
                     + (f"; {crit_lags} lags are on the critical path." if crit_lags else '.'))
    if neg:
        where.append(f"{neg:,} activities ({K.pct(F.get('neg_float_pct'), 1)}) have negative total float. "
                     + ("This is the real delay showing, not a logic mistake." if _behind(F) else "Check for a constraint date forcing them."))
    oe = F.get('open_ends') or 0
    good = "Every activity has a predecessor and a successor." if not oe else f"{oe} activities have no predecessor or no successor."
    if not issues:
        return _mk("The schedule logic is sound: no missing links, no critical out-of-sequence work and no unexplained long lags.",
                   [good] + where, [], ["Keep running Schedule Health after each update."])
    return _mk(f"The schedule can be used, but fix {len(issues)} thing{'s' if len(issues) != 1 else ''} before you send it out: "
               + ', '.join(issues) + '.',
               where + [good],
               ["These are logic and statusing problems. They make dates and float less reliable, and a consultant will reject the schedule for them."],
               [(f"Fix the {co} critical out-of-sequence activities first: open **Out of Sequence**, use **Resolve & Correct**, then download the corrected file."
                 if co else ''),
                (f"Close the {dg} missing links: **Schedule Health ▸ Dangling ▸ Resolve & Correct**." if dg else ''),
                (f"Write a reason for each of the {long_lags} long lags in the **Lag Report**. Where a lag hides real work, replace it with an activity."
                 if long_lags else ''),
                "Re-import the corrected file and run Schedule Health again."])


def b07(a, F, N):          # what changed
    d = _num(F.get('delay_days'))
    bf, ff = _dates(F, N)
    moved = (f"Against the baseline, the finish has moved from {bf} to {ff} — **{_days(d)} later**."
             if d and d > 0 and bf and ff else f_finish(F, N))
    return _mk(f"{moved} One file cannot show what was changed between two revisions; that needs both files side by side.",
               [f_head(N) or f_no_file(N)] + f_late_milestones(N, 2),
               ["This file holds one baseline and one update. It shows how far dates moved, not who changed durations, links or calendars."],
               ["To see what changed between two **baselines**: open **Baseline Revision** and load both revisions.",
                "To see what changed between two **updates**: open **Update vs Update** and load the previous update.",
                a_start_head(N)])


def b08(a, F, N):          # cost & EVM
    pv, ev = _num(F.get('pv')), _num(F.get('ev'))
    if not pv or ev is None:
        return _mk("The schedule has no cost loaded, so I cannot measure earned value in money.", [f_progress(F)], [],
                   ["Load budgeted cost on the activities in P6 and export again, or enter the weights in Project Setup."])
    gap = pv - ev
    grp = next((g for g in ((F.get('value_gap') or {}).get('groups') or []) if (_num(g.get('gap')) or 0) > 0), None)
    spi = F.get('spi')
    if abs(gap) < 0.005 * pv:
        gap = 0
        prob = f"The value of the work done matches the plan at the data date (done {_money(ev)}, planned {_money(pv)})."
    elif gap > 0:
        prob = (f"Work worth **{_money(gap)}** that was planned by the data date is not done yet "
                f"(done {_money(ev)}, planned {_money(pv)}).")
    else:
        prob = f"The work done is worth {_money(-gap)} MORE than planned by the data date (done {_money(ev)}, planned {_money(pv)})."
    cpi = _num(F.get('cpi'))
    if F.get('cost_derived'):
        why = ["The file has no real actual cost: actual cost equals earned value. So CPI is 1.00 by itself and says nothing about the budget."]
        do1 = "Report the money as 'behind plan in value'. Do not say 'on budget' until real actual cost is entered."
        do2 = "Enter the real actual cost — in P6, or in **Earned Value ▸ Project Setup** — to get a true CPI."
    else:
        word = 'over' if (cpi or 1) < 0.98 else ('under' if (cpi or 1) > 1.02 else 'on')
        why = [f"CPI is {K.ratio(cpi)}: the work done has cost {'more' if word == 'over' else 'less' if word == 'under' else 'about what'} "
               f"{'than' if word != 'on' else ''} its budget{'' if word != 'on' else ' allowed'}."]
        do1 = f"Report cost as running {word} budget (CPI {K.ratio(cpi)}), and the schedule as SPI {K.ratio(spi)}."
        do2 = "Check that the actual cost in P6 is complete up to the data date before you forecast the final cost."
    return _mk(prob,
               [f"SPI is {K.ratio(spi)}: for every 1.00 of work planned, {K.ratio(spi)} was done.",
                (f"**{grp['code']}** holds {K.pct(grp.get('pct_of_gap'), 0)} of the work that is behind ({_money(grp.get('gap'))})."
                 if grp and gap > 0 else ''),
                f_driver(F)],
               why, [do1, do2, a_start_head(N) if gap > 0 else ''])


def b09(a, F, N):          # manpower & resources
    d = _num(F.get('delay_days'))
    ch = _chain(N)
    if d is not None and d <= 0:
        return _mk("There is no delay to explain. Whether the manpower in the plan is realistic cannot be judged from the "
                   "dates alone — it needs labour loaded on the activities.",
                   [f_finish(F, N), f_path(N) or f_no_file(N)],
                   ["A schedule without labour on its activities shows when work happens, not how many people it needs."],
                   ["Load labour (trades and hours) on the activities in P6, then export again.",
                    "Use **Productivity & Resources** to turn quantities into man-hours and crew sizes.",
                    "Open **Baseline Narrative** for the resource loading and the peak manpower the schedule implies."])
    return _mk("This file cannot show whether manpower is the cause: the delay is on activities that have not started, "
               "and the schedule does not carry enough labour data to compare crews planned with crews on site.",
               [f_path(N) or f_no_file(N), f_head(N)],
               ["An activity that has not started is late because of something before it — access, drawings, materials, a client hold or no crew. "
                "The file does not record which.",
                "Adding crews helps only if a shortage of crews is the reason."],
               [(f"Ask the team responsible one question: why has {_act(ch[0])} not started — no crew and equipment, or no access and inputs? Get the answer in writing."
                 if ch and not ch[0].get('pct') else a_start_head(N)),
                "Load labour (trades and hours) on the critical activities in P6, then export again. Without it no manpower histogram is reliable.",
                "Use **Productivity & Resources** to turn quantities into man-hours and crew sizes for those activities.",
                a_inputs(N)])


def b10(a, F, N):          # engineering & procurement
    ds = [x for x in (F.get('disciplines') or [])
          if re.search(r'design|engineer|procure|submittal|shop draw', x.get('name') or '', re.I)]
    behind = sorted([x for x in ds if (_num(x.get('gap')) or 0) > 0], key=lambda x: -(_num(x.get('gap')) or 0))
    drv = K.main_driver(F)
    is_driver = bool(drv and any(drv['name'] == x['name'] for x in ds))
    subs = F.get('submittals') or []
    late_subs = [s for s in subs if (_num(s.get('planned_appr')) or 0) > (_num(s.get('actual_appr')) or 0)]
    where = [f"**{x['name']}**: {x.get('actual')}% done against {x.get('planned')}% planned." for x in behind[:3]]
    if late_subs:
        s = max(late_subs, key=lambda s: (_num(s.get('planned_appr')) or 0) - (_num(s.get('actual_appr')) or 0))
        where.append(f"{s.get('trade')} {s.get('submittal_type')}: {int(_num(s.get('planned_appr')) or 0)} approvals planned, "
                     f"{int(_num(s.get('actual_appr')) or 0)} received.")
    if not behind:
        return _mk("Engineering and procurement are on their planned progress. They are not what holds the project.",
                   [f_driver(F), f_head(N)], [], [a_start_head(N), a_inputs(N)])
    if is_driver:
        prob = f"Engineering is what holds the project: **{drv['name']}** is {drv.get('actual')}% done against {drv.get('planned')}% planned."
    else:
        prob = (f"Engineering and procurement are behind, but they are not what decides the finish date"
                + (f" — **{drv['name']}** is." if drv else '.'))
    return _mk(prob, where + [f_inputs(N)],
               ["Design that waits for a client input cannot move until the client provides it." if f_inputs(N) else
                "The file shows the progress gap but not its reason. Check the submittal log for what is returned and what is waiting.",
                f_head(N) if not is_driver else ''],
               [(f"Chase the approvals for {behind[0]['name']} first — it has the widest gap." if behind else ''),
                a_inputs(N),
                "Import your submittal / shop-drawing log in **Earned Value** (Engineering log) to see each package: submitted, approved, waiting.",
                a_start_head(N) if not is_driver else ''])


def b11(a, F, N):          # subcontractors, interfaces, handover
    vg = F.get('value_gap') or {}
    groups = [g for g in (vg.get('groups') or []) if (_num(g.get('gap')) or 0) > 0]
    ch = _chain(N)
    if not groups:
        return _mk("No package is behind its planned value at the data date.", [f_driver(F), f_path(N)], [],
                   ["Confirm with each subcontractor the dates of the critical activities in their scope."])
    top = groups[0]
    dim = vg.get('dimension') or 'activity code'
    where = [f"**{g['code']}**: {_money(g.get('gap'))} of planned work not done ({K.pct(g.get('pct_of_gap'), 0)} of all the late work)."
             for g in groups[:3] if (_num(g.get('pct_of_gap')) or 0) >= 1]
    return _mk(f"**{top['code']}** is the package furthest behind: it holds {K.pct(top.get('pct_of_gap'), 0)} of the work that is late "
               f"(packages read from the activity code '{dim}').",
               where + [f_path(N)],
               ["Trades that follow the late package are late because they wait for it, not because they are slow.",
                f_head(N)],
               [(f"Meet the team responsible for {top['code']} this week. Agree dates for the critical activities, starting with {_act(ch[0])}."
                 if ch else f"Meet the team responsible for {top['code']} this week and agree recovery dates."),
                "Check that testing, commissioning and handover activities exist before the finish milestone. If they are missing, add them in P6.",
                a_inputs(N)])


def b12(a, F, N):          # constructability
    lag = ((F.get('audit') or {}).get('lag_lead') or {}).get('kpis') or {}
    long_lags = lag.get('need_justification_count') or 0
    co, dg, oe = F.get('critical_oos') or 0, F.get('dangling_count') or 0, F.get('open_ends') or 0
    where = [(f"**{long_lags} lags** are longer than {lag.get('long_threshold_days') or 14} days. A long lag usually stands for work that is not in the schedule (curing, delivery, approval)."
              if long_lags else ''),
             (f"**{co} critical activities** were built out of sequence — check the logic matches how the site really works." if co else ''),
             (f"{dg} activities have a missing link." if dg else ''),
             ("Every activity has a predecessor and a successor." if not oe else f"{oe} activities have no predecessor or no successor.")]
    n_issue = sum(1 for x in (long_lags, co, dg) if x)
    if not n_issue:
        return _mk("The sequence of work is complete and connected. I found nothing a construction review must fix.",
                   where + [f_path(N)], [], ["Have the site team read the critical path once and confirm the order of work."])
    return _mk(f"The sequence of work is connected, but {n_issue} point{'s' if n_issue != 1 else ''} need a construction review before the plan is trusted.",
               where + [f_path(N)],
               ["The tool checks the logic of the network. It cannot judge whether the method of construction is right — a site engineer must."],
               [(f"Go through the {long_lags} long lags in the **Lag Report**. Replace each one that hides real work with an activity." if long_lags else ''),
                (f"Correct the {co} critical out-of-sequence activities in **Out of Sequence ▸ Resolve & Correct**." if co else ''),
                "Walk the critical path with the site team and confirm the order of work is how they will build it.",
                "Open the **Knowledge Base** for the standard sequence of this type of project and compare."])


def b13(a, F, N):          # claims & EOT
    d = _num(F.get('delay_days'))
    lo = (N.get('client_inputs_late_open') or []) if _nok(N) else []
    ld = (N.get('client_inputs_late_done') or []) if _nok(N) else []
    if d is not None and d <= 0:
        return _mk("There is no delay to the finish date, so there is no extension of time to claim today.",
                   [f_finish(F, N)], [], ["Keep a record of every late client item in case the finish slips later."])
    if not lo and not ld:
        return _mk(f"Not from this file alone. The finish is {_days(d)} late, but no client item in the schedule is late — "
                   "so on paper the delay is the contractor's.",
                   [f_finish(F, N), f_head(N) or f_no_file(N)],
                   ["A claim needs an event caused by the client: late drawings, late access, a variation, a late approval. None is in the schedule."],
                   ["Look in your letters, RFIs and site records for a client-caused event and its dates.",
                    "Add each event to the schedule as an activity linked to the work it held, then import again.",
                    "Then open **Consultant Review** to measure the days each event cost."])
    worst = sorted(lo or ld, key=lambda x: -(_num(x.get('slip_wd')) or 0))[:3]
    return _mk(f"Yes, there is a case to build: **{len(lo)} client item{'s' if len(lo) != 1 else ''}** {'are' if len(lo) != 1 else 'is'} late and still open"
               + (f", and {len(ld)} more were delivered late" if ld else '')
               + f". But the {_days(d)} is the total delay, not yet the days you can claim.",
               [f"{_act(x)}: due {x.get('baseline_finish')}, {_days(x.get('slip_wd'))} late." for x in worst] + [f_finish(F, N)],
               ["Only the days the client's items cost on the critical path can be claimed. That must be measured, event by event.",
                f_head(N)],
               ["Check today that a notice was sent for each late client item, within the time your contract allows. A missed notice can lose the claim.",
                "Open **Consultant Review**, enter each late client item as a delay event, and let it measure the days on the critical path.",
                "Keep a log for each event: date due, date received, activities held, letter reference.",
                "State the claim in calendar days and confirm each figure with a P6 reschedule (F9)."])


def b14(a, F, N):          # weather & calendars
    n = F.get('calendar_count')
    return _mk("The forecast finish does not include any allowance for bad weather. Nothing in the P6 file measures weather.",
               [f_finish(F, N), f"The schedule uses **{n} calendar{'s' if n != 1 else ''}**." if n else '', f_path(N)],
               ["P6 calendars hold working days and holidays only. Days lost to rain, wind, heat or sandstorms are not in them unless you add them."],
               ["Open **Bad Weather**. Choose the site location and site type; it gives the working days likely lost and the adjusted finish date.",
                "Open **P6 Calendar Audit** to check the working days and holidays of each calendar are right.",
                "If the weather days matter, add them to the P6 calendars as non-working days and reschedule (F9)."])


def b15(a, F, N):          # reporting
    d = _num(F.get('delay_days'))
    if d is not None and d <= 0:
        return _on_time_brief(F, N, 'Report that first.')
    return _mk(f"Report three things, in this order: the finish date, where the delay is, and what you are doing about it. "
               f"The finish is **{_days(d)} late**." if d else
               "Report three things, in this order: the finish date, where the work stands, and what you are doing about it.",
               [f_finish(F, N), f_progress(F), f_head(N) or f_no_file(N), f_inputs(N)],
               ["A manager reads the first line only. Give the date and the days late first; keep SPI and float for the planning team."]
               + (["Do not quote CPI: this file has no real actual cost."] if F.get('cost_derived') else []),
               ["Click **Build the dashboard** below, then **Download PDF** — one page for your manager.",
                "For the full monthly report, open **Reporting Studio** and pick the sections you need.",
                a_start_head(N), a_inputs(N)])


_BUILDERS = {'q01': b01, 'q02': b02, 'q03': b03, 'q04': b04, 'q05': b05, 'q06': b06, 'q07': b07, 'q08': b08,
             'q09': b09, 'q10': b10, 'q11': b11, 'q12': b12, 'q13': b13, 'q14': b14, 'q15': b15}


def plain_units(text):
    """Only the unit shorthand ('60 wd' → '60 working days') — for table CELLS, which can hold an
    activity name that must never be reworded (a 'Chain Link Fence' stays a chain link fence)."""
    t = str(text if text is not None else '')
    t = re.sub(r'(?<=\d)\s?wd\b', ' working days', t)
    return re.sub(r'\bwd\b', 'working days', t)


def plain_answer(a):
    """Planner shorthand → plain words across the long analysis too (verdict, pills, section text and
    table notes, actions, how it is measured). Activity names / IDs inside tables are not touched."""
    if not isinstance(a, dict):
        return a
    for k in ('verdict', 'measured'):
        if a.get(k):
            a[k] = plain(a[k])
    a['actions'] = [plain(x) for x in (a.get('actions') or [])]
    for p_ in (a.get('pills') or []):
        if isinstance(p_, dict) and p_.get('text'):
            p_['text'] = plain(p_['text'])
    for sec_ in (a.get('sections') or []):
        if not isinstance(sec_, dict):
            continue
        sec_['label'] = plain(sec_.get('label'))
        sec_['paras'] = [plain(x) for x in (sec_.get('paras') or [])]
        t = sec_.get('table')
        if isinstance(t, dict):
            t['cols'] = [plain(c) for c in (t.get('cols') or [])]
            if t.get('note'):
                t['note'] = plain(t['note'])
            t['rows'] = [[plain_units(c) for c in (row or [])] for row in (t.get('rows') or [])]
    for d_ in (a.get('drilldowns') or []):
        if isinstance(d_, dict) and d_.get('text'):
            d_['text'] = plain(d_['text'])
    for e_ in (a.get('evidence') or []):
        if isinstance(e_, dict):
            e_['k'], e_['v'] = plain(e_.get('k')), plain(e_.get('v'))
    return a


def build(qid, a, F, N):
    """The brief for one answer, or None (the answer then shows as before). Never raises."""
    fn = _BUILDERS.get(qid)
    if not fn or not (F or {}).get('ok'):
        return None
    try:
        b = fn(a or {}, F, N or {'ok': False})
    except Exception:
        return None
    if not b or not b.get('problem') or not b.get('do'):
        return None
    return b
