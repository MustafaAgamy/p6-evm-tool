"""Round-3 reading aids of the Update-vs-Update report (owner comments 68–73, round 3).

Four additive blocks, each worked out from the two files only — nothing is scheduled and
nothing in `p6_evm` changes:

`logic_changes`  — for the critical activities whose driver is 'logic changed': WHAT changed
                   in their relationships (link added / removed, type changed, lag changed).
`ev_by_code`     — Earned Value before / after / variance by every activity-code value (and by
                   WBS), so a pick of specific values still adds up to the report's totals.
`rate_outlook`   — the rate of progress between the two data dates carried forward: where it
                   lands, the time lost this period, the rate the baseline finish needs.
`advice`         — the conclusion as actions with numbers and dates, for Top Management and
                   for the Project Manager.
"""
from datetime import datetime, timedelta

from p6_period.movement import _deep_wbs, _MILESTONES
from p6_period.progress import _fmt

NO_VALUE = '(no value)'


# ── relationships changed ───────────────────────────────────────────────────

def _lag(d):
    d = d or 0.0
    return f'{d:g} d'


def _side_changes(base, upd, word):
    """One line per changed link of one side (predecessors or successors)."""
    out = []
    removed = [e for e in base if e.get('status') == 'removed']
    used = set()
    for e in upd:
        st = e.get('status')
        who = f'{word} {e.get("code")}' + (f' ({e.get("name")})' if e.get('name') else '')
        if st == 'added':
            out.append(f'{who} — {e.get("type")} relationship added (lag {_lag(e.get("lag_days"))})')
        elif st == 'changed' and e.get('change_kind') == 'lag':
            old = next((b for b in base if b.get('code') == e.get('code') and b.get('type') == e.get('type')), None)
            out.append(f'{who} — {e.get("type")} lag {_lag(old.get("lag_days")) if old else "?"} → {_lag(e.get("lag_days"))}')
        elif st == 'changed':
            old = next((b for i, b in enumerate(removed)
                        if b.get('code') == e.get('code') and i not in used), None)
            if old is not None:
                used.add(removed.index(old))
            out.append(f'{who} — relationship type {old.get("type") if old else "?"} → {e.get("type")}'
                       + (f', lag {_lag(old.get("lag_days"))} → {_lag(e.get("lag_days"))}'
                          if old and abs((old.get('lag_days') or 0.0) - (e.get('lag_days') or 0.0)) > 1e-9 else ''))
    for i, b in enumerate(removed):
        if i in used:
            continue
        who = f'{word} {b.get("code")}' + (f' ({b.get("name")})' if b.get('name') else '')
        out.append(f'{who} — {b.get("type")} relationship removed')
    return out


def logic_changes(matched, crit):
    """[{activity_id, activity_name, slip_days, prev_finish, curr_finish, wbs, codes, changes}]
    for the critical activities whose finish moved with a change of relationships."""
    rows = [r for r in (crit or {}).get('rows') or [] if r.get('driver') == 'logic changed']
    if not rows:
        return []
    from p6_compare.diff import diff_relationships
    diff = {d['activity_id']: d for d in diff_relationships(matched)['rows']}
    out = []
    for r in rows:
        d = diff.get(r['activity_id']) or {}
        changes = (_side_changes(d.get('baseline_preds') or [], d.get('update_preds') or [], 'Predecessor')
                   + _side_changes(d.get('baseline_succs') or [], d.get('update_succs') or [], 'Successor'))
        out.append({'activity_id': r['activity_id'], 'activity_name': r.get('activity_name', ''),
                    'slip_days': r.get('slip_days'), 'prev_finish': r.get('prev_finish'),
                    'curr_finish': r.get('curr_finish'), 'wbs': r.get('wbs'), 'codes': r.get('codes') or {},
                    'changes': changes})
    return out


# ── Earned Value by activity code ───────────────────────────────────────────

def _cost_records(metrics):
    return [r for r in (metrics or {}).get('records') or []
            if (r.get('bac') or 0) > 0 and r.get('planned_pct') is not None]


def ev_by_code(prev_metrics, curr_metrics, code_types=()):
    """{'WBS' | code type: [{value, activities, bac, ev_prev, ev_now, variance}]} from the
    cost-loaded activities of each update — the same activities and the same sum as the
    report's Earned Value (Performance % × baseline budget). Every value is listed, and the
    activities without that code sit under '(no value)', so each list adds up to the totals."""
    prev = {r['activity'].get('id'): r for r in _cost_records(prev_metrics)}
    curr = {r['activity'].get('id'): r for r in _cost_records(curr_metrics)}
    if not prev or not curr:
        return {}
    out = {}
    for t in ['WBS'] + list(code_types or ()):
        g = {}
        for code in set(prev) | set(curr):
            p, c = prev.get(code), curr.get(code)
            act = (c or p)['activity']
            val = _deep_wbs(act) if t == 'WBS' else ((act.get('activity_codes') or {}).get(t) or NO_VALUE)
            e = g.setdefault(val, {'value': val, 'activities': 0, 'bac': 0.0, 'ev_prev': 0.0, 'ev_now': 0.0})
            e['activities'] += 1
            if c:
                e['bac'] += c['bac']
                e['ev_now'] += c['bac'] * (c.get('actual_pct') or 0.0)
            if p:
                e['ev_prev'] += p['bac'] * (p.get('actual_pct') or 0.0)
        rows = []
        for e in g.values():
            rows.append({'value': e['value'], 'activities': e['activities'], 'bac': round(e['bac'], 2),
                         'ev_prev': round(e['ev_prev'], 2), 'ev_now': round(e['ev_now'], 2),
                         'variance': round(e['ev_now'] - e['ev_prev'], 2)})
        if t != 'WBS' and not any(r['value'] != NO_VALUE for r in rows):
            continue
        rows.sort(key=lambda r: (r['value'] == NO_VALUE, -r['variance'], -r['ev_now'], str(r['value'])))
        out[t] = rows
    return out


# ── rate of progress, carried forward ───────────────────────────────────────

def _parse(label):
    try:
        return datetime.strptime(label, '%d-%b.%Y')
    except Exception:
        return None


def _iso(d):
    return d.strftime('%Y-%m-%d') if d else None


def rate_outlook(prev, curr, summary, recovery):
    """The period's rate of progress and what it means in time. None when the two data dates
    or the earned progress cannot carry a rate.

    Rate = Earned Value variance ÷ calendar days between the two data dates (the % variance
    when the updates carry no cost). Finish at this rate = the recovery outlook's own
    projection, so the two sections never disagree."""
    s, rec = summary or {}, recovery or {}
    dd_prev = (getattr(prev, 'project', {}) or {}).get('data_date')
    dd_now = (getattr(curr, 'project', {}) or {}).get('data_date')
    days = s.get('period_days')
    earned = s.get('period_earned')
    if dd_prev and dd_now:
        dd_prev = datetime(dd_prev.year, dd_prev.month, dd_prev.day)
        dd_now = datetime(dd_now.year, dd_now.month, dd_now.day)
    if not (dd_prev and dd_now and days and days > 0) or earned is None:
        return None
    by_cost = s.get('pct_basis') == 'cost' and s.get('ev_variance') is not None
    base_fin = _parse(rec.get('baseline_finish') or '')
    rate_fin = _parse(rec.get('projected_finish') or '') if earned > 0 else None
    p6_fin = _parse(s.get('forecast_finish_now') or '')
    planned_var = s.get('planned_variance') if by_cost else s.get('period_forecast')
    out = {
        'by_cost': by_cost, 'period_days': days,
        'dd_prev': _iso(dd_prev), 'dd_now': _iso(dd_now),
        'dd_prev_label': _fmt(dd_prev), 'dd_now_label': _fmt(dd_now),
        'actual_prev': s.get('actual_prev'), 'actual_now': s.get('actual_now'),
        'planned_prev': s.get('planned_prev') if by_cost else None,
        'planned_now': s.get('planned_now') if by_cost else s.get('forecast_at_now'),
        'rate_pct': earned, 'planned_pct': planned_var,
        'daily_pct': round(earned / days, 3),
        'baseline_finish': _iso(base_fin), 'baseline_finish_label': rec.get('baseline_finish'),
        'rate_finish': _iso(rate_fin), 'rate_finish_label': _fmt(rate_fin) if rate_fin else None,
        'p6_finish': _iso(p6_fin), 'p6_finish_label': s.get('forecast_finish_now'),
        'remaining_pct': round(100.0 - (s.get('actual_now') or 0.0), 1),
        'required_pct': rec.get('required_rate'),
    }
    if by_cost:
        ev_var, pv_var = s.get('ev_variance') or 0, s.get('pv_variance') or 0
        daily = ev_var / days
        remaining = (s.get('bac') or 0) - (s.get('ev_now') or 0)
        out.update({'rate_money': ev_var, 'planned_money': pv_var, 'daily_money': round(daily),
                    'shortfall_money': round(pv_var - ev_var), 'remaining_money': round(remaining),
                    'gap_money': round((s.get('pv_now') or 0) - (s.get('ev_now') or 0))})
        out['days_lost'] = round((pv_var - ev_var) / daily) if daily > 0 else None
        if base_fin and (base_fin - dd_now).days > 0 and remaining > 0:
            need = remaining / (base_fin - dd_now).days * days
            out['required_money'] = round(need)
            out['required_more_pct'] = round(100.0 * (need / ev_var - 1)) if ev_var > 0 else None
    else:
        short = (planned_var or 0.0) - earned
        out['days_lost'] = round(short / (earned / days)) if earned > 0 else None
        req = rec.get('required_rate')
        out['required_more_pct'] = round(100.0 * (req / earned - 1)) if (req and earned > 0) else None
    if rate_fin:
        out['days_to_go'] = (rate_fin - dd_now).days
        if base_fin:
            out['days_after_baseline'] = (rate_fin - base_fin).days
        if p6_fin:
            out['logic_days'] = (p6_fin - rate_fin).days
    return out


# ── conclusion: actions with numbers and dates ──────────────────────────────

def _m(v):
    """Money in millions with one decimal (916.3 M); whole below one million."""
    if v is None:
        return '—'
    return f'{v / 1e6:,.1f} M' if abs(v) >= 1e6 else f'{v:,.0f}'


def _fronts(rows):
    """(did not move, ahead) among the values of ONE activity code, from their planned and
    earned % of the period."""
    stuck, ahead = [], []
    for r in rows or []:
        pl, ac = r.get('planned') or 0.0, r.get('actual') or 0.0
        if pl >= 0.3 and ac <= 0.25 * pl:
            stuck.append((pl - ac, r))
        elif ac >= 0.3 and ac > pl:
            ahead.append((ac - pl, r))
    stuck.sort(key=lambda x: -x[0])
    ahead.sort(key=lambda x: -x[0])
    return stuck[:3], ahead[:3]


def _front_text(items):
    return ' · '.join(f'{r["value"]}: planned {r.get("planned") or 0:.1f}%, earned {r.get("actual") or 0:.1f}%'
                      for _g, r in items)


def _front_items(code_type, rows):
    stuck, ahead = _fronts(rows)
    out = []
    if stuck:
        out.append({'title': f'Fronts that were planned and did not move (by {code_type})',
                    'text': _front_text(stuck) + '. Each needs a named cause and a restart date before the next update.'})
    if ahead:
        out.append({'title': f'Fronts that are ahead — keep them, do not add to them (by {code_type})',
                    'text': _front_text(ahead) + '. Surplus crews here can move to the critical fronts above.'})
    return out


def default_code_type(by_code):
    """The activity code the progress chart and the conclusion open on: the one that splits
    this period's movement into the most values (ties: the more earned, then the name)."""
    best, key = None, None
    for t, rows in (by_code or {}).items():
        moved = [r for r in rows or [] if (r.get('planned') or 0) > 0 or (r.get('actual') or 0) > 0]
        if not moved:
            continue
        k = (-len(moved), -round(sum(r.get('actual') or 0 for r in moved), 1), t)
        if key is None or k < key:
            best, key = t, k
    return best


def _open_chain(curr, cp):
    """The first activities of the current driving path that are not finished yet."""
    by = {a.get('id'): a for a in getattr(curr, 'activities', {}).values()}
    out = []
    for a in (cp or {}).get('current') or []:
        act = by.get(a.get('id')) or {}
        if (act.get('status') or '').replace(' ', '').lower() == 'completed':
            continue
        out.append(a)
        if len(out) == 2:
            break
    return out


def _due_next(curr, dd_now, days):
    """Activities the current update forecasts to finish before the next update."""
    if not (dd_now and days):
        return None
    end = dd_now + timedelta(days=days)
    n = 0
    for a in getattr(curr, 'activities', {}).values():
        if a.get('task_type') in _MILESTONES or (a.get('percent_complete') or 0.0) >= 1.0:
            continue
        f = a.get('remaining_early_finish') or a.get('planned_finish')
        if f and dd_now < f <= end:
            n += 1
    return n


def advice(curr, summary, recovery, rate, crit_summary, adherence, by_code, cp):
    """{'behind', 'tiles': [{label, value, sub, tone}], 'top_management': [{title, text}],
    'project_manager': [{title, text}], 'rules'} — every figure from the two files."""
    s, rec, r = summary or {}, recovery or {}, rate or {}
    adh, cs = adherence or {}, crit_summary or {}
    cost = bool(r.get('by_cost'))
    days = s.get('period_days')
    slip, dnow, dch = s.get('finish_slip_days'), s.get('delay_now'), s.get('delay_change')
    share = s.get('ev_of_pv_period') if cost else s.get('forecast_achievement')
    base, p6f = rec.get('baseline_finish'), s.get('forecast_finish_now')
    behind = bool((dnow or 0) > 0 or (slip or 0) > 0 or (share is not None and share < 0.95))
    dd_now = (getattr(curr, 'project', {}) or {}).get('data_date')
    next_dd = (dd_now + timedelta(days=days)) if (dd_now and days) else None
    pname = 'Performance %' if cost else 'Progress %'

    # tiles
    plan_now = r.get('planned_now')
    tiles = [{'label': pname, 'value': f'{s.get("actual_now", 0):.1f}%', 'tone': '',
              'sub': ((f'plan {plan_now:.1f}%' if plan_now is not None else '')
                      + (f' · {"behind" if r.get("gap_money", 0) > 0 else "ahead"} by {_m(abs(r.get("gap_money", 0)))}'
                         if cost and r.get('gap_money') is not None else ''))},
             {'label': 'Earned this period', 'value': f'{round(share * 100)}%' if share is not None else '—',
              'tone': 'bad' if (share is not None and share < 0.95) else ('good' if share is not None else ''),
              'sub': (f'{_m(r.get("rate_money"))} of {_m(r.get("planned_money"))} planned' if cost
                      else f'+{s.get("period_earned", 0):.1f}% of +{s.get("period_forecast", 0):.1f}% planned')},
             {'label': 'Planned finishes achieved', 'value': f'{adh.get("hit", 0)} of {adh.get("planned", 0)}',
              'tone': '', 'sub': (f'{round(adh["pct"])}% of the activities due to finish' if adh.get('pct') is not None
                                  else 'no activity was due to finish')},
             {'label': 'Forecast finish', 'value': p6f or '—', 'tone': 'navy',
              'sub': ((f'{dnow} wd after {base}' if (dnow or 0) > 0 else (f'{-dnow} wd before {base}' if (dnow or 0) < 0 else f'on {base}'))
                      if (dnow is not None and base) else '')
                     + (f' · {dch} wd lost this period' if (dch or 0) > 0
                        else (f' · {-dch} wd recovered this period' if (dch or 0) < 0 else ''))}]

    tm, pm = [], []
    req_m, req_p, more = r.get('required_money'), r.get('required_pct'), r.get('required_more_pct')
    need = (f'{_m(req_m)} every {days} days (now {_m(r.get("rate_money"))}'
            + (f', {more:+d}%' if more is not None else '') + ')') if (cost and req_m) else (
        f'{req_p:.1f}% every {days} days (now {s.get("period_earned", 0):.1f}%)' if req_p is not None else None)
    logic = r.get('logic_days')

    if behind:
        t1 = f'P6 forecasts {p6f}.' if p6f else ''
        if (slip or 0) > 0 and days:
            ratio = slip / days
            t1 += (f' In the last {days} days the finish moved {slip} calendar days later — '
                   + ('about one day lost for every day worked.' if 0.8 <= ratio <= 1.25
                      else f'{ratio:.1f} day lost for every day worked.'))
            nxt = _parse(p6f or '')
            if nxt:
                t1 += f' If the same slip repeats, the next update would show about {_fmt(nxt + timedelta(days=slip))}.'
        elif slip is not None and slip <= 0:
            t1 += ' The finish did not move later in this period, but the delay already carried is not being recovered.'
        tm.append({'title': (f'The project will not finish on {base} at the present performance' if base
                             else 'The project is behind its plan'), 'text': t1.strip()})
        if need and base:
            t2 = f'To finish on {base} the site must earn {need}'
            if logic and logic > 0:
                t2 += f' and take {logic} days out of the critical sequence'
            t2 += ('. If the extra resources are not approved, a revised completion date should be agreed '
                   'with the Client now rather than later.')
            tm.append({'title': 'Decision needed: recover or re-baseline', 'text': t2})
        elif base:
            tm.append({'title': 'Decision needed: revised completion date',
                       'text': f'The baseline finish {base} can no longer be reached by rate of work alone. '
                               'A revised completion date should be agreed with the Client.'})
        if cost and r.get('gap_money') is not None:
            tm.append({'title': 'Where the money is behind',
                       'text': (f'{_m(r["gap_money"])} of planned work is not yet earned'
                                + (f' (SPI {s["curr_spi"]:.2f})' if s.get('curr_spi') is not None else '') + '. '
                                + (f"This period's shortfall alone is {_m(r.get('shortfall_money'))}"
                                   + (f' — about {r["days_lost"]} days of work at the present rate.' if r.get('days_lost') else '.')
                                   if (r.get('shortfall_money') or 0) > 0 else
                                   'This period earned what the plan asked for; the gap is from earlier periods.'))})
    else:
        tm.append({'title': 'The project is holding its plan',
                   'text': (f'P6 forecasts {p6f}' + (f' against the baseline {base}' if base else '') + '. '
                            + (f'This period earned {round(share * 100)}% of what the plan asked for.' if share is not None else ''))})
        if r.get('rate_finish_label'):
            tm.append({'title': 'Where the present rate lands',
                       'text': f'At the rate of this period the remaining work would be earned by {r["rate_finish_label"]}.'
                               + (f' The sequence of the critical activities adds {logic} days to that.' if (logic or 0) > 0 else '')})
        tm.append({'title': 'No decision needed — keep the present resources',
                   'text': 'Keep the resources where they are; the risk to watch is the critical path below.'})

    chain = _open_chain(curr, cp)
    tail = []
    if chain:
        names = ' · '.join(f'{a["id"]} {a["name"]}' for a in chain)
        pm.append({'title': 'Put the resources on the critical chain first',
                   'text': f'The project finish is driven now by: {names}. Every day gained on these activities '
                           'returns directly to the finish date — an extra crew or a second shift belongs here '
                           'before anywhere else.'})
    if next_dd:
        bits = []
        if behind and cost and req_m:
            tgt = (s.get('actual_now') or 0.0) + (req_p or 0.0)
            bits.append(f'earn at least {_m(req_m)}' + (f' ({req_p:.1f}%) → {pname} {tgt:.1f}% or more' if req_p is not None else ''))
        elif behind and req_p is not None:
            bits.append(f'earn at least {req_p:.1f}% → {pname} {(s.get("actual_now") or 0.0) + req_p:.1f}% or more')
        elif cost and r.get('rate_money'):
            bits.append(f'earn at least {_m(r["rate_money"])} again')
        due = _due_next(curr, dd_now, days)
        if due:
            bits.append(f'finish the {due} activit{"y" if due == 1 else "ies"} the current update forecasts to finish by then')
        shortfall = next((d['count'] for d in cs.get('drivers') or [] if d.get('key') == 'progress shortfall'), 0)
        if shortfall:
            bits.append(f'no further slip on the {shortfall} critical activit{"y" if shortfall == 1 else "ies"} that slipped for lack of progress')
        if bits:
            text = '; '.join(bits) + '.'
            tail.append({'title': f'Target for the next update ({_fmt(next_dd)})', 'text': text[0].upper() + text[1:]})

    rules = ('Rules used: rate = ' + ('Earned Value variance' if cost else '% complete variance')
             + ' ÷ days between the two data dates · needed rate = '
             + ('(Budget − Earned Value)' if cost else 'remaining %')
             + ' ÷ days to the baseline finish · fronts = planned and earned % by activity code for the period '
               '(planned at least 0.3% and earned a quarter of it or less = did not move) · '
               'critical chain = the driving path to the project finish in the current update · '
               'next update = the current data date + the days of this period.')
    fronts = {t: _front_items(t, rows) for t, rows in (by_code or {}).items()}
    fronts = {t: v for t, v in fronts.items() if v}
    ftype = default_code_type(by_code)
    return {'behind': behind, 'tiles': tiles, 'top_management': tm,
            # the Project Manager list = pm_head + pm_fronts[the code chosen in the progress chart] + pm_tail
            'pm_head': pm, 'pm_fronts': fronts, 'pm_tail': tail, 'front_type': ftype,
            'project_manager': pm + fronts.get(ftype, []) + tail, 'rules': rules}
