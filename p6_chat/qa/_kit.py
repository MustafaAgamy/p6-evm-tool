"""Answer-construction kit for the Offline AI Chat question engine.

Every theme module in ``p6_chat/qa`` builds its answers with these helpers, so all 182
answers share ONE senior-planning-engineer voice, cite grounded numbers the same way, and
point to the right tool feature for the deep dive. The helpers read only from the FACTS
dict (``p6_chat.facts.build_facts``) — never a live metric of their own.

An answer is the shape the chat already renders (``renderAssistant``):
    {'headline': str, 'body': [str, ...], 'advice': [str, ...],
     'evidence': [{'module', 'plain', 'value'}, ...]}
Body/advice accept inline markdown (**bold**). Keep it detailed and plain — a manager with
no Primavera background must follow it, a planner must trust the numbers.

Honesty rules (binding):
  * Never invent a number. If a fact is None, say what's missing and point to the feature
    that computes it — never fabricate a figure.
  * ``delay_days`` is POSITIVE = behind, negative = ahead, 0 = on the date (whole-tool
    convention after the delay-sign fix).
  * For a 'gap' question, say plainly the tool doesn't compute it and how a planner handles
    it. For 'in-progress', name the feature being built.
"""


# ── answer + evidence builders ────────────────────────────────────────────────

def A(headline, body=None, advice=None, evidence=None):
    return {'headline': headline,
            'body': [b for b in (body or []) if b],
            'advice': [a for a in (advice or []) if a],
            'evidence': [e for e in (evidence or []) if e]}


def ev(module, plain, value):
    """One evidence chip. Skipped by A() if value is None/''."""
    if value is None or value == '':
        return None
    return {'module': module, 'plain': plain, 'value': value}


# ── number / phrase helpers (all None-safe) ─────────────────────────────────────

def _n(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def wd(days):
    """'60 working days' (absolute). None -> ''. """
    d = _n(days)
    if d is None:
        return ''
    d = abs(round(d))
    return f"{d:,} working day{'s' if d != 1 else ''}"


def weeks(days):
    d = _n(days)
    return '' if d is None else f"{max(1, round(abs(d) / 5))} week{'s' if max(1, round(abs(d)/5)) != 1 else ''}"


def pct(x, dp=0):
    """Whole-percent fact (already 0-100) -> '63%'. None -> '—'."""
    v = _n(x)
    return '—' if v is None else f"{v:.{dp}f}%"


def ratio(x, dp=2):
    """A ratio like SPI/CPI -> '0.66'. None -> '—'."""
    v = _n(x)
    return '—' if v is None else f"{v:.{dp}f}"


def money(x):
    """Cost value -> '562,725,980'. None -> '—'."""
    v = _n(x)
    return '—' if v is None else f"{v:,.0f}"


def dates(F, fmt):
    """`fmt` filled with the forecast ({ff}) and baseline ({bf}) finish — or '' when either is unknown,
    so a sentence never reads 'finish None'."""
    ff, bf = F.get('forecast_finish'), F.get('baseline_finish')
    return fmt.format(ff=ff, bf=bf) if ff and bf else ''


def delay_phrase(F):
    """One plain clause describing where the finish stands. Uses the signed delay_days."""
    d = F.get('delay_days')
    if d is None:
        return "the finish milestone isn't derivable from this file"
    d = round(_n(d))
    if d > 0:
        tail = ''
        if F.get('baseline_finish') and F.get('forecast_finish'):
            tail = f" — the planned finish of {F['baseline_finish']} has moved to about {F['forecast_finish']}"
        return f"about **{wd(d)} behind** (~{weeks(d)} late to finish){tail}"
    if d < 0:
        return f"about **{wd(d)} of float to completion** — ahead of the deadline"
    return "**on the planned finish date**"


def spi_verdict(F):
    """Plain read of pace from SPI. Returns (word, sentence)."""
    p = F.get('pace_pct')
    if p is None:
        return ('unknown', "the progress rate versus plan isn't derivable in this update")
    if p >= 100:
        return ('at or ahead of plan', f"work is being earned at about **{p}%** of the planned rate (SPI ≈ {ratio(F.get('spi'))}) — on or ahead of the planned pace")
    if p >= 90:
        return ('slightly behind', f"work is being earned at about **{p}%** of the planned rate (SPI ≈ {ratio(F.get('spi'))}) — a little under plan")
    return ('behind', f"work is being earned at about **{p}%** of the planned rate (SPI ≈ {ratio(F.get('spi'))}) — materially under the planned pace")


def worst_line(F):
    """A sentence naming the discipline with the widest raw gap, or '' if none stands out."""
    w = F.get('widest_gap') or F.get('worst_discipline')
    if not w:
        return ''
    drv = main_driver(F)
    tail = (" — the most likely home of the delay." if not drv or drv.get('name') == w.get('name') else
            f"; by weight, though, **{drv.get('name')}** is what moves the finish.")
    return (f"The widest gap is in **{w.get('name')}** — about **{w.get('actual')}%** done against "
            f"**{w.get('planned')}%** planned by now (a {w.get('gap')}-point gap){tail}")


def cost_state(F):
    """Honest cost phrase. When actual cost equals earned value the cost is derived from progress, CPI is 1.00
    by construction, and the file cannot say whether the job is on budget."""
    cpi = F.get('cpi')
    if F.get('cost_derived'):
        return f"not measured in this file (CPI {ratio(cpi)} only because actual cost is derived from progress)"
    if cpi is None:
        return "not derivable from this file"
    if cpi < 0.98:
        return f"running over budget on the work done (CPI {ratio(cpi)})"
    if cpi > 1.02:
        return f"running under budget on the work done (CPI {ratio(cpi)})"
    return f"close to budget on the work done (CPI {ratio(cpi)})"


def main_driver(F):
    """The discipline actually dragging the project — the largest weight × gap, not the
    largest raw gap (a 1%-weight design line with a huge gap moves the finish far less than a
    95%-weight construction front with a moderate gap). Returns the discipline dict or None."""
    best, best_score = None, 0.0
    for d in (F.get('disciplines') or []):
        gap = _n(d.get('gap')) or 0
        wgt = _n(d.get('weight')) or 0
        if gap <= 0:
            continue
        score = gap * wgt
        if score > best_score:
            best, best_score = d, score
    return best


def driver_line(F):
    """A sentence naming the real driver of the shortfall (weighted), or '' if none."""
    d = main_driver(F)
    if not d:
        return ''
    return (f"The shortfall is being carried by **{d.get('name')}** (about {round((d.get('weight') or 0)*100)}% "
            f"of the project by weight): **{d.get('actual')}%** done against **{d.get('planned')}%** planned — "
            f"a {d.get('gap')}-point gap on the work front that moves the finish date the most.")


# ── what the re-read P6 file shows (F['net_*'] — see facts.add_network) ────────────
# The library answers use these so they say the same thing as the 15 merged answers: the chain that
# sets the finish, the late client inputs, whether commissioning is in the file. All '' when the file
# couldn't be read, so an answer falls back to the stored analysis.

def late_inputs(F):
    return list(F.get('net_late_inputs') or [])


def inputs_text(F, k=3):
    """'Layout Approval (+122 wd), Road Level (+114 wd) and 5 more' — the late, still-open client inputs."""
    late = late_inputs(F)
    names = [' '.join(str(x['name']).split()) + (f" ({x['slip_wd']:+d} wd)" if x.get('slip_wd') is not None else '')
             for x in late[:k]]
    more = len(late) - len(names)
    return ', '.join(names) + (f" and {more} more" if more > 0 else '')


def inputs_line(F):
    """'**7 client inputs** are late and still open — …' or ''."""
    n = len(late_inputs(F))
    if not n:
        return ''
    return f"**{n} client input{'s' if n != 1 else ''}** {'are' if n != 1 else 'is'} late and still open — {inputs_text(F)}."


def chain_facts(F):
    """(count, started, tf_min, tf_max) of the chain that sets the finish, or None without the file."""
    if not F.get('net_ok') or not F.get('net_chain_count'):
        return None
    return (F['net_chain_count'], F.get('net_chain_started') or 0, F.get('net_chain_tf_min'), F.get('net_chain_tf_max'))


def chain_line(F):
    """'The finish is set by a chain of **52 activities**, none of them started, at −59 to −64 wd of float.' or ''."""
    c = chain_facts(F)
    if not c:
        return ''
    n, started, lo, hi = c
    st = ("none of them started" if started == 0 else f"{started} of them started")
    fl = (f", at {lo:+d} to {hi:+d} wd of float" if lo is not None and hi is not None and lo != hi else
          f", at {lo:+d} wd of float" if lo is not None else '')
    return f"The finish is set by a chain of **{n} activities**, {st}{fl}."


def delay_source(F):
    """Where the delay figure comes from — said the same way in every answer."""
    return ("That figure is P6's own: the finish milestone's exported forecast date (after your F9) against its "
            "baseline, counted in working days — it agrees with the milestone's total float.")


def chain_name(F):
    """'the **52-activity chain** that sets the finish' or '' without the file."""
    c = chain_facts(F)
    return f"the **{c[0]}-activity chain** that sets the finish" if c else ''


def driving_note(F):
    """P6's driving-path count said honestly: a wide SET of activities tied to the finish date, not one line —
    with the actual finish chain named beside it when the file was read. '' when the count isn't stored."""
    dp = F.get('driving_path_count')
    if dp is None:
        return ''
    c = chain_facts(F)
    return (f"P6's driving-path flag marks about **{dp} activities** — everything tied to the finish date, a far "
            "wider set than one line of work"
            + (f"; the chain that actually sets the finish is **{c[0]} activities**, listed in the main answer" if c
               else "") + ".")


def cause_line(F):
    """The honest read of WHOSE delay it is — what the file shows on each side, and that one update can't
    split it. Never asserts a manpower / productivity / contractor cause the file can't prove."""
    parts = []
    c = chain_facts(F)
    if c and c[1] == 0:
        parts.append("the chain that sets the finish hasn't started yet — that reads as a **late start**, not slow "
                     "production inside the chain")
    if late_inputs(F):
        parts.append(f"{len(late_inputs(F))} client inputs are late and still open ({inputs_text(F)}) — "
                     "employer-side evidence")
    head = ("What the file shows: " + '; '.join(parts) + '. ') if parts else ''
    return (head + "One update can't prove whose delay it is — whether the start was held by client inputs or by "
            "the contractor's own mobilisation and resources needs a time-impact analysis and the site records.")


def has_history(F):
    """True only with two or more DIFFERENT updates (data dates) stored — re-imports of the same file don't count."""
    return len(F.get('history') or []) >= 2


# ── feature pointers (merged, in-progress, and honest gaps) ─────────────────────
# Keyed by the canonical feature name as it appears in each question's `grounds`.
# `open` = where to find it in the tool; used to route the user to the exact figure.
FEATURE = {
    'EVM': {'open': 'the EVM tab', 'does': 'Planned vs Earned Value, SPI/CPI and the delay to completion'},
    'Schedule Audit': {'open': 'the Schedule Audit', 'does': 'the DCMA-style logic checks with per-activity findings and two suggested fixes each'},
    'Schedule Health Review': {'open': 'the Schedule Health Review', 'does': 'the graded health scores (logic, float, critical path/CPLI)'},
    'Critical Path Analyzer': {'open': 'the Critical Path Analyzer', 'does': 'the longest/driving path and its total float across schedules'},
    'Out of Sequence': {'open': 'the Out-of-Sequence review', 'does': 'activities progressed against their logic, with corrections'},
    'Baseline Revision Comparison': {'open': 'the Baseline Revision Comparison', 'does': 'what changed between two baselines — dates, logic, durations, calendars, manpower'},
    'Update Analysis': {'open': 'Update Analysis', 'does': 'this update measured against the baseline'},
    'Update vs Update': {'open': 'Update vs Update', 'does': 'this period measured against the previous update'},
    'Consultant Review': {'open': 'the Consultant Review', 'does': 'the forensic, but-for review of a progressed schedule'},
    'What-if / scenario engine': {'open': 'the What-if', 'does': 'an instant estimate of a change, then the exact P6 figure via a build → F9 round-trip'},
    'Calendar Audit': {'open': 'the Calendar Audit', 'does': 'working-day patterns, calendar comparison and the weather effect on forecast finish'},
    'Weather Impact': {'open': "the Calendar Audit's weather tab", 'does': 'the bad-weather effect on the forecast finish for the site type'},
    'Productivity & Resource Intelligence': {'open': 'Productivity & Resource Intelligence', 'does': 'productivity norms and man-hours by component, read against the P6 resources'},
    'Duration & Resource Calculation': {'open': 'Duration & Resource Calculation', 'does': 'quantity → duration → typed resources for a resource-loaded plan'},
    'Constructability Review': {'open': 'the Constructability / Knowledge Base', 'does': 'the construction sequence, WBS and missing-activity check for the project type'},
    'Construction Knowledge Base': {'open': 'the Knowledge Base', 'does': 'the reference sequence and suggested WBS for the project type'},
    'Claims / TIA reference': {'open': "the Copilot's Time-Impact Analysis", 'does': 'the finish-slip decomposition and the delay-method reference (AACE 29R-03 / FIDIC)'},
    'EOT Claim Builder': {'open': 'the EOT Claim Builder (being built)', 'does': 'a FIDIC EOT claim from the impacted schedule — in progress'},
    'Reporting Studio': {'open': 'the Reporting Studio', 'does': 'a composed Word/PDF/Excel report of any results you pick'},
    'Power BI live dashboards': {'open': 'the Power BI export (being built)', 'does': 'live portfolio dashboards — in progress'},
    'Copilot': {'open': 'the Expert-Analysis questions in this chat', 'does': 'the offline TIA, what-if, manager briefing and claims read'},
}

# Longest names first so multi-word features match before their shorter substrings.
_FEATURE_KEYS = sorted(FEATURE.keys(), key=len, reverse=True)


def features_in(grounds):
    """Canonical feature names named in a question's `grounds` string, in order."""
    if not grounds:
        return []
    g = str(grounds)
    found = []
    for k in _FEATURE_KEYS:
        if k.lower() in g.lower() and k not in found:
            found.append(k)
    return found


def go_deeper(grounds, lead="For the exact figure"):
    """An advice line pointing to the feature(s) that carry the detail for this question.
    Returns '' when the grounds are a pure GAP with no feature to point at."""
    feats = [f for f in features_in(grounds)]
    if not feats:
        return ''
    first = feats[0]
    f = FEATURE[first]
    line = f"{lead}, open **{f['open']}** — it gives you {f['does']}."
    if len(feats) > 1 and feats[1] in FEATURE:
        f2 = FEATURE[feats[1]]
        line += f" Cross-check in **{f2['open']}**."
    return line


def gap_note(grounds):
    """For a 'gap'/'in-progress' question: the honest 'the tool doesn't do this (yet)'
    sentence, taken from the GAP text in `grounds` when present."""
    g = str(grounds or '')
    if 'GAP' in g:
        # grounds like 'GAP — no contract-date ingest, correspondence, or monetary model'
        txt = g.split('GAP', 1)[1].lstrip(' —-–:').strip()
        return (f"The tool doesn't compute this from the schedule: {txt}. "
                "I can still give you the planning read below.") if txt else \
               "The tool doesn't compute this from the schedule yet — here's the planning read."
    return ''
