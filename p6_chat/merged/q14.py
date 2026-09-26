"""q14 — Weather & calendars: working days, weather lost, and the adjusted finish.

Covers: the working days the calendars give (the driving path's own working-day length, the calendar-day
spans behind it, and why a two-calendar compare matters on THIS network), whether procurement / client
supply durations respect holidays and shutdowns, weather days lost and the weather-adjusted finish for the
site type, crew-days that weather would swallow, and how to prove a shutdown wasn't the contractor's delay.

Honesty: the P6 extract carries no calendar definitions, no weather and no resources. Everything the file
does carry (calendar count, critical-path length, floats, finish dates, the chain's trades, client supply
dates, activity names) is read and used; the rest is routed to the Calendar Audit / Bad-Weather view,
Productivity & Resource Intelligence and Consultant Review. Nothing project-specific is hardcoded.
"""
import re
from datetime import datetime

from . import _kit2 as K

_NUM_WORDS = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight',
              9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve'}

# WBS words that name a trade / work package (the deepest matching WBS level is the "trade").
_TRADE_RE = re.compile(r'\b(works?|installations?|erection|civil|mechanical|electrical|steel|structur\w*|cables?|'
                       r'finish(?:es|ing)|mep|piling|foundations?|concrete|architectur\w*|commissioning|hvac|'
                       r'plumbing|infra\w*|roads?|earthworks?|landscap\w*|fit[- ]?out)\b', re.I)
# Work-type vocabulary for a readable summary of what a front physically is (primary words first).
_PRIMARY = [(r'\bpil(?:e|es|ing)\b', 'piling'), (r'excavat', 'excavation'),
            (r'\bsoil\b|backfill|compaction|earthwork', 'soil works'), (r'column', 'columns'),
            (r'\bbeams?\b', 'beams'), (r'\bsog\b|slab', 'slabs'), (r'\brafts?\b', 'raft'),
            (r'footing|foundation', 'foundations'), (r'\bwalls?\b', 'walls'), (r'\broof', 'roofing'),
            (r'cladding|fa[cç]ade|(?:silos?|roof|wall)\s+sheets?\b|sheeting', 'sheeting / cladding'),
            (r'catwalk|steel', 'steelwork'), (r'\bcables?\b|conduct|conduit|wiring', 'cabling'),
            (r'terminat', 'terminations'), (r'conveyor|roller|equipment|assembl', 'equipment installation'),
            (r'asphalt|paving', 'paving')]
_SECONDARY = [(r'concrete|pour', 'concrete'), (r'\btests?\b|testing', 'testing'),
              (r'waterproof|insulation', 'insulation / waterproofing'), (r'paint|coating', 'coatings')]
# Weather exposure: ground / concrete work, and lifting / work at height.
_GROUND_RE = re.compile(r'\bpil(?:e|es|ing)\b|excavat|\bsoil\b|backfill|earthwork|concrete|pour|\brafts?\b|\bsog\b|'
                        r'slab|footing|foundation|asphalt|paving|formwork|shuttering|\bfw\b|\brft\b|rebar|reinforc|'
                        r'column|\bbeams?\b|grout|compaction|blinding', re.I)
_HEIGHT_RE = re.compile(r'\broof|cladding|fa[cç]ade|scaffold|crane|\blift|catwalk|erection|steel|\btowers?\b|mast|'
                        r'gantry|\bsheets?\b', re.I)
_TEST_RE = re.compile(r'\btests?\b|testing', re.I)
# Client supply (deliveries / free-issue material), as opposed to approvals and area releases.
_SUPPLY_RE = re.compile(r'^(?:deliver\w*|supply|shipment)\b|\bdelivery (?:for|of)\b|\b(?:shipment|equipment|'
                        r'materials?|accessories|free[- ]issue|furnished)\b', re.I)
_SHUTDOWN_RE = re.compile(r'\b(shut[- ]?down|suspension|site stop|stoppage|site closure|holiday break)\b', re.I)
_WEATHER_RE = re.compile(r'\b(weather|rain ?days?|inclement|monsoon)\b', re.I)
_WATERSIDE_RE = re.compile(r'\b(quays?|harbou?r|port|coastal|sea ?wall|offshore|breakwater|wharf|docks?|marine|'
                           r'shoreline|jetty|berth)\b', re.I)


# ── small helpers ────────────────────────────────────────────────────────────────

def _word(n):
    return _NUM_WORDS.get(n, f"{n:,}") if isinstance(n, int) else str(n)


def _date(s):
    if not s:
        return None
    for fmt in ('%d-%b-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(s).strip()[:11], fmt)
        except ValueError:
            continue
    return None


def _fmt(dt):
    return dt.strftime('%d-%b-%Y') if dt else None


def _sg(n):
    """Signed whole number: '+5', '-3', '0'."""
    if n is None:
        return '—'
    n = round(n)
    return f"{n:+d}" if n else '0'


def _is_ms(x):
    return 'Milestone' in (x.get('type') or '')


def _nm(x):
    """An activity's name with P6's stray double spaces collapsed."""
    return ' '.join(str((x.get('name') if isinstance(x, dict) else x) or '').split())


def _last_wbs(x):
    parts = [p for p in (x.get('wbs') or '').split(' / ') if p]
    return parts[-1] if parts else ''


def _tag(x):
    """'name, <last WBS level>' unless the WBS level adds nothing the name doesn't already say."""
    last = _last_wbs(x)
    toks = [t for t in re.findall(r'[A-Za-z]{4,}', last.lower())]
    if not last or any(t in _nm(x).lower() for t in toks):
        return _nm(x)
    return f"{_nm(x)}, {last}"


def _trade_of(wbs):
    """(trade label, [location parts below it]) from a WBS path: the deepest level naming a trade."""
    parts = [p for p in (wbs or '').split(' / ') if p]
    for i in range(len(parts) - 1, 0, -1):
        if _TRADE_RE.search(parts[i]):
            return parts[i], parts[i + 1:]
    if len(parts) == 1:
        return parts[0], []
    return (' / '.join(parts[-2:]) if parts else '(no WBS)'), []


def _trades(chain):
    """The finish chain's trades in order of first appearance: [{label, locs, items}]."""
    out = {}
    for x in chain or []:
        if _is_ms(x):
            continue
        label, locs = _trade_of(x.get('wbs'))
        t = out.setdefault(label, {'label': label, 'locs': [], 'items': []})
        loc = ' / '.join(locs)
        if loc and loc not in t['locs']:
            t['locs'].append(loc)
        t['items'].append(x)
    return list(out.values())


def _locs_text(locs):
    if not locs:
        return ''
    split = [l.split(' / ') for l in locs]
    firsts = {s[0] for s in split}
    if len(firsts) == 1 and any(len(s) > 1 for s in split):
        tails = [' / '.join(s[1:]) for s in split if len(s) > 1]
        return f"{split[0][0]} — {', '.join(tails[:4])}"
    return ', '.join(locs[:4])


def _trade_text(t, detail=None):
    """'Civil Works (Zone A — Block 1, Block 2: piling, slabs)' — locations and an optional work summary."""
    inner = ': '.join(x for x in (_locs_text(t['locs']), ', '.join(detail or [])) if x)
    return t['label'] + (f" ({inner})" if inner else '')


def _work_types(names, limit=6):
    seen = []
    for nm in names:
        prim = [lab for rx, lab in _PRIMARY if re.search(rx, nm, re.I)]
        labs = prim or [lab for rx, lab in _SECONDARY if re.search(rx, nm, re.I)]
        for lab in labs:
            if lab not in seen:
                seen.append(lab)
    return seen[:limit]


def _join(items, last='and'):
    items = [i for i in items if i]
    if len(items) <= 1:
        return ''.join(items)
    return ', '.join(items[:-1]) + f" {last} " + items[-1]


def _finish(F, N, nok):
    """(name, id, forecast, baseline, tf, slip_wd) — from the file when readable, else the stored facts."""
    ck = ((F.get('audit') or {}).get('cpli') or {}).get('kpis') or {}
    fin = (N.get('finish_milestone') or {}) if nok else {}
    fc = fin.get('finish') or F.get('forecast_finish') or _fmt(_date(ck.get('finish_date')))
    bl = fin.get('baseline_finish') or F.get('baseline_finish')
    slip = fin.get('slip_wd') if fin.get('slip_wd') is not None else F.get('delay_days')
    tf = fin.get('tf') if fin.get('tf') is not None else ck.get('project_total_float_days')
    return fin.get('name'), fin.get('id'), fc, bl, tf, (None if slip is None else round(slip))


def _cpl(F):
    ck = ((F.get('audit') or {}).get('cpli') or {}).get('kpis') or {}
    cpl = ck.get('critical_path_length_days')
    return (round(cpl) if isinstance(cpl, (int, float)) else None), ck


# ── the answer ───────────────────────────────────────────────────────────────────

def build(F, N, role):
    nok = bool(N and N.get('ok'))
    d = F.get('delay_days')
    behind, ahead = (d or 0) > 0, (d or 0) < 0
    drv = K.main_driver(F)
    thinking = []
    ncal = F.get('calendar_count')
    ncal = int(ncal) if isinstance(ncal, (int, float)) else None
    cal_phrase = f"{_word(ncal)} calendar{'s' if ncal != 1 else ''}" if ncal else 'its calendars'

    fname, fid, ff, bf, ftf, slip = _finish(F, N, nok)
    cpl, ck = _cpl(F)
    dd_s = F.get('data_date') or (N.get('data_date') if nok else None)
    dd, ffd, bfd = _date(dd_s), _date(ff), _date(bf)
    cd_to_ff = (ffd - dd).days if (dd and ffd) else None
    cd_to_bf = (bfd - dd).days if (dd and bfd) else None
    cd_slip = abs((ffd - bfd).days) if (ffd and bfd) else None
    wd_to_bf = (cpl - slip) if (cpl is not None and slip is not None) else (
        cpl + ftf if (cpl is not None and ftf is not None) else None)
    fname_txt = f"{fname} ({fid})" if (fname and fid) else (fname or 'the finish milestone')

    chain = (N.get('chain') or []) if nok else []
    trades = _trades(chain)
    deep = [x for x in ((N.get('deepest') or []) if nok else []) if ftf is not None and x['tf'] < ftf - 1][:2]
    acts = ((N.get('kb_view') or {}).get('activities') or []) if nok else []
    names = [a.get('name') or '' for a in acts]
    shutdowns = [_nm(n) for n in names if _SHUTDOWN_RE.search(n)]
    weather_acts = [_nm(n) for n in names if _WEATHER_RE.search(n)]
    waterside = []
    for n in names:
        if _WATERSIDE_RE.search(n) and _nm(n) not in waterside:
            waterside.append(_nm(n))

    # ── 1. net working days per calendar ────────────────────────────────────────
    p1 = []
    if cpl is not None and ff:
        lead = (f"**This file has {cal_phrase}. On the driving path you have {cpl:,} working days from the data date "
                f"({dd_s}) to the {ff} forecast")
        if wd_to_bf is not None and slip:
            lead += (f", against {wd_to_bf:,} to the {(bf + ' ') if bf else ''}baseline finish. The difference is the "
                     f"{abs(slip)} wd {'slip' if slip > 0 else 'margin'}")
        lead += ". The split by calendar comes from the Calendar Audit, not from this extract.**"
    else:
        lead = (f"**This file has {cal_phrase}. From the {dd_s} data date the forecast finish"
                + (f" ({ff}) is {cd_to_ff} calendar days away" if cd_to_ff is not None else '')
                + (f" and sits {abs(slip)} wd {'behind' if slip > 0 else 'ahead of'} the {bf or 'baseline'} baseline"
                   if slip else '')
                + ". The working days each calendar gives come from the Calendar Audit — this update has no stored "
                  "critical-path length to read them from.**")
    p1.append(lead)
    if not nok:
        p1.append(K.network_note(N))
    p2 = []
    if cpl is not None and ck.get('cpli') is not None and ftf is not None:
        p2.append(f"The {cpl:,} is P6's own critical-path length in working days, and it is what the CPLI of "
                  f"{K.ratio(ck.get('cpli'))} is built on: ({cpl:,} {'-' if ftf < 0 else '+'} {abs(ftf)}) ÷ {cpl:,}.")
    rate_all = rate_slip = None
    if cpl and cd_to_ff and cd_to_ff > 0:
        rate_all = cpl / (cd_to_ff / 7.0)
        if rate_all <= 7.05:
            p2.append(f"Those {cpl:,} wd span {cd_to_ff:,} calendar days, so the driving calendar averages about "
                      f"{rate_all:.1f} working days a week.")
        else:
            rate_all = None
    if rate_all and slip and cd_slip:
        rate_slip = abs(slip) / (cd_slip / 7.0)
        if rate_slip <= 7.05:
            span = f"{bf} to {ff}" if slip > 0 else f"{ff} to {bf}"
            if rate_slip < rate_all - 0.25:
                p2.append(f"The average isn't even across the year, though: the {abs(slip)} wd from {span} take "
                          f"{cd_slip} calendar days (about {rate_slip:.1f} a week), so that stretch carries more "
                          "non-working days.")
            elif rate_slip > rate_all + 0.25:
                p2.append(f"The {abs(slip)} wd from {span} take {cd_slip} calendar days (about {rate_slip:.1f} a week), "
                          "so that stretch carries fewer non-working days than the average.")
            else:
                p2.append(f"The {abs(slip)} wd from {span} take {cd_slip} calendar days (about {rate_slip:.1f} a week), "
                          "in line with the average.")
    tail = ("The extract doesn't carry each calendar's name, work week, holidays or reduced-hours days. The P6 "
            "Calendar Audit reads those")
    if len(trades) >= 2:
        tail += (f", and they matter here because the driving path crosses trades: the {_trade_text(trades[0])} "
                 f"hand over to {_join([t['label'] for t in trades[1:5]])}. If those trades sit on "
                 "different calendars, the same duration lands on different dates.")
    else:
        tail += ", and they decide how many real working days every duration on the driving path gets."
    p2.append(tail)
    rows = []
    if dd_s and ff:
        rows.append(['Data date → forecast finish', f"{dd_s} → {ff}",
                     (f"{cpl:,} wd" if cpl is not None else 'Calendar Audit')
                     + (f" ({cd_to_ff:,} calendar days)" if cd_to_ff is not None else ''),
                     'Critical-path length (CPLI basis)' if cpl is not None else 'Plain date arithmetic'])
    if dd_s and (bf or wd_to_bf is not None):
        src = 'Plain date arithmetic'
        if wd_to_bf is not None and slip:
            src = f"{cpl:,} {'less' if slip > 0 else 'plus'} the {abs(slip)} wd {'slip' if slip > 0 else 'margin'}"
            if ftf is not None and round(ftf) == -slip:
                src += f" (= the {_sg(ftf)} project float)"
        rows.append(['Data date → baseline finish', f"{dd_s} → {bf or 'baseline'}",
                     (f"{wd_to_bf:,} wd" if wd_to_bf is not None else 'Calendar Audit')
                     + (f" ({cd_to_bf:,} calendar days)" if cd_to_bf is not None else ''), src])
    if slip and (bf or ff):
        b_, f_ = bf or 'baseline', ff or 'forecast'
        rows.append(['Baseline → forecast finish' if slip > 0 else 'Forecast → baseline finish',
                     f"{b_} → {f_}" if slip > 0 else f"{f_} → {b_}",
                     f"{abs(slip)} wd" + (f" ({cd_slip} calendar days)" if cd_slip is not None else ''),
                     f"{fname_txt} {'slip' if slip > 0 else 'margin'}" if fid else 'Stored delay to completion'])
    rows.append([f"Each of the {ncal} calendars" if ncal else 'Each calendar', 'Data date → finish',
                 'Not in this extract', 'P6 Calendar Audit'])
    s_days = K.sec('Net working days per calendar', *(p1 + [' '.join(p2)]),
                   table=K.tbl(['Window (driving path)', 'From → to', 'Working days', 'Where it comes from'], rows,
                               note="Every value is from the file or is plain date arithmetic on it. The per-week "
                                    "averages are readings, not the calendars' definitions."))
    thinking.append(f"Counted {ncal or 'the'} calendar{'s' if ncal != 1 else ''} and read the "
                    + (f"{cpl:,}-wd critical-path length against the finish dates" if cpl is not None
                       else "finish dates as calendar-day spans (no stored critical-path length)"))

    # ── 2. comparing two calendars ──────────────────────────────────────────────
    cmp_paras = []
    if len(trades) >= 2:
        t1, t2 = trades[0], trades[1]
        wt = _work_types([x['name'] for x in t1['items']])
        cmp_paras.append(
            f"Start with the calendars that carry the finish path: the one under the {_trade_text(t1, wt)}, and the "
            f"one under the {_trade_text(t2)}, which takes over at "
            f"{_nm(t2['items'][0])} ({t2['items'][0]['id']}). If they differ, the Calendar Audit lists every "
            "non-working day in each and highlights only where they differ: extra holidays, reduced-hours days, a "
            "different weekly day off. That difference, in days, is real schedule, not rounding.")
    elif nok:
        cmp_paras.append("The finish chain sits in one trade, so start the compare with its calendar against the "
                         "general/office calendar. The Calendar Audit lists every non-working day in each and "
                         "highlights only where they differ: extra holidays, reduced-hours days, a different weekly "
                         "day off.")
    else:
        cmp_paras.append("Start with the calendar under the work that sets the finish"
                         + (f" ({drv['name']} carries the weighted gap)" if drv else '')
                         + " against the general/office calendar. The Calendar Audit lists every non-working day in "
                           "each and highlights only where they differ: extra holidays, reduced-hours days, a "
                           "different weekly day off.")
    if deep:
        gaps = sorted({ftf - x['tf'] for x in deep})
        span = f"{gaps[0]}" if len(gaps) == 1 else f"{gaps[0]}-{gaps[-1]}"
        items = [f"{_sg(x['tf'])} ({_tag(x)})" for x in deep]
        cmp_paras.append(
            f"This file gives you a concrete reason to run the compare. The deepest float{'s are' if len(deep) > 1 else ' is'} "
            f"{_join(items)}, yet the project sits at {_sg(ftf)}. P6 states each activity's float in that activity's "
            f"own calendar. So a float {span} days deeper than the finish is often a calendar difference, or an "
            "intermediate constraint, rather than extra delay. The two-calendar compare tells you which it is before "
            f"anyone reports {_sg(deep[0]['tf'])} as the headline.")
    elif nok and ftf is not None and (N.get('deepest') or []):
        cmp_paras.append(f"The deepest float in the network ({_sg(N['deepest'][0]['tf'])}) matches the finish "
                         f"({_sg(ftf)}), so floats read consistently across calendars here; the compare still matters "
                         "wherever one trade hands over to another.")
    s_cmp = K.sec('Comparing two calendars', *cmp_paras)
    if nok:
        thinking.append(f"Traced the {N.get('chain_count', len(chain))}-activity finish chain across {len(trades)} "
                        f"trade{'s' if len(trades) != 1 else ''}"
                        + (f" and compared its deepest float ({_sg(deep[0]['tf'])}) with the finish ({_sg(ftf)})"
                           if deep else ''))

    # ── 3. procurement / shipping vs holidays and shutdowns ─────────────────────
    proc = next((x for x in (F.get('disciplines') or []) if re.search(r'procure|purchas|supply', x.get('name') or '', re.I)),
                None)
    proc_n = sum(1 for a in acts if (a.get('wbs_path') or '').split(' / ')[0] == (proc or {}).get('name')) if proc else 0
    client = (N.get('client_inputs') or []) if nok else []
    supply = [x for x in client if _SUPPLY_RE.search(x.get('name') or '')]
    fixed = [x for x in supply if not x['done'] and (x.get('slip_wd') or 0) <= 0 and x.get('tf') == 0]
    sup_late_open = [x for x in supply if not x['done'] and (x.get('slip_wd') or 0) > 0]
    sup_late_done = [x for x in supply if x['done'] and (x.get('slip_wd') or 0) > 0]
    pr = []
    lead = "It depends on the calendar those activities sit on"
    if proc:
        done_enough = (proc.get('actual') or 0) >= 90
        if done_enough and (fixed or sup_late_open):
            lead += ", and on this file the question has moved from your procurement to the client's"
        lead += (f". {proc['name']} is {proc['actual']}% complete against {proc['planned']}% planned"
                 + (f" ({proc_n} activities, about {round((proc.get('weight') or 0) * 100)}% of the weight)" if proc_n
                    else f" (about {round((proc.get('weight') or 0) * 100)}% of the weight)"))
        lead += (", so your own buying barely moves the finish now." if done_enough and (proc.get('weight') or 0) <= 0.05
                 else '.')
    else:
        lead += ". The file has no separate procurement discipline, so check the delivery activities directly."
    bits = [lead]
    if fixed:
        by_date = {}
        for x in fixed:
            by_date.setdefault(x['finish'], []).append(_nm(x))
        dates = sorted(by_date, key=lambda s: _date(s) or datetime.max)
        grp = [f"{_join(by_date[dt])} {'are all' if len(by_date[dt]) > 2 else ('are both' if len(by_date[dt]) == 2 else 'is')} "
               f"on {dt}" for dt in dates[:3]]
        bits.append("What's still ahead is client supply. " + '; '.join(grp) + '.')
        bits.append(f"{'All ' + _word(len(fixed)) if len(fixed) > 2 else ('Both' if len(fixed) == 2 else 'It')} "
                    f"sit{'s' if len(fixed) == 1 else ''} on {'their' if len(fixed) > 1 else 'its'} baseline "
                    f"date{'s' if len(fixed) > 1 else ''} with zero float, which usually points to fixed (constrained) "
                    "dates rather than calculated ones; confirm that, because a fixed date hides slip.")
    if sup_late_open:
        bits.append(f"{_join([_nm(x) for x in sup_late_open[:3]])} "
                    f"{'is' if len(sup_late_open) == 1 else ('are both' if len(sup_late_open) == 2 else 'are')} still open "
                    f"at the data date, {min(x['slip_wd'] for x in sup_late_open)}"
                    + (f"-{max(x['slip_wd'] for x in sup_late_open)}" if len(sup_late_open) > 1 else '')
                    + " wd past baseline.")
    if sup_late_done:
        lo, hi = min(x['slip_wd'] for x in sup_late_done), max(x['slip_wd'] for x in sup_late_done)
        bits.append(f"{_word(len(sup_late_done)).capitalize()} earlier client deliver{'y' if len(sup_late_done) == 1 else 'ies'} "
                    f"arrived {lo}{'' if lo == hi else f'-{hi}'} wd late.")
    pr.append(' '.join(bits))
    chk = ("Make two checks. First, activities that follow a client delivery (erection, installation) must sit on a "
           "site calendar that takes holidays out. Second, any supplier lead time modelled as a duration should run on "
           "a 7-day calendar if the supplier works through your holidays. Put a lead time on a 5- or 6-day calendar and "
           "it silently stretches across every holiday.")
    if nok:
        chk += (" The file doesn't name a shutdown, so there is nothing of that kind to check yet." if not shutdowns else
                f" The file names {len(shutdowns)} shutdown-type activit{'y' if len(shutdowns) == 1 else 'ies'} "
                f"({_join(shutdowns[:2])}); any procurement or shipping activity spanning it must run on a calendar "
                "that carries the same break.")
    pr.append(chk)
    s_proc = K.sec('Do procurement / shipping durations account for holidays and shutdowns?', *pr)
    thinking.append(f"Read {proc['name']} ({proc['actual']}% vs {proc['planned']}% planned) for the procurement check"
                    if proc else f"Looked for a procurement line among the {len(F.get('disciplines') or [])} "
                                 "disciplines (none)")
    if nok:
        thinking.append(f"Checked {len(client)} client inputs for supply dates ({len(supply)} deliveries) and scanned "
                        f"{len(acts):,} activity names for shutdown, weather and site-exposure words")

    # ── 4. weather days lost this month and finish impact ───────────────────────
    pos = (f"the {_sg(slip)} wd and the {ff} forecast are" if (slip and slip > 0 and ff) else
           (f"the {abs(slip)} wd margin and the {ff} forecast are" if (slip and ff) else
            (f"the {ff} forecast is" if ff else 'the forecast is')))
    wp = [f"**This P6 file doesn't measure weather, so {pos} weather-blind. The Bad-Weather view sizes the loss and "
          "the finish impact once you set the Site Type.**"]
    w2 = (f"Nothing in the schedule counts weather unless one of the {cal_phrase} carries a weather allowance as "
          "non-working days, and the Calendar Audit shows whether one does. So this month's lost days aren't in the "
          "file either.")
    if weather_acts:
        w2 += (f" The file does name {len(weather_acts)} weather-related activit{'y' if len(weather_acts) == 1 else 'ies'} "
               f"({_join(weather_acts[:2])}); check whether that is an allowance or ordinary scope.")
    w2 += (" The Bad-Weather-effect view counts adverse-weather days from the data date and shows, as a waterfall, "
           "how they push the forecast out.")
    ground = [x for x in chain if not _is_ms(x) and _GROUND_RE.search(x['name'])]
    gtr = _trades(ground)
    if gtr:                          # the ground front = the trade holding most of the ground / concrete work
        gmain = max(gtr, key=lambda t: len(t['items']))
        ground = gmain['items']
    height = [x for x in chain if not _is_ms(x) and _HEIGHT_RE.search(x['name']) and not _TEST_RE.search(x['name'])
              and x not in ground]
    if ground or height:
        w2 += " On this project, what matters is when the exposed work falls."
        if ground:
            g_last = max(ground, key=lambda x: _date(x['finish']) or datetime.min)
            gw = _work_types([x['name'] for x in ground])
            w2 += (f" The {_trade_text(gmain, gw)} on the finish chain runs from now to its last activity, "
                   f"{_nm(g_last)}, on {g_last['finish']}.")
        if height:
            hs = [f"{_nm(x)} ({x['finish']})" for x in height[:2]]
            w2 += (f" {_join(hs)}, which {'are' if len(hs) > 1 else 'is'} lifting and work at height, sit"
                   f"{'' if len(hs) > 1 else 's'} just before the finish"
                   + (f", with {len(height) - 2} more erection and steel activities after them." if len(height) > 2 else '.'))
        tfs = [x['tf'] for x in chain if x.get('tf') is not None]           # the chain only — deeper ones sit off it
        if tfs and max(tfs) < 0:
            w2 += (f" That chain is already at {_sg(max(tfs))} to {_sg(min(tfs))}, so every weather day lost on it goes "
                   "straight onto the finish.")
        elif tfs:
            w2 += (f" That chain holds {_sg(min(tfs))} wd of float at its tightest, so weather days first eat that "
                   "margin before they reach the finish.")
    wp.append(w2)
    s_wx = K.sec('Weather days lost this month and finish impact', *wp)

    # ── 5. weather-adjusted finish for the site type ────────────────────────────
    st = ("The Site Type drives the adverse-weather criteria, so set it to the real site. The built-in default is "
          "Desert / inland civil, which doesn't stop work for wind.")
    if waterside:
        st += (f" The file carries waterside items ({_join(waterside[:2])}). If the site is port-side or on the coast, "
               "use the Marine / Port or Coastal / general preset, because on the wrong preset an exposed site can "
               "read zero weather.")
    else:
        st += (" Pick from Desert / inland civil, Marine / Port, Coastal / general or Building / enclosed; on the wrong "
               "preset an exposed site can read zero weather.")
    st += (" With multi-year data the view builds a typical year and produces a weather-adjusted finish. That date "
           f"sits at or beyond {ff or 'the forecast finish'} unless the calendars already allow for weather. Treat "
           f"{ff or 'the current forecast'} as the no-weather case, and carry the weather-adjusted date into any "
           "recovery commitment or claim.")
    if ahead and slip:
        st += f" On this file the {abs(slip)} wd margin is the first thing the weather days will eat."
    s_adj = K.sec('Weather-adjusted finish for the site type', st)

    # ── 6. added crew-days lost to weather ──────────────────────────────────────
    late_open = (N.get('client_inputs_late_open') or []) if nok else []
    g_types = _work_types([x['name'] for x in ground], 4)
    h_types = [t for t in _work_types([x['name'] for x in height], 3) if t not in g_types]
    exposed = _join(g_types) + (f", then {_join(h_types)} at height" if h_types else '')
    if behind:
        where = (f"the {_trade_text(trades[0])} chain" if trades else
                 (f"the chain that sets the finish ({drv['name']} carries the weighted gap)" if drv else
                  'the chain that sets the finish'))
        cr = f"Recovery has to land on {where}" + (" and on closing the late client inputs" if late_open else '') + '.'
        if exposed:
            cr += f" Extra crews would therefore go to largely exposed work: {exposed}."
    elif ahead:
        cr = (f"You're {abs(d)} wd ahead, so extra crews aren't needed to hold the date. If you add any to protect the "
              "margin, the same rule applies.")
    else:
        cr = "Any crews added to hold the date go onto the chain that sets the finish."
    cr += (" Crew-days added in weather windows get paid for and produce nothing. I can't size that from this file: the "
           "data I'm reading carries no crew sizes or man-hours to multiply against weather days. Take the "
           "exposed-days count from the Bad-Weather view and the crew plan from Productivity & Resource Intelligence, "
           "then price the increase net of the weather loss.")
    s_crew = K.sec('Added crew-days that would just be lost to weather', cr)

    # ── 7. proving the shutdown wasn't your delay ───────────────────────────────
    if nok and shutdowns:
        sd1 = (f"The file names {len(shutdowns)} shutdown-type activit{'y' if len(shutdowns) == 1 else 'ies'} "
               f"({_join(shutdowns[:3])}). Proving it wasn't your delay is forensic work, not a single metric.")
    elif nok:
        sd1 = ("First, the honest point: the data I'm reading doesn't identify a shutdown. No shutdown activity appears "
               "in the file's activity list, and calendar blocks are read by the Calendar Audit, not this extract. If "
               "there was one (a site stop, an access closure, a client-ordered halt), proving it is forensic work, not "
               "a single metric.")
    else:
        sd1 = ("I can't scan the activity list this time, so I can't say whether a shutdown is named in the file. "
               "Either way, proving one is forensic work, not a single metric.")
    sd1 += (" Model the stop as a dated non-working exception in the right calendar, or as an employer event if the "
            "client ordered it. Keep the weather day-list and site diaries as the contemporaneous record. Then run "
            "Consultant Review (but-for) on the update before the stop, to show the finish moved because of the stop "
            "and not your production rate.")
    sd2 = ''
    if behind and late_open:
        lo = [f"{_nm(x)} {_sg(x['slip_wd'])} wd" for x in late_open[:2]]
        sd2 = (f"The same test settles the bigger question on this job: the late client inputs ({_join(lo)}) against "
               + (f"the {trades[0]['label']} chain." if trades else "the contractor's own driving chain."))
        sd2 += ' '
    sd2 += ("The offline engine is forward-pass only. It drafts and estimates; P6 F9 and the but-for run are what prove "
            "it. Use its output to support a notice or an EOT, not as proof on its own.")
    s_sd = K.sec("Proving the shutdown wasn't your delay", sd1, sd2)

    # ── pills / measured / actions / evidence ───────────────────────────────────
    pills = [K.pill(f"{ncal} calendars in the file", 'accent') if ncal else None,
             K.pill(f"driving path: {cpl:,} wd to {ff}", 'neutral') if (cpl is not None and ff) else None,
             (K.pill(f"{slip} wd slip = {cd_slip} calendar days", 'danger') if slip > 0 else
              K.pill(f"{abs(slip)} wd margin = {cd_slip} calendar days", 'success')) if (slip and cd_slip) else None,
             K.pill(f"float {_sg(deep[0]['tf'])} vs {_sg(ftf)}: check calendars", 'warning') if deep else None,
             K.pill('Weather: not in the P6 numbers', 'warning'),
             K.pill('Needs Site Type set', 'accent'),
             K.pill('No resource data in this read', 'warning'),
             (K.pill('No shutdown found in the file', 'neutral') if not shutdowns else
              K.pill(f"{len(shutdowns)} shutdown activit{'y' if len(shutdowns) == 1 else 'ies'} named", 'warning'))
             if nok else None]

    m = [f"The calendar count ({ncal}) is read from the file." if ncal else '']
    if cpl is not None:
        m.append(f"For working days, {cpl:,} is P6's critical-path length from the {dd_s} data date to the "
                 f"{ff or 'forecast'} finish, the CPLI basis"
                 + (f" (({cpl:,} {'-' if ftf < 0 else '+'} {abs(ftf)}) ÷ {cpl:,} = {K.ratio(ck.get('cpli'))})"
                    if (ftf is not None and ck.get('cpli') is not None) else '') + '.')
        if wd_to_bf is not None and slip:
            m.append(f"{wd_to_bf:,} is {cpl:,} {'less' if slip > 0 else 'plus'} the {abs(slip)} wd "
                     f"{'slip' if slip > 0 else 'margin'}.")
    spans = [str(x) for x in (cd_to_ff, cd_to_bf, cd_slip) if x is not None]
    if spans:
        m.append(f"The calendar-day spans ({' / '.join(spans)}) are plain date arithmetic.")
    m.append("Each calendar's work week, holidays and reduced-hours days are read by the P6 Calendar Audit and are "
             "not in this extract.")
    if nok:
        m.append("Floats" + (f" ({_sg(ftf)} at the finish" + (f", {', '.join(_sg(x['tf']) for x in deep)} deepest)"
                                                                if deep else ')') if ftf is not None else '')
                 + " and client-delivery dates come from the activity data; shutdown, weather and waterside words are "
                   "matched on the activity names.")
    blind = [f"SPI {K.ratio(F.get('spi'))}" if F.get('spi') is not None else '',
             f"the {_sg(d)} wd" if d else 'the delay', f"the {ff} finish" if ff else 'the forecast finish']
    m.append("Weather days are the days meeting the chosen Site Type's adverse-weather criteria in a typical year, "
             "counted from the data date and pushed through the driving calendar (the waterfall). None of that is in "
             f"{_join(blind, 'or')}. Crew-day loss needs resources, which this read doesn't carry. A shutdown defence is "
             "a but-for comparison in Consultant Review.")
    measured = ' '.join(x for x in m if x)

    t_first = [_trade_text(t) for t in trades[:2]]
    actions = [
        f"Run the P6 Calendar Audit and read net working days for each of the {ncal or ''} calendars".replace('  ', ' ')
        + (f", starting with the one under the {t_first[0]} and the one under the {trades[1]['label']}." if len(trades) >= 2
           else '.'),
        ("Compare those two calendars side by side." + (f" If they differ, that explains the "
                                                       f"{' / '.join(_sg(x['tf']) for x in deep)} floats against the "
                                                       f"{_sg(ftf)} finish." if deep else '')) if len(trades) >= 2 else
        "Compare the driving-path calendar with the general calendar side by side.",
        (f"Check the calendar on activities that follow client deliveries ({_join([_nm(x) for x in (fixed + sup_late_open)[:3]])})"
         + (f", and whether the {len(fixed)} zero-float delivery date{'s are' if len(fixed) > 1 else ' is'} fixed constraints."
            if fixed else '.')) if (fixed or sup_late_open) else
        "Check that procurement and shipping activities sit on a calendar that carries the holidays.",
        "Open the Bad-Weather view, set the Site Type to the real site"
        + (" (Marine / Port or Coastal / general if waterside)" if waterside else '') + ", and read weather days and the "
        "weather-adjusted finish.",
        f"Carry the weather-adjusted finish, not {ff or 'the current forecast'}, into recovery commitments and any claim"
        + (f", and state EOT in calendar days ({slip} wd = {cd_slip} calendar days)." if (slip and slip > 0 and cd_slip) else '.'),
        (f"Before adding crews to the {trades[0]['label']} chain" if (behind and trades) else "Before adding crews")
        + ", size the crew-days that fall in weather windows. Resource-load the file, or use Productivity & Resource "
          "Intelligence, so the loss can be priced.",
        "If a shutdown occurred, model it as a dated exception or employer event, keep the diaries and the weather list, "
        "and prove it with a Consultant Review but-for.",
    ]
    evidence = [K.ev('Calendars', ncal), K.ev('Data date', dd_s),
                K.ev('Driving path', (f"{cpl:,} wd" + (f" ({cd_to_ff:,} calendar days)" if cd_to_ff is not None else ''))
                     if cpl is not None else None),
                K.ev('To baseline finish', f"{wd_to_bf:,} wd" if wd_to_bf is not None else None),
                K.ev('Slip' if (slip or 0) > 0 else 'Margin',
                     (f"{abs(slip)} wd" + (f" = {cd_slip} calendar days" if cd_slip is not None else '')) if slip else None),
                K.ev('Forecast (weather-blind)', ff), K.ev('Baseline finish', bf),
                K.ev('CPLI', K.ratio(ck.get('cpli')) if ck.get('cpli') is not None else None),
                K.ev('Deepest float', f"{_sg(deep[0]['tf'])} ({_tag(deep[0])})" if deep else None),
                K.ev('Procurement', f"{proc['actual']}% vs {proc['planned']}%" if proc else None),
                K.ev('Client deliveries at zero float',
                     f"{len(fixed)} on baseline dates ({', '.join(sorted({x['finish'] for x in fixed}, key=lambda s: _date(s) or datetime.max))})"
                     if fixed else None),
                K.ev('Weather in metrics', 'none'), K.ev('Resource data in this read', 'none'),
                K.ev('Shutdown in file', ('none found' if not shutdowns else f"{len(shutdowns)} named") if nok else None)]
    drills = [K.drill('q13', "Claims & EOT: was the delay the client's?") if behind else
              K.drill('q13', 'Claims & EOT: do I have a case?'),
              K.drill('q04', f"Critical path & float: why {_tag(deep[0])} reads {_sg(deep[0]['tf'])}" if deep else
                      'Critical path & float: what drives the date?'),
              K.drill('q05', f"How do I recover the ~{slip} days?") if (behind and slip and slip > 0) else None,
              K.drill('q09', 'Is the delay resource-driven?' if behind else 'Is my manpower realistic?'),
              K.drill('q02', 'When will we finish, and will we hit the dates?')]
    head = (f"The driving path gives you {cpl:,} working days from the data date to {ff} across {cal_phrase}, but "
            "nothing in this file measures weather." if (cpl is not None and ff) else
            f"The file carries {cal_phrase}, but nothing in it measures weather"
            + (f"; the {ff} forecast" if ff else '; the forecast') + " assumes every working day is workable.")
    head += (" The forecast stays weather-blind until the Bad-Weather view sizes the loss with the right Site Type."
             if (cpl is not None and ff) else " The Bad-Weather view sizes the loss once the Site Type is set.")
    a = K.A2(head, [s_days, s_cmp, s_proc, s_wx, s_adj, s_crew, s_sd], pills=pills, measured=measured,
             actions=actions, evidence=evidence, drilldowns=drills)
    a['thinking'] = thinking
    return a
