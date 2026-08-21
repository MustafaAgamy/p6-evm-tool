"""Execution dashboard, recommendation and narrative for the Critical Path Analyzer.

Reads the already-assembled report pieces (census, lanes, milestones, float migration)
and derives: the Critical Path Health verdict + gauge, the KPI row, three chart series,
and the plain-language effect / recommendation / conclusion text.
"""

_WORST = {'good': 0, 'warn': 1, 'bad': 2}
_STATUS_LABEL = {'good': 'On track', 'warn': 'At risk', 'bad': 'Critical'}


def _cpli_band(v):
    if v is None:
        return 'warn'
    return 'good' if v >= 1.0 else ('warn' if v >= 0.95 else 'bad')


def _worst(*statuses):
    return max(statuses, key=lambda s: _WORST.get(s, 0))


def _gov_row(report):
    for m in report.get('milestones', []):
        if m.get('is_governing'):
            return m
    ms = report.get('milestones', [])
    return ms[0] if ms else None


def _reroute_targets(report):
    """Names of the work fronts newly on the current critical path (the reroute)."""
    for lane in report.get('lanes', []):
        if lane.get('role') == 'current':
            return [b.get('name') for b in lane.get('boxes', []) if b.get('state') == 'new']
    return []


def build_dashboard(report):
    cur = (report.get('census') or {}).get('current') or {}
    base_role = 'previous' if 'previous' in report.get('roles', []) else (
        'baseline' if 'baseline' in report.get('roles', []) else None)
    base = (report.get('census') or {}).get(base_role) or {}
    roles = report.get('roles', [])
    mig = (report.get('float_migration') or {}).get('counts') or {}
    reroute = _reroute_targets(report)

    cpli = cur.get('cpli')
    health = _worst(_cpli_band(cpli),
                    'warn' if reroute else 'good',
                    'bad' if (mig.get('near_to_crit') or 0) else 'good')

    def dlt(key):
        a, b = cur.get(key), base.get(key)
        return None if (a is None or b is None) else round(a - b, 2)

    kpis = [
        {'key': 'cpli', 'label': 'CPLI · project finish', 'value': cpli, 'delta': dlt('cpli'),
         'band': _cpli_band(cpli), 'higher_is_bad': False},
        {'key': 'length', 'label': 'Critical path length (wd)', 'value': cur.get('path_length_wd'),
         'delta': dlt('path_length_wd'), 'higher_is_bad': True},
        {'key': 'critical', 'label': 'Critical activities', 'value': cur.get('critical'),
         'delta': dlt('critical'), 'higher_is_bad': True},
        {'key': 'near', 'label': 'Near-critical', 'value': cur.get('near'),
         'delta': dlt('near'), 'higher_is_bad': True},
    ]

    charts = {
        'crit_near': {'roles': roles,
                      'critical': [(report['census'].get(r) or {}).get('critical') for r in roles],
                      'near': [(report['census'].get(r) or {}).get('near') for r in roles]},
        'cpli_trend': {'roles': roles,
                       'values': [(report['census'].get(r) or {}).get('cpli') for r in roles]},
        'ms_variance': sorted(
            [{'name': m['name'], 'var': m.get('var_vs_baseline_d')}
             for m in report.get('milestones', []) if m.get('var_vs_baseline_d') is not None],
            key=lambda x: -abs(x['var']))[:8],
    }

    gov = _gov_row(report)
    verdict = _verdict_text(health, cur, gov, reroute)
    factors = _health_factors(cpli, reroute, mig)

    return {'status': health, 'status_label': _STATUS_LABEL[health], 'verdict': verdict,
            'cpli': cpli, 'factors': factors, 'kpis': kpis, 'charts': charts,
            'reroute': reroute}


def _verdict_text(health, cur, gov, reroute):
    fin = (gov or {}).get('finishes', {}).get('current') or cur.get('gov_finish') or 'the forecast finish'
    slip = (gov or {}).get('var_vs_baseline_d')
    lead = {'bad': 'Critical', 'warn': 'At risk', 'good': 'On track'}[health]
    if slip is not None and slip > 0:
        return f"{lead} — the critical path finishes {fin}, {slip} working days behind baseline."
    if slip is not None and slip < 0:
        return f"{lead} — the critical path finishes {fin}, {abs(slip)} working days ahead of baseline."
    return f"{lead} — the critical path finishes {fin}."


def _health_factors(cpli, reroute, mig):
    out = []
    if cpli is not None:
        if cpli < 0.95:
            out.append(f"CPLI {cpli:.2f} — needs ~{round((1 - cpli) * 100)}% compression")
        elif cpli < 1.0:
            out.append(f"CPLI {cpli:.2f} — no float left")
        else:
            out.append(f"CPLI {cpli:.2f} — on or ahead of the finish")
    if reroute:
        out.append(f"Rerouted into {', '.join(reroute[:2])}" + ('…' if len(reroute) > 2 else ''))
    if mig.get('near_to_crit'):
        out.append(f"{mig['near_to_crit']} activities turned critical this period")
    return out


def build_narrative(report):
    """Plain-language effect, recommendation list and one-line conclusion."""
    cur = (report.get('census') or {}).get('current') or {}
    gov = _gov_row(report)
    mig = (report.get('float_migration') or {}).get('counts') or {}
    reroute = _reroute_targets(report)
    cpli = cur.get('cpli')
    fin = (gov or {}).get('finishes', {}).get('current') or cur.get('gov_finish')
    slip_bl = (gov or {}).get('var_vs_baseline_d')
    slip_pd = (gov or {}).get('var_this_period_d')

    # Effect on completion
    eff = []
    if fin:
        eff.append(f"The critical path now finishes at {(gov or {}).get('name') or 'the completion milestone'} on {fin}")
    if slip_bl is not None:
        eff.append(f"{abs(slip_bl)} working days {'behind' if slip_bl > 0 else 'ahead of'} baseline"
                   + (f", {slip_pd} of them this period" if slip_pd else ""))
    if reroute:
        eff.append(f"the driving work rerouted into {', '.join(reroute[:2])}")
    if cpli is not None and cpli < 1.0:
        eff.append(f"with a CPLI of {cpli:.2f}, the remaining path needs ~{round((1 - cpli) * 100)}% compression to hold")
    effect = '; '.join(eff) + '.' if eff else 'No governing critical path was found to report on.'

    # Recommendation
    rec = []
    if reroute:
        rec.append(f"Shift recovery focus to {', '.join(reroute[:2])} — the critical path left its old route and now runs through this work; compress it to claw back the slip.")
    if mig.get('near_to_crit'):
        rec.append(f"Protect the {mig['near_to_crit']} activities that just turned critical — any slip on them now pushes the finish day-for-day.")
    if mig.get('safe_to_near'):
        rec.append(f"Watch the {mig['safe_to_near']} activities eroding toward the path — they are the next reroute if recovery stalls.")
    if cpli is not None and cpli < 1.0:
        rec.append(f"CPLI {cpli:.2f} needs ~{round((1 - cpli) * 100)}% compression on the remaining path — target the driving sequence, not work that already has float.")
    if not rec:
        rec.append("The critical path is holding — keep protecting the driving activities and re-check next update.")

    # Conclusion
    if cpli is not None and cpli < 0.95:
        concl = f"Critical path at risk — {round((1 - cpli) * 100)}% recovery needed to hold the forecast."
    elif slip_bl and slip_bl > 0:
        concl = f"Critical path {slip_bl} working days behind baseline; recovery should target the current driving work."
    else:
        concl = "Critical path is on or ahead of plan this update."

    return {'effect': effect, 'recommendation': rec, 'conclusion': concl}
