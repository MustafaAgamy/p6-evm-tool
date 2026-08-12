"""Update-vs-Update exporters — PDF (HTML -> Chrome) and Excel.

`render_html` lays out a two-page management report: Page 1 is an Execution Dashboard
for top management (status verdict, Previous->Current scorecard, recovery outlook, key
facts, period S-curve, recommendation); Page 2 is the planner detail (progress, critical
movement, next-period watch list, what-moved, milestone trend). `report_excel` mirrors
the same sections into one sheet. Nothing here computes a number.
"""
import html
from datetime import datetime

_BLUE = '#26517d'
_AMBER = '#d97706'
_GOOD = '#16a34a'
_BAD = '#dc2626'
_PALETTE = ['#dc2626', '#16a34a', '#2563eb', '#d97706', '#7c3aed', '#db2777', '#0891b2', '#ea580c']


def _e(v):
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
        bits.append(f'SPI {_spi_var_disp(spv)}')
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
    c1 = _card('Overall % Complete', _num(s.get('actual_prev'), '%'), _num(s.get('actual_now'), '%'),
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
        left += (f'<br>To still hit the <b>baseline finish ({_e(r.get("baseline_finish"))})</b> you\'d need about '
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
    start_m = '' if ap is None else (
        f'<div class="pmark" style="left:{max(0.0, min(100.0, ap)):.1f}%;background:#94a3b8"></div>'
        f'<span class="tag-above" style="left:{max(0.0, min(100.0, ap)):.1f}%;color:#64748b">▾ start {ap:.1f}%</span>')
    plan_m = '' if fn is None else (
        f'<div class="pmark" style="left:{max(0.0, min(100.0, fn)):.1f}%"></div>'
        f'<span class="tag-above" style="left:{max(0.0, min(100.0, fn)):.1f}%">▾ planned {fn:.1f}%</span>')
    behind = ''
    if fn is not None:
        gap = round(fn - an, 1)
        behind = f' — <b>{"on/ahead of" if gap <= 0 else f"{abs(gap):.1f}% behind"}</b> your plan'
    ach = s.get('forecast_achievement')
    ach_txt = f'{round(ach * 100)}%' if ach is not None else '—'
    plan_txt = (f'Your last update planned <b>{fn:.1f}%</b> by now ({_svar(pf, "%")}). ' if fn is not None else '')
    return (f'<div class="prog"><div class="cap"><span>0% — project start</span><span>100% — finish</span></div>'
            f'<div class="pbar">{start_m}'
            f'<div class="pfill" style="width:{fill:.1f}%">{an:.1f}%</div>'
            f'<span class="tag-below" style="left:{fill:.1f}%">▴ now {an:.1f}%</span>'
            f'{plan_m}</div>'
            f'<div class="psent">On <b>{pdd}</b> you were at <b>{ap:.1f}%</b>. {plan_txt}You reached <b>{an:.1f}%</b> on <b>{cdd}</b> ({_svar(pe, "%")}). '
            f'All three are % of the whole project{behind}; you did {_svar(pe, "%")} of {_svar(pf, "%")} = <b>{ach_txt}</b>.</div></div>')


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


def _cp_chain(acts, mode):
    out = []
    for a in acts:
        k = _cp_key(a, mode)
        if not out or out[-1] != k:
            out.append(k)
    return out


def _critical_compare_html(report):
    """The driving path to the finish milestone, grouped to WBS boxes; the CURRENT path is
    red from where it diverges from the previous one (Ibrahim's "new critical path")."""
    cp = report.get('critical_path', {}) or {}
    prevA, currA = cp.get('previous') or [], cp.get('current') or []
    if not prevA and not currA:
        return '<p class="note">No driving path to the finish milestone could be derived.</p>'
    prev, curr = _cp_chain(prevA, 'leaf-parent'), _cp_chain(currA, 'leaf-parent')
    cset = set(curr)
    div = 0
    while div < len(prev) and div < len(curr) and prev[div] == curr[div]:
        div += 1

    def prow(items):
        out = []
        for i, w in enumerate(items):
            out.append(f'<span class="wbs {"same" if w in cset else "gone"}">{_e(w)}</span>')
            if i < len(items) - 1:
                out.append('<span class="arr">→</span>')
        return ' '.join(out) or '<span class="note">—</span>'

    def crow(items):
        out = []
        for i, w in enumerate(items):
            out.append(f'<span class="wbs {"new" if i >= div else "same"}">{_e(w)}</span>')
            if i < len(items) - 1:
                out.append(f'<span class="arr{" newarr" if i >= div else ""}">→</span>')
        return ' '.join(out) or '<span class="note">—</span>'
    return (f'<div class="cprow"><span class="cplbl">Previous</span>{prow(prev)}</div>'
            f'<div class="cprow"><span class="cplbl">Current</span>{crow(curr)}</div>'
            f'<div class="cplegend"><i style="background:#eef4fb;border:1px solid #c9ddf3"></i>same as last period'
            f'<i style="background:#fdecec;border:1px solid #f2b8b8"></i>new critical path (from divergence)'
            f'<i style="background:#f4f4f5;border:1px dashed #cbd5e1"></i>dropped off</div>'
            f'<p class="note">The <b>driving path</b> to the finish milestone (walked back through the driving links), grouped by WBS. On screen you can regroup by any WBS level or activity code. Red = the new route from where it diverges from last period.</p>')


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
    defs = ('<div class="defs"><div class="defs-h">What these mean</div>'
            '<div class="def"><b>Grey bar</b> = planned (due to finish/start this period), <b>coloured</b> = actual; the count on the right is always shown.</div>'
            '<div class="def"><b>Slipped</b> — the activity\'s finish moved <b>later</b> than the previous update showed.</div>'
            '<div class="def"><b>Stalled</b> — it was scheduled to be progressing but earned <b>0%</b> this period.</div>'
            '<div class="def"><b>Re-sequenced</b> — its logic / lag was <b>changed</b> vs last period.</div></div>')
    return f'<div>{rows}</div>{defs}'


def _bycode_html(report):
    """Where the period's progress came from, grouped by the first available activity code."""
    bc = report.get('progress_by_code', {}) or {}
    if not bc:
        return '<p class="note">No activity codes in this schedule to break progress down by.</p>'
    code_type = next(iter(bc))
    rows = bc[code_type][:8]
    mx = max((r['contribution'] for r in rows), default=1) or 1
    body = ''.join(
        f'<div class="bar2"><span class="l">{_e(r["value"])}</span>'
        f'<div class="t"><div class="f" style="width:{max(3, round(100.0 * r["contribution"] / mx))}%">{_svar(r["contribution"], "%")}</div></div></div>'
        for r in rows)
    return (f'<p class="note">Grouped by activity code <b>{_e(code_type)}</b> — where this period\'s progress came from (duration-weighted, indicative).</p>'
            + body)


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
        f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
        f'<td class="num">{_e(r.get("prev_pct"))}%</td><td class="num">{_e(r.get("curr_pct"))}%</td>'
        f'<td class="num {"neg" if r.get("reversal") else "pos"}">{_signpct(r.get("variance"))}</td>'
        f'<td>{_e(r.get("status"))}{" ⚠ reversed" if r.get("reversal") else ""}</td>'
        '</tr>' for r in shown)
    more = f'<p class="note">Showing the {len(shown)} biggest movers of {len(rows)} — full list on screen and in Excel.</p>' if len(rows) > len(shown) else ''
    return ('<table class="data"><thead><tr><th>Activity ID</th><th>Activity name</th>'
            '<th class="num">Prev %</th><th class="num">Current %</th><th class="num">Variance</th><th>Status</th></tr></thead><tbody>'
            + body + '</tbody></table>' + more)


def _critical_table_html(report):
    rows = (report.get('critical_movement', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No critical or near-critical activity moved this window.</p>'
    body = ''.join(
        '<tr>'
        f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td><td>{_e(r.get("wbs"))}</td>'
        f'<td class="num mono">{_e(r.get("prev_finish"))}</td><td class="num mono">{_e(r.get("curr_finish"))}</td>'
        f'<td class="num">{("+" + str(r.get("slip_days")) + " wd") if (r.get("slip_days") or 0) > 0 else "—"}</td>'
        f'<td class="num">{_e(r.get("float_days"))}</td><td>{_e(r.get("driver"))}</td>'
        f'<td>{"new" if r.get("critical_status") == "new" else "stayed"}</td>'
        '</tr>' for r in rows)
    return ('<table class="data"><thead><tr><th>Activity ID</th><th>Activity name</th><th>WBS</th>'
            '<th class="num">Finish (prev)</th><th class="num">Finish (now)</th><th class="num">Slip</th><th class="num">Float</th>'
            '<th>Driver</th><th>Critical</th></tr></thead><tbody>' + body + '</tbody></table>'
            '<p class="note">Construction / execution activities only. On screen you can filter this by any activity code.</p>')


def _watch_table_html(report):
    rows = (report.get('watch_list', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No near-critical work is queued for the next window.</p>'
    body = ''.join(
        '<tr>'
        f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
        f'<td class="num">{_e(r.get("float_days"))} wd</td><td class="num mono">{_e(r.get("due_to_start"))}</td>'
        f'<td>{_e(r.get("reason"))}</td></tr>' for r in rows)
    intro = ('<p class="note" style="margin-top:0">The near-critical construction activities <b>most likely to drive the next reporting window</b> '
             '— not yet finished, with little spare time — tightest float first. Watch these to protect the finish date.</p>')
    table = ('<table class="data"><thead><tr><th>Activity ID</th><th>Activity name</th>'
             '<th class="num">Float</th><th class="num">Due to start</th><th>Why watch it</th></tr></thead><tbody>'
             + body + '</tbody></table>')
    defs = ('<div class="defs"><div class="defs-h">Columns</div>'
            '<div class="def"><b>Float</b> — spare working days before this activity would delay the project finish (0 = on the critical path; ≤ 10 wd = near-critical).</div>'
            '<div class="def"><b>Due to start</b> — the activity\'s forecast start date, from the current update.</div>'
            '<div class="def"><b>Why watch it</b> — why it\'s near-critical: on the critical path, a successor to something slipping, or newly near-critical.</div></div>')
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


def _milestone_table_html(report):
    """Only the OVERALL project-completion milestone (Ibrahim's rule); the chart shows all."""
    r = (report.get('milestones', {}) or {}).get('overall')
    if not r:
        return '<p class="note">No project-completion milestone found in the update.</p>'
    return ('<table class="data"><thead><tr><th>Project completion milestone</th><th class="num">Baseline</th>'
            '<th class="num">Previous forecast</th><th class="num">Current forecast</th>'
            '<th>Slippage this period</th></tr></thead><tbody>'
            f'<tr><td>{_e(r.get("name"))}</td><td class="num mono">{_e(r.get("baseline_finish"))}</td>'
            f'<td class="num mono">{_e(r.get("prev_forecast"))}</td><td class="num mono">{_e(r.get("curr_forecast"))}</td>'
            f'<td>{_milestone_slip_cell(r.get("slip_period_days"), r.get("slip_baseline_days"))}</td></tr>'
            '</tbody></table>')


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
    x0, x1, rowh, top = 168, 905, 24, 14
    n = len(rows)
    h = top + n * rowh + 22
    xat = lambda t: x0 + (x1 - x0) * ((t - tmin) / (tmax - tmin))
    od = lambda iso: datetime.strptime(iso, '%Y-%m-%d').toordinal()
    trunc = lambda s: (s[:26] + '…') if s and len(s) > 27 else (s or '')
    parts = []
    for k in range(5):
        t = tmin + (tmax - tmin) * k / 4
        x = xat(t)
        parts.append(f'<line x1="{x:.0f}" y1="{top}" x2="{x:.0f}" y2="{top + n * rowh:.0f}" stroke="#f1f5f9"/>'
                     f'<text x="{x:.0f}" y="{top + n * rowh + 14:.0f}" text-anchor="middle" font-size="8" fill="#94a3b8">'
                     f'{datetime.fromordinal(int(t)).strftime("%b-%y")}</text>')
    for i, r in enumerate(rows):
        y = top + i * rowh + 12
        parts.append(f'<text x="{x0 - 8}" y="{y + 3:.0f}" text-anchor="end" font-size="8.5" fill="#1e293b">{_e(trunc(r.get("name")))}</text>')
        xs = [xat(od(r[k])) for k in ('baseline_iso', 'prev_iso', 'curr_iso') if r.get(k)]
        if len(xs) >= 2:
            parts.append(f'<line x1="{min(xs):.0f}" y1="{y}" x2="{max(xs):.0f}" y2="{y}" stroke="#cbd5e1"/>')
        if r.get('baseline_iso'):
            parts.append(f'<circle cx="{xat(od(r["baseline_iso"])):.0f}" cy="{y}" r="4" fill="#fff" stroke="#94a3b8" stroke-width="1.8"/>')
        if r.get('prev_iso'):
            parts.append(f'<circle cx="{xat(od(r["prev_iso"])):.0f}" cy="{y}" r="3.6" fill="#d97706"/>')
        if r.get('curr_iso'):
            parts.append(f'<circle cx="{xat(od(r["curr_iso"])):.0f}" cy="{y}" r="4" fill="#dc2626"/>')
    legend = ('<div class="legend" style="font-size:9.5px"><span><i style="background:#fff;border:2px solid #94a3b8;border-radius:50%;width:9px;height:9px"></i>Baseline</span>'
              '<span><i style="background:#d97706;border-radius:50%;width:10px;height:10px"></i>Previous forecast</span>'
              '<span><i style="background:#dc2626;border-radius:50%;width:10px;height:10px"></i>Current forecast</span></div>')
    return legend + f'<svg viewBox="0 0 940 {h}" width="100%" style="max-height:{h}px">{"".join(parts)}</svg>'


_SECTION_LABELS = [
    ('verdict', 'Status verdict'), ('progress', 'Progress chart'),
    ('dashboard', 'Execution Dashboard'), ('recommendation', 'Management recommendation'),
    ('critical_compare', 'Critical-path comparison'), ('critical', 'Critical-path movement table'),
    ('progress_table', 'Progress by activity'), ('watch', 'Next-period watch list'),
    ('whatmoved', 'What moved this period'), ('bycode', 'Progress by activity code'),
    ('milestones', 'Milestones (table + chart)'), ('conclusions', 'Conclusions'),
]


def render_html(report, trend=None, sections=None):
    """`sections` = list of section keys to include (None = all). Every section is tagged
    <section data-sec="KEY"> so the on-screen preview can toggle it and the PDF re-flows."""
    level, head, detail = _verdict(report)
    header = (f'<div class="rh"><div><h1>Update vs Update — Period Report</h1>'
              f'<div class="meta">{_e(report.get("project_name"))} · period comparison (Windows Analysis)</div></div>'
              f'<div class="win">Reporting window<br><b>{_e(report.get("data_date_prev"))} → {_e(report.get("data_date_now"))}</b>'
              f'<br>previous cutoff → current cutoff</div></div>')
    banner = (f'<div class="banner {level}"><span class="dot {level}"></span>'
              f'<div><div class="b1">{_e(head)}</div><div class="b2">{_e(detail)}</div></div></div>')
    dashboard = _exec_dashboard_html(report) + _recovery_html(report) + _facts_html(report) + _defs_html()
    milestones = (f'<div class="keep">{_milestone_table_html(report)}'
                  f'<div class="chart" style="margin-top:8px">{_milestone_drift_svg(report)}</div></div>')
    secs = [
        ('verdict', '', banner, False),
        ('progress', "Progress — where you are vs where you said you'd be", _progress_bar_html(report), False),
        ('dashboard', 'Execution Dashboard — Previous → Current, at each cutoff', dashboard, False),
        ('recommendation', 'What management needs to know', f'<div class="reco warn">{_e(report.get("project_conclusion"))}</div>', False),
        ('critical_compare', 'Critical-path comparison — by WBS', _critical_compare_html(report), True),
        ('critical', 'Critical-path movement in this window', _critical_table_html(report), False),
        ('progress_table', 'Progress by activity — % complete this period', _progress_table_html(report), False),
        ('watch', 'Next-period watch list', _watch_table_html(report), False),
        ('whatmoved', 'What moved this period — planned vs actual', _whatmoved_html(report), False),
        ('bycode', "Where this period's progress came from — by activity code", _bycode_html(report), False),
        ('milestones', 'Milestones — project completion & all finish milestones', milestones, False),
        ('conclusions', 'Executive conclusion — this period', f'<div class="reco">{_e(report.get("conclusion"))}</div>', False),
    ]
    keys = set(sections) if sections else None
    body = [header]
    for key, title, html, planner in secs:
        if keys is not None and key not in keys:
            continue
        t = f'<h2>{_e(title)}</h2>' if title else ''
        body.append(f'<section data-sec="{key}"{" class=pagebreak" if planner else ""}>{t}{html}</section>')
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 11mm; }}
      section.pagebreak {{ page-break-before: always; }}
      .prog {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 28px 16px 12px; }}
      .cap {{ display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin-bottom: 12px; }}
      .tag-above {{ position: absolute; top: -22px; transform: translateX(-50%); white-space: nowrap; font-size: 10px; font-weight: 700; color: #d97706; }}
      .tag-below {{ position: absolute; top: 36px; transform: translateX(-50%); white-space: nowrap; font-size: 10px; font-weight: 700; color: #2a78d6; }}
      .psent {{ margin-top: 34px; font-size: 11.5px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 12px; line-height: 1.5; }}
      .wmrow {{ display: flex; align-items: center; gap: 10px; margin: 6px 0; }} .wml {{ width: 96px; font-size: 11.5px; font-weight: 600; }}
      .wmtrack {{ flex: 1; position: relative; height: 18px; }}
      .wmp {{ position: absolute; left: 0; top: 0; height: 100%; background: #e5ebf2; border: 1px solid #d7dfe8; border-radius: 5px; }}
      .wma {{ position: absolute; left: 0; top: 2px; height: 14px; border-radius: 4px; }}
      .wma.g {{ background: #16a34a; }} .wma.b {{ background: #dc2626; }} .wma.w {{ background: #d97706; }} .wma.n {{ background: #94a3b8; }}
      .wmnum {{ width: 118px; font-size: 11px; color: #334155; }} .wmnum b {{ font-size: 12px; }}
      .cprow {{ display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin: 6px 0; }}
      .cplbl {{ width: 62px; font-size: 10.5px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: .3px; }}
      .wbs {{ border-radius: 8px; padding: 6px 12px; font-size: 11.5px; font-weight: 700; }}
      .wbs.same {{ background: #eef4fb; border: 1px solid #c9ddf3; color: #1e3a8a; }}
      .wbs.new {{ background: #fdecec; border: 1px solid #f2b8b8; color: #b91c1c; }}
      .wbs.gone {{ background: #f4f4f5; border: 1px dashed #cbd5e1; color: #94a3b8; text-decoration: line-through; }}
      .arr {{ color: #94a3b8; font-weight: 800; }} .arr.newarr {{ color: #dc2626; }}
      .cplegend {{ font-size: 10.5px; color: #64748b; margin-top: 7px; }} .cplegend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; vertical-align: middle; margin: 0 5px 0 12px; }}
      .bar2 {{ display: flex; align-items: center; gap: 10px; margin: 5px 0; }} .bar2 .l {{ width: 160px; font-size: 11.5px; }}
      .bar2 .t {{ flex: 1; background: #eef2f7; border-radius: 6px; height: 18px; overflow: hidden; border: 1px solid #e2e8f0; }}
      .bar2 .f {{ height: 100%; background: #2a78d6; display: flex; align-items: center; padding-left: 8px; color: #fff; font-weight: 700; font-size: 11px; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: system-ui, -apple-system, Arial, sans-serif; color: #1e293b; font-size: 12px; margin: 0; }}
      .page {{ page-break-after: always; }} .page:last-child {{ page-break-after: auto; }}
      .keep {{ page-break-inside: avoid; }} .chart {{ page-break-inside: avoid; }}
      h1 {{ font-size: 21px; margin: 0 0 2px; }}
      h2 {{ font-size: 14px; margin: 16px 0 8px; color: #26517d; border-bottom: 2px solid #26517d; padding-bottom: 4px; }}
      h3 {{ font-size: 12.5px; margin: 10px 0 6px; color: #26517d; }}
      .rh {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #26517d; padding-bottom: 10px; margin-bottom: 12px; }}
      .rh .meta {{ color: #64748b; font-size: 11.5px; }} .rh .win {{ text-align: right; font-size: 11.5px; color: #64748b; }} .rh .win b {{ color: #1e293b; font-size: 13px; }}
      .banner {{ display: flex; gap: 12px; align-items: center; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }}
      .banner.good {{ background: #eafaf0; border: 1px solid #a7e0bd; }}
      .banner.warn {{ background: #fff6e9; border: 1px solid #f4d199; }}
      .banner.bad {{ background: #fdecec; border: 1px solid #f2b8b8; }}
      .dot {{ width: 13px; height: 13px; border-radius: 50%; flex: none; }}
      .dot.good {{ background: #16a34a; }} .dot.warn {{ background: #d97706; }} .dot.bad {{ background: #dc2626; }}
      .banner .b1 {{ font-size: 15px; font-weight: 800; }} .banner .b2 {{ font-size: 12px; color: #475569; }}
      .cutoff {{ color: #334155; font-size: 12px; margin: 2px 0 8px; }}
      .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; }}
      .card {{ border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }}
      .card .ct {{ background: #f8fafc; border-bottom: 1px solid #e2e8f0; padding: 5px 9px; font-size: 9.5px; text-transform: uppercase; letter-spacing: .3px; color: #64748b; font-weight: 700; }}
      .card .cb {{ display: grid; grid-template-columns: 1fr 1fr; }}
      .card .cc {{ padding: 6px 9px; }} .card .cc + .cc {{ border-left: 1px solid #e2e8f0; }}
      .card .cl {{ font-size: 9px; color: #94a3b8; }} .card .cv {{ font-size: 15px; font-weight: 800; }}
      .card .cf {{ padding: 5px 9px; border-top: 1px solid #e2e8f0; font-size: 11.5px; font-weight: 700; text-align: center; }}
      .cf.good {{ background: #eafaf0; color: #16a34a; }} .cf.bad {{ background: #fdecec; color: #dc2626; }}
      .recov {{ display: grid; grid-template-columns: 1.5fr 1fr; border: 1px solid #f4d199; border-radius: 8px; overflow: hidden; margin-top: 12px; }}
      .recov .rl {{ padding: 11px 15px; background: #fff6e9; line-height: 1.55; }} .recov .rr {{ padding: 11px 15px; border-left: 1px solid #f4d199; }}
      .rh4 {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .4px; color: #d97706; font-weight: 700; margin-bottom: 4px; }}
      .rr-h {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .4px; color: #26517d; font-weight: 700; }}
      .rr-big {{ font-size: 14px; font-weight: 800; margin: 3px 0; }}
      .rr-v {{ font-size: 12px; font-weight: 700; }} .rr-v.bad {{ color: #dc2626; }} .rr-v.good {{ color: #16a34a; }} .rr-v.warn {{ color: #d97706; }}
      .facts {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; margin-top: 12px; }}
      .fact {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 11px; }}
      .fact .fl {{ font-size: 9.5px; color: #64748b; text-transform: uppercase; letter-spacing: .3px; }} .fact .fv {{ font-size: 15px; font-weight: 800; margin-top: 1px; }} .fact .fs {{ font-size: 10px; color: #94a3b8; }}
      .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 8px; }}
      .chart {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px; }}
      table.data {{ width: 100%; border-collapse: collapse; font-size: 10.5px; margin: 6px 0; }}
      table.data th {{ background: #26517d; color: #fff; text-align: left; padding: 5px 6px; font-weight: 600; }}
      table.data th.num {{ text-align: right; }}
      table.data td {{ border-bottom: 1px solid #e2e8f0; padding: 4px 6px; vertical-align: top; }}
      .mono {{ font-family: Consolas, monospace; }} .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
      .pos {{ color: #15803d; font-weight: 700; }} .neg {{ color: #b91c1c; font-weight: 700; }}
      .note {{ color: #64748b; font-style: italic; }}
      .pills {{ margin: 4px 0; }} .pill {{ display: inline-block; background: #eef2ff; color: #1e3a8a; border-radius: 12px; padding: 2px 10px; font-size: 11px; margin: 0 6px 6px 0; }}
      .legend {{ font-size: 11px; color: #64748b; margin: 4px 0; }} .legend span {{ margin-right: 16px; }} .legend i {{ display: inline-block; width: 16px; height: 3px; vertical-align: middle; margin-right: 5px; }}
      .reco {{ border: 1px solid #e2e8f0; border-left: 4px solid #26517d; border-radius: 0 8px 8px 0; padding: 10px 14px; line-height: 1.6; }}
      .reco.warn {{ border-left-color: #d97706; }}
      .pbwrap {{ margin: 4px 0; }} .pbtop {{ display: flex; justify-content: space-between; font-size: 10.5px; color: #94a3b8; margin-bottom: 15px; }}
      .pbar {{ position: relative; height: 30px; background: #eef2f7; border-radius: 8px; border: 1px solid #e2e8f0; }}
      .pfill {{ position: absolute; left: 0; top: 0; bottom: 0; background: #2a78d6; border-radius: 7px 0 0 7px; display: flex; align-items: center; justify-content: flex-end; padding-right: 9px; color: #fff; font-weight: 800; font-size: 12px; }}
      .pmark {{ position: absolute; top: -5px; bottom: -5px; width: 3px; background: #d97706; }}
      .pmark .lab {{ position: absolute; top: -16px; left: 50%; transform: translateX(-50%); white-space: nowrap; font-size: 10px; color: #d97706; font-weight: 700; }}
      .pbbot {{ text-align: center; font-size: 11.5px; color: #475569; margin-top: 5px; }}
      .twobar {{ margin-top: 12px; }} .tb {{ display: flex; align-items: center; gap: 10px; margin: 5px 0; }}
      .tb .lbl {{ width: 170px; font-size: 11.5px; color: #64748b; }}
      .tb .track {{ flex: 1; background: #eef2f7; border-radius: 6px; height: 19px; overflow: hidden; border: 1px solid #e2e8f0; }}
      .tb .fillp {{ height: 100%; background: #f0b357; display: flex; align-items: center; padding-left: 8px; color: #7c4a03; font-weight: 700; font-size: 11px; }}
      .tb .filla {{ height: 100%; background: #2a78d6; display: flex; align-items: center; padding-left: 8px; color: #fff; font-weight: 700; font-size: 11px; }}
      .chartlegend {{ margin-top: 10px; padding-top: 8px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #334155; line-height: 1.6; }}
      .chartlegend > div {{ margin: 2px 0; }} .lg-sw {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: middle; margin-right: 7px; }}
      .defs {{ margin-top: 12px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; }}
      .defs-h {{ font-size: 10px; text-transform: uppercase; letter-spacing: .4px; color: #64748b; font-weight: 700; margin-bottom: 5px; }}
      .def {{ font-size: 11px; color: #334155; line-height: 1.5; margin: 2px 0; }} .def b {{ color: #1e293b; }}
    </style></head><body>{"".join(body)}</body></html>'''


# ── Excel: mirrors the PDF, one sheet ───────────────────────────────────────

_PROGRESS_HEADERS = ['Activity ID', 'Activity name', 'Previous %', 'Current %', 'Variance', 'Status']
_CRITICAL_HEADERS = ['Activity ID', 'Activity name', 'Finish (prev)', 'Finish (now)',
                     'Slip', 'Float', 'Driver', 'Critical']
_WATCH_HEADERS = ['Activity ID', 'Activity name', 'Float (wd)', 'Due to start', 'Why watch it']


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
        out.append([r.get('activity_id', ''), r.get('activity_name', ''),
                    f"{r.get('prev_pct', 0)}%", f"{r.get('curr_pct', 0)}%",
                    _xl_sign(r.get('variance', 0), '%'), status]
                   + _code_cells(r, code_types))
    return out


def _critical_rows(report, code_types=()):
    out = []
    for r in (report.get('critical_movement', {}) or {}).get('rows', []):
        slip = r.get('slip_days') or 0
        out.append([r.get('activity_id', ''), r.get('activity_name', ''),
                    r.get('prev_finish', ''), r.get('curr_finish', ''),
                    _xl_sign(slip, ' wd') if slip else '', r.get('float_days', ''),
                    r.get('driver', ''), ('new' if r.get('critical_status') == 'new' else 'stayed')]
                   + _code_cells(r, code_types))
    return out


def _watch_rows(report, code_types=()):
    out = []
    for r in (report.get('watch_list', {}) or {}).get('rows', []):
        out.append([r.get('activity_id', ''), r.get('activity_name', ''),
                    r.get('float_days', ''), r.get('due_to_start', ''), r.get('reason', '')]
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
             ['Overall % Complete', _pctcell(s.get('actual_prev')), _pctcell(s.get('actual_now')), _svar(s.get('period_earned'), '%')],
             ['SPI', _spi_disp(s.get('prev_spi')) if s.get('prev_spi') is not None else '', _spi_disp(s.get('curr_spi')) if s.get('curr_spi') is not None else '', _spi_var_disp(s.get('spi_variance'))],
             ['Delay vs baseline', _num(s.get('delay_prev'), ' wd') if s.get('delay_prev') is not None else '', _num(s.get('delay_now'), ' wd') if s.get('delay_now') is not None else '', _svar(s.get('delay_change'), ' wd')],
             ['Forecast finish', s.get('forecast_finish_prev') or '', s.get('forecast_finish_now') or '',
              (f"slipped {s.get('finish_slip_days')} d" if (s.get('finish_slip_days') or 0) > 0 else '')],
             ['']]

    rows += [['Recovery outlook'],
             ['Work remaining', _pctcell(rec.get('work_remaining'))],
             ['Earned this period', _pctcell(rec.get('current_rate'))],
             ['Baseline finish', rec.get('baseline_finish') or ''],
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
    rows += [[''], ['Critical-path movement in this window'], _CRITICAL_HEADERS + list(ct)] + _critical_rows(report, ct)
    rows += [[''], ['Next-period watch list'], _WATCH_HEADERS + list(ct)] + _watch_rows(report, ct)

    rows += [[''], ['What moved this period']]
    for k, lbl in [('finished', 'Finished'), ('started', 'Started'), ('slipped', 'Slipped'),
                   ('stalled', 'Stalled'), ('re_sequenced', 'Re-sequenced')]:
        rows.append([lbl, counts.get(k, 0)])

    mrows = (report.get('milestones', {}) or {}).get('rows', [])
    if mrows:
        rows += [[''], ['Milestones — baseline vs previous vs current forecast'],
                 ['Key milestone', 'Baseline', 'Previous forecast', 'Current forecast',
                  'Slip this period (wd)', 'Slip vs baseline (wd)']]
        for m in mrows:
            rows.append([m.get('name', ''), m.get('baseline_finish', ''), m.get('prev_forecast', ''),
                         m.get('curr_forecast', ''), m.get('slip_period_days', ''), m.get('slip_baseline_days', '')])

    rows += [[''], ['Executive conclusion — this period'], [report.get('conclusion', '')]]
    rows += [[''], ['Project conclusion & outlook'], [report.get('project_conclusion', '')]]
    return headers, rows
