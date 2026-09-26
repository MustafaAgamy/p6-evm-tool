"""q03 — Is the delay real, how big is it, and how did it build up?

Covers: the integrity tells for a manufactured delay (slip vs float, where the slip starts, durations
carried along the chain, out-of-sequence, open ends / dangling, negative float, progress), the two tells
one file can't close (imposed dates, calendars), where the delay is concentrated (weighted discipline,
then the value gap by activity code or the finish chain's WBS), the defensible number, why SPI and the
date differ, the but-for split between employer and contractor (indicators only), and how the slip
built up — derived from F / N for ANY project.
"""
from datetime import datetime

from . import _kit2 as K
from .q02 import (chain_fronts, clean, client_inputs, dt, is_client, is_ms, key_dates, kpis, ms_group_match,
                  oos_concentration, audit_total, parts, plural, position, rng, sg, short, slip, token_link, toks, by_date_ids, STOP, WEAK)


def _m(x):
    """Cost value in the project's own units: 560.3M / 2.33M / 0.07M / 812K / 0."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return '—'
    a = abs(v)
    if a == 0:
        return '0'
    if a >= 1e9:
        return f"{v / 1e9:.2f}B"
    if a >= 1e7:
        return f"{v / 1e6:.1f}M"
    if a >= 1e4:
        return f"{v / 1e6:.2f}M"
    return f"{v:,.0f}"


def _pc(x, dp=2):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return '—'
    s = f"{v:.{dp}f}".rstrip('0').rstrip('.')
    return s + '%'


def _branch_label(x, drv_name):
    """The chain head's area below the discipline: 'Silos Civil Works / Phase C / Silo 9' style."""
    p = parts(x)
    if p and drv_name and p[0] == drv_name:
        p = p[1:]
    return ' / '.join(p) if p else 'the first activity'


def _branch_ms(keys, hp):
    """Sectional milestones of the scope the finish chain starts in (they share a distinctive word with the
    chain head's second WBS level, e.g. its trade), in slip order."""
    if not hp or len(hp) < 2:
        return []
    ht = toks(hp[1]) - STOP - WEAK
    if not ht:
        return []
    grp = [m for m in keys if ht & (toks(m.get('name')) - STOP)]
    return sorted(grp, key=lambda m: m.get('slip_wd') or 0)


def build(F, N, role):
    P = position(F, N)
    nok, fin, d, fc, bl, tf, dd = P['nok'], P['fin'], P['d'], P['fc'], P['bl'], P['tf'], P['dd']
    behind, ahead = P['behind'], P['ahead']
    spi, cpi = F.get('spi'), F.get('cpi')
    drv = K.main_driver(F)
    ck, hk = kpis(F, 'cpli'), kpis(F, 'hard_constraints')
    chain = list(N.get('chain') or []) if nok else []
    acts = [x for x in chain if not is_ms(x)]
    head = chain[0] if chain else None
    keys, keys_late = key_dates(N, P)
    allc, opn, late_open, late_done, other_open = client_inputs(N)
    deepest = list(N.get('deepest') or []) if nok else []
    chain_ids = {x['id'] for x in chain} | ({P['fid']} if P['fid'] else set())
    deeper = [x for x in deepest if tf is not None and x.get('tf') is not None and x['tf'] < tf - 1 and not is_client(x)]
    neg, negp = F.get('neg_float_count'), F.get('neg_float_pct')
    total = audit_total(F)
    vg = F.get('value_gap') or {}
    vgroups = [g for g in (vg.get('groups') or []) if isinstance(g, dict)]
    vtop = next((g for g in vgroups if (g.get('gap') or 0) > 0), None)
    fronts, common, labmap = chain_fronts(chain) if chain else ([], [], {})
    agree = d is not None and tf is not None and behind and abs(tf + d) <= 1
    thinking = []

    # ── 1. integrity tells ──────────────────────────────────────────────────────────────────────
    checks = []                                             # (check, this file, reading, ok: True/False/None)
    if d is not None and tf is not None and d != 0:
        where = (P['fid'] or 'the finish') + ('' if P['tf_src'] == 'milestone' else ' (stored critical-path check)')
        if agree:
            checks.append(('Finish slip vs finish float', f"{where}: {slip(d)} vs baseline; total float {sg(tf)}",
                           "Two independent measures agree to the day. The float shows the slip; it doesn't create it", True))
        elif behind:
            checks.append(('Finish slip vs finish float', f"{where}: {slip(d)} vs baseline; total float {sg(tf)}",
                           "They don't agree — a deadline, constraint or calendar is setting the float. Find which before "
                           "quoting either", False))
    if head:
        due = P['dd_dt'] and dt(head.get('baseline_finish')) and dt(head['baseline_finish']) <= P['dd_dt']
        this = (f"{head['id']} {clean(head['name'])}: baseline finish {head.get('baseline_finish')}, "
                f"{head.get('pct', 0)}% at {dd}, forecast {head.get('finish')}")
        if due and (head.get('pct') or 0) < 100:
            checks.append(('Where the slip starts', this,
                           ("Real work that was due before the data date and hasn't started. This is a site delay, not a "
                            "paper movement" if (head.get('pct') or 0) == 0 else
                            "Real work that was due before the data date and is still running. This is a site delay, not "
                            "a paper movement"), True))
        else:
            checks.append(('Where the slip starts', this,
                           "Not yet due, so the slip here is forecast through logic — trace what feeds it (a predecessor, "
                           "lag or constraint) before calling it a site delay", None))
    if acts and d:
        ref = d
        band = [x for x in acts if x.get('slip_wd') is not None and abs(x['slip_wd'] - ref) <= 3]
        exc = [x for x in acts if x.get('slip_wd') is not None and x['slip_wd'] - ref > 3]
        if band:
            bs = [x['slip_wd'] for x in band]
            this = (f"Slip holds at {min(bs)}–{max(bs)} wd on {len(band)} of the {len(acts)} chain activities, from "
                    f"{clean(acts[0]['name'])} to the finish")
            if exc:
                this += (" (the exception" + ('s are ' if len(exc) > 1 else ' is ') +
                         '; '.join(f"{clean(x['name'])} {x['id']} at {sg(x['slip_wd'])}" for x in exc[:2]) + ')')
            ok = len(band) >= 0.9 * len(acts)
            checks.append(('Durations along the chain', this,
                           "Downstream durations and lags weren't stretched. The delay is carried along the chain, not "
                           "padded" if ok else
                           "Slip grows along the chain — time was added downstream (longer durations, lags or logic). "
                           "Compare against the baseline in Baseline Revision Comparison", ok))
    if F.get('oos_count') is not None:
        conc = oos_concentration(F)
        ok = (F.get('oos_pct') or 0) < 5
        checks.append(('Out-of-sequence',
                       f"{F['oos_count']} ({K.pct(F.get('oos_pct'), 1)}), {F.get('critical_oos') or 0} critical"
                       + (f", {F['oos_grade']}" if F.get('oos_grade') else '')
                       + (f"; {conc[1]} of the {conc[2]} are in {conc[0]}" if conc else ''),
                       "Progress isn't being posted around the logic to fake or hide movement" if ok else
                       "Enough progress is posted against the logic to distort dates — resolve it before trusting the slip",
                       ok))
    if F.get('open_ends') is not None or F.get('dangling_count') is not None:
        oe, dg = F.get('open_ends'), F.get('dangling_count')
        ok = (oe or 0) <= max(1, 0.02 * (total or 0)) and (F.get('dangling_pct') or 0) < 5
        checks.append(('Open ends / dangling',
                       f"{oe if oe is not None else '—'} open ends; {dg if dg is not None else '—'} dangling"
                       + (f" ({K.pct(F.get('dangling_pct'), 1)})" if F.get('dangling_pct') is not None else ''),
                       ("The network is tied and nothing is left loose to let dates drift."
                        + (f" The {dg} are clean-up, not a red flag" if dg else '')) if ok else
                       "Loose logic can let dates drift and hide or understate slip — close it before quoting the number",
                       ok))
    if neg is not None:
        ok = (neg > 0) if behind else True
        checks.append(('Negative float', f"{neg:,} of {total:,} audited activities ({K.pct(negp, 1)})" if total else f"{neg:,}",
                       ("The slip is visible, not masked. A schedule that hides delay usually shows the opposite" if neg
                        else "No negative float") if ok else
                       "Behind, yet nothing is on negative float — a constraint or moved target may be masking the slip",
                       ok))
    if spi is not None and F.get('actual_pct') is not None:
        ok = (spi < 1) if behind else ((spi >= 1) if ahead else True)
        checks.append(('Progress vs plan',
                       f"{K.pct(F.get('actual_pct'))} earned vs {K.pct(F.get('planned_pct'))} planned (SPI {K.ratio(spi)})",
                       ("Consistent with a real shortfall on the ground, not inflated actuals" if behind else
                        "Consistent with a real gain on the ground") if ok else
                       ("Pace says ahead while the date says late — check for front-loaded progress claims" if behind else
                        "The date says ahead while pace is below plan — check the gain isn't coming from logic or "
                        "calendar edits"), ok))
    n_ok = sum(1 for c in checks if c[3] is True)
    n_bad = sum(1 for c in checks if c[3] is False)
    genuine = bool(checks) and n_bad == 0
    subject = 'slip' if behind else ('gain' if ahead else 'position')
    if behind and genuine:
        start_ok = next((c[3] for c in checks if c[0] == 'Where the slip starts'), None)
        front = (f", and it traces back to real {_branch_label(head, drv['name'] if drv else None)} work that was due and "
                 + ("hasn't started" if (head.get('pct') or 0) == 0 else 'is still running')) if head and start_ok else ''
        lead = (f"**Genuine. The slip shows openly in the network" + (f", the logic is tied{front}" if front else " and the logic is tied")
                + ". Close two checks before you call it clean to the client.**")
    elif behind:
        lead = (f"**Mostly real, but {n_bad} of the {len(checks)} tells need clearing before the number goes outside — "
                "they're flagged in the table.**")
    elif ahead:
        lead = (f"**There's no delay to test: the finish is {K.wd(d)} ahead of baseline. The same tells apply to a gain as "
                "to a slip — " + ('none of them flags a paper gain.**' if genuine else f"{n_bad} of them need a look before you bank it.**"))
    else:
        lead = "**The finish is on its baseline date; the tells below check that nothing is holding it there artificially.**"
    p2 = (f"{'Manufactured delay usually leaves' if not ahead else 'Manufactured gains usually leave'} fingerprints: progress posted against the logic, loose ends "
          "that let dates drift, durations changed after the fact, or an imposed date doing work that logic should do. "
          f"I checked {'each of these' if len(checks) > 3 else 'what the stored numbers allow'} against your {dd} update, and "
          + (f"all {len(checks)} checks below read clean." if genuine else f"{n_ok} of the {len(checks)} checks below read clean.")
          + " Two things this file can't settle on its own are covered in the next section.")
    s_int = K.sec('Is it manufactured? The integrity tells', lead, p2, K.network_note(N) if not nok else '',
                  table=K.tbl(['Check', 'This file', 'Reading'], [c[:3] for c in checks],
                              f"Every row comes from your file (update {dd})."))
    thinking.append(f"Ran {len(checks)} integrity checks on the {subject} ({n_ok} clean"
                    + (f", {n_bad} to clear" if n_bad else '') + ')')

    # ── 2. the two tells this file can't close ──────────────────────────────────────────────────
    t1 = "1) Imposed dates. "
    if hk.get('computable'):
        t1 += (f"The constraint check ran: {hk.get('contract_milestones', 0)} contract milestones, {hk.get('masked', 0)} "
               "masked by a constraint. " + ("None is holding a date artificially. " if not hk.get('masked') else
                                              "Look at the masked ones in P6 before quoting the number. "))
    else:
        t1 += "This export doesn't let me compute hard constraints, so I can't list them. "
    if d is not None and d != 0:
        t1 += (f"The headline number is safe either way: {sg(d)} is a straight baseline-vs-forecast date comparison that no "
               "constraint touches" + (", and it matches the float." if agree else '.'))
    if deeper:
        t1 += (f" What isn't settled: {len(deeper)} {plural(len(deeper), 'activity shows', 'activities show')} more negative float "
               "than the finish does. " + ('It is ' if len(deeper) == 1 else 'They are ')
               + ', '.join(f"{x['id']} {clean(x['name'])} at {sg(x['tf'])}" for x in deeper[:4])
               + f". That can only happen if something downstream of {'it' if len(deeper) == 1 else 'them'} is tighter than "
               f"{fc or 'the finish'}: an intermediate date, a lag, or a different calendar (P6 counts float in each "
               "activity's own calendar). Run the Schedule Audit constraint check and look at "
               f"{'it' if len(deeper) == 1 else 'those ' + str(len(deeper))} in P6 before anyone quotes {sg(deeper[0]['tf'])} as 'the worst'.")
    ncal = F.get('calendar_count')
    t2 = ("2) Calendars. " + (f"The file has {ncal} {plural(ncal, 'calendar')}. " if ncal else '')
          + ("Editing a calendar (fewer working days a week, more holidays) can inflate a delay, because the same dates then "
             "count as more working days." if not ahead else
             "Editing a calendar (more working days a week, fewer holidays) can manufacture a gain, because the same work then "
             "fits into fewer calendar days.")
          + " One snapshot can't show whether any calendar changed since the baseline. The "
          "Calendar Audit and the Baseline Revision calendar-match can.")
    if P['cal_days'] is not None and d:
        t2 += (f" Until those are run, quote the {'delay' if behind else 'position'} in calendar days as well as working days. "
               f"{bl} → {fc} is {abs(P['cal_days'])} calendar days, and no calendar edit can change that figure.")
    s_tells = K.sec("The two tells I can't close in this file", t1, t2)

    # ── 3. where it's concentrated (weighted) ───────────────────────────────────────────────────
    ds = sorted(F.get('disciplines') or [], key=lambda x: (-(x.get('weight') or 0), -(x.get('gap') or 0)))
    cp = []
    if drv:
        tot = sum((x.get('weight') or 0) * (x.get('gap') or 0) for x in ds if (x.get('gap') or 0) > 0) or 1
        share = (drv.get('weight') or 0) * (drv.get('gap') or 0) / tot
        s = (f"The {'delay' if behind else 'shortfall'} sits in **{drv['name']}**. That discipline carries "
             f"{round((drv.get('weight') or 0) * 100)}% of the weight and is {drv.get('gap')} {plural(drv.get('gap'), 'point')} behind "
             f"({drv.get('actual')}% vs {drv.get('planned')}%), so it owns "
             + ('essentially the whole ' if share >= 0.85 else ('most of the ' if share >= 0.5 else 'the largest part of the '))
             + ('delay.' if behind else 'weighted shortfall.'))
        raw = [x for x in ds if x['name'] != drv['name'] and (x.get('gap') or 0) > (drv.get('gap') or 0)]
        if raw:
            ws = sorted({round((x.get('weight') or 0) * 100) for x in raw})
            s += (f" The bigger raw gaps are on lines worth {' / '.join(str(w) for w in ws)}% of the job each. Those are real "
                  f"problems, but they barely move weighted progress or the {P['fname'] if P['fid'] else 'finish'}.")
        cp.append(s)
    else:
        cp.append("No discipline is behind its planned progress on the weighted read, so there is no delay to place.")
    notes = []
    for x in ds:
        if (x.get('actual') or 0) <= 5 and (x.get('gap') or 0) >= 20 and late_open:
            link = token_link(x['name'], late_open)
            if link:
                notes.append(f"{x['name']} is at {x.get('actual')}% while it waits on a client input: {link['id']} "
                             f"'{clean(link['name'])}' is still open and {slip(link.get('slip_wd'))} late.")
                break
    off_big = [m for m in keys if (m.get('slip_wd') or 0) > (d or 0) and m.get('tf') is not None and m['tf'] >= 0]
    if off_big and behind:
        b = max(off_big, key=lambda m: m['slip_wd'])
        notes.append(f"{clean(b['name'])} has slipped {b['slip_wd']} wd but still has {sg(b['tf'])} wd float, so it isn't on "
                     f"the {P['fname']} path.")
    done = [x for x in ds if (x.get('actual') or 0) >= 95]
    if done:
        notes.append(', '.join(f"{x['name']} ({x.get('actual')}%)" for x in done) + ' '
                     + ('is' if len(done) == 1 else 'are') + ' essentially done.')
    s_conc = K.sec("Where it's concentrated — eng vs proc vs construction", *cp,
                   table=K.tbl(['Discipline', 'Weight', 'Done / plan', 'Gap (pts)'],
                               [[x['name'] + (' (driver)' if drv and x['name'] == drv['name'] else ''),
                                 f"{round((x.get('weight') or 0) * 100)}%", f"{x.get('actual')}% / {x.get('planned')}%",
                                 x.get('gap')] for x in ds], ' '.join(notes) or None))
    thinking.append(f"Weighed {len(ds)} disciplines by weight × gap"
                    + (f" — {drv['name']} carries the {'delay' if behind else 'shortfall'}" if drv else ''))

    # ── 4. inside the driver ────────────────────────────────────────────────────────────────────
    s_in = None
    if drv or vgroups or chain:
        hp = parts(head) if head else []
        tail = hp[1:3] if hp and drv and hp[0] == drv['name'] else hp[:2]
        label = (f"Inside {drv['name'] if drv else 'the job'}" +
                 (f" — {vtop['code']} and {' / '.join(tail)}" if vtop and tail else
                  (f" — {' / '.join(tail)}" if tail else (f" — {vtop['code']}" if vtop else ''))))
        ip, itable = [], None
        zero_pv = [g for g in vgroups if not (g.get('pv') or 0)]
        if vtop:
            tg = vg.get('total_gap') or sum((g.get('gap') or 0) for g in vgroups)
            pc = vtop.get('pct_of_gap') or 0
            s = (f"Inside {'the driver' if drv else 'the job'}, the value gap is "
                 + ('almost entirely ' if pc >= 90 else ('mostly ' if pc >= 60 else 'led by '))
                 + f"{vtop['code']}. Split by the file's {vg.get('dimension') or 'activity'} code, {vtop['code']} "
                   f"{'carry' if vtop['code'].endswith('s') else 'carries'} {_m(vtop.get('gap'))} of the {_m(tg)} PV−EV gap ({_pc(pc)}).")
            if zero_pv:
                s += (f" {' and '.join(g['code'] for g in zero_pv[:3])} show no gap at all. That isn't because "
                      f"{'it is' if len(zero_pv) == 1 else 'they are'} on time. None of {'its' if len(zero_pv) == 1 else 'their'} "
                      f"value was planned to be earned by {dd}.")
                last_ms = [x for x in chain if is_ms(x)] + ([fin] if fin else [])
                trap = None
                for g in zero_pv:
                    gt = toks(g['code']) - STOP - {'installation', 'installations'}
                    for m in last_ms:
                        if gt and gt & (toks(m.get('name')) - STOP):
                            trap = (g, m)
                            break
                    if trap:
                        break
                if trap:
                    s += (f" This is the trap in reading value alone: the finish date lands on {trap[0]['code'].lower()} "
                          f"({trap[1]['id']}), which shows no shortfall today.")
            ip.append(s)
            rows = [[g['code'], _m(g.get('pv')), _m(g.get('ev')), _m(g.get('gap')), _pc(g.get('pct_of_gap'))]
                    for g in vgroups[:10]]
            rows.append(['Total', _m(vg.get('total_pv') or sum((g.get('pv') or 0) for g in vgroups)),
                         _m(vg.get('total_ev') or sum((g.get('ev') or 0) for g in vgroups)), _m(tg), '100%'])
            itable = K.tbl([vg.get('dimension') or 'Code', 'PV', 'EV', 'PV − EV', 'Share of gap'], rows,
                           f"Values are in the project's own cost units, rounded, and read from the "
                           f"'{vg.get('dimension') or 'activity'}' activity code at the {dd} data date.")
        elif nok and chain:
            ip.append("This update carries no activity-code split of the value gap, so I read the concentration from the "
                      "network instead: where the finish chain sits and how far each front has slipped.")
        if head and nok:
            br2 = ' / '.join(hp[:2])
            wt = list(N.get('wbs_top') or [])
            cnt = next((w['activities'] for w in wt if w.get('branch') == br2), None)
            rank = next((i for i, w in enumerate(wt) if w.get('branch') == br2), None)
            same = [x for x in acts if ' / '.join(parts(x)[:2]) == br2]
            nxt = []
            for x in same[1:]:
                nm = clean(x['name'])
                if nm not in nxt and nm != clean(head['name']):
                    nxt.append(nm)
            s = (f"The finish chain starts in **{' / '.join(hp[1:]) or br2}**"
                 + (f" ({cnt} activities in {hp[1] if len(hp) > 1 else br2}, "
                    + ('the largest block in the file' if rank == 0 else f"the #{rank + 1} block in the file") + ')'
                    if cnt else '') + '.')
            s += f" It begins with {clean(head['name'])} ({head['id']})"
            if nxt:
                s += f" and continues through {', '.join(nxt[:6])}" + (' and more' if len(nxt) > 6 else '')
            s += '.'
            if same and all((x.get('pct') or 0) == 0 for x in same):
                s += f" None of that work — {len(same)} activities on the chain — has started."
            grp = _branch_ms(keys, hp)
            if len(grp) >= 2:
                s += (" The sectional milestones of that scope get later the closer they are to the chain: "
                      + ', '.join(f"{clean(m['name'])} {sg(m.get('slip_wd'))} wd" for m in grp[:6]) + '.')
            ip.append(s)
            if not vtop and fronts:
                rows = []
                for lab, c, n0 in fronts:
                    xs = [x for x in acts if labmap.get(x['id']) == lab]
                    rows.append([lab, c, n0, rng([x.get('slip_wd') for x in xs]), rng([x.get('tf') for x in xs])])
                itable = K.tbl(['Front on the finish chain', 'Activities', 'Not started', 'Slip (wd)', 'Float (wd)'], rows,
                               ("All under " + ' / '.join(common) + '. ' if common else '')
                               + "Read from the WBS of the chain traced back from the finish milestone.")
        if ip:
            s_in = K.sec(label, *ip, table=itable)

    # ── 5. the defensible number ────────────────────────────────────────────────────────────────
    dn = []
    if d is not None and d != 0:
        cal = f", or {abs(P['cal_days'])} calendar days" if P['cal_days'] is not None else ''
        if behind:
            moved = (f" {P['flabel'][0].upper() + P['flabel'][1:]} has moved from {bl} to {fc}" if bl and fc else '')
            flt = ((f", and P6's own total float on it reads {sg(tf)}." if moved else
                    f" The stored total float at the finish reads {sg(tf)}.") if tf is not None else ('.' if moved else ''))
            dn.append(f"**{sg(d)} working days (about {K.weeks(d)}{cal}) is the number you can defend."
                      + moved + flt
                      + f" How the {d} days split between employer and contractor, and how they built up update by update, "
                        f"are separate analyses. Neither changes the {d}.**")
        else:
            dn.append(f"**{K.wd(d)} ahead (about {K.weeks(d)}{cal}) is the defensible position"
                      + (f": {P['flabel']} is forecast {fc} against a {bl} baseline" if bl and fc else '') + '.**')
        hold = []
        if bl and fc:
            hold.append(f"Comparing dates ({bl} vs {fc}) gives {slip(d)}.")
        elif d:
            hold.append(f"The stored comparison of forecast and baseline finish gives {slip(d)}.")
        if tf is not None:
            sd = [x for x in chain + keys if is_ms(x) and x.get('finish') == fc and x.get('tf') == tf and x['id'] != P['fid']]
            seen = set()
            sd = [x for x in sd if not (x['id'] in seen or seen.add(x['id']))]
            hold.append(f"The {'network' if P['tf_src'] == 'milestone' else 'stored critical-path check'} gives {sg(tf)} wd total float on {P['fid'] or 'the finish'}"
                        + (' and on ' + ', '.join(f"{clean(x['name'])} ({x['id']})" for x in sd[:2])
                           + (', which finishes the same day' if len(sd) == 1 else ', which finish the same day') if sd else '') + '.')
            same_slip = [m for m in keys if m.get('slip_wd') == d and m['id'] not in {x['id'] for x in sd}]
            if same_slip:
                hold.append(', '.join(f"{clean(m['name'])} ({m['id']})" for m in same_slip[:2])
                            + f" {'has' if len(same_slip) == 1 else 'have'} slipped by the same {d} wd.")
        cpl, ptf = ck.get('critical_path_length_days'), ck.get('project_total_float_days')
        if ck.get('cpli') is not None and cpl and ptf is not None and ptf < 0:
            hold.append(f"CPLI confirms it too: the remaining critical path is {cpl} wd long, but only {cpl + ptf} wd are left "
                        f"before {bl or 'the baseline finish'}, so ({cpl} − {abs(ptf)}) ÷ {cpl} = {K.ratio(ck['cpli'])}.")
        if hold:
            dn.append(("It holds up because two independent measures agree. " if agree else
                       ("The measures, side by side: " if behind else '')) + ' '.join(hold))
        big = [m for m in keys if (m.get('slip_wd') or 0) > (d or 0) and m.get('tf') is not None and m['tf'] >= 0]
        if big and behind:
            b = max(big, key=lambda m: m['slip_wd'])
            dn.append(f"Keep one figure out of the headline. {clean(b['name'])} has slipped further ({slip(b['slip_wd'])}), "
                      f"but it has {sg(b['tf'])} wd float and doesn't drive the {P['fname']}. Calling it 'the delay' would "
                      "overstate the position.")
    elif d == 0:
        dn.append("**0 working days: the finish is on its baseline date.**")
    else:
        dn.append("**The finish slip can't be read from this update, so there is no defensible number yet — re-import the "
                  "file with its baseline.**")
    s_num = K.sec('The defensible number', *dn)

    # ── 6. SPI vs the date ──────────────────────────────────────────────────────────────────────
    s_spi = None
    if spi is not None and d is not None:
        ev_, pv_ = F.get('ev'), F.get('pv')
        sp = [f"They measure different things, so don't expect them to match and never use one to check the other. "
              f"SPI {K.ratio(spi)} measures volume: value earned"
              + (f" ({_m(ev_)}, {K.pct(F.get('actual_pct'))})" if ev_ else f" ({K.pct(F.get('actual_pct'))})")
              + " divided by the value planned by now"
              + (f" ({_m(pv_)}, {K.pct(F.get('planned_pct'))})" if pv_ else f" ({K.pct(F.get('planned_pct'))})")
              + f", across the whole job, whether on the critical path or not. {slip(d)} measures time: how far the "
                "finish has moved along the one chain that sets it."]
        s2 = ''
        if vtop and fronts:
            s2 = (f"On this job the two point at different places. {vtop['code']} "
                  f"{'cause' if vtop['code'].endswith('s') else 'causes'} {'almost all' if (vtop.get('pct_of_gap') or 0) >= 90 else 'most'} "
                  f"of the SPI shortfall ({_pc(vtop.get('pct_of_gap'))} of the gap). The date is set by a chain that runs "
                  f"through {' → '.join(lab for lab, _, _ in fronts[:5])}.")
            zp = [g['code'] for g in vgroups if not (g.get('pv') or 0)]
            if zp:
                s2 += (f" None of the {' or '.join(zp[:3])} value is due yet, so SPI can't see "
                       f"{'it' if len(zp) == 1 else 'them'}.")
        elif drv and fronts:
            s2 = (f"The SPI shortfall is weighted to {drv['name']} ({round((drv.get('weight') or 0) * 100)}% of the job); the "
                  f"date is set by the {len(chain)}-activity chain that runs through "
                  f"{' → '.join(lab for lab, _, _ in fronts[:5])}. Much of that chain isn't due yet, so SPI can't see it.")
        s2 += (" SPI will also drift back toward 1.0 as the job nears completion, whether or not the date recovers. "
               f"Quote {slip(d)} as the {'delay' if behind else 'position'} and SPI {K.ratio(spi)} as the pace, side by side.")
        sp.append(s2.strip())
        if F.get('cost_derived'):
            sp.append(f"Don't read CPI {K.ratio(cpi)} as good cost news either. Actual cost in this file is derived from "
                      "progress, so it equals earned value by definition and carries no cost signal.")
        else:
            sp.append(K.cost_note(F))
        s_spi = K.sec(f"Why SPI {K.ratio(spi)} and {slip(d)} aren't the same figure", *sp)

    # ── 7. but-for ──────────────────────────────────────────────────────────────────────────────
    s_bf = None
    if behind:
        bp = [f"The {sg(d)} wd is the total slip. This file can't tell you how much of it the employer caused and how much "
              "is yours." + (" It does show two contributors on negative-float paths, and both have to go into the analysis."
                             if nok and late_open else '')]
        btable = None
        if nok and late_open:
            roots = {parts(x)[0] for x in late_open if parts(x)}
            where = f" under '{next(iter(roots))}'" if len(roots) == 1 else ''
            negs = [x for x in late_open if (x.get('tf') or 0) < 0]
            e = (f"Employer side: late client inputs. {len(late_open)} {plural(len(late_open), 'item')}{where} "
                 f"{'is' if len(late_open) == 1 else 'are'} {rng([x.get('slip_wd') for x in late_open])} working days late, and "
                 + (f"all {len(late_open)} have" if len(negs) == len(late_open) and len(late_open) > 1 else f"{len(negs)} {plural(len(negs), 'has', 'have')}")
                 + f" negative float ({rng([x.get('tf') for x in negs])}).")
            if late_done:
                e += (f" Another {len(late_done)} client {plural(len(late_done), 'input')} arrived late "
                      f"({rng([x.get('slip_wd') for x in late_done], ' wd')}); already delivered, so history for the "
                      "analysis rather than a live risk.")
            e += " On this evidence these are strong EOT indicators. They are not yet proof of entitlement."
            bp.append(e)
            contractor = [x for x in deepest if not is_client(x) and (x.get('pct') or 0) == 0][:2]
            if contractor or head:
                c = "Contractor side: the unstarted work on and around the finish chain."
                if contractor:
                    c += (" The most negative float in the file is on contractor work that hasn't started: "
                          + ', '.join(f"{clean(x['name'])} ({x['id']}, {sg(x['tf'])})" for x in contractor))
                if head and head['id'] not in {x['id'] for x in contractor}:
                    c += (f"{', and' if contractor else ' It starts with'} {clean(head['name'])} ({head['id']}), which "
                          f"{'was due' if P['dd_dt'] and dt(head.get('baseline_finish')) and dt(head['baseline_finish']) <= P['dd_dt'] else 'is planned to finish'} "
                          f"{head.get('baseline_finish')} and is at {head.get('pct', 0)}%")
                c += (". One snapshot can't show whether that start is held up by an employer input or by the contractor's "
                      "own mobilisation.")
                bp.append(c)
            ch_tf = [x['tf'] for x in chain if x.get('tf') is not None] + [x['tf'] for x in deeper]
            in_tf = [x['tf'] for x in late_open if x.get('tf') is not None]
            if ch_tf and in_tf:
                if min(ch_tf) < min(in_tf):
                    bp.append(f"What the float hints at, and only hints at: the finish chain sits at {rng(ch_tf)}, which is "
                              f"more negative than any client input ({rng(in_tf)}). If this snapshot's float were the whole "
                              f"story, the client inputs alone would not explain all {d} days, which points toward concurrent "
                              "delay. But float from one update is not proof of cause.")
                else:
                    bp.append(f"What the float hints at, and only hints at: the client inputs sit as deep as the finish chain "
                              f"({rng(in_tf)} vs {rng(ch_tf)}), so they could explain the slip on their own. But float from "
                              "one update is not proof of cause.")
            btable = K.tbl(['Client input (ID)', 'Baseline → forecast', 'Slip (wd)', 'Float (wd)'],
                           [[f"{clean(x['name'])} ({x['id']})", f"{x.get('baseline_finish')} → {x.get('finish')}"
                             + ('*' if x.get('finish') == dd else ''), sg(x.get('slip_wd')), sg(x.get('tf'))]
                            for x in late_open[:12]],
                           ((f"* Still open at the data date, so P6 holds the forecast at {dd} and the slip grows every "
                             "working day the item stays open." if any(x.get('finish') == dd for x in late_open) else '')
                            + (f" Separately, {len([x for x in other_open if (x.get('tf') is not None and x['tf'] <= 0)])} "
                               "upcoming client inputs are on time but have zero float: "
                               + '; '.join(f"{short(x['name'], 50)} on {x.get('finish')}" for x in
                                           sorted([x for x in other_open if x.get('tf') is not None and x['tf'] <= 0],
                                                  key=lambda x: dt(x.get('finish')) or datetime.max)[:5])
                               + ". Any late delivery goes straight onto the path."
                               if any(x.get('tf') is not None and x['tf'] <= 0 for x in other_open) else '')).strip() or None)
        elif nok:
            bp.append("No late employer/client input is flagged in the file's WBS, so on this snapshot the slip reads as the "
                      "contractor's own execution on the finish chain — still to be confirmed.")
        bp.append("Settling the split needs a time-impact or windows analysis: insert the employer-side events (such as late "
                  "client inputs) as delay events and "
                  "re-run the network (Consultant Review), then walk the updates window by window (Update vs Update). This "
                  "snapshot can't show crews or productivity either, so whether the work was held back by resources or by "
                  "missing inputs is a question for Productivity & Resource Intelligence. Until that analysis is done, present "
                  f"{sg(d)} wd as the total slip, not as an apportioned or entitlement figure.")
        s_bf = K.sec('But-for — how much is contractor vs owner/consultant', *bp, table=btable)
        if nok and allc:
            thinking.append(f"Checked {len(allc)} client inputs ({len(late_open)} open and late) against the chain's float")

    # ── 8. how it built up ──────────────────────────────────────────────────────────────────────
    tr = F.get('trend')
    bu = []
    if tr and tr.get('prev_delay') is not None and d is not None:
        delta = tr.get('delta') or 0
        bu.append(f"Since the previous stored update the delay moved from {K.signed(tr['prev_delay'])} to {K.signed(d)} — "
                  + (f"{K.wd(delta)} lost this period." if delta > 0 else (f"{K.wd(delta)} recovered this period." if delta < 0
                                                                             else "no change this period."))
                  + " For the window-by-window attribution, run Update vs Update across all your updates.")
    else:
        bu.append("A period-by-period build-up (which update lost which days) needs earlier updates to compare against. This "
                  f"file is one snapshot (data date {dd}), so I won't reconstruct a trend from it. Load your earlier updates "
                  f"into Update vs Update and it will attribute the {'slip' if behind else 'movement'} window by window.")
    btab = None
    if nok and (keys or chain) and d:
        s = f"What this file does show is where in the network the {abs(d)} days {'built up' if behind else 'came from'}"
        first = []
        if keys_late and behind:
            grp = [m for m in _branch_ms(keys, parts(head) if head else []) if (m.get('slip_wd') or 0) > 0]
            seq = grp if len(grp) >= 2 else sorted([m for m in keys_late if (m.get('slip_wd') or 0) <= d],
                                                   key=lambda m: m.get('slip_wd') or 0)
            neg_ms = [m for m in seq if (m.get('tf') or 0) < 0]
            if seq:
                first.append(("the slip grows across the sectional dates of the scope the chain starts in: " if len(grp) >= 2 else
                              "the slip grows across the key dates: ")
                             + ', '.join(f"{clean(m['name'])} {sg(m['slip_wd'])} wd" for m in seq[:6])
                             + (f", up to {clean(seq[-1]['name'])} {sg(seq[-1]['slip_wd'])} wd" if len(seq) > 6 else '')
                             + ('. ' + (f"Only {' and '.join(clean(m['name']) for m in neg_ms[:3])} "
                                        f"{'carries' if len(neg_ms) == 1 else 'carry'} negative float and "
                                        f"{'sits' if len(neg_ms) == 1 else 'sit'} on the way to the finish"
                                        if neg_ms and len(neg_ms) < len(seq) else
                                        ('All of them carry negative float' if neg_ms else 'None of them carries negative float yet'))))
        if acts and head and head.get('slip_wd') is not None and behind:
            s0 = head['slip_wd']
            band = [x for x in acts if x.get('slip_wd') is not None and abs(x['slip_wd'] - d) <= 3]
            exc = [x for x in acts if x.get('slip_wd') is not None and abs(x['slip_wd'] - d) > 3]
            if s0 >= d - 3:
                first.append(f"the full {d} days are already present at the first activity of the finish chain. "
                             f"{clean(head['name'])} ({head['id']}) is {s0} wd late, and that same "
                             f"{rng([x['slip_wd'] for x in band])} wd carries unchanged"
                             + (f" ({'; '.join(clean(x['name']) + ' ' + x['id'] for x in exc[:2])} aside)" if exc else '')
                             + (f" through {' → '.join(lab for lab, _, _ in fronts[:5])}" if fronts else '')
                             + " to the finish. Nothing was added along the way; the whole delay comes from the late start "
                               "at the head. That matters for recovery: the downstream durations are as planned, so time can "
                               "only come back by compressing or overlapping them")
            else:
                first.append(f"the slip grows along the finish chain from {s0} wd at its head ({clean(head['name'])}, "
                             f"{head['id']}) to {d} wd at the finish, so about {d - s0} wd were added downstream — longer "
                             "durations, lags or logic. Baseline Revision Comparison shows which")
        if first:
            ords = ['First', 'Second']
            s += (', and ' + ('two things stand out. ' if len(first) == 2 else 'one thing stands out. ')
                  + ' '.join(f"{ords[i] + ', ' if len(first) == 2 else ''}{f[0].upper() + f[1:] if len(first) == 1 else f}"
                             + ('' if f.endswith('.') else '.') for i, f in enumerate(first)))
        else:
            s += '.'
        bu.append(s)
        rows = [[f"{clean(m['name'])} ({m['id']})", f"{m.get('baseline_finish')} → {m.get('finish')}", sg(m.get('slip_wd')),
                 sg(m.get('tf'))] for m in (keys + ([fin] if fin else []))[:16]]
        btab = K.tbl(['Milestone (ID)', 'Baseline → forecast', 'Slip (wd)', 'Float (wd)'], rows,
                     "Read from the key dates in your file. Positive float means the milestone isn't driving the "
                     f"{P['fname'] if P['fid'] else 'finish'} today.")
    s_build = K.sec('How it built up, period by period', *bu, table=btab)
    if chain:
        thinking.append(f"Traced the {len(chain)}-activity finish chain back to its head and followed the slip along it")

    # ── verdict / pills ─────────────────────────────────────────────────────────────────────────
    if d is None:
        verdict = "I can't size the delay from this update — the finish has no baseline to compare against."
    elif behind:
        verdict = (("Genuine: " if genuine else "Real, with tells to clear: ") + f"{sg(d)} working days on "
                   + (f"{P['fname']} ({bl} → {fc})" if bl and fc else 'the finish')
                   + (", float agreeing to the day" if agree else '')
                   + ((", and it starts at the unstarted " if (head.get('pct') or 0) == 0 else ", and it starts at ")
                      + f"{clean(head['name'])} ({head['id']})" if head else '')
                   + ". Who owns it needs a TIA, not this snapshot.")
    elif ahead:
        verdict = (f"There's no delay: the finish is {K.wd(d)} ahead of its baseline" + (f" ({fc} vs {bl})" if fc and bl else '')
                   + f", SPI {K.ratio(spi)}. " + ("Nothing in the checks suggests a paper gain." if genuine else
                                                  "Clear the flagged checks before you bank the gain."))
    else:
        verdict = f"No delay: the finish is on its baseline date (SPI {K.ratio(spi)})."
    pills = [K.pill(('Genuine: logic is clean' if behind else 'Gain reads as genuine') if genuine
                    else f"{n_bad} integrity {plural(n_bad, 'tell')} to clear",
                    'success' if genuine else 'warning') if checks and d else None,
             K.pill(f"{slip(d)} · float {sg(tf)} agrees" if agree else (slip(d) if d is not None else None),
                    'danger' if behind else ('success' if ahead else 'neutral')),
             K.pill(f"Starts at {short(head['name'], 32)}", 'danger') if head and behind else None,
             K.pill(f"{vtop['code']} = {_pc(vtop.get('pct_of_gap'))} of gap", 'warning') if vtop else
             (K.pill(f"{drv['name']} = {round((drv.get('weight') or 0) * 100)}% of weight", 'warning') if drv else None),
             K.pill(f"{len(late_open)} client {plural(len(late_open), 'input')} late ({rng([x.get('slip_wd') for x in late_open], ' wd')})",
                    'warning') if late_open else None,
             K.pill(f"SPI {K.ratio(spi)} ≠ the date", 'neutral') if spi is not None and d else None,
             K.pill('Split needs TIA / Consultant Review', 'accent') if behind else None]

    measured = (f"How this is measured from your P6 file (update {dd}). "
                + (f"The delay is measured on {P['flabel']}: baseline finish vs current forecast finish in working days ({slip(d)}). "
                   if d is not None else '')
                + (f"That is cross-checked against P6's own total float ({sg(tf)})" if tf is not None else '')
                + (f" and against CPLI (({ck.get('critical_path_length_days')} − {abs(ck['project_total_float_days'])}) ÷ "
                   f"{ck.get('critical_path_length_days')} = {K.ratio(ck.get('cpli'))})"
                   if ck.get('cpli') is not None and ck.get('critical_path_length_days') and (ck.get('project_total_float_days') or 0) < 0 else '')
                + ('. ' if tf is not None else '')
                + (f"The {abs(P['cal_days'])} calendar days is plain date arithmetic. " if P['cal_days'] is not None and d else '')
                + ("The integrity checks are read off the network: out-of-sequence, open-end, dangling and negative-float "
                   f"counts{f' across the {total:,} audited activities' if total and F.get('has_audit') else ''}"
                   + (f", plus the slip carried along the {len(chain)}-activity chain traced back from the finish" if chain else '')
                   + '. ')
                + "Concentration is weighted by discipline"
                + (f", and the PV−EV gap is then split by the file's {vg.get('dimension')} code. " if vtop else
                   (", then placed on the finish chain's WBS. " if chain else '. '))
                + (f"SPI = EV ÷ PV ({_m(F.get('ev'))} ÷ {_m(F.get('pv'))}). " if F.get('ev') and F.get('pv') else '')
                + (f"CPI is {K.ratio(cpi)} because actual cost is derived from progress. " if F.get('cost_derived') else '')
                + ("Client inputs are the activities whose WBS or name marks them as employer / client / consultant inputs, "
                   "with baseline vs forecast finish and total float. " if allc else '')
                + "Not in this file: "
                + ('hard constraints (not computable from the export), ' if not hk.get('computable') else '')
                + "calendar changes since the baseline, resource loading, and earlier updates. That is why the "
                  "employer/contractor split (Consultant Review) and the period build-up (Update vs Update) are separate passes.")
    top_in = sorted(late_open, key=lambda x: (x.get('tf') if x.get('tf') is not None else 0))[:5]
    zero_up = [x for x in other_open if x.get('tf') is not None and x['tf'] <= 0]
    actions = [
        ((f"Quote {sg(d)} working days" if behind else f"Quote {K.wd(d)} ahead")
         + (f" ({abs(P['cal_days'])} calendar days)" if P['cal_days'] is not None else '')
         + (f" on {P['fid']}" if P['fid'] else '') + f" as the headline {'delay' if behind else 'position'} and SPI "
         f"{K.ratio(spi)} as the pace, as separate figures."
         + (f" Keep CPI {K.ratio(cpi)} out of any cost story." if F.get('cost_derived') else '')) if d else '',
        (f"Before the number goes outside, run the Schedule Audit constraint check and look at the "
         f"{len(deeper)} {plural(len(deeper), 'activity', 'activities')} with more negative float than the finish ("
         + ', '.join(f"{x['id']} {sg(x['tf'])}" for x in deeper[:4]) + ").") if deeper else
        ("Run the Schedule Audit constraint check before the number goes outside." if not hk.get('computable') else ''),
        (f"Run the Calendar Audit and the Baseline Revision calendar-match on the {F.get('calendar_count')} "
         f"{plural(F.get('calendar_count') or 0, 'calendar')} to rule out calendar inflation.") if F.get('calendar_count') else
        "Run the Calendar Audit to rule out calendar inflation.",
        (f"Enter the {len(late_open)} late client {plural(len(late_open), 'input')} in the delay register with baseline, "
         "forecast, slip and float, and check your contract's notice clause. Missing a notice deadline, not missing proof, "
         "is what can lose an EOT.") if late_open else '',
        ("Chase the open inputs in order of float: " + ', '.join(f"{short(x['name'], 50)} ({sg(x.get('tf'))})" for x in top_in)
         + '.') if top_in else '',
        (f"Find out why {clean(head['name'])} ({head['id']}) "
         + ("hasn't started" if (head.get('pct') or 0) == 0 else f"is only {head.get('pct')}% done")
         + ", whether it's an employer hold or our own mobilisation, and record the answer. It decides the concurrency "
           "argument.") if head and behind else '',
        ("Run Consultant Review with the client inputs as delay events, and Update vs Update across your earlier updates, "
         "before stating any split or claim.") if behind else "Keep each update's file so Update vs Update can confirm the trend.",
        (f"Watch the {len(zero_up)} upcoming client {plural(len(zero_up), 'input')} with zero float ("
         + by_date_ids(zero_up) + ").") if zero_up else '',
    ]
    evidence = [K.ev('Delay', f"{slip(d)} (~{max(1, round(abs(d) / 5))} wk"
                     + (f"; {abs(P['cal_days'])} calendar days" if P['cal_days'] is not None else '') + ')' if d else None),
                K.ev(f"Finish ({P['fid']})" if P['fid'] else 'Finish', f"{bl} → {fc}" if bl and fc else fc),
                K.ev('Float on finish', f"{sg(tf)} wd" + (' (agrees with slip)' if agree else '') if tf is not None else None),
                K.ev('Chain origin', f"{head['id']} {clean(head['name'])}: due {head.get('baseline_finish')}, {head.get('pct', 0)}%"
                     if head else None),
                K.ev('SPI', f"{K.ratio(spi)} ({K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}): pace, not date"
                     if spi is not None else None),
                K.ev('CPI', f"{K.ratio(cpi)}, derived from progress" if F.get('cost_derived') else K.ratio(cpi) if cpi is not None else None),
                K.ev(f"{vtop['code']} share of PV−EV gap", _pc(vtop.get('pct_of_gap'))) if vtop else
                (K.ev('Driver', f"{drv['name']} ({round((drv.get('weight') or 0) * 100)}% weight)") if drv else None),
                K.ev('Client inputs late', f"{len(late_open)}, {rng([x.get('slip_wd') for x in late_open], ' wd')}, float "
                     f"{rng([x.get('tf') for x in late_open])}" if late_open else None),
                K.ev('OOS', f"{F.get('oos_count')} ({K.pct(F.get('oos_pct'), 1)}), {F.get('critical_oos') or 0} critical"
                     + (f", {F['oos_grade']}" if F.get('oos_grade') else '') if F.get('oos_count') is not None else None),
                K.ev('Open ends / dangling', f"{F.get('open_ends')} / {F.get('dangling_count')}"
                     if F.get('open_ends') is not None and F.get('dangling_count') is not None else None),
                K.ev('Negative float', f"{neg:,} ({K.pct(negp, 1)})" if neg is not None else None),
                K.ev('Hard constraints', 'Not computable; verify' if (F.get('audit') or {}).get('hard_constraints') and not hk.get('computable')
                     else None)]
    a = K.A2(verdict, [s_int, s_tells, s_conc, s_in, s_num, s_spi, s_bf, s_build], pills=pills, measured=measured,
             actions=actions, evidence=evidence,
             drilldowns=[K.drill('q04', 'What exactly is on the finish chain, and how much float is left?'),
                         K.drill('q13', 'Do the late client inputs support an EOT?') if late_open else
                         (K.drill('q13', 'Is there an EOT case?') if behind else None),
                         K.drill('q05', f"How do I recover the ~{d} days?") if behind else
                         K.drill('q02', 'When will we finish, and will we hit the dates?'),
                         K.drill('q14', f"Check the {F.get('calendar_count')} calendars for inflation" if F.get('calendar_count')
                                 else 'Check the calendars for inflation')])
    a['thinking'] = thinking[:4]
    return a
