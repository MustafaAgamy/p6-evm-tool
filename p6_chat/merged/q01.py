"""q01 — Where do we stand: are we ahead or behind, over or under budget?

Covers: status (SPI / delay / progress), cost read, trend, worst discipline by how much (weighted),
the chain that sets the finish, and what the file points to as the reason — for ANY project.
"""
from . import _kit2 as K


def _fronts(chain):
    """Collapse a finish chain into its work fronts in order: [(front, count)]."""
    out = []
    for x in chain:
        parts = [p for p in (x.get('wbs') or '').split(' / ') if p]
        front = ' / '.join(parts[-2:]) if parts else '(no WBS)'
        if out and out[-1][0] == front:
            out[-1] = (front, out[-1][1] + 1)
        else:
            out.append((front, 1))
    return out


def build(F, N, role):
    d = F.get('delay_days')
    spi = F.get('spi')
    behind, ahead = (d or 0) > 0, (d or 0) < 0
    drv = K.main_driver(F)
    nok = bool(N and N.get('ok'))
    fin = (N or {}).get('finish_milestone') or {}
    thinking = []

    # ── verdict ─────────────────────────────────────────────────────────────────
    if d is None:
        head = f"Progress is at SPI {K.ratio(spi)} ({K.pct(F.get('actual_pct'))} done vs {K.pct(F.get('planned_pct'))} planned); the finish slip can't be read from this file."
    elif behind:
        head = (f"Behind: about {K.wd(d)} late (SPI {K.ratio(spi)}, {K.pct(F.get('actual_pct'))} done vs "
                f"{K.pct(F.get('planned_pct'))} planned)" + (f", carried by {drv['name']}" if drv else '') + '.')
    elif ahead:
        head = f"Ahead: about {K.wd(d)} of float to completion (SPI {K.ratio(spi)})."
    else:
        head = f"On the planned finish date (SPI {K.ratio(spi)})."
    if F.get('cost_derived'):
        head += f" The CPI of {K.ratio(F.get('cpi'))} is not a budget signal."
    pills = [K.pill(f"SPI {K.ratio(spi)} · {K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}",
                    'danger' if (spi or 1) < 0.9 else ('warning' if (spi or 1) < 1 else 'success')),
             K.pill(K.signed(d) + (f" · finish {F.get('forecast_finish')}" if F.get('forecast_finish') else ''),
                    'danger' if behind else 'success') if d is not None else None,
             K.pill(f"CPI {K.ratio(F.get('cpi'))} · cost derived from progress", 'neutral') if F.get('cost_derived')
             else K.pill(f"CPI {K.ratio(F.get('cpi'))}", 'warning' if (F.get('cpi') or 1) < 0.98 else 'success')]

    # ── time and cost ───────────────────────────────────────────────────────────
    s_time = K.sec('Time and cost',
                   (f"You're {'behind' if behind else 'ahead' if ahead else 'on the date'}. At the {F.get('data_date')} "
                    f"data date you've earned {K.pct(F.get('actual_pct'))} of the work against {K.pct(F.get('planned_pct'))} "
                    f"planned — SPI {K.ratio(spi)}. In dates, the finish is {K.delay_phrase(F)}.")
                   if d is not None else
                   f"At the {F.get('data_date')} data date you've earned {K.pct(F.get('actual_pct'))} against {K.pct(F.get('planned_pct'))} planned (SPI {K.ratio(spi)}).",
                   K.cost_note(F),
                   (f"In value terms, {K.money(abs(F['pv'] - F['ev']))} of planned value "
                    f"{'is not yet earned' if F['pv'] > F['ev'] else 'has been earned ahead of plan'} "
                    f"(PV {K.money(F['pv'])} vs EV {K.money(F['ev'])}, in the project's own currency units).")
                   if F.get('pv') and F.get('ev') else '')

    # ── trend ───────────────────────────────────────────────────────────────────
    tr = F.get('trend')
    if tr and tr.get('prev_delay') is not None:
        delta = tr.get('delta') or 0
        trend_paras = [f"Since the previous update the delay moved from {K.signed(tr['prev_delay'])} to {K.signed(d)} — "
                       + (f"a further {K.wd(delta)} lost." if delta > 0 else (f"{K.wd(delta)} recovered." if delta < 0 else "no change."))]
    else:
        trend_paras = ["This update has no earlier, comparable update stored with it, so I can't tell you whether the "
                       "last period gained or lost ground — and I won't invent a trend."]
    if nok:
        ms = [m for m in N.get('milestones') or [] if not m['done'] and m.get('slip_wd') is not None][:10]
        if len(ms) >= 3:
            trend_paras.append("What the file does show is where the slip sits across the scope today — the sectional "
                               "milestones, in baseline order, and how far each has moved:")
            t_trend = K.tbl(['Milestone', 'Baseline', 'Forecast', 'Slip (wd)'],
                            [[m['name'], m['baseline_finish'], m['finish'], f"{m['slip_wd']:+d}"] for m in ms])
        else:
            t_trend = None
    else:
        t_trend = None
    trend_paras.append("For a real period trend, load last update's file and run Update vs Update — it names the "
                       "activities that lost float this period.")
    s_trend = K.sec('Trend since last update', *trend_paras, table=t_trend)
    thinking.append('Checked the stored update history for a comparable earlier update')

    # ── worst discipline ────────────────────────────────────────────────────────
    ds = sorted(F.get('disciplines') or [], key=lambda x: -(x.get('weight') or 0))
    widest = max(ds, key=lambda x: x.get('gap') or 0) if ds else None
    disc_paras = []
    if drv and widest and widest['name'] != drv['name'] and (widest.get('gap') or 0) > 0:
        disc_paras.append(f"**{widest['name']}** is worst by raw gap ({widest['gap']} points), but **{drv['name']}** is "
                          f"worst by effect on the finish because it carries {round((drv.get('weight') or 0) * 100)}% of the "
                          "weight — a small-weight line barely moves the total.")
    elif drv:
        disc_paras.append(f"**{drv['name']}** is the worst, and it matters most: {round((drv.get('weight') or 0) * 100)}% "
                          f"of the weight, {drv['actual']}% done vs {drv['planned']}% planned.")
    else:
        disc_paras.append("No discipline is behind its planned progress on the weighted read.")
    vg = F.get('value_gap') or {}
    groups = [g for g in (vg.get('groups') or []) if (g.get('gap') or 0) > 0]
    if groups:
        top = groups[0]
        disc_paras.append(f"By {vg.get('dimension', 'activity code')}, **{top['code']}** holds "
                          f"{round(top.get('pct_of_gap') or 0, 1)}% of the value gap ({K.money(top['gap'])} of "
                          f"{K.money(vg.get('total_gap'))}).")
    s_disc = K.sec('Which discipline is worst — and by how much', *disc_paras,
                   table=K.tbl(['Discipline', 'Weight', 'Done / planned', 'Gap (pts)'],
                               [[x['name'] + (' (driver)' if drv and x['name'] == drv['name'] else ''),
                                 f"{round((x.get('weight') or 0) * 100)}%", f"{x['actual']}% / {x['planned']}%", x.get('gap')]
                                for x in ds]))
    thinking.append("Weighed each discipline's gap by its share of the job")

    # ── driving path ────────────────────────────────────────────────────────────
    if nok and N.get('chain'):
        chain = N['chain']
        fronts = _fronts(chain)
        not_started = sum(1 for x in chain if x['pct'] == 0)
        head_act = chain[0]
        dp = [f"The finish ({fin.get('name', 'the finish milestone')}, {fin.get('finish')}) is set by a chain of "
              f"{N['chain_count']} activities within {N['chain_band']} wd of its float ({N['finish_tf']:+d} wd)"
              + (f", {not_started} of them not started." if not_started else '.'),
              'In order, it runs through: ' + '; '.join(f"{f} ({n})" for f, n in fronts[:8]) + '.']
        if head_act.get('baseline_finish'):
            dp.append(f"The head of the chain, **{head_act['name']}** ({head_act['id']}), was due {head_act['baseline_finish']} "
                      f"and is now forecast {head_act['finish']} (float {head_act['tf']:+d} wd, {head_act['pct']}% done).")
        deep = N.get('deepest') or []
        if deep:
            dp.append('The tightest points in the network: ' + '; '.join(
                f"{x['name']} ({x['id']}, {x['tf']:+d} wd, {x['pct']}%)" for x in deep[:2]) + '.')
        dp.append("Recovery has to land on this chain — work off it doesn't move the finish.")
        s_path = K.sec("What's setting the date (driving path)", *dp)
        thinking.append(f"Traced the {N['chain_count']}-activity chain that sets the finish")
    else:
        s_path = K.sec("What's setting the date (driving path)", K.network_note(N),
                       f"From the stored float check: {F.get('neg_float_count') or 0} activities are on negative float "
                       f"({K.pct(F.get('neg_float_pct'))}); critical density is graded {F.get('cpli_density_grade') or 'n/a'}.")

    # ── why (indicative) ────────────────────────────────────────────────────────
    why = []
    if nok:
        late_open = N.get('client_inputs_late_open') or []
        late_done = N.get('client_inputs_late_done') or []
        if late_open or late_done:
            why.append('Two contributors are visible — neither is proven from one snapshot.')
            if late_open:
                why.append(f"First, late employer/client inputs: {len(late_open)} still open and late — " + '; '.join(
                    f"{x['name']} ({x['id']}) {x['slip_wd']:+d} wd" + (f", float {x['tf']:+d}" if x.get('tf') is not None else '')
                    for x in late_open[:7]) + '.' + (f" Another {len(late_done)} were delivered late ({min(x['slip_wd'] for x in late_done):+d} to "
                                                     f"{max(x['slip_wd'] for x in late_done):+d} wd)." if late_done else '')
                           + " Employer-side items on negative-float paths are strong EOT indicators.")
            why.append("Second, the execution of the chain that sets the finish itself — this file can't separate the two, "
                       "and it isn't resource-loaded, so it can't show whether crews or productivity are short.")
            thinking.append(f"Checked {len(N.get('client_inputs') or [])} client/employer input activities against their dates")
        else:
            why.append("No late employer/client input activities are flagged in the file's WBS, so the slip reads as "
                       "execution on the driving chain — still to be confirmed.")
    why.append("Splitting the delay between employer and contractor needs a time-impact / windows analysis (Consultant "
               "Review, Update vs Update) — report potential delay events with notices, not an entitlement.")
    s_why = K.sec("Why it's late — what the file points to (indicative, not proven)", *why) if behind else None

    measured = (f"SPI = EV ÷ PV at the {F.get('data_date')} data date ({K.money(F.get('ev'))} ÷ {K.money(F.get('pv'))}); "
                "progress is category-weighted. The delay is the finish milestone's forecast against its baseline in "
                "working days, matching its total float in P6. "
                + ("CPI = EV ÷ AC, and AC equals EV in this file, so CPI is 1.00 by construction. " if F.get('cost_derived') else '')
                + ("The driving chain, milestones and client inputs are re-read from the P6 file you sent." if nok else ''))
    fin_pair = (f"finish {F['forecast_finish']} vs {F['baseline_finish']}, "
                if F.get('forecast_finish') and F.get('baseline_finish') else '')
    actions = [f"Report the position as {K.signed(d)} ({fin_pair}SPI {K.ratio(spi)})"
               + (" and show cost as 'not measured' until real actuals are loaded." if F.get('cost_derived') else '.') if d is not None else '',
               (f"Aim recovery at the chain that sets the finish — start with {N['chain'][0]['name']} ({N['chain'][0]['id']})."
                if nok and N.get('chain') and behind else ''),
               (f"Chase the late client inputs, starting with {N['client_inputs_late_open'][0]['name']}, and put notices on record."
                if nok and N.get('client_inputs_late_open') else ''),
               'Load the previous update and run Update vs Update to get the real period trend.']
    ev = [K.ev('SPI', K.ratio(spi)), K.ev('Delay', K.signed(d)),
          K.ev('Progress', f"{K.pct(F.get('actual_pct'))} vs {K.pct(F.get('planned_pct'))}"),
          K.ev('Driver', drv['name'] if drv else None),
          K.ev('Finish chain', f"{N['chain_count']} activities" if nok else None)]
    a = K.A2(head, [s_time, s_trend, s_disc, s_path, s_why], pills=pills, measured=measured, actions=actions,
             evidence=ev,
             drilldowns=[K.drill('q02', 'When will we finish, and will we hit the dates?'),
                         K.drill('q05', 'How do I recover the delay?') if behind else K.drill('q04', "How much float is left?"),
                         K.drill('q03', 'Is the delay real, and why?') if behind else None],
             tools=[K.tool('dashboard', 'Build the dashboard')])
    a['thinking'] = thinking
    return a
