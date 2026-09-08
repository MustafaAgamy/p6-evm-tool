"""Overview provider — an honest executive header for the Reporting Studio.

This provider invents NOTHING. It only re-presents statuses/severities that other
features have ALREADY produced and stored:

  * the per-domain status chips read whatever band a feature assigned itself — EVM
    carries no pass/fail band, so its chip is always ``'neutral'``; Schedule quality
    reads the Schedule Health roll-up's OWN verdict (``ctx.audit['health']``);
    Weather carries no tone of its own, so it is ``'neutral'`` too; Buildability
    isn't in ``ctx`` cheaply, so it reads "Not run".
  * the "What needs attention" register aggregates each audit module's OWN findings,
    taking the module's OWN worst finding-severity — never a threshold derived here.

Where a domain exposes no status, the chip is ``tone='neutral'`` with headline
"Not run" — never a guessed green/amber/red. The single overall verdict is
DEFERRED (its rule is the planner's), so this provider always passes
``verdict=None`` to :func:`payloads.status_header`.
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special.providers._util import _SEV_MAP   # reuse the canonical severity map
from p6_special.registry import Item

FEATURE = 'overview'
FEATURE_TITLE = 'Overview'

# Order high→medium→low→info (the payload vocabulary's four severities).
_SEV_RANK = {'high': 0, 'medium': 1, 'low': 2, 'info': 3}

# The Schedule Health roll-up assigns its OWN submission verdict (p6_audit.health
# `_verdict`). We only translate that existing band to a chip tone — no new rule.
_VERDICT_TONE = {
    'Ready to submit':      'good',
    'Acceptable to submit': 'warn',
    'Not ready to submit':  'bad',
    'Blocked':              'bad',
    'Not computed':         'neutral',
}

_NOT_RUN = 'Not run'


# ── status header ────────────────────────────────────────────────────────────
def _evm_chip(ctx):
    """EVM domain chip, or None if there is no stored EVM result at all.

    EVM has no stored pass/fail band in this tool, so the tone is ALWAYS neutral —
    we never colour SPI/CPI good or bad here (that would be an invented band)."""
    e = ctx.evm
    if not e:
        return None
    spi, cpi = e.get('spi'), e.get('cpi')
    if spi is not None or cpi is not None:
        headline = f'SPI {fmt.ratio(spi)} · CPI {fmt.ratio(cpi)}'
    else:
        ap = e.get('overall_actual_pct')
        headline = f'Progress {fmt.pct01(ap)}' if ap is not None else 'Imported'
    return {'domain': 'EVM', 'tone': 'neutral', 'headline': headline}


def _schedule_chip(ctx):
    """Schedule-quality chip from the Schedule Health roll-up's OWN score + verdict.

    The roll-up (ctx.audit['health']) already carries a DCMA-anchored score and a
    submission verdict the audit feature assigns itself — we map that verdict to a
    tone. If a score exists but no recognised verdict band, the score shows with a
    neutral tone. If nothing was run, the chip reads "Not run" (neutral)."""
    health = (ctx.audit or {}).get('health') or {}
    score = health.get('score')
    verdict = health.get('verdict')
    if not ctx.audit or (score is None and not verdict):
        return {'domain': 'Schedule quality', 'tone': 'neutral', 'headline': _NOT_RUN}
    if score is not None:
        headline = f'{fmt.num(score)}%'
        tone = _VERDICT_TONE.get(verdict, 'neutral')
    else:
        # A verdict but no numeric score (e.g. Blocked / Not computed) — show the
        # feature's own words, coloured by its own band.
        headline = verdict
        tone = _VERDICT_TONE.get(verdict, 'neutral')
    return {'domain': 'Schedule quality', 'tone': tone, 'headline': headline}


def _weather_chip(ctx):
    """Weather chip. The weather estimate carries no tone/band of its own, so the
    chip is neutral whether or not there is a slip. Absent → "Not run"."""
    w = ctx.weather
    if not isinstance(w, dict):
        return {'domain': 'Weather', 'tone': 'neutral', 'headline': _NOT_RUN}
    net = w.get('net_finish_delay')
    if isinstance(net, (int, float)):
        headline = f'+{int(round(net))} wd'
    else:
        headline = 'Estimated'
    return {'domain': 'Weather', 'tone': 'neutral', 'headline': headline}


def _buildability_chip(ctx):
    """Constructability requires a run and is not in ctx cheaply → always Not run."""
    return {'domain': 'Buildability', 'tone': 'neutral', 'headline': _NOT_RUN}


def _status_header(ctx):
    domains = []
    evm = _evm_chip(ctx)
    if evm:                       # skip only when the EVM object is entirely absent
        domains.append(evm)
    domains.append(_schedule_chip(ctx))
    domains.append(_weather_chip(ctx))
    domains.append(_buildability_chip(ctx))
    # verdict is DEFERRED — its rule belongs to the planner. Always None.
    return P.status_header(domains, verdict=None)


def _header_avail(ctx):
    return 'ready' if ctx.evm else 'no_data'


# ── what needs attention ───────────────────────────────────────────────────
def _worst_severity(findings):
    """The module's OWN worst finding-severity, mapped to the payload vocabulary.
    Returns None when no finding carries a severity (that module has no existing
    classification to re-present, so it is omitted — never assigned a guess)."""
    ranked = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        raw = f.get('severity')
        if not raw:
            continue
        sev = _SEV_MAP.get(str(raw).lower())
        if sev:
            ranked.append(sev)
    if not ranked:
        return None
    return min(ranked, key=lambda s: _SEV_RANK[s])


def _attention(ctx):
    audit = ctx.audit or {}
    modules = audit.get('modules') or {}
    order = audit.get('module_order') or list(modules.keys())

    flagged = []   # (rank, -count, item)
    for key in order:
        mod = modules.get(key) or {}
        findings = mod.get('findings') or []
        if not findings:
            continue
        sev = _worst_severity(findings)
        if sev is None:
            # No per-finding severity classification (e.g. the CPLI driving path is a
            # route, not a defect list) → nothing the feature marked as a problem.
            continue
        count = len(findings)
        name = mod.get('name') or key
        title = f"{count} finding{'' if count == 1 else 's'} in {name}"
        flagged.append((_SEV_RANK[sev], -count,
                        {'severity': sev, 'title': title,
                         'detail': f'Schedule Audit · {name}'}))

    # Weather slip: the estimate gives a net delay (a count) with no severity band,
    # but the feature itself marks a positive net delay as a slip to the finish —
    # so we surface it at 'medium' (never a severity derived from the day count).
    w = ctx.weather
    if isinstance(w, dict):
        net = w.get('net_finish_delay')
        if isinstance(net, (int, float)) and net > 0:
            n = int(round(net))
            flagged.append((_SEV_RANK['medium'], -n,
                            {'severity': 'medium',
                             'title': f"+{n} working day{'' if n == 1 else 's'} weather slip to finish",
                             'detail': 'Calendar & Weather · Forecast'}))

    flagged.sort(key=lambda t: (t[0], t[1]))
    items = [t[2] for t in flagged]

    overflow = 0
    if len(items) > 8:
        overflow = len(items) - 8
        items = items[:8]
        items.append({'severity': 'info',
                      'title': f'+{overflow} more in the report',
                      'detail': 'Schedule Audit'})
    return P.findings(items, empty='Nothing flagged this update.')


def _attention_avail(ctx):
    return 'ready' if ctx.audit else 'no_data'


# ── provider ─────────────────────────────────────────────────────────────────
def provide(ctx):
    return [
        Item('overview:status_header', FEATURE, FEATURE_TITLE, 'Status header',
             'summary', _status_header, _header_avail),
        Item('overview:attention', FEATURE, FEATURE_TITLE, 'What needs attention',
             'findings', _attention, _attention_avail),
    ]
