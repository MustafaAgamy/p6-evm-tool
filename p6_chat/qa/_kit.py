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
    """A sentence naming the worst-performing discipline, or '' if none stands out."""
    w = F.get('worst_discipline')
    if not w:
        return ''
    return (f"The widest gap is in **{w.get('name')}** — about **{w.get('actual')}%** done against "
            f"**{w.get('planned')}%** planned by now (a {w.get('gap')}-point gap), the most likely home of the delay.")


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
