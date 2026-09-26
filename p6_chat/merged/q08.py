"""q08 — Cost & EVM: where do we stand on money, and where will it land?

Covers: earned vs planned and the two variances (SV / CV), over/under by discipline and the value-gap split,
the over-claim check, whether the schedule is cost-loaded (and how PV is re-derived), the cumulative S-curve and
% spent vs % complete, work fronts burning value, the exportable one-page dashboard, EAC / ETC / VAC / TCPI,
the CPI trend, prolongation and cashflow, and a time-based (earned-schedule) read — for ANY project.

Every name and number comes from F (DB facts) and N (the network re-read). The budget (BAC) is not stored with
the chat facts, so it is IMPLIED: PV and EV are one budget times the budgeted lines' planned and earned %, and
the builder only quotes a BAC when both reconcile to the same figure within the ±0.5-point rounding.
"""
import re
from datetime import datetime

from . import _kit2 as K

# words that don't identify a scope (used to link a lagging line to the client input that gates it)
_GENERIC = {'phase', 'design', 'engineering', 'works', 'work', 'procurement', 'construction', 'and', 'the', 'of',
            'for', 'to', 'from', 'i', 'ii', 'iii', 'iv', 'package', 'detailed', 'schematic', 'general', 'civil',
            'installation', 'client', 'employer', 'start', 'delivery', 'approval', 'by', 'in', 'on', 'with'}


# ── small helpers ────────────────────────────────────────────────────────────────

def _n(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _m(v, signed=False, approx=False):
    """Compact, currency-neutral amount: 562.7M / 2.33M / 74k / 950 (unicode minus for negatives).
    approx=True rounds to 3 significant figures for implied figures (≈ 919M, not 918.6M)."""
    v = _n(v)
    if v is None:
        return '—'
    a = abs(v)
    if approx and 1e8 <= a < 1e9:
        t = f"{a / 1e6:.0f}M"
    elif a >= 1e9:
        t = f"{a / 1e9:.2f}bn"
    elif a >= 1e7:
        t = f"{a / 1e6:.1f}M"
    elif a >= 1e6:
        t = f"{a / 1e6:.2f}M"
    elif a >= 1e4:
        t = f"{a / 1e3:.0f}k"
    elif a >= 1e3:
        t = f"{a / 1e3:.1f}k"
    else:
        t = f"{a:.0f}"
    if t in ('0', '0k', '0.0k'):
        return '0'
    return ('−' if v < 0 else ('+' if signed and v > 0 else '')) + t


def _pctg(x):
    """Share-of-gap percent: 99.25% / 0.74% / 42.1%."""
    x = _n(x) or 0.0
    if x == 0:
        return '0%'
    return f"{x:.2f}%" if (x < 1 or x > 99) else f"{x:.1f}%"


def _frac_words(x):
    """0.342 -> 'about a third (34%)'."""
    for val, w in ((0.25, 'a quarter'), (1 / 3, 'a third'), (0.5, 'half'), (2 / 3, 'two-thirds'), (0.75, 'three-quarters')):
        if abs(x - val) <= 0.025:
            return f"about {w} ({round(x * 100)}%)"
    return f"{round(x * 100)}%"


def _sd(d):
    """Short signed delay: '+60 wd' / '12 wd ahead' / 'on the date'."""
    if d is None:
        return None
    d = round(d)
    return f"+{d} wd" if d > 0 else (f"{abs(d)} wd ahead" if d < 0 else 'on the date')


def _date(s):
    if not s:
        return None
    s = str(s)
    for fmt, cut in (('%d-%b-%Y', None), ('%Y-%m-%d %H:%M:%S', 19), ('%Y-%m-%d', 10)):
        try:
            return datetime.strptime(s[:cut] if cut else s, fmt)
        except ValueError:
            continue
    return None


def _fmt(dt):
    return dt.strftime('%d-%b-%Y') if dt else None


def _nm(s, limit=64):
    """A P6 name tidied for prose: collapsed whitespace, long names cut at a word boundary."""
    s = ' '.join(str(s or '').split())
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(' ', 1)[0].rstrip(' ,;&-') + '…'


def _i(v):
    """Signed whole number with a real minus sign: +122 / −48 / 0."""
    v = round(_n(v) or 0)
    return f"+{v}" if v > 0 else (f"−{abs(v)}" if v < 0 else '0')


def _poss(s):
    return s + ("'" if s.endswith('s') else "'s")


def _wk(d):
    """'12-week' (adjective form)."""
    return f"{max(1, round(abs(_n(d) or 0) / 5))}-week"


def _names(xs):
    xs = [x for x in xs if x]
    if not xs:
        return ''
    return xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + ' and ' + xs[-1]


def _finish_dates(F, N):
    """(baseline finish, forecast finish) from F, else the finish milestone in N, else the CPLI audit."""
    fin = ((N or {}).get('finish_milestone') or {}) if (N or {}).get('ok') else {}
    bl = F.get('baseline_finish') or fin.get('baseline_finish')
    fc = F.get('forecast_finish') or fin.get('finish')
    if not fc:
        ck = ((F.get('audit') or {}).get('cpli') or {}).get('kpis') or {}
        fc = _fmt(_date(ck.get('finish_date')))
    return bl, fc


def _interval(val, p, tol=0.5):
    """Budget interval implied by val = BAC x p% with p known to +-tol points. (lo, hi) or None."""
    if val is None or p is None or p + tol <= 0:
        return None
    lo = val / ((p + tol) / 100.0)
    hi = val / ((p - tol) / 100.0) if p - tol > 0 else float('inf')
    return lo, hi


def implied_bac(F):
    """Which progress lines carry the budget, and the budget itself, from PV/EV and the lines' %.

    PV = BAC x (budget-weighted planned % of the costed lines); EV likewise with earned %. The tool's default
    weights give costed lines 95% by cost and spread 5% equally over unbudgeted design/procurement lines, so
    the candidate costed set is 'everything except the equal smallest-weight group', then 'every line'. A
    candidate is accepted only if PV and EV imply the same BAC within the +-0.5-point rounding of the stored %.
    Returns {bac, lo, hi, costed, uncosted, p, a} or None (can't be pinned)."""
    pv, ev = _n(F.get('pv')), _n(F.get('ev'))
    ds = [d for d in (F.get('disciplines') or []) if (_n(d.get('weight')) or 0) > 0
          and d.get('planned') is not None and d.get('actual') is not None]
    if not pv or ev is None or not ds:
        return None
    wmin = min(_n(d['weight']) for d in ds)
    small = [d for d in ds if abs(_n(d['weight']) - wmin) < 1e-9]
    cands = []
    if len(small) < len(ds) and sum(_n(d['weight']) for d in small) <= 0.051:
        cands.append(([d for d in ds if d not in small], small))
    cands.append((ds, []))
    for S, U in cands:
        W = sum(_n(d['weight']) for d in S)
        p = sum(_n(d['weight']) * _n(d['planned']) for d in S) / W
        a = sum(_n(d['weight']) * _n(d['actual']) for d in S) / W
        p_lo, p_hi, a_lo, a_hi = p - 0.5, p + 0.5, a - 0.5, a + 0.5
        # tighten with the overall % (weights of the unbudgeted lines are known)
        op, oa = _n(F.get('planned_pct')), _n(F.get('actual_pct'))
        wu = sum(_n(d['weight']) for d in U)
        if U and op is not None and oa is not None and abs(W + wu - 1) < 0.02:
            tol = (0.5 + 0.5 * wu) / W
            po = (op - sum(_n(d['weight']) * _n(d['planned']) for d in U)) / W
            ao = (oa - sum(_n(d['weight']) * _n(d['actual']) for d in U)) / W
            if max(p_lo, po - tol) <= min(p_hi, po + tol):
                p_lo, p_hi = max(p_lo, po - tol), min(p_hi, po + tol)
            if max(a_lo, ao - tol) <= min(a_hi, ao + tol):
                a_lo, a_hi = max(a_lo, ao - tol), min(a_hi, ao + tol)
        if p_hi <= 0:
            continue
        ip = (pv / (p_hi / 100.0), pv / (p_lo / 100.0) if p_lo > 0 else float('inf'))
        if ev > 0:
            if a_hi <= 0:
                continue
            ie = (ev / (a_hi / 100.0), ev / (a_lo / 100.0) if a_lo > 0 else float('inf'))
        else:
            ie = (0.0, float('inf')) if a_lo <= 0 else None
            if ie is None:
                continue
        lo, hi = max(ip[0], ie[0]), min(ip[1], ie[1])
        if lo <= hi and hi != float('inf'):
            bac = (lo + hi) / 2
            return {'bac': bac, 'lo': lo, 'hi': hi, 'costed': [d['name'] for d in S],
                    'uncosted': [d['name'] for d in U], 'p': pv / bac * 100, 'a': ev / bac * 100}
    return None


def _tokens(s):
    return {t for t in re.findall(r'[a-z0-9]+', (s or '').lower()) if len(t) >= 3 and t not in _GENERIC}


def gating_input(disc_name, N):
    """A late, open client input whose name shares a distinctive word with the discipline (or None)."""
    toks = _tokens(disc_name)
    if not toks or not (N or {}).get('ok'):
        return None
    for x in N.get('client_inputs_late_open') or []:
        if toks & _tokens(x.get('name')):
            return x
    return None


def _earned_schedule(F):
    """Earned-schedule date from stored update history: when the baseline planned today's earned %.
    Returns (es_datetime, n_points) or (None, n_points)."""
    pts = {}
    for h in F.get('history') or []:
        dt, p = _date(h.get('date')), _n(h.get('planned'))
        if dt and p is not None:
            pts[dt] = p if p <= 1.5 else p / 100.0
    pts = sorted(pts.items())
    a = (_n(F.get('actual_pct')) or 0) / 100.0
    if len(pts) < 2 or not a:
        return None, len(pts)
    for (d0, p0), (d1, p1) in zip(pts, pts[1:]):
        if p0 <= a <= p1 and p1 > p0:
            return d0 + (d1 - d0) * ((a - p0) / (p1 - p0)), len(pts)
    return None, len(pts)


# ── the answer ───────────────────────────────────────────────────────────────────

def build(F, N, role):
    nok = bool(N and N.get('ok'))
    pv, ev, ac = _n(F.get('pv')), _n(F.get('ev')), _n(F.get('ac'))
    cpi, spi = _n(F.get('cpi')), _n(F.get('spi'))
    d = F.get('delay_days')
    behind, ahead = (d or 0) > 0, (d or 0) < 0
    derived = bool(F.get('cost_derived'))
    dd = F.get('data_date')
    P, A_ = F.get('planned_pct'), F.get('actual_pct')
    bl, fc = _finish_dates(F, N)
    drv = K.main_driver(F)
    thinking = []

    if not pv:
        return _no_budget(F, N, bl, fc, drv)

    B = implied_bac(F)
    bac = B['bac'] if B else None
    sv = (ev - pv) if ev is not None else None
    cv = (ev - ac) if (ev is not None and ac is not None) else None
    costed = _names(B['costed']) if B else ''
    single = bool(B and len(B['costed']) == 1 and B['uncosted'])
    p_c, a_c = (round(B['p']), round(B['a'])) if B else (P, A_)
    vg = F.get('value_gap') if isinstance(F.get('value_gap'), dict) else {}
    groups = [g for g in (vg.get('groups') or []) if isinstance(g, dict)]
    gapg = sorted([g for g in groups if (_n(g.get('gap')) or 0) > 0], key=lambda g: -(_n(g.get('gap')) or 0))
    top = gapg[0] if gapg else None
    dim = vg.get('dimension') or 'activity code'
    ds = sorted(F.get('disciplines') or [], key=lambda x: -(_n(x.get('weight')) or 0))
    ck = ((F.get('audit') or {}).get('cpli') or {}).get('kpis') or {}
    cpli = _n(ck.get('cpli')) if ck.get('cpli_computable', True) else None
    chain = (N.get('chain') or []) if nok else []
    head = chain[0] if chain else None
    dd_dt = _date(dd)
    head_overdue = bool(head and head.get('baseline_finish') and dd_dt and _date(head['baseline_finish'])
                        and _date(head['baseline_finish']) < dd_dt and not head.get('pct'))
    late_ci = sorted([x for x in ((N.get('client_inputs_late_open') or []) if nok else [])
                      if x.get('tf') is not None and x['tf'] < 0], key=lambda x: x['tf'])
    eac = (bac / cpi) if (bac and cpi) else None
    etc = (eac - ac) if (eac is not None and ac is not None) else None
    wu = [d_ for d_ in ds if B and d_['name'] in B['uncosted']]
    wu_pct = round((_n(wu[0]['weight']) or 0) * 100) if wu else None

    thinking.append((f"Reconciled PV ({_m(pv)}) and EV ({_m(ev)}) against each line's planned/earned % — the budget sits on "
                     f"{costed} (BAC ≈ {_m(bac, approx=True)})") if B else
                    f"Tried to reconcile PV ({_m(pv)}) and EV ({_m(ev)}) to one budget across {len(ds)} progress lines — they don't")
    thinking.append(f"Compared actual cost with earned value — {'equal to the unit, so cost is derived from progress' if derived else 'loaded separately, so CPI is a real signal'}")

    # ── verdict ─────────────────────────────────────────────────────────────────
    if sv is not None and sv < 0:
        where = (f", {_pctg(top.get('pct_of_gap'))} of that gap in {top['code']}" if top else
                 (f", all of it on {costed}, the only budgeted line" if single else ''))
        head_txt = f"Behind plan in value: {_m(-sv)} of planned value is unearned{where}."
    elif sv is not None and sv > 0:
        head_txt = f"Ahead of plan in value: {_m(sv)} more earned than planned by the {dd} data date."
    else:
        head_txt = "Earned value is on the planned line."
    mixed = bool(B is None and sv and P is not None and A_ is not None and (A_ - P) * sv < 0)
    cpi_off = bool(cpi is not None and ev and ac and abs(ev / ac - cpi) > 0.02)
    if mixed or (B is None and cpi_off):
        head_txt = (f"The money and the progress don't tell the same story: {_m(abs(sv))} of value "
                    f"{'unearned against plan' if sv < 0 else 'earned ahead of plan'}, yet progress reads {K.pct(A_)} "
                    f"against {K.pct(P)} planned" + (f" and the finish is {_sd(d)}" if d is not None else '')
                    + (" — and the stored CPI doesn't match EV ÷ AC" if cpi_off else '')
                    + ". Check the EVM weights and overrides before quoting a cost position.")
    elif derived:
        when = (f" ({_sd(d)} to {fc})" if (d is not None and fc) else (f" ({_sd(d)})" if d is not None else ''))
        head_txt += f" CPI {K.ratio(cpi)} only mirrors progress, so forecast the landing in time{when}, not in money."
    elif cpi is not None:
        word = 'over' if cpi < 0.98 else ('under' if cpi > 1.02 else 'close to')
        head_txt += (f" CPI {K.ratio(cpi)}: {word} budget on the work done"
                     + (f", heading for about {_m(eac, approx=True)} against a {_m(bac, approx=True)} budget" if eac else '') + '.')

    pills = [K.pill(f"SV {_m(sv)} {'behind' if sv < 0 else 'ahead of'} plan", 'danger' if sv < 0 else 'success') if sv else None,
             K.pill(f"{top['code']} = {_pctg(top.get('pct_of_gap'))} of the gap", 'danger') if top else
             (K.pill(f"{B['costed'][0]} = all of the gap", 'danger') if single and (sv or 0) < 0 else None),
             K.pill(f"CV {_m(cv)} · CPI {K.ratio(cpi)} = progress mirror", 'warning') if derived else
             K.pill(f"CV {_m(cv)} · CPI {K.ratio(cpi)}", 'warning' if (cpi or 1) < 0.98 else 'success'),
             K.pill(f"BAC ≈ {_m(bac, approx=True)}" + (f", {costed} only" if B['uncosted'] else ''), 'neutral') if B else None,
             K.pill(f"planned {p_c}% vs earned {a_c}% (cost)", 'danger' if a_c < p_c else 'success') if B else None,
             K.pill('EAC = BAC; ignores the slip', 'warning') if (derived and behind and eac) else
             (K.pill(f"EAC ≈ {_m(eac, approx=True)}", 'warning' if (cpi or 1) < 0.98 else 'neutral') if (eac and not derived) else None),
             K.pill(f"read time: {_sd(d)}", 'accent') if d is not None else None,
             K.pill('one-page Excel export', 'success')]

    # ── 1. earned vs planned ─────────────────────────────────────────────────────
    gap_home = (f", and {_pctg(top.get('pct_of_gap'))} of it sits in {top['code']}" if top else
                (f", and all of it sits on {costed}" if single else ''))
    if derived and sv is not None and sv < 0:
        lead = (f"**You're {_m(-sv)} of planned value behind, and cost reads level with earned value — but that's an "
                f"artefact: actual cost in this file moves in lock-step with progress. The real variance is schedule{gap_home}.**")
    elif sv is not None and cv is not None:
        level = abs(cv) <= 0.005 * max(abs(ev or 0), 1.0)
        lead = (f"**You're {_m(abs(sv))} of planned value {'behind' if sv < 0 else 'ahead'} and "
                + ("level on cost for the work done (CV ≈ 0).**" if level else
                   f"{_m(abs(cv))} {'over' if cv < 0 else 'under'} cost on the work done (CPI {K.ratio(cpi)}).**"))
    else:
        lead = ''
    frac = ((pv - ev) / pv) if (pv and ev is not None) else None
    p2 = (f"Planned value to the {dd} data date is {_m(pv)}; you've earned {_m(ev)}. That's a Schedule Variance "
          f"(SV = EV − PV) of {_m(sv)}, so "
          + (f"{_frac_words(frac)} of the value planned by now hasn't been earned." if frac and frac > 0 else
             f"you've earned {round(-frac * 100) if frac else 0}% more than planned by now.")
          + (f" Cost Variance (CV = EV − AC) is {_m(cv)}" + (f", because actual cost is also {_m(ac)}." if derived else
                                                            f": actual cost is {_m(ac)}.") if cv is not None else ''))
    if B and B['uncosted']:
        p3 = (f"One thing to know before quoting any of these: only {costed} carries budget in this file (BAC ≈ {_m(bac, approx=True)}). "
              f"{_names(B['uncosted'])} carry none. They count toward the progress % and the SPI, but not toward the money.")
        if derived and (sv or 0) < 0:
            p3 += (f" Read together, {_m(sv)} schedule and {_m(cv)} cost describe a time problem with a budget-friendly "
                   f"mask. Don't let CPI {K.ratio(cpi)} reassure the room while {_m(-sv)} of planned work sits unearned.")
    elif B:
        p3 = (f"The budget (BAC ≈ {_m(bac, approx=True)}) is spread across every progress line in proportion to its weight, so the "
              "money and the progress % tell the same story.")
    else:
        p3 = ("I can't pin the budget (BAC) from the stored numbers: PV and EV don't reconcile to one set of progress "
              "percentages" + (" — EV sits below PV while progress reads ahead of plan" if mixed and sv < 0 else
                               (" — EV sits above PV while progress reads behind plan" if mixed else ''))
              + ". Check the category weights and any progress overrides on the EVM tab before quoting a budget figure.")
    if cpi_off:
        p3 += (f" The stored CPI ({K.ratio(cpi)}) also doesn't match EV ÷ AC ({K.ratio(ev / ac)}); re-import the file "
               "before quoting either.")
    s1 = K.sec('Earned vs planned, and the two variances in cost terms', lead, p2, p3, K.network_note(N))

    # ── 2. over / under by discipline ────────────────────────────────────────────
    if derived:
        o1 = ("Over or under budget by discipline can't be read from this file: actual cost equals earned value to the "
              "unit, the signature of cost generated from progress, so every line's CV is 0 too.")
    else:
        o1 = (f"The file gives cost performance for the whole job (CPI {K.ratio(cpi)}), not a CPI per line, so over/under "
              "by discipline needs the per-category actual cost on the EVM tab.")
    if top:
        tot_pv = sum(_n(g.get('pv')) or 0 for g in groups)
        o1 += (f" What can be read is who is behind plan in value, and that is "
               f"{'almost entirely' if (_n(top.get('pct_of_gap')) or 0) >= 90 else 'led by'} {top['code']} (table).")
        if pv and abs(tot_pv - pv) <= 0.005 * pv:
            o1 += f" The file's {dim} code splits the whole {_m(pv)} PV with nothing left over, so this split covers all the money."
    elif B:
        o1 += (" What can be read is who is behind plan in value" +
               (f": all of it sits on {costed}, the only budgeted line." if single else ", line by line (table)."))
    done, parts = [], []
    for x in ds:
        if (x.get('actual') or 0) >= 100 and (x.get('planned') or 0) >= 100:
            done.append(x['name'])
            continue
        w = round((_n(x.get('weight')) or 0) * 100)
        parts.append(f"{x['name']}{f' ({w}% weight)' if (drv and x['name'] == drv['name']) or w >= 30 else ''} at "
                     f"{x.get('actual')}% against {x.get('planned')}%")
    o2 = ''
    if parts:
        o2 = ("On progress, not money, the discipline picture is: " + '; '.join(parts)
              + (f"; {_names(done)} complete." if done else '.'))
    big_uncosted = [x for x in ds if B and x['name'] in B['uncosted'] and (x.get('gap') or 0) >= 20]
    if big_uncosted:
        o2 += (f" The gaps on {_names([x['name'] for x in big_uncosted])} look alarming but carry no budget here, so "
               "they are progress problems, not cost problems.")
    suspect = None
    for x in sorted(ds, key=lambda x: -(x.get('gap') or 0)):
        if (x.get('gap') or 0) >= 20:
            ci = gating_input(x['name'], N)
            if ci:
                suspect = (x, ci)
                break
    if suspect:
        x, ci = suspect
        o2 += (f" {x['name']} at {x.get('actual')}% has an obvious suspect: the client input that gates it, "
               f"'{_nm(ci['name'])}' ({ci['id']}), is {ci['slip_wd']} wd late and still open. Confirm the logic tie in "
               "P6 before saying so in writing.")
    if top:
        rows = [[g['code'], _m(g.get('pv')), _m(g.get('ev')), _m(g.get('gap')), _pctg(g.get('pct_of_gap'))] for g in groups]
        rows.append(['Total', _m(pv), _m(ev), _m(vg.get('total_gap') if vg.get('total_gap') is not None else (pv - ev)), '100%'])
        zero = [g['code'] for g in groups if not (_n(g.get('pv')) or 0)]
        t2 = K.tbl([dim, 'PV to date', 'EV', 'Gap (PV − EV)', 'Share of gap'], rows,
                   f"Real, from the file's {dim} code. These are behind-plan gaps, not overspends."
                   + (f" {_names(zero)} show zero planned value to date: either their work is planned after {dd} or it "
                      "carries no budget, and this read can't separate the two." if zero else ''))
    else:
        t2 = K.tbl(['Discipline', 'Weight', 'Carries budget', 'Done / planned', 'Gap (pts)'],
                   [[x['name'] + (' (driver)' if drv and x['name'] == drv['name'] else ''),
                     f"{round((_n(x.get('weight')) or 0) * 100)}%",
                     ('yes' if x['name'] in B['costed'] else 'no') if B else '—',
                     f"{x.get('actual')}% / {x.get('planned')}%",
                     x.get('gap') if (x.get('gap') is None or x['gap'] >= 0) else _i(x['gap'])] for x in ds],
                   "Progress by line from the stored EVM result; 'carries budget' is implied from PV and EV. The split of "
                   "the value gap by an activity code wasn't stored with this update — re-import the file to get it.")
    s2 = K.sec('Over / under budget by discipline', o1, o2, table=t2)
    thinking.append(f"Split the {_m(vg.get('total_gap') or (pv - ev))} value gap across {len(groups)} {dim} codes" if top
                    else f"Weighed the {len(ds)} disciplines' progress gaps against where the budget sits")

    # ── 3. over-claiming ─────────────────────────────────────────────────────────
    if derived:
        c1 = (f"There's no over-claim signal in the cost data, and there can't be. AC equals EV to the unit "
              f"({K.money(ac)} both). That is the signature of P6 calculating actual cost from % complete rather than from "
              "booked site costs. When actual cost is generated from progress, EV can never exceed AC, so a cost-based "
              "over-claim test has nothing to test.")
    elif ev is not None and ac is not None and abs(ev - ac) <= 0.005 * max(ev, 1.0):
        c1 = ("EV and AC are level (CV ≈ 0), so the cost data shows no over-claim: nothing has been earned ahead of the "
              "cost booked against it.")
    elif ev is not None and ac is not None and ev > ac:
        c1 = (f"EV runs {_m(ev - ac)} ahead of AC (CPI {K.ratio(cpi)}). That is either genuine efficiency or progress "
              "claimed ahead of the cost that should come with it — the file alone can't tell which, so test the "
              "biggest-earning activities against measured quantities.")
    else:
        c1 = (f"EV sits {_m((ac or 0) - (ev or 0))} below AC (CPI {K.ratio(cpi)}): the work done has cost more than it "
              "earned — the opposite of an over-claim.")
    oos, oos_pct = F.get('oos_count'), F.get('oos_pct')
    mpk = None
    if oos is not None:
        concl = (((F.get('audit') or {}).get('out_of_sequence') or {}).get('kpis') or {}).get('executive_conclusion') or ''
        mpk = re.search(r'concentrated in the (.+?) package \((\d+) of (\d+)', concl)
        c2 = (f"The nearest proxy the file offers is out-of-sequence progress, meaning progress recorded ahead of its "
              f"logic. There are {oos} such activities ({K.pct(oos_pct, 1)})"
              + (f", {mpk.group(2)} of them in the {mpk.group(1)} package" if mpk else '')
              + (f" and {F.get('critical_oos')} on the critical path" if F.get('critical_oos') is not None else '') + '.'
              + (" That is small." if (_n(oos_pct) or 0) < 5 else " That is enough to review before the next claim."))
    else:
        c2 = "Out-of-sequence progress wasn't audited for this update, so there's no proxy either — run the Schedule Audit."
    if head_overdue:
        c2 += (f" The head of the finish chain is also reported honestly: {_nm(head['name'])} ({head['id']}) is past its "
               f"{head['baseline_finish']} baseline finish and shown at 0%, not given progress on paper.")
    c2 += " A true over-claim test compares claimed % against measured site quantities, which sit outside the XML."
    s3 = K.sec('Over-claiming check (EV > AC by discipline)', c1, c2)

    # ── 4. cost-loaded? PV re-derived ────────────────────────────────────────────
    if derived:
        l1 = ("Budget: yes. Actuals: no, not in any way you can audit."
              + (f" The budget sits on {costed} (BAC ≈ {_m(bac, approx=True)}, the figure PV and EV both reconcile to)" +
                 (f"; {_names(B['uncosted'])} carry none." if B['uncosted'] else '.') if B else ''))
    else:
        l1 = (f"Budget: yes, and actual cost is loaded separately from progress (AC {_m(ac)} against EV {_m(ev)}), so "
              "CPI is a real signal." + (f" The budget sits on {costed} (BAC ≈ {_m(bac, approx=True)})." if B else ''))
    l1 += (" Which resource lines carry that budget — labour, equipment or material — isn't in this read; "
           "Productivity & Resource Intelligence lists the assignments.")
    l2 = ("P6 XML omits Schedule %, PV and EV, so the tool re-derives the planned side. Each activity's planned % comes "
          "from its baseline dates in its own calendar; PV = BAC × planned %, and EV = BAC × actual %. AC is read "
          "straight from the file")
    if derived:
        l2 += (f", and it equals EV because P6 generated it from progress. So the budget is real, the planned side is a "
               f"close re-derivation, and the actuals are a mirror of progress. Say that once, plainly, in the report, so "
               f"no one reads CPI {K.ratio(cpi)} as financial health. For genuine cost performance, actual costs have to be "
               "booked in P6 from site cost records instead of being calculated from % complete.")
    else:
        l2 += ", independently of progress, which is what makes CV and CPI meaningful here."
    s4 = K.sec('Is the schedule cost-loaded, and where PV is re-derived', l1, l2)

    # ── 5. S-curve ───────────────────────────────────────────────────────────────
    budget_word = (f"the {costed} budget" if (B and B['uncosted']) else 'the budget') if B else 'blended progress'
    if p_c is not None and a_c is not None:
        story = (f"the {abs(p_c - a_c)}-point gap between planned ({p_c}%) and earned ({a_c}%) on {budget_word}"
                 if a_c <= p_c else
                 f"earned ({a_c}%) running {a_c - p_c} points ahead of planned ({p_c}%) on {budget_word}")
        sc1 = (f"**The S-curve's story is {story}."
               + (" Spent sits on the earned line because cost is derived from progress." if derived else '')
               + " And yes, it exports as a one-page Excel.**")
    else:
        sc1 = ''
    es_dt, n_pts = _earned_schedule(F)
    sc2 = (f"The curve plots cumulative PV (baseline dates × budget) against cumulative EV and AC up to the data date. At "
           f"{dd} planned is at {_m(pv)} and earned{'/actual' if derived else ''} at {_m(ev)}"
           + ('' if derived else f", actual cost at {_m(ac)}") + f". The vertical gap between the lines is exactly the "
           f"{_m(sv)} schedule variance, and that gap is the chart's message."
           + (f" {n_pts} updates are stored for this project, so the curve has measured points behind today's." if n_pts >= 2 else
              " Only this update is stored so far, so today is the one measured point; earlier points fill in as you import more updates."))
    rows5 = [['Planned (PV)', _m(pv), f"{p_c}%" if B else '—'],
             ['Earned (EV)', _m(ev), f"{a_c}%" if B else '—'],
             ['Actual (AC)', _m(ac), f"{round(ac / bac * 100)}%" if (B and ac is not None) else '—'],
             ['Gap PV − EV', _m(pv - ev), f"{abs(p_c - a_c)} pts" if B else '—']]
    note5 = ''
    if B and B['uncosted']:
        note5 = (f"% of BAC is against the {costed} budget (≈ {_m(bac, approx=True)}), so it matches {_poss(costed)} {p_c}% planned / "
                 f"{a_c}% actual. The headline {K.pct(P)} / {K.pct(A_)} is blended progress including the lines that carry "
                 f"no budget ({wu_pct}% weight each)." if wu_pct is not None else '')
    elif not B:
        note5 = "% of BAC is left blank because the budget can't be pinned from the stored numbers."
    if derived:
        note5 += " EV and AC share one line because cost is derived from progress."
    s5 = K.sec('The cumulative cost S-curve (planned vs actual)', sc1, sc2,
               table=K.tbl([f"At data date {dd}", 'Cumulative', '% of BAC'], rows5, note5.strip() or None))

    # ── 6. % spent vs % complete ─────────────────────────────────────────────────
    if B and ac is not None:
        spent, comp = round(ac / bac * 100), round(ev / bac * 100)
        if derived:
            ps1 = (f"% spent (AC ÷ BAC) is {spent}% and % complete on the budget (EV ÷ BAC) is {comp}%; they sit on top of "
                   "each other. Normally a gap between them shows money leaving faster than work arrives. Here they are "
                   "equal by derivation, so this pair tells you nothing about efficiency.")
        else:
            ps1 = (f"% spent (AC ÷ BAC) is {spent}% against {comp}% complete on the budget (EV ÷ BAC): money is leaving "
                   + ('faster' if spent > comp else 'slower' if spent < comp else 'at the same rate')
                   + f" than work arrives ({abs(spent - comp)} points).")
    else:
        ps1 = (f"Without a pinned budget, compare spend and progress directly: AC is {_m(ac)} against EV {_m(ev)}"
               + (" — equal by derivation, so the pair says nothing about efficiency." if derived else '.'))
    ps2 = (f"The gap that matters is planned against earned: {p_c}% against {a_c}% "
           f"{'on the money' if B else 'on blended progress'} ({abs(p_c - a_c)} points)"
           + (f", or {K.pct(P)} against {K.pct(A_)} on blended progress ({abs((P or 0) - (A_ or 0))} points)"
              if (B and B['uncosted'] and P is not None) else '')
           + ". That's the number to put next to the S-curve, not spent against complete.") if p_c is not None else ''
    s6 = K.sec('Percent-spent vs percent-complete', ps1, ps2)

    # ── 7. burning budget without progress ───────────────────────────────────────
    b1 = ("Strictly, nothing in this file can burn budget without progress, because actual cost is generated from progress."
          if derived else
          f"Burn without progress shows as AC rising while EV stalls; the file gives the total (CPI {K.ratio(cpi)}), not a per-front split.")
    if top:
        b1 += (f" What you can see is where planned value fell due and wasn't earned: {top['code']}, {_m(top.get('gap'))} of "
               f"the {_m(vg.get('total_gap') or (pv - ev))} gap. This read doesn't split that below {dim}; to name the areas "
               "holding it, run the value gap by another of the file's activity codes (area, phase or zone).")
    elif drv:
        b1 += (f" What you can see is where planned value fell due and wasn't earned: {drv['name']}, the weighted driver "
               f"({drv.get('actual')}% against {drv.get('planned')}%).")
    if nok:
        fm = N.get('finish_milestone') or {}
        sect = [m for m in (N.get('milestones_open_late') or [])
                if m.get('type') == 'FinishMilestone' and m.get('id') != fm.get('id')][:5]
        if sect:
            b1 += " The next sectional key dates already carry the slip: " + ', '.join(
                f"{_nm(m['name'])} {_i(m['slip_wd'])}" for m in sect) + ' wd.'
    b2 = ''
    if head:
        after = sum(1 for x in chain if _date(x.get('baseline_finish')) and dd_dt and _date(x['baseline_finish']) > dd_dt)
        wparts = [p for p in (head.get('wbs') or '').split(' / ') if p]
        b2 = (f"Keep two places apart. The value gap sits in the work that was due by {dd}. The date is driven by the "
              f"{N.get('chain_count', len(chain))}-activity chain that starts at {_nm(head['name'])} ({head['id']}"
              + (f", {' / '.join(wparts[-2:])})" if wparts else ')')
              + (f", {after} of whose activities are planned to finish after the data date, so that is where time is being "
                 "lost rather than where today's value gap sits." if after else '.')
              + (f" Its first activity was due on {head['baseline_finish']} and is still {head.get('pct', 0)}%."
                 if head_overdue else ''))
    b2 = (b2 + " " if b2 else '') + ("Real burn (labour and plant cost against output) needs site cost records the file "
                                     "doesn't hold. For labour hours, see the manpower answer (Productivity & Resource Intelligence).")
    s7 = K.sec('Work fronts burning budget without progress', b1, b2)

    # ── 8. dashboard ─────────────────────────────────────────────────────────────
    s8 = K.sec('The exportable one-page cost/EVM dashboard',
               "Yes. Ask me to 'create a professional dashboard' here in the chat. It builds the one-pager with the KPI "
               "tiles (PV, EV, AC, SPI, CPI, SV, CV), the S-curve anchored to these same EVM numbers and "
               + (f"the {dim} value-gap table." if top else "the discipline progress table.")
               + " Every table exports to a native Excel .xlsx through the shared export, not a screenshot.",
               "The dashboard only renders the numbers already computed from this file; it never recomputes them."
               + (" Put the caveat on the page itself, 'CPI and AC are progress-derived', so the one-pager can't be "
                  "misread when it's forwarded." if derived else ''))

    # ── 9. EAC / ETC / TCPI ──────────────────────────────────────────────────────
    if eac is not None:
        vac = bac - eac
        tcpi = ((bac - ev) / (bac - ac)) if (ac is not None and abs(bac - ac) > 1e-6) else None
        if derived:
            e1 = (f"**EAC equals the budget (≈ {_m(bac, approx=True)}) because CPI is fixed at {K.ratio(cpi)} by derivation."
                  + (f" That cost forecast ignores a {abs(round(d))}-working-day slip, so forecast delivery in time "
                     f"({_sd(d)}" + (f" to {fc}" if fc else '') + "), not in money.**" if behind else '**'))
            e2 = (f"With CPI at {K.ratio(cpi)} the cost forecast collapses onto the budget line, which is exactly what to "
                  "expect when actual cost is generated from progress. The figures below are arithmetically correct but "
                  "carry no cost-risk signal.")
        else:
            e1 = (f"**At CPI {K.ratio(cpi)} the job lands at about {_m(eac, approx=True)} against a {_m(bac, approx=True)} budget — "
                  f"{_m(abs(vac))} {'over' if vac < 0 else 'under'}.**")
            e2 = ((f"To still land on budget, the remaining work has to run at TCPI {K.ratio(tcpi)}"
                   + (" — a step-change few jobs achieve once CPI has settled." if tcpi > 1.1 else
                      " — achievable if the current efficiency holds." if tcpi <= 1.0 else " — tight but not unusual.")
                   ) if tcpi is not None else '')
            if behind:
                e2 += f" None of this includes time-related cost for the {abs(round(d))}-working-day slip."
        t9 = K.tbl(['Metric', 'Formula', 'Value'],
                   [['EAC', 'BAC ÷ CPI', f"≈ {_m(eac, approx=True)}" + (' (= BAC)' if abs(vac) < 0.001 * bac else '')],
                    ['ETC', 'EAC − AC', f"≈ {_m(etc, approx=True)} to go"],
                    ['VAC', 'BAC − EAC', _m(vac)],
                    ['TCPI', '(BAC − EV) ÷ (BAC − AC)', K.ratio(tcpi)]],
                   (f"BAC is the implied budget on {costed}" + (", the only costed scope in the file." if B['uncosted'] else '.')
                    + (" Every figure reads clean because AC = EV." if derived else '')
                    + (f" EAC {'≈ BAC ' if derived else ''}forecasts money on the old time basis and contains nothing for "
                       f"the {_wk(d)} extension." if behind else '')))
        s9 = K.sec('Forecast at completion (EAC / ETC / TCPI)', e1, e2, table=t9)
    else:
        s9 = K.sec('Forecast at completion (EAC / ETC / TCPI)',
                   "EAC = BAC ÷ CPI needs the budget, and I can't pin BAC from the stored numbers without guessing — read it "
                   "from the EVM tab and the forecast is one division away."
                   + (f" In time, the landing is {_sd(d)}" + (f" ({fc})" if fc else '') + '.' if d is not None else ''))

    # ── 10. CPI trend ────────────────────────────────────────────────────────────
    tr = F.get('trend') or {}
    t1 = (f"A single file gives one CPI point ({K.ratio(cpi)}). A trend needs the stored update history, which Update vs "
          "Update and the trend view read from prior snapshots in the DB."
          + (f" {n_pts} distinct updates are stored for this project, so the trend view can plot it." if n_pts >= 2 else
             " Only this update is stored so far, so I won't invent a curve here."))
    if derived:
        t2_ = (f"Because actual cost is generated from progress, expect CPI to sit at {K.ratio(cpi)} in every update "
               "regardless. That flat line is itself the reason to watch the time trend instead: SPI and the finish float, "
               "update over update.")
    else:
        t2_ = ("Watch for CPI drifting down across three updates in a row: once a job is past roughly a fifth complete, "
               "cumulative CPI rarely recovers by more than a few points, so an early slide is a reliable warning.")
    if tr.get('prev_delay') is not None and d is not None:
        t2_ += f" On time, the finish moved from {K.signed(tr['prev_delay'])} to {K.signed(d)} since the previous update."
    s10 = K.sec('CPI trend over updates', t1, t2_)

    # ── 11. prolongation and cashflow ────────────────────────────────────────────
    remaining = etc if etc is not None else ((bac - ev) if bac else None)
    no_contract = F.get('hard_constraints_computable') is False
    if behind:
        pr1 = (f"The forecast above contains no time-related cost. You're about {K.wd(d)} ({K.weeks(d)}) late, and that "
               "extension carries prolongation: extended site overheads, staff, plant and preliminaries."
               + (f" It also stretches the cashflow, because the remaining ≈ {_m(remaining, approx=True)} of "
                  f"{'budgeted ' if B and B['uncosted'] else ''}value now earns out to {fc} instead of {bl}."
                  if (remaining and fc and bl) else '')
               + " The tool doesn't model prolongation" + (", and no contract milestones are loaded, so the overrun "
                                                           "can't be priced against contract dates here." if no_contract else '.'))
        pr2 = "Whether any of that cost is recoverable depends on entitlement, and one snapshot can't settle it."
        if late_ci:
            pr2 += (f" {'Several late client inputs sit' if len(late_ci) > 1 else 'A late client input sits'} on "
                    "negative-float paths: " + '; '.join(
                        f"{_nm(x['name'], 56)} {_i(x['slip_wd'])} wd (float {_i(x['tf'])})" for x in late_ci[:4])
                    + (". Those are strong EOT indicators." if len(late_ci) > 1 else ". That is a strong EOT indicator."))
        pr2 += (" Prolongation cost follows only proven employer-caused critical delay, which needs a TIA or windows "
                "analysis (Consultant Review, Update vs Update). Until then, report prolongation as a known, unpriced gap "
                f"rather than presenting {'EAC ≈ BAC' if derived else 'the EAC'} as the whole picture.")
    elif ahead:
        pr1 = (f"You're forecast about {K.wd(d)} ahead of the finish, so no prolongation is being carried. The cashflow "
               "question runs the other way: the remaining "
               + (f"≈ {_m(remaining, approx=True)} of " if remaining else '') + "value earns out earlier than the baseline"
               + (f" ({fc} against {bl})" if (fc and bl) else '') + ", which can pull payment milestones forward — worth "
               "telling the commercial team.")
        pr2 = ("The tool doesn't produce a month-by-month forward cashflow; the S-curve's forward PV line is the nearest read"
               + (", and no contract milestones are loaded to price against." if no_contract else '.'))
    else:
        pr1 = ("You're on the planned finish, so no prolongation is being carried."
               + (f" The remaining ≈ {_m(remaining, approx=True)} earns out to {fc} as planned." if (remaining and fc) else ''))
        pr2 = "The tool doesn't produce a month-by-month forward cashflow; the S-curve's forward PV line is the nearest read."
    s11 = K.sec('Prolongation and cashflow (known gap)', pr1, pr2)
    if nok and N.get('client_inputs'):
        thinking.append(f"Checked {len(N.get('client_inputs') or [])} client-input activities for time-related cost exposure "
                        f"({len(late_ci)} late and open on negative float)")

    # ── 12. earned schedule / time read ──────────────────────────────────────────
    evpv = (ev / pv) if (pv and ev is not None) else None
    w1 = (f"The SPI shown is category-weighted actual % ÷ planned % ({K.pct(A_)} ÷ {K.pct(P)} = {K.ratio(spi)})"
          + (f"; the cost version, EV ÷ PV, {'also gives' if (spi is not None and abs(evpv - spi) < 0.005) else 'gives'} "
             f"{K.ratio(evpv)}." if evpv is not None else '.')
          + " Both are bound to climb back to 1.00 near completion, because at the end earned and planned both equal the "
          "full scope, however late you finish. A badly late job can post SPI ≈ 1.0 in its final months, a classic EVM "
          "blind spot.")
    w2 = ("Earned Schedule fixes this by turning earned value into time: it asks when the baseline should have earned "
          "this much, giving a variance in weeks that stays honest to the end.")
    if es_dt and dd_dt:
        lag = (dd_dt - es_dt).days
        w2 += (f" From the {n_pts} stored updates, the baseline had planned {K.pct(A_)} by about {_fmt(es_dt)}, so on "
               f"earned schedule you're about {max(1, round(abs(lag) / 7))} weeks {'behind' if lag > 0 else 'ahead'} in time.")
    else:
        w2 += " It isn't built yet, but you already have time reads that don't drift."
    float_line = ((f"The {_sd(d)} is the finish milestone's total float in its own calendar" if d > 0 else
                   f"The finish float ({_sd(d)}) is measured on the finish milestone in its own calendar")
                  if d is not None else '')
    if float_line:
        w2 += f" {float_line}."
    if cpli is not None:
        cpl = ck.get('critical_path_length_days')
        if cpli < 1:
            w2 += (f" CPLI {K.ratio(cpli)}" + (f" (target {K.ratio(ck.get('target'))})" if ck.get('target') else '')
                   + (f" says the remaining {cpl}-day critical path would have to be done in about "
                      f"{round((1 - cpli) * 100)}% less time" if cpl else " says the remaining critical path is too long")
                   + (f" to hold {bl}." if bl else " to hold the finish date."))
        else:
            w2 += f" CPLI {K.ratio(cpli)} (≥ 1.00) says the remaining critical path has room to hold the date."
    w2 += " Report those, not EV/PV SPI, as completion nears."
    s12 = K.sec('Why cost-SPI drifts to 1.0 — read time instead', w1, w2)

    # ── measured / actions / evidence ────────────────────────────────────────────
    measured = ("PV, EV and AC come from compute() on this file. "
                + (f"BAC isn't stored with the chat facts, so it is implied: PV and EV are one budget times the budgeted "
                   f"lines' planned and earned %, and both reconcile to ≈ {_m(bac, approx=True)} ({_m(B['lo'], approx=True)}–{_m(B['hi'], approx=True)} within the "
                   f"stored rounding) only when the budget sits on {costed}"
                   + ("; the lines without budget count in progress % and SPI but not in the money. " if B['uncosted'] else '. ')
                   if B else "BAC couldn't be implied because PV and EV don't reconcile to one set of progress percentages. ")
                + "Planned % per activity is re-derived from baseline dates in the activity's own calendar because P6 XML "
                f"omits Schedule %/PV/EV. SV = EV − PV = {_m(sv)}; CV = EV − AC = {_m(cv)}. "
                + ("AC equals EV to the unit, so P6 generated it from % complete; that is why CV = 0 and CPI = 1.00. " if derived else '')
                + (f"The value gap by {dim} is the file's own activity code. " if top else '')
                + ("EAC = BAC ÷ CPI, ETC = EAC − AC, TCPI = (BAC − EV) ÷ (BAC − AC). " if eac is not None else '')
                + f"SPI is category-weighted actual % ÷ planned %; EV ÷ PV gives {K.ratio(evpv)}. "
                + ((float_line
                    + (f"; CPLI = ({ck.get('critical_path_length_days')} − {abs(round(d))}) ÷ {ck.get('critical_path_length_days')}. "
                       if (cpli is not None and ck.get('critical_path_length_days') and d > 0) else '. '))
                   if float_line else '')
                + "The CPI trend needs stored history; Earned Schedule, prolongation and contract-date pricing are not built.")
    actions = [
        (f"Lead the cost page with SV {_m(sv)}" + (f" and {_poss(top['code'])} {_pctg(top.get('pct_of_gap'))} share of it" if top else
                                                   (f" on {costed}" if single else '')) + f", not with CPI {K.ratio(cpi)}.")
        if (derived and (sv or 0) < 0) else '',
        "State once, in writing, that AC is generated from % complete (AC = EV to the unit). CV, CPI and EAC are therefore "
        "not a cost audit." if derived else '',
        (f"Split the {_m(top.get('gap'))} {top['code']} gap by another activity code (area, phase or zone) so the report "
         "names which areas hold it.") if top else
        "Re-import the file so the value gap is stored by activity code, then name the code that holds it.",
        (f"Show the S-curve on the {budget_word} ({p_c}% planned vs {a_c}% earned, {abs(p_c - a_c)} points), not spent "
         "against complete, which is flat by design.") if (derived and B) else '',
        "Ask for 'create a professional dashboard' and export the one-pager to Excel for the weekly report"
        + (", with the progress-derived caveat on the page." if derived else '.'),
        (f"Report EAC = BAC ≈ {_m(bac, approx=True)} only alongside the time read: {_sd(d)}" + (f" to {fc}" if fc else '')
         + (f" and CPLI {K.ratio(cpli)}." if cpli is not None else '.')) if (derived and eac is not None and behind) else '',
        "If real cost control is needed, book actual costs in P6 from site cost records instead of calculating them from "
        "% complete." if derived else '',
        (f"Chase {_nm(suspect[1]['name'])} ({suspect[1]['id']}, +{suspect[1]['slip_wd']} wd): {suspect[0]['name']} is at "
         f"{suspect[0].get('actual')}% against {suspect[0].get('planned')}% planned behind it.") if suspect else '',
        (f"Flag prolongation and cashflow for the {_wk(d)} slip as a known, unpriced gap. Tie any claim for "
         "time-related cost to a TIA on the late client inputs (Consultant Review / Update vs Update).") if behind else '',
        "Pull the CPI and SPI trend from stored updates" + (", and expect CPI to stay at 1.00, which is why the days and "
                                                            "float trend is the one to watch." if derived else '.'),
    ]
    evidence = [K.ev('PV', _m(pv)),
                K.ev('EV / AC', f"{_m(ev)} / {_m(ac)}" + (' (equal to the unit)' if derived else '')),
                K.ev('SV', _m(sv)),
                K.ev('CV · CPI', f"{_m(cv)} · {K.ratio(cpi)}" + (' (progress-derived)' if derived else '')),
                K.ev('BAC', f"≈ {_m(bac, approx=True)}" + (f", {costed} only" if B['uncosted'] else '')) if B else None]
    for g in gapg[:2]:
        evidence.append(K.ev(f"Gap — {g['code']}", f"{_m(g.get('gap'))} ({_pctg(g.get('pct_of_gap'))})"))
    evidence += [K.ev('Cost progress', f"{p_c}% planned vs {a_c}% earned") if B else None,
                 K.ev('Blended progress', f"{K.pct(P)} planned vs {K.pct(A_)} actual"),
                 K.ev(suspect[0]['name'], f"{suspect[0].get('actual')}% vs {suspect[0].get('planned')}%; input "
                                          f"+{suspect[1]['slip_wd']} wd") if suspect else None,
                 K.ev('EAC / ETC', f"≈ {_m(eac, approx=True)} / ≈ {_m(etc, approx=True)}") if eac is not None else None,
                 K.ev('SPI', f"{K.ratio(spi)} (weighted %); EV/PV {K.ratio(evpv)}"),
                 K.ev('Time read', f"{_sd(d)} ({K.weeks(d)})" + (f" · finish {fc}" if fc else '')) if d is not None else None,
                 K.ev('CPLI', f"{K.ratio(cpli)}" + (f" vs {K.ratio(ck.get('target'))} target" if ck.get('target') else ''))
                 if cpli is not None else None,
                 K.ev('OOS (over-claim proxy)', f"{oos} ({K.pct(oos_pct, 1)})" + (f", {mpk.group(2)} in {mpk.group(1)}"
                                                                                   if (oos is not None and mpk) else ''))
                 if oos is not None else None]

    sections = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, s12]
    a = K.A2(head_txt, sections, pills=pills, measured=measured, actions=actions, evidence=evidence,
             drilldowns=[K.drill('q01', 'Where do we stand overall — ahead or behind?'),
                         K.drill('q13', 'Can I recover prolongation cost for the late client inputs?') if behind else None,
                         K.drill('q09', 'Is the delay resource-driven?') if behind else
                         K.drill('q09', 'Is the manpower plan realistic?'),
                         K.drill('q15', "Build the one-page dashboard for this week's report")],
             tools=[K.tool('dashboard', 'Build the dashboard')])
    a['thinking'] = thinking[:4]
    return a


def _no_budget(F, N, bl, fc, drv):
    """The schedule carries no budget: say so plainly and give the progress and time reads instead."""
    d = F.get('delay_days')
    P, A_ = F.get('planned_pct'), F.get('actual_pct')
    head = ("This schedule carries no budget, so there's no money position to read — only progress"
            + (f": {K.pct(A_)} done against {K.pct(P)} planned (SPI {K.ratio(F.get('spi'))})" if P is not None else '')
            + (f", finish {_sd(d)}" if d is not None else '') + '.')
    s1 = K.sec('Earned vs planned, and the two variances in cost terms',
               "PV, EV and AC are all zero or missing in this file, so SV, CV and CPI can't be computed. The progress "
               f"read stands in: {K.pct(A_)} earned against {K.pct(P)} planned at the {F.get('data_date')} data date."
               + (f" The weighted driver is {drv['name']} ({drv.get('actual')}% against {drv.get('planned')}%)." if drv else ''))
    s4 = K.sec('Is the schedule cost-loaded, and where PV is re-derived',
               "No. None of the activities carries a budget, so every money figure (S-curve in cost, EAC, TCPI, "
               "over-claim test) is out of reach. Load budgeted units or costs on the activities in P6 and re-import to "
               "unlock them; Productivity & Resource Intelligence reads what resources are assigned today.")
    s12 = K.sec('Why cost-SPI drifts to 1.0 — read time instead',
                "The SPI shown is category-weighted actual % ÷ planned %; like any EVM index it drifts back to 1.00 near "
                "completion however late you finish."
                + (f" The time read that doesn't drift is the finish float: {_sd(d)}" + (f" to {fc}." if fc else '.')
                   if d is not None else ''))
    net = K.network_note(N)
    a = K.A2(head, [s1, s4, s12] + ([K.sec('File', net)] if net else []),
             pills=[K.pill('no budget loaded', 'warning'), K.pill(f"read time: {_sd(d)}", 'accent') if d is not None else None],
             measured="PV, EV and AC from compute() on this file; all are zero or missing, so no cost metric is quoted.",
             actions=['Load budgets (cost or budgeted units) on the activities in P6 and re-import for a cost/EVM read.',
                      'Meanwhile report progress % and the finish float, not money.'],
             evidence=[K.ev('Progress', f"{K.pct(A_)} vs {K.pct(P)}"), K.ev('Delay', K.signed(d))],
             drilldowns=[K.drill('q01', 'Where do we stand overall — ahead or behind?')],
             tools=[K.tool('dashboard', 'Build the dashboard')])
    a['thinking'] = ['Checked PV, EV and AC — no budget is loaded in this file',
                     "Fell back to the weighted progress and the finish milestone's float for the position"]
    return a
