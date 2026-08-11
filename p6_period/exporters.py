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
        bits.append(f'SPI {_svar(spv)}')
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
    c2 = _card('SPI', _num(s.get('prev_spi')), _num(s.get('curr_spi')),
               (f'{"▲ " if (sv or 0) >= 0 else "▼ "}{_svar(sv)}' if sv is not None else '—'), (sv or 0) >= 0)
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
    ach = s.get('forecast_achievement')
    adh_pct = adh.get('pct')

    def fact(label, value, sub=''):
        return (f'<div class="fact"><div class="fl">{_e(label)}</div><div class="fv">{_e(value)}</div>'
                + (f'<div class="fs">{_e(sub)}</div>' if sub else '') + '</div>')
    return ('<div class="facts">'
            + fact('Forecast achievement', f'{round(ach * 100)}%' if ach is not None else '—', 'earned vs forecast')
            + fact('Schedule adherence', f'{adh_pct:.0f}%' if adh_pct is not None else '—',
                   f"{adh.get('hit', 0)} of {adh.get('planned', 0)} due finishes hit")
            + fact('Started this period', counts.get('started', 0), 'first progress recorded')
            + fact('New critical items', cm.get('new_critical', 0), 'entered critical path')
            + '</div>')


def _scurve_svg(sc):
    periods = (sc or {}).get('periods') or []
    if len(periods) < 2:
        return ''
    fc, ac = sc.get('forecast') or [], sc.get('actual') or []
    x0, x1, y0, y1, n = 45, 900, 235, 20, len(periods)
    xat = lambda i: x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0)
    yat = lambda p: y0 - (y0 - y1) * (max(0.0, min(100.0, p or 0)) / 100.0)

    def poly(arr, color, dash=None):
        pts = [f'{xat(i):.1f},{yat(p):.1f}' for i, p in enumerate(arr) if p is not None]
        if len(pts) < 2:
            return ''
        d = f' stroke-dasharray="{dash}"' if dash else ''
        return f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2.5"{d}/>'
    grid = ''.join(f'<line x1="{x0}" y1="{yat(p):.0f}" x2="{x1}" y2="{yat(p):.0f}" stroke="#eee"/>'
                   f'<text x="{x0 - 6}" y="{yat(p) + 3:.0f}" text-anchor="end" font-size="10" fill="#666">{p}%</text>'
                   for p in (0, 50, 100))
    return (f'<svg viewBox="0 0 940 250" width="100%">{grid}'
            f'{poly(fc, _AMBER, "5 4")}{poly(ac, _BLUE)}'
            f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#ccc"/></svg>'
            f'<div class="legend"><span><i style="background:{_BLUE}"></i>Actual to date</span>'
            f'<span><i style="background:{_AMBER}"></i>Where last period said you\'d be</span></div>')


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
        f'<td>{"finished" if r.get("finished") else ("started" if r.get("started") else ("reversed" if r.get("reversal") else ""))}</td>'
        '</tr>' for r in shown)
    more = f'<p class="note">Showing the {len(shown)} biggest movers of {len(rows)} — full list on screen and in Excel.</p>' if len(rows) > len(shown) else ''
    return ('<table class="data"><thead><tr><th>Activity ID</th><th>Activity name</th>'
            '<th class="num">Prev %</th><th class="num">Current %</th><th class="num">Variance</th><th>Note</th></tr></thead><tbody>'
            + body + '</tbody></table>' + more)


def _critical_table_html(report):
    rows = (report.get('critical_movement', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No critical or near-critical activity moved this window.</p>'
    body = ''.join(
        '<tr>'
        f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
        f'<td class="num mono">{_e(r.get("prev_finish"))}</td><td class="num mono">{_e(r.get("curr_finish"))}</td>'
        f'<td class="num">{("+" + str(r.get("slip_days")) + " wd") if (r.get("slip_days") or 0) > 0 else "—"}</td>'
        f'<td class="num">{_e(r.get("float_days"))}</td><td>{_e(r.get("driver"))}</td>'
        f'<td>{"new" if r.get("critical_status") == "new" else "stayed"}</td>'
        '</tr>' for r in rows)
    return ('<table class="data"><thead><tr><th>Activity ID</th><th>Activity name</th>'
            '<th class="num">Finish (prev)</th><th class="num">Finish (now)</th><th class="num">Slip</th><th class="num">Float</th>'
            '<th>Driver</th><th>Critical</th></tr></thead><tbody>' + body + '</tbody></table>')


def _watch_table_html(report):
    rows = (report.get('watch_list', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No near-critical work is queued for the next window.</p>'
    body = ''.join(
        '<tr>'
        f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
        f'<td class="num">{_e(r.get("float_days"))} wd</td><td class="num mono">{_e(r.get("due_to_start"))}</td>'
        f'<td>{_e(r.get("reason"))}</td></tr>' for r in rows)
    return ('<table class="data"><thead><tr><th>Activity ID</th><th>Activity name</th>'
            '<th class="num">Float</th><th class="num">Due to start</th><th>Why watch it</th></tr></thead><tbody>'
            + body + '</tbody></table>')


def _buckets_html(report):
    counts = (report.get('buckets', {}) or {}).get('counts', {})
    order = [('finished', 'Finished'), ('started', 'Started'), ('slipped', 'Slipped'),
             ('stalled', 'Stalled'), ('re_sequenced', 'Re-sequenced')]
    return '<div class="pills">' + ''.join(
        f'<span class="pill">{counts.get(k, 0)} {lbl}</span>' for k, lbl in order) + '</div>'


def _trend_svg(trend):
    periods = (trend or {}).get('periods') or []
    series = (trend or {}).get('series') or []
    ts_of = lambda d: datetime.strptime(d, '%Y-%m-%d').toordinal()
    all_ts = [ts_of(f) for s in series for f in (s.get('finishes') or []) if f]
    if len(periods) < 2 or len(all_ts) < 2:
        return ''
    tmin, tmax = min(all_ts), max(all_ts)
    if tmin == tmax:
        tmin, tmax = tmin - 30, tmax + 30
    x0, x1, y0, y1, n = 60, 900, 240, 24, len(periods)
    xat = lambda i: x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0)
    yat = lambda t: y0 - (y0 - y1) * ((t - tmin) / (tmax - tmin))
    lines = []
    for si, s in enumerate(series):
        color = _PALETTE[si % len(_PALETTE)]
        pts = [f'{xat(i):.1f},{yat(ts_of(f)):.1f}' for i, f in enumerate(s.get('finishes') or []) if f]
        if len(pts) > 1:
            lines.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2"/>')
    yticks = ''
    for k in range(4):
        t = tmin + (tmax - tmin) * k / 3
        y = yat(t)
        yticks += (f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#eee"/>'
                   f'<text x="{x0 - 6}" y="{y + 3:.1f}" text-anchor="end" font-size="10" fill="#666">'
                   f'{datetime.fromordinal(int(t)).strftime("%b-%y")}</text>')
    legend = ''.join(f'<span><i style="background:{_PALETTE[si % len(_PALETTE)]}"></i>{_e(s.get("name"))}</span>'
                     for si, s in enumerate(series))
    return (f'<div class="legend">{legend}</div>'
            f'<svg viewBox="0 0 940 265" width="100%">{yticks}'
            f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#ccc"/>'
            f'<line x1="{x0}" y1="{y1}" x2="{x0}" y2="{y0}" stroke="#ccc"/>'
            f'{"".join(lines)}</svg>')


def render_html(report, trend=None):
    level, head, detail = _verdict(report)
    scurve = _scurve_svg(report.get('scurve'))
    scurve_block = (f'<h3>Period S-curve</h3><div class="chart">{scurve}</div>') if scurve else ''
    trend_svg = _trend_svg(trend)
    trend_block = (f'<h3>Milestone finish trend — every update so far</h3>{trend_svg}'
                   f'<p class="note">Rising line = that milestone\'s finish keeps slipping later.</p>') if trend_svg else ''
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 11mm; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: system-ui, -apple-system, Arial, sans-serif; color: #1e293b; font-size: 12px; margin: 0; }}
      .page {{ page-break-after: always; }} .page:last-child {{ page-break-after: auto; }}
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
      .facts {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; margin-top: 12px; }}
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
    </style></head><body>

      <div class="page">
        <div class="rh">
          <div><h1>Update vs Update — Period Report</h1>
            <div class="meta">{_e(report.get('project_name'))} · period comparison (Windows Analysis)</div></div>
          <div class="win">Reporting window<br><b>{_e(report.get('data_date_prev'))} → {_e(report.get('data_date_now'))}</b><br>previous cutoff → current cutoff</div>
        </div>
        <div class="banner {level}"><span class="dot {level}"></span>
          <div><div class="b1">{_e(head)}</div><div class="b2">{_e(detail)}</div></div></div>

        <h2>Execution Dashboard — Previous → Current, at each cutoff</h2>
        {_exec_dashboard_html(report)}
        {_recovery_html(report)}
        {_facts_html(report)}

        <div class="split">
          <div>{scurve_block}</div>
          <div><h3>What management needs to know</h3>
            <div class="reco warn">{_e(report.get('project_conclusion'))}</div></div>
        </div>
      </div>

      <div class="page">
        <h2>Progress by activity — % complete this period</h2>
        {_progress_table_html(report)}
        <h2>Critical-path movement in this window</h2>
        {_critical_table_html(report)}
        <h2>Next-period watch list</h2>
        {_watch_table_html(report)}
        <div class="split">
          <div><h3>What moved this period</h3>{_buckets_html(report)}</div>
          <div>{trend_block}</div>
        </div>
        <h2>Executive conclusion — this period</h2>
        <div class="reco">{_e(report.get('conclusion'))}</div>
      </div>

    </body></html>'''


# ── Excel: mirrors the PDF, one sheet ───────────────────────────────────────

_PROGRESS_HEADERS = ['Activity ID', 'Activity name', 'Previous %', 'Current %', 'Variance', 'Note']
_CRITICAL_HEADERS = ['Activity ID', 'Activity name', 'Finish (prev)', 'Finish (now)',
                     'Slip', 'Float', 'Driver', 'Critical']
_WATCH_HEADERS = ['Activity ID', 'Activity name', 'Float (wd)', 'Due to start', 'Why watch it']


def _code_cells(row, code_types):
    """One cell per activity-code dimension — the activity's value (blank if none),
    so the exported tables can be filtered / pivoted by any activity code in Excel."""
    codes = row.get('codes') or {}
    return [codes.get(t, '') for t in code_types]


def _progress_rows(report, code_types=()):
    out = []
    for r in (report.get('progress', {}) or {}).get('rows', []):
        note = 'finished' if r.get('finished') else ('started' if r.get('started')
               else ('progress reversed' if r.get('reversal') else ''))
        out.append([r.get('activity_id', ''), r.get('activity_name', ''),
                    r.get('prev_pct', 0), r.get('curr_pct', 0), r.get('variance', 0), note]
                   + _code_cells(r, code_types))
    return out


def _critical_rows(report, code_types=()):
    out = []
    for r in (report.get('critical_movement', {}) or {}).get('rows', []):
        slip = r.get('slip_days') or 0
        out.append([r.get('activity_id', ''), r.get('activity_name', ''),
                    r.get('prev_finish', ''), r.get('curr_finish', ''),
                    (f'+{slip} wd' if slip > 0 else ''), r.get('float_days', ''),
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
             ['SPI', _num(s.get('prev_spi')) if s.get('prev_spi') is not None else '', _num(s.get('curr_spi')) if s.get('curr_spi') is not None else '', _svar(s.get('spi_variance'))],
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

    periods = (trend or {}).get('periods') or []
    series = (trend or {}).get('series') or []
    if periods and series:
        rows += [[''], ['Milestone finish trend'], ['Milestone'] + list(periods)]
        for ser in series:
            rows.append([ser.get('name', '')] + [(f or '') for f in (ser.get('finishes') or [])])

    rows += [[''], ['Executive conclusion — this period'], [report.get('conclusion', '')]]
    rows += [[''], ['Project conclusion & outlook'], [report.get('project_conclusion', '')]]
    return headers, rows
