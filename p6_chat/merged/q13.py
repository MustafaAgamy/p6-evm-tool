"""q13 — Claims & EOT: do I have a case, how many days, and how do I build the claim?

Covers, for ANY project: EOT indicators (the finish slip, late employer/client inputs and their float),
fault and time-vs-money, how many days are defensible, which delay-analysis method fits the data, the
weather / employer / contractor split, whether weather exceeded a normal allowance, concurrency and
pacing, the TIA fragnet per event, the FIDIC clause per event type and notice window, and how to
assemble the claim. Indicators only — never entitlement; every name and number comes from F / N.
"""
import re
from datetime import timedelta

from . import _kit2 as K
from .q12 import (K2_join, SEA_WORDS, _clean, _dt, _has, _is_area, _p1, chain_front, chain_steps, num_word,
                  short_name, trade_name)

# whole-word patterns (so 'access' never matches 'accessories', 'area' never matches 'areas-of-work' codes)
APPROVAL = re.compile(r'\b(approval|approve[sd]?|consent|permission)\b', re.I)
DESIGN_INFO = re.compile(r'\b(design|drawings?|information|data|loads|survey|rfis?|instructions?)\b', re.I)
ACCESS = re.compile(r'\b(release|access|possession|site handover|handover of (the )?site|areas?)\b', re.I)
FREE_ISSUE = re.compile(r'\b(deliver(y|ed|ies)?|equipment|materials?|embedded|steel|suppl(y|ied)|shipments?|'
                        r'free[- ]issue|furnished|accessories)\b', re.I)
_STOP = {'delivery', 'deliver', 'client', 'employer', 'owner', 'approval', 'release', 'completion', 'works', 'phase',
         'start', 'parts', 'main', 'full', 'structure', 'design', 'construction', 'installation', 'consultant',
         'before', 'after', 'required', 'inputs', 'input', 'items', 'first', 'second'}

# event type → (row label, FIDIC 1999, FIDIC 2017)
CLAUSES = [
    ('approval', 'Late approvals', "8.4(e): delay by the Employer / Employer's Personnel", '8.5(e)'),
    ('design', 'Late design data / information', '1.9 (Red Book) or 8.4(e)', '1.9 (Red Book) or 8.5(e)'),
    ('access', 'Late access / area release', "2.1 Right of Access; 8.4(e) if another contractor's works held you",
     '2.1; 8.5(e)'),
    ('free', 'Late client-furnished (free-issue) items', '4.20 + 8.4(e)', '2.6 + 8.5(e)'),
    ('other', 'Other employer events', '8.4(e)', '8.5(e)'),
]


def event_type(x):
    """Classify an employer input by what it is: approval, design data, access/release, free-issue, other."""
    wbs = x.get('wbs') or ''
    # classify on the subject of the name — 'X to start Y' is about X (Y is only what it gates)
    name = re.split(r'\bto start\b', x.get('name') or '', maxsplit=1, flags=re.I)[0]
    if APPROVAL.search(name):
        return 'approval'
    if DESIGN_INFO.search(name):
        return 'design'
    if ACCESS.search(name) or (ACCESS.search(wbs) and not FREE_ISSUE.search(name)):
        return 'access'
    if FREE_ISSUE.search(name) or FREE_ISSUE.search(wbs):
        return 'free'
    return 'other'


_DONE_VERB = {'approval': ('approval came', 'approvals came'), 'design': ('design input came', 'design inputs came'),
              'access': ('area release came', 'area releases came'), 'free': ('client delivery arrived', 'client deliveries arrived'),
              'other': ('client item came', 'client items came')}


def _done_phrase(done, types):
    """'5 client deliveries arrived 57-83 wd late and 1 approval came 61 wd late — all already closed'."""
    groups = {}
    for x in done:
        groups.setdefault(types.get(x['id'], 'other'), []).append(x['slip_wd'])
    bits = []
    for t, sl in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        rng = str(sl[0]) if min(sl) == max(sl) else f"{min(sl)}-{max(sl)}"
        bits.append(f"{num_word(len(sl))} {_DONE_VERB[t][len(sl) != 1]} {rng} wd late")
    return K2_join(bits) + (' — all already closed' if len(done) > 1 else ' — already closed')


def _points(pts):
    pts = [p for p in pts if p]
    if not pts:
        return ''
    return (' Two points specific to this file. ' + pts[0] + ' And ' + pts[1][:1].lower() + pts[1][1:]
            if len(pts) == 2 else ' One point specific to this file: ' + pts[0][:1].lower() + pts[0][1:])


def _driver_line(drv):
    return (f"The shortfall sits on {drv['name']} ({round((drv.get('weight') or 0) * 100)}% of the weight, "
            f"{drv['actual']}% done vs {drv['planned']}% planned).") if drv else ''


def _m(v):
    """Compact value in the project's own currency units: 562.7M / 370.4k / 950."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return '—'
    a = abs(v)
    return (f"{v / 1e9:.2f}B" if a >= 1e9 else f"{v / 1e6:.1f}M" if a >= 1e6 else f"{v / 1e3:.0f}k" if a >= 1e4
            else f"{v:,.0f}")


def _span(a, b):
    """'Feb–Jul 2026' / 'Dec 2025–Jul 2026' from two dd-Mon-yyyy strings."""
    ta, tb = _dt(a), _dt(b)
    if not ta or not tb:
        return ''
    if ta > tb:
        ta, tb = tb, ta
    if (ta.year, ta.month) == (tb.year, tb.month):
        return tb.strftime('%b %Y')
    return (ta.strftime('%b') if ta.year == tb.year else ta.strftime('%b %Y')) + '–' + tb.strftime('%b %Y')


def _rng(vals, signed=True):
    vals = [v for v in vals if v is not None]
    if not vals:
        return ''
    lo, hi = min(vals), max(vals)
    f = (lambda v: f"{v:+d}") if signed else str
    return f(lo) if lo == hi else f"{f(lo)} to {f(hi)}"


def _frng(vals):
    """Float range shallow → deep: '-3 to -48'."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return ''
    return f"{max(vals):+d}" if min(vals) == max(vals) else f"{max(vals):+d} to {min(vals):+d}"


def _label(x):
    """Name + its area (', Silo 10'-style) when the area isn't already in the name."""
    leaf = (x.get('wbs') or '').split(' / ')[-1]
    nm = _clean(x.get('name'))
    return nm + (f", {leaf}" if _is_area(leaf) and leaf.lower() not in nm.lower() else '')


def _status(x, dd):
    if (x.get('pct') or 0) > 0:
        return f"In progress ({x['pct']}%)"
    return 'Open on the data date' if x.get('finish') == dd else 'Not received'


def _ties(x, rows, discs):
    """What a fragnet for this input should link it to — read from its own name, else a distinctive word it
    shares with an activity on the finish chain, else the generic successor by event type.
    Returns (tie, hint) — hint names a discipline that the tie feeds and that is itself behind."""
    name = re.sub(r'\s+', ' ', x.get('name') or '')
    m = re.search(r'\bto start\s+(.+)$', name, re.I)
    tie = None
    if m:
        tie = re.sub(r'\s+before the\b.*$', '', m.group(1), flags=re.I).strip()
        tie = _cap(tie)
    else:
        words = [w for w in re.findall(r'[A-Za-z]{5,}', name.lower()) if w not in _STOP]
        best = None
        for w in words:
            hits = [r for r in rows if w in (r.get('name') or '').lower()]
            if hits and len(hits) <= 3 and (best is None or len(hits) < best[1]):
                best = (hits[0], len(hits))
        if best:
            r = best[0]
            tie = (f"The finish chain carries '{_clean(r['name'])}'"
                   + (f", {(r.get('wbs') or '').split(' / ')[-1]}" if _is_area((r.get('wbs') or '').split(' / ')[-1]) else '')
                   + ' (confirm whether these are the same)')
    if not tie:
        tie = {'approval': 'The works it releases (confirm successors in P6)',
               'design': 'The design and works it feeds (confirm successors in P6)',
               'access': 'The works in the released area (confirm successors in P6)',
               'free': 'The installation it supplies (confirm successors in P6)'}.get(event_type(x),
                                                                                    'Its successors in P6 (confirm)')
    low, hint = tie.lower(), ''
    for dsc in discs:
        toks = [t for t in re.findall(r'[a-z]{3,}', dsc['name'].lower())
                if t not in ('phase', 'design', 'engineering', 'works', 'construction', 'procurement', 'and')]
        if toks and all(t in low for t in toks) and (dsc.get('gap') or 0) > 0 and \
                (('design' not in dsc['name'].lower()) or 'design' in low):
            hint = f"{dsc['name']} is {dsc['actual']}% vs {dsc['planned']}% planned"
            break
    return tie, hint


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


def build(F, N, role):
    nok = bool(N and N.get('ok'))
    d = F.get('delay_days')
    d = None if d is None else round(d)
    behind, ahead = d is not None and d > 0, d is not None and d < 0
    dd = F.get('data_date') or ((N or {}).get('data_date'))
    fin = (N.get('finish_milestone') or {}) if nok else {}
    bl = fin.get('baseline_finish') or F.get('baseline_finish')
    fc = fin.get('finish') or F.get('forecast_finish')
    cal_days = (_dt(fc) - _dt(bl)).days if (_dt(fc) and _dt(bl)) else None
    fin_tf = N.get('finish_tf') if nok else None
    chain = list(N.get('chain') or []) if nok else []
    deep = list(N.get('deepest') or []) if nok else []
    tasks = [x for x in chain if 'Milestone' not in (x.get('type') or '')]
    ci_all = list(N.get('client_inputs') or []) if nok else []
    open_ci = [x for x in ci_all if not x.get('done')]
    late_open = list(N.get('client_inputs_late_open') or []) if nok else []
    late_done = list(N.get('client_inputs_late_done') or []) if nok else []
    ontime_open = [x for x in open_ci if (x.get('slip_wd') or 0) <= 0]
    tfs = [x['tf'] for x in late_open if x.get('tf') is not None]
    slips = [x['slip_wd'] for x in late_open if x.get('slip_wd') is not None]
    neg_late = [x for x in late_open if x.get('tf') is not None and x['tf'] < 0]
    driving = [x for x in late_open if x.get('tf') is not None and fin_tf is not None and x['tf'] <= fin_tf + 2]
    front, front_seg = chain_front(chain) if chain else ('', '')
    fseg = front_seg or 'finish-chain'
    head_act = tasks[0] if tasks else None
    deep0 = deep[0] if deep else None
    started = sum(1 for x in tasks if (x.get('pct') or 0) > 0)
    chain_tf = [x['tf'] for x in tasks if x.get('tf') is not None]      # the chain only — deeper activities sit off it
    chain_rng = _frng(chain_tf)
    head_late = bool(head_act and head_act.get('baseline_finish') and _dt(head_act['baseline_finish']) and _dt(dd)
                     and _dt(head_act['baseline_finish']) < _dt(dd) and (head_act.get('pct') or 0) == 0)
    discs = F.get('disciplines') or []
    cbranch = None
    if ci_all:
        from collections import Counter
        cb = Counter((x.get('wbs') or '').split(' / ')[0] for x in ci_all if x.get('wbs'))
        cbranch = next((b for b, _ in cb.most_common() if _has(b, ('client', 'employer', 'owner', 'input'))), None)
    nf_n, nf_pct = F.get('neg_float_count'), F.get('neg_float_pct')
    crit_n, drv_n = F.get('cpli_critical_count'), F.get('driving_path_count')
    cal_n = F.get('calendar_count')
    updates = len({str(h.get('date'))[:10] for h in (F.get('history') or []) if h.get('date')})
    oos, crit_oos = F.get('oos_count'), F.get('critical_oos')
    lg = ((F.get('audit') or {}).get('lag_lead') or {}).get('kpis') or {}
    drv = K.main_driver(F)
    thinking = []
    strong = len(neg_late) >= 2
    if nok:
        thinking.append(f"Checked {len(ci_all)} client/employer input activities: {len(late_open)} late and still open, "
                        f"{len(late_done)} completed late")
    else:
        if d is not None:
            thinking.append(f"Read the stored finish position: {K.signed(d)}" + (f", {bl} → {fc}" if bl and fc else ''))
        if nf_n:
            thinking.append(f"Checked the stored float: {nf_n:,} activities on negative float"
                            + (f", {drv_n:,} on the driving path" if drv_n else ''))
        thinking.append("Tried to re-read the P6 file for the client-input activities — "
                        + ((N or {}).get('error') or 'file not found') + ", so no event list this time")
    if late_open and fin_tf is not None:
        thinking.append(f"Compared their float ({_frng(tfs)}) with the {fin_tf:+d} wd finish path "
                        f"({N.get('chain_count') or len(chain)}-activity chain) to see whether any drives the finish")
    elif chain:
        thinking.append(f"Traced the {N.get('chain_count') or len(chain)}-activity chain that sets the finish")
    ev_types = {x['id']: event_type(x) for x in late_open + late_done}
    if late_open:
        thinking.append(f"Mapped each late input to a delay type, a fragnet tie and a FIDIC clause "
                        f"({len({ev_types[x['id']] for x in late_open})} event types)")
    if behind and cal_days is not None:
        thinking.append(f"Converted the {d} wd slip to {cal_days} calendar days ({bl} → {fc})")
    names_late = [f"{short_name(x['name'])} {x['slip_wd']:+d} wd" for x in late_open]
    short_late = [short_name(x['name']) for x in late_open]
    fin_lbl = (f"{fin.get('name')} ({fin.get('id')})" if fin.get('name') else 'the finish milestone')
    moved = (f"The headline: {fin_lbl} has moved from its {bl} baseline to a {fc} forecast." if (bl and fc) else
             f"The headline: {fin_lbl} is {K.signed(d) or 'off'} against its baseline.")

    # ── verdict + pills ─────────────────────────────────────────────────────────────────────────────
    if behind and late_open:
        head = (f"{'Yes, strong' if strong else 'Yes, some'} EOT indicators: {num_word(len(late_open))} client input"
                f"{'s are' if len(late_open) != 1 else ' is'} {_rng(slips).replace('+', '').replace(' to ', '-')} wd late"
                + (", all on negative float" if len(neg_late) == len(late_open) else
                   (f", {len(neg_late)} of them on negative float" if neg_late else ''))
                + f". But {d} wd is the gross slip, not your entitlement, and "
                + (f"in the current logic none of the open inputs drives the {fin_tf:+d} finish path, so a TIA / windows "
                   "run must split it before you quote a number." if not driving and fin_tf is not None else
                   f"{short_name(driving[0]['name'])} sits level with the {fin_tf:+d} finish path, so it is the first event to "
                   "prove with a TIA — before you quote a number." if driving else
                   "a TIA / windows run must split it before you quote a number."))
    elif behind and nok and late_done:
        head = (f"Weak indicators only: the finish is {K.wd(d)} late, and {len(late_done)} client items were delivered "
                "late but are closed, so their effect is baked into today's dates. A windows analysis on the earlier "
                "updates is the only way to show whether they moved the finish.")
    elif behind and nok:
        head = (f"Not from the file alone: the finish is {K.wd(d)} late, but no employer / client input activity in the "
                "file is late — on the schedule's face the slip reads as execution. An employer event has to come "
                "from your records (drawings, RFIs, access, variations) before there's a case.")
    elif behind:
        head = (f"Possibly: the finish is {K.wd(d)} late"
                + (f" with {nf_n:,} activities on negative float" if nf_n else '')
                + ", but I couldn't re-read the file to check the client inputs, so the indicators must come from your "
                  f"delay-event log. {d} wd is the gross slip, not an entitlement; only a TIA / windows run can split it.")
    elif ahead:
        head = (f"No time claim on this update: the finish is forecast {K.wd(d)} ahead of its baseline"
                + (f" ({fc} against {bl})" if fc and bl else '')
                + ", so there's no delay to completion to extend. Keep the notice discipline anyway — an employer "
                  "event that eats your float or disrupts crews can still carry cost.")
    elif d == 0:
        head = ("No time claim on this update: the finish is on its baseline date. Keep the notice discipline for any "
                "employer event — float it consumes is still worth recording.")
    else:
        head = ("I can't measure a finish slip from this file, so there's no delay figure to claim yet. The indicators, "
                "method and clauses below still apply once the finish milestone is readable.")

    concurrency = ('likely' if (late_open and chain and not driving) else 'to test' if driving else None)
    pills = [
        K.pill(f"~{d} wd gross slip", 'danger') if behind else
        (K.pill(f"{K.signed(d)} · no slip to extend", 'success') if d is not None else None),
        K.pill(f"{len(late_open)} of {len(open_ci)} open client inputs late ({_rng(slips)} wd)", 'warning') if late_open else None,
        (K.pill(f"all {len(late_open)} on negative float ({_frng(tfs)})", 'danger') if len(neg_late) == len(late_open)
         else K.pill(f"{len(neg_late)} of {len(late_open)} on negative float", 'warning')) if late_open else None,
        K.pill(f"finish path {fin_tf:+d}: {front or fin.get('name')}", 'warning') if (behind and fin_tf is not None) else None,
        K.pill('entitlement ≠ slip', 'warning') if behind else None,
        K.pill('notice clock: 28 days', 'accent'),
        K.pill(f"concurrency: {concurrency}", 'danger' if concurrency == 'likely' else 'warning') if concurrency else None,
        K.pill('windows + TIA (MIP 3.3 / 3.7)', 'accent') if behind else None,
        K.pill('claim builder: in development', 'neutral')]

    # ── 1. do you have indicators ───────────────────────────────────────────────────────────────────
    p1 = []
    if not nok:
        p1.append(K.network_note(N))
    if behind and late_open:
        p1.append(f"**{'Yes, you have strong' if strong else 'Yes, you have some'} EOT indicators. "
                  f"{num_word(len(late_open), cap=True)} client "
                  f"input{'s are' if len(late_open) != 1 else ' is'} {_rng(slips).replace('+', '').replace(' to ', ' to ')} "
                  "working days late"
                  + (", and every one sits on a negative-float path." if len(neg_late) == len(late_open) else
                     f", {len(neg_late)} of them on negative-float paths." if neg_late else '.')
                  + f" But {d} wd is the gross slip, not your entitlement. Splitting it between employer and contractor "
                    "needs a TIA / windows analysis. One snapshot can't do it.**")
        txt = (moved + f" That is {d} working days "
               "late" + (f", with {nf_n:,} activities ({_p1(nf_pct)}) on negative float" if nf_n else '') + ". Negative "
               "float alone only says the network can't make its dates. It becomes an EOT indicator because the file also "
               "carries " + (f"a dedicated '{cbranch}' WBS ({len(open_ci)} open items)" if cbranch else
                             f"{len(open_ci)} open employer / client input activities")
               + f", and {num_word(len(late_open))} of those items {'are' if len(late_open) != 1 else 'is'} late: "
               + ', '.join(names_late) + '.')
        if late_done:
            txt += f" On top of that, {_done_phrase(late_done, ev_types)}."
        txt += " Employer-side events on late paths are the classic footprint of a time claim."
        p1.append(txt)
        if tasks:
            steps, rest = chain_steps(chain, limit=8)
            last_task = max(tasks, key=lambda x: _dt(x.get('finish')) or _dt('01-Jan-1900'))
            last = next((x for x in reversed(chain) if 'Milestone' in (x.get('type') or '')
                         and _dt(x.get('finish')) and _dt(last_task.get('finish')) and
                         _dt(x['finish']) >= _dt(last_task['finish'])), chain[-1])
            p1.append(f"What the file does not show is that those events caused the {d} days. The finish date is set by "
                      f"the {front or 'finish'} chain. It runs through " + ', '.join(steps)
                      + (f", then {len(rest)} more through {K2_join(list(dict.fromkeys(trade_name(x) for x in rest))[:4])}"
                         if rest else '')
                      + f", into {_clean(last['name'])} ({last['id']}). That chain is "
                      + ('0% started' if not started else f"{started} of {len(tasks)} started")
                      + f", with float between {chain_rng.replace(' to ', ' and ')}. Your claim has to answer one question: "
                        "was a client hold behind it?")
    elif behind and nok:
        p1.append(f"**{'Weak' if late_done else 'Not from the file alone'} — the finish is {K.wd(d)} late but no open "
                  "employer / client input is late.**")
        p1.append(moved[:-1]
                  + (f", with {nf_n:,} activities ({_p1(nf_pct)}) on negative float" if nf_n else '') + '. '
                  + (f"The file names {len(ci_all)} employer / client input activities; none still open is late. "
                     if ci_all else "The file has no activities named as employer / client inputs, so it can't show an employer event. ")
                  + (f"{len(late_done)} were delivered late ({_rng([x['slip_wd'] for x in late_done])} wd) and are closed. "
                     if late_done else '')
                  + "Late drawings, RFIs, access or variations live in your correspondence, not the P6 export — log them "
                    "against the activities they held before you argue cause.")
    elif behind:
        p1.append(f"**Possibly — the finish is {K.wd(d)} late, but the employer side has to come from your records until "
                  "the file can be re-read.**")
        p1.append(f"The slip is real: {K.delay_phrase(F)}"
                  + (f", with {nf_n:,} activities ({_p1(nf_pct)}) on negative float" if nf_n else '')
                  + (f" and {drv_n:,} on the driving path" if drv_n else '') + '. '
                  + (_driver_line(drv) + ' ' if drv else '')
                  + "That tells you where the finish is slipping, not why. Re-import the file and I'll list the employer / "
                    "client input activities with their slip and float — those are the candidate delay events.")
    elif ahead or d == 0:
        p1.append(f"**No — the finish is {'ahead of' if ahead else 'on'} its baseline, so there is no delay to completion "
                  "to extend.**")
        gap = f"{abs(d)} wd ahead" if ahead else 'on the date'
        p1.append((f"The forecast finish is {fc} against a {bl} baseline ({gap})." if fc and bl else
                   f"The finish stands {gap} against its baseline.")
                  + " That doesn't mean no employer event happened: a late approval or access that ate float, or disrupted "
                    "crews, can still carry cost (disruption, or prolongation of a section) and must still be notified. "
                    "Float you lose to the employer today is float you won't have when your own risk lands.")
    else:
        p1.append("The finish milestone isn't readable from this file, so there's no measured delay to claim. The "
                  "indicators, method and clause map below still hold once it is.")
    sec1 = K.sec('Do you have indicators?', *p1)

    # ── 2. the late client inputs ───────────────────────────────────────────────────────────────────
    rows2 = [[f"{_clean(x['name'])} ({x['id']})", x.get('baseline_finish'), x.get('finish'), f"{x['slip_wd']:+d}",
              (f"{x['tf']:+d}" if x.get('tf') is not None else None), _status(x, dd)] for x in late_open]
    note2 = None
    if late_open:
        zero = sum(1 for x in late_open if not x.get('pct'))
        on_dd = [x for x in late_open if x.get('finish') == dd]
        if len(late_open) == 1:
            note2 = 'It is 0% complete.' if zero else 'It is under way.'
        elif zero == len(late_open):
            note2 = f"All {num_word(zero)} are 0% complete."
        else:
            note2 = f"{num_word(zero, cap=True)} {'are' if zero != 1 else 'is'} 0% complete." if zero else 'All are under way.'
        if on_dd:
            one = len(on_dd) == 1
            note2 += (f" The {num_word(len(on_dd))} forecast at {dd} {'sits' if one else 'sit'} on the data date. In P6 that "
                      f"means {'it is' if one else 'they are'} still outstanding and the slip grows every week "
                      f"{'it stays' if one else 'they stay'} open (or {'it has' if one else 'they have'} happened and nobody "
                      f"actualised {'it' if one else 'them'}, so check).")
        if ontime_open:
            same_tf0 = all((x.get('tf') or 0) == 0 for x in ontime_open)
            note2 += (f" The other {num_word(len(ontime_open))} open client item{'s' if len(ontime_open) != 1 else ''}, "
                      + ', '.join(short_name(x['name']) for x in ontime_open[:6])
                      + f", sit on {'their' if len(ontime_open) != 1 else 'its'} baseline dates"
                      + (' with zero float.' if same_tf0 else '.'))
        if late_done:
            one = len(late_done) == 1
            note2 += (f" The {num_word(len(late_done))} client item{'' if one else 's'} completed late "
                      f"({_rng([x['slip_wd'] for x in late_done])} wd) {'has' if one else 'have'} already happened, so "
                      f"{'it no longer carries' if one else 'they no longer carry'} float in this snapshot.")
    p2 = ([f"These are the real rows from the file's '{cbranch}' WBS. They are your candidate delay events."
           if cbranch else "These are the real employer / client input rows in your file. They are your candidate delay events."]
          if late_open else [])
    sec2 = K.sec('The late client inputs in your file', *p2,
                 table=K.tbl(['Client input (ID)', 'Baseline', 'Forecast', 'Slip (wd)', 'Float (wd)', f"Status at {dd}"],
                             rows2, note=note2))

    # ── 3. whose fault — time vs money ──────────────────────────────────────────────────────────────
    def _by_type(t, done=False):
        src = late_done if done else late_open
        return [x for x in src if ev_types.get(x['id']) == t]
    comp_cand = (K2_join(short_late) if late_open else
                 ('Needs the file' if not nok else 'None late in this file'))
    if late_done:
        comp_cand += f"; also {_done_phrase(late_done, ev_types)}"
    if behind and tasks and head_act:
        ne = (f"Not proven either way. The {fseg} chain is {'0% started' if not started else f'{started} of {len(tasks)} started'}"
              + (f", and {_label(head_act)} ({head_act['id']}) was due {head_act['baseline_finish']}" if head_late else '')
              + ". If no client hold sits behind it, it lands here")
    elif behind and drv:
        ne = (f"The driving shortfall on {drv['name']} ({drv['actual']}% done vs {drv['planned']}% planned) lands here "
              "unless an employer event sits behind it")
    else:
        ne = 'Nothing to allocate on this update' if not behind else 'The residual once employer and neutral events are proven'
    rows3 = [['Compensable', 'Employer (late approvals, information, site release, free-issue items)',
              'Time + money (prolongation)', comp_cand],
             ['Excusable / neutral', 'No-one (exceptionally adverse weather, force majeure)', 'Time only',
              'None identifiable. The file carries no weather record, so this needs the Weather audit'],
             ['Non-excusable', 'You (productivity, resourcing, sequence)', 'Nothing', ne]]
    money = ("On money: CPI reads " + K.ratio(F.get('cpi')) + " only because actual cost in this file is derived from "
             "progress. It is not a cost record, so price prolongation from your site overheads and cost ledger, not from "
             "the P6 numbers." if F.get('cost_derived') else
             "On money: prolongation is priced from your time-related site overheads, not from CPI"
             + (f" (CPI {K.ratio(F.get('cpi'))} describes the work done, not the cost of standing time)." if F.get('cpi') else '.'))
    intro3 = ("Fault splits the delay into three buckets, and the money follows the bucket. "
              + ("Here is how this file's events map. Treat them as candidates, not findings." if (behind and nok) else
                 "Without the file I can only place what the stored numbers show — treat it as a frame, not findings."
                 if behind else
                 "With no slip on this update there's nothing to allocate today, but the bucket still decides what any "
                 "employer event is worth later — so here is the map."))
    sec3 = K.sec('Whose fault — and time vs money', intro3,
                 table=K.tbl(['Delay type', 'Who caused it', 'You get', 'Candidates on this file'], rows3,
                             note="The candidates come from WBS and activity names. Which bucket each one lands in depends "
                                  "on the contract and your correspondence. " + money))

    # ── 4. how many days are justifiable ────────────────────────────────────────────────────────────
    p4 = []
    if behind:
        p4.append(f"Not {d}, and on this snapshot not a number anyone can defend yet. {d} wd is the gross finish slip. "
                  "Your justifiable figure is the employer-caused critical delay, isolated by a TIA or but-for run.")
        if late_open and fin_tf is not None and tfs:
            deepest_ci = min((x for x in late_open if x.get('tf') is not None), key=lambda x: x['tf'])
            others = [x['tf'] for x in late_open if x.get('tf') is not None and x is not deepest_ci]
            txt = (f"The float does give you a warning worth acting on. The deepest open client input is "
                   f"{short_name(deepest_ci['name'])} at {deepest_ci['tf']:+d}"
                   + (f"; the rest sit between {_frng(others).replace(' to ', ' and ')}" if len(others) > 1 else
                      (f"; the other sits at {others[0]:+d}" if others else '')) + '. '
                   + f"The finish path is at {fin_tf:+d}"
                   + (f" ({_label(head_act)} is {head_act['tf']:+d}" if head_act and head_act.get('tf') is not None else '')
                   + (')' if head_act else '')
                   + (f"; {_label(deep0)} sits off that chain at {deep0['tf']:+d}"
                      if deep0 and deep0 is not head_act and deep0.get('tf') is not None
                      and deep0['id'] not in {x['id'] for x in tasks} else '') + '. '
                   "A predecessor that drives an activity carries float at least as negative as that activity. ")
            if not driving:
                txt += (f"So, allowing for calendar differences, none of the open client inputs is driving the finish path "
                        f"in the current logic. That leaves two possibilities. Either the {fseg} chain is late for reasons "
                        "of its own, or the logic doesn't tie the client holds to the works they actually held up. Settle "
                        "that before any number goes in a letter: if a client input genuinely held "
                        f"{fseg}, the logic has to show it.")
            else:
                txt += (f"{short_name(driving[0]['name'])} sits at {driving[0]['tf']:+d}, level with the finish path, so in "
                        "the current logic it may be driving the finish. That is your strongest single event — run its "
                        "fragnet first.")
            p4.append(txt)
        reasons = []
        if late_done:
            reasons.append(f"events that have already closed, such as {short_name(late_done[0]['name'])} "
                           f"({late_done[0]['slip_wd']:+d} wd), no longer carry float, so their effect is baked into today's dates")
        reasons.append(f"the float is measured against the {bl or 'baseline'} finish; if any EOT has already been granted, "
                       "the datum moves")
        p4.append(f"{'Two more reasons' if len(reasons) > 1 else 'One more reason'} one snapshot can't give you the figure. "
                  + ' '.join(f"{w}, {r}." for w, r in zip(('First', 'Second'), reasons))
                  + " Both need the earlier updates (Update vs Update, Consultant Review)."
                  if len(reasons) > 1 else
                  f"One more reason one snapshot can't give you the figure: {reasons[0]}. That needs the earlier updates "
                  "(Update vs Update, Consultant Review).")
    else:
        p4.append("None as an extension of time on this update — there is no delay to completion. What you can still "
                  "justify is float lost to employer events, recorded now, so the days are on file if a later slip "
                  "needs them. A TIA on the update in force when the event happened quantifies it.")
    sec4 = K.sec('How many days are justifiable', *p4)

    # ── 5. which method fits ────────────────────────────────────────────────────────────────────────
    due = [x.get('baseline_finish') for x in late_open if _dt(x.get('baseline_finish'))]
    due.sort(key=_dt)
    fell = f"{due[0]} and {due[-1]}" if len(due) > 1 else (due[0] if due else '')
    p5 = [(("Your data points to a combination. " if behind else
            "Nothing needs analysing on this update; if an employer event does, your data points to a combination. ")
           + "You have a baseline"
           + (f", a progressed update at {dd}, and client events that fell due between {fell}" if len(due) > 1 else
              (f", a progressed update at {dd}, and a client event that fell due on {fell}" if due else
               f" and a progressed update at {dd}"))
           + '.' + (" Only this one update is stored in the tool, so windows needs the earlier updates loaded."
                    if updates <= 1 else f" {updates} dated updates are stored in the tool."))]
    two_fam = bool(late_open and tasks)
    rows5 = [['Windows / time-slice', '3.3-3.4',
              (f"Best spine, but it needs the dated updates covering {_span(due[0], dd)}, when the client inputs fell due"
               if due else "Best spine once the dated updates are loaded — it shows what drove each period")],
             ['Time Impact Analysis (fragnet)', '3.7',
              (f"Per event: one fragnet each for {K2_join(short_late[:8])}" if late_open else
               "Per event, on the update in force just before it — the prospective method")],
             ['As-planned vs as-built', '3.1-3.2',
              (f"Weak here. Two late families (client inputs and the {fseg} chain) overlap in time, and this method can't "
               "separate them" if two_fam else "Descriptive — shows where the time went, not why")],
             ['Collapsed as-built', '3.8',
              ("Not yet. The as-built logic needs cleaning first: "
               + K2_join([f"{oos} out-of-sequence ({crit_oos or 0} critical)" if oos else '',
                          f"{lg.get('lagged_count')} lags ({_p1(lg.get('lagged_pct'))}), {lg.get('long_count')} of them over "
                          f"{lg.get('long_threshold_days') or 14} wd" if lg.get('lagged_count') else ''])
               if (oos or lg.get('lagged_count')) else
               "Needs a clean, fully progressed as-built network")
              + (f"; and the job is only {F.get('actual_pct')}% done" if (F.get('actual_pct') or 100) < 90 else '')]]
    sec5 = K.sec('Which method fits your data', *p5,
                 table=K.tbl(['Method', 'AACE MIP', 'Fits your data?'], rows5,
                             note="Windows tells the retrospective story (what actually drove each period). TIA fragnets "
                                  "carry each discrete client event. AACE 29R-03 names the methods; the contract and the "
                                  "forum can prefer one — confirm with your claims consultant."))

    # ── 6. the three-way split ──────────────────────────────────────────────────────────────────────
    p6 = []
    if behind:
        if late_open:
            p6.append(f"**Only one of the three buckets has evidence behind it on this file: the employer side, with "
                      f"{num_word(len(late_open))} late client input{'s' if len(late_open) != 1 else ''} at float {_frng(tfs)}. The "
                      f"finish path ({fin_tf:+d}) runs through the {fseg} works with no recorded cause, and weather isn't in "
                      f"the file at all. So the {d} wd can't be split from this snapshot.**" if fin_tf is not None else
                      f"**The employer side has evidence ({len(late_open)} late client inputs); weather and your own share "
                      f"don't. The {d} wd can't be split from this snapshot.**")
        elif nok:
            p6.append(f"**None of the three buckets has direct evidence in this file, so the {d} wd can't be split from "
                      "this snapshot.**")
        else:
            p6.append(f"**Without the file I can't see the employer side, and weather isn't recorded anywhere — so the {d} wd "
                      "can't be split from what I hold.**")
        p6.append("Right now you have one gross number and three possible owners. Here is what the file puts in each bucket.")
        emp = ((f"{len(late_open)} late client inputs ({_rng(slips)} wd, float {_frng(tfs)})" if late_open else
                ('No late employer / client input in the file' if nok else 'Not readable without the file'))
               + (f"; {_done_phrase(late_done, ev_types)}" if late_done else ''))
        con = ((f"{fseg} chain {'0% started' if not started else f'{started} of {len(tasks)} started'} at {chain_rng}"
                + (f"; {_label(head_act)} due {head_act['baseline_finish']}, not started" if head_late else ''))
               if tasks else (_driver_line(drv) if drv else 'The driving front, once the file is re-read'))
        rows6 = [['Weather (excusable)', f"Nothing. No weather record; {cal_n or 'the'} calendar{'s' if cal_n != 1 else ''}, "
                                          "weather allowance unknown", 'Weather / Calendar Audit', 'Time only'],
                 ['Employer (compensable)', emp, 'Delay-event log mapped to activities, then TIA', 'Time + money'],
                 ['Contractor (non-excusable)', con, 'The residual after the two above, if no client hold sits behind it', 'None']]
        note6 = ("The rows are real. The split in days can't be computed from one snapshot; it needs the delay-event log, "
                 "the weather audit and a windows / but-for run. I don't read resource loading here, so this can't show "
                 f"whether the {fseg} works are late for lack of manpower or because they were held — Productivity & "
                 "Resource Intelligence reads the P6 resources.")
    else:
        p6.append("With the finish not behind its baseline there's no slip to divide. If an employer event is using up "
                  "your float, record it now against the activity it held — float is usually shared, and the party that "
                  "uses it first often keeps it.")
        rows6, note6 = [], None
    sec6 = K.sec('The three-way split', *p6, table=K.tbl(['Bucket', 'What this file shows', 'Source of truth', 'Entitlement'],
                                                         rows6, note=note6) if rows6 else None)

    # ── 7. weather ──────────────────────────────────────────────────────────────────────────────────
    sea = None
    if nok:
        for a in ((N.get('kb_view') or {}).get('activities') or []):
            t = ((a.get('name') or '') + ' ' + (a.get('wbs_path') or '')).lower()
            if any(re.search(r'\b' + w + r'\b', t) for w in SEA_WORDS):
                sea = re.sub(r'\s+', ' ', a.get('name') or '').strip()
                break
    p7 = [("The file can't answer this. Nothing in it records weather, and neither the "
           + ((f"{K.signed(d).split(' ')[0]} wd slip nor the {fc} forecast" if behind else
               f"{abs(d)} wd lead nor the {fc} forecast" if ahead else f"{fc} forecast nor its float")
              if (d is not None and fc) else 'slip nor the forecast')
           + " counts it." + (" None of the events that are actually late in this file is a weather event." if late_open else '')),
          ("Excusable weather is only the excess over what a competent contractor should have planned for. If the "
           "calendars already allow for a normal year's weather, a normal year gets you nothing. Run the Bad-Weather "
           "view (Calendar Audit) from the data date with the right Site Type. It counts adverse-weather days against a "
           f"typical year and shows what the {num_word(cal_n) + ' ' if cal_n else ''}calendar{'' if cal_n == 1 else 's'} "
           "already take" + ('s' if cal_n == 1 else '') + " out."
           + (f" The file carries port-side work ({sea}), so if the site is by the sea, pick the coastal preset; the "
              "wrong preset reads zero weather." if sea else " Pick the preset that matches the site — the wrong one "
                                                              "reads zero weather.")
           + " Don't claim a single weather day until that audit is done.")]
    sec7 = K.sec('Was the weather worse than you should have allowed?', *p7)

    # ── 8. concurrency and pacing ───────────────────────────────────────────────────────────────────
    # pacing candidates: open milestones that slipped but still carry positive float — works fronts first
    pacing = sorted([m for m in (N.get('milestones') or []) if not m.get('done') and (m.get('slip_wd') or 0) > 0
                     and (m.get('tf') or 0) > 0],
                    key=lambda m: (_has(m.get('name'), ('design', 'engineering', 'procurement', 'submittal')),
                                   _dt(m.get('baseline_finish')) or _dt('31-Dec-2999')))[:4] if nok else []
    p8, rows8 = [], []
    if behind:
        base = ("Concurrency means an employer delay and one of yours hit the critical path in the same window. The usual "
                "result: you keep the time but lose the prolongation money for the overlap. ")
        if late_open and tasks:
            base += ("On this file it's a live risk, because two late families run side by side"
                     + (f", with {crit_n:,} activities at critical float and {drv_n:,} on the driving path" if crit_n and drv_n else '')
                     + f". If a client input held the {fseg} works, that stretch has no concurrency — the employer event "
                       f"is the cause. If nothing did, the {fseg} chain is the dominant delay; the client inputs then delay "
                       f"their own paths (float {_frng(tfs)}) but not the finish, and the Engineer will say they were "
                       "concurrent at best, not critical.")
        elif not nok:
            base += ("I can't see the employer side without the file, so concurrency can't be tested from what I hold — "
                     "re-import it and I'll set the late client inputs beside the finish chain.")
        else:
            base += ("On this file only one late family is visible, so there's no concurrency to argue yet — it becomes "
                     "live the moment an employer event is shown on the driving path.")
        base += " FIDIC 2017 (8.5) sends concurrency to the Special Provisions, so check yours."
        p8.append(base)
        pac = ("Pacing is the mirror image. "
               + (f"{K2_join([_clean(m['name']) for m in pacing[:3]])} slipped but still carry positive float, so they "
                  "aren't setting the finish. If you deliberately slowed them because the finish was already held "
                  "elsewhere, that is a pacing defence, but only if the decision was made and recorded at the time."
                  if pacing else "If you slow a floated front because the finish is already held elsewhere, that is a "
                                 "pacing defence — but only if it's decided and recorded at the time.")
               + " Neither concurrency nor pacing can be declared from the XML. Both need dated events against activities "
                 "and a window-by-window driving-path comparison (Update vs Update + Consultant Review).")
        p8.append(pac)
        if late_open:
            on_dd = sum(1 for x in late_open if x.get('finish') == dd)
            later = [x for x in late_open if x.get('finish') != dd]
            rows8.append(['Client inputs (employer side)',
                          (', '.join(short_late[:6]) + '…') if len(short_late) > 6 else K2_join(short_late),
                          _frng(tfs), 'Open' + (f" ({on_dd} on the data date" if on_dd else ' (')
                          + (f"; {short_name(later[0]['name'])} forecast {later[0]['finish']})" if later else ')')])
        fams = {}
        for x in tasks:
            parts = (x.get('wbs') or '').split(' / ')
            fams.setdefault(parts[1] if len(parts) > 1 else parts[0], []).append(x)
        for fam, rows in list(fams.items())[:3]:
            st, _ = chain_steps(rows, limit=4)
            tfam = [x['tf'] for x in rows if x.get('tf') is not None]     # this front's chain activities only
            s_n = sum(1 for x in rows if (x.get('pct') or 0) > 0)
            last = max(rows, key=lambda x: _dt(x.get('finish')) or _dt('01-Jan-1900'))
            rows8.append([fam + (f" ({front_seg})" if front_seg and front_seg not in fam else ''),
                          ', '.join(st) + ('…' if len(rows) > len(st) else ''), _frng(tfam),
                          ('0% started' if not s_n else f"{s_n} of {len(rows)} started") + f"; finish {last.get('finish')}"])
        if pacing:
            rows8.append(['Slipped but floated (pacing candidates)',
                          ' / '.join(m['id'] for m in pacing), ' / '.join(f"{m['tf']:+d}" for m in pacing),
                          'Slipped ' + ' / '.join(f"{m['slip_wd']:+d}" for m in pacing) + ' wd, not driving'])
    else:
        p8.append("Not live on this update: with no delay to completion there's no critical overlap to apportion. Keep "
                  "dated records of any employer event and any front you deliberately slow — that record is what "
                  "decides concurrency and pacing if the finish slips later.")
    sec8 = K.sec('Concurrency and pacing — the money killer', *p8,
                 table=K.tbl(['Late family', 'Real activities', 'Float (wd)', f"Status at {dd}"], rows8,
                             note="Floats and slips come from the file. Whether a family is concurrent or paced is a "
                                  "windows finding, not a float reading."))

    # ── 9. the fragnet ──────────────────────────────────────────────────────────────────────────────
    by_float = sorted([x for x in late_open if x.get('tf') is not None], key=lambda x: x['tf']) + \
        [x for x in late_open if x.get('tf') is None]
    ties = {x['id']: _ties(x, chain + deep, discs) for x in late_open}
    rows9 = [[f"{_clean(x['name'])} ({x['id']})", x.get('baseline_finish'),
              f"{x['slip_wd']:+d} / " + (f"{x['tf']:+d}" if x.get('tf') is not None else '—'),
              ties[x['id']][0] + (f" ({ties[x['id']][1]})" if ties[x['id']][1] else ''), 'Not run yet'] for x in by_float]
    p9 = []
    if late_open:
        firsts = [short_name(x['name']) for x in by_float[:3]]
        p9.append(f"**Build one fragnet per late client input, starting with "
                  + (f"the {num_word(len(firsts))} deepest: " if len(firsts) > 1 else 'the deepest: ')
                  + f"{K2_join(firsts)}. Map each to its FIDIC clause, then wrap them in a "
                  "baseline-vs-impacted-vs-actual S-curve. The offline engine estimates each move; P6 F9 proves it.**")
    p9.append("A TIA works one event at a time. Take the update in force just before the event fell due and insert a small "
              "fragnet: the wait for the input, plus the links from it to the work it actually holds. Then re-schedule. "
              "How far the finish moves is that event's potential EOT."
              + _points([f"The events fell due between {fell}, so each fragnet needs the update from that period, not this "
                         f"{dd} one." if len(due) > 1 else '',
                         f"Each fragnet has to link the input to the work it genuinely gated, because today none of the open "
                         f"inputs is driving the {fin_tf:+d} finish path." if (late_open and not driving and fin_tf is not None)
                         else '']))
    if not late_open:
        p9.append("Without the file I can't list the employer inputs, so each fragnet starts from your delay-event log — "
                  "the event, the date it fell due, the date it arrived and the activity it held. Re-import the file and "
                  "I'll lay the late client inputs out as a fragnet table." if not nok else
                  "With no late employer input in the file, a fragnet today is prospective: if an approval, access or "
                  "free-issue item is at risk, model its likely late date now on the current update and read the finish "
                  "move — that is also your early-warning notice evidence.")
    sec9 = K.sec('Modelling the fragnet (TIA)', *p9,
                 table=K.tbl(['Event (ID)', 'Due (baseline)', 'Slip / float now', 'Fragnet ties it to', 'Finish move'], rows9,
                             note="The finish move is deliberately left blank because it comes from the run, not from the "
                                  "float. The offline engine is forward-pass only: it drafts and ESTIMATES the move, so "
                                  "validate every day in P6 F9 before it goes in a claim. Run events in date order, each on "
                                  "its own update, rather than stacking them in one model."))

    # ── 10. FIDIC clause ────────────────────────────────────────────────────────────────────────────
    rows10 = []
    for t, lbl, c99, c17 in CLAUSES:
        ev_open = _by_type(t)
        ev_done = _by_type(t, done=True)
        if not (ev_open or ev_done):
            continue
        what = ', '.join(f"{short_name(x['name'])} ({x['id']})" for x in ev_open[:4]) + ('…' if len(ev_open) > 4 else '')
        if ev_done:
            what += (('; ' if what else '') + f"{len(ev_done)} completed late ("
                     + _rng([x['slip_wd'] for x in ev_done]) + ' wd)')
        rows10.append([f"{lbl}: {what}", c99, c17])
    if not rows10:
        rows10 = [[lbl + ' (none late in this file)' if nok else lbl, c99, c17] for t, lbl, c99, c17 in CLAUSES[:4]]
    rows10.append(['Exceptionally adverse weather (only if the audit shows it)', '8.4(c)', '8.5(c)'])
    rows10.append(['Notice of claim', '20.1: 28 days; detailed claim within 42', '20.2.1: 28 days; fully detailed claim (20.2.4) within 84'])
    designs = [x['name'] for x in discs if _has(x['name'], ('design',))]
    p10 = ["The event type picks the clause."
           + (f" This file hints at a design-build contract, because the contractor's programme carries "
              f"{K2_join(designs[:3])}. So confirm whether you are under the Red or the Yellow Book, since some clauses "
              "(1.9 for one) differ between them." if designs else
              " Confirm whether you are under the Red (employer's design) or Yellow (design-build) Book — some clauses "
              "(1.9 for one) differ between them.")]
    note10 = ("These clauses are candidates by event type only; the tool doesn't read the contract. Confirm the book "
              "(Red / Yellow), the edition (1999 / 2017) and the Particular Conditions.")
    if due and _dt(dd):
        closes = [_dt(x) + timedelta(days=28) for x in due]
        passed = sum(1 for c in closes if c < _dt(dd))
        note10 += (f" Counting 28 days from each due date, the notice windows for the late inputs closed between "
                   f"{min(closes).strftime('%d-%b-%Y')} and {max(closes).strftime('%d-%b-%Y')}"
                   + (f" — all before the {dd} data date" if passed == len(closes) else f" — {passed} of {len(closes)} before the data date")
                   + ", so check the notice log first: a missed notice is the first defence you'll face (both editions "
                     "count from when you became aware, or should have). For events still open, keep serving interim "
                     "(continuing-event) particulars.")
    else:
        note10 += " Serve notice within 28 days of becoming aware of an event; for continuing events, keep serving interim particulars."
    sec10 = K.sec('Find the FIDIC clause for the event', *p10,
                  table=K.tbl(['Event on this file', 'FIDIC 1999', 'FIDIC 2017'], rows10, note=note10))

    # ── 11. assemble ────────────────────────────────────────────────────────────────────────────────
    vg = F.get('value_gap') or {}
    top = next((g for g in (vg.get('groups') or []) if (g.get('gap') or 0) > 0), None)
    story = ''
    if behind:
        story = ((f"The actual story on this file is already stark. The forecast is {fc} against a {bl} baseline. "
                  if fc and bl else '')
                 + (f"Earned value is {_m(F.get('ev'))} against {_m(F.get('pv'))} planned ({K.pct(F.get('actual_pct'))} "
                    f"done vs {K.pct(F.get('planned_pct'))}, SPI {K.ratio(F.get('spi'))})" if F.get('pv') and F.get('ev') else '')
                 + (f", and {top['code']} carries {round(top.get('pct_of_gap') or 0, 2)}% of that value gap" if top else '')
                 + ('. ' if F.get('pv') and F.get('ev') else ''))
    p11 = [(("" if behind else "There's no time claim to assemble on this update. If one becomes live, it works like this. ")
            + "The claim is the fragnets, the clauses and the evidence, told as three curves: baseline (as-planned), "
              "impacted (baseline plus fragnets) and actual (your progressed updates). "
            + story
            + "The S-curves split from the data date onward. The impacted curve is the part you don't have yet; it comes "
              "from the fragnet runs."),
           ("Before it goes out, check four things. The reference programme must be the contract baseline, not a later "
            "re-baseline that absorbed delay. Each base update must have been accepted. The result must be converted from "
            "working to calendar days"
            + (f": the {d} wd from {bl} to {fc} is {cal_days} calendar days" if behind and cal_days is not None else '')
            + ". And the wording must say 'the analysis indicates a potential EOT of N days', never 'we are entitled'. "
              "The EOT Claim Builder, which will assemble this into a FIDIC-structured Word/PDF, is in development and "
              "not in this build. Today you assemble it by hand from the TIA results, using the tool's S-curve, milestone "
              "table and client-input table as exhibits — the Reporting Studio composes them into one PDF / Word pack.")]
    sec11 = K.sec('Assemble the claim', *p11)

    # ── measured / actions / evidence ────────────────────────────────────────────────────────────────
    measured = (("Indicators come straight from the P6 file. " if nok else
                 "Indicators come from the stored analysis of your P6 update. ")
                + (f"{fin.get('id') or 'The finish milestone'} baseline {bl} vs forecast {fc} gives {d} wd"
                   + (f" (project total float {fin_tf:+d})" if fin_tf is not None else '') + '. ' if (bl and fc and d is not None) else
                   (f"The delay of {K.signed(d)} is the stored finish-milestone read. " if d is not None else ''))
                + (f"There are {nf_n:,} negative-float activities ({_p1(nf_pct)})" if nf_n else '')
                + (f", {crit_n:,} at critical float and {drv_n:,} on the driving path. " if (nf_n and crit_n and drv_n) else
                   ('. ' if nf_n else ''))
                + ((f"The {len(ci_all)} employer / client input activities (found by WBS and activity name) give, per item, "
                    f"baseline vs current finish, slip in working days and total float; "
                    + (f"{num_word(len(late_open))} open {'ones are' if len(late_open) != 1 else 'one is'} late. "
                       if late_open else "none of the open ones is late. "))
                   if nok else '')
                + ("The finish chain and its floats come from the driving-path trace (activities within "
                   f"{N.get('chain_band')} wd of the finish float). " if chain else '')
                + (f"PV {_m(F.get('pv'))} / EV {_m(F.get('ev'))} are the tool's re-derived EVM at {dd}. " if F.get('pv') else '')
                + ("CPI is 1.00 because cost is derived from progress. " if F.get('cost_derived') else '')
                + "NOT in the file: fault, weather, the contract and its notices, resources, and the days each event "
                  "caused. Those need the delay-event log, the Weather audit and a TIA / windows run (Consultant Review, "
                  "Update vs Update). Fragnet moves from the offline engine are forward-pass estimates, to be validated in "
                  "P6 F9. FIDIC references are a map by event type, not legal advice."
                + ('' if nok else ' The P6 file couldn\'t be re-read, so the client-input detail is missing.'))
    actions = [
        (f"Don't quote {d} wd as your entitlement; it's the gross slip. Isolate the employer-caused critical days with a "
         "TIA / but-for run first.") if behind else
        "Keep notifying employer events even with no slip — the float they use is worth recording.",
        (f"Open the notice log today for the {num_word(len(late_open))} late client input{'s' if len(late_open) != 1 else ''} "
         f"(due {_span(due[0], due[-1])}). Confirm a 28-day notice went for each"
         + (f", and serve continuing-event particulars for the {num_word(sum(1 for x in late_open if x.get('finish') == dd))} "
            "still open at the data date." if any(x.get('finish') == dd for x in late_open) else '.')) if (late_open and due) else '',
        (f"Trace the predecessors of {_label(head_act)} ({head_act['id']}, due {head_act['baseline_finish']}, not started). "
         f"If a client hold is behind it, the logic must show it; if not, the {fseg} chain is your delay.")
        if (behind and head_late) else '',
        next((f"Tie each open client input to the work it actually gates — e.g. {short_name(x['name'])} to the "
              f"{ties[x['id']][0][:1].lower() + ties[x['id']][0][1:]}"
              + (f", where {ties[x['id']][1]}" if ties[x['id']][1] else '') + " — before you build fragnets."
              for x in sorted(late_open, key=lambda y: not ties[y['id']][1])
              if re.search(r'\bto start\b', x.get('name') or '', re.I)), '') if late_open else '',
        ("Build the delay-event log now: event, date due, date received, activities held, correspondence reference. "
         + (f"Cover the {num_word(len(late_open))} late client input{'s' if len(late_open) != 1 else ''}"
            + (f" plus the {num_word(len(late_done))} late client item{'s' if len(late_done) != 1 else ''} already closed."
               if late_done else '.') if late_open else
            ("Start from your correspondence — the file has no late employer input to seed it." if nok else
             "Start from your correspondence, and re-import the file so its client-input activities can seed it."))),
        (f"Use windows (Update vs Update) across the {_span(due[0], dd)} updates as the spine, with one TIA fragnet per "
         "discrete event on the update in force before it.") if due else
        "Use windows (Update vs Update) on your dated updates as the spine, with a TIA fragnet per discrete event.",
        "Validate every fragnet's day count in P6 F9; the offline figure is an estimate.",
        "Run the Weather audit with the right Site Type before claiming any weather day.",
        ((f"Document any pacing on {K2_join([m['id'] for m in pacing[:3]])} now, while it's still contemporaneous, and "
          f"expect the Engineer to argue concurrency on the {fseg} chain.") if pacing and behind else ''),
        ("Price prolongation from site overheads and the cost ledger, not from this file's AC, which is derived from progress."
         if F.get('cost_derived') else "Price prolongation from time-related site overheads, not from CPI."),
        "Confirm the book (Red / Yellow), edition (1999 / 2017) and Particular Conditions, and tag each event to its clause.",
        (f"Lead the claim with the three-curve S-curve and the client-input table, stated in calendar days ({d} wd = "
         f"{cal_days} calendar days).") if (behind and cal_days is not None) else '',
    ]
    evidence = [
        K.ev('Gross slip', f"{K.signed(d).split(' (')[0]} ({fin.get('id')})" if (d is not None and fin.get('id'))
             else (K.signed(d) if d is not None else None)),
        K.ev('Baseline → forecast', f"{bl} → {fc}" if bl and fc else None),
        K.ev('In calendar days', str(cal_days) if (cal_days is not None and behind) else None),
        K.ev('Late client inputs', f"{len(late_open)} of {len(open_ci)}" if nok else None),
        K.ev('Worst input', f"{short_name(late_open[0]['name'])} {late_open[0]['slip_wd']:+d} wd / TF "
                            f"{late_open[0]['tf']:+d}" if late_open and late_open[0].get('tf') is not None else None),
        K.ev('Input float range', _frng(tfs) if tfs else None),
        K.ev('Finish-path float', (f"{fin_tf:+d}" + (f" ({_label(head_act)} {head_act['tf']:+d})" if head_act and head_act.get('tf') is not None else ''))
             if fin_tf is not None else None),
        K.ev('Deepest float', f"{deep0['tf']:+d} ({_label(deep0)})" if deep0 and deep0.get('tf') is not None else None),
        K.ev('Negative float', f"{nf_n:,} ({_p1(nf_pct)})" if nf_n else None),
        K.ev('Driving path', f"{drv_n:,} activities" if drv_n else None),
        K.ev('Client items completed late', f"{len(late_done)} ({_rng([x['slip_wd'] for x in late_done])} wd, closed)" if late_done else None),
        K.ev('PV / EV', f"{_m(F.get('pv'))} / {_m(F.get('ev'))}" if F.get('pv') else None),
        K.ev('SPI / CPI', f"{K.ratio(F.get('spi'))} / {K.ratio(F.get('cpi'))}" + (' (cost from progress)' if F.get('cost_derived') else '')),
        K.ev('Notice', '28 days (FIDIC)'),
        K.ev('Method', 'Windows + TIA (MIP 3.3 / 3.7)'),
    ]
    drills = [K.drill('q03', 'Is the delay real, and how much is contractor vs owner / consultant?'),
              K.drill('q10', 'Is late client / consultant input driving the delay?'),
              K.drill('q04', f"What's driving the date, and why does {_label(deep0)} read {deep0['tf']:+d}?"
                      if deep0 and deep0.get('tf') is not None and fin_tf is not None and deep0['tf'] < fin_tf else
                      "What's driving the date?"),
              K.drill('q14', 'Was any of it weather? Calendars and weather days'),
              K.drill('q05', f"How do I recover the ~{d} days?") if behind else None]
    a = K.A2(head, [sec1, sec2, sec3, sec4, sec5, sec6, sec7, sec8, sec9, sec10, sec11], pills=pills,
             measured=measured, actions=actions, evidence=evidence, drilldowns=drills,
             tools=[K.tool('tia', 'Run the time-impact analysis')])
    a['thinking'] = thinking[:4] or ['Read the stored finish position and float checks for this update']
    return a
