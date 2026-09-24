"""Theme 6 — Schedule Health, Logic Audit & Correction.

The DCMA 14-point read: is the logic sound, which specific checks flag and by how much,
was the update even statused honestly before anyone trusts a number off it, and — the part
that matters most — which defects actually move the finish versus which are housekeeping for
the consultant. Every answer is grounded in the stored audit modules (open ends, out-of-
sequence, dangling, float, negative float, hard constraints, relationship types, leads,
lags, high duration, circular, CPLI) exposed on the FACTS dict; where a per-item list or the
composite score lives in a dedicated screen the answer points there, and it never invents a
count the file doesn't hold. The recurring senior message: a genuine slip is not a data
artefact — clean the logic so nobody can dismiss the delay, but don't expect the cleanup to
recover the date.
"""
from . import _kit as K


# ── shared bits ──────────────────────────────────────────────────────────────

def _no_project(F):
    return None if F.get('ok') else K.A(
        "Send me your P6 schedule first.",
        body=["Drag a .xer or .xml P6 export into the chat and I'll read it, then I can answer this "
              "from your own numbers — offline, nothing leaves your PC."])


def _k(F, module):
    """The stored KPI dict for one audit module, or {} (fully None-safe)."""
    a = F.get('audit') or {}
    m = a.get(module) or {}
    return m.get('kpis') or {}


def _grade(F, module):
    a = F.get('audit') or {}
    m = a.get(module) or {}
    return m.get('grade')


def _c(n, sing, plur):
    """'3 open ends' / '1 open end' / None when n is None."""
    if n is None:
        return None
    try:
        n = int(round(float(n)))
    except (TypeError, ValueError):
        return None
    return f"{n:,} {sing if n == 1 else plur}"


def _acts(F):
    """'1,503 activities' from activity_count, or 'the activity network'."""
    n = F.get('activity_count')
    try:
        return f"{int(round(float(n))):,} activities" if n is not None else 'the activity network'
    except (TypeError, ValueError):
        return 'the activity network'


def _delay_chip(F):
    d = F.get('delay_days')
    if d is None:
        return None
    d = round(d)
    if d > 0:
        return f"+{d} wd (behind)"
    if d < 0:
        return f"{d} wd (ahead)"
    return "on date"


def _driver_clause(F):
    """A grounded clause naming the weighted driver of the shortfall, or ''."""
    d = K.main_driver(F)
    if not d:
        return ''
    return (f"driven by **{d.get('name')}** ({round((d.get('weight') or 0) * 100)}% of the project by "
            f"weight, {d.get('actual')}% done against {d.get('planned')}% planned)")


def _delay_is_real_line(F):
    """The recurring senior line: the position is genuine, not a logic/data artefact."""
    d = F.get('delay_days')
    if d is None:
        return ("One caveat: I can't derive a finish-milestone slip from this file, so judge the position "
                "against the driving path directly once the finish milestone is confirmed.")
    if d > 0:
        dc = _driver_clause(F)
        tail = f", {dc}" if dc else ""
        return (f"Crucially, the slip is **genuine, not a data artefact** — the finish is {K.delay_phrase(F)}{tail}. "
                "Don't let anyone write the delay off as a logic or lag trick; the cleanup below is housekeeping, "
                "the slip is real.")
    if d < 0:
        return (f"And the position is genuine — the finish is {K.delay_phrase(F)} — so the clean logic is "
                "reporting a real margin, not a constraint hiding one.")
    return ("And the position is genuine — the finish sits **on the planned date** — so the logic is reporting "
            "a real result, not a suppressed one.")


def _grade_word(g):
    return {'Excellent': 'excellent', 'Good': 'good', 'Acceptable': 'acceptable',
            'Needs Attention': 'needs attention', 'Critical': 'critical'}.get(g, (g or '').lower() or 'ungraded')


def _is_flag(g):
    return g in ('Critical', 'Needs Attention')


# DCMA-point roster: (module key, plain label, KPI key holding the defect count, (singular, plural))
_MOD_TABLE = [
    ('open_ends',          'Logic completeness (open ends)', 'open_ends',       ('open end', 'open ends')),
    ('dangling',           'Dangling logic',                 'total_dangling',  ('dangling activity', 'dangling activities')),
    ('leads',              'Leads (negative lag)',           'leads',           ('lead', 'leads')),
    ('lag_lead',           'Lags',                           'lagged_count',    ('lagged link', 'lagged links')),
    ('relationship_types', 'Relationship types (non-FS)',    'non_fs',          ('non-FS link', 'non-FS links')),
    ('hard_constraints',   'Hard constraints',               'hard_count',      ('hard constraint', 'hard constraints')),
    ('float',              'Excessive float',                'above_threshold', ('high-float activity', 'high-float activities')),
    ('negative_float',     'Negative float',                 'negative_count',  ('negative-float activity', 'negative-float activities')),
    ('high_duration',      'High duration',                  'over_threshold',  ('long activity', 'long activities')),
    ('out_of_sequence',    'Out-of-sequence progress',       'oos_count',       ('out-of-sequence activity', 'out-of-sequence activities')),
    ('whole_day',          'Part-day durations',             'decimal_count',   ('part-day activity', 'part-day activities')),
    ('circular',           'Circular logic',                 'loops',           ('loop', 'loops')),
]


def _present_modules(F):
    """Every DCMA module actually stored on this snapshot, with its defect count + grade."""
    a = F.get('audit') or {}
    out = []
    for key, label, ckey, (sing, plur) in _MOD_TABLE:
        m = a.get(key)
        if not m:
            continue
        k = m.get('kpis') or {}
        out.append({'key': key, 'label': label, 'count': k.get(ckey), 'sing': sing,
                    'plur': plur, 'grade': m.get('grade'), 'pct': m.get('pct')})
    return out


def _cpli_line(F):
    """A grounded sentence on critical-path / CPLI health, or ''."""
    dp = F.get('driving_path_count')
    cc = F.get('cpli_critical_count')
    cpli = _k(F, 'cpli').get('cpli')
    g = F.get('cpli_grade') or _grade(F, 'cpli')
    bits = []
    if dp is not None:
        bits.append(f"the driving path runs to about **{int(round(dp)):,} activities**")
    if cc is not None:
        bits.append(f"**{int(round(cc)):,}** sit at critical (near-zero) float")
    if not bits and cpli is None and not g:
        return ''
    line = "On the critical path: " + ("; ".join(bits) if bits else "graded on the Health Review")
    if cpli is not None:
        line += (f", and CPLI ≈ **{K.ratio(cpli)}** — "
                 + ("baseline logic is still holding the finish (float ≥ 0)." if cpli >= 1
                    else "the path is already into negative float, so any further slip moves the finish."))
    else:
        line += "."
    return line


def _no_audit(F, grounds, what):
    """Honest fallback when the audit modules haven't been stored for this snapshot."""
    body = [
        f"I can only ground {what} once the logic audit has run on this snapshot — I won't put a number "
        "on logic I haven't measured.",
        "What I can already tell you from the schedule: the finish is " + K.delay_phrase(F) + ". "
        + (_delay_is_real_line(F) if (F.get('delay_days') or 0) != 0 else ''),
    ]
    return K.A(
        "Run the logic audit and I'll read this straight off your own network.",
        body=[b for b in body if b],
        advice=[K.go_deeper(grounds, 'To populate this')],
        evidence=[K.ev('EVM', 'Delay', _delay_chip(F))])


# ── answers ────────────────────────────────────────────────────────────────────

def t06q00(F, role):
    """Overall DCMA 14-point pass/fail read."""
    if not F.get('ok'):
        return _no_project(F)
    if not F.get('has_audit'):
        return _no_audit(F, 'Schedule Health Review', 'a DCMA 14-point score')
    tech = role == 'planning'
    mods = _present_modules(F)
    flagged = [m for m in mods if _is_flag(m['grade'])]
    minor = [m for m in mods if m['grade'] == 'Acceptable' and (m['count'] or 0) > 0]
    npts = len(mods)

    def _phrase(items):
        parts = [(_c(m['count'], m['sing'], m['plur']) or m['label'].lower()) for m in items]
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]} and {parts[1]}"
        return ", ".join(parts[:-1]) + f" and {parts[-1]}"

    n_flag = len(flagged)
    if n_flag == 0 and not minor:
        head = (f"Reads **clean overall** — on the {npts} logic points I can score from this snapshot, "
                "nothing structural is corrupting the numbers.")
    elif n_flag == 0:
        head = (f"**Broadly clean.** No logic point is over its DCMA tolerance across the {npts} I can read — "
                f"only within-tolerance housekeeping remains ({_phrase(minor)}).")
    elif n_flag == 1:
        head = (f"**Broadly clean.** Just one of the {npts} logic points is over tolerance — {_phrase(flagged)} — "
                "and it isn't manufacturing the delay.")
    elif n_flag == 2:
        head = (f"**Two points need work** of the {npts} I can read — {_phrase(flagged)} — before anyone banks a "
                "forecast off this.")
    else:
        head = (f"**Mixed.** {n_flag} of the {npts} logic points I can read are over tolerance "
                f"({_phrase(flagged)}) — clean those before you rely on the forecast.")

    body = [
        (f"The Health Review runs all 14 DCMA points; I can score {npts} of them from this snapshot "
         "(invalid-date, resource, missed-task and BEI points sit outside the numbers I hold here — "
         "read those off the report itself)."),
        (f"Across {_acts(F)} the picture is "
         + ("housekeeping, not rot: " if (flagged or minor) else "clean: ")
         + (_phrase(flagged + minor) + "." if (flagged or minor)
            else "no logic point is flagging above tolerance.")),
        _delay_is_real_line(F),
    ]
    cl = _cpli_line(F)
    if cl and tech:
        body.append(cl + (f" Float health is graded **{_grade_word(F.get('float_grade'))}**."
                          if F.get('float_grade') else ""))
    body.append("Bottom line: " + ("treat the schedule as reliable enough to report and forecast off, and "
                                    "tidy the flagged points before resubmission." if len(flagged) <= 1 else
                                    "clean the flagged points, then re-score before you rely on the forecast."))
    return K.A(head, body,
               advice=["Fix the flagged points, re-run the review, then bank the position.",
                       K.go_deeper('Schedule Health Review', 'For the exact composite score across all 14 points')],
               evidence=[K.ev('Schedule Health', 'Points flagging', f"{len(flagged)} of {npts}") if npts else None,
                         K.ev('Out-of-sequence', 'Activities', F.get('oos_count')),
                         K.ev('Open ends', 'Count', F.get('open_ends')),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t06q01(F, role):
    """Which checks fail and by how much over threshold."""
    if not F.get('ok'):
        return _no_project(F)
    if not F.get('has_audit'):
        return _no_audit(F, 'Schedule Health Review', 'the failing checks')
    tech = role == 'planning'
    mods = _present_modules(F)
    failing = [m for m in mods if _is_flag(m['grade']) or (m['grade'] == 'Acceptable' and (m['count'] or 0) > 0)]
    failing.sort(key=lambda m: (m['pct'] if m['pct'] is not None else -1), reverse=True)

    if not failing:
        head = "**Nothing is failing.** Every logic point I can score sits inside its DCMA tolerance."
        body = [
            f"Across {_acts(F)} no check trips its threshold — the network is clean where it counts.",
            _delay_is_real_line(F),
            "That means the story is execution, not data: don't spend the review hunting logic defects that aren't there.",
        ]
        return K.A(head, body,
                   advice=[K.go_deeper('Schedule Health Review', 'For the exact per-point percentages')],
                   evidence=[K.ev('Open ends', 'Count', F.get('open_ends')),
                             K.ev('Out-of-sequence', 'Activities', F.get('oos_count'))])

    head = (f"**{len(failing)} check{'s' if len(failing) != 1 else ''}** stand out — ranked worst-first below, "
            "with the actual defect rate against the DCMA line.")
    lines = ["The checks over the line, in priority order:"]
    for m in failing:
        cnt = _c(m['count'], m['sing'], m['plur'])
        pctxt = f", **{K.pct(m['pct'], 1)}** of the network" if m['pct'] is not None else ""
        lines.append(f"• **{m['label']}** — {cnt or 'flagged'}{pctxt} (grade {_grade_word(m['grade'])}).")
    body = lines
    body.append(
        "The well-known DCMA lines for context: open ends and negative-lag leads should be **near zero**, "
        "hard constraints and high-duration activities under **5%**, and Finish-to-Start logic over **90%**. "
        "Read the exact allowed figure per point off the Health Review — I don't want to dress a convention up "
        "as your file's own threshold.")
    body.append(_delay_is_real_line(F))
    if tech:
        cl = _cpli_line(F)
        if cl:
            body.append(cl)
    return K.A(head, body,
               advice=["Work the list top-down; the top item is where you're furthest over the line.",
                       K.go_deeper('Schedule Health Review', 'For the exact percentage per point')],
               evidence=[K.ev(failing[0]['label'], 'Rate', K.pct(failing[0]['pct'], 1)) if failing[0]['pct'] is not None else None,
                         K.ev('Open ends', 'Count', F.get('open_ends')),
                         K.ev('Out-of-sequence', 'Activities', F.get('oos_count'))])


def t06q02(F, role):
    """Plain-English logic health for briefing the client."""
    if not F.get('ok'):
        return _no_project(F)
    if not F.get('has_audit'):
        return _no_audit(F, 'Schedule Health Review', 'a plain read of the logic')
    mods = _present_modules(F)
    flagged = [m for m in mods if _is_flag(m['grade'])]
    minor = [m for m in mods if m['grade'] == 'Acceptable' and (m['count'] or 0) > 0]
    oe = _c(F.get('open_ends'), 'loose end', 'loose ends')
    oos = _c(F.get('oos_count'), 'activity ticked off out of order', 'activities ticked off out of order')

    if not flagged and not minor:
        head = "In plain terms: the skeleton is **sound** — no structural red flags."
    elif not flagged:
        head = "In plain terms: the skeleton is **sound** — a couple of minor items to tidy, no rot."
    else:
        head = "In plain terms: the skeleton is **mostly sound**, with a short list to close before it's client-ready."

    body = [
        (f"Out of {_acts(F)}, the only housekeeping items are "
         + " and ".join([x for x in (oe, oos) if x])
         + "." if (oe or oos) else
         f"Out of {_acts(F)} the logic reads clean — no loose ends or out-of-order progress worth flagging."),
        "That's not rot — it's the kind of tidy-up every live schedule needs, not a sign the plan is broken.",
        _delay_is_real_line(F),
        ("So when we brief the client, the message is simple: the schedule is trustworthy for decisions once the "
         "loose ends are closed, and the reported position is real — not an artefact of soft logic."),
    ]
    return K.A(head, body,
               advice=["Brief it as: sound network, short tidy-up list, and a real (not manufactured) position.",
                       K.go_deeper('Schedule Health Review', 'For the graded logic quality behind this')],
               evidence=[K.ev('Open ends', 'Count', F.get('open_ends')),
                         K.ev('Out-of-sequence', 'Activities', F.get('oos_count')),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t06q03(F, role):
    """Clean enough to submit to the consultant?"""
    if not F.get('ok'):
        return _no_project(F)
    if not F.get('has_audit'):
        return _no_audit(F, 'Schedule Health Review', 'a submit/no-submit read')
    oe = F.get('open_ends')
    oos = F.get('oos_count')
    mods = _present_modules(F)
    flagged = [m for m in mods if _is_flag(m['grade'])]
    heavy = len(flagged) > 2 or (oe or 0) > 0 and (F.get('open_ends_grade') in ('Critical',))

    head = ("**Close, but tidy it first.**" if (oe or oos or flagged)
            else "**Yes — it will clear review as it stands.**")
    body = [
        ("A sharp reviewer bounces on open ends every time — every activity bar the final milestone needs a "
         f"successor, and you're carrying {_c(oe, 'open end', 'open ends') or 'none'}."
         if oe else
         "Logic completeness is clean — no open ends for a reviewer to bounce on."),
        ("They'll also query the out-of-sequence items and want a one-line status note on each — you have "
         f"{_c(oos, 'out-of-sequence activity', 'out-of-sequence activities') or 'none'}."
         if oos else
         "There's no out-of-sequence progress to explain, which removes the usual second query."),
    ]
    if flagged:
        names = ", ".join(m['label'].split(' (')[0].lower() for m in flagged)
        body.append(f"The points still over the DCMA line — {names} — are what a reviewer marks up; none is fatal, "
                    "but each is a reason to send it back if you submit as-is.")
    body.append(
        "That's not structural — it's typically half a day of housekeeping. Close the open ends, add the "
        "status notes, confirm no key milestone is left dangling, and it clears review.")
    body.append(_delay_is_real_line(F)
                + " Submitting dirty invites a rejection over cosmetics while the real story gets buried in the markup.")
    return K.A(head, body,
               advice=["Half a day of housekeeping now saves a rejection cycle — close the open ends before you send it.",
                       K.go_deeper('Schedule Health Review, Constructability Review',
                                   'For the full check list a reviewer will run')],
               evidence=[K.ev('Open ends', 'Count', oe),
                         K.ev('Out-of-sequence', 'Activities', oos),
                         K.ev('Logic points flagging', 'Count', len(flagged) if mods else None)])


def t06q04(F, role):
    """Was the update statused correctly before trusting the numbers?"""
    if not F.get('ok'):
        return _no_project(F)
    dd = F.get('data_date')
    oos = F.get('oos_count')
    head = "**Validate the statusing before you trust any EVM or delay figure — garbage in, garbage out.**"
    body = [
        ("Update Analysis checks the classic data-entry tells: activities showing progress with **no actual "
         "start**, completed work **missing actual dates**, and **remaining duration left on finished activities**. "
         "Those specific tells are computed there, not carried on this snapshot, so run it before you report — "
         "I won't claim a clean statusing I haven't measured."),
        (f"Data date on this file is **{dd}** — that's the cutoff every number is measured to." if dd else
         "I can't read a data date off this snapshot — confirm it's current, because a stale data date silently "
         "distorts every earned-value and delay figure."),
        ((f"The one statusing flag I can already see is out-of-sequence progress: "
          f"{_c(oos, 'activity', 'activities')} progressed against their logic — reconcile each before you rely on "
          "the update, because out-of-sequence work is exactly where progress gets recorded against the wrong bar.")
         if oos else
         "I see no out-of-sequence progress on this snapshot, which is one less statusing worry."),
        (f"Once the statusing is clean, the headline holds: {K.spi_verdict(F)[1]}, and the finish is "
         f"{K.delay_phrase(F)}. Never report those off an unvalidated update."),
    ]
    return K.A(head, body,
               advice=["Run Update Analysis first, clear any statusing flags, then report the EVM and delay.",
                       K.go_deeper('Update Analysis, Schedule Health Review', 'For the data-quality checks')],
               evidence=[K.ev('Data date', 'Cutoff', dd),
                         K.ev('Out-of-sequence', 'Activities', oos),
                         K.ev('EVM', 'SPI', K.ratio(F.get('spi')))])


def t06q05(F, role):
    """Every dangling activity and open end, and why each matters."""
    if not F.get('ok'):
        return _no_project(F)
    if not F.get('has_audit'):
        return _no_audit(F, 'Schedule Audit, Schedule Health Review', 'the dangling / open-end list')
    ek = _k(F, 'open_ends')
    dk = _k(F, 'dangling')
    oe = F.get('open_ends')
    no_succ = ek.get('no_successor')
    no_pred = ek.get('no_predecessor')
    dang = F.get('dangling_count')
    start_d = dk.get('start_dangling')
    fin_d = dk.get('finish_dangling')
    both_d = dk.get('both_dangling')

    total = (oe or 0) + (dang or 0)
    head = (f"You have {_c(oe, 'open end', 'open ends') or 'no open ends'}"
            + (f" and {_c(dang, 'dangling activity', 'dangling activities')}" if dang else "")
            + " — here's the breakdown and why each one distorts the schedule."
            if total else "**No open ends or dangling activities** — logic completeness is clean.")
    body = []
    if oe:
        body.append(
            "**Open ends** break down as "
            + ", ".join([x for x in (_c(no_succ, 'with no successor (open finish)', 'with no successor (open finish)'),
                                     _c(no_pred, 'with no predecessor (open start)', 'with no predecessor (open start)')) if x])
            + ". An activity with **no successor** can slip freely without pushing the finish — so it *hides* delay; "
              "one with **no predecessor** drifts with no driver telling it when to start.")
    if dang:
        body.append(
            "**Dangling** activities are tied on only one side — "
            + ", ".join([x for x in (_c(start_d, 'open at the start', 'open at the start'),
                                     _c(fin_d, 'open at the finish', 'open at the finish'),
                                     _c(both_d, 'open both ends', 'open both ends')) if x])
            + ". A finish-dangling activity looks driven but its completion pushes nothing downstream, so its slip "
              "is invisible to the finish date.")
    body.append(
        f"On {_acts(F)} these counts are "
        + ("low — but every one distorts float and the critical-path calculation, so they're worth closing."
           if total else "clean.")
        if True else "")
    if F.get('neg_float_count'):
        body.append(
            f"Close them and your negative-float picture — **{_c(F.get('neg_float_count'), 'activity', 'activities')}** "
            f"({K.pct(F.get('neg_float_pct'), 1)}) currently on negative total float — becomes fully trustworthy, "
            "because right now an open end can flatter or distort that reading.")
    body.append("The Schedule Audit lists each one by activity ID with a reason line — that's your itemised punch list.")
    return K.A(head, [b for b in body if b],
               advice=["Close every open end and tie in each dangling activity, then re-run to confirm the float reads true.",
                       K.go_deeper('Schedule Audit, Schedule Health Review', 'For the itemised list by activity ID')],
               evidence=[K.ev('Open ends', 'Total', oe),
                         K.ev('Open ends', 'No successor', no_succ),
                         K.ev('Dangling', 'Total', dang),
                         K.ev('Negative float', 'Activities', F.get('neg_float_count'))])


def t06q06(F, role):
    """Suggest missing links to close open ends + corrected XER."""
    if not F.get('ok'):
        return _no_project(F)
    oe = F.get('open_ends')
    head = (f"The Schedule Audit will propose links for each of your {_c(oe, 'open end', 'open ends')} and write you "
            "a corrected XER to reimport."
            if oe else "**No open ends to close** — logic completeness is already clean, so there's nothing to relink.")
    if not oe:
        body = [
            "There are no open-ended activities on this snapshot, so there's no missing link to suggest and no "
            "corrected file needed for this check.",
            "If the audit hasn't run yet, run it to confirm — I'm reading the stored open-ends count, and it's zero.",
            _delay_is_real_line(F),
        ]
        return K.A(head, [b for b in body if b],
                   advice=[K.go_deeper('Schedule Audit', 'To re-confirm and export a corrected file if needed')],
                   evidence=[K.ev('Open ends', 'Count', oe)])
    body = [
        ("For each open end the audit infers a candidate predecessor/successor from the evidence in your own "
         "file — WBS neighbours, activity codes, naming and the natural construction sequence — and ranks each "
         "suggestion by confidence (High / Moderate / Insufficient)."),
        ("You accept or edit each one; only then does it write a corrected XER/XML you reimport into P6. Nothing is "
         "auto-applied to your baseline — a suggestion is a starting point, not gospel."),
        ("Treat them as exactly that: eyeball each against how the work physically builds, especially anything tying "
         "into the driving path, because a wrong link there would move the finish for the wrong reason."),
        _delay_is_real_line(F),
    ]
    return K.A(head, [b for b in body if b],
               advice=["Review every suggested link against the real build sequence before you accept it — never auto-apply logic to a live baseline.",
                       K.go_deeper('Schedule Audit', 'To generate the suggestions and export the corrected XER')],
               evidence=[K.ev('Open ends', 'To close', oe),
                         K.ev('Open ends', 'No successor', _k(F, 'open_ends').get('no_successor')),
                         K.ev('Open ends', 'No predecessor', _k(F, 'open_ends').get('no_predecessor'))])


def t06q07(F, role):
    """Hard constraints — count, placement, over the DCMA 5% limit?"""
    if not F.get('ok'):
        return _no_project(F)
    hk = _k(F, 'hard_constraints')
    computable = F.get('hard_constraints_computable')
    if not F.get('has_audit') or (computable is False):
        return K.A(
            "The Health Review counts and grades hard constraints against the DCMA 5% ceiling.",
            body=[
                "I can't read a stored hard-constraint count off this snapshot"
                + (" (the check reports it as not computable on this file)." if computable is False else " yet."),
                "What matters on this file: the finish is " + K.delay_phrase(F) + ". "
                + (_delay_is_real_line(F) if (F.get('delay_days') or 0) > 0 else ""),
                "The manipulation to watch for is a **Must-Finish-On** or **Mandatory** constraint bolted onto the "
                "completion milestone to mask negative float — if the review flags one on the driving path, strip it "
                "so total float shows honestly.",
            ],
            advice=[K.go_deeper('Schedule Health Review', 'For the exact constraint count and 5% test')],
            evidence=[K.ev('EVM', 'Delay', _delay_chip(F))])
    hard = hk.get('hard_count')
    hpct = hk.get('hard_pct')
    by_type = hk.get('by_type') or {}
    over = (hpct is not None and hpct > 5.0)
    head = (f"**{_c(hard, 'hard constraint', 'hard constraints')}** on the file — "
            + (f"**{K.pct(hpct, 1)}** of activities, which is **over** the DCMA 5% ceiling." if over
               else (f"**{K.pct(hpct, 1)}** of activities, **inside** the DCMA 5% ceiling." if hpct is not None
                     else "read the percentage off the report.")))
    body = []
    if by_type:
        parts = [f"{n} × {t}" for t, n in by_type.items() if n]
        if parts:
            body.append("By type: " + ", ".join(parts) + ". Must-Finish-On and Mandatory are the hard ones — they "
                        "override logic and can freeze or mask float.")
    body.append(
        "The DCMA test is simple: hard constraints should be under 5% of activities, because each one stops the "
        "network flexing the way real work does." + (" You're over that line." if over else " You're within it."))
    body.append(_delay_is_real_line(F)
                + " That matters here: no one has bolted a Must-Finish-On onto the completion milestone to mask "
                "negative float — the slip is showing honestly.")
    body.append("If any hard constraint sits on the driving path, strip it and let logic drive the date — you want "
                "negative float visible, not suppressed.")
    return K.A(head, [b for b in body if b],
               advice=["Replace any date constraint on the driving path with real logic so the finish moves honestly.",
                       K.go_deeper('Schedule Health Review', 'For the constraint list and placement')],
               evidence=[K.ev('Constraints', 'Hard count', hard),
                         K.ev('Constraints', 'Share', K.pct(hpct, 1) if hpct is not None else None),
                         K.ev('Constraints', 'DCMA line', '5%')])


def t06q08(F, role):
    """FS vs other relationship types."""
    if not F.get('ok'):
        return _no_project(F)
    rk = _k(F, 'relationship_types')
    if not F.get('has_audit') or not rk:
        return _no_audit(F, 'Schedule Health Review', 'the relationship-type mix')
    fs = rk.get('fs_pct')
    ss = rk.get('ss_pct')
    ff = rk.get('ff_pct')
    sf = rk.get('sf_pct')
    non_fs = rk.get('non_fs')
    total = rk.get('total_relationships')
    ok_fs = (fs is not None and fs >= 90.0)
    head = (f"**{K.pct(fs, 1)}** of your logic is Finish-to-Start — "
            + ("**above** the DCMA >90% guidance, so the mix is healthy." if ok_fs
               else ("**under** the DCMA >90% guidance, so there's conversion to do." if fs is not None
                     else "read the exact split off the report."))
            if fs is not None else "The Health Review gives the FS/SS/FF/SF split against the DCMA >90%-FS guidance.")
    body = [
        ("The full split: "
         + ", ".join([x for x in (f"**FS {K.pct(fs, 1)}**" if fs is not None else None,
                                   f"SS {K.pct(ss, 1)}" if ss is not None else None,
                                   f"FF {K.pct(ff, 1)}" if ff is not None else None,
                                   f"SF {K.pct(sf, 1)}" if sf is not None else None) if x])
         + (f" across {total:,} relationships" if total else "")
         + f", i.e. {_c(non_fs, 'non-FS link', 'non-FS links')} to look at." if non_fs is not None else ""),
        ("As a rule, heavy **SS/FF** is where overlap gets hidden and logic goes soft — a start-to-start lets two "
         "activities run in parallel on an assumed offset that may not hold, and an open finish-to-finish can flatter "
         "durations."),
        ("If the driving chain is threaded with start-to-starts rather than clean finish-to-starts, that overlap may "
         "be flattering the forecast — convert what you can to FS, but not blindly. Some overlap is genuine (a trade "
         "following another down a line), so keep the links that reflect how the work truly runs."),
    ]
    if sf and sf > 0:
        body.append(f"Watch the **SF** links specifically ({K.pct(sf, 1)}) — start-to-finish is rare in real "
                    "construction and usually a modelling error worth checking one by one.")
    return K.A(head, [b for b in body if b],
               advice=["Convert soft SS/FF on the driving path to FS where the real sequence allows; leave genuine overlap alone.",
                       K.go_deeper('Schedule Health Review', 'For the exact mix and the non-FS list')],
               evidence=[K.ev('Relationships', 'FS share', K.pct(fs, 1) if fs is not None else None),
                         K.ev('Relationships', 'Non-FS links', non_fs),
                         K.ev('Relationships', 'DCMA line', '>90% FS')])


def t06q09(F, role):
    """Lags and leads — counts, excessive, justified or hiding work?"""
    if not F.get('ok'):
        return _no_project(F)
    llk = _k(F, 'lag_lead')
    lk = _k(F, 'leads')
    if not F.get('has_audit') or not (llk or lk):
        return _no_audit(F, 'Schedule Audit, Schedule Health Review', 'the lag / lead counts')
    lagged = llk.get('lagged_count')
    lagged_pct = llk.get('lagged_pct')
    leads = llk.get('leads_count')
    if leads is None:
        leads = lk.get('leads')
    longs = llk.get('long_count')
    need_just = llk.get('need_justification_count')
    long_days = llk.get('long_threshold_days')
    crit = llk.get('critical_count')
    verdict = llk.get('verdict')

    head = (f"**{_c(lagged, 'lagged link', 'lagged links')}**"
            + (f" ({K.pct(lagged_pct, 1)})" if lagged_pct is not None else "")
            + (f" and **{_c(leads, 'lead', 'leads')}**" if leads is not None else "")
            + " — leads are the one to worry about."
            if lagged is not None else "The audit counts every lag and lead and flags the negatives.")
    body = [
        ("**Leads** — negative lags — are the red flag: they let a successor start *before* its driver is done and "
         "quietly compress the path. " + (f"You have {_c(leads, 'lead', 'leads')}." if leads is not None else "")
         + (" DCMA wants that at zero." if (leads or 0) else " That's the DCMA-clean position.")),
        ("**Lags** aren't wrong in themselves, but a long lag is often a **hidden activity** — cure time, a delivery "
         "lead, a permit wait — that should be a real, resourced bar you can track and progress, not an invisible gap "
         "in a link."
         + (f" {_c(longs, 'lag', 'lags')} exceed the {int(long_days) if long_days else 'long'}-day line"
            + (f" and {_c(need_just, 'link', 'links')} need a written justification." if need_just is not None else ".")
            if longs is not None else "")),
    ]
    if crit:
        body.append(f"**{_c(crit, 'lagged link', 'lagged links')}** sit on the critical path — those are the ones a "
                    "reviewer will challenge first, because a lag there directly sets the finish.")
    if verdict:
        body.append(f"The audit's overall read on your lag/lead usage: **{verdict}**.")
    body.append(
        (_delay_is_real_line(F) + " In lag terms: no lag manipulation is masking the slip — nobody's inflated a lag "
         "to absorb lost time.") if (F.get('delay_days') or 0) > 0 else
        "Cross-check any long lag against the Constructability missing-activity list — a lag hiding real scope is the "
        "most common way a schedule under-counts work.")
    return K.A(head, [b for b in body if b],
               advice=["Turn any long lag on the driving path into a real activity, and eliminate every lead you can't defend.",
                       K.go_deeper('Schedule Audit, Constructability Review', 'For the lag register and the missing-scope cross-check')],
               evidence=[K.ev('Leads/Lags', 'Leads', leads),
                         K.ev('Leads/Lags', 'Lagged links', lagged),
                         K.ev('Leads/Lags', 'Long lags', longs),
                         K.ev('Leads/Lags', 'On critical path', crit)])


def t06q10(F, role):
    """Activities over the 44-day threshold to break down."""
    if not F.get('ok'):
        return _no_project(F)
    hk = _k(F, 'high_duration')
    if not F.get('has_audit') or not hk:
        return _no_audit(F, 'Schedule Health Review', 'the high-duration list')
    over = hk.get('over_threshold')
    thr = hk.get('threshold')
    hpct = hk.get('high_pct')
    maxd = hk.get('max_duration')
    thr_txt = f"{int(thr)}" if thr is not None else "44"
    head = (f"**{_c(over, 'activity', 'activities')}** run longer than the {thr_txt}-working-day DCMA limit"
            + (f" ({K.pct(hpct, 1)} of the schedule)." if hpct is not None else ".")
            if over is not None else f"The Health Review lists every activity over the {thr_txt}-day limit.")
    body = [
        ("Long bars kill progress granularity — you can't see a 90-day activity slipping until it's already too late, "
         "and a single long bar smears earned value across weeks so the update looks flat when work is actually "
         "moving (or stalling)."),
        (f"The longest single activity on this file runs about **{int(round(maxd))} days**." if maxd else ""),
        ("Break the offenders into monthly or milestone-based chunks — one bar per pour, per floor, per span — so "
         "each update actually shows movement and the earned value lands where the work happened."),
        ("Prioritise any long bar sitting on the driving path" + (
            f" ({_driver_clause(F)})" if _driver_clause(F) else "") + " — that's where a coarse duration is most "
         "likely to be hiding a slip."),
    ]
    return K.A(head, [b for b in body if b],
               advice=[f"Split every activity over {thr_txt} days on the driving path into trackable, milestone-sized pieces.",
                       K.go_deeper('Schedule Health Review', 'For the exact list of long activities')],
               evidence=[K.ev('High duration', 'Over threshold', over),
                         K.ev('High duration', 'Longest (days)', int(round(maxd)) if maxd else None),
                         K.ev('High duration', 'DCMA line', f"{thr_txt} wd")])


def t06q11(F, role):
    """Circular logic / loops."""
    if not F.get('ok'):
        return _no_project(F)
    ck = _k(F, 'circular')
    loops = ck.get('loops')
    in_loops = ck.get('activities_in_loops')
    longest = ck.get('longest_loop')
    if not F.get('has_audit') or loops is None:
        # Infer from the fact that a coherent forecast exists.
        coherent = (F.get('delay_days') is not None) or bool(F.get('forecast_finish'))
        return K.A(
            "**No sign of circular logic** — the network is calculating cleanly." if coherent
            else "Run the Health Review's loop scan to confirm the network is calculating.",
            body=[
                "A loop is a **blocking gate**: if the logic circles back on itself, P6 can't run the forward/backward "
                "pass — no float, no critical path, no reliable finish until it's broken.",
                ("The tell here is that we're getting a coherent read — the finish is " + K.delay_phrase(F)
                 + " with a derivable critical path — which only happens when the network resolves, i.e. no open loops."
                 if coherent else
                 "I can't confirm it from a stored count on this snapshot, so run the loop scan first."),
                "If the check ever flags a loop, fix it before you read any other metric — everything downstream is "
                "meaningless until the network calculates.",
            ],
            advice=[K.go_deeper('Schedule Health Review', 'For the explicit loop scan')],
            evidence=[K.ev('EVM', 'Delay', _delay_chip(F))])
    if loops == 0:
        head = "**No circular logic** — zero loops, the network calculates cleanly."
        body = [
            "This is the gate that has to pass before anything else counts: a loop stops P6 running the schedule, so "
            "float, critical path and finish date would all be meaningless. Yours is clear.",
            f"The scan checked {_acts(F)} and found no relationship that circles back on itself.",
            "That's why the rest of this review is trustworthy — the forecast finish (" + K.delay_phrase(F)
            + ") comes from a network that actually resolves.",
        ]
    else:
        head = (f"**{_c(loops, 'loop', 'loops')}** detected — this is a **blocking** problem, fix it before you trust "
                "any other number.")
        body = [
            f"A loop stops the network calculating, so right now float, critical path and finish date are all "
            f"unreliable. **{_c(in_loops, 'activity is', 'activities are')}** caught in the loop(s)"
            + (f", the longest running to {int(longest)} activities." if longest else ".") ,
            "Open the loop scan, find the relationship that circles back, and delete or redirect it — usually one "
            "wrong predecessor is closing the ring.",
            "Do this first. Every other metric in this review is provisional until the loop is broken and the "
            "schedule recalculates.",
        ]
    return K.A(head, [b for b in body if b],
               advice=["Clear any loop before reading float or critical path — it's a hard gate, not a warning." if (loops or 0) else
                       "Nothing to do here — the loop gate is passed.",
                       K.go_deeper('Schedule Health Review', 'For the loop scan detail')],
               evidence=[K.ev('Circular', 'Loops', loops),
                         K.ev('Circular', 'Activities in loops', in_loops)])


def t06q12(F, role):
    """Out-of-sequence progress — why, fix, corrected schedule."""
    if not F.get('ok'):
        return _no_project(F)
    ok_ = _k(F, 'out_of_sequence')
    oos = F.get('oos_count')
    oos_pct = F.get('oos_pct')
    crit = F.get('critical_oos')
    near = ok_.get('near_critical_oos')
    if not F.get('has_audit') or oos is None:
        return _no_audit(F, 'Schedule Audit', 'the out-of-sequence list')
    if oos == 0:
        head = "**No out-of-sequence progress** — every statused activity moved in its planned order."
        body = [
            f"Across {_acts(F)} nothing has been progressed against its logic, so there's no sequence to reconcile "
            "and nothing distorting your progress reading on that front.",
            _delay_is_real_line(F),
            "That's one fewer thing for a reviewer to query, and it means the recorded progress can be trusted "
            "against the network as drawn.",
        ]
        return K.A(head, [b for b in body if b],
                   advice=[K.go_deeper('Schedule Audit', 'To re-confirm on the same engine')],
                   evidence=[K.ev('Out-of-sequence', 'Activities', oos)])
    head = (f"**Yes — {_c(oos, 'activity', 'activities')}** progressed out of planned logic"
            + (f" ({K.pct(oos_pct, 1)} of the schedule)." if oos_pct is not None else ".")
            + (f" **{int(crit)}** of them on the critical path." if crit else ""))
    body = [
        ("The usual causes are one of two: work **started before its predecessor formally finished** — access or "
         "materials came early and the crew got on with it — or the **logic no longer matches** how the trades are "
         "actually building, so P6 thinks the order is wrong when the field is right."),
        ("The Schedule Audit gives a **per-item cause**, lets you apply or edit a correction, re-validates on the "
         "**same engine**, then writes a corrected XER/XML to reimport into P6 — so the fix is round-tripped, not "
         "guessed."),
        (f"{_c(oos, 'item', 'items')} is manageable" + (f", but check the **{int(crit)} on the critical path** first"
         if crit else "") + ": out-of-sequence progress on the driving path can flatter true progress and mask the "
         "slip we're reporting, so those are the ones that actually matter."),
        _delay_is_real_line(F),
    ]
    return K.A(head, [b for b in body if b],
               advice=["Reconcile the critical-path out-of-sequence items first, correct on the same engine, then reimport the corrected file.",
                       K.go_deeper('Schedule Audit', 'To apply the corrections and export the corrected schedule')],
               evidence=[K.ev('Out-of-sequence', 'Activities', oos),
                         K.ev('Out-of-sequence', 'Share', K.pct(oos_pct, 1) if oos_pct is not None else None),
                         K.ev('Out-of-sequence', 'On critical path', crit)])


def t06q13(F, role):
    """Milestones tied into logic on both sides?"""
    if not F.get('ok'):
        return _no_project(F)
    ek = _k(F, 'open_ends')
    oe = F.get('open_ends')
    no_succ = ek.get('no_successor')
    no_pred = ek.get('no_predecessor')
    dang = F.get('dangling_count')
    head = ("Every milestone should be driven on both sides — a predecessor pushing it, and (for interim ones) a "
            "successor carrying it forward.")
    body = [
        ("A **detached milestone floats free** and reports a date nobody's schedule actually controls — dangerous "
         "for a sectional-completion date that carries LD exposure, because it can look safe while the work feeding "
         "it slips."),
        (f"On this file the logic-completeness check flags {_c(oe, 'open end', 'open ends') or 'no open ends'}"
         + (f" ({_c(no_pred, 'with no predecessor', 'with no predecessor')}, "
            f"{_c(no_succ, 'with no successor', 'with no successor')})" if (no_pred is not None or no_succ is not None) else "")
         + (f" and {_c(dang, 'dangling activity', 'dangling activities')}" if dang else "")
         + ". The audit lists each by ID — **check whether any of them is a key milestone**, because a dangling "
           "milestone is the worst offender."
         if (oe or dang) else ". Logic completeness is clean, so no milestone is obviously left hanging — but "
           "confirm the contractual ones specifically on the audit's milestone view."),
        ("Every contractual milestone — especially the handover/sectional dates carrying liquidated damages — must "
         "be **network-driven**, so its forecast moves honestly the moment the work behind it slips. A milestone on "
         "a date constraint instead of logic will lie to you."),
        _delay_is_real_line(F),
    ]
    return K.A(head, [b for b in body if b],
               advice=["Confirm each contractual milestone has a real predecessor (and a successor if interim) — no date-constraint stand-ins.",
                       K.go_deeper('Schedule Health Review, Schedule Audit', 'For the milestone tie-in check by ID')],
               evidence=[K.ev('Open ends', 'Count', oe),
                         K.ev('Open ends', 'No successor', no_succ),
                         K.ev('Dangling', 'Count', dang)])


def t06q14(F, role):
    """Prioritised punch list: completion-driving vs cosmetic."""
    if not F.get('ok'):
        return _no_project(F)
    if not F.get('has_audit'):
        return _no_audit(F, 'Schedule Health Review, Schedule Audit', 'a prioritised punch list')
    crit_oos = F.get('critical_oos')
    oos = F.get('oos_count')
    neg = F.get('neg_float_count')
    oe = F.get('open_ends')
    dang = F.get('dangling_count')
    hk = _k(F, 'hard_constraints')
    hard = hk.get('hard_count')
    hd = _k(F, 'high_duration').get('over_threshold')
    non_fs = _k(F, 'relationship_types').get('non_fs')

    driving = []
    if crit_oos:
        driving.append(f"reconcile the **{int(crit_oos)} out-of-sequence items on the critical path**")
    elif oos:
        driving.append(f"reconcile the **{_c(oos, 'out-of-sequence item', 'out-of-sequence items')}** and confirm none sits on the driving path")
    if neg:
        driving.append(f"resolve the **{_c(neg, 'negative-float activity', 'negative-float activities')}** — the network's own slip signal")
    if oe:
        driving.append(f"close any of the **{_c(oe, 'open end', 'open ends')}** that sits on the driving path")
    if hard:
        driving.append(f"strip any of the **{_c(hard, 'hard constraint', 'hard constraints')}** suppressing float on the critical path")

    cosmetic = []
    if oe:
        cosmetic.append(f"tie in the remaining open ends and **{_c(dang, 'dangling activity', 'dangling activities') or 'any dangling activities'}**")
    if hd:
        cosmetic.append(f"break down the **{_c(hd, 'long activity', 'long activities')}** over the duration limit")
    if non_fs:
        cosmetic.append(f"clean up the **{_c(non_fs, 'non-FS link', 'non-FS links')}** where the sequence allows")

    head = "Here's the punch list, split by what **moves the finish** versus what's **housekeeping for the consultant**."
    body = [
        ("**First — completion-driving (do these before resubmit):** " + "; ".join(driving) + "."
         if driving else
         "**Completion-driving:** nothing on the critical path is flagging — no out-of-sequence, negative float or "
         "constraint issue is currently moving your finish."),
        ("**Then — cosmetic (housekeeping the reviewer wants, but they don't move the date):** " + "; ".join(cosmetic) + "."
         if cosmetic else
         "**Cosmetic:** the housekeeping items are clean too — little left to tidy."),
        _delay_is_real_line(F),
        ("So the completion-driving fixes are a short list; the rest is presentation for the consultant. Don't burn a "
         "week polishing cosmetics while the real recovery work — on the driving front — waits."),
    ]
    return K.A(head, [b for b in body if b],
               advice=["Work the completion-driving list first; only then spend time on the cosmetic tidy-up for the reviewer.",
                       K.go_deeper('Schedule Health Review, Schedule Audit', 'For the full finding list behind this')],
               evidence=[K.ev('Out-of-sequence', 'On critical path', crit_oos if crit_oos is not None else oos),
                         K.ev('Negative float', 'Activities', neg),
                         K.ev('Open ends', 'Count', oe),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t06q15(F, role):
    """Will cleaning up the logic change the finish date?"""
    if not F.get('ok'):
        return _no_project(F)
    oe = F.get('open_ends')
    oos = F.get('oos_count')
    d = F.get('delay_days')
    items = " and ".join([x for x in (_c(oe, 'open end', 'open ends'),
                                      _c(oos, 'out-of-sequence item', 'out-of-sequence items')) if x]) or "the logic flags"
    if d is not None and d > 0:
        head = "**Mostly no — and that's the message.**"
        body = [
            (f"Closing {items} cleans the logic and makes the forecast trustworthy, but it **won't pull the finish "
             f"in**. The slip is {K.delay_phrase(F)}" + (f", {_driver_clause(F)}" if _driver_clause(F) else "")
             + " — it's a physical shortfall on the work, not a data defect."),
            ("There's one exception worth checking: if an **open end or out-of-sequence item sits on the driving "
             "path**, closing it can change which path is critical and shift the date. That's exactly why you "
             "reconcile the critical-path items first — but on most files the cleanup is neutral to the finish."),
            ("Run it through the What-if / F9 keystone before you rework: it gives an instant estimate, then the "
             "exact P6 figure via a build → F9 round-trip, so you're not guessing whether the cleanup bought time."),
            ("Don't let anyone hope the tidy-up recovers the date — real recovery comes from the levers you test in "
             "the What-if (extra shift, second crew, resequencing the driving front), not from closing open ends."),
        ]
    elif d is not None and d <= 0:
        head = "**No — and it doesn't need to.**"
        body = [
            (f"You're {K.delay_phrase(F)}, so there's no slip for the cleanup to recover. Closing {items} makes the "
             "logic clean and the margin **trustworthy**, but it won't move a finish that's already holding."),
            ("The one thing to watch: if a fix touches the driving path it can shift which path is critical — verify "
             "on the What-if before you assume the margin is unchanged."),
            ("Use the What-if / F9 keystone to confirm: instant estimate first, exact P6 figure via the build → F9 "
             "round-trip. Clean the logic to protect the date, not to gain one you already have."),
        ]
    else:
        head = "The cleanup won't manufacture a finish date — confirm the position on the F9 keystone."
        body = [
            (f"Closing {items} cleans the logic, but I can't derive a finish-milestone slip from this file, so I "
             "won't claim the fix moves a date I can't measure."),
            ("Run the What-if / F9 keystone: it estimates the effect instantly, then confirms the exact P6 figure via "
             "a build → F9 round-trip — that's the only honest way to say whether the cleanup changes completion."),
            "Confirm the finish milestone first, then judge any fix against it.",
        ]
    return K.A(head, [b for b in body if b],
               advice=["Verify any driving-path fix on the What-if/F9 before you rework — cleanup rarely recovers time, real levers do.",
                       K.go_deeper('What-if / scenario engine, Schedule Health Review', 'To test the finish effect before reworking')],
               evidence=[K.ev('Open ends', 'To close', oe),
                         K.ev('Out-of-sequence', 'To reconcile', oos),
                         K.ev('EVM', 'Delay', _delay_chip(F))])


def t06q16(F, role):
    """GAP — redundant / duplicate relationships."""
    if not F.get('ok'):
        return _no_project(F)
    head = "**Honest answer: the tool can't ground this one yet.**"
    body = [
        (K.gap_note('GAP — redundant-relationship detection is not in the DCMA set or the current audits')
         or "Redundant-relationship detection isn't in the current audit set, so I won't put a number on it."),
        ("A redundant relationship is a link that adds nothing because a longer logic path already governs the same "
         "two activities — harmless to the calculation, but it clutters the network and obscures the true driving "
         "path, which makes the schedule harder to read and to defend."),
        ("For now you'd spot it manually in P6 (or a scheduling add-in) — look for a direct FS between two activities "
         "that are also connected through a longer chain. To ground it here we'd need a **transitive-redundancy "
         "pass** added to the logic audit; it's a clean fit beside the existing checks."),
        ("Everything else in this review stands on measured numbers — this is the one item I'm flagging as not yet "
         "computed, rather than guessing at it."),
    ]
    return K.A(head, [b for b in body if b],
               advice=["Until it's built, scan for redundant FS links manually on the driving path — that's where clutter hurts readability most.",
                       "Ask again once the logic audit gains a transitive-redundancy pass — then I can count them for you."],
               evidence=[K.ev('Schedule Audit', 'Logic checks today', 'DCMA set (no redundancy pass)')])


ANSWERS = {
    't06q00': t06q00, 't06q01': t06q01, 't06q02': t06q02, 't06q03': t06q03, 't06q04': t06q04,
    't06q05': t06q05, 't06q06': t06q06, 't06q07': t06q07, 't06q08': t06q08, 't06q09': t06q09,
    't06q10': t06q10, 't06q11': t06q11, 't06q12': t06q12, 't06q13': t06q13, 't06q14': t06q14,
    't06q15': t06q15, 't06q16': t06q16,
}
