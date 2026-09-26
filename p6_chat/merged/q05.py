"""q05 — How do I recover the delay — and model and cost the options?

Covers: how much must be recovered and the best way (where recovery has to land, the levers ranked, the free
lever of late client inputs, how the path moves as you crash it), modelling and costing a recovery (what-if per
lever, a resourced / costed scenario, days-per-cost and CPI, staffability) and running a what-if (the two-step
estimate → F9, the six levers, why only F9 is committable) — for ANY project. Builds on q04's network read.
"""
from . import _kit2 as K
from .q04 import (view, audit_view, route, ends_of, ladder_names, was_due, fl, rng, p1, n0, nm, idn, join_and,
                  _tokens)

_STOP = {'design', 'engineering', 'phase', 'works', 'work', 'construction', 'procurement', 'the', 'and', 'for', 'of',
         'from', 'client', 'start', 'approval', 'delivery', 'ii', 'iii', 'all'}


def _frac(spi):
    for val, word in ((0.5, 'half'), (2 / 3, 'two-thirds'), (0.75, 'three-quarters'), (0.8, 'four-fifths'),
                      (0.9, 'nine-tenths')):
        if abs(spi - val) <= 0.02:
            return word
    return f"{round(spi * 100)}%"


def _share(p):
    if p is None:
        return None
    for lo, hi, w in ((20, 30, 'about a quarter'), (30, 37, 'about a third'), (45, 55, 'about half'),
                      (62, 70, 'about two-thirds')):
        if lo <= p < hi:
            return w
    return f"{p1(p)}%"


def _sig(s):
    return {t for t in _tokens(s) - _STOP if len(t) >= 3 and not t.isdigit()}


def _open_at(x, dd):
    return f"open at {dd}" if x.get('finish') == dd else (x.get('finish') or '—')


def build(F, N, role):
    v = view(F, N)
    A = audit_view(F)
    nok = v['ok'] and bool(v.get('work'))
    d = F.get('delay_days')
    behind = (d or 0) > 0
    dd = v.get('dd') or F.get('data_date')
    fin = v.get('fin') or {}
    fin_tf = v.get('fin_tf')
    fronts = v.get('fronts') or [] if nok else []
    ladder = v.get('ladder') or [] if nok else []
    ho = v.get('handoff') if nok else None
    head = v.get('head') if nok else None
    drv = K.main_driver(F)
    spi, cpi = F.get('spi'), F.get('cpi')
    neg, neg_pct, crit = A['neg'], A['neg_pct'], A['crit']
    cl_late = v.get('client_late') or []
    cl_neg = v.get('client_late_neg') or [] if nok else []
    cl_open = v.get('client_open') or []
    cl_done = v.get('client_done_late') or []
    base = fin.get('baseline_finish') or F.get('baseline_finish')
    fcst = fin.get('finish') or F.get('forecast_finish')
    fin_ref = idn(fin) if fin.get('id') else 'the finish milestone'
    fin_id = fin.get('id') or 'finish'
    thinking = []

    # the pieces of the chain recovery works on
    up = [fr for fr in fronts if fr['role'] in ('head', 'upstream')]
    fed = next((fr for fr in fronts if fr['role'] == 'fed'), None)
    tail = [fr for fr in fronts if fr['role'] == 'tail']
    g0 = ladder[0] if ladder else None
    cg = next((g for g in ladder if g['client']), None)
    big = max(up, key=lambda fr: len(fr['rows'])) if up else None
    big_rows = [x for x in (big['rows'] if big else []) if x is not head]
    ex1 = big_rows[min(2, len(big_rows) - 1)] if big_rows else head
    ex2 = big_rows[len(big_rows) // 2] if len(big_rows) > 3 else (big_rows[-1] if big_rows else None)
    chain_ids = {x['id'] for x in (v.get('chain') or [])}
    deeper_off = [x for x in (v.get('deeper') or []) if x['id'] not in chain_ids] if nok else []
    ft = next((x for x in cl_open if ' before ' in f" {nm(x).lower()} "), None) if nok else None
    trunk = ((v['driver'] + (f" {fronts[0]['trade']}" if fronts and fronts[0]['trade'] else '') + ' trunk')
             if nok and v.get('has_wbs') else 'driving chain')
    cap_by_client = bool(behind and cg and cg['gap'] < d)
    tail_names = join_and([fr['label'] for fr in tail])
    cc = F.get('calendar_count')

    # ── verdict ─────────────────────────────────────────────────────────────────────────────────
    if behind and nok:
        head_line = (f"Recovering the {round(d)} wd means compressing the {trunk}"
                     + (" AND closing the late client inputs — either one alone caps out early" if cap_by_client else
                        (f" upstream — past ~{g0['gap']} wd the {ladder_names(g0, True)} path takes over" if g0 else ''))
                     + "; model each move in the What-if and commit only the F9 figure.")
    elif behind:
        head_line = (f"Recovering the {round(d)} wd means compressing the chain that sets the finish — "
                     + ("I couldn't re-read the file to name it" if not v['ok'] else "the file shows no chain I can trace")
                     + ", so start from the weighted driver"
                     + (f" ({drv['name']})" if drv else '') + "; model each move in the What-if and commit only the F9 figure.")
    elif d is None:
        head_line = ("I can't size a delay from this file (no finish slip is stored), so there's no recovery target yet — "
                     "test any change in the What-if before you make it.")
    else:
        head_line = ("There's no delay to recover: "
                     + (f"the finish has about {K.wd(d)} of float to completion (SPI {K.ratio(spi)})" if d < 0 else
                        f"the finish is on its date (SPI {K.ratio(spi)})")
                     + ". Protect that float, and test any change in the What-if before you make it.")
    pills = ([K.pill(f"recover {round(d)} wd" + (f" → {base}" if base else ''), 'danger'),
              K.pill(f"work the {trunk}", 'warning') if nok else None,
              K.pill(f"tail-only crash caps at ~{g0['gap']} wd", 'warning') if g0 and g0['fed'] and tail else None,
              K.pill(f"{nm(cg['items'][0])} {cg['gap']} wd from driving", 'danger') if cg else None]
             if behind else
             [K.pill(K.signed(d), 'success') if d is not None else None, K.pill('protect the float', 'accent')])
    pills += [K.pill('no crew rates in the file → cost is qualitative', 'neutral') if behind else None,
              K.pill('commit the F9, not the estimate', 'accent')]

    # ── the gap to erase ────────────────────────────────────────────────────────────────────────
    tr = F.get('trend')
    has_trend = bool(tr and tr.get('prev_delay') is not None)
    if behind:
        slip = fin.get('slip_wd') if nok and fin.get('slip_wd') is not None else d
        g1 = ((f"**Pull {fin_ref} back {round(slip)} working days, from {fcst} to its {base} baseline." if nok and base and fcst else
               f"**Pull the finish back {round(d)} working days" + (f", from {fcst} to {base}." if base and fcst else '.'))
              + (f" Neither the {v['driver']} works nor the client inputs can get you there alone.**" if cap_by_client else '**'))
        g2 = (f"That's the whole slip, about {K.weeks(d)}."
              + (f" The finish milestone carries {fl(fin_tf)} wd of total float" if nok else '')
              + ((" and" if nok else f" {n0(neg)}") + (f" {n0(neg)}" if nok else '') + f" activities ({p1(neg_pct)}%) sit on "
                 f"negative float, so this isn't one late activity: {_share(neg_pct)} of the network is behind its dates."
                 if neg is not None else ('.' if nok else ''))
              + (f" The pace hasn't turned either. SPI {K.ratio(spi)} means you're earning about {_frac(spi)} of the planned "
                 f"work ({K.pct(F.get('actual_pct'))} done against {K.pct(F.get('planned_pct'))} planned)." if spi is not None and spi < 1 else
                 (f" SPI is {K.ratio(spi)}, so the pace itself is at or above plan — the slip sits on the chain, not in the "
                  "overall rate." if spi is not None else ''))
              + (f" Since the previous update the gap moved from {K.signed(tr['prev_delay'])} to {K.signed(d)}, so re-measure "
                 "it at every update (Update vs Update)." if has_trend else
                 " This is a single snapshot, so I can't tell you how fast the gap is growing. Re-measure it at the next "
                 f"update (Update vs Update)" + (f" and treat {round(d)} as the floor, not the ceiling." if (spi or 1) < 1 else '.')))
        if nok and not g2.endswith('.'):
            g2 += '.'
        g3 = ''
        if cl_neg:
            lo_s, hi_s = min(x['slip_wd'] for x in cl_late), max(x['slip_wd'] for x in cl_late)
            g3 = (f"One thing to settle up front: part of the {round(d)} may not be yours to buy back. {len(cl_late)} of the "
                  f"{len(cl_open)} still-open client inputs are {lo_s}–{hi_s} wd late, and "
                  + (f"all {len(cl_late)} sit" if len(cl_neg) == len(cl_late) else f"{len(cl_neg)} of them sit")
                  + f" on negative-float paths. Those are strong EOT indicators. Plan recovery against the full {round(d)} "
                  "until the employer/contractor split exists, but that split needs a TIA / Consultant Review. Until you have "
                  "it, don't pay acceleration for days that may turn out to be the employer's.")
        s_gap = K.sec('The gap to erase', g1, g2, g3)
        thinking.append(f"Measured the gap: {fin_id} forecast {fcst} vs baseline {base} = {fl(slip)} wd"
                        if nok else f"Measured the gap from the stored finish slip: {K.signed(d)}")
    else:
        s_gap = K.sec('The gap to erase',
                      "**There's nothing to erase: " + (K.delay_phrase(F).replace('**', '') if d is not None else
                                                         "the stored numbers carry no finish slip") + '.**',
                      (f"SPI is {K.ratio(spi)} ({K.pct(F.get('actual_pct'))} done against {K.pct(F.get('planned_pct'))} planned). "
                       if spi is not None else '')
                      + ("Recovery thinking here is about keeping the float: "
                         + (f"**{drv['name']}** is the one line behind plan ({drv['actual']}% vs {drv['planned']}%, "
                            f"{round((drv.get('weight') or 0) * 100)}% of the weight), so watch it first. " if drv else '')
                         + "Re-measure at the next update in Update vs Update — one snapshot shows no trend."),
                      K.network_note(N))
        thinking.append(f"Checked the finish position: {K.signed(d) or 'not stored'} — nothing to recover")

    # ── where the recovery has to land ──────────────────────────────────────────────────────────
    s_land = None
    if behind and nok:
        on_chain = lambda name: any(name.lower() in (x.get('wbs') or '').lower() for x in v['work'])
        off = sorted([x for x in F.get('disciplines') or [] if (x.get('gap') or 0) >= 10 and not on_chain(x['name'])],
                     key=lambda x: -(x.get('gap') or 0))[:3]
        l1 = (f"Recovery only counts on the chain that sets the date, and in this file you can trace it activity by activity. "
              f"It starts at {idn(head)}. " + was_due(head, dd)
              + " From there it runs through " + ', then '.join(f"{fr['label']} ({len(fr['rows'])})" for fr in fronts)
              + f", and ends at {ends_of(v)}. That's {v['length']} activities, "
              + ('every one 0% started' if v['started'] == 0 else f"{v['started']} of them started")
              + f", on {rng(*v['full'])} wd of float.")
        l2 = ''
        if drv:
            drv_on = on_chain(drv['name'])
            vg = F.get('value_gap') or {}
            top = next((g for g in (vg.get('groups') or []) if (g.get('gap') or 0) > 0), None)
            l2 = (("It's also where the value is. " if drv_on else
                   f"The weighted driver, **{drv['name']}**, isn't on this chain, so progress there and the finish date are two "
                   "separate problems. ")
                  + (f"{top['code']} carries {p1(top.get('pct_of_gap'))}% of the PV−EV gap, and " if top else '')
                  + f"{drv['name']} ({round((drv.get('weight') or 0) * 100)}% weight) is {drv['actual']}% done against "
                  f"{drv['planned']}% planned.")
            if off:
                l2 += (" The " + join_and([x['name'] for x in off]) + f" line{'s look' if len(off) > 1 else ' looks'} worse on "
                       "paper: " + join_and([f"{x['name']} is {x['actual']}% against {x['planned']}%" for x in off]) + ". But "
                       + (f"each is about {round((off[0].get('weight') or 0) * 100)}% weight" if len({x.get('weight') for x in off}) == 1
                          else 'they carry ' + join_and([f"{round((x.get('weight') or 0) * 100)}%" for x in off]) + ' of the weight')
                       + f" and {'neither' if len(off) == 2 else 'none' if len(off) > 2 else 'it'} "
                       + ('is' if len(off) != 1 else 'is not') + f"{' on' if len(off) != 1 else ' on'} the {fl(fin_tf)} chain, "
                       "so crews there buy nothing on the date.").replace('it is not on', "it isn't on")
                for x in off:
                    link = next((c for c in cl_neg if _sig(x['name']) & _sig(nm(c))), None)
                    if link:
                        l2 += (f" One caveat: {x['name']} waits on the late {nm(link)} input ({fl(link['tf'])}), so it turns "
                               "into a date risk if that input stays open.")
                        break
        rows = []
        for fr in fronts:
            r = fr['rows']
            first, last = r[0], r[-1]
            rec = {'head': 'Yes — head of the chain, ' + ('not started' if (first.get('pct') or 0) == 0 else f"{first['pct']}% done"),
                   'upstream': 'Yes', 'fed': 'Yes, once the work ahead of it moves',
                   'tail': 'Tail only — see the watch below'}[fr['role']]
            rows.append([f"{fr['label']} — {idn(first)}" + (f" + {len(r) - 1} more" if len(r) > 1 else ''),
                         rng(min(x['tf'] for x in r), max(x['tf'] for x in r)),
                         f"{last.get('finish')} ({last.get('baseline_finish') or '—'})", rec])
        if off:
            rows.append(['; '.join(x['name'] for x in off), f"not on the {fl(fin_tf)} chain", '—',
                         'No — about ' + join_and(sorted({f"{round((x.get('weight') or 0) * 100)}%" for x in off})) + ' weight'
                         + (' each' if len(off) > 1 else '')])
        note = (f"Real rows: the finish-driving chain in this file ({v['length']} activities, grouped by work front). Floats, "
                "forecasts and baselines are P6's own."
                + ((f" The {'two deepest floats' if len(deeper_off) >= 2 else 'deepest float'} in the file sit"
                    f"{'' if len(deeper_off) >= 2 else 's'} alongside the chain: "
                    + join_and([f"{idn(x)} at {fl(x['tf'])}" for x in deeper_off[:2]])
                    + (', both 0%.' if len(deeper_off) >= 2 and all(x.get('pct') == 0 for x in deeper_off[:2]) else '.'))
                   if deeper_off else ''))
        s_land = K.sec('Where the recovery has to land', l1, l2,
                       table=K.tbl(['Chain segment (P6 IDs)', 'Float (wd)', 'Forecast finish (baseline)', 'Recover here?'],
                                   rows, note))
        thinking.append(f"Mapped the {v['length']}-activity driving chain into {len(fronts)} work fronts to see where recovery lands")
    elif behind:
        s_land = K.sec('Where the recovery has to land', K.network_note(N),
                       (f"From the stored numbers, the weighted driver is **{drv['name']}** ({round((drv.get('weight') or 0) * 100)}% "
                        f"of the weight, {drv['actual']}% done vs {drv['planned']}% planned) — recovery belongs on its "
                        "critical activities, not on the lines with the biggest raw gap." if drv else '')
                       + (f" {n0(crit)} activities sit at critical float, so expect a crowded network." if crit else ''))

    # ── the three levers ────────────────────────────────────────────────────────────────────────
    s_levers = None
    if behind:
        if ho:
            resq = (f"Break the {ho['units'][0]} → {ho['units'][-1]} hand-offs within {ho['parent']}. Repeating unit-to-unit work like "
                    "this is often tied by a rig, formwork set or crew moving across rather than by the physics of the work. "
                    f"If so, {ho['units'][-1]} can run alongside {ho['units'][0]}.")
        elif nok:
            resq = (f"Overlap steps on the chain where the link is crew availability rather than physics (FS → SS + lag), "
                    f"starting from {idn(head)}.")
        else:
            resq = "Overlap chain steps where the link is crew availability rather than physics (FS → SS + lag)."
        crash = ((f"A second crew or plant set on {join_and([fr['label'] for fr in up[:2]])}"
                  + (f", and a second {fed['trade']} crew for {fed['label']}" if fed and fed['trade'] else '') + '.')
                 if nok else "A second crew or plant set on the driving activities.")
        if deeper_off:
            x = deeper_off[0]
            crash += (f" Before you buy crews, look at {idn(x)} ({fl(x['tf'])}, forecast {x.get('finish')}): its float runs "
                      "deeper than the finish's, which usually means a hold, lag or intermediate date. If it's a technical hold "
                      "(curing, testing, inspection), ask the engineer whether it can be shortened.")
        s_levers = K.sec('The three levers, ranked', 'You have three levers on your own works. The cheapest comes first:',
                         table=K.tbl(['Lever', 'In this file, that means', 'Cost / risk'], [
                             ['1. Re-sequence / fast-track', resq,
                              'Cheapest: logic only. It fails if the second front has no crew, rig or formwork to run on.'],
                             ['2. Crash (crews / plant)', crash,
                              'Direct cost, and productivity falls with each crew you add to a congested front.'],
                             ['3. Extend the work window', "A 6th or 7th day, or longer hours, on the calendar the chain uses."
                              + (f" The file has {cc} calendars, so edit the right one first." if cc and cc > 1 else ''),
                              'Cheap per day, but fatigue and weather set a ceiling.']],
                             "No day figures here on purpose: the only committable number is the What-if F9 on this file."
                             + (" There's also a fourth lever that costs you nothing: the late client inputs, below." if cl_neg else '')))

    # ── the free lever: late client inputs ──────────────────────────────────────────────────────
    s_free = None
    if behind and cl_neg:
        c0 = cl_neg[0]
        allz = all((x.get('pct') or 0) == 0 for x in cl_neg)
        f1 = (f"{len(cl_late)} of the {len(cl_open)} client inputs still open are late."
              + (" All are 0%, and each sits on its own negative-float path." if allz and len(cl_neg) == len(cl_late) else '')
              + f" Float tells you how far each one is from taking over the finish. The driver is at {fl(fin_tf)}, so an input "
              f"at {fl(c0['tf'])} has {c0['tf'] - fin_tf} wd of slack before it drives the date, and every week it stays open "
              "eats that slack.")
        first = (f"compress the {trunk} by more than about {c0['tf'] - fin_tf} wd and, unless {nm(c0)} has landed, its path is "
                 "likely to take over as the driver; the F9 re-run will show exactly where.")
        second = (f"{idn(ft)} is already a recovery move sitting in your file: approval to start that work before its "
                  "predecessor completes is a fast-track, so push it.") if ft else ''
        f2 = ((f"Two things follow. First, {first} Second, {second}" if second else f"One thing follows: {first[0].upper() + first[1:]}")
              + " Because these are employer-side items on negative-float paths, log them and give notice. Whether they actually "
              "moved the finish, and by how much, needs the TIA / Consultant Review split."
              + (f" {len(cl_done)} other client input{'s' if len(cl_done) != 1 else ''} came in late "
                 f"({min(x['slip_wd'] for x in cl_done):+d} to {max(x['slip_wd'] for x in cl_done):+d} wd) but "
                 f"{'are' if len(cl_done) != 1 else 'is'} already done. That time is sunk: it's an EOT question, not "
                 "something recovery can buy back." if cl_done else ''))
        rows = [[idn(x), f"{_open_at(x, dd)} ({x.get('baseline_finish') or '—'})", f"{fl(x.get('slip_wd'))} wd", fl(x['tf']),
                 f"{x['tf'] - fin_tf} wd"] for x in cl_neg]
        on_time = v.get('client_on_time') or []
        dues = sorted({x.get('finish') for x in on_time if x.get('finish')})
        note = (f"Slack before it drives = the input's float minus the driver's {fl(fin_tf)}, which is how many more working "
                "days it can slip before it joins the finish-driving chain."
                + (f" 'Open at {dd}' means P6 has rolled the unreceived input to the data date." if any(x.get('finish') == dd for x in cl_neg) else '')
                + (f" The {len(on_time)} other open input{'s' if len(on_time) != 1 else ''}"
                   + (f" due {join_and(dues[:3])}" if dues else '') + f" ({' / '.join(x['id'] for x in on_time[:6])}) "
                   f"{'are' if len(on_time) != 1 else 'is'} on time today, so keep {'them' if len(on_time) != 1 else 'it'} there."
                   if on_time else ''))
        s_free = K.sec('The free lever — close the late client inputs', f1, f2,
                       table=K.tbl(['Client input (P6 ID)', 'Forecast (baseline)', 'Slip', 'Float', 'Slack before it drives'],
                                   rows, note))
        thinking.append(f"Checked {len(cl_open)} open client inputs ({len(cl_late)} late) and {len(ladder)} parallel paths "
                        "for how far each caps recovery")

    # ── the watch: crashing moves the path ──────────────────────────────────────────────────────
    s_watch = None
    if behind and g0:
        if g0['fed'] and tail:
            w1 = (f"Once you compress the driver, the next-longest path takes over, and here that path is close behind. "
                  f"{ladder_names(g0)} {'sit' if len(g0['items']) > 1 else 'sits'} at {fl(g0['tf'])} against the driver's "
                  f"{fl(fin_tf)}. Crash only the tail ({tail_names}) and after roughly {g0['gap']} wd the "
                  f"{ladder_names(g0, True)} path is likely to set the date: you'll have paid for {g0['gap']} days. Compress "
                  f"upstream instead, on the {trunk} that feeds the {fed['label']} work and the tail together.")
        else:
            w1 = (f"Once you compress the driver, the next-longest path takes over: {ladder_names(g0)} at {fl(g0['tf'])}, "
                  f"{g0['gap']} wd behind the driver's {fl(fin_tf)}. Crash the chain by more than ~{g0['gap']} wd and that path "
                  "sets the date, so pair the chain's recovery with recovery on that path.")
        rest = ladder[1:9]
        w2 = (("Here's the ladder behind it, read straight off float. "
               + '; '.join(f"{ladder_names(g, True)} {fl(g['tf'])} ({g['gap']} wd of slack)" for g in rest) + '. ' if rest else '')
              + f"Recovering the full {round(d)} means pulling every one of those paths back to zero float, not just the top one. "
              "That makes it iterative: make one move, re-run F9, see which path drives now, and buy compression against that "
              "path, never the old one."
              + (f" With {n0(crit)} activities at critical float, expect the driver to jump after the first move." if crit else ''))
        s_watch = K.sec('The watch — crashing moves the path', w1, w2)
    elif behind and crit:
        s_watch = K.sec('The watch — crashing moves the path',
                        f"Compress the driver and the next path takes over. With {n0(crit)} activities at critical float"
                        + (f" ({A['dens_word']} density)" if A['dens_word'] else '') + ", expect the driver to jump after the "
                        "first move — re-run F9 after each one and buy compression against whatever drives now. Which paths "
                        "sit next in line needs the file re-read.")

    # ── how the what-if models each lever ───────────────────────────────────────────────────────
    ex_crash = (f"e.g. {idn(ex1)}" + (f" or {idn(ex2)}" if ex2 and ex2 is not ex1 else '')) if nok and ex1 else 'a driving activity'
    ex_crew = big['label'] if big else 'the driving front'
    ex_delay = (f"e.g. {nm(cg['items'][0])} past {cg['items'][0].get('finish')}" if cg else
                (f"e.g. {idn(head)}" if head else 'a late input or start'))
    m_bul = (("• Crash: shorten a chain activity, " + ex_crash if nok else "• Crash: shorten a driving activity") + ", then F9.\n"
             f"• Add crew: a second crew or plant set on {ex_crew}, modelled as a shorter duration or a parallel activity, then F9.\n"
             "• Shift: edit the calendar the chain uses (6th/7th day, longer hours). P6 needs the calendar changed first, and "
             "the What-if does that before the F9.\n"
             "• Fast-track / re-sequence: " + (f"cut a {ho['units'][0]} → {ho['units'][-1]} hand-off link, or " if ho else '')
             + "turn an FS into SS + lag, then F9.\n"
             + (f"• Delay: slip a client input further ({ex_delay})" if cg else
                (f"• Delay: slip an activity ({ex_delay})" if head else "• Delay: slip a late input or start"))
             + " to see when it takes over the finish, then F9.")
    s_model = K.sec('How the what-if models each lever',
                    "**Model each move in the What-if on the real chain, one at a time, and rank them by the days F9 says they "
                    "buy. The file can't price them for you: what I read carries no labour resources or crash rates.**",
                    "Each lever is a defined edit to the network followed by a reschedule, so you get a real number instead of a guess:",
                    m_bul,
                    "The What-if applies the edit, runs P6 F9 and reports the new "
                    + (f"{fin_id} finish" if fin.get('id') else 'finish date')
                    + ". The day-gain is forecast-before minus forecast-after. Model one move at a time so you see each "
                    "one's own contribution, stack only the winners, and re-read the driving path after each.")

    # ── a resourced, costed scenario ────────────────────────────────────────────────────────────
    s_cost = None
    if behind:
        vg = F.get('value_gap') or {}
        top = next((g for g in (vg.get('groups') or []) if (g.get('gap') or 0) > 0), None)
        c1 = ("The honest limit: nothing I read from this P6 file carries labour or plant assignments or crash rates"
              + (f". It carries budget values (PV {K.money(F.get('pv'))} in the project's own currency units"
                 + (f", {top['code']} holding {p1(top.get('pct_of_gap'))}% of the gap" if top else '') + ')' if F.get('pv') else '')
              + ", so it can't tell you what a second crew or rig costs or how many people a second shift needs. Productivity "
              "& Resource Intelligence fills part of the gap: it turns each move into man-hours and crew/plant needs from "
              "productivity norms. The rate per crew, rig or shift has to come from you or your commercial team, and until "
              "it does the cost side stays qualitative. The tool also won't search the network for the cheapest crash plan "
              "on its own. You pick the candidates and the What-if tests them.")
        rows = []
        if cl_neg:
            caps = [x['tf'] - fin_tf for x in cl_neg[:3]]
            rows.append(["Close the nearest late client inputs: " + join_and([idn(x) for x in cl_neg[:3]]),
                         f"Lifts the {min(caps)}–{max(caps)} wd caps; run in What-if",
                         'Client pressure, no site resource', 'Nil to the contractor'])
        if ho:
            rows.append([f"Break the {ho['units'][0]} → {ho['units'][-1]} hand-off; run {ho['units'][-1]} in parallel",
                         'Run in What-if', f"2nd crew / rig / formwork set for {ho['units'][-1]}", 'Medium — plant or formwork hire'])
        rows.append([f"Second crew or plant set on {ex_crew}", 'Run in What-if', 'Crew + plant', 'Medium'])
        if deeper_off:
            rows.append([f"Shorten the hold around {idn(deeper_off[0])} ({fl(deeper_off[0]['tf'])})", 'Run in What-if',
                         "Method change (mix, propping, test regime), engineer's sign-off", 'Low to medium'])
        rows.append(["6th/7th day on the chain's calendar", 'Run in What-if', 'Same crews, more days', 'Overtime premium; fatigue'])
        nxt = fed or (tail[0] if tail else None)
        if nxt:
            rows.append([f"Second {nxt['trade'] or 'trade'} crew on {nxt['label']}", 'Run in What-if',
                         f"{(nxt['trade'] or 'Trade').capitalize()} crew + lifting / plant time",
                         'Medium to high; only helps once the work ahead of it moves'])
        s_cost = K.sec('A resourced, costed scenario', c1,
                       table=K.tbl(['Candidate move (on the chain)', 'F9 day-gain', 'Added resource', 'Cost'], rows,
                                   "No day-gain is shown because none has been run yet: the F9 figure for each move comes from "
                                   "the What-if on this file. Man-hours per move come from Productivity & Resource "
                                   "Intelligence (norm-based); the rate per crew, rig and shift is yours to supply."))

    # ── rank by days-per-cost, and CPI ──────────────────────────────────────────────────────────
    s_rank = None
    if behind:
        order = []
        if cl_neg:
            order.append("Close the client inputs first: it costs nothing and lifts the caps on everything else.")
        if ho:
            order.append(f"{'Next' if order else 'First'}, re-sequence the {ho['units'][0]} → {ho['units'][-1]} hand-offs "
                         "(logic, little spend).")
        order.append(f"{'Then add' if order else 'Add'} plant and crews on the {trunk}, and extend the calendar last.")
        r1 = ("Rank by F9 working days bought per unit of cost, not by raw days. "
              + ('Here the order almost writes itself. ' if nok else '') + ' '.join(order)
              + " Crashing buys days at a falling rate, because a second crew on a tight front clears less than the first.")
        if F.get('cost_derived'):
            r2 = (f"Don't expect CPI to warn you. In this file actual cost is derived from progress (AC equals EV), which is "
                  f"why CPI reads exactly {K.ratio(cpi)}, and acceleration spend won't show in it unless you start loading real "
                  "actual costs. Track the recovery budget separately.")
        elif cpi is not None:
            r2 = (f"CPI is {K.ratio(cpi)} today. Acceleration spend lands in actual cost before the earned value it buys, so "
                  "expect CPI to dip while you recover — budget the premium explicitly and track it against the days F9 says "
                  "it bought.")
        else:
            r2 = "Cost can't be read from this file (no actual cost loaded), so track the recovery budget separately."
        vg = F.get('value_gap') or {}
        zero = [g['code'] for g in (vg.get('groups') or []) if not g.get('pv')]
        if zero:
            r2 += (f" Don't expect SPI to reward all of the recovery either. {join_and(zero[:3])} carr"
                   f"{'y' if len(zero) > 1 else 'ies'} zero value in the file, so days you win there move the finish but not SPI.")
        elif drv:
            r2 += (" Don't expect SPI to reward all of the recovery either: SPI moves with weighted value, and "
                   f"{drv['name']} carries {round((drv.get('weight') or 0) * 100)}% of it, so SPI only recovers as that work "
                   "earns — days won on low-weight work move the finish but barely move SPI.")
        s_rank = K.sec('Rank by days-per-cost — and watch CPI', r1, r2)

    # ── staffability ────────────────────────────────────────────────────────────────────────────
    s_staff = None
    if behind:
        win = v.get('window') if nok else None
        s_staff = K.sec('Staffability — can the peak be manned?',
                        "The file can't answer this on its own: nothing I read carries labour, so there's no P6 histogram to "
                        "check. Take each winning move through Productivity & Resource Intelligence for its man-hour load. Then "
                        "check the peak against what the site, the camp and your subcontractors can actually field"
                        + (f" in {win['text']}. That's when {join_and(win['fronts'][:5])} stack up on the chain." if win else '.')
                        + " The tool gives man-hours, not headcount, and whether crews and plant are available in the market is "
                        "outside the file, so that part is your call. Keep only the moves that clear the staffing ceiling and "
                        "drop or phase the rest.")

    # ── how the what-if works ───────────────────────────────────────────────────────────────────
    s_two = K.sec('How the what-if works — two steps',
                  "**Test each move before you commit to it: use the instant estimate to line them up, then P6's own F9 for "
                  "the number you can defend.**",
                  "Step 1: pick a lever on a chain activity, say "
                  + (f"a second crew on {ex_crew} or a 6th day on the chain's calendar" if nok else
                     "a second crew on a driving activity or a 6th day on its calendar")
                  + f". You get an instant estimate of the new {fin_id if fin.get('id') else 'finish'} date and the day-gain, "
                  "with no P6 run needed. That lets you line up five or six moves and compare them in minutes instead of "
                  "hand-building each one in Primavera.",
                  "Step 2: once you've found the moves that pay, the tool builds them into the schedule and runs P6's own F9 "
                  "recalculation for the exact figure. Rule of thumb: the estimate is for triage, and the F9 number is what "
                  "goes in the recovery plan or a claim.")
    six = [['Delay', 'Pushes a start or milestone later',
            (f"{idn(cg['items'][0])} slipping past {cg['items'][0].get('finish')}: see when it takes over the finish" if cg else
             (f"{idn(head)} starting later than forecast" if head else 'A late input or start: see when it takes over the finish'))],
           ['Extend', "Lengthens an activity's duration",
            f"{idn(ex1)} running longer than planned" if nok and ex1 else 'A driving activity running longer than planned'],
           ['Crash', 'Shortens a duration by spending more',
            idn(ex2) if nok and ex2 else (idn(ex1) if nok and ex1 else 'A driving activity, with more crew or plant')],
           ['Add crew', 'Raises resources / output on a task',
            f"Second crew or plant set on {ex_crew}" if nok else 'A second crew on the driving front'],
           ['Re-sequence', 'Changes the logic between activities',
            f"Cut the {ho['units'][0]} → {ho['units'][-1]} hand-off links" if ho else
            'Re-order chain steps where the link is crew availability, not physics'],
           ['Fast-track', 'Overlaps activities (FS → SS + lag)',
            f"{idn(ft)}: already a planned fast-track" if ft else
            (f"Overlap {fronts[0]['label']} with {fronts[1]['label']}" if len(fronts) > 1 else 'Overlap consecutive chain steps')]]
    s_six = K.sec('The six levers', table=K.tbl(['Lever', 'What it changes', 'In this file, e.g.'], six,
                                                 "Crash, add-crew and fast-track compress; re-sequence and delay/extend reshape the "
                                                 "network. All of them act on the real activities and relationships in this file."))

    # ── estimate vs F9 ──────────────────────────────────────────────────────────────────────────
    est = ("The instant estimate is a retained-logic forward pass over your own logic. It matches P6 to the day on progressed "
           "networks and drifts on unprogressed or constrained ones")
    deeper = v.get('deeper') or [] if nok else []
    if nok and v['started'] == 0 and deeper:
        est += (f", and this file is both. It's {K.pct(F.get('actual_pct'))} done overall, yet every one of the {v['length']} "
                "activities on the driving chain is 0% started. Several floats also sit "
                + ('deeper than' if fin_tf < 0 else 'below') + " the finish's "
                f"{fl(fin_tf)} ({', '.join(fl(x['tf']) for x in deeper[:3])}), which usually means an intermediate constraint or "
                "a different calendar is in play. That's exactly where an estimate can drift, so use it to rank moves and "
                "never to quote one.")
    elif nok and v['started'] == 0:
        est += (f". Here every one of the {v['length']} chain activities is unstarted, so expect drift: use the estimate to "
                "rank moves and never to quote one.")
    elif nok and deeper:
        est += (f". Here {len(deeper)} float{'s sit' if len(deeper) != 1 else ' sits'} "
                + ('deeper than' if fin_tf < 0 else 'below') + f" the finish's {fl(fin_tf)}, "
                "which points to a constraint, lag or calendar — expect drift, and use the estimate to rank moves only.")
    elif nok:
        est += (". Here the chain is progressed and no float runs deeper than the finish's, so the estimate should sit "
                "close — still, quote only the F9.")
    else:
        est += ". I couldn't re-read the file to say which this is, so treat the estimate as triage only."
    est += (" The F9 run is Primavera recalculating your actual file, and that's the figure for a recovery plan or an EOT "
            "submission. The tool always labels which one you're looking at.")
    s_est = K.sec('Estimate vs F9 — and why the gap matters', est)

    # ── on this schedule ────────────────────────────────────────────────────────────────────────
    if behind and nok:
        caps = [x['tf'] - fin_tf for x in cl_neg]
        o = (f"You're {round(d)} working days behind on {nm(fin) if fin.get('id') else 'the finish'} ({base} → {fcst}). One "
             f"chain sets that date: {route(v)}, " + ('all 0% started' if v['started'] == 0 else f"{v['started']} of it started")
             + f", with {rng(*v['full'])} wd of float."
             + (" The deepest float in the file is " + join_and([f"{idn(x)} at {fl(x['tf'])}" for x in deeper_off[:2]]) + '.'
                if deeper_off else '')
             + (f" Behind that chain, the late client inputs are {min(caps)}–{max(caps)} wd from taking "
                "over." if caps else '')
             + " My order: " + (f"chase {join_and([nm(x) for x in cl_neg[:3]])} this week. " if cl_neg else '')
             + (f"{'Then model' if cl_neg else 'Model'} breaking the {ho['units'][0]} → {ho['units'][-1]} hand-offs. " if ho else '')
             + f"After that, add crews and calendar on the {trunk}, each move proven by F9. If you crash anything off that "
             "chain, the estimate will read about zero. That's the tool telling you it's the wrong activity before you've "
             "spent anything on it.")
    elif behind:
        o = (f"You're about {K.wd(d)} behind" + (f" ({base} → {fcst})" if base and fcst else '') + '. '
             + (f"The weighted driver is {drv['name']}; " if drv else '')
             + ("re-import the file so I can name the chain that sets the date" if not v['ok'] else
                "check the finish milestone's logic in P6 so the chain that sets the date can be traced")
             + ", then work the levers in cost order — free "
             "(client inputs) first, logic next, crews and calendar last — each move proven by F9.")
    else:
        o = ("You're not behind, so nothing needs buying back. "
             + (f"Keep the float by watching {drv['name']}, the one line under plan, " if drv else 'Keep the float ')
             + "and run any proposed change through the What-if before you make it — the estimate to compare, F9 to commit.")
    s_here = K.sec('On this schedule', o)
    if len(thinking) < 4:
        thinking.append("Framed the levers (re-sequence, crash, calendar) on the real chain for the What-if to price in F9"
                        if nok else "Framed the what-if levers generically — the file couldn't be re-read to name activities")

    # ── measured / actions / evidence ───────────────────────────────────────────────────────────
    vg = F.get('value_gap') or {}
    top = next((g for g in (vg.get('groups') or []) if (g.get('gap') or 0) > 0), None)
    measured = ((f"The gap is {fin_ref} forecast at {fcst} against its {base} baseline finish: {fl(fin.get('slip_wd'))} working "
                 f"days. That matches the {fl(fin_tf)} wd total float on the finish"
                 + (f" and is cross-checked against {n0(neg)} activities ({p1(neg_pct)}%) on negative float" if neg is not None else '')
                 + f". The chain is every open activity within {v.get('band')} wd of the finish's float ({v['length']} activities), "
                 "each with its P6 float, forecast and baseline finish. 'Slack before it drives' is each path's float minus the "
                 f"driver's {fl(fin_tf)}. ") if behind and nok else
                ((K.network_note(N) + ' ') if not v['ok'] else '')
                + (f"The finish position is the stored slip: {K.signed(d)}. " if d is not None and not nok else ''))
    measured += ((f"The value facts come from the file's budget values: {top['code']} holds {p1(top.get('pct_of_gap'))}% of the "
                  "PV−EV gap. " if top else '')
                 + (f"AC is derived from progress, so CPI reads {K.ratio(cpi)}. " if F.get('cost_derived') else '')
                 + "The file read carries no labour resources, so man-hours come from Productivity & Resource Intelligence norms "
                 "and rates from you. The committable day-gain for any move is the What-if's P6 F9 recalculation of your file, "
                 "never the forward-pass estimate.")
    if behind:
        actions = [
            f"Set the recovery target at {round(d)} wd on {fin_id if fin.get('id') else 'the finish'} and re-measure it at the "
            "next update" + (", because one snapshot gives no trend." if not has_trend else '.'),
            ("Chase the late client inputs closest to driving this week: "
             + join_and([f"{nm(x)} ({fl(x['tf'])}, {x['tf'] - fin_tf} wd slack)" for x in cl_neg[:3]])
             + ". Log each as an EOT indicator and give notice.") if cl_neg else '',
            (f"Put every paid recovery move on the {trunk}, not the tail ({tail_names}). Crashing only the tail caps at about "
             f"{g0['gap']} wd before the {ladder_names(g0, True)} path ({fl(g0['tf'])}) takes over.") if g0 and g0['fed'] and tail else '',
            ("In the What-if, model " + (f"breaking the {ho['units'][0]} → {ho['units'][-1]} hand-offs first. Then try "
                                         if ho else '') + f"a second crew or plant set on {ex_crew}, and a 6th/7th day on the "
             "chain's calendar, one at a time.") if nok else
            ('Re-import the file' if not v['ok'] else "Check the finish milestone's logic in P6") + ' so the driving chain '
            'can be named, then model each lever in the What-if, one at a time.',
            (f"Ask the engineer whether the hold around {idn(deeper_off[0])} ({fl(deeper_off[0]['tf'])}) can be shortened "
             "before you buy crews.") if deeper_off else '',
            ("After each move, re-run F9 and follow the new driver down the ladder ("
             + ', '.join(fl(g['tf']) for g in ladder[:4]) + '…).') if ladder else 'After each move, re-run F9 and re-read the driving path.',
            "Take the winning moves through Productivity & Resource Intelligence for man-hours, price them at your own rates, "
            "and check " + (f"the {v['window']['text']} peak" if nok and v.get('window') else 'the peak') + ' is staffable.',
            (f"Track acceleration cost outside CPI: AC is derived from progress here, so CPI stays at {K.ratio(cpi)} whatever "
             "you spend.") if F.get('cost_derived') else 'Budget the acceleration premium explicitly and watch CPI as you spend it.',
            "Put only the F9 day-gain in the recovery plan"
            + (", and get the employer/contractor split from Consultant Review before paying to recover days that may be the "
               "employer's." if cl_neg or cl_done else '.'),
        ]
    else:
        actions = [(f"Protect the float: watch {drv['name']} ({drv['actual']}% vs {drv['planned']}% planned) first." if drv else
                    'Protect the float: watch the lines closest to their planned progress.'),
                   'Run any proposed change (re-sequence, crew move, calendar edit) through the What-if before committing it.',
                   'Re-measure at the next update in Update vs Update — one snapshot shows no trend.']
    evidence = [
        K.ev('Gap', f"{fl(fin.get('slip_wd'))} wd on {fin_id}" if nok and fin.get('slip_wd') is not None else K.signed(d)),
        K.ev('Baseline → forecast', f"{base} → {fcst}") if base and fcst else None,
        K.ev('Chain head', f"{head['id']} · {head.get('pct', 0)}% · {fl(head['tf'])}") if head else None,
        K.ev('Driving chain', f"{v['length']} activities, " + ('all 0%' if v['started'] == 0 else f"{v['started']} started")) if nok else None,
        K.ev('Deepest float', f"{N['deepest'][0]['id']} {fl(N['deepest'][0]['tf'])}") if nok and N.get('deepest') else None,
        K.ev('Next path', f"{' / '.join(i['id'] for i in g0['items'][:2])} {fl(g0['tf'])}") if g0 else None,
        K.ev('Nearest client input', f"{cl_neg[0]['id']} {fl(cl_neg[0]['tf'])} ({cl_neg[0]['tf'] - fin_tf} wd slack)") if cl_neg else None,
        K.ev('Late client inputs', f"{len(cl_late)} of {len(cl_open)} · {fl(min(x['slip_wd'] for x in cl_late))} to "
                                   f"{fl(max(x['slip_wd'] for x in cl_late))} wd") if nok and cl_late else None,
        K.ev('Neg float', f"{n0(neg)} ({p1(neg_pct)}%)") if neg is not None else None,
        K.ev('SPI / CPI', f"{K.ratio(spi)} / {K.ratio(cpi)}" + (' (AC derived)' if F.get('cost_derived') else '')),
        K.ev('Value gap', f"{top['code']} {p1(top.get('pct_of_gap'))}%") if top else None,
        K.ev('Labour loading', 'not in the file read'),
        K.ev('Exact gain', 'What-if P6 F9'),
    ]
    a = K.A2(head_line, [s_gap, s_land, s_levers, s_free, s_watch, s_model, s_cost, s_rank, s_staff, s_two, s_six, s_est, s_here],
             pills=pills, measured=measured, actions=actions, evidence=evidence,
             drilldowns=[K.drill('q04', "What's driving the date, and how much float is left?"),
                         K.drill('q13', 'Do the late client inputs give me an EOT case?') if cl_neg or cl_done else None,
                         K.drill('q09', 'Is my manpower realistic for a recovery?'),
                         K.drill('q02', 'When will we finish, and will we hit the sectional dates?')],
             tools=[K.tool('whatif', 'Run the what-if')])
    a['thinking'] = thinking[:4]
    return a
