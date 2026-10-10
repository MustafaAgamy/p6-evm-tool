"""Update-vs-Update exporters — PDF (HTML -> Chrome) and Excel.

`render_html` lays out a two-page management report: Page 1 is an Execution Dashboard
for top management (status verdict, Previous->Current scorecard, recovery outlook, key
facts, period S-curve, recommendation); Page 2 is the planner detail (progress, critical
movement, activities to watch, what-moved, milestone trend). `report_excel` mirrors
the same sections into one sheet. Nothing here computes a number.
"""
import html
import textwrap
from datetime import datetime

import report_theme
from utils import date_text as _date_text

_BLUE = report_theme.var('rpt-accent')
_AMBER = report_theme.var('rpt-warn')
_GOOD = report_theme.var('rpt-good')
_BAD = report_theme.var('rpt-bad')
_PALETTE = [report_theme.var('rpt-bad'), report_theme.var('rpt-good'), report_theme.var('rpt-series-1'),
            report_theme.var('rpt-warn'), report_theme.var('rpt-series-4'), report_theme.var('rpt-series-6'),
            report_theme.var('rpt-series-5'), report_theme.var('rpt-series-3')]


def _e(v):
    v = _date_text(v)                     # an ISO date shows as 03-Dec.2026 (comment 46)
    return html.escape(str(v if v is not None else ''))


def _num(v, suffix=''):
    return f'{v}{suffix}' if v is not None else '—'


def _svar(v, suffix=''):
    if v is None:
        return '—'
    return f'{"+" if v > 0 else ""}{v}{suffix}'


def _signpct(v):
    if v is None:
        return '—'
    return f'+{v:.1f}%' if v > 0 else f'{v:.1f}%'


def _spi_disp(v):
    """SPI as a whole percentage (0.81 → '81%')."""
    return f'{round(v * 100)}%' if v is not None else '—'


def _spi_var_disp(v):
    if v is None:
        return '—'
    return f'{"+" if v > 0 else ""}{round(v * 100)}%'


def _pctcell(v):
    return f'{v}%' if v is not None else ''


def _money(v):
    return f'{v:,.0f}' if v is not None else '—'


def _money_short(v):
    a = abs(v)
    if a >= 1e9:
        return f'{v / 1e9:.2f} B'
    if a >= 1e6:
        return f'{v / 1e6:.1f} M'
    return f'{v:,.0f}'


def _by_cost(report):
    """True when the % of both updates is the Performance % of the cost-loaded activities."""
    return ((report or {}).get('summary') or {}).get('pct_basis') == 'cost'


def _pct_title(report):
    return 'Performance %' if _by_cost(report) else 'Overall % Complete'


def _sn_th():
    return '<th class="num" style="width:34px">S/N</th>'


# ── Status verdict (drives the banner) ──────────────────────────────────────

def _verdict(report):
    """(level, headline, detail). Prefers the engine-computed verdict on the report;
    falls back to computing here (keeps exporters usable standalone / in tests)."""
    v = report.get('verdict')
    if v:
        return v.get('level', 'warn'), v.get('headline', ''), v.get('detail', '')
    s = report.get('summary', {}) or {}
    rec = report.get('recovery', {}) or {}
    spv, dch, slip, earned = s.get('spi_variance'), s.get('delay_change'), s.get('finish_slip_days'), s.get('period_earned')
    worse = (spv is not None and spv < 0) or (dch is not None and dch > 0) or (slip is not None and slip > 0)
    better = (spv is not None and spv > 0) or (dch is not None and dch < 0) or (slip is not None and slip < 0)
    if rec.get('feasible') is False and (dch or 0) > 0:
        level, head = 'bad', 'Off track — recovery to the baseline is unlikely at the current rate'
    elif worse and not better:
        level, head = 'warn', 'Slipping — the project lost ground this period'
    elif better and not worse:
        level, head = 'good', 'On track — the project gained ground this period'
    else:
        level, head = 'warn', 'Mixed — little net movement this period'
    bits = []
    if earned is not None:
        ach = s.get('forecast_achievement')
        bits.append(f'earned {_signpct(earned)}' + (f' ({round(ach * 100)}% of plan)' if ach is not None else ''))
    if spv is not None:
        bits.append(f'SPI change {_spi_var_disp(spv)}')
    if slip:
        bits.append(f'finish {"slipped" if slip > 0 else "pulled in"} {abs(slip)} d')
    return level, head, ('; '.join(bits) + '.' if bits else '')


# ── Page 1 — Execution Dashboard ────────────────────────────────────────────

def _card(title, pv, cv, foot, good):
    cls = 'good' if good else 'bad'
    return (f'<div class="card"><div class="ct">{title}</div>'
            f'<div class="cb"><div class="cc"><div class="cl">Previous</div><div class="cv">{_e(pv)}</div></div>'
            f'<div class="cc"><div class="cl">Current</div><div class="cv">{_e(cv)}</div></div></div>'
            f'<div class="cf {cls}">{_e(foot)}</div></div>')


def _exec_dashboard_html(report):
    s = report.get('summary', {}) or {}
    pe, sv, dv, slip = s.get('period_earned'), s.get('spi_variance'), s.get('delay_change'), s.get('finish_slip_days')
    c1 = _card(_pct_title(report), _num(s.get('actual_prev'), '%'), _num(s.get('actual_now'), '%'),
               f'{"▲ " if (pe or 0) >= 0 else "▼ "}{_svar(pe, "%")}', (pe or 0) >= 0)
    c2 = _card('SPI', _spi_disp(s.get('prev_spi')), _spi_disp(s.get('curr_spi')),
               (f'{"▲ " if (sv or 0) >= 0 else "▼ "}{_spi_var_disp(sv)}' if sv is not None else '—'), (sv or 0) >= 0)
    c3 = _card('Delay vs baseline', _num(s.get('delay_prev'), ' wd'), _num(s.get('delay_now'), ' wd'),
               (f'{"▲ " if (dv or 0) > 0 else "▼ "}{_svar(dv, " wd")}' if dv is not None else '—'), (dv or 0) <= 0)
    finish_foot = '—' if slip is None else (f'▼ slipped {slip} d' if slip > 0 else (f'▲ pulled in {-slip} d' if slip < 0 else 'no change'))
    c4 = _card('Forecast finish', s.get('forecast_finish_prev') or '—', s.get('forecast_finish_now') or '—',
               finish_foot, (slip or 0) <= 0)
    cutoff = (f'<p class="cutoff">Comparison window · <b>{_e(report.get("data_date_prev"))}</b> (previous cutoff) '
              f'→ <b>{_e(report.get("data_date_now"))}</b> (current cutoff)</p>')
    return cutoff + f'<div class="cards">{c1}{c2}{c3}{c4}</div>'


def _recovery_html(report):
    r = report.get('recovery', {}) or {}
    if not r:
        return ''
    left = f'Work remaining <b>{_num(r.get("work_remaining"), "%")}</b> · this period earned <b>{_num(r.get("current_rate"), "%")}</b>.'
    if r.get('required_rate') is not None:
        ra = r.get('required_achievement')
        left += (f'<br>To still hit the <b>baseline finish ({_e(r.get("baseline_finish"))}'
                 f'{" · approx" if report.get("baseline_approx") else ""})</b> you\'d need about '
                 f'<b>{_num(r.get("required_rate"), "%")}/period</b>' + (f' (≈{round(ra * 100)}% achievement)' if ra is not None else '') + '.')
    elif r.get('note'):
        left += f'<br>{_e(r.get("note"))}'
    feas = r.get('feasible')
    verdict = ('Recovery to baseline unlikely at the current rate' if feas is False
               else ('Recovery to baseline achievable' if feas is True else 'Indicative projection'))
    vcls = 'bad' if feas is False else ('good' if feas is True else 'warn')
    return (f'<div class="recov"><div class="rl"><div class="rh4">Recovery outlook</div>{left}'
            f'<div class="note" style="margin-top:5px">Indicative planning projection — not a P6 reschedule.</div></div>'
            f'<div class="rr"><div class="rr-h">At the current rate</div>'
            f'<div class="rr-big">Projected finish ≈ {_e(r.get("projected_finish") or "—")}</div>'
            f'<div class="rr-v {vcls}">{verdict}</div></div></div>')


def _facts_html(report):
    s = report.get('summary', {}) or {}
    adh = report.get('schedule_adherence', {}) or {}
    cm = report.get('critical_movement', {}) or {}
    counts = (report.get('buckets', {}) or {}).get('counts', {})
    pc = (report.get('progress', {}) or {}).get('counts', {})   # construction-only progress counts
    ach = s.get('forecast_achievement')
    adh_pct = adh.get('pct')

    def fact(label, value, sub=''):
        return (f'<div class="fact"><div class="fl">{_e(label)}</div><div class="fv">{_e(value)}</div>'
                + (f'<div class="fs">{_e(sub)}</div>' if sub else '') + '</div>')
    return ('<div class="facts">'
            + fact('Activities completed', pc.get('finished', 0), 'reached 100% this period')
            + fact('Activities in progress', pc.get('increased', 0), 'positive % variance this period')
            + fact('Forecast achievement', f'{round(ach * 100)}%' if ach is not None else '—', 'earned vs forecast')
            + fact('Schedule adherence', f'{adh_pct:.0f}%' if adh_pct is not None else '—',
                   f"{adh.get('hit', 0)} of {adh.get('planned', 0)} due finishes hit")
            + fact('Started this period', counts.get('started', 0), 'first progress recorded')
            + fact('New critical items', cm.get('new_critical', 0), 'entered critical path')
            + '</div>')


def _progress_bar_html(report):
    """Three points on the whole-project bar: where you started the period, where the
    last update planned you'd be, and where you actually are. Exact one-decimal %s that
    match the Execution Dashboard."""
    s = report.get('summary', {}) or {}
    ap, an, fn = s.get('actual_prev'), s.get('actual_now'), s.get('forecast_at_now')
    pe, pf = s.get('period_earned'), s.get('period_forecast')
    if an is None:
        return ''
    pdd, cdd = _e(report.get('data_date_prev')), _e(report.get('data_date_now'))
    fill = max(0.0, min(100.0, an))
    clamp = lambda v: max(0.0, min(100.0, v))
    # the markers above the bar: labels that would sit on each other step up a line, and a
    # label near either end is anchored to that end so it is never cut off
    tags, base_txt = [], ''
    if ap is not None:
        tags.append((clamp(ap), f'start {ap:.1f}%', 'var(--rpt-muted)'))
    if fn is not None:
        tags.append((clamp(fn), f'planned {fn:.1f}%', 'var(--rpt-warn)'))
    bp = s.get('planned_now') if _by_cost(report) else None
    if bp is not None:
        tags.append((clamp(bp), f'baseline plan {bp:.1f}%', 'var(--rpt-bad)'))
        base_txt = f' The baseline planned <b>{bp:.1f}%</b> by this cut-off.'
    tags.sort(key=lambda t: t[0])
    last_at, lines, marks = {}, 1, []
    for pos, txt, col in tags:
        lv = 0
        while lv in last_at and pos - last_at[lv] < 17:
            lv += 1
        last_at[lv] = pos
        lines = max(lines, lv + 1)
        tr = 'translateX(-100%)' if pos > 86 else ('translateX(0)' if pos < 10 else 'translateX(-50%)')
        marks.append(f'<div class="pmark" style="left:{pos:.1f}%;background:{col};top:{-5 - 14 * lv}px"></div>'
                     f'<span class="tag-above" style="left:{pos:.1f}%;color:{col};top:{-21 - 14 * lv}px;transform:{tr}">▾ {txt}</span>')
    what = ('All are <b>Performance %</b> — Earned Value ÷ Budget of the cost-loaded activities, as P6 shows it'
            if _by_cost(report) else 'All three are % of the whole project')
    behind = ''
    if fn is not None:
        gap = round(fn - an, 1)
        behind = f' — <b>{"on/ahead of" if gap <= 0 else f"{abs(gap):.1f}% behind"}</b> your plan'
    ach = s.get('forecast_achievement')
    ach_txt = f'{round(ach * 100)}%' if ach is not None else '—'
    plan_txt = (f'Your last update planned <b>{fn:.1f}%</b> by now ({_svar(pf, "%")}). ' if fn is not None else '')
    return (f'<div class="prog"><div class="cap"><span>0% — project start</span><span>100% — finish</span></div>'
            f'<div class="pbar" style="margin-top:{14 * (lines - 1)}px">'
            f'<div class="pfill" style="width:{fill:.1f}%">{an:.1f}%</div>'
            f'<span class="tag-below" style="left:{fill:.1f}%">▴ now {an:.1f}%</span>'
            f'{"".join(marks)}</div>'
            f'<div class="psent">On <b>{pdd}</b> you were at <b>{ap:.1f}%</b>. {plan_txt}You reached <b>{an:.1f}%</b> on <b>{cdd}</b> ({_svar(pe, "%")}). '
            f'{what}{behind}; you did {_svar(pe, "%")} of {_svar(pf, "%")} = <b>{ach_txt}</b>.{base_txt}</div></div>')


# ── Earned Value — before, after and variance (owner, comments 68–73 round 2) ──

def _ev_bridge_svg(s, pdd, cdd):
    """Three columns: Earned Value at the previous cut-off, what this period added, Earned
    Value now — the added part drawn from where the previous one ends."""
    a, b = s['ev_prev'], s['ev_now']
    top = max(a, b, 1)
    base, hh = 150, 100
    y = lambda v: base - hh * v / top
    d = b - a
    col = 'var(--rpt-good)' if d >= 0 else 'var(--rpt-bad)'
    ya, yb = y(a), y(b)
    dy, dh = min(ya, yb), max(abs(ya - yb), 2)
    pe = s.get('period_earned')
    t = lambda x, yy, txt, size=11, fill='var(--rpt-muted)', w='400': (
        f'<text x="{x}" y="{yy:.0f}" text-anchor="middle" font-size="{size}" font-weight="{w}" fill="{fill}">{txt}</text>')
    return (f'<svg viewBox="0 0 700 190" width="100%" style="max-height:230px" role="img" aria-label="Earned Value bridge">'
            f'<line x1="40" y1="{base}" x2="660" y2="{base}" stroke="var(--rpt-chart-axis)" stroke-width="1.5"/>'
            f'<rect x="70" y="{ya:.0f}" width="130" height="{base - ya:.0f}" rx="2" fill="var(--rpt-muted)"/>'
            f'<line x1="200" y1="{ya:.0f}" x2="285" y2="{ya:.0f}" stroke="var(--rpt-chart-axis)" stroke-dasharray="4 4"/>'
            f'<rect x="285" y="{dy:.0f}" width="130" height="{dh:.0f}" rx="2" fill="{col}"/>'
            f'<line x1="415" y1="{yb:.0f}" x2="500" y2="{yb:.0f}" stroke="var(--rpt-chart-axis)" stroke-dasharray="4 4"/>'
            f'<rect x="500" y="{yb:.0f}" width="130" height="{base - yb:.0f}" rx="2" fill="var(--rpt-accent)"/>'
            + t(135, ya - 6, _money(a), 12.5, 'var(--rpt-ink)', '700')
            + t(350, dy - 6, f'{d:+,.0f}', 12.5, col, '700')
            + t(565, yb - 6, _money(b), 12.5, 'var(--rpt-ink)', '700')
            + t(135, base + 15, 'Earned Value — previous') + t(135, base + 29, f'{pdd} · {_num(s.get("actual_prev"), "%")}')
            + t(350, base + 15, 'Earned this period') + t(350, base + 29, f'{_svar(pe, "%")} of the budget')
            + t(565, base + 15, 'Earned Value — current') + t(565, base + 29, f'{cdd} · {_num(s.get("actual_now"), "%")}')
            + '</svg>')


def _ev_html(report):
    """Performance % tiles, the Earned Value bridge and the before / after / variance table.
    Empty when the updates carry no cost (nothing to earn against)."""
    s = report.get('summary', {}) or {}
    if not _by_cost(report) or s.get('ev_now') is None or s.get('ev_prev') is None:
        return ''
    from p6_export.auto_parts import wrap_part as _part
    pdd, cdd = _e(report.get('data_date_prev')), _e(report.get('data_date_now'))
    pe, days = s.get('period_earned'), s.get('period_days')
    intro = (f'<p class="note" style="margin-top:0;font-style:normal"><b>Performance %</b> = Earned Value ÷ Budget of the cost-loaded '
             f'activities ({_money(s.get("cost_activities"))} of {_money(s.get("all_activities"))} activities; Budget '
             f'<b>{_money(s.get("bac"))}</b>) — the figure P6 shows as Performance % Complete. Activities without cost take no part.</p>')
    if s.get('bac_prev') is not None and s.get('bac') is not None and abs(s['bac_prev'] - s['bac']) >= 1:
        intro += (f'<p class="note">The budget itself changed between the two updates: {_money(s["bac_prev"])} → {_money(s["bac"])}. '
                  'Each Performance % is against its own update\'s budget.</p>')

    def tile(k, v, f, cls=''):
        return (f'<div class="fact"><div class="fl">{k}</div><div class="fv {cls}">{v}</div><div class="fs">{f}</div></div>')
    tiles = ('<div class="facts" style="margin-top:6px">'
             + tile(f'Performance % — previous · {pdd}', _num(s.get('actual_prev'), '%'), 'Earned Value ÷ Budget')
             + tile(f'Performance % — current · {cdd}', _num(s.get('actual_now'), '%'), 'Earned Value ÷ Budget')
             + tile('Variance — earned this period', _svar(pe, '%'),
                    f'in {days} calendar days' if days is not None else 'between the two cut-offs',
                    'pos' if (pe or 0) >= 0 else 'neg')
             + '</div>')

    def var(txt, good=None):
        cls = '' if good is None else (' pos' if good else ' neg')
        return f'<td class="num{cls}">{txt}</td>'

    def row(label, a, b, v, bold=False):
        lab = f'<b>{label}</b>' if bold else label
        return f'<tr><td>{lab}</td><td class="num mono">{a}</td><td class="num mono">{b}</td>{v}</tr>'
    spv, slip = s.get('spi_variance'), s.get('finish_slip_days')
    f2 = lambda v: f'{v:.2f}' if v is not None else '—'
    slip_txt = ('—' if slip is None else (f'{slip} days later' if slip > 0
                else (f'{-slip} days earlier' if slip < 0 else 'no change')))
    table = ('<table class="data"><thead><tr><th>Figure</th>'
             f'<th class="num">Previous · {pdd}</th><th class="num">Current · {cdd}</th><th class="num">Variance</th></tr></thead><tbody>'
             + row('Earned Value', _money(s.get('ev_prev')), _money(s.get('ev_now')),
                   var(f'{s["ev_variance"]:+,.0f}', s['ev_variance'] >= 0), True)
             + row('Planned Value', _money(s.get('pv_prev')), _money(s.get('pv_now')), var(f'{s.get("pv_variance") or 0:+,.0f}'))
             + row('Performance % (Earned Value ÷ Budget)', _num(s.get('actual_prev'), '%'), _num(s.get('actual_now'), '%'),
                   var(_svar(pe, '%'), (pe or 0) >= 0), True)
             + row('Planned %', _num(s.get('planned_prev'), '%'), _num(s.get('planned_now'), '%'), var(_svar(s.get('planned_variance'), '%')))
             + row('SPI (Earned Value ÷ Planned Value)', f2(s.get('prev_spi')), f2(s.get('curr_spi')),
                   var(f'{spv:+.2f}' if spv is not None else '—', None if spv is None else spv >= 0))
             + row('Forecast finish', _e(s.get('forecast_finish_prev') or '—'), _e(s.get('forecast_finish_now') or '—'),
                   var(slip_txt, None if slip is None else slip <= 0))
             + '</tbody></table>')
    reading = ''
    pvv, evv, share = s.get('pv_variance'), s.get('ev_variance'), s.get('ev_of_pv_period')
    if pvv and pvv > 0 and share is not None:
        reading = (f'<p class="note"><b>Reading:</b> the plan asked for {_money_short(pvv)} of work in this period; '
                   f'{_money_short(evv)} was earned — {round(share * 100)}% of what the period needed.</p>')
    reading += ('<p class="note"><b>Where each figure is in P6:</b> Earned Value = the sum of the column "Earned Value Cost" '
                '(each activity\'s Performance % Complete × its baseline budget); Budget = "Budget At Completion", '
                'the baseline\'s Budgeted Total Cost; Performance % = one ÷ the other. '
                'Planned Value, Planned % and SPI are worked out by the tool from the baseline dates and budget — '
                'P6 does not write them into the exported file, so its own "Planned Value Cost" can differ slightly.</p>')
    return (intro + _part('earned_value.tiles', 'Performance % — previous, current, variance', tiles)
            + '<div class="chart keep" style="margin-top:9px" data-part="earned_value.bridge" '
              'data-part-label="Earned Value bridge — previous → earned → current">'
            + _ev_bridge_svg(s, pdd, cdd) + '</div>'
            + _part('earned_value.table', 'Earned Value — before / after / variance table', table + reading)
            + _ev_code_html(report))


def _ev_pcts(r):
    """(Performance % previous, Performance % current, Variance %) of one Earned-Value-by-code
    row — each the money over that value's own budget; Nones when it has no budget."""
    bac = r.get('bac') or 0
    if not bac:
        return None, None, None
    return (100.0 * (r.get('ev_prev') or 0) / bac, 100.0 * (r.get('ev_now') or 0) / bac,
            100.0 * (r.get('variance') or 0) / bac)


def _ev_pct_cells(r):
    return ['' if v is None else round(v, 1) for v in _ev_pcts(r)]


def _ev_code_html(report):
    """Earned Value before / after / variance by the values of the activity code picked on
    screen (round 3, point 04) — only the picked values when some are ticked, with their total."""
    t = report.get('ev_code_type')
    rows = ((report.get('ev_by_code') or {}).get(t) or []) if t else []
    if not rows:
        return ''
    _t, vals = _cf_parts(report.get('code_filter'))
    picked = [r for r in rows if r.get('value') in vals] if vals else rows
    if not picked:
        return ''
    from p6_export.auto_parts import wrap_part as _part
    s = report.get('summary', {}) or {}
    pdd, cdd = _e(report.get('data_date_prev')), _e(report.get('data_date_now'))
    tot = {k: sum(r.get(k) or 0 for r in picked) for k in ('activities', 'bac', 'ev_prev', 'ev_now', 'variance')}

    def tr(sn, name, r, bold=False):
        b = (lambda x: f'<b>{x}</b>') if bold else (lambda x: x)
        v = r.get('variance') or 0
        pp, pn, pvar = _ev_pcts(r)
        pct = (f'<td class="num">{b("—" if pp is None else f"{pp:.1f}%")}</td>'
               f'<td class="num">{b("—" if pn is None else f"{pn:.1f}%")}</td>'
               + ('<td class="num">—</td>' if pvar is None else
                  f'<td class="num {"pos" if pvar > 0.05 else ("neg" if pvar < -0.05 else "")}">{pvar:+.1f}%</td>'))
        return (f'<tr><td class="num">{sn}</td><td>{b(_e(name))}</td><td class="num">{b(_money(r.get("activities")))}</td>'
                f'<td class="num mono">{b(_money(r.get("bac")))}</td><td class="num mono">{b(_money(r.get("ev_prev")))}</td>'
                f'<td class="num mono">{b(_money(r.get("ev_now")))}</td>'
                f'<td class="num {"pos" if v > 0.5 else ("neg" if v < -0.5 else "")}">{v:+,.0f}</td>{pct}</tr>')
    body = ''.join(tr(i, r.get('value'), r) for i, r in enumerate(picked, 1))
    body += tr('', 'Total — the picked values' if vals else 'Total — all cost-loaded activities', tot, True)
    table = (f'<table class="data"><thead><tr>{_sn_th()}<th>{_e(t)}</th><th class="num">Cost-loaded activities</th>'
             f'<th class="num">Budget</th><th class="num">Earned Value — previous · {pdd}</th>'
             f'<th class="num">Earned Value — current · {cdd}</th><th class="num">Variance</th>'
             f'<th class="num">Performance % — previous</th><th class="num">Performance % — current</th>'
             f'<th class="num">Variance %</th></tr></thead><tbody>'
             + body + '</tbody></table>'
             '<p class="note">Performance % = Earned Value ÷ Budget of that value; Variance % = the progress it gained '
             'between the two updates (Variance ÷ Budget).</p>')
    note = ''
    pv = s.get('ev_variance')
    if vals and pv:
        note = (f'<p class="note">The picked values earned {_money(tot["variance"])} of the project\'s {_money(pv)} in this period '
                f'({round(100.0 * tot["variance"] / pv)}%).</p>')
    head = f'Earned Value by {_e(t)}' + (' — the picked values only' if vals else ' — every value')
    return _part('earned_value.by_code', 'Earned Value by activity code — before / after / variance',
                 f'<div class="sub-h">{head}</div>{table}{note}')


# ── Critical-path movement — the summary in charts, in front of the table ──

def _crit_summary(report):
    """The summary block for the rows the report is about to print — re-read from those rows
    when a code filter narrowed them (or an older saved result carries none)."""
    cs = report.get('critical_summary')
    if cs is None or report.get('code_filter'):
        from p6_period.movement import critical_summary
        cs = critical_summary(report.get('critical_movement'), report.get('code_types') or [])
    return cs or {}


def crit_group_choice(cs, chosen=None):
    """(group 1, group 2) the two 'where' charts are drawn by. The owner's pick when given;
    else the activity code that covers most critical activities in the fewest values, and WBS."""
    groups = (cs or {}).get('groups') or {}
    chosen = list(chosen or [])
    codes = [k for k in groups if k != 'WBS' and (groups[k].get('groups') or 0) >= 2]
    # a code that only repeats the WBS comes last — the second chart is the WBS already
    codes.sort(key=lambda k: ('wbs' in k.lower(), -(groups[k].get('covered') or 0), groups[k].get('groups') or 0, k))
    g1 = chosen[0] if (chosen and chosen[0] in groups) else (codes[0] if codes else None)
    g2 = chosen[1] if (len(chosen) > 1 and chosen[1] in groups) else ('WBS' if 'WBS' in groups else None)
    if g1 == g2:
        g1 = None
    return g1, g2


def _hbars(rows, label, value, text, cls=''):
    mx = max([value(r) for r in rows] or [1]) or 1
    return '<div class="hbs">' + ''.join(
        f'<div class="hb"><span class="hbl">{_e(label(r))}</span>'
        f'<div class="hbt"><i class="{cls}" style="width:{max(1, round(100.0 * value(r) / mx))}%"></i></div>'
        f'<span class="hbn">{text(r)}</span></div>' for r in rows) + '</div>'


def _crit_group_chart(cs, g):
    grp = ((cs.get('groups') or {}).get(g) or {})
    rows = grp.get('rows') or []
    if not rows:
        return ''
    n = grp.get('groups') or len(rows)
    head = (f'Where the critical activities are, and the worst slip in each — by {_e(g)}'
            + (f' (top {len(rows)} of {n})' if n > len(rows) else ''))
    worst = cs.get('max_slip') or 0

    def text(r):
        ms = r.get('max_slip') or 0
        cls = 'slip worst' if (ms > 0 and ms >= worst) else ('slip' if ms > 0 else 'slip none')
        return f'<b>{r["count"]}</b> <span class="{cls}">{f"worst slip {ms} wd" if ms > 0 else "no slip"}</span>'
    note = ('Bar = how many critical activities sit in the group. Badge = the largest slip of any of them between the two '
            'updates (working days); red = the worst in the project.')
    if g != 'WBS' and grp.get('covered') is not None:
        note += f' {grp["covered"]} of the {cs.get("total")} critical activities carry this code.'
    return (f'<div class="keep"><div class="sub-h">{head}</div>'
            + _hbars(rows, lambda r: r['value'], lambda r: r['count'], text).replace('<div class="hbs">', '<div class="hbs wide">', 1)
            + f'<p class="note">{note}</p></div>')


_DRIVER_MEANING = {
    'progress shortfall': 'the finish moved later because the work did not progress as the previous update planned',
    'held': 'the finish stayed where it was, or moved earlier',
    'logic changed': 'the planner edited the relationships of the activity — a link added or removed, its type or its lag changed',
    'duration extended': 'the remaining duration was made longer than the previous update had',
}


def _driver_bars(drivers):
    """'Why they moved' — one bar per reason, each with a line saying what the reason means."""
    mx = max([d['count'] for d in drivers] or [1]) or 1
    return '<div class="hbs">' + ''.join(
        f'<div class="hb"><span class="hbl"><b>{_e(d["label"])}</b></span>'
        f'<div class="hbt"><i class="w" style="width:{max(1, round(100.0 * d["count"] / mx))}%"></i></div>'
        f'<span class="hbn"><b>{d["count"]}</b></span></div>'
        + (f'<div class="hbm">{_e(_DRIVER_MEANING[d["key"]])}</div>' if d.get('key') in _DRIVER_MEANING else '')
        for d in drivers) + '</div>'


def _moved_text(n):
    if n is None:
        return '—', ''
    if n > 0:
        return f'{n} wd later', 'neg'
    if n < 0:
        return f'{-n} wd earlier', 'pos'
    return 'no change', ''


def _logic_html(report):
    """What 'Relationships changed' means, and what changed for each of those activities."""
    rows = report.get('logic_changes') or []
    if not rows:
        return ''
    box = ('<div class="defs" style="margin-top:6px"><div class="defs-h">"Relationships changed" — what it means</div>'
           '<div class="def">Between the previous and the current update, the <b>relationships</b> of the activity were edited: '
           'a predecessor or successor was added or removed, the relationship type changed (FS / SS / FF / SF), or the lag changed. '
           'For these activities the finish date moved because the planner changed the logic — not because of progress on site. '
           'Only construction activities are counted.</div></div>')

    def tr(i, r):
        txt, cls = _moved_text(r.get('slip_days'))
        ch = '<br>'.join(_e(c) for c in r.get('changes') or []) or '—'
        return (f'<tr><td class="num">{i}</td><td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
                f'<td class="num mono">{_e(r.get("prev_finish"))}</td><td class="num mono">{_e(r.get("curr_finish"))}</td>'
                f'<td class="num {cls}">{txt}</td><td>{ch}</td></tr>')
    table = (f'<table class="data"><thead><tr>{_sn_th()}<th>Activity ID</th><th>Activity name</th>'
             '<th class="num">Finish — previous</th><th class="num">Finish — current</th><th class="num">Finish moved</th>'
             '<th>What changed in the relationships (previous → current)</th></tr></thead><tbody>'
             + ''.join(tr(i, r) for i, r in enumerate(rows, 1)) + '</tbody></table>')
    n = len(rows)
    return (f'<div class="keep"><div class="sub-h">Relationships changed — the {n} critical activit{"y" if n == 1 else "ies"}</div>'
            f'{box}{table}</div>')


def _critical_summary_html(report, group=None):
    cs = _crit_summary(report)
    total = cs.get('total') or 0
    if not total:
        return ''
    s = report.get('summary', {}) or {}
    slip = s.get('finish_slip_days')
    fin = '—' if slip is None else (f'+{slip} d' if slip > 0 else (f'{slip} d' if slip < 0 else 'no change'))

    def tile(k, v, f, cls=''):
        return f'<div class="fact"><div class="fl">{k}</div><div class="fv {cls}">{v}</div><div class="fs">{f}</div></div>'
    prev_total, left = cs.get('prev_total'), cs.get('left')
    tiles = ('<div class="facts" style="grid-template-columns:repeat(5,1fr);margin-top:4px">'
             + tile('Critical now', total, f'previous update: {prev_total}' if prev_total is not None else 'in the current update')
             + tile('Stayed critical', cs.get('stayed', 0), 'critical in both updates')
             + tile('New critical', cs.get('new', 0), 'became critical this period', 'neg' if cs.get('new') else '')
             + tile('No longer critical', left if left is not None else '—',
                    (f'{cs.get("left_finished") or 0} finished · {(left or 0) - (cs.get("left_finished") or 0)} gained float'
                     if left is not None else ''))
             + tile('Finish of the path', fin, f'{_e(s.get("forecast_finish_prev") or "—")} → {_e(s.get("forecast_finish_now") or "—")}',
                    'neg' if (slip or 0) > 0 else '')
             + '</div>'
             '<p class="note" style="font-style:normal"><b>Critical</b> = P6\'s own Critical flag, read with the file\'s setting '
             '(Total Float less than or equal to the critical limit — 0 unless the project changed it — or the Longest Path). '
             'The count is the one P6 gives under the filter Critical = Yes; finished activities are never critical.</p>')
    bands = cs.get('bands') or []
    mx = max([b['count'] for b in bands] or [1]) or 1
    hist = ('<div class="hist">' + ''.join(
        f'<div class="hcol"><b>{b["count"]}</b><i style="height:{max(2, round(100.0 * b["count"] / mx))}%"></i></div>' for b in bands)
        + '</div><div class="hl">' + ''.join(f'<span>{_e(b["label"])}</span>' for b in bands) + '</div>')
    slipped = [b for b in bands if (b.get('lo') or 0) >= 1]
    big = max(slipped, key=lambda b: b['count']) if slipped else None
    reading = ''
    if big:
        days = s.get('period_days')
        reading = (f'<div class="def"><b>Reading:</b> {big["count"]} of {total} moved {_e(big["label"]).replace(" days", "")} working days'
                   + (f' in this period of {days} calendar days' if days is not None else '')
                   + f'; the largest slip is {cs.get("max_slip")} working days.</div>')
    ex = cs.get('example')
    example = (f'<div class="def" style="color:var(--rpt-muted)">Example: {_e(ex["activity_id"])} {_e(ex["activity_name"])} — '
               f'{_e(ex["prev_finish"])} → {_e(ex["curr_finish"])} = {ex["slip_days"]} working days.</div>') if ex else ''
    how = ('<div class="defs"><div class="defs-h">How to read this chart</div>'
           '<div class="def"><b>Slip</b> = the activity\'s finish in the current update − its finish in the previous update, '
           'in working days. It is not measured against the baseline and it is not the Total Float.</div>'
           '<div class="def"><b>Each bar</b> = the number of critical activities whose finish moved by that many working days.</div>'
           + reading + example + '</div>')
    left_col = f'<div><div class="sub-h">How far the critical activities slipped (working days)</div>{hist}{how}</div>'
    g1, g2 = crit_group_choice(cs, group)
    why = '<div class="sub-h">Why they moved</div>' + _driver_bars(cs.get('drivers') or [])
    right_col = f'<div>{why}</div>'
    g = g1 or g2
    where = _crit_group_chart(cs, g) if g else ''
    new_rows = cs.get('new_rows') or []
    newt = ''
    if new_rows:
        shown = new_rows[:20]
        newt = (f'<div class="keep"><div class="sub-h">The {len(new_rows)} activit{"y" if len(new_rows) == 1 else "ies"} that became critical this period</div>'
                f'<table class="data"><thead><tr>{_sn_th()}<th>Activity ID</th><th>Activity name</th>'
                '<th class="num">Slip (working days)</th><th class="num">Total Float — previous (working days)</th>'
                '<th class="num">Total Float — current (working days)</th></tr></thead><tbody>'
                + ''.join(f'<tr><td class="num">{i}</td><td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
                          f'<td class="num {"neg" if (r.get("slip_days") or 0) > 0 else ""}">{_svar(r.get("slip_days"))}</td>'
                          f'<td class="num">{_num(r.get("prev_float_days"))}</td>'
                          f'<td class="num">{_num(r.get("float_days"))}</td></tr>' for i, r in enumerate(shown, 1))
                + '</tbody></table>'
                + (f'<p class="note">{len(new_rows) - len(shown)} more — all are marked "new" in the full table of the Word and Excel exports.</p>' if len(new_rows) > len(shown) else '')
                + '</div>')
    return (f'<div class="keep">{tiles}</div><div class="split keep">{left_col}{right_col}</div>{where}{newt}')


# ── Critical path style — which one to use (printed above the comparison) ──

_CP_STYLE_CARDS = (
    ('chain', '1 · Connected chain',
     '<rect x="2" y="18" width="70" height="22" rx="4" fill="var(--rpt-accent-soft)" stroke="var(--rpt-accent)"/>'
     '<rect x="90" y="18" width="70" height="22" rx="4" fill="var(--rpt-accent-soft)" stroke="var(--rpt-accent)"/>'
     '<rect x="178" y="18" width="70" height="22" rx="4" fill="var(--rpt-bad-bg)" stroke="var(--rpt-bad)"/>'
     '<path d="M72 29h18M160 29h18M248 29h22" stroke="var(--rpt-muted)" stroke-width="2"/>'
     '<rect x="272" y="21" width="16" height="16" transform="rotate(45 280 29)" fill="var(--rpt-bad)"/>',
     'the route as blocks joined one after another; the new part in red.',
     'you want to read the logic — what leads to what.'),
    ('timeline', '2 · Date-axis timeline',
     '<line x1="0" y1="52" x2="300" y2="52" stroke="var(--rpt-chart-axis)"/>'
     '<g stroke="var(--rpt-chart-grid)"><line x1="60" y1="4" x2="60" y2="52"/><line x1="130" y1="4" x2="130" y2="52"/>'
     '<line x1="200" y1="4" x2="200" y2="52"/><line x1="270" y1="4" x2="270" y2="52"/></g>'
     '<rect x="10" y="10" width="200" height="12" rx="2" fill="var(--rpt-muted)"/>'
     '<rect x="10" y="30" width="200" height="12" rx="2" fill="var(--rpt-accent)"/>'
     '<rect x="210" y="30" width="50" height="12" rx="2" fill="var(--rpt-bad)"/>',
     'last update over this update on real months.',
     'you want to see WHEN the path runs and how many days the finish moved.'),
    ('table', '3 · Compact table',
     '<rect x="4" y="6" width="292" height="14" fill="var(--rpt-surface-2)"/>'
     '<g fill="none" stroke="var(--rpt-chart-axis)"><rect x="4" y="6" width="292" height="46"/>'
     '<line x1="4" y1="20" x2="296" y2="20"/><line x1="4" y1="36" x2="296" y2="36"/>'
     '<line x1="90" y1="6" x2="90" y2="52"/><line x1="194" y1="6" x2="194" y2="52"/></g>',
     'the two routes side by side as text.',
     'space is short or the report goes into a letter.'),
)


def _cp_styles_html(style='chain'):
    """The three ways the critical path can be drawn, what each shows and when to use it —
    the one this report uses is outlined (owner: 'clarify the differences of the style types')."""
    cards = ''.join(
        f'<div class="stylecard{" sel" if key == style else ""}"><div class="sc-h">{_e(title)}'
        + ('<span class="sc-on">used in this report</span>' if key == style else '') + '</div>'
        f'<svg viewBox="0 0 300 58" width="100%" style="max-height:62px">{svg}</svg>'
        f'<div class="def"><b>Shows:</b> {_e(shows)}</div><div class="def"><b>Use it when</b> {_e(when)}</div></div>'
        for key, title, svg, shows, when in _CP_STYLE_CARDS)
    return ('<div class="keep"><div class="sub-h">Critical path style — which one to use</div>'
            f'<div class="stylecards">{cards}</div>'
            '<p class="note">All three draw the same route from the same figures — only the drawing changes.</p></div>')


def _cp_key(act, mode):
    """Grouping key for a driving-path activity: a WBS segment or an activity-code value."""
    if mode.startswith('code:'):
        return (act.get('codes') or {}).get(mode[5:]) or '(no code)'
    segs = [s for s in (act.get('wbs_path') or '').split(' > ') if s]
    if not segs:
        return '(no WBS)'
    if mode.startswith('wbs'):
        i = int(mode[3:])
        return segs[i] if i < len(segs) else segs[-1]
    return segs[-2] if len(segs) >= 2 else segs[-1]      # 'leaf-parent' default


def _cp_segments(acts, mode):
    """Consecutive driving-path activities grouped into dated segments by WBS level or
    activity code. Each: {'key', 'start' (ISO|None), 'finish' (ISO|None)}."""
    segs = []
    for a in acts:
        k = _cp_key(a, mode)
        st, fn = a.get('start'), a.get('finish')
        if segs and segs[-1]['key'] == k:
            s = segs[-1]
            if st and (s['start'] is None or st < s['start']):
                s['start'] = st
            if fn and (s['finish'] is None or fn > s['finish']):
                s['finish'] = fn
        else:
            segs.append({'key': k, 'start': st, 'finish': fn})
    return segs


def _cp_conclusion(prev, curr, div, summary):
    """Plain-English headline. Finish date + slip come from the summary (the P6 numbers).
    Unchanged route reads one way, a reroute another — matching the one-row / two-row layout."""
    fn, slip = summary.get('forecast_finish_now'), summary.get('finish_slip_days')
    route = lambda segs, a: ' → '.join(s['key'] for s in segs[a:]) or '—'
    if div < len(curr) or div < len(prev):                    # the route rerouted
        at = curr[div - 1]['key'] if div > 0 else 'the start'
        head = (f'Your critical path <b>rerouted at {_e(at)}</b> — it used to finish through '
                f'<b>{_e(route(prev, div))}</b>; now it runs <b>{_e(route(curr, div))}</b>')
        if slip and slip > 0:
            head += f', slipping the finish <b>+{slip} days to {_e(fn)}</b>.'
        elif slip and slip < 0:
            head += f', pulling the finish in <b>{abs(slip)} days to {_e(fn)}</b>.'
        elif fn:
            head += f', with the finish holding at <b>{_e(fn)}</b>.'
        else:
            head += '.'
        return head
    head = (f'<b>Same critical path as last period.</b> It runs <b>{_e(route(curr, 0))}</b> '
            f'and drives your finish on <b>{_e(fn)}</b>')          # unchanged route
    if slip and slip > 0:
        head += f' (slipped {slip} day{"s" if slip != 1 else ""} this period).'
    elif slip and slip < 0:
        head += f' (pulled in {abs(slip)} day{"s" if abs(slip) != 1 else ""} this period).'
    else:
        head += '.'
    return head


def _cp_timeline_data(report, mode='leaf-parent'):
    """Structured route comparison: WAS/NOW segments (dated), the divergence index, whether
    the route `changed`, the finish labels + slip, and the plain conclusion. None if there's
    no driving path."""
    cp = report.get('critical_path', {}) or {}
    prevA, currA = cp.get('previous') or [], cp.get('current') or []
    if not prevA and not currA:
        return None
    prev, curr = _cp_segments(prevA, mode), _cp_segments(currA, mode)
    div = 0
    while div < len(prev) and div < len(curr) and prev[div]['key'] == curr[div]['key']:
        div += 1
    s = report.get('summary', {}) or {}
    return {'prev': prev, 'curr': curr, 'divergence': div,
            'changed': div < len(prev) or div < len(curr),
            'finish_prev': s.get('forecast_finish_prev'), 'finish_now': s.get('forecast_finish_now'),
            'slip_days': s.get('finish_slip_days'), 'conclusion': _cp_conclusion(prev, curr, div, s)}


def _span_label(a_iso, b_iso):
    """A compact month range for a segment: 'Sep 2025' | 'Aug – Sep 2025' | 'Aug 25 – Jan 26'."""
    def _p(iso):
        try:
            return datetime.strptime(iso, '%Y-%m-%d')
        except Exception:
            return None
    a, b = _p(a_iso), _p(b_iso)
    if not a and not b:
        return ''
    a, b = a or b, b or a
    if a.year == b.year and a.month == b.month:
        return a.strftime('%b %Y')
    if a.year == b.year:
        return f'{a.strftime("%b")} – {b.strftime("%b %Y")}'
    return f'{a.strftime("%b %y")} – {b.strftime("%b %y")}'


def _cp_widths(prev, curr, div):
    """Block widths (px) proportional to each segment's duration, on ONE shared scale so
    the two rows use the same mapping. The shared prefix takes the CURRENT row's widths in
    both rows, so it lines up vertically even if progress shifted the dates; each tail uses
    its own durations. The longer chain's finish flag then sits further right = the slip."""
    def _days(s):
        try:
            d = (datetime.strptime(s['finish'], '%Y-%m-%d') - datetime.strptime(s['start'], '%Y-%m-%d')).days
            return d if d > 0 else 30
        except Exception:
            return 30
    def _floor(s):
        # room for the block's own name on about two lines (it wraps inside the block; a
        # 58 px block used to CUT a long name - 'Above Silos From S6 Till S10 …' read 'Above')
        n = len(str(s.get('key') or ''))
        return min(150, max(58, int(n * 6.2 / 2) + 14))
    pd = div if div <= len(curr) else len(curr)
    prefix = [_days(curr[i]) for i in range(pd)]
    curr_tail = [_days(s) for s in curr[pd:]]
    prev_tail = [_days(s) for s in prev[div:]] if div <= len(prev) else []
    widest = max(sum(prefix) + sum(curr_tail), sum(prefix) + sum(prev_tail), 1)
    scale = 620.0 / widest
    px = lambda w, s: max(_floor(s), round(w * scale))
    pre = [px(w, curr[i]) for i, w in enumerate(prefix)]
    return (pre + [px(w, s) for w, s in zip(prev_tail, prev[div:])],
            pre + [px(w, s) for w, s in zip(curr_tail, curr[pd:])])


def _cp_chain_html(segs, widths, div, tail_role, flag_role, finish_date):
    """One connected chain of blocks flowing to a finish flag. Blocks before `div` are
    shared (blue); from `div` on they take `tail_role` ('gone' grey-struck | 'new' red)."""
    out = []
    for i, s in enumerate(segs):
        role = 'shared' if i < div else tail_role
        lab = _span_label(s.get('start'), s.get('finish'))
        sub = f'<small>{_e(lab)}</small>' if lab else ''
        w = widths[i] if i < len(widths) else 80
        out.append(f'<div class="cpblk {role}" style="width:{w}px">{_e(s["key"])}{sub}</div>')
        if i < len(segs) - 1:
            newarr = ' new' if (tail_role == 'new' and i >= div - 1) else ''
            out.append(f'<div class="cparw{newarr}">→</div>')
    final_new = ' new' if (tail_role == 'new' and div < len(segs)) else ''
    out.append(f'<div class="cparw{final_new}">→</div>'
               f'<div class="cpflag {flag_role}"><span class="cpdia {flag_role}"></span>'
               f'<b>{_e(finish_date)}</b><span class="cpfl">finish</span></div>')
    return '<div class="cpchain">' + ''.join(out) + '</div>'


def _cp_chain_body(data):
    """Connected-chain body (the conclusion is added by the caller): one row when unchanged,
    two aligned rows (old greyed, new red) on a reroute."""
    prev, curr, div = data['prev'], data['curr'], data['divergence']
    wprev, wcurr = _cp_widths(prev, curr, div)
    if not data['changed']:
        return ('<div class="cprowlbl">This period\'s critical path</div>'
                + _cp_chain_html(curr, wcurr, len(curr), 'new', 'now', data['finish_now'])
                + '<p class="note">One row — the route is the same as last period. The blocks sit end-to-end as a '
                  'chain, each labelled with the months it spans.</p>')
    slip = data.get('slip_days')
    slipnote = (f'<div class="cpslip">↳ the finish moved {"+" if slip > 0 else ""}{slip} working days '
                f'(the Now chain runs {"longer" if slip > 0 else "shorter"} than the old one).</div>') if slip else ''
    legend = ('<div class="cplegend"><i style="background:var(--rpt-accent-soft)"></i>shared route (unchanged)'
              '<i style="background:var(--rpt-bad-bg)"></i>new route (from the reroute)'
              '<i style="background:var(--rpt-surface-2)"></i>old route (dropped off)</div>')
    return ('<div class="cprowlbl">Was — last update</div>'
            + _cp_chain_html(prev, wprev, div, 'gone', 'was', data['finish_prev'])
            + '<div class="cprowlbl" style="margin-top:9px">Now — this update</div>'
            + _cp_chain_html(curr, wcurr, div, 'new', 'now', data['finish_now'])
            + slipnote + legend
            + '<p class="note">Two rows because the route changed. They line up at the reroute point; the old route '
              'is greyed, the new route red, and the finish flags sit further apart the bigger the slip.</p>')


_CP_TL_FILL = {'same': report_theme.var('rpt-accent-soft'), 'new': report_theme.var('rpt-bad'), 'gone': report_theme.var('rpt-surface-2')}
_CP_TL_INK = {'same': report_theme.var('rpt-accent'), 'new': report_theme.var('rpt-accent-ink'), 'gone': report_theme.var('rpt-muted')}


def _cp_timeline_body(data, report):
    """Date-axis Gantt style: WAS row (last update) over NOW row (this update) on a real
    calendar; shared prefix blue, new route red from the divergence, dropped tail grey;
    finish diamonds + the TOTAL slip bracket (no per-segment day splits)."""
    prev, curr, div = data['prev'], data['curr'], data['divergence']

    def _ord(iso):
        try:
            return datetime.strptime(iso, '%Y-%m-%d').toordinal()
        except Exception:
            return None
    UNIT = 20                                        # fallback width (days) for an undated segment

    def _layout(segs):
        pos, cur = [], None
        for s in segs:
            a, b = _ord(s.get('start')), _ord(s.get('finish'))
            start = a if a is not None else (cur if cur is not None else 0)
            if cur is not None and start < cur:
                start = cur                          # keep the row monotonic on odd dates
            end = b if (b is not None and b > start) else start + UNIT
            pos.append((start, end)); cur = end
        return pos
    pprev, pcurr = _layout(prev), _layout(curr)
    xs = [v for pr in (pprev + pcurr) for v in pr]
    if not xs:
        return '<p class="note">The driving path has no dates to place on a timeline.</p>'
    tmin, tmax = min(xs), max(xs)
    if tmax <= tmin:
        tmax = tmin + UNIT
    x0, x1 = 160, 830
    xat = lambda t: x0 + (x1 - x0) * (t - tmin) / (tmax - tmin)
    p = []
    for k in range(5):                               # month gridlines + labels
        t = tmin + (tmax - tmin) * k / 4
        x = xat(t)
        p.append(f'<line x1="{x:.0f}" y1="40" x2="{x:.0f}" y2="222" stroke="var(--rpt-chart-grid)"/>'
                 f'<text x="{x:.0f}" y="238" text-anchor="middle" font-size="9" fill="var(--rpt-chart-axis)">'
                 f'{datetime.fromordinal(int(t)).strftime("%b-%y")}</text>')

    def _draw(segs, pos, y, is_curr):
        for i, (s, (a, b)) in enumerate(zip(segs, pos)):
            role = 'same' if i < div else ('new' if is_curr else 'gone')
            x, w = xat(a), max(6.0, xat(b) - xat(a))
            p.append(f'<rect x="{x:.0f}" y="{y}" width="{w:.0f}" height="24" rx="4" fill="{_CP_TL_FILL[role]}"/>')
            cap = int(w / 6.5)
            if w >= 34 and cap >= 3:
                lab = s['key'] if len(s['key']) <= cap else s['key'][:cap - 1] + '…'
                p.append(f'<text x="{x + w / 2:.0f}" y="{y + 16:.0f}" text-anchor="middle" '
                         f'font-size="10" fill="{_CP_TL_INK[role]}">{_e(lab)}</text>')
    _draw(prev, pprev, 60, False)
    _draw(curr, pcurr, 120, True)
    p.append(f'<text x="14" y="74" font-size="11" font-weight="700" fill="var(--rpt-muted)">WAS · {_e(report.get("data_date_prev"))}</text>')
    p.append(f'<text x="14" y="134" font-size="11" font-weight="700" fill="var(--rpt-ink)">NOW · {_e(report.get("data_date_now"))}</text>')
    if pprev:
        fx = xat(pprev[-1][1])
        p.append(f'<path d="M{fx:.0f},72 l7,-7 l7,7 l-7,7 z" fill="var(--rpt-muted)"/>'
                 f'<text x="{fx + 18:.0f}" y="58" font-size="9.5" fill="var(--rpt-muted)">finish {_e(data["finish_prev"])}</text>')
    if pcurr:
        gx = xat(pcurr[-1][1])
        p.append(f'<path d="M{gx:.0f},132 l7,-7 l7,7 l-7,7 z" fill="var(--rpt-bad)"/>'
                 f'<text x="{gx + 18:.0f}" y="118" font-size="9.5" fill="var(--rpt-bad)" font-weight="700">finish {_e(data["finish_now"])}</text>')
    slip = data.get('slip_days')
    if pprev and pcurr and slip:
        lo, hi = sorted((xat(pprev[-1][1]), xat(pcurr[-1][1])))
        p.append(f'<line x1="{lo:.0f}" y1="196" x2="{hi:.0f}" y2="196" stroke="var(--rpt-bad)" stroke-width="1.5"/>'
                 f'<line x1="{lo:.0f}" y1="192" x2="{lo:.0f}" y2="200" stroke="var(--rpt-bad)"/>'
                 f'<line x1="{hi:.0f}" y1="192" x2="{hi:.0f}" y2="200" stroke="var(--rpt-bad)"/>'
                 f'<text x="{(lo + hi) / 2:.0f}" y="212" text-anchor="middle" font-size="10.5" '
                 f'fill="var(--rpt-bad)" font-weight="700">{"+" if slip > 0 else ""}{slip} wd</text>')
    if div < len(curr) or div < len(prev):
        src = pcurr[div][0] if div < len(pcurr) else (pprev[div][0] if div < len(pprev) else None)
        if src is not None:
            dx = xat(src)
            p.append(f'<line x1="{dx:.0f}" y1="52" x2="{dx:.0f}" y2="168" stroke="var(--rpt-bad)" stroke-width="1" stroke-dasharray="3 3"/>'
                     f'<text x="{dx:.0f}" y="182" text-anchor="middle" font-size="9.5" fill="var(--rpt-bad)" font-weight="700">rerouted here</text>')
    legend = ('<div class="cplegend"><i style="background:var(--rpt-accent-soft)"></i>shared route (on both)'
              '<i style="background:var(--rpt-bad)"></i>new critical route (from the reroute)'
              '<i style="background:var(--rpt-surface-2)"></i>old route (dropped off)</div>')
    return (f'<svg viewBox="0 0 960 250" width="100%" role="img" aria-label="Critical path timeline">{"".join(p)}</svg>'
            f'{legend}<p class="note">The finish-driving route on a real date axis — <b>WAS</b> (last update) over '
            f'<b>NOW</b> (this update). The bracket at the right is the <b>total finish movement</b>.</p>')


def _cp_table_body(data):
    """Compact Was/Now comparison as a table — the most print-dense style; the new part of
    the route (from the divergence) is shown in red."""
    prev, curr, div = data['prev'], data['curr'], data['divergence']
    plain = lambda segs: ' → '.join(_e(s['key']) for s in segs) or '—'

    def _redtail(segs):
        parts = [(f'<span class="cpt-red">{_e(s["key"])}</span>' if i >= div else _e(s['key'])) for i, s in enumerate(segs)]
        return ' → '.join(parts) or '—'
    slip = data.get('slip_days')
    fintail = ''
    if slip and slip > 0:
        fintail = f' <span class="cpt-red">(+{slip} wd)</span>'
    elif slip and slip < 0:
        fintail = f' <span class="cpt-red">({slip} wd)</span>'
    if data['changed']:
        at = _e(curr[div - 1]['key']) if div > 0 else 'the start'
        rerouted = f'<span class="cpt-red">{at}</span> <span class="cpt-mut">(was: {plain(prev[div:])})</span>'
    else:
        rerouted = '— <span class="cpt-mut">(unchanged this period)</span>'
    return ('<table class="cptable"><tr><th></th><th>Was — last update</th><th>Now — this update</th></tr>'
            f'<tr><td class="cpt-k">Driving route</td><td>{plain(prev)}</td><td>{_redtail(curr)}</td></tr>'
            f'<tr><td class="cpt-k">Forecast finish</td><td>{_e(data["finish_prev"])}</td>'
            f'<td class="cpt-fin">{_e(data["finish_now"])}{fintail}</td></tr>'
            f'<tr><td class="cpt-k">Rerouted at</td><td>—</td><td>{rerouted}</td></tr></table>'
            '<p class="note">The finish-driving route as text — the most compact style; the new part of the route is in red.</p>')


def _critical_compare_html(report, style='chain', mode='leaf-parent'):
    """Critical-path comparison in the chosen presentation `style` (chain | timeline | table),
    grouped by `mode`. All three styles share the same data, so every figure is identical —
    only the drawing changes. `style`/`mode` come from the on-screen picker and the PDF export."""
    data = _cp_timeline_data(report, mode)
    if not data:
        return '<p class="note">No driving path to the finish milestone could be derived.</p>'
    concl = (f'<div class="cpconcl {"warn" if data["changed"] else "good"}">'
             f'<span class="cpic">{"⚠" if data["changed"] else "✓"}</span><div>{data["conclusion"]}</div></div>')
    body = (_cp_timeline_body(data, report) if style == 'timeline'
            else _cp_table_body(data) if style == 'table'
            else _cp_chain_body(data))
    from p6_export.auto_parts import wrap_part as _part
    return (_part('critical_compare.styles', 'Critical path style — which one to use', _cp_styles_html(style))
            + _part('critical_compare.conclusion', 'Did the finish-driving path change — conclusion', concl)
            + _part('critical_compare.paths', 'Critical path — previous vs current', body))


def _whatmoved_html(report):
    """Planned vs actual chart for what moved; counts shown as text so they're always readable."""
    counts = (report.get('buckets', {}) or {}).get('counts', {})
    pc = report.get('plan_counts', {}) or {}
    fin, sta = counts.get('finished', 0), counts.get('started', 0)
    pfin, psta = pc.get('planned_finish', 0), pc.get('planned_start', 0)
    slip, stal, res = counts.get('slipped', 0), counts.get('stalled', 0), counts.get('re_sequenced', 0)
    mx = max(pfin, psta, fin, sta, slip, stal, res, 1)
    w = lambda n: max(2, round(100.0 * n / mx))

    def row(lbl, planned, actual, cls, txt):
        pbar = f'<div class="wmp" style="width:{w(planned)}%"></div>' if planned else ''
        return (f'<div class="wmrow"><span class="wml">{lbl}</span>'
                f'<div class="wmtrack">{pbar}<div class="wma {cls}" style="width:{w(actual)}%"></div></div>'
                f'<span class="wmnum">{txt}</span></div>')
    rows = (row('Finished', pfin, fin, 'g', f'<b>{fin}</b> done / {pfin} due')
            + row('Started', psta, sta, 'g', f'<b>{sta}</b> done / {psta} due')
            + row('Slipped', 0, slip, 'b', f'<b>{slip}</b> activities')
            + row('Stalled', 0, stal, 'w', f'<b>{stal}</b> activities')
            + row('Re-sequenced', 0, res, 'n', f'<b>{res}</b> activities'))
    defs = ('<div class="defs" data-part="whatmoved.defs" data-part-label="What these mean (definitions)">'
            '<div class="defs-h">What these mean</div>'
            '<div class="def"><b>Grey bar</b> = planned (due to finish/start this period), <b>coloured</b> = actual; the count on the right is always shown.</div>'
            '<div class="def"><b>Slipped</b> — the activity\'s finish moved <b>later</b> than the previous update showed.</div>'
            '<div class="def"><b>Stalled</b> — it was scheduled to be progressing but earned <b>0%</b> this period.</div>'
            '<div class="def"><b>Re-sequenced</b> — its logic / lag was <b>changed</b> vs last period.</div></div>')
    return (f'<div data-part="whatmoved.chart" data-part-label="What moved — planned vs actual bars">{rows}</div>'
            f'{defs}')


def bycode_group(report, group=None):
    """The activity code the progress histogram is drawn by: the one chosen on screen, else
    the code that splits this period's movement into the most values."""
    bc = report.get('progress_by_code', {}) or {}
    if group in bc:
        return group
    try:
        from p6_period.insight import default_code_type
        return default_code_type(bc) or next(iter(bc), None)
    except Exception:
        return next(iter(bc), None)


def _bycode_html(report, group=None):
    """Planned vs actual progress of the period by one activity code, as a histogram: two
    columns per value (planned, actual), each with its figure above it."""
    bc = report.get('progress_by_code', {}) or {}
    if not bc:
        return '<p class="note">No activity codes in this schedule to break progress down by.</p>'
    code_type = bycode_group(report, group)
    allrows = bc.get(code_type) or []
    rows = [r for r in allrows if (r.get('planned') or 0) > 0 or (r.get('actual') or 0) > 0][:10] or allrows[:10]
    mx = max((max(r['planned'], r['actual']) for r in rows), default=1) or 1
    h = lambda v: max(1, round(86.0 * v / mx))

    def col(r):
        pl, ac = r['planned'], r['actual']
        low = ac < pl - 0.05
        return ('<div class="vg">'
                f'<div class="vb"><b>{pl:.1f}%</b><i class="pl" style="height:{h(pl)}%"></i></div>'
                f'<div class="vb"><b class="{"neg" if low else ""}">{ac:.1f}%</b><i class="ac" style="height:{h(ac)}%"></i></div></div>')
    chart = ('<div class="vhist">' + ''.join(col(r) for r in rows) + '</div>'
             '<div class="vl-row">' + ''.join(f'<span class="vl">{_e(r["value"])}</span>' for r in rows) + '</div>')
    legend = ('<div class="legend"><span><i style="background:var(--rpt-warn);height:9px;width:12px"></i>Planned for the period</span>'
              '<span><i style="background:var(--rpt-accent);height:9px;width:12px"></i>Actual in the period</span>'
              '<span>% of the whole project · a red label = earned less than planned</span></div>')
    more = len(allrows) - len(rows)
    return (f'<p class="note" style="font-style:normal">Grouped by activity code <b>{_e(code_type)}</b>'
            + (f' — the {len(rows)} values that moved most' if more > 0 else '')
            + '. Each value has two columns, with its figure above it — weighted by each activity\'s cost / duration share of the project.</p>'
            + f'<div class="chart keep" data-part="bycode.chart" data-part-label="Progress by activity code — planned vs actual histogram">{legend}{chart}</div>')


def _defs_html():
    defs = [
        ('Forecast achievement', 'how much of what you forecast last period you actually delivered (100% = hit your plan; 78% = about three-quarters).'),
        ('Schedule adherence', 'of the activities that were due to finish this period, how many actually finished (72% = 13 of 18).'),
        ('Started this period', 'activities that got underway this period (recorded their first progress).'),
        ('New critical activities', 'activities that became critical this period — any delay to them now pushes the project finish date.'),
    ]
    return ('<div class="defs"><div class="defs-h">What these numbers mean</div>'
            + ''.join(f'<div class="def"><b>{_e(a)}</b> — {_e(b)}</div>' for a, b in defs) + '</div>')


# ── Page 2 — planner tables ─────────────────────────────────────────────────

def _progress_table_html(report):
    rows = (report.get('progress', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No activity changed its % complete between the two updates.</p>'
    shown = rows[:20]
    body = ''.join(
        '<tr>'
        f'<td class="num">{i}</td>'
        f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
        f'<td>{_e(r.get("status"))}{" ⚠ reversed" if r.get("reversal") else ""}</td>'
        f'<td class="num">{_e(r.get("prev_pct"))}%</td><td class="num">{_e(r.get("curr_pct"))}%</td>'
        f'<td class="num {"neg" if r.get("reversal") else "pos"}">{_signpct(r.get("variance"))}</td>'
        '</tr>' for i, r in enumerate(shown, 1))
    more = f'<p class="note">Showing the {len(shown)} biggest movers of {len(rows)} — full list on screen and in Excel.</p>' if len(rows) > len(shown) else ''
    return (f'<table class="data"><thead><tr>{_sn_th()}<th>Activity ID</th><th>Activity name</th><th>Status</th>'
            '<th class="num">Prev %</th><th class="num">Current %</th><th class="num">Variance</th></tr></thead><tbody>'
            + body + '</tbody></table>' + more
            + '<p class="note">Prev % / Current % are each activity\'s own Performance % Complete, as P6 holds it.</p>')


def _critical_table_html(report):
    rows = (report.get('critical_movement', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No activity is critical in the current update.</p>'
    body = ''.join(
        '<tr>'
        f'<td class="num">{i}</td>'
        f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td><td>{_e(r.get("wbs"))}</td>'
        f'<td class="num mono">{_e(r.get("prev_finish"))}</td><td class="num mono">{_e(r.get("curr_finish"))}</td>'
        f'<td class="num">{("+" + str(r.get("slip_days")) + " wd") if (r.get("slip_days") or 0) > 0 else ((str(r.get("slip_days")) + " wd") if (r.get("slip_days") or 0) < 0 else "—")}</td>'
        f'<td class="num">{_e(r.get("float_days"))}</td><td>{_e(r.get("driver"))}</td>'
        f'<td>{"new" if r.get("critical_status") == "new" else "stayed"}</td>'
        '</tr>' for i, r in enumerate(rows, 1))
    return (f'<table class="data"><thead><tr>{_sn_th()}<th>Activity ID</th><th>Activity name</th><th>WBS</th>'
            '<th class="num">Finish (prev)</th><th class="num">Finish (now)</th><th class="num">Slip (wd)</th><th class="num">Total Float (wd)</th>'
            '<th>Driver</th><th>Critical</th></tr></thead><tbody>' + body + '</tbody></table>'
            '<p class="note">Every activity P6 flags Critical in the current update, worst slip first. '
            'On screen you can filter this by any activity code.</p>')


def _watch_table_html(report):
    rows = (report.get('watch_list', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No near-critical work is queued before the next update.</p>'
    body = ''.join(
        '<tr>'
        f'<td class="num">{i}</td>'
        f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
        f'<td class="num mono">{_e(r.get("due_to_start"))}</td><td class="num">{_e(r.get("float_days"))}</td>'
        f'<td>{_e(r.get("reason"))}</td></tr>' for i, r in enumerate(rows, 1))
    intro = ('<div class="reco" style="margin-bottom:8px">These are the <b>unfinished construction activities most likely to delay the finish date '
             'before your next update</b> — the ones with a Total Float of 10 working days or less, tightest first. '
             'The last column says why each one is listed: <b>1)</b> it is on the critical path · '
             '<b>2)</b> its float dropped to 10 working days or less in this period · '
             '<b>3)</b> it follows an activity that slipped this period. '
             'Any other was already near-critical in the previous update.</div>')
    table = ('<table class="data" data-part="watch.table" data-part-label="Activities to watch — table">'
             f'<thead><tr>{_sn_th()}<th>Activity ID</th><th>Activity name</th>'
             '<th class="num">Due to start</th><th class="num">Total Float (working days)</th><th>Why it is listed</th></tr></thead><tbody>'
             + body + '</tbody></table>')
    defs = ('<div class="defs" data-part="watch.defs" data-part-label="Column notes">'
            '<div class="defs-h">Columns</div>'
            '<div class="def"><b>Total Float</b> — spare working days before this activity would delay the project finish (0 or less = on the critical path; up to 10 = near-critical).</div>'
            '<div class="def"><b>Due to start</b> — the activity\'s forecast start date, from the current update.</div>'
            '<div class="def"><b>Why it is listed</b> — the reason this activity needs attention before the next update.</div></div>')
    return intro + table + defs


def _buckets_html(report):
    counts = (report.get('buckets', {}) or {}).get('counts', {})
    order = [('finished', 'Finished'), ('started', 'Started'), ('slipped', 'Slipped'),
             ('stalled', 'Stalled'), ('re_sequenced', 'Re-sequenced')]
    return '<div class="pills">' + ''.join(
        f'<span class="pill">{counts.get(k, 0)} {lbl}</span>' for k, lbl in order) + '</div>'


def _milestone_slip_cell(sp, sb):
    if sp is None:
        return '—'
    if sp > 0:
        tail = f' (→ +{sb} d vs baseline)' if sb is not None else ''
        return f'<span class="neg">▼ +{sp} d{tail}</span>'
    if sp < 0:
        return f'<span class="pos">▲ {abs(sp)} d earlier</span>'
    return '<span class="pos">• on track</span>'


def _moved_cell(sp):
    if sp is None:
        return '—'
    if sp > 0:
        return f'<span class="neg">{sp} wd later</span>'
    if sp < 0:
        return f'<span class="pos">{abs(sp)} wd earlier</span>'
    return '<span class="pos">no change</span>'


def _vs_baseline_cell(sb):
    if sb is None:
        return '—'
    if sb > 0:
        return f'<span class="neg">{sb} wd late</span>'
    if sb < 0:
        return f'<span class="pos">{abs(sb)} wd early</span>'
    return '<span class="pos">on baseline</span>'


def _milestone_table_html(report):
    """Every finish milestone, its name in full (owner: 'the milestones seem trimmed') — the
    project-completion milestone in bold."""
    ms = report.get('milestones', {}) or {}
    rows = list(ms.get('rows') or [])
    overall = ms.get('overall')
    if not rows and overall:
        rows = [overall]
    if not rows:
        return '<p class="note">No finish milestone found in the update.</p>'
    ax = ' · approx' if report.get('baseline_approx') else ''   # own Planned dates stand in
    oid = (overall or {}).get('activity_id')

    def name(r):
        n = _e(r.get('name'))
        return f'<b>{n}</b> <span class="note">(project completion)</span>' if (oid and r.get('activity_id') == oid) else n
    body = ''.join(
        f'<tr><td class="num">{i}</td><td>{name(r)}</td><td class="num mono">{_e(r.get("baseline_finish"))}</td>'
        f'<td class="num mono">{_e(r.get("prev_forecast"))}</td><td class="num mono">{_e(r.get("curr_forecast"))}</td>'
        f'<td class="num">{_moved_cell(r.get("slip_period_days"))}</td>'
        f'<td class="num">{_vs_baseline_cell(r.get("slip_baseline_days"))}</td></tr>' for i, r in enumerate(rows, 1))
    return (f'<table class="data"><thead><tr>{_sn_th()}<th style="width:32%">Milestone</th>'
            f'<th class="num">Baseline{ax}</th>'
            '<th class="num">Previous forecast</th><th class="num">Current forecast</th>'
            f'<th class="num">Moved this period</th><th class="num">Against baseline{ax}</th></tr></thead><tbody>'
            + body + '</tbody></table>')


def _milestone_drift_svg(report):
    """One row per milestone on a date line — Baseline (hollow), Previous forecast (amber),
    Current forecast (red) dots, so each milestone's slide is visible."""
    rows = (report.get('milestones', {}) or {}).get('rows', [])
    ords = []
    for r in rows:
        for k in ('baseline_iso', 'prev_iso', 'curr_iso'):
            if r.get(k):
                ords.append(datetime.strptime(r[k], '%Y-%m-%d').toordinal())
    if not rows or len(ords) < 2:
        return ''
    tmin, tmax = min(ords), max(ords)
    if tmin == tmax:
        tmin, tmax = tmin - 15, tmax + 15
    # drawn 700 units wide (was 940): on the Reporting Studio's portrait page the 940-wide chart
    # was scaled to 68 % and its labels printed at 4 pt; 700 keeps them near 7 pt there and the
    # landscape report still shows it at natural size (max-height stops it growing)
    x0, x1, top = 236, 680, 14
    # the name in full, wrapped onto as many lines as it needs — never cut (owner comment)
    names = [textwrap.wrap(str(r.get('name') or ''), 40) or [''] for r in rows]
    heights = [max(24, 12 * len(ls) + 10) for ls in names]
    ytops = [top + sum(heights[:i]) for i in range(len(rows))]
    body_h = sum(heights)
    h = top + body_h + 22
    xat = lambda t: x0 + (x1 - x0) * ((t - tmin) / (tmax - tmin))
    od = lambda iso: datetime.strptime(iso, '%Y-%m-%d').toordinal()
    parts = []
    for k in range(5):
        t = tmin + (tmax - tmin) * k / 4
        x = xat(t)
        parts.append(f'<line x1="{x:.0f}" y1="{top}" x2="{x:.0f}" y2="{top + body_h:.0f}" stroke="var(--rpt-chart-grid)"/>'
                     f'<text x="{x:.0f}" y="{top + body_h + 14:.0f}" text-anchor="middle" font-size="9.5" fill="var(--rpt-chart-axis)">'
                     f'{datetime.fromordinal(int(t)).strftime("%b-%y")}</text>')
    for i, r in enumerate(rows):
        y = ytops[i] + heights[i] / 2
        ls = names[i]
        for j, ln in enumerate(ls):
            ty = y + 3 + 12 * (j - (len(ls) - 1) / 2)
            parts.append(f'<text x="{x0 - 8}" y="{ty:.0f}" text-anchor="end" font-size="10" fill="var(--rpt-ink)">{_e(ln)}</text>')
        xs = [xat(od(r[k])) for k in ('baseline_iso', 'prev_iso', 'curr_iso') if r.get(k)]
        if len(xs) >= 2:
            parts.append(f'<line x1="{min(xs):.0f}" y1="{y:.0f}" x2="{max(xs):.0f}" y2="{y:.0f}" stroke="var(--rpt-chart-grid)"/>')
        if r.get('baseline_iso'):
            parts.append(f'<circle cx="{xat(od(r["baseline_iso"])):.0f}" cy="{y:.0f}" r="4" fill="var(--rpt-bg)" stroke="var(--rpt-muted)" stroke-width="1.8"/>')
        if r.get('prev_iso'):
            parts.append(f'<circle cx="{xat(od(r["prev_iso"])):.0f}" cy="{y:.0f}" r="3.6" fill="var(--rpt-warn)"/>')
        if r.get('curr_iso'):
            parts.append(f'<circle cx="{xat(od(r["curr_iso"])):.0f}" cy="{y:.0f}" r="4" fill="var(--rpt-bad)"/>')
    legend = ('<div class="legend" style="font-size:9.5px"><span><i style="background:var(--rpt-bg);border:2px solid var(--rpt-muted);border-radius:50%;width:9px;height:9px"></i>Baseline'
              + (' · approx' if report.get('baseline_approx') else '') + '</span>'
              '<span><i style="background:var(--rpt-warn);border-radius:50%;width:10px;height:10px"></i>Previous forecast</span>'
              '<span><i style="background:var(--rpt-bad);border-radius:50%;width:10px;height:10px"></i>Current forecast</span></div>')
    return legend + f'<svg viewBox="0 0 700 {h}" width="100%" style="max-height:{h}px">{"".join(parts)}</svg>'



# ── Rate of progress carried forward (round 3, point 06) ───────────────────

def _rate_svg(r):
    d = lambda iso: datetime.strptime(iso, '%Y-%m-%d') if iso else None
    d0, d1 = d(r.get('dd_prev')), d(r.get('dd_now'))
    bf, rf, pf = d(r.get('baseline_finish')), d(r.get('rate_finish')), d(r.get('p6_finish'))
    if not (d0 and d1):
        return ''
    last = max([x for x in (bf, rf, pf) if x] + [d1])
    span = max(1, (last - d0).days)
    W, H, L, Rm, T, B = 1000, 324, 44, 22, 62, 54
    X = lambda dt: L + (W - L - Rm) * (dt - d0).days / span
    Y = lambda p: T + (H - T - B) * (1 - max(0.0, min(100.0, p)) / 100.0)
    acc, warn, bad, good, mut = 'var(--rpt-accent)', 'var(--rpt-warn)', 'var(--rpt-bad)', 'var(--rpt-good)', 'var(--rpt-muted)'
    p = []
    for g in (0, 25, 50, 75, 100):
        p.append(f'<line x1="{L}" y1="{Y(g):.0f}" x2="{W - Rm}" y2="{Y(g):.0f}" stroke="var(--rpt-chart-grid)" stroke-width="1"/>'
                 f'<text x="{L - 6}" y="{Y(g) + 3:.0f}" text-anchor="end" font-size="10" fill="{mut}">{g}%</text>')
    p.append(f'<line x1="{L}" y1="{Y(0):.0f}" x2="{W - Rm}" y2="{Y(0):.0f}" stroke="var(--rpt-chart-axis)" stroke-width="1.5"/>')
    a0, a1 = r.get('actual_prev') or 0.0, r.get('actual_now') or 0.0
    # finish markers — each label on its own line above the chart, so close dates never overlap
    marks = []
    if bf:
        marks.append((bf, mut, f'Baseline finish {r.get("baseline_finish_label")}'))
    if rf:
        dab = r.get('days_after_baseline')
        extra = '' if dab is None else (f' (+{dab} days)' if dab > 0 else (f' ({dab} days)' if dab < 0 else ''))
        marks.append((rf, acc, f'At the current rate {r.get("rate_finish_label")}{extra}'))
    if pf:
        lg = r.get('logic_days')
        extra = '' if not lg else (f' (+{lg} days more — sequence of the critical path)' if lg > 0 else f' ({lg} days)')
        marks.append((pf, bad, f'P6 forecast {r.get("p6_finish_label")}{extra}'))
    marks.sort(key=lambda m: m[0])
    for i, (dt, col, txt) in enumerate(marks):
        x, ty = X(dt), 13 + 15 * i
        anchor = 'end' if x > W * 0.55 else 'start'
        p.append(f'<line x1="{x:.0f}" y1="{ty + 4}" x2="{x:.0f}" y2="{Y(0):.0f}" stroke="{col}" stroke-width="1.4" stroke-dasharray="4 3"/>'
                 f'<text x="{x - 5 if anchor == "end" else x + 5:.0f}" y="{ty}" text-anchor="{anchor}" font-size="11" font-weight="700" fill="{col}">{_e(txt)}</text>')
    # baseline plan (the two cut-offs, then on to the baseline finish)
    pp, pn = r.get('planned_prev'), r.get('planned_now')
    if pn is not None:
        if pp is not None:
            p.append(f'<line x1="{X(d0):.0f}" y1="{Y(pp):.0f}" x2="{X(d1):.0f}" y2="{Y(pn):.0f}" stroke="{warn}" stroke-width="2.5"/>')
        gap = round(pn - a1, 1)
        gtxt = f'baseline plan {pn:.1f}%' + (f' — gap {gap:.1f}%' if gap > 0 else '')
        if gap > 0 and r.get('gap_money'):
            gtxt += f' = {_money(r["gap_money"])}'
        p.append(f'<circle cx="{X(d1):.0f}" cy="{Y(pn):.0f}" r="4" fill="{warn}"/>'
                 f'<text x="{X(d1) + 9:.0f}" y="{Y(pn) - 7:.0f}" font-size="10.5" font-weight="700" fill="{warn}">{_e(gtxt)}</text>')
    # the rate the baseline finish needs
    if bf and bf > d1:
        p.append(f'<line x1="{X(d1):.0f}" y1="{Y(a1):.0f}" x2="{X(bf):.0f}" y2="{Y(100):.0f}" stroke="{good}" stroke-width="2" stroke-dasharray="7 4"/>')
    # the current rate, carried forward
    if rf:
        p.append(f'<line x1="{X(d1):.0f}" y1="{Y(a1):.0f}" x2="{X(rf):.0f}" y2="{Y(100):.0f}" stroke="{acc}" stroke-width="2" stroke-dasharray="7 4"/>'
                 f'<circle cx="{X(rf):.0f}" cy="{Y(100):.0f}" r="4" fill="{acc}"/>')
    # actual between the two updates
    p.append(f'<line x1="{X(d0):.0f}" y1="{Y(a0):.0f}" x2="{X(d1):.0f}" y2="{Y(a1):.0f}" stroke="{acc}" stroke-width="4" stroke-linecap="round"/>'
             f'<circle cx="{X(d0):.0f}" cy="{Y(a0):.0f}" r="4.5" fill="{acc}"/><circle cx="{X(d1):.0f}" cy="{Y(a1):.0f}" r="4.5" fill="{acc}"/>'
             f'<text x="{X(d0) + 2:.0f}" y="{Y(a0) + 17:.0f}" font-size="10.5" font-weight="700" fill="{acc}">{a0:.1f}%</text>'
             f'<text x="{X(d1) + 9:.0f}" y="{Y(a1) + 15:.0f}" font-size="10.5" font-weight="700" fill="{acc}">'
             f'{a1:.1f}% ({_svar(r.get("rate_pct"), "%")} in {r.get("period_days")} days)</text>')
    # the months along the time axis — a tick at every month start, the month named under its span
    segs, y, m = [], d0.year, d0.month
    while datetime(y, m, 1) < last:
        a = datetime(y, m, 1)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        segs.append((max(a, d0), min(datetime(y, m, 1), last), a.strftime('%b.%Y'), a > d0))
    step = max(1, -(-len(segs) * 58 // (W - L - Rm)))
    for i, (a, b, txt, tick) in enumerate(segs):
        if tick:
            p.append(f'<line x1="{X(a):.0f}" y1="{Y(0):.0f}" x2="{X(a):.0f}" y2="{Y(0) + 6:.0f}" stroke="var(--rpt-chart-axis)" stroke-width="1.2"/>')
        if i % step == 0 and X(b) - X(a) >= 36:
            p.append(f'<text x="{(X(a) + X(b)) / 2:.0f}" y="{H - B + 15}" text-anchor="middle" font-size="10.5" font-weight="700" fill="{mut}">{txt}</text>')
    # the two data dates, under the months
    p.append(f'<text x="{X(d0) - 4:.0f}" y="{H - B + 30}" font-size="10" fill="{mut}">▲ {_e(r.get("dd_prev_label"))}</text>'
             f'<text x="{X(d1) - 4:.0f}" y="{H - B + 44}" font-size="10" fill="{mut}">▲ {_e(r.get("dd_now_label"))} · current data date</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-height:{H}px">{"".join(p)}</svg>'


def _rate_html(report):
    r = report.get('rate_outlook')
    if not r:
        return ''
    from p6_export.auto_parts import wrap_part as _part
    cost, days = r.get('by_cost'), r.get('period_days')
    rate, plan = r.get('rate_pct') or 0.0, r.get('planned_pct')
    if cost:
        intro = (f'Between the two updates ({days} calendar days) the project earned <b>{_money(r.get("rate_money"))} = {rate:.1f}%</b> — '
                 f'against {_money(r.get("planned_money"))} = {_num(plan, "%")} in the baseline plan for the same days. '
                 'The chart carries that rate forward.')
    else:
        intro = (f'Between the two updates ({days} calendar days) the project earned <b>{rate:.1f}%</b> — against '
                 f'{_num(plan, "%")} planned for the same days. The chart carries that rate forward.')
    sw = lambda col, dash=False: (f'<i style="background:{"none" if dash else col};'
                                  f'{"border-top:3px dashed " + col + ";height:0;" if dash else "height:4px;"}width:22px"></i>')
    legend = ('<div class="legend">'
              f'<span>{sw("var(--rpt-accent)")}Actual between the two updates</span>'
              f'<span>{sw("var(--rpt-accent)", True)}Carried forward at the current rate</span>'
              f'<span>{sw("var(--rpt-good)", True)}Rate needed to finish on the baseline date</span>'
              f'<span>{sw("var(--rpt-warn)")}Baseline plan</span>'
              f'<span>{sw("var(--rpt-bad)", True)}P6 forecast finish</span></div>')

    def tile(k, v, f, cls=''):
        return f'<div class="fact"><div class="fl">{k}</div><div class="fv {cls}">{v}</div><div class="fs">{f}</div></div>'
    daily = r.get('daily_money')
    lost = r.get('days_lost')
    if cost:
        t1 = f'{_money_short(r.get("rate_money") or 0)} per {days} days = {_money_short(daily or 0)} per day'
        t2 = (f'Shortfall {_money(r.get("shortfall_money"))} against the plan ÷ {_money_short(daily or 0)} per day'
              if (lost or 0) > 0 else 'The period earned what the plan asked for')
    else:
        t1 = f'{r.get("daily_pct")}% per day'
        t2 = ('Shortfall against the plan ÷ the rate per day' if (lost or 0) > 0 else 'The period earned what the plan asked for')
    dab = r.get('days_after_baseline')
    t3 = (f'{r.get("remaining_pct")}% still to earn ÷ {rate:.1f}% per {days} days = {r.get("days_to_go")} days'
          + ('' if dab is None else (f' · {dab} days after the baseline' if dab > 0
                                     else (f' · {-dab} days before the baseline' if dab < 0 else ' · on the baseline date')))
          ) if r.get('rate_finish_label') else 'No progress was earned in this period — no date can be projected'
    req, more = r.get('required_pct'), r.get('required_more_pct')
    t4 = ((f'{_money_short(r["required_money"])} per {days} days' if r.get('required_money') else f'per {days} days')
          + ('' if more is None else (f' — {more}% more than now' if more > 0 else ' — the present rate is enough')))
    tiles = ('<div class="facts" style="grid-template-columns:repeat(4,1fr);margin-top:8px">'
             + tile('Current rate', f'{rate:.1f}% / period', t1)
             + tile('Time lost this period', f'{max(lost or 0, 0)} days', t2, 'neg' if (lost or 0) > 0 else '')
             + tile('Finish at this rate', _e(r.get('rate_finish_label') or '—'), t3)
             + tile(f'Rate needed for {_e(r.get("baseline_finish_label") or "the baseline finish")}',
                    f'{req:.1f}% / period' if req is not None else '—',
                    t4 if req is not None else 'The baseline finish has already passed', 'neg' if (more or 0) > 0 else '')
             + '</div>')
    lg, rf, pf = r.get('logic_days'), r.get('rate_finish_label'), r.get('p6_finish_label')
    read = ''
    if rf and pf and (lg or 0) > 0:
        read = (f'Volume of work alone would finish on <b>{_e(rf)}</b>, but P6 forecasts <b>{_e(pf)}</b>: the extra {lg} days come from '
                'the <b>sequence of the critical activities</b>, not from the amount of work. So recovery needs both — a higher rate '
                'and shortening the critical chain. ')
    elif rf and pf and (lg or 0) < 0:
        read = (f'P6 forecasts <b>{_e(pf)}</b>, {-lg} days before the date the present rate gives ({_e(rf)}): the remaining work is '
                'planned at a faster rate than this period achieved — the forecast holds only if the rate rises. ')
    read += ('Rate = ' + ('Earned Value variance' if cost else '% complete variance')
             + ' ÷ calendar days between the two data dates; it assumes the same rate continues.')
    how = f'<div class="defs"><div class="defs-h">How to read it</div><div class="def">{read}</div></div>'
    return (f'<p class="note" style="margin-top:0;font-style:normal">{intro}</p>'
            + '<div class="chart keep" data-part="rate.chart" data-part-label="Rate of progress — chart">'
            + legend + _rate_svg(r) + '</div>'
            + _part('rate.tiles', 'Rate of progress — the four figures', tiles)
            + _part('rate.reading', 'Rate of progress — how to read it', how))


# ── Conclusion and recommended actions (round 3, point 10) ─────────────────

def advice_pm_items(adv, group=None):
    """The Project Manager list — the fronts follow the activity code chosen in the progress chart."""
    adv = adv or {}
    fr = adv.get('pm_fronts') or {}
    g = group if group in fr else adv.get('front_type')
    if 'pm_head' not in adv:
        return adv.get('project_manager') or []
    return (adv.get('pm_head') or []) + (fr.get(g) or []) + (adv.get('pm_tail') or [])


def _advice_html(report, group=None):
    adv = report.get('advice')
    if not adv:
        return ''
    from p6_export.auto_parts import wrap_part as _part
    tone = {'bad': 'neg', 'good': 'pos'}
    tiles = ('<div class="facts" style="grid-template-columns:repeat(4,1fr);margin-top:4px">' + ''.join(
        f'<div class="fact"><div class="fl">{_e(t.get("label"))}</div><div class="fv {tone.get(t.get("tone"), "")}">{_e(t.get("value"))}</div>'
        f'<div class="fs">{_e(t.get("sub"))}</div></div>' for t in adv.get('tiles') or []) + '</div>')

    def col(title, items, cls):
        return (f'<div class="adv {cls}"><div class="adv-h">{title}</div>' + ''.join(
            f'<div class="adv-i"><b>{i} · {_e(it.get("title"))}</b><div>{_e(it.get("text"))}</div></div>'
            for i, it in enumerate(items, 1)) + '</div>')
    return (_part('advice.tiles', 'Conclusion — the four figures', tiles)
            + _part('advice.top', 'Conclusion — for Top Management', col('For Top Management', adv.get('top_management') or [], 'tm'))
            + _part('advice.pm', 'Conclusion — for the Project Manager',
                    col('For the Project Manager', advice_pm_items(adv, group), 'pm'))
            + f'<p class="note">{_e(adv.get("rules"))} The wording adapts to the result of each pair of updates.</p>')


_SECTION_LABELS = [
    ('verdict', 'Status verdict'), ('progress', 'Progress chart'),
    ('earned_value', 'Earned Value — before, after and variance'),
    ('dashboard', 'Execution Dashboard'), ('recommendation', 'Management recommendation'),
    ('critical_compare', 'Critical-path comparison'), ('critical', 'Critical-path movement (summary + table)'),
    ('progress_table', 'Progress by activity'), ('watch', 'Activities to watch before the next update'),
    ('whatmoved', 'What moved this period'), ('bycode', 'Progress by activity code'),
    ('milestones', 'Milestones (table + chart)'), ('conclusions', 'Conclusions'),
    ('rate', 'Rate of progress and where it lands'), ('advice', 'Conclusion and recommended actions'),
]


NO_VALUE = '(no value)'


def _cf_parts(cf):
    """(code type, set of picked values) of a code filter. `values` = the picked values of
    one activity code (or of 'WBS'); the older single `value` still reads."""
    if not cf or not cf.get('type'):
        return None, set()
    vals = cf.get('values')
    if vals is None:
        vals = [cf.get('value')] if cf.get('value') else []
    return cf['type'], {v for v in vals if v not in (None, '')}


def _cf_match(r, t, vals):
    if t == 'WBS':
        if 'wbs' not in r:
            return True                     # an older saved result: the row carries no WBS to test
        return (r.get('wbs') or NO_VALUE) in vals
    return ((r.get('codes') or {}).get(t) or NO_VALUE) in vals


def _cf_text(cf):
    t, vals = _cf_parts(cf)
    if not t or not vals:
        return ''
    vs = sorted(vals, key=str)
    return f'{t}: ' + ', '.join(str(v) for v in vs[:6]) + (f' … (+{len(vs) - 6} more)' if len(vs) > 6 else '')


def _apply_code_filter(report, cf):
    """Return the report narrowed to the picked values of one activity code (so the exports
    follow the on-screen picker): the activities that moved, the watch list, the critical-path
    movement (rows AND counts) and the relationship changes. The Earned Value by code table
    follows the same pick. Project-level aggregates are left whole."""
    t, vals = _cf_parts(cf)
    if not t:
        return report
    out = dict(report)
    out['ev_code_type'] = t
    if not vals:
        return out
    out['code_filter'] = {'type': t, 'values': sorted(vals, key=str)}
    if len(vals) == 1:
        out['code_filter']['value'] = next(iter(vals))
    for key in ('progress', 'watch_list'):
        sec = report.get(key) or {}
        out[key] = dict(sec, rows=[r for r in (sec.get('rows') or []) if _cf_match(r, t, vals)])
    cm = report.get('critical_movement') or {}
    rows = [r for r in (cm.get('rows') or []) if _cf_match(r, t, vals)]
    new = sum(1 for r in rows if r.get('critical_status') == 'new')
    cm2 = dict(cm, rows=rows, new_critical=new, critical_now=len(rows), stayed=len(rows) - new)
    if 'left_rows' in cm:
        left = [r for r in (cm.get('left_rows') or []) if _cf_match(r, t, vals)]
        cm2.update(left_rows=left, left=len(left), left_finished=sum(1 for r in left if r.get('reason') == 'Finished'),
                   critical_prev=len(rows) - new + len(left))
    out['critical_movement'] = cm2
    out['logic_changes'] = [r for r in (report.get('logic_changes') or []) if _cf_match(r, t, vals)]
    return out


apply_code_filter = _apply_code_filter


def render_html(report, trend=None, sections=None, code_filter=None,
                critical_style='chain', critical_mode='leaf-parent', theme='light', critical_group=None,
                bycode_group=None):
    """`sections` = list of section keys to include (None = all); `code_filter` =
    {'type','value'} to limit the activity tables to one activity code; `critical_style`
    (chain | timeline | table) + `critical_mode` = the critical-path presentation the user
    picked (carried from the screen so the PDF matches); `critical_group` = the one or two
    groupings (WBS / an activity code) of the critical-movement summary charts. Every section is tagged
    <section data-sec="KEY"> so the preview can toggle it and the PDF re-flows."""
    report = _apply_code_filter(report, code_filter)
    level, head, detail = _verdict(report)
    header = (f'<div class="rh"><div><h1>Update vs Update — Period Report</h1>'
              f'<div class="meta">{_e(report.get("project_name"))} · period comparison (Windows Analysis)</div>'
              + (f'<div class="meta">Baseline: {_e(report.get("baseline_label"))}</div>'
                 if report.get('baseline_approx') and report.get('baseline_label') else '')
              + '</div>'
              f'<div class="win">Reporting window<br><b>{_e(report.get("data_date_prev"))} → {_e(report.get("data_date_now"))}</b>'
              f'<br>previous cutoff → current cutoff</div></div>')
    banner = (f'<div class="banner {level}"><span class="dot {level}"></span>'
              f'<div><div class="b1">{_e(head)}</div><div class="b2">{_e(detail)}</div></div></div>')
    # the single parts of a section, named for the Report Contents picker (owner comment 1)
    from p6_export.auto_parts import wrap_part as _part
    dashboard = (_part('dashboard.exec', 'Execution dashboard — previous → current', _exec_dashboard_html(report))
                 + _part('dashboard.recovery', 'Recovery outlook', _recovery_html(report))
                 + _part('dashboard.facts', 'Key facts of the period', _facts_html(report))
                 + _part('dashboard.defs', 'What these numbers mean', _defs_html()))
    milestones = ('<div class="keep">'
                  + _part('milestones.table', 'Milestones — table', _milestone_table_html(report))
                  + '<div class="chart" style="margin-top:8px" data-part="milestones.chart" '
                    'data-part-label="All finish milestones — drift chart">'
                  + f'{_milestone_drift_svg(report)}</div></div>')
    # the full table is not printed any more (owner, round 3): it stays in the Word export —
    # the server shows the `word-only` block when it writes the .docx — and in Excel
    critical = (_part('critical.summary', 'Critical-path movement — summary in charts', _critical_summary_html(report, critical_group))
                + _part('critical.logic', 'Relationships changed — what changed for each activity', _logic_html(report))
                + '<div class="word-only"><h3>Critical-path movement — full table</h3>' + _critical_table_html(report) + '</div>')
    cft = _cf_text(report.get('code_filter'))
    inc = f'<div class="cutoff">Included: <b>{_e(cft)}</b></div>' if cft else ''
    cost = _by_cost(report)
    secs = [
        ('verdict', '', banner, False),
        ('progress', ("Performance % — where you are vs where you said you'd be" if cost
                      else "Progress — where you are vs where you said you'd be"), _progress_bar_html(report), False),
        ('earned_value', 'Earned Value — before, after and variance', _ev_html(report), False),
        ('rate', 'Rate of progress and where it lands', _rate_html(report), False),
        ('dashboard', 'Execution Dashboard — Previous → Current, at each cutoff', dashboard, False),
        ('recommendation', 'What management needs to know', f'<div class="reco warn">{_e(report.get("project_conclusion"))}</div>', False),
        ('critical_compare', 'Critical-path comparison — the finish-driving route', _critical_compare_html(report, critical_style, critical_mode), True),
        ('critical', 'Critical-path movement in this window', inc + critical, False),
        ('progress_table', 'Progress by activity — % complete this period', inc + _progress_table_html(report), False),
        ('watch', 'Activities to watch before the next update', _watch_table_html(report), False),
        ('whatmoved', 'What moved this period — planned vs actual', _whatmoved_html(report), False),
        ('bycode', "Where this period's progress came from — by activity code", _bycode_html(report, bycode_group), False),
        ('milestones', 'Milestones — project completion & all finish milestones', milestones, False),
        ('conclusions', 'Executive conclusion — this period', f'<div class="reco">{_e(report.get("conclusion"))}</div>', False),
        ('advice', 'Conclusion and recommended actions', _advice_html(report, bycode_group), False),
    ]
    keys = set(sections) if sections else None
    cf = report.get('code_filter')
    body = [header]
    if cf:
        body.append(f'<div class="cutoff" style="background:var(--rpt-accent-soft);border-color:var(--rpt-accent-soft);color:var(--rpt-accent)">'
                    f'<b>Filtered:</b> <b>{_e(cft)}</b> — the activities that moved, the Earned Value by code and the '
                    'critical-path movement below show only these.</div>')
    for key, title, html, planner in secs:
        if keys is not None and key not in keys:
            continue
        if key in ('earned_value', 'rate', 'advice') and not html:   # nothing to show (no cost / an older saved result)
            continue
        t = f'<h2>{_e(title)}</h2>' if title else ''
        body.append(f'<section data-sec="{key}"{" class=pagebreak" if planner else ""}>{t}{html}</section>')
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 11mm; }}
      section.pagebreak {{ page-break-before: always; }}
      .prog {{ border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 28px 16px 12px; }}
      .cap {{ display: flex; justify-content: space-between; font-size: 10px; color: var(--rpt-muted); margin-bottom: 12px; }}
      .tag-above {{ position: absolute; top: -22px; transform: translateX(-50%); white-space: nowrap; font-size: 10px; font-weight: 700; color: var(--rpt-warn); }}
      .tag-below {{ position: absolute; top: 36px; transform: translateX(-50%); white-space: nowrap; font-size: 10px; font-weight: 700; color: var(--rpt-accent); }}
      .psent {{ margin-top: 34px; font-size: 11.5px; background: var(--rpt-surface); border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 8px 12px; line-height: 1.5; }}
      .wmrow {{ display: flex; align-items: center; gap: 10px; margin: 6px 0; }} .wml {{ width: 96px; font-size: 11.5px; font-weight: 600; }}
      .wmtrack {{ flex: 1; position: relative; height: 18px; }}
      .wmp {{ position: absolute; left: 0; top: 0; height: 100%; background: var(--rpt-surface-2); border: 1px solid var(--rpt-edge); border-radius: 5px; }}
      .wma {{ position: absolute; left: 0; top: 2px; height: 14px; border-radius: 4px; }}
      .wma.g {{ background: var(--rpt-good); }} .wma.b {{ background: var(--rpt-bad); }} .wma.w {{ background: var(--rpt-warn); }} .wma.n {{ background: var(--rpt-muted); }}
      .wmnum {{ width: 118px; font-size: 11px; color: var(--rpt-ink-soft); }} .wmnum b {{ font-size: 12px; }}
      .cprow {{ display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin: 6px 0; }}
      .cplbl {{ width: 62px; font-size: 10.5px; font-weight: 700; color: var(--rpt-muted); text-transform: uppercase; letter-spacing: .3px; }}
      .wbs {{ border-radius: 8px; padding: 6px 12px; font-size: 11.5px; font-weight: 700; }}
      .wbs.same {{ background: var(--rpt-accent-soft); border: 1px solid var(--rpt-accent-soft); color: var(--rpt-accent); }}
      .wbs.new {{ background: var(--rpt-bad-bg); border: 1px solid var(--rpt-bad); color: var(--rpt-bad); }}
      .wbs.gone {{ background: var(--rpt-surface-2); border: 1px dashed var(--rpt-edge); color: var(--rpt-muted); text-decoration: line-through; }}
      .arr {{ color: var(--rpt-muted); font-weight: 800; }} .arr.newarr {{ color: var(--rpt-bad); }}
      .cplegend {{ font-size: 10.5px; color: var(--rpt-muted); margin-top: 7px; }} .cplegend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; vertical-align: middle; margin: 0 5px 0 12px; }}
      .cpconcl {{ border-radius: 8px; padding: 10px 14px; font-size: 12.5px; line-height: 1.5; margin-bottom: 13px; display: flex; gap: 9px; align-items: flex-start; }}
      .cpconcl.good {{ background: var(--rpt-good-bg); color: var(--rpt-good); }} .cpconcl.warn {{ background: var(--rpt-warn-bg); color: var(--rpt-warn); }}
      .cpconcl .cpic {{ font-size: 15px; line-height: 1.2; }}
      .cprowlbl {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .4px; color: var(--rpt-muted); margin: 2px 0 5px; }}
      /* the chain WRAPS onto a second line when the page is narrower than the chain (the Reporting
         Studio's portrait page: a 1 000 px chain overflowed the 688 px page and Chrome shrank the
         WHOLE document to 67 %); a block grows in height so its full name shows, never cut */
      .cpchain {{ display: flex; align-items: stretch; flex-wrap: wrap; row-gap: 6px; margin-bottom: 4px; }}
      .cpblk {{ flex: none; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 44px; border-radius: 7px; font-weight: 700; font-size: 11px; line-height: 1.15; padding: 3px 5px; text-align: center; overflow-wrap: anywhere; break-inside: avoid; }}
      .cpblk small {{ font-weight: 600; font-size: 9px; opacity: .85; margin-top: 1px; }}
      .cpblk.shared {{ background: var(--rpt-accent-soft); color: var(--rpt-accent); }} .cpblk.new {{ background: var(--rpt-bad-bg); color: var(--rpt-bad); }} .cpblk.gone {{ background: var(--rpt-surface-2); color: var(--rpt-muted); text-decoration: line-through; }}
      .cparw {{ flex: none; display: flex; align-items: center; color: var(--rpt-muted); font-weight: 900; font-size: 14px; padding: 0 4px; }} .cparw.new {{ color: var(--rpt-bad); }}
      .cpflag {{ flex: none; display: flex; flex-direction: column; justify-content: center; padding-left: 9px; white-space: nowrap; }}
      .cpflag b {{ font-size: 12px; }} .cpflag .cpfl {{ font-size: 9px; color: var(--rpt-muted); text-transform: uppercase; letter-spacing: .3px; }}
      .cpflag.now b {{ color: var(--rpt-bad); }} .cpflag.was b {{ color: var(--rpt-muted); }}
      .cpdia {{ width: 10px; height: 10px; transform: rotate(45deg); border-radius: 2px; margin-bottom: 3px; }} .cpdia.now {{ background: var(--rpt-bad); }} .cpdia.was {{ background: var(--rpt-muted); }}
      .cpslip {{ font-size: 11px; color: var(--rpt-bad); font-weight: 700; margin-top: 3px; }}
      .cptable {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 2px; }}
      .cptable th, .cptable td {{ border: 1px solid var(--rpt-edge); padding: 6px 10px; text-align: left; vertical-align: top; }}
      .cptable th {{ background: var(--rpt-th-bg); color: var(--rpt-th-ink); font-size: 11px; }}
      .cptable td.cpt-k {{ font-weight: 700; color: var(--rpt-muted); width: 130px; white-space: nowrap; }}
      .cptable .cpt-red {{ color: var(--rpt-bad); font-weight: 700; }} .cptable .cpt-mut {{ color: var(--rpt-muted); }}
      .cptable td.cpt-fin {{ font-weight: 700; }}
      .bar2 {{ display: flex; align-items: center; gap: 10px; margin: 5px 0; }} .bar2 .l {{ width: 160px; font-size: 11.5px; }}
      .bar2 .t {{ flex: 1; background: var(--rpt-surface-2); border-radius: 6px; height: 18px; overflow: hidden; border: 1px solid var(--rpt-edge); }}
      .bar2 .f {{ height: 100%; background: var(--rpt-accent); display: flex; align-items: center; padding-left: 8px; color: var(--rpt-accent-ink); font-weight: 700; font-size: 11px; }}
      .bar2r {{ margin: 8px 0; }} .bar2r-h {{ font-size: 12px; margin-bottom: 3px; }} .bar2r-n {{ font-size: 10.5px; color: var(--rpt-muted); margin-top: 2px; }}
      .bar2r-t {{ position: relative; height: 16px; background: var(--rpt-surface-2); border: 1px solid var(--rpt-edge); border-radius: 5px; }}
      .bar2r-pl {{ position: absolute; left: 0; top: 0; height: 100%; background: var(--rpt-surface-2); border: 1px solid var(--rpt-edge); border-radius: 5px; }}
      .bar2r-ac {{ position: absolute; left: 0; top: 2px; height: 10px; background: var(--rpt-accent); border-radius: 4px; }}
      .hbm {{ font-size: 10px; color: var(--rpt-muted); margin: -2px 0 6px; line-height: 1.35; }}
      .slip {{ display: inline-block; border-radius: 9px; padding: 0 7px; margin-left: 4px; font-weight: 700; background: var(--rpt-warn-bg); color: var(--rpt-warn); }}
      .slip.worst {{ background: var(--rpt-bad-bg); color: var(--rpt-bad); }} .slip.none {{ background: var(--rpt-surface-2); color: var(--rpt-muted); font-weight: 600; }}
      .hbs.wide .hbn {{ width: 150px; }}
      .vhist {{ display: flex; align-items: flex-end; gap: 12px; height: 176px; border-bottom: 1.5px solid var(--rpt-chart-axis); padding: 4px 6px 0; }}
      .vg {{ flex: 1; height: 100%; display: flex; align-items: flex-end; justify-content: center; gap: 4px; }}
      .vb {{ width: 44%; max-width: 40px; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; }}
      .vb b {{ font-size: 10px; margin-bottom: 2px; white-space: nowrap; }} .vb b.neg {{ color: var(--rpt-bad); }}
      .vb i {{ display: block; width: 100%; border-radius: 3px 3px 0 0; }} .vb i.pl {{ background: var(--rpt-warn); }} .vb i.ac {{ background: var(--rpt-accent); }}
      .vl-row {{ display: flex; gap: 12px; padding: 4px 6px 0; }} .vl {{ flex: 1; text-align: center; font-size: 10px; color: var(--rpt-ink-soft); overflow-wrap: anywhere; }}
      .adv {{ border: 1px solid var(--rpt-edge); border-left: 4px solid var(--rpt-accent); border-radius: 0 8px 8px 0; padding: 9px 14px; margin-top: 10px; }}
      .adv.tm {{ border-left-color: var(--rpt-warn); }}
      .adv-h {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .4px; font-weight: 800; color: var(--rpt-accent); margin-bottom: 4px; }}
      .adv.tm .adv-h {{ color: var(--rpt-warn); }}
      .adv-i {{ margin: 6px 0; line-height: 1.5; break-inside: avoid; }} .adv-i b {{ font-size: 12px; }} .adv-i div {{ color: var(--rpt-ink-soft); }}
      .word-only {{ display: none; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: system-ui, -apple-system, Arial, sans-serif; color: var(--rpt-ink); font-size: 12px; margin: 0; }}
      .page {{ page-break-after: always; }} .page:last-child {{ page-break-after: auto; }}
      .keep {{ page-break-inside: avoid; }} .chart {{ page-break-inside: avoid; }}
      h1 {{ font-size: 21px; margin: 0 0 2px; }}
      h2, h3, .sub-h {{ break-after: avoid; page-break-after: avoid; }}
      .sub-h {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .35px; color: var(--rpt-muted); font-weight: 700; margin: 12px 0 7px; }}
      .fact .fv.neg {{ color: var(--rpt-bad); }} .fact .fv.pos {{ color: var(--rpt-good); }}
      .hist {{ display: flex; align-items: flex-end; gap: 10px; height: 118px; border-bottom: 1.5px solid var(--rpt-chart-axis); padding: 16px 6px 0; }}
      .hcol {{ flex: 1; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; }}
      .hcol b {{ font-size: 11.5px; margin-bottom: 2px; }} .hcol i {{ display: block; width: 100%; background: var(--rpt-accent); border-radius: 4px 4px 0 0; }}
      .hl {{ display: flex; gap: 10px; padding: 3px 6px 0; }} .hl span {{ flex: 1; text-align: center; font-size: 10px; color: var(--rpt-muted); }}
      .hb {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; break-inside: avoid; }}
      .hbl {{ width: 34%; font-size: 11px; overflow-wrap: anywhere; }}
      .hbt {{ flex: 1; height: 14px; background: var(--rpt-surface-2); border: 1px solid var(--rpt-edge); border-radius: 4px; overflow: hidden; }}
      .hbt i {{ display: block; height: 100%; background: var(--rpt-accent); }} .hbt i.w {{ background: var(--rpt-warn); }}
      .hbn {{ width: 92px; font-size: 11px; color: var(--rpt-ink-soft); text-align: right; white-space: nowrap; }}
      .stylecards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; }}
      .stylecard {{ border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 8px 11px; }}
      .stylecard.sel {{ border: 2px solid var(--rpt-accent); background: var(--rpt-surface); }}
      .sc-h {{ font-size: 12px; font-weight: 800; margin-bottom: 4px; }}
      .sc-on {{ float: right; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .3px; color: var(--rpt-accent); }}
      h2 {{ font-size: 14px; margin: 16px 0 8px; color: var(--rpt-accent); border-bottom: 2px solid var(--rpt-accent); padding-bottom: 4px; }}
      h3 {{ font-size: 12.5px; margin: 10px 0 6px; color: var(--rpt-accent); }}
      .rh {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid var(--rpt-accent); padding-bottom: 10px; margin-bottom: 12px; }}
      .rh .meta {{ color: var(--rpt-muted); font-size: 11.5px; }} .rh .win {{ text-align: right; font-size: 11.5px; color: var(--rpt-muted); }} .rh .win b {{ color: var(--rpt-ink); font-size: 13px; }}
      .banner {{ display: flex; gap: 12px; align-items: center; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }}
      .banner.good {{ background: var(--rpt-good-bg); border: 1px solid var(--rpt-good); }}
      .banner.warn {{ background: var(--rpt-warn-bg); border: 1px solid var(--rpt-warn); }}
      .banner.bad {{ background: var(--rpt-bad-bg); border: 1px solid var(--rpt-bad); }}
      .dot {{ width: 13px; height: 13px; border-radius: 50%; flex: none; }}
      .dot.good {{ background: var(--rpt-good); }} .dot.warn {{ background: var(--rpt-warn); }} .dot.bad {{ background: var(--rpt-bad); }}
      .banner .b1 {{ font-size: 15px; font-weight: 800; }} .banner .b2 {{ font-size: 12px; color: var(--rpt-ink-soft); }}
      .cutoff {{ color: var(--rpt-ink-soft); font-size: 12px; margin: 2px 0 8px; }}
      .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; }}
      .card {{ border: 1px solid var(--rpt-edge); border-radius: 8px; overflow: hidden; }}
      .card .ct {{ background: var(--rpt-surface); border-bottom: 1px solid var(--rpt-edge); padding: 5px 9px; font-size: 9.5px; text-transform: uppercase; letter-spacing: .3px; color: var(--rpt-muted); font-weight: 700; }}
      .card .cb {{ display: grid; grid-template-columns: 1fr 1fr; }}
      .card .cc {{ padding: 6px 9px; }} .card .cc + .cc {{ border-left: 1px solid var(--rpt-edge); }}
      .card .cl {{ font-size: 9px; color: var(--rpt-muted); }} .card .cv {{ font-size: 15px; font-weight: 800; }}
      .card .cf {{ padding: 5px 9px; border-top: 1px solid var(--rpt-edge); font-size: 11.5px; font-weight: 700; text-align: center; }}
      .cf.good {{ background: var(--rpt-good-bg); color: var(--rpt-good); }} .cf.bad {{ background: var(--rpt-bad-bg); color: var(--rpt-bad); }}
      .recov {{ display: grid; grid-template-columns: 1.5fr 1fr; border: 1px solid var(--rpt-warn); border-radius: 8px; overflow: hidden; margin-top: 12px; }}
      .recov .rl {{ padding: 11px 15px; background: var(--rpt-warn-bg); line-height: 1.55; }} .recov .rr {{ padding: 11px 15px; border-left: 1px solid var(--rpt-warn); }}
      .rh4 {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .4px; color: var(--rpt-warn); font-weight: 700; margin-bottom: 4px; }}
      .rr-h {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .4px; color: var(--rpt-accent); font-weight: 700; }}
      .rr-big {{ font-size: 14px; font-weight: 800; margin: 3px 0; }}
      .rr-v {{ font-size: 12px; font-weight: 700; }} .rr-v.bad {{ color: var(--rpt-bad); }} .rr-v.good {{ color: var(--rpt-good); }} .rr-v.warn {{ color: var(--rpt-warn); }}
      .facts {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; margin-top: 12px; }}
      .fact {{ border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 8px 11px; }}
      .fact .fl {{ font-size: 9.5px; color: var(--rpt-muted); text-transform: uppercase; letter-spacing: .3px; }} .fact .fv {{ font-size: 15px; font-weight: 800; margin-top: 1px; }} .fact .fs {{ font-size: 10px; color: var(--rpt-muted); }}
      .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 8px; }}
      .chart {{ border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 8px; }}
      table.data {{ width: 100%; border-collapse: collapse; font-size: 10.5px; margin: 6px 0; }}
      table.data th {{ background: var(--rpt-th-bg); color: var(--rpt-th-ink); text-align: left; padding: 5px 6px; font-weight: 600; }}
      table.data th.num {{ text-align: right; }}
      table.data td {{ border-bottom: 1px solid var(--rpt-edge); padding: 4px 6px; vertical-align: top; }}
      .mono {{ font-family: Consolas, monospace; }} .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
      .pos {{ color: var(--rpt-good); font-weight: 700; }} .neg {{ color: var(--rpt-bad); font-weight: 700; }}
      .note {{ color: var(--rpt-muted); font-style: italic; }}
      .pills {{ margin: 4px 0; }} .pill {{ display: inline-block; background: var(--rpt-accent-soft); color: var(--rpt-accent); border-radius: 12px; padding: 2px 10px; font-size: 11px; margin: 0 6px 6px 0; }}
      .legend {{ font-size: 11px; color: var(--rpt-muted); margin: 4px 0; }} .legend span {{ margin-right: 16px; }} .legend i {{ display: inline-block; width: 16px; height: 3px; vertical-align: middle; margin-right: 5px; }}
      .reco {{ border: 1px solid var(--rpt-edge); border-left: 4px solid var(--rpt-accent); border-radius: 0 8px 8px 0; padding: 10px 14px; line-height: 1.6; }}
      .reco.warn {{ border-left-color: var(--rpt-warn); }}
      .pbwrap {{ margin: 4px 0; }} .pbtop {{ display: flex; justify-content: space-between; font-size: 10.5px; color: var(--rpt-muted); margin-bottom: 15px; }}
      .pbar {{ position: relative; height: 30px; background: var(--rpt-surface-2); border-radius: 8px; border: 1px solid var(--rpt-edge); }}
      .pfill {{ position: absolute; left: 0; top: 0; bottom: 0; background: var(--rpt-accent); border-radius: 7px 0 0 7px; display: flex; align-items: center; justify-content: flex-end; padding-right: 9px; color: var(--rpt-accent-ink); font-weight: 800; font-size: 12px; }}
      .pmark {{ position: absolute; top: -5px; bottom: -5px; width: 3px; background: var(--rpt-warn); }}
      .pmark .lab {{ position: absolute; top: -16px; left: 50%; transform: translateX(-50%); white-space: nowrap; font-size: 10px; color: var(--rpt-warn); font-weight: 700; }}
      .pbbot {{ text-align: center; font-size: 11.5px; color: var(--rpt-ink-soft); margin-top: 5px; }}
      .twobar {{ margin-top: 12px; }} .tb {{ display: flex; align-items: center; gap: 10px; margin: 5px 0; }}
      .tb .lbl {{ width: 170px; font-size: 11.5px; color: var(--rpt-muted); }}
      .tb .track {{ flex: 1; background: var(--rpt-surface-2); border-radius: 6px; height: 19px; overflow: hidden; border: 1px solid var(--rpt-edge); }}
      .tb .fillp {{ height: 100%; background: var(--rpt-warn); display: flex; align-items: center; padding-left: 8px; color: var(--rpt-accent-ink); font-weight: 700; font-size: 11px; }}
      .tb .filla {{ height: 100%; background: var(--rpt-accent); display: flex; align-items: center; padding-left: 8px; color: var(--rpt-accent-ink); font-weight: 700; font-size: 11px; }}
      .chartlegend {{ margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--rpt-edge); font-size: 11px; color: var(--rpt-ink-soft); line-height: 1.6; }}
      .chartlegend > div {{ margin: 2px 0; }} .lg-sw {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: middle; margin-right: 7px; }}
      .defs {{ margin-top: 12px; background: var(--rpt-surface); border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 10px 14px; }}
      .defs-h {{ font-size: 10px; text-transform: uppercase; letter-spacing: .4px; color: var(--rpt-muted); font-weight: 700; margin-bottom: 5px; }}
      .def {{ font-size: 11px; color: var(--rpt-ink-soft); line-height: 1.5; margin: 2px 0; }} .def b {{ color: var(--rpt-ink); }}
    </style>{report_theme.theme_style_tag(theme)}</head><body>{"".join(body)}</body></html>'''


# ── Excel: mirrors the PDF, one sheet ───────────────────────────────────────

_PROGRESS_HEADERS = ['S/N', 'Activity ID', 'Activity name', 'Status', 'Previous %', 'Current %', 'Variance']
_CRITICAL_HEADERS = ['S/N', 'Activity ID', 'Activity name', 'Finish (prev)', 'Finish (now)',
                     'Slip (wd)', 'Total Float (wd)', 'Driver', 'Critical']
_WATCH_HEADERS = ['S/N', 'Activity ID', 'Activity name', 'Due to start', 'Total Float (wd)', 'Why it is listed']


def _code_cells(row, code_types):
    """One cell per activity-code dimension — the activity's value (blank if none),
    so the exported tables can be filtered / pivoted by any activity code in Excel."""
    codes = row.get('codes') or {}
    return [codes.get(t, '') for t in code_types]


def _xl_sign(v, suffix=''):
    """Signed cell with an arrow, so the Excel keeps the up/down indication (▲ +12%)."""
    if v is None:
        return ''
    if v > 0:
        return f'▲ +{v}{suffix}'
    if v < 0:
        return f'▼ {v}{suffix}'
    return f'{v}{suffix}'


def _progress_rows(report, code_types=()):
    out = []
    for r in (report.get('progress', {}) or {}).get('rows', []):
        status = r.get('status', '') + (' (reversed)' if r.get('reversal') else '')
        out.append([len(out) + 1, r.get('activity_id', ''), r.get('activity_name', ''), status,
                    f"{r.get('prev_pct', 0)}%", f"{r.get('curr_pct', 0)}%",
                    _xl_sign(r.get('variance', 0), '%')]
                   + _code_cells(r, code_types))
    return out


def _critical_rows(report, code_types=()):
    out = []
    for r in (report.get('critical_movement', {}) or {}).get('rows', []):
        slip = r.get('slip_days') or 0
        out.append([len(out) + 1, r.get('activity_id', ''), r.get('activity_name', ''),
                    r.get('prev_finish', ''), r.get('curr_finish', ''),
                    _xl_sign(slip, ' wd') if slip else '', r.get('float_days', ''),
                    r.get('driver', ''), ('new' if r.get('critical_status') == 'new' else 'stayed')]
                   + _code_cells(r, code_types))
    return out


def _watch_rows(report, code_types=()):
    out = []
    for r in (report.get('watch_list', {}) or {}).get('rows', []):
        out.append([len(out) + 1, r.get('activity_id', ''), r.get('activity_name', ''),
                    r.get('due_to_start', ''), r.get('float_days', ''), r.get('reason', '')]
                   + _code_cells(r, code_types))
    return out


def progress_excel(report):
    """(headers, rows) for the Progress-by-activity % variance table (single section)."""
    ct = report.get('code_types', []) or []
    return _PROGRESS_HEADERS + list(ct), _progress_rows(report, ct)


def report_excel(report, trend=None):
    """(headers, rows) for a single sheet that MIRRORS the PDF, section for section:
    status, Execution Dashboard, recovery, key facts, progress, critical movement, watch
    list, what-moved, milestone trend, and both conclusions. Single-sheet writer, no
    p6_evm change."""
    s = report.get('summary', {}) or {}
    rec = report.get('recovery', {}) or {}
    adh = report.get('schedule_adherence', {}) or {}
    counts = (report.get('buckets', {}) or {}).get('counts', {})
    level, head, detail = _verdict(report)

    headers = ['Update vs Update — Period Report', report.get('project_name', ''),
               f"{report.get('data_date_prev', '')} → {report.get('data_date_now', '')}", '', '', '', '', '']
    rows = [[f'STATUS — {head}'], [detail], ['']]

    rows += [['Execution Dashboard', 'Previous', 'Current', 'Variance'],
             [_pct_title(report), _pctcell(s.get('actual_prev')), _pctcell(s.get('actual_now')), _svar(s.get('period_earned'), '%')],
             ['SPI', _spi_disp(s.get('prev_spi')) if s.get('prev_spi') is not None else '', _spi_disp(s.get('curr_spi')) if s.get('curr_spi') is not None else '', _spi_var_disp(s.get('spi_variance'))],
             ['Delay vs baseline', _num(s.get('delay_prev'), ' wd') if s.get('delay_prev') is not None else '', _num(s.get('delay_now'), ' wd') if s.get('delay_now') is not None else '', _svar(s.get('delay_change'), ' wd')],
             ['Forecast finish', s.get('forecast_finish_prev') or '', s.get('forecast_finish_now') or '',
              (f"slipped {s.get('finish_slip_days')} d" if (s.get('finish_slip_days') or 0) > 0 else '')],
             ['']]

    if _by_cost(report) and s.get('ev_now') is not None:
        f2 = lambda v: round(v, 2) if v is not None else ''
        rows += [['Earned Value — before, after and variance', 'Previous', 'Current', 'Variance'],
                 ['Earned Value', s.get('ev_prev'), s.get('ev_now'), s.get('ev_variance')],
                 ['Planned Value', s.get('pv_prev'), s.get('pv_now'), s.get('pv_variance')],
                 ['Performance % (Earned Value ÷ Budget)', _pctcell(s.get('actual_prev')), _pctcell(s.get('actual_now')), _svar(s.get('period_earned'), '%')],
                 ['Planned %', _pctcell(s.get('planned_prev')), _pctcell(s.get('planned_now')), _svar(s.get('planned_variance'), '%')],
                 ['SPI (Earned Value ÷ Planned Value)', f2(s.get('prev_spi')), f2(s.get('curr_spi')), f2(s.get('spi_variance'))],
                 ['Budget of the cost-loaded activities', s.get('bac_prev'), s.get('bac'), ''],
                 ['Cost-loaded activities', '', f"{s.get('cost_activities')} of {s.get('all_activities')}", ''],
                 ['']]

    rows += [['Recovery outlook'],
             ['Work remaining', _pctcell(rec.get('work_remaining'))],
             ['Earned this period', _pctcell(rec.get('current_rate'))],
             ['Baseline finish' + (' · approx' if report.get('baseline_approx') else ''), rec.get('baseline_finish') or ''],
             ['Required rate to hit baseline', _pctcell(rec.get('required_rate')) + ('/period' if rec.get('required_rate') is not None else '')],
             ['Projected finish at current rate', rec.get('projected_finish') or ''],
             ['Recovery feasible', {True: 'Yes', False: 'No'}.get(rec.get('feasible'), '—')],
             ['Schedule adherence', (f"{adh.get('hit', 0)} of {adh.get('planned', 0)} due finishes hit"
                                     + (f" ({adh.get('pct')}%)" if adh.get('pct') is not None else ''))],
             ['']]

    # Activity-code columns appended to every activity table so the export can be
    # filtered/pivoted by any activity code (Ibrahim's request).
    ct = report.get('code_types', []) or []
    rows += [['Progress by activity — % complete this period'], _PROGRESS_HEADERS + list(ct)] + _progress_rows(report, ct)
    cs = _crit_summary(report)
    if cs.get('total'):
        left = cs.get('left')
        rows += [[''], ['Critical-path movement — summary (Critical = the P6 Critical flag)'],
                 ['Critical now', cs.get('total')], ['Critical in the previous update', '' if cs.get('prev_total') is None else cs.get('prev_total')],
                 ['Stayed critical', cs.get('stayed')], ['New critical', cs.get('new')],
                 ['No longer critical', '' if left is None else left],
                 ['  of which finished', '' if left is None else (cs.get('left_finished') or 0)],
                 [''], ['Slip of the finish this period (working days)', 'Critical activities']]
        rows += [[b['label'], b['count']] for b in cs.get('bands') or []]
        rows += [[''], ['Why they moved', 'Critical activities']] + [[d['label'], d['count']] for d in cs.get('drivers') or []]
        for g in crit_group_choice(cs):
            grp = (cs.get('groups') or {}).get(g) if g else None
            if grp and grp.get('rows'):
                rows += [[''], [f'By {g}', 'Critical activities', 'Worst slip (wd)']]
                rows += [[x['value'], x['count'], x.get('max_slip') or 0] for x in grp['rows']]
    rows += [[''], ['Critical-path movement in this window'], _CRITICAL_HEADERS + list(ct)] + _critical_rows(report, ct)
    rows += [[''], ['Activities to watch before the next update'], _WATCH_HEADERS + list(ct)] + _watch_rows(report, ct)

    rows += [[''], ['What moved this period']]
    for k, lbl in [('finished', 'Finished'), ('started', 'Started'), ('slipped', 'Slipped'),
                   ('stalled', 'Stalled'), ('re_sequenced', 'Re-sequenced')]:
        rows.append([lbl, counts.get(k, 0)])

    mrows = (report.get('milestones', {}) or {}).get('rows', [])
    if mrows:
        rows += [[''], ['Milestones — baseline vs previous vs current forecast'],
                 ['S/N', 'Key milestone', 'Baseline' + (' · approx' if report.get('baseline_approx') else ''),
                  'Previous forecast', 'Current forecast',
                  'Slip this period (wd)', 'Slip vs baseline (wd)' + (' · approx' if report.get('baseline_approx') else '')]]
        for i, m in enumerate(mrows, 1):
            rows.append([i, m.get('name', ''), m.get('baseline_finish', ''), m.get('prev_forecast', ''),
                         m.get('curr_forecast', ''), m.get('slip_period_days', ''), m.get('slip_baseline_days', '')])

    rows += [[''], ['Executive conclusion — this period'], [report.get('conclusion', '')]]
    rows += [[''], ['Project conclusion & outlook'], [report.get('project_conclusion', '')]]
    rows += _excel_round3_rows(report)
    cft = _cf_text(report.get('code_filter'))
    if cft:
        rows = [[f'Filtered — {cft}: the activity tables, the critical-path movement and the Earned Value by code show only these.'],
                ['']] + rows
    return headers, rows


def _excel_round3_rows(report):
    """Rate of progress, relationship changes, Earned Value by the picked code and the
    conclusion's actions — the same figures the PDF prints. Never raises."""
    rows = []
    try:
        r = report.get('rate_outlook')
        if r:
            cost, days = r.get('by_cost'), r.get('period_days')
            x = lambda v: '' if v is None else v
            rows += [[''], ['Rate of progress and where it lands'],
                     ['Days between the two data dates', x(days)],
                     ['Earned in the period (%)', x(r.get('rate_pct'))], ['Planned for the period (%)', x(r.get('planned_pct'))]]
            if cost:
                rows += [['Earned in the period (Earned Value variance)', x(r.get('rate_money'))],
                         ['Planned for the period (Planned Value variance)', x(r.get('planned_money'))],
                         ['Current rate per day', x(r.get('daily_money'))],
                         ['Shortfall against the plan this period', x(r.get('shortfall_money'))]]
            rows += [['Time lost this period (days)', x(r.get('days_lost'))],
                     ['Still to earn (%)', x(r.get('remaining_pct'))],
                     ['Finish at the current rate', x(r.get('rate_finish_label'))],
                     ['Days from the current data date to that finish', x(r.get('days_to_go'))],
                     ['Baseline finish', x(r.get('baseline_finish_label'))],
                     ['Finish at the current rate − baseline finish (days)', x(r.get('days_after_baseline'))],
                     ['P6 forecast finish', x(r.get('p6_finish_label'))],
                     ['P6 forecast − finish at the current rate (days; the sequence of the critical path)', x(r.get('logic_days'))],
                     ['Rate needed for the baseline finish (% per period)', x(r.get('required_pct'))]]
            if cost:
                rows += [['Rate needed for the baseline finish (per period)', x(r.get('required_money'))]]
            rows += [['Rate needed − current rate (%)', x(r.get('required_more_pct'))]]
        lc = report.get('logic_changes') or []
        if lc:
            rows += [[''], ['Relationships changed — the critical activities whose logic was edited between the two updates'],
                     ['S/N', 'Activity ID', 'Activity name', 'Finish (prev)', 'Finish (now)', 'Finish moved (wd)',
                      'What changed in the relationships (previous → current)']]
            rows += [[i, a.get('activity_id', ''), a.get('activity_name', ''), a.get('prev_finish', ''), a.get('curr_finish', ''),
                      '' if a.get('slip_days') is None else a.get('slip_days'), '; '.join(a.get('changes') or [])]
                     for i, a in enumerate(lc, 1)]
        t = report.get('ev_code_type')
        ev = ((report.get('ev_by_code') or {}).get(t) or []) if t else []
        if ev:
            _t, vals = _cf_parts(report.get('code_filter'))
            picked = [e for e in ev if e.get('value') in vals] if vals else ev
            if picked:
                rows += [[''], [f'Earned Value by {t}' + (' — the picked values only' if vals else '')],
                         ['S/N', t, 'Cost-loaded activities', 'Budget', 'Earned Value — previous', 'Earned Value — current', 'Variance',
                          'Performance % — previous', 'Performance % — current', 'Variance %']]
                rows += [[i, e.get('value', ''), e.get('activities', 0), round(e.get('bac') or 0), round(e.get('ev_prev') or 0),
                          round(e.get('ev_now') or 0), round(e.get('variance') or 0)] + _ev_pct_cells(e)
                         for i, e in enumerate(picked, 1)]
                tot = {k: sum(e.get(k) or 0 for e in picked) for k in ('activities', 'bac', 'ev_prev', 'ev_now', 'variance')}
                rows += [['', 'Total'] + [round(tot[k]) for k in ('activities', 'bac', 'ev_prev', 'ev_now', 'variance')]
                         + _ev_pct_cells(tot)]
        adv = report.get('advice')
        if adv:
            rows += [[''], ['Conclusion and recommended actions']]
            rows += [[t_.get('label', ''), t_.get('value', ''), t_.get('sub', '')] for t_ in adv.get('tiles') or []]
            for title, items in (('For Top Management', adv.get('top_management') or []),
                                 ('For the Project Manager', advice_pm_items(adv, report.get('bycode_group')))):
                rows += [[''], [title]] + [[f'{i} · {it.get("title", "")}', it.get('text', '')] for i, it in enumerate(items, 1)]
            rows += [[''], [adv.get('rules', '')]]
    except Exception:
        pass
    return rows


_MOVED_WORDS = (('finished', 'Finished'), ('started', 'Started'), ('slipped', 'Slipped'),
                ('stalled', 'Stalled'), ('re_sequenced', 'Re-sequenced'))


def report_excel_extra_sheets(report):
    """The parts of the Update-vs-Update report the flat first sheet only counts or draws —
    as extra sheets for ``write_sections_xlsx`` (owner comment 29): the S-curve's numbers, the
    progress by EVERY activity code, the critical path in each update, and the activities
    behind each 'what moved' count. A part with no data gets no sheet; never raises."""
    report = report or {}
    sheets = []
    try:
        sc = report.get('scurve') or {}
        periods = sc.get('periods') or []
        if periods:
            fc, ac = sc.get('forecast') or [], sc.get('actual') or []
            marks = {sc.get('dd_prev_idx'): 'Previous data date', sc.get('dd_now_idx'): 'Current data date'}
            pick = lambda xs, i: xs[i] if i < len(xs) and xs[i] is not None else ''
            sheets.append({'name': 'S-Curve', 'blocks': [{
                'title': 'S-curve — cumulative progress by month',
                'note': 'Forecast = the cumulative % the previous update planned; Actual = the cumulative % achieved.',
                'headers': ['Month', 'Forecast cumulative %', 'Actual cumulative %', 'Marker'],
                'rows': [[p, pick(fc, i), pick(ac, i), marks.get(i, '')] for i, p in enumerate(periods)]}]})

        bc = report.get('progress_by_code') or {}
        rows = []
        for code_type, vals in bc.items():
            for v in vals or []:
                pl, act = v.get('planned'), v.get('actual')
                gap = round(act - pl, 1) if isinstance(pl, (int, float)) and isinstance(act, (int, float)) else ''
                rows.append([code_type, v.get('value', ''), '' if pl is None else pl,
                             '' if act is None else act, gap])
        if rows:
            sheets.append({'name': 'Progress by Code', 'blocks': [{
                'title': 'Planned vs actual progress this period, by activity code',
                'note': 'Percent of the whole project, weighted by each activity\'s cost / duration share. '
                        'Actual − planned below zero = behind the plan.',
                'headers': ['Activity code', 'Code value', 'Planned this period %', 'Actual this period %',
                            'Actual − planned %'],
                'rows': rows}]})

        cp = report.get('critical_path') or {}
        blocks = []
        for key, title in (('previous', 'Critical path — previous update'),
                           ('current', 'Critical path — current update')):
            acts = cp.get(key) or []
            if acts:
                blocks.append({'title': title, 'note': f'{len(acts)} activities, in path order.',
                               'headers': ['S/N', 'Activity ID', 'Activity Name', 'WBS', 'Start', 'Finish'],
                               'rows': [[i, a.get('id', ''), a.get('name', ''), a.get('wbs_path', ''),
                                         a.get('start') or '', a.get('finish') or '']
                                        for i, a in enumerate(acts, 1)]})
        if blocks:
            sheets.append({'name': 'Critical Path', 'blocks': blocks})

        lists = (report.get('buckets') or {}).get('lists') or {}
        rows = [[i, lbl, a.get('activity_id', ''), a.get('activity_name', '')]
                for key, lbl in _MOVED_WORDS for i, a in enumerate(lists.get(key) or [], 1)]
        if rows:
            sheets.append({'name': 'What Moved', 'blocks': [{
                'title': 'What moved this period — the activities behind each count',
                'note': 'S/N restarts with each movement.',
                'headers': ['S/N', 'Movement', 'Activity ID', 'Activity Name'], 'rows': rows}]})
        left_rows = (report.get('critical_movement') or {}).get('left_rows') or []
        if left_rows:
            sheets.append({'name': 'No Longer Critical', 'blocks': [{
                'title': 'Critical in the previous update, not critical in the current one',
                'headers': ['S/N', 'Activity ID', 'Activity Name', 'WBS', 'Why', 'Total Float now (wd)'],
                'rows': [[i, a.get('activity_id', ''), a.get('activity_name', ''), a.get('wbs', ''), a.get('reason', ''),
                          '' if a.get('float_days') is None else a.get('float_days')]
                         for i, a in enumerate(left_rows, 1)]}]})
        ev = report.get('ev_by_code') or {}
        rows = [[t, e.get('value', ''), e.get('activities', 0), round(e.get('bac') or 0), round(e.get('ev_prev') or 0),
                 round(e.get('ev_now') or 0), round(e.get('variance') or 0)] + _ev_pct_cells(e)
                for t, vals in ev.items() for e in vals or []]
        if rows:
            sheets.append({'name': 'EV by Code', 'blocks': [{
                'title': 'Earned Value by activity code and by WBS — previous, current, variance',
                'note': 'Cost-loaded activities only — the same activities and the same sum as the report\'s Earned Value. '
                        'Each activity code (and the WBS) adds up to the project total; "(no value)" = activities without that code.',
                'headers': ['Activity code', 'Code value', 'Cost-loaded activities', 'Budget', 'Earned Value — previous',
                            'Earned Value — current', 'Variance', 'Performance % — previous', 'Performance % — current',
                            'Variance %'],
                'rows': rows}]})
        lc = report.get('logic_changes') or []
        if lc:
            sheets.append({'name': 'Relationship Changes', 'blocks': [{
                'title': 'Critical activities whose relationships were edited between the two updates',
                'note': 'One row per changed relationship (previous → current).',
                'headers': ['S/N', 'Activity ID', 'Activity Name', 'Finish (prev)', 'Finish (now)', 'Finish moved (wd)',
                            'What changed'],
                'rows': [[i, a.get('activity_id', ''), a.get('activity_name', ''), a.get('prev_finish', ''),
                          a.get('curr_finish', ''), '' if a.get('slip_days') is None else a.get('slip_days'), c]
                         for i, a in enumerate(lc, 1) for c in (a.get('changes') or ['—'])]}]})
    except Exception:
        pass
    return sheets
