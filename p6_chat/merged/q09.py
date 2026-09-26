"""q09 — Manpower & resources: is it realistic, and is the delay resource-driven?

Covers: logic-limited vs manpower-limited (the finish chain, how it slipped, crew-movement ties), manpower vs
sequencing and the weighted worst discipline, the late client inputs as the other contributor, concurrent
work-fronts at the back end, whether resourcing changed between revisions, and the realism checks (peak, ramp,
histogram, resource loading, productivity) — saying plainly what this read can and can't show. For ANY project.

The chat's read of the P6 file carries dates, float and progress — not the resource assignments — so no peak,
histogram or man-hour figure is ever quoted; the answer reads what the network proves and routes the rest to
Productivity & Resource Intelligence, Duration & Resource Calculation and Baseline Revision Comparison.
"""
import re
from datetime import timedelta

from . import _kit2 as K
from .q08 import _date, _i, _n, _names, _nm, _poss, _tokens, implied_bac, _m

BACK_END_DAYS = 21      # finish milestones forecast within this many calendar days of the finish = the back-end window


def _area(x):
    parts = [p for p in (x.get('wbs') or '').split(' / ') if p]
    return parts[-1] if parts else '(no WBS)'


def _front(x):
    parts = [p for p in (x.get('wbs') or '').split(' / ') if p]
    return ' / '.join(parts[-2:]) if parts else '(no WBS)'


def _fronts(chain):
    """Group the chain by work front (last two WBS levels), in order of first appearance: [(front, [rows])]."""
    out, idx = [], {}
    for x in chain:
        f = _front(x)
        if f not in idx:
            idx[f] = len(out)
            out.append((f, []))
        out[idx[f]][1].append(x)
    return out


def _repeated_op(rows):
    """The same operation (activity name) appearing in two or more areas: (name, [areas]) or None."""
    seen = {}
    for x in rows:
        key = ' '.join((x.get('name') or '').lower().split())
        if key:
            seen.setdefault(key, []).append(x)
    best = None
    for key, xs in seen.items():
        areas = []
        for x in xs:
            a = _area(x)
            if a not in areas:
                areas.append(a)
        if len(areas) >= 2 and (best is None or len(areas) > len(best[1])):
            best = (_nm(xs[0]['name']), areas)
    return best


def _span(ds):
    ds = [d for d in ds if d]
    if not ds:
        return None, None
    return min(ds), max(ds)


def _months(a, b):
    if not a or not b:
        return ''
    return (f"{a:%b} to {b:%b %Y}" if a.year == b.year else f"{a:%b %Y} to {b:%b %Y}") if (a.year, a.month) != (b.year, b.month) \
        else f"{b:%b %Y}"


def _fmt(dt):
    return dt.strftime('%d-%b-%Y') if dt else '—'


def _pos(d):
    """'60 wd behind' / '12 wd ahead' / 'on the date'."""
    if d is None:
        return 'not measurable'
    d = round(d)
    return f"{d} wd behind" if d > 0 else (f"{abs(d)} wd ahead" if d < 0 else 'on the date')


def build(F, N, role):
    d = F.get('delay_days')
    behind, ahead = (d or 0) > 0, (d or 0) < 0
    spi, P, A_ = F.get('spi'), F.get('planned_pct'), F.get('actual_pct')
    dd = F.get('data_date')
    dd_dt = _date(dd)
    drv = K.main_driver(F)
    derived = bool(F.get('cost_derived'))
    nok = bool(N and N.get('ok'))
    fin = (N.get('finish_milestone') or {}) if nok else {}
    ftf = N.get('finish_tf') if nok else None
    chain = (N.get('chain') or []) if nok else []
    n_chain = N.get('chain_count', len(chain)) if nok else 0
    head = chain[0] if chain else None
    thinking = []

    # ── chain facts ─────────────────────────────────────────────────────────────
    started = sum(1 for x in chain if (x.get('pct') or 0) > 0)
    all_zero = bool(chain) and started == 0
    tfs = [x['tf'] for x in chain if x.get('tf') is not None]
    slips = sorted(x['slip_wd'] for x in chain if x.get('slip_wd') is not None)
    med = slips[len(slips) // 2] if slips else None
    near = [s for s in slips if med is not None and abs(s - med) <= 3]
    uniform = len(slips) >= 5 and len(near) >= 0.8 * len(slips)
    head_bl = _date(head.get('baseline_finish')) if head else None
    overdue = bool(head and head_bl and dd_dt and head_bl < dd_dt and (head.get('pct') or 0) < 100)
    fronts = _fronts(chain)
    deepest = (N.get('deepest') or []) if nok else []
    rep = _repeated_op(chain + deepest) if nok else None
    if chain:
        thinking.append(f"Traced the {n_chain}-activity finish chain and measured its slip "
                        f"({_i(slips[0])} to {_i(slips[-1])} wd" + (f", {len(near)} of {len(slips)} within 3 wd of the median"
                                                                  if slips else '') + ')' if slips else
                        f"Traced the {n_chain}-activity finish chain")

    # ── client inputs ───────────────────────────────────────────────────────────
    late_ci = sorted([x for x in ((N.get('client_inputs_late_open') or []) if nok else [])],
                     key=lambda x: (x.get('tf') is None, x.get('tf') if x.get('tf') is not None else 0))
    neg_ci = [x for x in late_ci if x.get('tf') is not None and x['tf'] < 0]
    deep_ci = [x for x in neg_ci if ftf is not None and ftf < 0 and x['tf'] <= 0.5 * ftf]
    worst_ci = neg_ci[0] if neg_ci else None
    if nok:
        thinking.append(f"Checked {len(N.get('client_inputs') or [])} client/employer input activities — "
                        f"{len(late_ci)} late and still open")

    # ── back-end concurrency ────────────────────────────────────────────────────
    fin_dt = _date(fin.get('finish'))
    open_fms = [m for m in ((N.get('milestones') or []) if nok else [])
                if m.get('type') == 'FinishMilestone' and not m.get('done') and m.get('id') != fin.get('id')
                and _date(m.get('finish'))]
    cluster = [m for m in open_fms if fin_dt and timedelta(0) <= fin_dt - _date(m['finish']) <= timedelta(days=BACK_END_DAYS)]
    c_bl_lo, c_bl_hi = _span([_date(m.get('baseline_finish')) for m in cluster])
    c_fc_lo, c_fc_hi = _span([_date(m.get('finish')) for m in cluster])
    squeeze = None
    for i, a in enumerate(open_fms):
        for b in open_fms[i + 1:]:
            if a in cluster and b in cluster:
                continue
            ab, bb = _date(a.get('baseline_finish')), _date(b.get('baseline_finish'))
            if not (ab and bb):
                continue
            blg, fcg = abs((ab - bb).days), abs((_date(a['finish']) - _date(b['finish'])).days)
            if blg >= 7 and fcg <= 2:
                squeeze = (a, b, blg, fcg)
                break
        if squeeze:
            break
    if open_fms:
        thinking.append(f"Compared the baseline and forecast spacing of {len(open_fms)} open key-date milestones")

    # ── discipline / value gap ──────────────────────────────────────────────────
    ds = sorted(F.get('disciplines') or [], key=lambda x: -(_n(x.get('weight')) or 0))
    wsum = sum((_n(x.get('weight')) or 0) * max(_n(x.get('gap')) or 0, 0) for x in ds)
    vg = F.get('value_gap') if isinstance(F.get('value_gap'), dict) else {}
    groups = [g for g in (vg.get('groups') or []) if isinstance(g, dict)]
    gapg = sorted([g for g in groups if (_n(g.get('gap')) or 0) > 0], key=lambda g: -(_n(g.get('gap')) or 0))
    top = gapg[0] if gapg else None
    dim = vg.get('dimension') or 'activity code'
    tot_pv = sum(_n(g.get('pv')) or 0 for g in groups) or None
    thinking.append("Weighed each discipline's gap by its share of the job" if not top else
                    f"Split the value gap across {len(groups)} {dim} codes and their share of planned value")

    oos, oos_pct, oos_grade, crit_oos = F.get('oos_count'), F.get('oos_pct'), F.get('oos_grade'), F.get('critical_oos')
    concl = (((F.get('audit') or {}).get('out_of_sequence') or {}).get('kpis') or {}).get('executive_conclusion') or ''
    mpk = re.search(r'concentrated in the (.+?) package \((\d+) of (\d+)', concl)
    oos_ok = oos is not None and (_n(oos_pct) or 0) < 5
    hd = ((F.get('audit') or {}).get('high_duration') or {}).get('kpis') or {}
    if not chain:
        if oos is not None:
            thinking.append(f"Read the sequencing and density audits ({oos} out-of-sequence, "
                            f"{F.get('neg_float_count') if F.get('neg_float_count') is not None else 'n/a'} on negative float)")
        thinking.append("Looked for resource assignments in the stored facts — none are carried, so no histogram is quoted")

    # ── verdict ─────────────────────────────────────────────────────────────────
    head_nm = _nm(head['name'], 40) if head else ''
    if behind and chain:
        verdict = (f"This file can't prove a manpower-driven delay: the ~{round(d)} wd sits on a {n_chain}-activity chain"
                   + (" that hasn't started" if all_zero else f" that is only {started} of {len(chain)} started")
                   + (f", and its first activity, {head_nm}, is already past its {head['baseline_finish']} baseline finish"
                      if overdue else '')
                   + ". Find out why on site before you add crews.")
    elif behind:
        verdict = (f"Nothing in the stored numbers proves a manpower-driven delay: you're {_pos(d)} at SPI "
                   f"{K.ratio(spi)}" + (f", carried by {drv['name']}" if drv else '')
                   + ". The resource read needs the schedule file and its resource assignments.")
    elif ahead:
        verdict = (f"No sign of a resource-driven delay — you're {abs(round(d))} wd ahead (SPI {K.ratio(spi)}). Whether "
                   "the manpower plan is realistic is a resource-loading question this read can't settle on its own.")
    else:
        verdict = (f"No resource-driven delay shows in this update (SPI {K.ratio(spi)}). Whether the manpower plan is "
                   "realistic is a resource-loading question this read can't settle on its own.")

    pills = [K.pill('manpower cause: not provable from this file', 'warning') if behind else
             K.pill(f"{_pos(d)} · SPI {K.ratio(spi)}", 'success') if d is not None else None,
             (K.pill('finish chain 0% started', 'danger') if all_zero else
              K.pill(f"finish chain {started}/{len(chain)} started", 'warning')) if chain else None,
             K.pill(f"{head_nm} due {head['baseline_finish']} · not started", 'danger')
             if (overdue and not head.get('pct')) else None,
             (K.pill(f"OOS {K.pct(oos_pct, 1)} · crews follow the logic", 'success') if oos_ok else
              K.pill(f"OOS {K.pct(oos_pct, 1)} · sequencing issue", 'warning')) if oos is not None else None,
             K.pill('resource assignments: not in this read', 'warning'),
             K.pill(f"client inputs on {_i(deep_ci[-1]['tf'])} to {_i(deep_ci[0]['tf'])} wd paths", 'accent')
             if len(deep_ci) >= 2 else (K.pill(f"{len(late_ci)} client inputs late", 'accent') if late_ci else None)]

    # ── 1. logic-limited or manpower-limited ────────────────────────────────────
    if chain:
        lead = ("**This file can't prove the delay is manpower-driven. What it does show is that the "
                + (f"~{round(d)} working days sit" if behind else "finish date sits")
                + f" on a {n_chain}-activity chain" + (" that hasn't started" if all_zero else '')
                + ". Whether that comes down to crews and plant or to access and inputs is a site question. The schedule "
                "can't answer it.**")
        route = '; '.join(f"{f} ({len(xs)})" for f, xs in fronts[:6])
        p2 = ("Two ways a finish gets set. Logic-limited: the dependencies fix the date, and more crews won't move it. "
              "Manpower-limited: work could run side by side, but there aren't enough crews, so it queues. "
              f"The chain that sets your finish starts at {_nm(head['name'])} ({head['id']}). It is {head.get('pct', 0)}% "
              f"done, with total float {_i(head.get('tf'))} wd"
              + (f" and a baseline finish of {head['baseline_finish']}" if head.get('baseline_finish') else '')
              + (f", so it should already be finished at the {dd} data date." if overdue else '.')
              + f" From there it runs through {route}"
              + (f", to {_nm(fin.get('name'))} ({fin.get('id')})" if fin.get('id') else '') + '.'
              + (" Every link is 0%" if all_zero else f" {started} of {len(chain)} links have started")
              + (f", and the chain sits at {_i(max(tfs))} to {_i(min(tfs))} wd of float." if tfs else '.')
              + " Whether anything in the logic is holding its first activity isn't in this read — check its "
              "predecessors in P6. If none is still open, the late start is a site decision (crews, plant, access or "
              "inputs), not logic.")
        readings = []
        if uniform:
            readings.append(f"The slip is almost the same all the way down the chain: {_i(near[0])} to {_i(near[-1])} wd on "
                            f"{len(near)} of {len(slips)} links. The durations haven't stretched; the whole chain has been "
                            "pushed right" + (" because it never started" if all_zero else '')
                            + ", so this is a late start, not slow production inside the chain.")
        elif slips:
            readings.append(f"The slip varies along the chain ({_i(slips[0])} to {_i(slips[-1])} wd), so durations or logic "
                            "inside it have changed too — production on the chain is part of the story. Update Analysis "
                            "shows which links stretched.")
        if rep:
            readings.append(f"Part of the logic may be a resource decision rather than physics. The same operation repeats "
                            f"across areas — {rep[0]} in {_names(rep[1][:3])} — which is where a crew, rig or formwork set "
                            "moving from one area to the next usually sits in the logic. If those ties are crew movement, a "
                            "second crew or set lets the areas overlap, and that is exactly where extra resources could "
                            "shorten the chain.")
        p3 = ''
        if readings:
            p3 = ('Two readings follow. First, ' + readings[0][0].lower() + readings[0][1:] + ' Second, '
                  + readings[1][0].lower() + readings[1][1:]) if len(readings) == 2 else readings[0]
        s1 = K.sec('Logic-limited or manpower-limited?', lead, p2, p3)
    else:
        s1 = K.sec('Logic-limited or manpower-limited?', K.network_note(N),
                   "Two ways a finish gets set. Logic-limited: the dependencies fix the date, and more crews won't move it. "
                   "Manpower-limited: work could run side by side, but there aren't enough crews, so it queues. Telling "
                   "them apart needs the chain that sets the finish, which comes from the file."
                   + (f" From the stored numbers alone: SPI {K.ratio(spi)}, the finish {_pos(d)}"
                      + (f", and {F.get('neg_float_count')} activities on negative float" if F.get('neg_float_count') is not None else '')
                      + '.' if d is not None else ''))

    # ── 2. manpower or sequencing ───────────────────────────────────────────────
    if oos is None:
        q1 = ("Out-of-sequence progress wasn't audited for this update, so sequencing can't be ruled in or out — run the "
              "Schedule Audit.")
    elif oos_ok:
        q1 = (f"Sequencing isn't the problem. Out-of-sequence progress covers {oos} activities ({K.pct(oos_pct, 1)}"
              + (f", graded {oos_grade}" if oos_grade else '') + ")."
              + (f" Only {crit_oos} of them are on the critical path" if crit_oos is not None else '')
              + (f", and {mpk.group(2)} of the {mpk.group(3)} are in the {mpk.group(1)} package" if mpk else '')
              + ", so the crews are largely working in the planned order.")
    else:
        q1 = (f"Sequencing is part of the problem: {oos} activities ({K.pct(oos_pct, 1)}) were progressed out of sequence"
              + (f", {crit_oos} on the critical path" if crit_oos is not None else '')
              + ". Review them in the Out-of-Sequence review before blaming manpower.")
    slow = (spi is not None and spi < 1) or behind
    if drv and not slow:
        q1 += (f" Overall pace is at or ahead of plan (SPI {K.ratio(spi)}). The only line behind on the weighted read is "
               f"{drv['name']}, {drv.get('gap')} point{'s' if drv.get('gap') != 1 else ''} under its plan "
               f"({drv.get('actual')}% against {drv.get('planned')}%) — too small to point at a manpower shortfall.")
    elif drv:
        q1 += (f" The shortfall is pace, and it sits where the weight is. {drv['name']} is "
               f"{round((_n(drv.get('weight')) or 0) * 100)}% of the job and stands at {drv.get('actual')}% done against "
               f"{drv.get('planned')}% planned.")
        if not top and wsum:
            share = (_n(drv.get('weight')) or 0) * (_n(drv.get('gap')) or 0) / wsum * 100
            if share >= 80:
                q1 += (f" On the weighted read that line carries {round(share)}% of the whole shortfall, so SPI "
                       f"{K.ratio(spi)} is essentially {_poss(drv['name'])} SPI.")
        others = [x['name'] for x in ds if x is not drv and (x.get('gap') or 0) >= 20]
        if others and slow:
            q1 += (f" The bigger raw gaps on {_names(others[:3])} carry little weight, so they barely move the finish"
                   " (the engineering & procurement answer covers them).")
    if top and tot_pv:
        share_pv = (_n(top.get('pv')) or 0) / tot_pv * 100
        q1 += (f" Inside the value, {top['code']} carries {round(_n(top.get('pct_of_gap')) or 0, 2)}% of the gap between "
               "planned and earned value.")
        if share_pv >= 80:
            q1 += (f" Read that figure with care. {top['code']} also carries {share_pv:.1f}% of all planned value in the "
                   f"file, so SPI {K.ratio(spi)} is really {_poss(top['code'])} SPI, and the other fronts barely register "
                   "in it.")
        rows = []
        for g in groups:
            gpv = _n(g.get('pv')) or 0
            sp = gpv / tot_pv * 100
            rows.append([g['code'], ('<0.1%' if 0 < sp < 0.1 else f"{sp:.1f}%" if sp < 99.95 else '100%') if gpv else '0%',
                         K.ratio((_n(g.get('ev')) or 0) / gpv) if gpv else '—',
                         f"{_n(g.get('pct_of_gap')) or 0:.2f}%" if (_n(g.get('pct_of_gap')) or 0) else '0%'])
        zero = [g['code'] for g in groups if not (_n(g.get('pv')) or 0)]
        track = []
        for z in zero:
            zt = _tokens(z)
            m = next((m for m in open_fms + ([fin] if fin else [])
                      if zt and zt & _tokens(m.get('name')) and m.get('slip_wd') is not None), None)
            if m:
                track.append(f"{_nm(m['name'])} {_i(m['slip_wd'])} wd")
        t2 = K.tbl([f"{dim} (P6 code)", 'Share of planned value', 'Earned ÷ planned', 'Share of value gap'], rows,
                   f"Planned value (PV) and earned value (EV) per '{dim}' code at the {dd} data date."
                   + (f" {_names(zero)} carry no value, so track them by milestone instead"
                      + (': ' + ', '.join(track) + '.' if track else '.') if zero else ''))
    else:
        t2 = K.tbl(['Discipline', 'Weight', 'Earned ÷ planned', 'Share of weighted shortfall'],
                   [[x['name'] + (' (driver)' if drv and x['name'] == drv['name'] else ''),
                     f"{round((_n(x.get('weight')) or 0) * 100)}%",
                     K.ratio((_n(x.get('actual')) or 0) / _n(x['planned'])) if _n(x.get('planned')) else '—',
                     f"{round((_n(x.get('weight')) or 0) * max(_n(x.get('gap')) or 0, 0) / wsum * 100)}%" if wsum else '—']
                    for x in ds],
                   "Progress by discipline from the stored EVM result; the shortfall share is weight × gap, the measure "
                   "that moves the overall %. The value split by an activity code wasn't stored with this update.")
    s2 =K.sec('Manpower or sequencing — and which discipline', q1, table=t2)

    # ── 3. input-driven? ────────────────────────────────────────────────────────
    if late_ci:
        i1 = (f"The other visible contributor isn't manpower at all. {len(late_ci)} client and consultant input"
              f"{'s are' if len(late_ci) > 1 else ' is'} late and still open at the data date."
              + (f" {'All' if len(neg_ci) == len(late_ci) else len(neg_ci)} of them sit on negative float" if neg_ci else '')
              + (f", {len(deep_ci)} of them at {_i(deep_ci[-1]['tf'])} to {_i(deep_ci[0]['tf'])} wd" if len(deep_ci) >= 2 else '')
              + (" (table below)." if neg_ci else " (table below)."))
        if worst_ci and ftf is not None:
            if worst_ci['tf'] > ftf:
                i2 = (f"None of them is as negative as the {_i(ftf)} wd finish chain, so none of them sets today's date. But "
                      f"even with that chain fully recovered, the {_nm(worst_ci['name'], 48)} path would still run "
                      f"{abs(worst_ci['tf'])} wd late. That is concurrency: an employer-side delay running alongside "
                      + ("a front that hasn't started." if all_zero else "the contractor's own chain."))
            else:
                i2 = (f"{_nm(worst_ci['name'], 48)} sits at {_i(worst_ci['tf'])} wd, as negative as the finish itself, so it "
                      "may be on the path that sets the date.")
            i2 += (" Splitting the two takes a time-impact analysis (TIA) or a windows analysis, run through Consultant "
                   "Review and Update vs Update. These inputs are strong EOT indicators, not proof.")
        else:
            i2 = ("None of them sits on negative float, so they aren't holding the finish today; keep them chased so they "
                  "don't become the path.")
        t3 = K.tbl(['Client / consultant input (open)', 'Slip vs baseline (wd)', 'Float (wd)'],
                   [[f"{x['id']} {_nm(x['name'], 70)}", _i(x.get('slip_wd')), _i(x['tf']) if x.get('tf') is not None else '—']
                    for x in late_ci[:10]],
                   "Ranked by float. Full dates and the engineering reading are in the engineering & procurement answer.")
        s3 = K.sec('Or input-driven? The late client inputs', i1, i2, table=t3)
    elif nok:
        s3 = K.sec('Or input-driven? The late client inputs',
                   "No late, open employer or client input activities are flagged in the file's WBS, so nothing points to "
                   "an input-driven delay. If client inputs aren't modelled as activities, add them — without them the "
                   "schedule can't show an employer-side delay at all.")
    else:
        s3 = K.sec('Or input-driven? The late client inputs',
                   "The client-input check reads the activities in the file, so it needs the schedule re-read (see above). "
                   "Late employer inputs on negative float are the other usual contributor to check before blaming manpower.")

    # ── 4. concurrent fronts ────────────────────────────────────────────────────
    crit, crit_pct = F.get('cpli_critical_count'), F.get('cpli_critical_pct')
    neg, neg_pct = F.get('neg_float_count'), F.get('neg_float_pct')
    c1 = ''
    if crit is not None and neg is not None:
        dense = (_n(crit_pct) or 0) >= 30 or (_n(neg_pct) or 0) >= 30
        c1 = (f"{'The network is dense.' if dense else 'The network is not unusually dense.'} {crit} activities "
              f"({K.pct(crit_pct, 1)}) sit at critical float and {neg} ({K.pct(neg_pct, 1)}) sit on negative float"
              + (", so almost every front is near-critical at once." if dense else ", so there is room to stagger fronts."))
    if len(cluster) >= 2 and c_bl_lo and c_fc_lo:
        bl_spread, fc_spread = (c_bl_hi - c_bl_lo).days, (c_fc_hi - c_fc_lo).days
        c1 += (f" The concurrency test that matters is at the back end. In the baseline, "
               f"{_names([_nm(m['name'], 48) for m in cluster[:5]])} fell between {_fmt(c_bl_lo)} and {_fmt(c_bl_hi)}. "
               + ("The forecast squeezes them closer" if fc_spread < bl_spread - 3 else "The forecast still lands them together")
               + f", between {_fmt(c_fc_lo)} and {_fmt(c_fc_hi)}.")
        if squeeze:
            a, b, blg, fcg = squeeze
            c1 += (f" {_nm(a['name'], 48)} and {_nm(b['name'], 48)} were {blg} days apart in the baseline "
                   f"({a['baseline_finish']} and {b['baseline_finish']}) and now fall {fcg} day{'s' if fcg != 1 else ''} "
                   f"apart ({a['finish']} and {b['finish']}).")
        c1 += (" So the crews and subcontractors behind those completions are all needed at full strength in the same "
               "weeks. Any recovery that compresses the finish chain pushes more work into that window.")
    c2 = ("Adding fronts is only feasible if the plant, the formwork and the crews exist — a second rig or formwork set on "
          "the chain, for example. Whether the back-end peak can be staffed is a histogram question this read can't "
          "answer (see below). Model each extra front in the What-if before committing to it.")
    s4 = K.sec('Concurrent work-fronts — feasible?', c1, c2)

    # ── 5. revisions ────────────────────────────────────────────────────────────
    labels = _names([f for f, _ in sorted(fronts, key=lambda fx: -len(fx[1]))[:2]]) if fronts else ''
    s5 = K.sec('Did resourcing change between revisions?',
               "This is a single update, so it can't show what changed from the previous revision."
               + (" It does hint at one thing: the even slip down the finish chain means those durations still match the "
                  "baseline. In this update the chain was moved, not re-sized." if uniform else '')
               + " To see whether crew hours or durations "
               + (f"on the finish chain ({labels}) " if labels else '')
               + "were cut, stretched or re-spread between revisions, send the previous revision with this one to Baseline "
               "Revision Comparison. One trap to avoid: the comparison must sum Labour resources only. If material or "
               "value lines get into the sum, the 'man-hours' figure means nothing.")

    # ── 6. can and can't show ───────────────────────────────────────────────────
    where = _names([f for f, _ in fronts[:4]]) if fronts else ''
    s6 = K.sec("What this update can and can't show",
               "**Your manpower can't be judged from this read. First, the chat's read of your file carries dates, float "
               "and progress, not the resource assignments, so I can't see labour hours or crew sizes."
               + (" Second, the chain that sets the date hasn't started, so there is no actual output to measure "
                  "productivity against." if all_zero else '') + "**",
               (f"What it can show is where the crews must land: {where}, in that order. It also shows "
                if where else "What it can show is ")
               + f"how far off the pace is (SPI {K.ratio(spi)}, {K.pct(A_)} done against {K.pct(P)} planned). "
               "What it can't give is a trustworthy weekly headcount. Peak, ramp and demobilisation come from labour hours "
               "spread over time, and those come from the resource assignments — Productivity & Resource Intelligence "
               "reads them from the file.")

    # ── 7. peak, ramp, histogram ────────────────────────────────────────────────
    win = _months(c_bl_lo or c_fc_lo, c_fc_hi) if cluster else ''
    rows7 = [['Peak labour and its week', 'labour hours on every activity, spread over the resource calendar',
              "not in this read: the resource assignments aren't carried into the chat's facts"],
             ['Spike vs plateau at the back end', f"the weekly curve through {win}" if win else 'the weekly curve to completion',
              (f"dates only: {len(cluster)} completions land between {_fmt(c_fc_lo)} and {_fmt(c_fc_hi)}" if cluster else
               'dates only: no cluster of completions near the finish')],
             ['Ramp onto the finish-chain front', 'how fast the first crews mobilise on it',
              ('not measurable: the chain is 0% started' if all_zero else
               f"{started} of {len(chain)} chain activities started") if chain else 'needs the file re-read'],
             ['Actual productivity', 'actual units against earned progress on work that has started',
              'none on the chain, because nothing on it has started' if all_zero else
              'progress % only; no quantities or units in this read']]
    s7 = K.sec('Peak, ramp and histogram realism',
               "I can't quote a peak or judge the histogram's shape from this read, and I won't guess one. This is what "
               "each check needs, and what this file gives:",
               table=K.tbl(['Check', 'What it needs', 'What this file gives'], rows7,
                           "Every entry is read from this file. Once the activities carry trade hours, Productivity & "
                           "Resource Intelligence can draw the labour-only histogram and test the peak against what each "
                           "subcontractor can field."))

    # ── 8. resource-loaded? ─────────────────────────────────────────────────────
    B = implied_bac(F)
    r1 = ("This read can't tell you, and I won't guess. The chat's facts carry the budget"
          + (f" (≈ {_m(B['bac'], approx=True)} on {_names(B['costed'])})" if B else '')
          + " and progress, not the resource assignments, so which activities carry labour, plant or material — and how "
          "many man-hours by discipline — needs Productivity & Resource Intelligence on this file."
          + (" One clue from the numbers: actual cost equals earned value to the unit, so whatever is loaded, its actuals "
             "are generated from progress rather than booked hours." if derived else '')
          + (" What the plan does say is where the crews have to be. Here is the chain that sets the date, front by front:"
             if fronts else ''))
    t8 = None
    if fronts:
        rows8 = []
        for f, xs in fronts[:10]:
            ft = [x['tf'] for x in xs if x.get('tf') is not None]
            st = sum(1 for x in xs if (x.get('pct') or 0) > 0)
            names = []
            for x in xs:
                nmx = _nm(x['name'], 40)
                if nmx not in names:
                    names.append(nmx)
            rows8.append([f, len(xs), (_i(min(ft)) if min(ft) == max(ft) else f"{_i(max(ft))} to {_i(min(ft))}") if ft else '—',
                          'none started' if st == 0 else f"{st} of {len(xs)} started",
                          '; '.join(names[:2]) + (f" (+{len(names) - 2} more)" if len(names) > 2 else '')])
        dp = deepest[:2]
        t8 = K.tbl(['Front on the finish chain (WBS)', 'Activities', 'Float (wd)', 'Progress', 'Includes'], rows8,
                   "Fronts, float and progress come from the file."
                   + (f" The most-negative activities in the schedule are " + ' and '.join(
                       f"{_nm(x['name'], 60)} ({x['id']}, {_i(x['tf'])})" for x in dp)
                      + (", both 0% started" if len(dp) == 2 and all(not x.get('pct') for x in dp) else '') + '.' if dp else '')
                   + " Resource names per activity come from Productivity & Resource Intelligence.")
    s8 = K.sec('Is it resource-loaded? Man-hours by discipline', r1, table=t8)

    # ── 9. durations vs quantities ──────────────────────────────────────────────
    over, hpct, thr = hd.get('over_threshold'), hd.get('high_pct'), hd.get('threshold')
    firsts = []
    if uniform and med is not None:
        firsts.append(f"the finish chain keeps its baseline durations after a ~{abs(med)} wd late start, so the forecast "
                      "still assumes baseline production rates on work "
                      + ("nobody has started." if all_zero else "that is barely under way."))
    if over is not None and thr is not None:
        firsts.append(f"durations aren't obviously lumped into long placeholders: only {over} activities ({K.pct(hpct, 1)}) "
                      f"run longer than {thr} working days." if (_n(hpct) or 0) < 5 else
                      f"{over} activities ({K.pct(hpct, 1)}) run longer than {thr} working days — long placeholders hide "
                      "the production rate, so break them down before judging productivity.")
    shows = (" It does show two things. First, " + firsts[0] + " Second, " + firsts[1]) if len(firsts) == 2 else \
        ((" It does show one thing: " + firsts[0]) if firsts else '')
    s9 = K.sec('Durations vs quantities — is the productivity credible',
               "This read can't tell you. It carries no quantities, so durations can't be checked against a productivity "
               "norm here." + shows
               + " To test credibility, run Duration & Resource Calculation with the Productivity KB on the "
               + ("finish-chain quantities." if chain else "remaining quantities.")
               + (f" If the norms imply longer durations than the plan, the {_i(ftf)} wd grows and no crew size will hit "
                  "the date." if (ftf is not None and ftf < 0) else
                  " If the norms imply longer durations than the plan, the float you have now will shrink."))

    # ── 10. the one thing ───────────────────────────────────────────────────────
    if behind and chain:
        o = (("The work that sets your finish hasn't started. " if all_zero else
              f"The work that sets your finish is only {started} of {len(chain)} activities under way. ")
             + f"You're earning at {F.get('pace_pct') or round((spi or 0) * 100)}% of planned pace"
             + (f", and {drv['name']} stands at {drv.get('actual')}% against {drv.get('planned')}%" if drv else '')
             + ", but that average isn't what sets the date. The date is set by the "
             + f"{n_chain}-activity chain" + (" at 0%" if all_zero else '') + '.'
             + (f" Its first activity was due to finish on {head['baseline_finish']}." if overdue else '')
             + " The cause could be a missing crew or plant (contractor) or access and inputs the schedule doesn't model "
             "(employer). The site records will show which; the file can't. Answer that question first, before buying "
             "crews and before claiming time.")
    elif behind:
        o = (f"You're {_pos(d)} and earning at SPI {K.ratio(spi)}"
             + (f", carried by {drv['name']}" if drv else '')
             + ". Whether that is crews or logic needs the finish chain from the file — re-import it, then ask again.")
    else:
        o = (f"Nothing in this update points to a resource-driven delay: you're {_pos(d) if d is not None else 'on plan'} "
             f"with SPI {K.ratio(spi)}. The manpower question for you is whether the remaining plan can be staffed at its "
             "peak — a resource-loading question for Productivity & Resource Intelligence.")
    s10 = K.sec('The one thing this update does say', o)

    # ── measured / actions / evidence ───────────────────────────────────────────
    measured = ((f"The finish chain is the set of unfinished activities within {N.get('chain_band')} wd of the finish "
                 f"milestone's total float ({_i(ftf)} wd), read in finish order from the file. Slip is the number of "
                 "working days between each activity's baseline finish and its current finish, counted in the activity's "
                 "own calendar. " if chain else '')
                + "Out-of-sequence, negative-float, critical-density and long-duration counts come from the Schedule Audit "
                "modules on this file. "
                + (f"Value shares are PV and EV per '{dim}' code at the {dd} data date. " if top else
                   "The discipline shortfall share is weight × (planned % − actual %). ")
                + ("Client inputs are activities the file's WBS or names mark as employer, client or consultant items. "
                   if nok else '')
                + "Resource assignments (labour, equipment, material) are not part of this read, so no histogram, peak or "
                "man-hour figure is quoted; Productivity & Resource Intelligence reads them from the file, labour only.")
    rep_act = (f"Where the chain ties one area's work to the next ({rep[0]} in {_names(rep[1][:2])}), check whether the tie "
               "is crew, rig or formwork movement; if it is, price a second crew or set and test it in the What-if before "
               "committing.") if rep else "Test any extra crew or plant on the finish chain in the What-if before committing."
    actions = [
        (f"This week, get the site's written answer to one question: why hasn't {_nm(head['name'])} ({head['id']}, due "
         f"{head['baseline_finish']}) started? Was it the crew and plant, or access and inputs? The answer decides whose "
         "delay this is.") if (behind and overdue and not head.get('pct')) else
        ((f"Get the site's view on what is holding {_nm(head['name'])} ({head['id']}) at the head of the finish chain — "
          "crews, plant, access or inputs.") if (behind and head) else ''),
        rep_act if behind else '',
        (f"Chase the client inputs in parallel: " + '; '.join(f"{_nm(x['name'], 48)} ({_i(x['tf'])})" for x in neg_ci[:4])
         + (f". Recovering only the finish chain still leaves those paths late, the {_nm(worst_ci['name'], 48)} path by "
            f"{abs(worst_ci['tf'])} wd." if (worst_ci and ftf is not None and worst_ci['tf'] > ftf) else '.'))
        if neg_ci else '',
        "Load trade labour on the finish-chain activities before anyone quotes a histogram, and keep material lines out of "
        "any man-hour sum." if chain else "Load trade labour on the activities before anyone quotes a histogram.",
        ("Then run Productivity & Resource Intelligence on labour only, and test the "
         + (f"{win} back-end peak ({len(cluster)} completions together) " if win else 'back-end peak ')
         + "against what each subcontractor can actually field."),
        "Send the previous revision to Baseline Revision Comparison to see whether finish-chain durations or crew hours "
        "changed.",
        "Test the finish-chain durations against quantities in Duration & Resource Calculation before the recovery plan "
        "relies on baseline production rates." if chain else
        "Test the remaining durations against quantities in Duration & Resource Calculation.",
    ]
    evidence = [K.ev('Finish-chain head', f"{head['id']} {_nm(head['name'], 40)} · TF {_i(head.get('tf'))} · {head.get('pct', 0)}%")
                if head else None,
                K.ev('Its baseline finish', f"{head['baseline_finish']} (data date {dd})") if (head and head.get('baseline_finish')) else None,
                K.ev('Deepest float', ' · '.join(f"{x['id']} {_i(x['tf'])}" for x in deepest[:2])
                     + (' · both 0%' if len(deepest) >= 2 and all(not x.get('pct') for x in deepest[:2]) else ''))
                if deepest else None,
                K.ev('Chain slip', (f"{_i(near[0])} to {_i(near[-1])} wd on {len(near)} of {len(slips)} links, near-uniform"
                                    if uniform else f"{_i(slips[0])} to {_i(slips[-1])} wd, uneven"))
                if slips else None,
                K.ev('SPI', f"{K.ratio(spi)} ({K.pct(A_)} vs {K.pct(P)})"),
                K.ev(drv['name'], f"{drv.get('actual')}% vs {drv.get('planned')}% · "
                                  f"{round((_n(drv.get('weight')) or 0) * 100)}% weight") if drv else None,
                K.ev(top['code'], f"{round(_n(top.get('pct_of_gap')) or 0, 2)}% of value gap"
                     + (f" · {(_n(top.get('pv')) or 0) / tot_pv * 100:.1f}% of PV" if tot_pv else '')) if top else None,
                K.ev('Out-of-sequence', f"{oos} ({K.pct(oos_pct, 1)})"
                     + (f" · {crit_oos} critical" if crit_oos is not None else '')
                     + (f" · {mpk.group(2)} in {mpk.group(1)}" if mpk else '')) if oos is not None else None,
                K.ev('Negative float', f"{neg} ({K.pct(neg_pct, 1)})") if neg is not None else None,
                K.ev('Critical density', f"{crit} at critical float" + (f" · {F.get('cpli_density_grade')}"
                                                                       if F.get('cpli_density_grade') else ''))
                if crit is not None else None,
                K.ev('Resource loading', 'not in this read — Productivity & Resource Intelligence'),
                K.ev('Client-input paths', f"{_i(deep_ci[-1]['tf'])} to {_i(deep_ci[0]['tf'])} wd float")
                if len(deep_ci) >= 2 else None]
    a = K.A2(verdict, [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10], pills=pills, measured=measured, actions=actions,
             evidence=evidence,
             drilldowns=[K.drill('q05', f"How do I recover the ~{round(d)} days?") if behind else None,
                         K.drill('q04', 'What exactly is driving the date, and how much float is left?'),
                         K.drill('q13', 'Do the late client inputs give me an EOT case?') if neg_ci else None,
                         K.drill('q08', 'Cost & EVM — where do we stand on money?') if not behind else None],
             tools=[K.tool('whatif', 'Run the what-if')] if behind else [])
    a['thinking'] = thinking[:4]
    return a
