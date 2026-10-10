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
    # the rate is counted on working days (the calendar most activities run on)
    wd = rec.get('work_days') or days
    cal_name = rec.get('calendar_name')
    dw = 'working days' if cal_name is not None else 'days'
    base_fin = _parse(rec.get('baseline_finish') or '')
    rate_fin = _parse(rec.get('projected_finish') or '') if earned > 0 else None
    p6_fin = _parse(s.get('forecast_finish_now') or '')
    planned_var = s.get('planned_variance') if by_cost else s.get('period_forecast')
    out = {
        'by_cost': by_cost, 'period_days': days, 'work_days': wd, 'calendar_name': cal_name, 'day_word': dw,
        'dd_prev': _iso(dd_prev), 'dd_now': _iso(dd_now),
        'dd_prev_label': _fmt(dd_prev), 'dd_now_label': _fmt(dd_now),
        'actual_prev': s.get('actual_prev'), 'actual_now': s.get('actual_now'),
        'planned_prev': s.get('planned_prev') if by_cost else None,
        'planned_now': s.get('planned_now') if by_cost else s.get('forecast_at_now'),
        'rate_pct': earned, 'planned_pct': planned_var,
        'daily_pct': round(earned / wd, 3),
        'baseline_finish': _iso(base_fin), 'baseline_finish_label': rec.get('baseline_finish'),
        'rate_finish': _iso(rate_fin), 'rate_finish_label': _fmt(rate_fin) if rate_fin else None,
        'p6_finish': _iso(p6_fin), 'p6_finish_label': s.get('forecast_finish_now'),
        'remaining_pct': round(100.0 - (s.get('actual_now') or 0.0), 1),
        'required_pct': rec.get('required_rate'),
    }
    if by_cost:
        ev_var, pv_var = s.get('ev_variance') or 0, s.get('pv_variance') or 0
        daily = ev_var / wd
        remaining = (s.get('bac') or 0) - (s.get('ev_now') or 0)
        out.update({'rate_money': ev_var, 'planned_money': pv_var, 'daily_money': round(daily),
                    'shortfall_money': round(pv_var - ev_var), 'remaining_money': round(remaining),
                    'gap_money': round((s.get('pv_now') or 0) - (s.get('ev_now') or 0))})
        out['days_lost'] = round((pv_var - ev_var) / daily) if daily > 0 else None
        to_bl = rec.get('work_days_to_baseline') or ((base_fin - dd_now).days if base_fin else 0)
        if base_fin and (base_fin - dd_now).days > 0 and to_bl > 0 and remaining > 0:
            need = remaining / to_bl * wd
            out['required_money'] = round(need)
            out['required_more_pct'] = round(100.0 * (need / ev_var - 1)) if ev_var > 0 else None
    else:
        short = (planned_var or 0.0) - earned
        out['days_lost'] = round(short / (earned / wd)) if earned > 0 else None
        req = rec.get('required_rate')
        out['required_more_pct'] = round(100.0 * (req / earned - 1)) if (req and earned > 0) else None
    if rate_fin:
        out['days_to_go_cal'] = (rate_fin - dd_now).days
        out['days_to_go'] = rec.get('days_needed') if rec.get('days_needed') is not None else out['days_to_go_cal']
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


def _weeks(days):
    """'3 weeks' for 21 days, '10 days' otherwise — the period in a site reader's words."""
    if days and days % 7 == 0:
        w = days // 7
        return '1 week' if w == 1 else f'{w} weeks'
    return f'{days} days'


_WORDS = ('no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten')


def _word(n):
    return _WORDS[n] if 0 <= n < len(_WORDS) else str(n)


def _join(names, bold=True):
    names = [f'**{n}**' if bold else str(n) for n in names]
    if len(names) <= 1:
        return ''.join(names)
    return ', '.join(names[:-1]) + ' and ' + names[-1]


def _front_items(code_type, rows, period='this period', has_chain=True):
    """The work fronts of ONE activity code in plain words: the ones that were planned and
    did not move, and the ones that did more than planned."""
    stuck, ahead = _fronts(rows)
    out = []
    if stuck:
        n = len(stuck)
        none = all((r.get('actual') or 0.0) <= 0.0 for _g, r in stuck)
        names = _join([r['value'] for _g, r in stuck])
        out.append({'title': (f'{_word(n).capitalize()} work front{"" if n == 1 else "s"} '
                              + ('did not move at all' if none else 'hardly moved')),
                    'text': f'{names} {"was" if n == 1 else "were"} planned to progress in {period} and '
                            + ('did nothing.' if none else 'did a quarter of the plan or less.'),
                    'action': 'find the reason this week (access, materials, drawings or subcontractor) '
                              'and fix a restart date.',
                    'ref': f'Planner reference: activity code {code_type} · '
                           + _front_text(stuck)})
    if ahead:
        n = len(ahead)
        names = _join([r['value'] for _g, r in ahead])
        out.append({'title': (f'{_word(n).capitalize()} work front{" is" if n == 1 else "s are"} doing better '
                              f'than planned — do not add to {"it" if n == 1 else "them"}'),
                    'text': f'{names} did more than planned.',
                    'action': (f'keep {"it as it is" if n == 1 else "them as they are"}; any spare crew goes to '
                               + ('item 1.' if has_chain else 'the work fronts that are behind.')),
                    'ref': f'Planner reference: activity code {code_type} · ' + _front_text(ahead)})
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


def advice(curr, summary, recovery, rate, crit_summary, adherence, by_code, cp, finish=None):
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
                                   + (f' — about {r["days_lost"]} {r.get("day_word") or "days"} of work at the present rate.' if r.get('days_lost') else '.')
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

    # For the Project Manager — plain words: no SPI, no "critical chain", no % of the project.
    # Activity IDs and code names stay as a small "Planner reference" line under each action.
    per = _weeks(days) if days else 'this period'
    last = f'the last {per}' if days else 'this period'
    these = f'these {per}' if days else 'this period'
    fin_prev = s.get('forecast_finish_prev')
    headline = None
    if share is not None:
        big = f'In {last} the site completed {_share_words(share)} of the planned work.'
        bits = ([f'Work done: {_m(r.get("rate_money"))}', f'Work planned: {_m(r.get("planned_money"))}'] if cost
                else [f'Work done: {s.get("period_earned", 0):.1f}%', f'Work planned: {s.get("period_forecast", 0):.1f}%'])
        if p6f and fin_prev and slip:
            bits.append(f'Expected handover moved from {fin_prev} to {p6f} '
                        f'({abs(slip)} days {"later" if slip > 0 else "earlier"}).')
        elif p6f:
            bits.append(f'Expected handover: {p6f} (did not move).')
        small = ' · '.join(bits[:2]) + (' · ' + bits[2] if len(bits) > 2 else '')
        if base:
            small += f' Contract date: {base}.'
        headline = {'big': big, 'small': small}

    chain = _open_chain(curr, cp)
    tail = []
    if chain:
        paths = {a.get('wbs_path') or '' for a in chain}
        segs = [x.strip() for x in (paths.pop() if len(paths) == 1 else '').split('>') if x.strip()]
        where = (f'{segs[-1]} — {segs[-2]}' if len(segs) >= 2 else (segs[-1] if segs else ''))
        n = len(chain)
        pm.append({'title': f'Put extra crews on {where} first' if where
                   else f'Put extra crews on {"this job" if n == 1 else "these " + _word(n) + " jobs"} first',
                   'text': (f'The handover date of the whole project now depends on {_word(n)} job{"" if n == 1 else "s"}: '
                            + _join([a['name'] for a in chain])
                            + (f' in {where}' if where else '')
                            + '. Every day saved here is a day saved on the handover.'),
                   'action': 'add a crew or a second shift here before anywhere else.',
                   'ref': 'Planner reference: ' + ' · '.join(str(a['id']) for a in chain)})
    if adh.get('planned'):
        hit, plan = adh.get('hit') or 0, adh['planned']
        left = plan - hit
        if left > 0:
            tail.append({'title': (f'Only {hit} of the {plan} jobs due to finish were finished' if hit < 0.8 * plan
                                   else f'{hit} of the {plan} jobs due to finish were finished'),
                         'text': f'{left} job{"" if left == 1 else "s"} that should have closed '
                                 f'{"is" if left == 1 else "are"} still open.',
                         'action': f'ask the planner for the list of {left} and close '
                                   f'{"it" if left == 1 else "them"} before starting new ones.'})
    if next_dd:
        bits = []
        if behind and cost and req_m:
            bits.append(f'complete work worth at least **{_m(req_m)}** ({last} gave {_m(r.get("rate_money"))}'
                        + (f' — about {more}% more is needed' if (more or 0) > 0 else '') + ')')
        elif behind and req_p is not None:
            bits.append(f'complete at least **{req_p:.1f}%** of the project ({last} gave {s.get("period_earned", 0):.1f}%)')
        elif cost and r.get('rate_money'):
            bits.append(f'complete work worth at least **{_m(r["rate_money"])}** again')
        due = _due_next(curr, dd_now, days)
        if due:
            bits.append(f'finish the **{due} job{"" if due == 1 else "s"}** due by that date')
        if bits:
            text = ' and '.join(bits) + '.'
            if behind and base and (req_m or req_p is not None):
                text += ' That is the pace needed to still reach the contract date.'
            tail.append({'title': f'Target for the next {per} (by {_fmt(next_dd)})' if days
                         else f'Target for the next update ({_fmt(next_dd)})',
                         'text': text[0].upper() + text[1:]})
    def small_item(sm):
        return ({'title': 'The last works to finish are small in money but long in time', 'tone': 'warn',
                     'text': (f'{_join(sm["names"])} {"is" if len(sm["names"]) == 1 else "are"} only about '
                              f'{round(sm["share"])}% of the project value, but '
                              + ('it runs' if len(sm["names"]) == 1 else 'they run') + f' until {sm["until_month"]} and '
                              + ('it sets' if len(sm["names"]) == 1 else 'they set') + ' the handover date.'
                              + (' Hardly any of this work has started.' if (sm.get('done_pct') or 0) < 10 else '')),
                     'action': 'confirm now the delivery dates, the subcontractors and the crews for these works'
                               + (f' — do not wait for {sm["big"]} to finish.' if sm.get('big') else '.')})

    # this action follows the activity code picked in "When will the project finish"
    fin = finish or {}
    pm_small = {t: small_item(x['small']) for t, x in (fin.get('by_type') or {}).items() if x.get('small')}
    small_now = [pm_small[fin['code_type']]] if fin.get('code_type') in pm_small else []

    rules = ('Rules used: rate = ' + ('Earned Value variance' if cost else '% complete variance')
             + ' ÷ days between the two data dates · needed rate = '
             + ('(Budget − Earned Value)' if cost else 'remaining %')
             + ' ÷ days to the baseline finish · fronts = planned and earned % by activity code for the period '
               '(planned at least 0.3% and earned a quarter of it or less = did not move) · '
               'the jobs the handover depends on = the first unfinished activities of the driving path to the '
               'project finish in the current update · jobs due to finish = Schedule adherence · '
               'next update = the current data date + the days of this period.')
    fronts = {t: _front_items(t, rows, these, bool(chain)) for t, rows in (by_code or {}).items()}
    fronts = {t: v for t, v in fronts.items() if v}
    ftype = default_code_type(by_code)
    return {'behind': behind, 'tiles': tiles, 'top_management': tm, 'pm_headline': headline,
            # the Project Manager list = pm_head + pm_fronts[the code chosen in the progress chart] + pm_tail
            # + pm_small[the code chosen in "When will the project finish"]
            'pm_head': pm, 'pm_fronts': fronts, 'pm_tail': tail, 'front_type': ftype, 'pm_small': pm_small,
            'project_manager': pm + fronts.get(ftype, []) + tail + small_now, 'rules': rules}


# ── round 4: figures explained, and the finish by time ──────────────────────

def _share_words(share):
    """0.54 → 'about half' — the period's share of the plan in a site reader's words."""
    p = share * 100.0
    for top, words in ((12, 'very little'), (30, 'about a quarter'), (40, 'about a third'), (58, 'about half'),
                       (70, 'about two thirds'), (82, 'about three quarters'), (95, 'most')):
        if p < top:
            return words
    return 'all' if p < 105 else 'more than all'


def explain(summary, adherence, rate):
    """Where the figures of the report come from: the four markers of the progress bar, the
    Forecast achievement and the Schedule adherence, each with its calculation and how to
    check it in P6. {'markers': [...], 'forecast': {...}, 'adherence': {...}}."""
    s, adh, r = summary or {}, adherence or {}, rate or {}
    cost = s.get('pct_basis') == 'cost' and s.get('ev_variance') is not None
    ddp, ddn = s.get('data_date_prev') or '—', s.get('data_date_now') or '—'
    ap, an, fn = s.get('actual_prev'), s.get('actual_now'), s.get('forecast_at_now')
    pe, pf = s.get('period_earned'), s.get('period_forecast')
    days = s.get('period_days')
    pc = lambda v: '—' if v is None else f'{v:.1f}%'
    p6_yes = 'Yes — Performance %' if cost else 'No — tool calculation'
    markers = []
    if ap is not None:
        markers.append({'key': 'start', 'name': 'Start', 'value': pc(ap), 'source': f'Previous update · {ddp}',
                        'meaning': 'Actual progress when the period started', 'in_p6': cost, 'p6': p6_yes})
    if an is not None:
        markers.append({'key': 'now', 'name': 'Now', 'value': pc(an), 'source': f'Current update · {ddn}',
                        'meaning': 'Actual progress today', 'in_p6': cost, 'p6': p6_yes})
    if cost and s.get('planned_now') is not None:
        markers.append({'key': 'baseline', 'name': 'Baseline plan', 'value': pc(s['planned_now']),
                        'source': f'Baseline, at {ddn}',
                        'meaning': 'Where the baseline wanted the project today'
                                   + (f' (it was {pc(s["planned_prev"])} at {ddp})' if s.get('planned_prev') is not None else ''),
                        'in_p6': True, 'p6': 'Yes — Planned %'})
    if fn is not None:
        markers.append({'key': 'forecast', 'name': 'Previous update forecast', 'value': pc(fn),
                        'source': f'Previous update · {ddp} only',
                        'meaning': f'Where the {ddp} update itself expected the project to be by {ddn}'
                                   + (f' = {pc(ap)} + {pc(pf)}' if (ap is not None and pf is not None) else ''),
                        'in_p6': False, 'p6': 'No — tool calculation'})

    fa = s.get('forecast_achievement')
    forecast = None
    if fa is not None and pe is not None and pf is not None:
        tiles = [{'label': 'Forecast achievement', 'value': f'{round(fa * 100)}%', 'tone': '',
                  'sub': f'{pc(pe)} earned of the {pc(pf)} the {ddp} update scheduled'}]
        if cost and s.get('ev_of_pv_period') is not None:
            sh = s['ev_of_pv_period']
            tiles.append({'label': 'Against the baseline', 'value': f'{round(sh * 100)}%',
                          'tone': 'bad' if sh < 0.95 else 'good',
                          'sub': f'{_m(s.get("ev_variance"))} earned of the {_m(s.get("pv_variance"))} the baseline '
                                 f'planned for the same {days} days'})
        calc = [f'Earned in the period = {pc(an)} − {pc(ap)} = {pc(pe)}'
                + (f'  ({s.get("ev_now", 0):,.0f} − {s.get("ev_prev", 0):,.0f} = {s.get("ev_variance", 0):,.0f} '
                   f'of budget {s.get("bac", 0):,.0f})' if cost else ''),
                f'Scheduled by the {ddp} update for {ddp} → {ddn} = {pc(pf)}',
                f'Forecast achievement = {pc(pe)} ÷ {pc(pf)} = {round(fa * 100)}%']
        forecast = {'tiles': tiles, 'calc': calc,
                    'text': f'The {pc(pf)} is read from the {ddp} update only: each activity\'s work is spread evenly '
                            'between its remaining early start and remaining early finish, and the part that falls '
                            'between the two data dates is added up.',
                    'note': 'Not a P6 figure. It compares the site with its own last forecast, not with the baseline.'
                            + (f' The earned {pc(pe)} is by cost; the scheduled {pc(pf)} is by activity duration.' if cost else '')}

    adherence_x = None
    if adh.get('planned'):
        plan, hit = adh['planned'], adh.get('hit') or 0
        pct = round(adh['pct']) if adh.get('pct') is not None else round(100.0 * hit / plan)
        left = plan - hit
        adherence_x = {
            'tiles': [{'label': 'Schedule adherence', 'value': f'{pct}%', 'tone': 'bad' if pct < 75 else '',
                       'sub': f'{hit} of {plan} activities due to finish were finished'},
                      {'label': 'Due and not finished', 'value': str(left), 'tone': '',
                       'sub': 'listed by name in Word and Excel' if left else 'every due activity was finished'}],
            'calc': [f'Due to finish = activities of the {ddp} update, not milestones, not yet complete, '
                     f'finish date after {ddp} and up to {ddn} = {plan}',
                     f'Finished = those same {plan} that are 100% complete in the {ddn} update = {hit}',
                     f'Schedule adherence = {hit} ÷ {plan} = {pct}%'],
            'text': 'It is a count of activities — a small activity and a large one each count as one. '
                    f'Activities that finished early without being due are not in the {hit}.',
            'p6': f'To check in P6: open the {ddp} update → filter activities that are not milestones, not Completed, '
                  f'with Finish between {ddp} and {ddn} ({plan}). Then see how many of them are Completed in the '
                  f'{ddn} update ({hit}).',
            'missed': list(adh.get('missed') or [])}
    return {'markers': markers, 'forecast': forecast, 'adherence': adherence_x}


_TYPE_NAMES = ('type of works', 'type of work', 'work type', 'works type', 'discipline', 'trade')


def work_type_code(curr, code_types):
    """The activity code that splits the schedule into types of work (civil, mechanical,
    steel…): a code named type of work / discipline / trade, else the code with 2–12 values that covers the most activities."""
    types = list(code_types or [])
    low = {t.lower().strip(): t for t in types}
    for n in _TYPE_NAMES:
        if n in low:
            return low[n]
    for n in _TYPE_NAMES:                       # e.g. 'Trade Code', 'Discipline (L2)'
        hit = sorted(t for t in types if n in t.lower())
        if hit:
            return hit[0]
    best, key = None, None
    acts = list(getattr(curr, 'activities', {}).values())
    for t in types:
        vals, n = set(), 0
        for a in acts:
            v = (a.get('activity_codes') or {}).get(t)
            if v:
                vals.add(v)
                n += 1
        if 2 <= len(vals) <= 12:
            k = (-n, t)
            if key is None or k < key:
                best, key = t, k
    return best


def _wbs_key(curr):
    """Group by WBS: the first WBS level (from the top) that splits the schedule in two or more."""
    paths = [[x.strip() for x in (a.get('wbs_path') or '').split('>') if x.strip()]
             for a in getattr(curr, 'activities', {}).values()]
    depth = 0
    for d in range(max((len(p) for p in paths), default=0)):
        depth = d
        if len({p[d] for p in paths if len(p) > d}) >= 2:
            break

    def key(a):
        p = [x.strip() for x in (a.get('wbs_path') or '').split('>') if x.strip()]
        return p[min(depth, len(p) - 1)] if p else None
    return key


def _roll_types(data, metrics, keyf):
    rec = {r['activity'].get('id'): (r.get('bac') or 0.0, r.get('actual_pct') or 0.0)
           for r in (metrics or {}).get('records') or []}
    g = {}
    for a in getattr(data, 'activities', {}).values():
        key = keyf(a) or NO_VALUE
        e = g.setdefault(key, {'n': 0, 'open': 0, 'bac': 0.0, 'ev': 0.0, 's': None, 'f': None})
        b, p = rec.get(a.get('id'), (0.0, 0.0))
        e['n'] += 1
        e['bac'] += b
        e['ev'] += b * p
        if (a.get('percent_complete') or 0.0) < 1.0:
            e['open'] += 1
            st, fi = a.get('remaining_early_start'), a.get('remaining_early_finish')
            if st and (e['s'] is None or st < e['s']):
                e['s'] = st
            if fi and (e['f'] is None or fi > e['f']):
                e['f'] = fi
    return g


def _day(d):
    return datetime(d.year, d.month, d.day) if d else None


MAX_FINISH_VALUES = 40


def finish_by_type(prev, curr, prev_metrics, curr_metrics, code_types, summary, rate):
    """When the project finishes BY TIME, grouped by an activity code the reader picks: for
    every value, its share of the budget, how much is done, and the finish P6 calculated for it
    in each update (the latest Finish of its activities that are not complete). Nothing here is
    estimated by the tool — the money-rate date is carried beside it for reference only.

    The default section (the code that reads as "type of work") is the dict itself; 'types'
    lists every code that can be picked and 'by_type' holds the section of each. Every schedule
    differs, so WBS is always offered too. None when nothing splits the work."""
    by = {}
    for t in list(code_types or []) + ['WBS']:
        keyf = _wbs_key(curr) if t == 'WBS' else (lambda a, t=t: (a.get('activity_codes') or {}).get(t))
        try:
            sec = _finish_section(prev, curr, prev_metrics, curr_metrics, t, keyf, summary, rate)
        except Exception:
            sec = None
        named = [x for x in (sec or {}).get('rows') or [] if not x['none']]
        if sec and 2 <= len(named) <= MAX_FINISH_VALUES:
            by[t] = sec
    if not by:
        return None
    default = work_type_code(curr, [t for t in by if t != 'WBS']) or ('WBS' if 'WBS' in by else next(iter(by)))
    return dict(by[default], types=list(by), by_type=by)


def _finish_section(prev, curr, prev_metrics, curr_metrics, code_type, keyf, summary, rate):
    s, r = summary or {}, rate or {}
    dd = _day((getattr(curr, 'project', {}) or {}).get('data_date'))
    if not dd:
        return None
    gp, gc = _roll_types(prev, prev_metrics, keyf), _roll_types(curr, curr_metrics, keyf)
    tot = sum(e['bac'] for e in gc.values())
    cost = tot > 0
    contract, money, forecast = _parse(r.get('baseline_finish_label') or ''), _parse(r.get('rate_finish_label') or ''), \
        _parse(s.get('forecast_finish_now') or '')
    ends = [d for d in (contract, money, forecast) if d] + [_day(e['f']) for e in gc.values() if e['f']]
    span = max(1, (max(ends) - dd).days) if ends else 1
    pos = lambda d: round(max(0.0, min(100.0, 100.0 * (d - dd).days / span)), 1) if d else None

    rows = []
    for name, c in gc.items():
        p = gp.get(name) or {}
        f_now, f_prev, st = _day(c['f']), _day(p.get('f')), _day(c['s'])
        left = pos(max(st, dd)) if st else 0.0
        rows.append({'value': name, 'none': name == NO_VALUE, 'activities': c['n'], 'open': c['open'],
                     'bac': round(c['bac']), 'share': round(100.0 * c['bac'] / tot, 1) if cost else None,
                     'done_pct': round(100.0 * c['ev'] / c['bac'], 1) if c['bac'] > 0 else None,
                     'start': _iso(st), 'start_label': _fmt(st) if st else '',
                     'finish_prev': _fmt(f_prev) if f_prev else '', 'finish_now': _fmt(f_now) if f_now else '',
                     'finish_iso': _iso(f_now),
                     'moved': (f_now - f_prev).days if (f_now and f_prev) else None,
                     'days_left': (f_now - dd).days if f_now else None,
                     'left': left, 'width': round(max(0.0, (pos(f_now) or 0.0) - left), 1) if f_now else 0.0,
                     'late': False})
    rows.sort(key=lambda x: (x['none'], -(x['bac'] if cost else x['activities']), x['value']))
    fins_now = [_parse(x['finish_now']) for x in rows if x['finish_now']]
    fins_prev = [_parse(x['finish_prev']) for x in rows if x['finish_prev']]
    f_now, f_prev = (max(fins_now) if fins_now else None), (max(fins_prev) if fins_prev else None)
    total = {'value': 'Project', 'activities': sum(x['activities'] for x in rows), 'open': sum(x['open'] for x in rows),
             'bac': round(tot), 'share': 100.0 if cost else None, 'done_pct': s.get('actual_now'),
             'finish_prev': _fmt(f_prev) if f_prev else '', 'finish_now': _fmt(f_now) if f_now else '',
             'moved': (f_now - f_prev).days if (f_now and f_prev) else None,
             'days_left': (f_now - dd).days if f_now else None}

    # small in money, long in time: the named types under 10% of the budget that are still
    # open after the date the money would all be earned
    daily = r.get('daily_money') or 0
    dw = r.get('day_word') or 'days'
    dw1 = dw[:-1]
    named = [x for x in rows if not x['none']]
    big = max(named, key=lambda x: x['share'] or 0) if (cost and named) else None
    small, why = None, None
    if cost and money and daily > 0 and big and (big['share'] or 0) >= 50.0:
        late = [x for x in named if (x['share'] or 0) < 10.0 and x['bac'] > 0 and x['open'] and x['finish_iso']
                and _parse(x['finish_now']) > money]
        # only when one value carries the money and the late ones together are a small part of it
        if late and 0.5 <= 100.0 * sum(x['bac'] for x in late) / tot <= 25.0:
            for x in late:
                x['late'] = True
            bac = sum(x['bac'] for x in late)
            until = max(_parse(x['finish_now']) for x in late)
            last_start = max((x for x in late if x['start']), key=lambda x: x['start'], default=None)
            ev = sum(x['bac'] * (x['done_pct'] or 0.0) / 100.0 for x in late)
            small = {'names': [x['value'] for x in late], 'share': round(100.0 * bac / tot, 1), 'money': round(bac),
                     'days_at_rate': round(bac / daily), 'until': _fmt(until), 'until_month': until.strftime('%B %Y'),
                     'days_left': (until - dd).days, 'big': big['value'],
                     'done_pct': round(100.0 * ev / bac, 1) if bac else 0.0}
            why = (f'**Why the money date is too early.** {big["value"]} carries {big["share"]:.1f}% of the budget, so the '
                   f'money rate is really the rate of {big["value"]}. {_join(small["names"], bold=False)} '
                   + ('is' if len(small['names']) == 1 else 'together are') + ' only '
                   f'**{small["share"]:.1f}% of the budget ({_m(bac)})**. At {_m(daily)} a {dw1} that money would be earned '
                   f'in **{small["days_at_rate"]} {dw}** — but in the schedule these works need until '
                   f'**{small["until"]} ({small["days_left"]} {"calendar days" if dw != "days" else "days"})**'
                   + (f', and {last_start["value"]} cannot even start before {last_start["start_label"]}'
                      if (last_start and _parse(last_start['start_label']) > dd) else '')
                   + '. Small in money, long in time: they decide the finish, not the money.')

    days = s.get('period_days')
    # the approved wording says "work type"; any other grouping is named neutrally
    unit = 'work type' if any(n in code_type.lower() for n in _TYPE_NAMES) else 'group'
    moved = [x['moved'] for x in rows if x['moved'] is not None]
    later = [m for m in moved if m > 0]
    warning = None
    if later and days:
        slip = s.get('finish_slip_days') or max(later)
        ratio = slip / days
        how = ('almost one day for every day worked' if 0.8 <= ratio <= 1.25 else f'{ratio:.1f} days for every day worked')
        rng = f'{min(later)} to {max(later)}' if min(later) != max(later) else f'{max(later)}'
        warning = ((f'In these {days} days every {unit} moved {rng} days later' if len(later) == len(moved)
                    else f'In these {days} days {len(later)} of the {len(moved)} {unit}s moved later (up to {max(later)} days)')
                   + f' — the finish is moving {how}. If the next period is the same, '
                   + (s.get('forecast_finish_now') or 'the forecast finish') + ' will move again.')

    ddp, ddn = s.get('data_date_prev') or '—', s.get('data_date_now') or '—'
    calc = [f'Finish of a {unit} = the latest Finish date of its activities that are not complete, in that update',
            f'Forecast finish of the project = the latest of all {unit}s'
            + (f' = {total["finish_now"]} (the P6 finish)' if total['finish_now'] else ''),
            f'Moved = Finish in the {ddn} update − Finish in the {ddp} update']
    if cost and money and r.get('remaining_money') is not None and daily:
        calc.append(f'Money date (kept for reference) = remaining budget {r["remaining_money"]:,.0f} ÷ {daily:,.0f} a {dw1} '
                    f'= {r.get("days_to_go")} {dw}'
                    + (f' on calendar “{r["calendar_name"]}” ({r.get("work_days")} working days in the '
                       f'{days} calendar days between the two updates)' if r.get('calendar_name') else '')
                    + f' → {r.get("rate_finish_label")}')
    after = (forecast - contract).days if (forecast and contract) else None
    return {'code_type': code_type, 'by_cost': cost, 'dd_label': _fmt(dd), 'prev_label': ddp, 'now_label': ddn,
            'period_days': days, 'rows': rows, 'total': total,
            'contract_label': r.get('baseline_finish_label'), 'contract_pos': pos(contract),
            'money_label': r.get('rate_finish_label') if cost else None, 'money_pos': pos(money) if cost else None,
            'rate_label': r.get('rate_finish_label'), 'daily_money': daily or None, 'day_word': dw,
            'forecast_label': s.get('forecast_finish_now'), 'forecast_pos': pos(forecast),
            'days_after_contract': after, 'slip_days': s.get('finish_slip_days'),
            'small': small, 'why': why, 'warning': warning, 'calc': calc,
            'calc_note': 'No date here is estimated by the tool: every finish is the date P6 calculated from the logic '
                         'and the remaining durations.',
            'p6': 'To check in P6: open each update → Group by '
                  + ('WBS' if code_type == 'WBS' else f'activity code "{code_type}"') + ' → show the Finish column. '
                  'The summary band of each group shows the same finish dates as this table.'}
