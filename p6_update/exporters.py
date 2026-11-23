"""Update-Analysis exporters — PDF (HTML → Chrome headless) and Excel.

`render_html` lays out the four sections in the house consultant style: Time Status
(donut + PV/EV/Variance), Planned vs Actual by activity code (one chart per selected
code), the Driving Path Analyzer (the governing milestone's driving path as work-front
boxes), and Planned vs Actual by activity count. `report_excel` mirrors them.
Nothing here computes a number — it only presents what `p6_update.analysis` produced.
"""
import html
from datetime import datetime

import report_theme
from utils import date_text as _date_text

_BLUE = report_theme.var('rpt-accent')
_PLAN = report_theme.var('rpt-series-3')
_ACT = report_theme.var('rpt-series-1')
_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _e(v):
    v = _date_text(v)                     # an ISO date shows as 03-Dec.2026 (comment 46)
    return html.escape(str(v if v is not None else ''))


def _fdate(iso):
    """ISO date → '09-Feb.2027'."""
    if not iso:
        return '—'
    try:
        d = datetime.strptime(str(iso)[:10], '%Y-%m-%d')
        return f'{d.day:02d}-{_MONTHS[d.month - 1]}.{d.year}'
    except Exception:
        return str(iso)


def _num(n):
    if n is None:
        return '—'
    try:
        return f'{n:,.0f}'
    except Exception:
        return str(n)


def _pct(v):
    return f'{v:.0f}%' if isinstance(v, (int, float)) else '—'


def _pct2(v):
    return f'{v:.2f}%' if isinstance(v, (int, float)) else '—'


def _svar(v):
    if v is None:
        return '—'
    return f'+{v}' if v > 0 else str(v)


# ── Section 1 · Time Status ─────────────────────────────────────────────────

def _donut(elapsed, planned, actual):
    def arc(r, pct):
        c = 2 * 3.14159265 * r
        on = c * max(0.0, min(100.0, pct or 0)) / 100.0
        return f'{on:.1f} {c - on:.1f}'
    lab = f'{actual:.2f}%' if actual is not None else '—'
    return f'''<svg width="140" height="140" viewBox="0 0 150 150">
      <circle cx="75" cy="75" r="58" fill="none" stroke="{report_theme.var('rpt-edge')}" stroke-width="18"/>
      <circle cx="75" cy="75" r="58" fill="none" stroke="{_ACT}" stroke-width="18" stroke-dasharray="{arc(58, elapsed)}" transform="rotate(-90 75 75)"/>
      <circle cx="75" cy="75" r="40" fill="none" stroke="{report_theme.var('rpt-edge')}" stroke-width="10"/>
      <circle cx="75" cy="75" r="40" fill="none" stroke="{report_theme.var('rpt-good')}" stroke-width="10" stroke-dasharray="{arc(40, actual)}" transform="rotate(-90 75 75)"/>
      <text x="75" y="70" text-anchor="middle" font-size="17" font-weight="700" fill="{report_theme.var('rpt-ink')}">{_e(lab)}</text>
      <text x="75" y="88" text-anchor="middle" font-size="10" fill="{report_theme.var('rpt-muted')}">earned</text>
    </svg>'''


def _timestatus_html(report, cost_only=False):
    ts = report.get('time_status', {}) or {}
    ep, pp, ap = ts.get('elapsed_pct'), ts.get('planned_pct'), ts.get('actual_pct')
    elapsed_txt = '—'
    if ep is not None:
        elapsed_txt = f'{ep:.1f}%'
        if ts.get('exceeded_days'):
            elapsed_txt = f'100% — baseline exceeded by {ts["exceeded_days"]} days'
    sentence = (f'<b>{elapsed_txt}</b> of the baseline time has elapsed, but only '
                f'<b>{_pct2(ap)}</b> of the work is earned (planned to be at <b>{_pct2(pp)}</b> by now).')
    if ts.get('baseline_kind') == 'revised':
        sentence = (f'This file is a <b>revised baseline</b> — the baseline re-set at its data date, with '
                    f'<b>{_pct2(ap)}</b> of the work already earned (planned <b>{_pct2(pp)}</b>). '
                    f'<b>{elapsed_txt}</b> of its time has elapsed: the clock starts at its data date.')
    elif ts.get('baseline_kind') == 'original':
        sentence = (f'This file is the <b>original baseline</b>, set at its data date before any progress: '
                    f'<b>{elapsed_txt}</b> of its time has elapsed.')
    elif ts.get('baseline_file'):
        sentence = (f'This file has no baseline in P6 and is read as the baseline itself: '
                    f'<b>{elapsed_txt}</b> of its time has elapsed (the clock starts at its data date); '
                    f'<b>{_pct2(ap)}</b> is earned against <b>{_pct2(pp)}</b> planned.')
    verdicts = ''
    if ts.get('behind_plan') is not None and pp is not None and ap is not None:
        v = ts['behind_plan']
        tag = 'bad' if v > 0 else 'good'
        verb = 'short of' if v > 0 else 'ahead of'
        verdicts += (f'<div class="vrow"><span class="vtag {tag}">Behind plan · {abs(v)}</span>'
                     f'<span>You planned to have earned <b>{_pct2(pp)}</b> by the data date; you’ve earned '
                     f'<b>{_pct2(ap)}</b> — {abs(v):.2f} points {verb} the plan.</span></div>')
    if ts.get('behind_clock') is not None and ep is not None and ap is not None:
        v = ts['behind_clock']
        tag = 'bad' if v > 0 else 'good'
        verdicts += (f'<div class="vrow"><span class="vtag {tag}">Behind clock · {abs(v)}</span>'
                     f'<span><b>{ep:.1f}%</b> of the baseline time is used up, but only <b>{_pct2(ap)}</b> '
                     f'of the work is done — {abs(v):.2f} points {"less" if v > 0 else "more"} work than time spent.</span></div>')
    # parts of this section for the Report Contents picker (owner comment 1)
    cost = (f'<div class="cost" data-part="time.values" data-part-label="Planned Value / Earned Value / Variance">'
            f'<div class="costcard"><div class="cl">Planned Value (PV)</div><div class="cv">{_num(ts.get("pv"))}</div></div>'
            f'<div class="costcard"><div class="cl">Earned Value (EV)</div><div class="cv">{_num(ts.get("ev"))}</div></div>'
            f'<div class="costcard"><div class="cl">Variance = EV − PV</div>'
            f'<div class="cv {"neg" if (ts.get("cost_variance") or 0) < 0 else ""}">{_num(ts.get("cost_variance"))}</div></div>'
            f'</div>')
    if cost_only:                          # Section 1 now leads with the summary band
        return cost
    return (f'<div class="ts" data-part="time.status" data-part-label="Time status — elapsed vs earned (gauge and reading)">'
            f'<div>{_donut(ep, pp, ap)}</div>'
            f'<div class="ts-body"><div class="ts-sentence">{sentence}</div>'
            f'<div class="verdicts">{verdicts}</div></div></div>{cost}')


# ── Section 1 · summary band (approved 2026-11-23) ──────────────────────────
# The verdict line, the six key numbers and Progress at the data date (the donut + the
# ruler) — the same ready-made text the screen prints (report['summary']).

def _ruler_svg(ts):
    """Earned, Planned and Time elapsed on one 0–100% bar (an SVG so Word keeps it)."""
    ep, pp, ap = ts.get('elapsed_pct'), ts.get('planned_pct'), ts.get('actual_pct')
    x0, x1, y = 20, 620, 52
    xat = lambda v: x0 + (x1 - x0) * max(0.0, min(100.0, v or 0)) / 100.0
    ink, muted, edge = report_theme.var('rpt-ink'), report_theme.var('rpt-muted'), report_theme.var('rpt-edge')
    surf = report_theme.var('rpt-surface')
    s = (f'<rect x="{x0}" y="{y}" width="{x1 - x0}" height="26" rx="6" fill="{surf}" stroke="{edge}"/>'
         f'<rect x="{x0}" y="{y}" width="{xat(ap) - x0:.1f}" height="26" rx="6" fill="{_ACT}"/>')
    for v in (0, 25, 50, 75, 100):
        s += f'<text x="{xat(v):.1f}" y="{y + 56}" text-anchor="middle" font-size="9.5" fill="{muted}">{v}%</text>'
    close = ep is not None and pp is not None and abs((ep or 0) - (pp or 0)) < 14

    def mark(v, colour, label, where):
        x = xat(v)
        ty = {'dn': y + 42, 'up': y - 10, 'up2': y - 26}[where]
        return (f'<line x1="{x:.1f}" y1="{y - 6}" x2="{x:.1f}" y2="{y + 32}" stroke="{colour}" stroke-width="3"/>'
                f'<text x="{x:.1f}" y="{ty}" text-anchor="middle" font-size="11" font-weight="700" fill="{colour}">{_e(label)}</text>')
    if ap is not None:
        s += mark(ap, _ACT, f'Earned {_pct2(ap)}', 'dn')
    if ep is not None:
        s += mark(ep, muted, f'Time {ep:.1f}%', 'up')
    if pp is not None:
        s += mark(pp, _PLAN, f'Planned {_pct2(pp)}', 'up2' if close else 'up')
    return f'<svg viewBox="0 0 640 120" width="100%" style="max-width:640px;color:{ink}">{s}</svg>'


def _summary_html(report):
    sm = report.get('summary') or {}
    ts = report.get('time_status', {}) or {}
    kpis = ''.join(
        f'<td class="kpi {_e(k.get("tone"))}"><div class="kl">{_e(k.get("label"))}</div>'
        f'<div class="kv{" kd" if k.get("key") == "finish" else ""}">{_e(k.get("value"))}</div>'
        f'<div class="ks">{_e(k.get("sub"))}</div></td>' for k in sm.get('kpis') or [])
    gap = []
    if ts.get('behind_plan') is not None:
        v = ts['behind_plan']
        gap.append(f'Behind plan <b class="{"neg" if v > 0 else "pos"}">{abs(v):.2f} points</b> (earned vs planned)')
    if ts.get('behind_clock') is not None:
        v = ts['behind_clock']
        gap.append(f'behind the clock <b class="{"neg" if v > 0 else "pos"}">{abs(v):.2f} points</b> (earned vs time used)')
    cv = ts.get('cost_variance')
    var_txt = ''
    if isinstance(cv, (int, float)):
        var_txt = (f' Variance EV − PV <b class="{"neg" if cv < 0 else "pos"}">'
                   f'{"−" if cv < 0 else "+"}{_m(abs(cv))}</b>.')
    ep = ts.get('elapsed_pct')
    return (f'<div class="verdict {_e(sm.get("status"))}" data-part="time.verdict" data-part-label="Verdict and six key numbers">'
            f'<div class="vline"><span class="pill">{_e(sm.get("label"))}</span>'
            f'<div><div class="vh">{_e(sm.get("headline"))}</div><div class="vd">{_e(sm.get("detail"))}</div></div></div>'
            f'<table class="kpis"><tr>{kpis}</tr></table></div>'
            f'<div class="prog" data-part="time.status" data-part-label="Progress at the data date (donut and ruler)">'
            f'<h3>Progress at the data date</h3>'
            f'<table class="progt"><tr><td class="don">{_donut(ep, ts.get("planned_pct"), ts.get("actual_pct"))}'
            f'<div class="donleg">outer: time {f"{ep:.1f}%" if ep is not None else "—"} · inner: earned</div></td>'
            f'<td>{_ruler_svg(ts)}</td></tr></table>'
            f'<div class="gapnote">{" · ".join(gap)}{"." if gap else ""}{var_txt}</div></div>')


# ── Section 6 · Progress S-curve (approved 2026-11-23) ──────────────────────

def _scurve_svg(sc, ms):
    pts = sc.get('points') or []
    if len(pts) < 2:
        return ''
    W, H, L, R, T, B = 1060, 360, 48, 150, 22, 44
    d = lambda s: datetime.strptime(str(s)[:10], '%Y-%m-%d').timestamp()
    ext = [d(x) for x in (ms.get('baseline_finish'), ms.get('expected_finish')) if x]
    tms = [d(p['date']) for p in pts]
    ta, tb = min(tms) - 15 * 86400, max(tms + ext) + 5 * 86400
    X = lambda v: L + (v - ta) / (tb - ta) * (W - L - R)
    Y = lambda v: T + (100 - v) * (H - T - B) / 100
    grid, axis = report_theme.var('rpt-chart-grid'), report_theme.var('rpt-chart-axis')
    bad, acc, muted = report_theme.var('rpt-bad'), _BLUE, report_theme.var('rpt-muted')
    s = ''
    for v in (0, 25, 50, 75, 100):
        s += (f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{grid}"/>'
              f'<text x="{L - 8}" y="{Y(v) + 4:.1f}" font-size="11" text-anchor="end" fill="{axis}">{v}%</text>')
    months = [p for p in pts if p['kind'] == 'month']
    every = max(1, -(-len(months) // 12))
    for i, p in enumerate(months):
        if i % every == 0:
            s += (f'<text x="{X(d(p["date"])):.1f}" y="{H - 16}" font-size="11" text-anchor="middle" '
                  f'fill="{axis}">{_e(_fdate(p["date"])[3:])}</text>')

    def line(key, colour, width, dash=''):
        seg = [p for p in pts if p.get(key) is not None]
        if not seg:
            return ''
        path = ' '.join(f'{"L" if i else "M"}{X(d(p["date"])):.1f},{Y(p[key]):.1f}' for i, p in enumerate(seg))
        dash = f' stroke-dasharray="{dash}"' if dash else ''
        return f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="{width}"{dash}/>'
    s += line('planned', _PLAN, 3) + line('forecast', bad, 2.5, '7 5') + line('earned', _ACT, 3.5)
    for p in pts:
        if p.get('earned') is not None and p['kind'] == 'month':
            s += (f'<circle cx="{X(d(p["date"])):.1f}" cy="{Y(p["earned"]):.1f}" r="3" '
                  f'fill="{report_theme.var("rpt-paper", "#fff")}" stroke="{_ACT}" stroke-width="1.5"/>')
        if p['kind'] == 'update':
            s += f'<circle cx="{X(d(p["date"])):.1f}" cy="{Y(p["earned"]):.1f}" r="5.5" fill="{_ACT}"/>'
    dd = next((p for p in pts if p['kind'] == 'data_date'), None)
    if dd:
        xd = X(d(dd['date']))
        s += (f'<line x1="{xd:.1f}" x2="{xd:.1f}" y1="{T}" y2="{H - B}" stroke="{acc}" stroke-dasharray="4 4"/>'
              f'<text x="{xd + 6:.1f}" y="{T + 10}" font-size="11.5" fill="{acc}" font-weight="700">data date {_e(_fdate(dd["date"]))}</text>')
        if dd.get('planned') is not None:
            s += (f'<circle cx="{xd:.1f}" cy="{Y(dd["planned"]):.1f}" r="5.5" fill="{_PLAN}"/>'
                  f'<text x="{xd - 9:.1f}" y="{Y(dd["planned"]) - 8:.1f}" font-size="12" text-anchor="end" font-weight="700" fill="{_PLAN}">Planned {_pct2(dd["planned"])}</text>')
        s += (f'<circle cx="{xd:.1f}" cy="{Y(dd["earned"]):.1f}" r="5.5" fill="{_ACT}"/>'
              f'<text x="{xd + 9:.1f}" y="{Y(dd["earned"]) + 18:.1f}" font-size="12" font-weight="700" fill="{_ACT}">Earned {_pct2(dd["earned"])}</text>')
    if ms.get('baseline_finish'):
        xb = X(d(ms['baseline_finish']))
        s += (f'<line x1="{xb:.1f}" x2="{xb:.1f}" y1="{Y(100):.1f}" y2="{H - B}" stroke="{muted}" stroke-dasharray="3 4"/>'
              f'<text x="{xb - 4:.1f}" y="{Y(100) - 6:.1f}" font-size="11" text-anchor="end" fill="{muted}">baseline finish {_e(_fdate(ms["baseline_finish"]))}</text>')
    if ms.get('expected_finish'):
        xe, sl = X(d(ms['expected_finish'])), ms.get('slip_days')
        tail = f'<tspan x="{xe + 5:.1f}" dy="14">({"+" if (sl or 0) > 0 else ""}{sl} d)</tspan>' if sl is not None else ''
        s += (f'<line x1="{xe:.1f}" x2="{xe:.1f}" y1="{Y(100):.1f}" y2="{H - B}" stroke="{bad}" stroke-dasharray="3 4"/>'
              f'<text font-size="11" fill="{bad}" font-weight="700"><tspan x="{xe + 5:.1f}" y="{Y(45):.1f}">expected finish</tspan>'
              f'<tspan x="{xe + 5:.1f}" dy="14">{_e(_fdate(ms["expected_finish"]))}</tspan>{tail}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%">{s}</svg>'


def _scurve_html(report):
    sc = report.get('scurve') or {}
    pts = sc.get('points') or []
    if not pts:
        return '<p class="note">Not enough dated activities to draw the S-curve.</p>'
    ms = ((report.get('critical_path') or {}).get('charts') or [{}])[0].get('milestone') or {}
    dd = next((p for p in pts if p['kind'] == 'data_date'), {})
    on = [e for e in sc.get('earlier') or [] if e.get('on')]
    earlier = (' · '.join(f'{_fdate(e["data_date"])} ({_pct2(e.get("earned"))})' for e in on)
               if on else 'none')
    basis = ('its planned duration (this file carries no cost)' if sc.get('basis') == 'duration' else 'its budget')
    last = sc.get('last_remaining_finish')
    ms_note = (f' ({_e(ms.get("name") or "the completion milestone")} is {_fdate(ms["expected_finish"])})'
               if ms.get('expected_finish') and last and str(ms['expected_finish'])[:10] != last else '')
    leg = (f'<div class="bc-leg"><span><i style="background:{_PLAN}"></i>Planned (baseline)</span>'
           f'<span><i style="background:{_ACT}"></i>Earned, rebuilt from actual dates</span>'
           f'<span><i style="background:{_ACT};border-radius:50%"></i>Earned, from an earlier update</span>'
           f'<span><i style="background:{report_theme.var("rpt-bad")};height:3px"></i>Forecast (P6 remaining dates)</span></div>')
    note = (f'<div class="scnote"><b>Earlier updates on this curve:</b> {_e(earlier)}. '
            f'<b>Planned</b> = the same Planned % rule as Time Status (each activity\'s baseline dates, in its own '
            f'calendar\'s working time, weighted by {basis}), at every month end; on the data date it is exactly '
            f'{_pct2(dd.get("planned"))}. <b>Earned</b> = each activity\'s % complete spread over its actual start → '
            f'actual finish (or the data date); where an earlier update of this job was imported, its own Earned % '
            f'stands at its data date; on the data date it is exactly {_pct2(dd.get("earned"))}. <b>Forecast</b> = each '
            f'activity\'s remaining work spread over its remaining start → finish in this P6 file'
            f'{f"; it reaches 100% on {_fdate(last)}" if last else ""}{ms_note}.</div>')
    rows = ''
    for p in pts:
        g = (p['earned'] - p['planned']) if (p.get('earned') is not None and p.get('planned') is not None) else None
        src = 'earlier update' if p.get('earned_source') == 'update' else (p.get('earned_source') or '')
        tag = ' · data date' if p['kind'] == 'data_date' else (' · update' if p['kind'] == 'update' else '')
        cls = ' class="ddrow"' if p['kind'] == 'data_date' else ''
        rows += (f'<tr{cls}><td>{_fdate(p["date"])}{tag}</td>'
                 f'<td class="num">{_pct2(p.get("planned")) if p.get("planned") is not None else ""}</td>'
                 f'<td class="num">{_pct2(p.get("earned")) if p.get("earned") is not None else ""}</td>'
                 f'<td class="num">{_pct2(p.get("forecast")) if p.get("forecast") is not None else ""}</td>'
                 f'<td class="num {"neg" if (g or 0) < 0 else "pos"}">{"" if g is None else f"{g:+.2f}"}</td>'
                 f'<td>{_e(src)}</td></tr>')
    table = ('<table class="ctab"><thead><tr><th>Date</th><th class="num">Planned %</th><th class="num">Earned %</th>'
             '<th class="num">Forecast %</th><th class="num">Gap (earned − planned)</th><th>Earned from</th></tr></thead>'
             f'<tbody>{rows}</tbody></table>')
    return (f'<div data-part="scurve.chart" data-part-label="S-curve chart">{_scurve_svg(sc, ms)}{leg}{note}</div>'
            f'<div data-part="scurve.table" data-part-label="Monthly values">{table}</div>')



# ── Section 2 · Planned vs Actual by activity code (one chart per code) ──────

def _bars_for(rows):
    if not rows:
        return '<p class="note">No values for this activity code.</p>'
    out = []
    for r in rows:
        var = r.get('variance', 0)
        cls = 'neg' if var < 0 else 'pos'
        out.append(
            f'<div class="bc-row"><div class="bc-name">{_e(r.get("value"))}</div>'
            f'<div class="bc-track"><div class="bc-pl" style="width:{max(0, min(100, r.get("planned", 0)))}%"></div></div>'
            f'<div class="bc-track"><div class="bc-ac" style="width:{max(0, min(100, r.get("actual", 0)))}%"></div></div>'
            f'<div class="bc-num">planned {r.get("planned", 0):.1f}% · actual {r.get("actual", 0):.1f}% · '
            f'<b class="{cls}">{_svar(var)}</b></div></div>')
    leg = (f'<div class="bc-leg"><span><i style="background:{_PLAN}"></i>Planned %</span>'
           f'<span><i style="background:{_ACT}"></i>Actual %</span></div>')
    return '<div class="bc">' + ''.join(out) + '</div>' + leg


def _bycode_html(report, code_filter=None):
    by = report.get('by_code', {}) or {}
    if not by:
        return '<p class="note">No activity codes found in this update.</p>'
    # Which code dimensions to show — the on-screen selection, else the first.
    types = None
    if code_filter:
        types = code_filter.get('types') or ([code_filter['type']] if code_filter.get('type') else None)
    if not types:
        types = [next(iter(by))]
    types = [t for t in types if t in by]
    if not types:
        types = [next(iter(by))]
    blocks = []
    for i, t in enumerate(types, 1):
        blocks.append(f'<div class="chart2" data-part="bycode.c{i}" data-part-label="Planned vs Actual — {_e(t)}">'
                      f'<h3>{_e(t)}</h3>{_bars_for(by[t])}</div>')
    return ''.join(blocks)


# ── Section 3 · Driving Path Analyzer ───────────────────────────────────────

def _box_html(b):
    cls = 'done' if b.get('complete') else ''
    tag = ' <span class="bx-tag">activity — no cost in WBS</span>' if b.get('source') == 'activity' else ''
    return (f'<div class="box {cls}"><div class="bt">{_e(b.get("name"))}{tag}</div>'
            f'<div class="bc">{_e(b.get("crumb"))}</div>'
            f'<div class="b4">'
            f'<div><div class="k">Planned</div><div class="v">{b.get("planned", 0):.1f}%</div></div>'
            f'<div><div class="k">Actual</div><div class="v">{b.get("pct", 0):.1f}%</div></div>'
            f'<div><div class="k">Baseline Finish</div><div class="v mono">{_fdate(b.get("bl_finish"))}</div></div>'
            f'<div><div class="k">Expected Finish</div><div class="v mono">{_fdate(b.get("exp_finish"))}</div></div>'
            f'<div class="full"><div class="k">Delay</div>'
            f'<div class="v {"neg" if (b.get("slip_days") or 0) > 0 else ""}">{_svar(b.get("slip_days"))} d</div></div>'
            f'</div></div>')


def _driving_html(report):
    cp = report.get('critical_path', {}) or {}
    if not cp.get('charts'):
        return '<p class="note">No governing completion milestone with a driving path was found in this update.</p>'
    out = []
    if cp.get('headline'):
        out.append(f'<div class="dphead">{_e(cp["headline"])}</div>')
    for ci, chart in enumerate(cp['charts'], 1):
        ms = chart.get('milestone', {}) or {}
        sm = chart.get('start_milestone') or {}
        parts = []
        if sm.get('name'):
            parts.append(f'<div class="msbox start"><div class="msflag">▶ Start Milestone</div>'
                         f'<div class="mst">{_e(sm.get("name"))}</div>'
                         f'<div class="r"><span>Date</span><b class="mono">{_fdate(sm.get("date"))}</b></div></div>')
            parts.append('<div class="arw">▸</div>')
        boxes = chart.get('boxes', [])
        for b in boxes:
            parts.append(_box_html(b))
            parts.append('<div class="arw">▸</div>')
        parts.append(f'<div class="msbox"><div class="msflag">◆ Completion Milestone</div>'
                     f'<div class="mst">{_e(ms.get("name"))}</div>'
                     f'<div class="r"><span>Baseline Finish</span><b class="mono">{_fdate(ms.get("baseline_finish"))}</b></div>'
                     f'<div class="r"><span>Expected Finish</span><b class="mono">{_fdate(ms.get("expected_finish"))}</b></div>'
                     f'<div class="r"><span>Delay</span><b class="neg">{_svar(ms.get("slip_days"))} d</b></div></div>')
        out.append(f'<div class="chain" data-part="driving.c{ci}" '
                   f'data-part-label="Driving path to {_e(ms.get("name") or "the completion milestone")}">'
                   f'{"".join(parts)}</div>')
    return ''.join(out)


# ── Section 5 · Scope weight & recommendation ───────────────────────────────

def _m(v):
    """12,345,678 -> '12.3 M' (as the screen)."""
    v = float(v or 0)
    return f"{v / 1e6:,.1f} M" if abs(v) >= 1e6 else f"{v:,.0f}"


def _bar(actual, planned, colour):
    a, p = max(0.0, min(100.0, actual or 0)), max(0.0, min(100.0, planned or 0))
    return (f'<div style="position:relative;height:11px;background:{report_theme.var("rpt-surface")};border:1px solid {report_theme.var("rpt-edge")};'
            f'border-radius:6px;min-width:120px;-webkit-print-color-adjust:exact;print-color-adjust:exact">'
            f'<div style="position:absolute;left:0;top:0;bottom:0;width:{a:.1f}%;background:{colour};border-radius:6px"></div>'
            f'<div style="position:absolute;top:-3px;bottom:-3px;left:calc({p:.1f}% - 1px);width:3px;background:{report_theme.var("rpt-ink")}"></div></div>')


def _scope_html(report, code_type=None):
    """Section 5 - Scope by Cost (15-Oct redesign): Cost, Planned Value, Earned Value, EV - PV and
    SPI for the scope, one row per activity-code value, the recommendation by money behind plan."""
    scope = report.get('scope', {}) or {}
    if not scope:
        return '<p class="note">No cost-loaded activity codes to weigh in this update.</p>'
    ct = code_type if code_type in scope else (report.get('scope_default') if report.get('scope_default') in scope else next(iter(scope)))
    s = scope[ct]
    rows = s.get('rows', [])
    good, bad, warn = report_theme.var('rpt-good'), report_theme.var('rpt-bad'), report_theme.var('rpt-warn')
    pv = s.get('pv') if s.get('pv') is not None else sum(r.get('pv') or 0 for r in rows)
    ev = s.get('ev') if s.get('ev') is not None else sum(r.get('ev') or 0 for r in rows)
    d = ev - pv
    tiles = [('Cost', _m(s.get('total'))), ('Planned Value', _m(pv)), ('Earned Value', _m(ev)),
             ('EV − PV', f'<span style="color:{bad if d < 0 else good}">{"−" if d < 0 else "+"}{_m(abs(d))}</span>'),
             ('SPI', f'{ev / pv:.2f}' if pv else '—')]
    strip = ('<table class="kv5"><tr>' + ''.join(f'<td><div class="t">{t}</div><div class="v">{v}</div></td>' for t, v in tiles)
             + '</tr></table>')
    body = []
    for r in rows:
        dd = (r.get('ev') or 0) - (r.get('pv') or 0)
        col = good if dd >= 0 else (warn if r.get('pv') and dd / r['pv'] > -0.1 else bad)
        body.append(f'<tr><td><b>{_e(r["value"])}</b></td><td class="num">{_m(r.get("bac"))}</td>'
                    f'<td class="num">{(r.get("weight_pct") or 0):.1f}%</td><td class="num">{_m(r.get("pv"))}</td>'
                    f'<td class="num">{_m(r.get("ev"))}</td>'
                    f'<td class="num" style="color:{bad if dd < 0 else good};font-weight:800">{"−" if dd < 0 else "+"}{_m(abs(dd))}</td>'
                    f'<td>{_bar(r.get("actual"), r.get("planned"), col)}'
                    f'<div class="note">{(r.get("actual") or 0):.1f}% earned · {(r.get("planned") or 0):.1f}% planned</div></td></tr>')
    table = ('<table class="ctab"><thead><tr><th>Scope</th><th class="num">Cost</th><th class="num">Weight</th>'
             '<th class="num">Planned Value</th><th class="num">Earned Value</th><th class="num">EV − PV</th>'
             '<th>Earned vs planned</th></tr></thead><tbody>' + ''.join(body) + '</tbody></table>')
    note = ('<div class="note">Planned Value = Cost × planned % at the data date · Earned Value = Cost × actual % · '
            'bar = earned %, marker = planned %</div>')
    recs = ''.join(f'<p>{_e(t)}</p>' for t in s.get('recommendation', []))
    rec = (f'<div class="rec" data-part="scope.recommendation" data-part-label="Recommendation">'
           f'<h4>◆ Recommendation</h4>{recs}</div>') if recs else ''
    return (f'<div class="scope-h">Scope by <b>{_e(ct)}</b> · cost-loaded construction scope</div>'
            + f'<div data-part="scope.bars" data-part-label="Scope by {_e(ct)} — Cost, Planned Value, Earned Value">'
            + strip + table + note + '</div>' + rec)


# ── Section 4 · Planned vs Actual by activity count ─────────────────────────

def _counts_rows(c):
    """The WBS rows the screen shows (all, or the WBS the planner picked)."""
    rows = c.get('by_wbs') or []
    shown = c.get('wbs_shown')
    if isinstance(shown, list) and shown:
        keep = set(shown)
        return [r for r in rows if r.get('wbs') in keep], rows
    return rows, rows


def _counts_html(report):
    """Section 4 - Planned vs Actual by COUNT of activities, per WBS (15-Oct redesign). Actual =
    P6 Activity Status, Planned = baseline dates at the data date - the same rows as the screen."""
    c = report.get('counts', {}) or {}
    shown, rows = _counts_rows(c)
    if not c or not c.get('total') or not rows:
        return '<p class="note">No activities to count in this update.</p>'
    good, bad, warn = report_theme.var('rpt-good'), report_theme.var('rpt-bad'), report_theme.var('rpt-warn')

    def line(name, n, p, a, bold=False):
        pp = 100.0 * p[0] / n if n else 0.0
        ap = 100.0 * a[0] / n if n else 0.0
        g = ap - pp
        col = good if g >= -0.05 else (warn if g > -10 else bad)
        st = ' style="font-weight:800;border-top:2px solid #cbd5e1"' if bold else ''
        cells = ''.join(f'<td class="num"><b>{a[i]:,}</b> <span class="note">/ {p[i]:,}</span></td>' for i in range(3))
        return (f'<tr{st}><td>{_e(name)}</td><td class="num">{n:,}</td>{cells}'
                f'<td>{_bar(ap, pp, col)}<div class="note">{ap:.1f}% actual · {pp:.1f}% planned</div></td>'
                f'<td class="num" style="font-weight:800;color:{bad if g < -0.05 else (good if g > 0.05 else "inherit")}">{"+" if g > 0 else ""}{g:.1f}</td></tr>')

    def total(lst):
        return (sum(r['activities'] for r in lst), [sum(r['planned'][i] for r in lst) for i in range(3)],
                [sum(r['actual'][i] for r in lst) for i in range(3)])
    body = ''.join(line(r['wbs'], r['activities'], r['planned'], r['actual']) for r in shown)
    if not c.get('code_filter'):          # one activity-code value picked: no total rows (15-Oct)
        if len(shown) != len(rows):
            n, p, a = total(shown)
            body += line(f'Shown WBS ({len(shown)} of {len(rows)})', n, p, a, True)
        n, p, a = total(rows)
        body += line('Whole schedule', n, p, a, True)
    nb = (f' · {c["no_baseline"]:,} activities have no baseline dates (counted as planned Not Started)'
          if c.get('no_baseline') else '')
    return (f'<div class="note">Actual = P6 Activity Status (Completed / In Progress / Not Started) · '
            f'Planned = baseline dates at the data date{nb}</div>'
            '<table class="ctab"><thead><tr><th>WBS</th><th class="num">Activities</th>'
            '<th class="num">Completed<br><span class="note">actual / planned</span></th>'
            '<th class="num">In Progress<br><span class="note">actual / planned</span></th>'
            '<th class="num">Not Started<br><span class="note">actual / planned</span></th>'
            '<th>% complete by count</th><th class="num">Gap</th></tr></thead><tbody>' + body + '</tbody></table>'
            '<div class="note">bar = actual % complete by count, marker = planned · gap = actual − planned (points)</div>')


# ── Assembly ────────────────────────────────────────────────────────────────

def render_html(report, sections=None, code_filter=None, scope_code=None, theme='light'):
    """`sections` = list of keys to include (None = all): time · bycode · driving · counts ·
    scope · scurve (an older saved selection's 'conclusion' now lives inside time). `code_filter` = {'types': [...]} picks Section 2's charts;
    `scope_code` picks Section 5's activity-code dimension."""
    header = (f'<div class="rh"><div><h1>{_e(report.get("title") or "Update Analysis")}</h1>'
              f'<div class="meta">{_e(report.get("project_name"))} · single-update read against its baseline</div>'
              + (f'<div class="meta">Baseline: {_e(report.get("baseline_label"))}</div>' if report.get('baseline_label') else '')
              + '</div>'
              f'<div class="win">Data date<br><b>{_fdate(report.get("data_date"))}</b>'
              f'<br>{_e(report.get("file") or "")}</div></div>')
    secs = [
        ('time', '1 · Time Status', _summary_html(report) + _timestatus_html(report, cost_only=True)),
        ('bycode', '2 · Planned vs Actual — by activity code', _bycode_html(report, code_filter)),
        ('driving', '3 · Driving Path Analyzer', _driving_html(report)),
        ('counts', '4 · Planned vs Actual — by activity count', _counts_html(report)),
        ('scope', '5 · Scope Weight & Recommendation', _scope_html(report, scope_code)),
        ('scurve', '6 · Progress S-curve', _scurve_html(report)),
    ]
    keys = set(sections) if sections else None
    if keys is not None and 'conclusion' in keys:   # the old opening line is now the verdict
        keys.add('time')
    body = [header]
    for key, title, htmls in secs:
        if keys is not None and key not in keys:
            continue
        whole = ' data-parts="none"' if key == 'counts' else ''     # one chart: ticked as a whole
        body.append(f'<section class="sec-{key}" data-sec="{key}"{whole}><h2>{_e(title)}</h2>{htmls}</section>')
    _ink = report_theme.var('rpt-ink')
    _muted = report_theme.var('rpt-muted')
    _edge = report_theme.var('rpt-edge')
    _surface = report_theme.var('rpt-surface')
    _accent_soft = report_theme.var('rpt-accent-soft')
    _good = report_theme.var('rpt-good')
    _good_bg = report_theme.var('rpt-good-bg')
    _warn = report_theme.var('rpt-warn')
    _bad = report_theme.var('rpt-bad')
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 11mm; }}
      * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      body {{ font-family: system-ui, -apple-system, Arial, sans-serif; color: {_ink}; font-size: 12px; margin: 0; }}
      h1 {{ font-size: 21px; margin: 0 0 2px; }}
      h2 {{ font-size: 14px; margin: 18px 0 8px; color: {_BLUE}; border-bottom: 2px solid {_BLUE}; padding-bottom: 4px; }}
      h3 {{ font-size: 13px; margin: 0 0 10px; color: {_BLUE}; }}
      .rh {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid {_BLUE}; padding-bottom: 10px; margin-bottom: 12px; }}
      .rh .meta {{ color: {_muted}; font-size: 11.5px; }} .rh .win {{ text-align: right; font-size: 11.5px; color: {_muted}; }} .rh .win b {{ color: {_ink}; font-size: 13px; }}
      section {{ page-break-inside: avoid; }}
      .reco {{ border: 1px solid {_edge}; border-left: 4px solid {_BLUE}; border-radius: 0 8px 8px 0; padding: 10px 14px; line-height: 1.6; }}
      .note {{ color: {_muted}; font-style: italic; }}
      .mono {{ font-variant-numeric: tabular-nums; }} .neg {{ color: {_bad}; }} .pos {{ color: {_good}; }}
      /* Time status */
      .ts {{ display: flex; gap: 22px; align-items: center; border: 1px solid {_edge}; border-radius: 10px; padding: 14px 16px; }}
      .ts-sentence {{ font-size: 15px; line-height: 1.5; }}
      .verdicts {{ margin-top: 10px; display: flex; flex-direction: column; gap: 7px; }}
      .vrow {{ display: flex; gap: 10px; font-size: 12.5px; }} .vtag {{ flex: none; width: 108px; font-weight: 700; }}
      .vtag.bad {{ color: {_bad}; }} .vtag.good {{ color: {_good}; }}
      .cost {{ margin-top: 12px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
      .costcard {{ border: 1px solid {_edge}; border-radius: 8px; padding: 10px 13px; }}
      .costcard .cl {{ font-size: 10.5px; color: {_muted}; text-transform: uppercase; letter-spacing: .3px; }}
      .costcard .cv {{ font-size: 17px; font-weight: 800; margin-top: 3px; font-variant-numeric: tabular-nums; }}
      /* Summary band */
      .verdict .vline {{ display: flex; gap: 12px; align-items: flex-start; border: 1px solid {_edge}; border-left: 5px solid {_bad}; border-radius: 0 8px 8px 0; padding: 10px 14px; margin-bottom: 10px; }}
      .verdict.on_track .vline {{ border-left-color: {_good}; }} .verdict.baseline .vline {{ border-left-color: {_BLUE}; }}
      .pill {{ flex: none; font-weight: 800; font-size: 11px; padding: 3px 10px; border-radius: 12px; border: 1px solid {_bad}; color: {_bad}; }}
      .verdict.on_track .pill {{ border-color: {_good}; color: {_good}; }} .verdict.baseline .pill {{ border-color: {_BLUE}; color: {_BLUE}; }}
      .vh {{ font-size: 14px; font-weight: 700; }} .vd {{ font-size: 11.5px; color: {_muted}; margin-top: 2px; }}
      .kpis {{ width: 100%; border-collapse: separate; border-spacing: 8px 0; margin: 0 -8px 10px; table-layout: fixed; }}
      .kpi {{ border: 1px solid {_edge}; border-top: 4px solid {_muted}; border-radius: 8px; padding: 7px 9px; vertical-align: top; }}
      .kpi.bad {{ border-top-color: {_bad}; }} .kpi.good {{ border-top-color: {_good}; }}
      .kl {{ font-size: 9.5px; color: {_muted}; text-transform: uppercase; font-weight: 700; letter-spacing: .3px; }}
      .kv {{ font-size: 17px; font-weight: 800; font-variant-numeric: tabular-nums; }} .kv.kd {{ font-size: 14px; }}
      .kpi.bad .kv {{ color: {_bad}; }} .kpi.good .kv {{ color: {_good}; }}
      .ks {{ font-size: 10px; color: {_muted}; }}
      .prog {{ border: 1px solid {_edge}; border-radius: 10px; padding: 10px 14px; }}
      .progt {{ width: 100%; border-collapse: collapse; }} .progt td {{ vertical-align: middle; }} .progt td.don {{ width: 170px; text-align: center; }}
      .donleg {{ font-size: 10px; color: {_muted}; }}
      .gapnote {{ font-size: 12px; margin-top: 4px; }}
      /* S-curve */
      /* section 6 starts a page so its heading stays with the chart (house page rule) */
      section.sec-scurve {{ break-before: page; page-break-before: always; page-break-inside: auto; }}
      section.sec-scurve:first-of-type {{ break-before: auto; page-break-before: auto; }}
      h2 {{ break-after: avoid; page-break-after: avoid; }}
      [data-part="scurve.chart"] {{ break-inside: avoid; page-break-inside: avoid; }}
      .scnote {{ font-size: 11px; color: {_muted}; line-height: 1.5; margin: 6px 0 8px; }} .scnote b {{ color: {_ink}; }}
      .ctab tr.ddrow td {{ font-weight: 800; background: {_accent_soft}; }}
      /* By code */
      .chart2 {{ border: 1px solid {_edge}; border-radius: 10px; padding: 12px 14px; margin-bottom: 12px; }}
      .bc-row {{ margin-bottom: 12px; }} .bc-name {{ font-size: 12px; font-weight: 600; margin-bottom: 3px; }}
      .bc-track {{ height: 13px; background: {_surface}; border-radius: 3px; overflow: hidden; margin-bottom: 3px; }}
      .bc-pl {{ height: 100%; background: {_PLAN}; }} .bc-ac {{ height: 100%; background: {_ACT}; }}
      .bc-num {{ font-size: 11px; color: {_muted}; }}
      .bc-leg {{ font-size: 11px; color: {_muted}; margin-top: 4px; }} .bc-leg span {{ margin-right: 16px; }}
      .bc-leg i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: middle; margin-right: 6px; }}
      /* Driving path */
      .dphead {{ background: {_accent_soft}; border: 1px solid {_edge}; border-radius: 8px; padding: 10px 14px; font-size: 12.5px; line-height: 1.5; margin-bottom: 12px; }}
      .chain {{ display: flex; align-items: stretch; flex-wrap: wrap; gap: 5px; margin-bottom: 8px; }}
      .arw {{ display: flex; align-items: center; color: {_muted}; font-weight: 900; font-size: 15px; }}
      .msbox {{ flex: none; width: 188px; border: 2px solid {_BLUE}; border-radius: 10px; padding: 10px 11px; background: {_accent_soft}; }}
      .msbox.start {{ border-color: {_good}; background: {_good_bg}; }}
      .msbox.start .msflag, .msbox.start .mst {{ color: {_good}; }}
      .msbox .msflag {{ font-size: 9px; text-transform: uppercase; letter-spacing: .4px; color: {_BLUE}; opacity: .8; margin-bottom: 6px; }}
      .msbox .mst {{ font-size: 12px; font-weight: 800; color: {_BLUE}; line-height: 1.2; margin-bottom: 6px; }}
      .msbox .r {{ display: flex; justify-content: space-between; font-size: 11px; margin: 2px 0; }} .msbox .r span {{ color: {_muted}; }}
      .box {{ flex: none; width: 184px; border: 1px solid {_edge}; border-radius: 10px; padding: 9px 11px; }}
      .box.done {{ border-color: {_good}; background: {_good_bg}; }}
      .box .bt {{ font-size: 12px; font-weight: 700; line-height: 1.2; }} .box .bc {{ font-size: 9.5px; color: {_muted}; margin: 3px 0 8px; }}
      .bx-tag {{ font-size: 8px; color: {_warn}; font-weight: 600; }}
      .b4 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 8px; }}
      .b4 .k {{ font-size: 9px; color: {_muted}; text-transform: uppercase; letter-spacing: .3px; }}
      .b4 .v {{ font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; }} .b4 .full {{ grid-column: 1 / -1; border-top: 1px dashed {_edge}; padding-top: 4px; }}
      /* Counts */
      .cn-total {{ font-size: 12.5px; margin-bottom: 10px; }}
      .cn-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}
      .cn-lbl {{ flex: none; width: 110px; font-size: 12.5px; font-weight: 600; }}
      .cn-bars {{ flex: 1; }}
      .cn-track {{ position: relative; height: 18px; background: {_surface}; border-radius: 4px; margin: 3px 0; overflow: hidden; }}
      .cn-track span {{ position: absolute; left: 8px; top: 1px; font-size: 11px; font-weight: 700; color: {_ink}; }}
      .cn-pl {{ height: 100%; background: {_PLAN}; opacity: .85; }} .cn-ac {{ height: 100%; background: {_ACT}; opacity: .85; }}
      /* Scope */
      .scope-h {{ font-size: 12.5px; color: {_muted}; margin-bottom: 12px; }}
      .ctab {{ width: 100%; border-collapse: collapse; font-size: 11.5px; margin: 6px 0; }}
      .ctab th {{ text-align: left; font-size: 10px; color: {_muted}; text-transform: uppercase; letter-spacing: .3px; padding: 5px 6px; border-bottom: 2px solid {_edge}; }}
      .ctab td {{ padding: 5px 6px; border-bottom: 1px solid {_edge}; vertical-align: middle; }}
      .ctab .num {{ text-align: right; white-space: nowrap; }}
      .ctab .note {{ font-style: normal; font-size: 10px; }}
      .kv5 {{ width: 100%; border-collapse: separate; border-spacing: 8px 0; margin: 4px -8px 8px; }}
      .kv5 td {{ background: {_surface}; border: 1px solid {_edge}; border-radius: 8px; padding: 6px 9px; }}
      .kv5 .t {{ font-size: 9.5px; color: {_muted}; text-transform: uppercase; font-weight: 700; }} .kv5 .v {{ font-size: 15px; font-weight: 800; }}
      .wrow {{ display: flex; align-items: center; gap: 12px; margin-bottom: 7px; }}
      .wname {{ flex: none; width: 220px; font-size: 12px; }}
      .wtrack {{ flex: 1; height: 17px; background: {_surface}; border-radius: 4px; overflow: hidden; }}
      .wfill {{ height: 100%; background: {_accent_soft}; }} .wrow.top .wfill {{ background: {_ACT}; }}
      .wpct {{ flex: none; width: 50px; text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }}
      .wcost {{ flex: none; width: 110px; text-align: right; font-variant-numeric: tabular-nums; color: {_muted}; font-size: 11px; }}
      .wpa {{ flex: none; width: 130px; }}
      .wpa-t {{ height: 5px; background: {_surface}; border-radius: 3px; overflow: hidden; margin: 2px 0; }}
      .wpa-pl {{ height: 100%; background: {_PLAN}; }} .wpa-ac {{ height: 100%; background: {_ACT}; }}
      .wpanum {{ font-size: 10px; color: {_muted}; font-variant-numeric: tabular-nums; margin-top: 1px; }}
      .rec {{ margin-top: 14px; background: {_accent_soft}; border: 1px solid {_edge}; border-radius: 10px; padding: 12px 15px; }}
      .rec h4 {{ margin: 0 0 6px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .4px; color: {_BLUE}; }}
      .rec p {{ margin: 5px 0; font-size: 13px; }} .rec .star {{ color: {_BLUE}; font-weight: 800; margin-right: 6px; }}
    </style>{report_theme.theme_style_tag(theme)}</head><body>{"".join(body)}</body></html>'''


# ── Excel: one sheet mirroring the four sections ────────────────────────────

_HEADERS = ['Section', 'Above (WBS)', 'Item', 'Planned', 'Actual', 'Variance / Delay',
            'Baseline Finish', 'Expected Finish']


def report_excel(report):
    """(headers, rows) for a single sheet mirroring the PDF."""
    rows = []
    ts = report.get('time_status', {}) or {}
    elapsed = ('100% (exceeded %d d)' % ts['exceeded_days']) if ts.get('exceeded_days') else (
        f'{ts.get("elapsed_pct")}%' if ts.get('elapsed_pct') is not None else '')
    rows.append(['Time Status', '', f'Time elapsed {elapsed}',
                 ts.get('planned_pct', ''), ts.get('actual_pct', ''), ts.get('behind_plan', ''),
                 _fdate(ts.get('baseline_finish')), ''])
    rows.append(['Time Status — cost', '', 'PV / EV / Variance',
                 _num(ts.get('pv')), _num(ts.get('ev')), _num(ts.get('cost_variance')), '', ''])

    for t, brows in (report.get('by_code', {}) or {}).items():
        for r in brows:
            rows.append([f'Planned vs Actual · {t}', '', r.get('value', ''),
                         r.get('planned', ''), r.get('actual', ''), r.get('variance', ''), '', ''])

    cp = report.get('critical_path', {}) or {}
    for chart in cp.get('charts', []):
        ms = chart.get('milestone', {}) or {}
        rows.append(['Driving Path — milestone', '', ms.get('name', ''),
                     '', '', _svar(ms.get('slip_days')), _fdate(ms.get('baseline_finish')), _fdate(ms.get('expected_finish'))])
        for b in chart.get('boxes', []):
            rows.append(['Driving Path — work front', b.get('crumb', ''), b.get('name', ''),
                         b.get('planned', ''), b.get('pct', ''), _svar(b.get('slip_days')),
                         _fdate(b.get('bl_finish')), _fdate(b.get('exp_finish'))])

    c = report.get('counts', {}) or {}
    if c:
        for label, pk, ak in [('Completed', 'planned_completed', 'actual_completed'),
                              ('In Progress', 'planned_in_progress', 'actual_in_progress'),
                              ('Not Started', 'planned_not_started', 'actual_not_started')]:
            rows.append(['Activity count', '', label, c.get(pk, 0), c.get(ak, 0), '', '', ''])

    scope = report.get('scope', {}) or {}
    dflt = report.get('scope_default')
    s = scope.get(dflt) if dflt in scope else (next(iter(scope.values())) if scope else None)
    if s:
        for r in s.get('rows', []):
            rows.append([f'Scope weight · {s.get("code_type")}', '', r.get('value', ''),
                         '', '', f'{r.get("weight_pct", 0)}%', '', _num(r.get('bac'))])
        for t in s.get('recommendation', []):
            rows.append(['Scope recommendation', '', t, '', '', '', '', ''])
    return _HEADERS, rows


# ── Excel (standard): sheets mirroring the on-screen sections ────────────────
# The tool-wide Excel standard — one titled block per report section, full self-explaining
# headers WITH UNITS, readable %/date strings — consumed by
# p6_evm.xlsx_writer.write_sections_xlsx. `report_excel` (the flat table above) is kept
# intact for any caller that still wants it. This feature colours progress green/red
# (behind vs ahead), not the Critical/High/Medium/Low badge system the shared writer's
# `severity_col` colours, so no severity column is used — that would misrepresent the
# report; the sign of each variance/delay carries the same meaning in words instead.


def _xdate(iso):
    """ISO date → '09 Feb 2026' (the tool-wide Excel date standard)."""
    if not iso:
        return '—'
    try:
        return datetime.strptime(str(iso)[:10], '%Y-%m-%d').strftime('%d-%b.%Y')
    except Exception:
        return str(iso)


def _pcts(v, dec=1):
    """A percent value already on the 0–100 scale → '61.42%' / '33.7%'; '—' when absent."""
    return f'{v:.{dec}f}%' if isinstance(v, (int, float)) and not isinstance(v, bool) else '—'


def _pts(v, dec=2):
    """A signed points figure (a difference, not a percentage) → '+13.20' / '-5.00'."""
    return f'{v:+.{dec}f}' if isinstance(v, (int, float)) and not isinstance(v, bool) else '—'


def _days(v):
    """Working-days delay → '+5 d' (later) / '-3 d' (earlier) / '0 d'; '—' when absent."""
    if v is None:
        return '—'
    try:
        return f'+{v} d' if v > 0 else f'{v} d'
    except Exception:
        return str(v)


def _cost(v):
    """Numeric cost cell (header carries the 'cost' meaning); '—' when absent."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else '—'


def report_excel_sections(report):
    """Return the `sheets` structure for `write_sections_xlsx`, mirroring the on-screen /
    PDF Update-Analysis report: the Executive read, then Sections 1–5 as clearly-titled
    tables with full, unit-bearing headers and readable %/date formatting.

    Only sections whose data exists are emitted. `report_excel` (the legacy flat table) is
    left untouched. The server passes the header/context block itself via `meta=` — these
    sheets start with the first real section, per the shared contract.
    """
    report = report or {}
    ts = report.get('time_status', {}) or {}
    by = report.get('by_code', {}) or {}
    cp = report.get('critical_path', {}) or {}
    counts = report.get('counts', {}) or {}
    scope = report.get('scope', {}) or {}

    sheets = []
    # Is there any real time-status content? (An empty / no-baseline report has none —
    # then every section below is skipped and the "No data" fallback at the end fires,
    # instead of a Time Status sheet full of em-dashes.)
    has_time = bool(report.get('conclusion')) or any(
        ts.get(k) is not None for k in
        ('elapsed_pct', 'planned_pct', 'actual_pct', 'behind_plan', 'behind_clock',
         'pv', 'ev', 'cost_variance'))

    # ── Sheet 1 · Executive read + Section 1 Time Status ────────────────────
    sm = report.get('summary') or {}
    if sm.get('headline'):                 # the verdict + six key numbers (approved 2026-11-23)
        blocks = [{
            'title': f"1 - Time Status - {sm.get('label') or 'Summary'}",
            'headers': ['Verdict'],
            'rows': [[sm.get('headline')], [sm.get('detail') or '']],
        }, {
            'title': '1 - Time Status - Key numbers',
            'headers': ['Measure', 'Value', 'Note'],
            'rows': [[k.get('label'), k.get('value'), k.get('sub') or ''] for k in sm.get('kpis') or []],
        }]
    else:
        blocks = [{
            'title': 'Executive Read',
            'headers': ["Planner's summary"],
            'rows': [[report.get('conclusion') or '—']],
        }]

    if ts.get('exceeded_days'):
        elapsed_txt = f'100% (baseline finish exceeded by {ts["exceeded_days"]} days)'
    elif ts.get('elapsed_pct') is not None:
        elapsed_txt = _pcts(ts.get('elapsed_pct'), 1)
    else:
        elapsed_txt = '—'
    prog_rows = [
        ['Baseline time elapsed', elapsed_txt,
         "Calendar days from the baseline's data date (the earliest baseline start when the file "
         'carries none; a baseline file on its own starts at its own data date) to the data date, '
         'over the whole baseline to its finish'],
        ['Planned progress by data date', _pcts(ts.get('planned_pct'), 2),
         'Planned Value / budget (cost-based, over cost-loaded activities)'],
        ['Earned / actual progress', _pcts(ts.get('actual_pct'), 2),
         'Earned Value / budget'],
    ]
    if ts.get('behind_plan') is not None:
        prog_rows.append(['Behind plan (percentage points)', _pts(ts.get('behind_plan')),
                          'Planned % minus Actual % (positive = behind plan)'])
    if ts.get('behind_clock') is not None:
        prog_rows.append(['Behind clock (percentage points)', _pts(ts.get('behind_clock')),
                          'Time-elapsed % minus Actual % (positive = less work done than time spent)'])
    prog_rows += [
        ['Baseline start', _xdate(ts.get('baseline_start')), ''],
        ['Baseline finish', _xdate(ts.get('baseline_finish')), ''],
        ['Data date', _xdate(ts.get('data_date') or report.get('data_date')), ''],
    ]
    blocks.append({
        'title': '1 - Time Status - Progress vs Baseline Clock',
        'headers': ['Measure', 'Value', 'What it means'],
        'rows': prog_rows,
    })

    if any(ts.get(k) is not None for k in ('pv', 'ev', 'cost_variance')):
        blocks.append({
            'title': '1 - Time Status - Cost (Earned Value)',
            'headers': ['Measure', 'Amount (project cost)'],
            'rows': [
                ['Planned Value (PV)', _cost(ts.get('pv'))],
                ['Earned Value (EV)', _cost(ts.get('ev'))],
                ['Variance (EV minus PV)', _cost(ts.get('cost_variance'))],
            ],
        })
    if has_time:
        sheets.append({'name': 'Time Status', 'blocks': blocks})

    # ── Sheet 2 · Section 2 Planned vs Actual by activity code ──────────────
    code_blocks = []
    for t, rows in by.items():
        if not rows:
            continue
        code_blocks.append({
            'title': f'2 - Planned vs Actual - by {t}',
            'note': 'Cumulative planned vs actual %, cost-weighted; worst gap first.',
            'headers': [str(t), 'Planned % (vs baseline)', 'Actual % (complete)',
                        'Variance (pts, actual minus planned)', 'Activities (count)'],
            'rows': [[r.get('value', ''), _pcts(r.get('planned'), 1), _pcts(r.get('actual'), 1),
                      _pts(r.get('variance'), 1), r.get('activity_count', 0)] for r in rows],
        })
    if code_blocks:
        sheets.append({'name': 'By Activity Code', 'blocks': code_blocks})

    # ── Sheet 3 · Section 3 Driving Path Analyzer ───────────────────────────
    charts = cp.get('charts') or []
    if charts:
        dp_blocks = []
        for chart in charts:
            ms = chart.get('milestone', {}) or {}
            sm = chart.get('start_milestone') or {}
            note = cp.get('headline') or ''
            if sm.get('name'):
                note = ((note + ' ') if note else '') + \
                    f'Path released by start milestone "{sm.get("name")}" on {_xdate(sm.get("date"))}.'
            dp_blocks.append({
                'title': f'3 - Driving Path - Governing Milestone: {ms.get("name", "")}',
                'note': note,
                'headers': ['Governing completion milestone', 'Baseline Finish',
                            'Expected Finish', 'Delay (working days)'],
                'rows': [[ms.get('name', ''), _xdate(ms.get('baseline_finish')),
                          _xdate(ms.get('expected_finish')), _days(ms.get('slip_days'))]],
            })
            boxes = chart.get('boxes') or []
            dp_blocks.append({
                'title': 'Work Fronts on the Driving Path (in path order)',
                'headers': ['Work Front', 'Above (WBS path)', 'Type',
                            'Planned % (vs baseline)', 'Actual % (complete)',
                            'Baseline Finish', 'Expected Finish', 'Delay (working days)'],
                'rows': [[b.get('name', ''), b.get('crumb', ''),
                          ('WBS rollup' if b.get('source') == 'wbs' else 'Activity (no cost in WBS)'),
                          _pcts(b.get('planned'), 1), _pcts(b.get('pct'), 1),
                          _xdate(b.get('bl_finish')), _xdate(b.get('exp_finish')),
                          _days(b.get('slip_days'))] for b in boxes],
            })
        sheets.append({'name': 'Driving Path', 'blocks': dp_blocks})

    # ── Sheet 4 · Section 4 Planned vs Actual by activity count, per WBS ────
    if counts and counts.get('total') and counts.get('by_wbs'):
        shown, allrows = _counts_rows(counts)

        def xrow(name, n, p, a):
            pp = round(100.0 * p[0] / n, 1) if n else 0.0
            ap = round(100.0 * a[0] / n, 1) if n else 0.0
            return [name, n, a[0], p[0], a[1], p[1], a[2], p[2], _pcts(pp, 1), _pcts(ap, 1), round(ap - pp, 1)]
        crow = [xrow(r['wbs'], r['activities'], r['planned'], r['actual']) for r in shown]
        for label, lst in (() if counts.get('code_filter') else
                           ((f'Shown WBS ({len(shown)} of {len(allrows)})', shown) if len(shown) != len(allrows) else (None, None),
                            ('Whole schedule', allrows))):
            if label:
                crow.append(xrow(label, sum(r['activities'] for r in lst), [sum(r['planned'][i] for r in lst) for i in range(3)],
                                 [sum(r['actual'][i] for r in lst) for i in range(3)]))
        note = ('Actual = P6 Activity Status (Completed / In Progress / Not Started). Planned = baseline dates at the '
                'data date (finish on or before it = Completed, start on or before it = In Progress).'
                + (f' {counts["no_baseline"]} activities have no baseline dates (counted as planned Not Started).'
                   if counts.get('no_baseline') else ''))
        sheets.append({'name': 'Activity Counts', 'blocks': [{
            'title': '4 - Planned vs Actual - by count of activities, per WBS',
            'note': note,
            'headers': ['WBS', 'Activities', 'Completed - actual', 'Completed - planned', 'In Progress - actual',
                        'In Progress - planned', 'Not Started - actual', 'Not Started - planned',
                        'Planned % complete (count)', 'Actual % complete (count)', 'Gap (points)'],
            'rows': crow,
        }]})

    # ── Sheet 5 · Section 5 Scope Weight & Recommendation ───────────────────
    dflt = report.get('scope_default')
    s = scope.get(dflt) if dflt in scope else (next(iter(scope.values())) if scope else None)
    if s and s.get('rows'):
        ct = s.get('code_type', 'Scope')
        scope_blocks = [{
            'title': f'5 - Scope by Cost - by {ct}',
            'note': ('Cost = baseline cost of each scope. Planned Value = Cost x planned % at the data date. '
                     'Earned Value = Cost x actual %. SPI = Earned Value / Planned Value.'),
            'headers': [str(ct), 'Cost', 'Weight (% of cost)', 'Planned Value', 'Earned Value', 'EV - PV', 'SPI',
                        'Planned %', 'Actual %'],
            'rows': [[r.get('value', ''), _cost(r.get('bac')), _pcts(r.get('weight_pct'), 1), _cost(r.get('pv')),
                      _cost(r.get('ev')), _cost(r.get('ev_minus_pv')), r.get('spi'),
                      _pcts(r.get('planned'), 1), _pcts(r.get('actual'), 1)] for r in s['rows']]
                    + [['Total', _cost(s.get('total')), _pcts(100.0, 1), _cost(s.get('pv')), _cost(s.get('ev')),
                        _cost(s.get('ev_minus_pv')), s.get('spi'), '', '']],
        }]
        recs = s.get('recommendation') or []
        if recs:
            scope_blocks.append({
                'title': '5 - Recommendation',
                'headers': ['Recommendation'],
                'rows': [[t] for t in recs],
            })
        sheets.append({'name': 'Scope Weight', 'blocks': scope_blocks})

    # The screen lets the planner switch the scope-weight breakdown to any activity code; the
    # workbook carries every one of them, not only the one shown first (owner comment 29).
    all_rows = []
    for key, sc in (scope or {}).items():
        ct = (sc or {}).get('code_type') or key
        for r in (sc or {}).get('rows') or []:
            all_rows.append([str(ct), r.get('value', ''), _pcts(r.get('weight_pct'), 1), _cost(r.get('bac')),
                             _cost(r.get('pv')), _cost(r.get('ev')), _cost(r.get('ev_minus_pv')),
                             _pcts(r.get('planned'), 1), _pcts(r.get('actual'), 1)])
    if len(scope or {}) > 1 and all_rows:
        sheets.append({'name': 'Scope Weight - All Codes', 'blocks': [{
            'title': '5 - Scope by Cost - by every activity code',
            'note': "Each value's share of the cost-loaded scope, with its Planned Value and Earned Value, per activity code.",
            'headers': ['Activity code', 'Code value', 'Weight (% of cost)', 'Cost', 'Planned Value', 'Earned Value',
                        'EV - PV', 'Planned %', 'Actual %'],
            'rows': all_rows,
        }]})

    # ── Section 6 Progress S-curve (approved 2026-11-23) ────────────────────
    sc = report.get('scurve') or {}
    pts = sc.get('points') or []
    if pts:
        src = lambda p: 'earlier update' if p.get('earned_source') == 'update' else (p.get('earned_source') or '')
        gap = lambda p: (_pts(p['earned'] - p['planned']) if p.get('earned') is not None
                         and p.get('planned') is not None else '')
        sc_blocks = [{
            'title': '6 - Progress S-curve - monthly values',
            'note': ('Planned = the Time Status Planned % rule at every month end; Earned = rebuilt from each '
                     "activity's actual dates, or an earlier imported update of the same job at its data date; "
                     "Forecast = remaining work over P6's remaining dates. At the data date all equal Time Status."),
            'headers': ['Date', 'Point', 'Planned %', 'Earned %', 'Forecast %', 'Gap (pts, earned minus planned)',
                        'Earned from'],
            'rows': [[_xdate(p['date']), {'data_date': 'data date', 'update': 'earlier update'}.get(p['kind'], 'month end'),
                      _pcts(p.get('planned'), 2) if p.get('planned') is not None else '',
                      _pcts(p.get('earned'), 2) if p.get('earned') is not None else '',
                      _pcts(p.get('forecast'), 2) if p.get('forecast') is not None else '',
                      gap(p), src(p)] for p in pts],
        }]
        on = [e for e in sc.get('earlier') or [] if e.get('on')]
        if on:
            sc_blocks.append({
                'title': '6 - Progress S-curve - earlier updates on the curve',
                'headers': ['Data date', 'Schedule', 'Earned %', 'Linked by'],
                'rows': [[_xdate(e.get('data_date')), e.get('label') or e.get('file') or '',
                          _pcts(e.get('earned'), 2), 'same baseline' if e.get('auto') else 'added by hand'] for e in on],
            })
        sheets.append({'name': 'Progress S-curve', 'blocks': sc_blocks})

    if not sheets:
        sheets = [{'name': 'Update Analysis', 'blocks': [{
            'title': 'Update Analysis',
            'headers': ['Metric', 'Value'],
            'rows': [['No data', 'Run Update Analysis on a schedule with a baseline first.']],
        }]}]
    return sheets
