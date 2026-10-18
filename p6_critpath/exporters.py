"""PDF (print HTML) and Excel exporters for the Critical Path Analyzer.

render_html builds a landscape, print-ready page from the report the client already
holds (no re-parse). Every section is wrapped in <section data-sec="KEY"> so the
preview's Report Contents picker can toggle it and the PDF re-flows. Print colours are
theme tokens (`--rpt-*`, injected via report_theme.theme_style_tag) so the same markup
renders in every appearance mode — see report_theme.py.
"""

import report_theme
from utils import date_text as _date_text

# Module colour constants, resolved at render time via the injected `--rpt-*` custom
# properties (see report_theme.py). Verified usage before mapping:
#   _BAD/_WARN/_GOOD/_MUTED -> the census/milestone/dashboard "critical / near / safe"
#                              semantic states (red/amber/green/grey), unchanged meaning
#   _ACCENT                 -> the page's one brand blue, reused everywhere as heading /
#                              link / "current"-role colour, not a chart-series colour
#   _GRID / _AXIS_TXT       -> chart gridlines/reference lines vs. bar/point value labels
#   Driving-path lane states (NEW ON PATH / LEFT PATH / stayed / complete):
#     - complete (bdone)  -> _GOOD  (already green; finished work, unambiguous)
#     - new on path (bnew)-> _BAD   (already red in the source design; a newly-critical
#                                    front is the headline risk of the report)
#     - left path (bleft) -> NEUTRAL (hair-strong/surface-2/muted; kept neutral as in the
#                                    source design — a front leaving the critical path isn't
#                                    inherently bad, and must stay visually distinct from the
#                                    red "new on path" alarm)
#     - stayed (default)  -> neutral edge/surface tokens, no semantic colour
_BAD = report_theme.var('rpt-bad')
_BAD_BG = report_theme.var('rpt-bad-bg')
_WARN = report_theme.var('rpt-warn')
_GOOD = report_theme.var('rpt-good')
_MUTED = report_theme.var('rpt-muted')
_ACCENT = report_theme.var('rpt-accent')
_GRID = report_theme.var('rpt-chart-grid')
_AXIS_TXT = report_theme.var('rpt-chart-axis')
_EDGE = report_theme.var('rpt-edge')
_BG = report_theme.var('rpt-bg')

_ROLE_LABEL = {'baseline': 'Baseline', 'previous': 'Previous update', 'current': 'Current update'}
_ROLE_SHORT = {'baseline': 'Baseline', 'previous': 'Previous', 'current': 'Current'}
_STATUS_HEX = {'good': (_GOOD, report_theme.var('rpt-good-bg')), 'warn': (_WARN, report_theme.var('rpt-warn-bg')),
               'bad': (_BAD, _BAD_BG)}


def _e(v):
    v = _date_text(v)                     # an ISO date shows as 03-Dec.2026 (comment 46)
    if v is None:
        return ''
    return (str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _n1(v):
    """A day count as P6 shows it: whole when whole, else one decimal. A float carried from
    hours (total float 341.33 h / 8) printed as -42.666666666666664 on the cards."""
    if isinstance(v, float):
        v = round(v, 1)
        if v == int(v):
            v = int(v)
    return v


def _sd(v, suffix=' d'):
    if v is None:
        return '—'
    v = _n1(v)
    return f"{'+' if v > 0 else ''}{v}{suffix}"


def _cpli(v):
    return 'n/a' if v is None else f"{v:.2f}"


# ── Sections ─────────────────────────────────────────────────────────────────

def _header(report):
    files = report.get('files', {})
    parts = []
    for role in ('baseline', 'previous', 'current'):
        if role in files:
            parts.append(f"{_ROLE_LABEL[role]}: <b>{_e(files[role])}</b>")
    # Data-date window strip — one pill per loaded schedule.
    dd = report.get('data_dates', {})
    strip = []
    for role in ('baseline', 'previous', 'current'):
        if dd.get(role):
            strip.append(f'<span class="ddpill">{_ROLE_SHORT[role]} data date <b>{_e(dd[role])}</b></span>')
    pills = f'<div class="ddstrip">{"".join(strip)}</div>' if strip else ''
    bl = (f'<div class="meta">Baseline: {_e(report.get("baseline_label"))}</div>'
          if report.get('baseline_approx') and report.get('baseline_label') else '')
    return (f'<div class="rh"><div><h1>Critical Path Analyzer</h1>'
            f'<div class="meta">{" &nbsp;·&nbsp; ".join(parts)}</div>{bl}{pills}</div></div>')


def _banner(report):
    d = report.get('dashboard', {})
    status = d.get('status', 'warn')
    hexc, bg = _STATUS_HEX.get(status, _STATUS_HEX['warn'])
    return (f'<div class="banner" style="background:{bg};border-color:{hexc}">'
            f'<span class="btag" style="background:{hexc}">{_e(d.get("status_label"))}</span>'
            f'<span class="btext">{_e(report.get("conclusion") or d.get("verdict"))}</span></div>')


# ── Dashboard charts (inline SVG / pure-HTML, theme-token colours) ────────────

def _chart_crit_near(cn):
    """Grouped bars: critical (red) + near-critical (amber) per schedule. A null near
    value (a float-less baseline) is labelled 'n/a' rather than drawn as a measured 0."""
    roles = cn.get('roles', [])
    crit = cn.get('critical', [])
    near = cn.get('near', [])
    if not roles:
        return '<div class="note">No census data to plot.</div>'
    vals = [v for v in (list(crit) + list(near)) if v is not None]
    mx = max(vals) if vals else 0
    if mx <= 0:
        mx = 1
    W, H = 300, 170
    pad_l, pad_r, pad_t, pad_b = 8, 8, 22, 34
    plot_h = H - pad_t - pad_b
    plot_w = W - pad_l - pad_r
    n = len(roles)
    group_w = plot_w / n
    bw = min(26.0, group_w / 3)
    gap = 4.0
    y0 = pad_t + plot_h
    parts = [f'<line x1="{pad_l}" y1="{y0}" x2="{W - pad_r}" y2="{y0}" stroke="{_GRID}" stroke-width="1"/>']
    for i, role in enumerate(roles):
        gx = pad_l + i * group_w + group_w / 2
        pairs = [(crit[i] if i < len(crit) else None, _BAD),
                 (near[i] if i < len(near) else None, _WARN)]
        bx0 = gx - (bw * 2 + gap) / 2
        for j, (val, col) in enumerate(pairs):
            x = bx0 + j * (bw + gap)
            if val is None:
                parts.append(f'<text x="{x + bw / 2:.1f}" y="{y0 - 4:.1f}" font-size="8" '
                             f'fill="{_MUTED}" text-anchor="middle">n/a</text>')
                continue
            bh = (val / mx) * plot_h
            y = y0 - bh
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" '
                         f'fill="{col}" rx="2"/>')
            parts.append(f'<text x="{x + bw / 2:.1f}" y="{y - 3:.1f}" font-size="9" '
                         f'font-weight="700" fill="{_AXIS_TXT}" text-anchor="middle">{val}</text>')
        parts.append(f'<text x="{gx:.1f}" y="{H - pad_b + 14:.1f}" font-size="9" '
                     f'fill="{_MUTED}" text-anchor="middle">{_e(_ROLE_SHORT.get(role, role))}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>')


def _chart_cpli(ct):
    """CPLI trend polyline across schedules, with dashed 0.95 / 1.00 reference lines.
    Null points are skipped; the ends are inset so the first/last labels aren't clipped."""
    roles = ct.get('roles', [])
    values = ct.get('values', [])
    if not roles:
        return '<div class="note">No CPLI trend to plot.</div>'
    pts = [(i, v) for i, v in enumerate(values) if v is not None]
    W, H = 300, 170
    inset = 30.0
    pad_t, pad_b = 18, 30
    plot_h = H - pad_t - pad_b
    n = len(roles)

    def xpos(i):
        if n <= 1:
            return W / 2
        return inset + (W - 2 * inset) * i / (n - 1)

    allv = [v for _, v in pts] + [0.95, 1.0]
    lo, hi = min(allv), max(allv)
    if hi - lo < 0.1:
        lo -= 0.05
        hi += 0.05
    span = hi - lo

    def ypos(v):
        return pad_t + plot_h * (1 - (v - lo) / span)

    parts = []
    for ref, lbl in ((1.0, '1.00'), (0.95, '0.95')):
        y = ypos(ref)
        parts.append(f'<line x1="{inset}" y1="{y:.1f}" x2="{W - inset}" y2="{y:.1f}" '
                     f'stroke="{_GRID}" stroke-width="1" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="2" y="{y + 3:.1f}" font-size="8" fill="{_MUTED}">{lbl}</text>')
    if len(pts) >= 2:
        poly = ' '.join(f'{xpos(i):.1f},{ypos(v):.1f}' for i, v in pts)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{_ACCENT}" stroke-width="2"/>')
    for i, v in pts:
        x, y = xpos(i), ypos(v)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{_ACCENT}"/>')
        parts.append(f'<text x="{x:.1f}" y="{y - 6:.1f}" font-size="9" font-weight="700" '
                     f'fill="{_ACCENT}" text-anchor="middle">{v:.2f}</text>')
    for i, role in enumerate(roles):
        parts.append(f'<text x="{xpos(i):.1f}" y="{H - pad_b + 16:.1f}" font-size="9" '
                     f'fill="{_MUTED}" text-anchor="middle">{_e(_ROLE_SHORT.get(role, role))}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>')


def _chart_ms_variance(msv):
    """Horizontal bars of milestone slip vs baseline (+behind = red, -ahead = green),
    pure HTML so it never clips. Long names ellipsize with a title tooltip."""
    if not msv:
        return '<div class="note">No milestone variance to plot.</div>'
    mx = max((abs(m.get('var') or 0) for m in msv), default=0) or 1
    rows = []
    for m in msv:
        v = m.get('var') or 0
        w = abs(v) / mx * 100
        col = _BAD if v > 0 else (_GOOD if v < 0 else _MUTED)
        name = _e(m.get('name'))
        rows.append(
            f'<div class="mvrow"><div class="mvname" title="{name}">{name}</div>'
            f'<div class="mvbar"><span style="width:{w:.0f}%;background:{col}"></span>'
            f'<b style="color:{col}">{"+" if v > 0 else ""}{v} d</b></div></div>')
    return f'<div class="mvchart">{"".join(rows)}</div>'


def _dashboard(report):
    d = report.get('dashboard', {})
    kpi_cells = []
    for k in d.get('kpis', []):
        if k['value'] is None:
            val = 'n/a'
        elif k['key'] == 'cpli':
            val = f"{k['value']:.2f}"
        else:
            val = k['value']
        unit = ' wd' if k['key'] == 'length' else ''
        delta = '' if k.get('delta') is None else _sd(k['delta'], '')
        # Previous value + variance, so the dashboard reads current vs previous (fix #3).
        pv = k.get('prev')
        if pv is None:
            prev_txt = ''
        else:
            pv = f"{pv:.2f}" if k['key'] == 'cpli' else pv
            prev_txt = f'Previous {pv}{unit}' + (f' · {delta}' if delta else '')
        kpi_cells.append(f'<div class="kpi"><div class="kk">{_e(k["label"])}</div>'
                         f'<div class="kv">{val}{unit} <span class="kcur">current</span></div>'
                         f'<div class="kd">{prev_txt}</div></div>')
    factors = ''.join(f'<li>{_e(f)}</li>' for f in d.get('factors', []))
    dash = (f'<div class="dash" data-part="dashboard.health" data-part-label="Critical path health (CPLI) and key figures">'
            f'<div class="health"><div class="hgauge">{_cpli(d.get("cpli"))}<span>CPLI</span></div>'
            f'<div><div class="htitle">Critical Path Health</div>'
            f'<div class="hverdict">{_e(d.get("verdict"))}</div><ul class="hfactors">{factors}</ul></div></div>'
            f'<div class="kpis">{"".join(kpi_cells)}</div></div>')

    # Charts — everything on screen must reach the PDF (fix #1).
    charts = d.get('charts', {})
    charts_html = ''
    if charts:
        cn = _chart_crit_near(charts.get('crit_near', {}) or {})
        ct = _chart_cpli(charts.get('cpli_trend', {}) or {})
        mv = _chart_ms_variance(charts.get('ms_variance', []) or [])
        charts_html = (
            '<div class="charts">'
            '<div class="chartcard" data-part="dashboard.crit_near" data-part-label="Chart — critical &amp; near-critical by schedule">'
            f'<div class="chartt">Critical &amp; near by schedule</div>{cn}'
            f'<div class="chartlegend"><i style="background:{_BAD}"></i>Critical '
            f'<i style="background:{_WARN}"></i>Near-critical</div></div>'
            '<div class="chartcard" data-part="dashboard.cpli_trend" data-part-label="Chart — CPLI trend">'
            f'<div class="chartt">CPLI trend</div>{ct}</div>'
            '<div class="chartcard" data-part="dashboard.ms_slip" data-part-label="Chart — milestone slip vs baseline">'
            f'<div class="chartt">Milestone slip vs baseline</div>{mv}</div>'
            '</div>')
    return dash + charts_html


def _lane(lane, approx=False):
    role = lane.get('role')
    ax = ' · approx' if approx and role != 'baseline' else ''   # own Planned dates stand in
    ms = lane.get('milestone') or {}
    if not ms.get('name') and not lane.get('boxes'):
        # This milestone doesn't exist in this schedule — show a placeholder, not an empty box.
        return (f'<div class="lane"><div class="lanekeep"><div class="lanehdr"><span class="lanetag lt-{role}">{_e(_ROLE_LABEL.get(role))}</span>'
                f'<span class="lanesub">this milestone is not in this schedule</span></div></div></div>')
    fin = ms.get('baseline_finish') if role == 'baseline' else ms.get('expected_finish')
    boxes = [f'<div class="msbox"><div class="msflag">◆ Milestone</div><div class="mst">{_e(ms.get("name"))}</div>'
             f'<div class="msr"><span>{"BL Finish" if role == "baseline" else "Exp Finish"}</span><b>{_e(fin)}</b></div>'
             f'<div class="msr"><span>Delay{ax}</span><b>{_sd(ms.get("slip_days"))}</b></div></div>']
    lane_boxes = lane.get('boxes', [])
    first_new = next((i for i, x in enumerate(lane_boxes) if x.get('state') == 'new'), -1)
    for i, b in enumerate(lane_boxes):
        st = b.get('state', 'stayed')
        cls = {'new': 'bnew', 'left': 'bleft', 'done': 'bdone'}.get(st, '')
        flag = ('<div class="bflag bfnew">NEW ON PATH</div>' if st == 'new'
                else '<div class="bflag bfleft">LEFT PATH</div>' if st == 'left' else '')
        planned = '—' if b.get('planned') is None else f"{round(b['planned'])}%"
        actual = '—' if b.get('pct') is None else f"{round(b['pct'])}%"
        tf = '—' if b.get('driver_tf') is None else _sd(b.get('driver_tf'), ' wd')
        # A big ▸ leads a box only when it continues the live chain: a stayed/done box, or a NEW box
        # that is not the first. Never before a LEFT box, and never before the START of the new
        # critical path (Ibrahim: "remove the arrow before the new critical path").
        arrow = '' if (st == 'left' or (st == 'new' and i == first_new)) else '<div class="arw">▸</div>'
        boxes.append(
            f'{arrow}<div class="box {cls}">{flag}<div class="bt">{_e(b.get("name"))}</div>'
            f'<div class="bcrumb">{_e(b.get("crumb"))}</div>'
            f'<div class="bgrid">'
            f'<div><div class="bk">Planned{ax}</div><div class="bv">{planned}</div></div>'
            f'<div><div class="bk">Actual</div><div class="bv">{actual}</div></div>'
            f'<div><div class="bk">BL finish{ax}</div><div class="bv">{_e(b.get("bl_finish"))}</div></div>'
            f'<div><div class="bk">Expected</div><div class="bv">{_e(b.get("exp_finish"))}</div></div>'
            f'<div class="bfull"><div class="bk">Slip{ax} / Total float</div><div class="bv">{_sd(b.get("slip_days"))} / {tf}</div></div>'
            f'</div></div>')
    return (f'<div class="lane"><div class="lanekeep"><div class="lanehdr"><span class="lanetag lt-{role}">{_e(_ROLE_LABEL.get(role))}</span>'
            f'<span class="lanesub">{_e(lane.get("sub"))}</span></div></div><div class="chain">{"".join(boxes)}</div></div>')


def _lanes(report, milestone_ids=None):
    blocks = report.get('milestone_paths', [])
    if milestone_ids:                       # limit the PDF to the chosen milestone paths
        wanted = set(milestone_ids)
        blocks = [b for b in blocks if b.get('id') in wanted]
    if not any(any(ln.get('boxes') for ln in b.get('lanes', [])) for b in blocks):
        return '<div class="note">No governing critical path was found in these schedules.</div>'
    legend = (f'<div class="cplegend"><i style="background:{_BAD_BG};border:2px solid {_BAD}"></i>New on critical path '
              f'<i style="background:{_BAD_BG};border:1px dashed {_BAD}"></i>Left the path '
              f'<i style="background:{_BG};border:1px solid {_EDGE}"></i>Stayed '
              f'<i style="background:{_BG};border:1px solid {_GOOD}"></i>Complete</div>')
    out = []
    for bi, b in enumerate(sorted(blocks, key=lambda x: 0 if x.get('is_governing') else 1), 1):
        flag = '◆ ' if b.get('is_governing') else ''
        hdr = (f'<div class="mpkeep"><div class="mphdr"><span class="mpname">{flag}{_e(b.get("name"))}</span>'
               f'<span class="mpfin">Baseline {_e(b.get("baseline_finish")) or "—"} '
               f'· Current {_e(b.get("current_finish")) or "—"} '
               f'· Slip {_sd(b.get("slip_days"))}</span></div></div>')
        lanes_html = ''.join(_lane(l, report.get('baseline_approx')) for l in b.get('lanes', []))
        out.append(f'<div class="mpblock" data-part="driving_path.m{bi}" '
                   f'data-part-label="Path to {_e(b.get("name") or "milestone")}">{hdr}{lanes_html}</div>')
    return ''.join(out) + legend


def _census(report):
    c = report.get('census', {})
    roles = report.get('roles', [])
    has = lambda r: r in roles
    cur, prev, bl = c.get('current', {}), c.get('previous', {}), c.get('baseline', {})

    def cell(r, txt):
        return f'<td class="num">{txt}</td>' if has(r) else ''

    src = lambda r: (c.get(r, {}) or {}).get('critical_source')
    mark = lambda o: '<sup>†</sup>' if o.get('critical_source') == 'path' else ''

    def cnt(o, n, p, m=False):
        return '—' if o.get(n) is None else f"{o[n]} · <b>{o[p]}%</b>{mark(o) if m else ''}"

    def _red(txt):
        # Every census variance is RED (Ibrahim's rule).
        return f'<td class="num" style="color:{_BAD};font-weight:700">{txt}</td>' if txt is not None else '<td class="num">—</td>'

    def _sum_over(key, rs):
        vals = [c.get(r, {}).get(key) for r in rs if has(r)]
        vals = [v for v in vals if v is not None]
        return round(sum(vals), 1) if vals else None

    def dcell(key, unit, cumulative, cum_roles, a_role, b_role):
        if cumulative:                                     # cumulative sum of the % columns
            s = _sum_over(key, cum_roles)
            return _red(None if s is None else f'+{s}{unit}')
        a, b = c.get(a_role, {}).get(key), c.get(b_role, {}).get(key)   # plain difference
        if a is None or b is None:
            return '<td class="num">—</td>'
        dec = 2 if key == 'cpli' else 1 if key.endswith('_pct') else 0   # % deltas keep one decimal
        dd = round(a - b, dec)
        shown = f'{dd:.{dec}f}' if dec else f'{dd}'
        return _red(f'{"+" if dd > 0 else ""}{shown}{unit}')

    def colh(role, label):
        dd = c.get(role, {}).get('data_date')
        sub = f'<div class="thdd">{_e(dd)}</div>' if dd else ''
        return f'<th class="num">{label}{sub}</th>'

    # (label, getter, delta-key, delta-unit, cumulative)  All rows = PLAIN difference now.
    rows = [
        ('Critical activities (P6 Critical filter)', lambda o: cnt(o, 'critical', 'critical_pct', True), 'critical_pct', ' pts', False),
        ('Near-critical (TF 1 to 10 wd)', lambda o: cnt(o, 'near', 'near_pct'), 'near_pct', ' pts', False),
        ('Critical path length (remaining, wd)', lambda o: '—' if o.get('path_length_wd') is None else f"{o['path_length_wd']} wd", 'path_length_wd', ' wd', False),
        ('Total float · finish (wd)', lambda o: '—' if o.get('total_float_wd') is None else f"{o['total_float_wd']} wd", 'total_float_wd', ' wd', False),
        ('CPLI', lambda o: _cpli(o.get('cpli')), 'cpli', '', False),
    ]
    head = ('<tr><th>Measure</th>'
            + (colh('baseline', 'Baseline') if has('baseline') else '')
            + (colh('previous', 'Previous') if has('previous') else '')
            + (colh('current', 'Current') if has('current') else '')
            + ('<th class="num">Δ period</th>' if has('previous') else '')
            + ('<th class="num">Δ baseline</th>' if has('baseline') else '') + '</tr>')
    body = ''
    for label, get, key, unit, cumulative in rows:
        body += ('<tr><td>' + label + '</td>'
                 + cell('baseline', get(bl)) + cell('previous', get(prev)) + cell('current', get(cur))
                 + (dcell(key, unit, cumulative, ['previous', 'current'], 'current', 'previous') if has('previous') else '')
                 + (dcell(key, unit, cumulative, ['baseline', 'previous', 'current'], 'current', 'baseline') if has('baseline') else '') + '</tr>')
    note = ('<div class="note">Every variance is the <b>plain difference</b> — current minus the compared '
            'schedule (e.g. baseline 28% → current 62% = +34 pts). All shown red.</div>')
    foot = ''
    if any(src(r) == 'path' for r in roles):
        foot = ('<div class="note"><b>†</b> This schedule has no activity float in its export, so its critical '
                'count is the activities on the <b>longest path to completion</b> (not TF ≤ 0) — a different basis '
                'than a floated update.</div>')
    return f'<table class="t"><thead>{head}</thead><tbody>{body}</tbody></table>{note}{foot}'


def _milestones(report):
    rows = report.get('milestones', [])
    roles = report.get('roles', [])
    c = report.get('census', {})
    has = lambda r: r in roles
    if not rows:
        return '<div class="note">No finish milestones found.</div>'

    def slip(v):
        if v is None:
            return '—'
        col = _BAD if v > 0 else _GOOD if v < 0 else _MUTED
        return f'<span style="color:{col};font-weight:700">{"+" if v > 0 else ""}{v} d</span>'

    def colh(role, label):
        dd = c.get(role, {}).get('data_date')
        sub = f'<div class="thdd">{_e(dd)}</div>' if dd else ''
        return f'<th class="num">{label}{sub}</th>'

    head = ('<tr><th>Milestone</th>'
            + (colh('baseline', 'Baseline') if has('baseline') else '')
            + (colh('previous', 'Previous') if has('previous') else '')
            + (colh('current', 'Current') if has('current') else '')
            + '<th class="num">vs Baseline</th>' + ('<th class="num">This period</th>' if has('previous') else '') + '</tr>')
    body = ''
    for m in rows:
        f = m.get('finishes', {})
        body += ('<tr' + (' class="gov"' if m.get('is_governing') else '') + '><td>'
                 + ('◆ ' if m.get('is_governing') else '') + _e(m.get('name')) + '</td>'
                 + (f'<td class="num">{_e(f.get("baseline"))}</td>' if has('baseline') else '')
                 + (f'<td class="num">{_e(f.get("previous"))}</td>' if has('previous') else '')
                 + (f'<td class="num">{_e(f.get("current"))}</td>' if has('current') else '')
                 + f'<td class="num">{slip(m.get("var_vs_baseline_d"))}</td>'
                 + (f'<td class="num">{slip(m.get("var_this_period_d"))}</td>' if has('previous') else '')
                 + '</tr>')
    return f'<table class="t"><thead>{head}</thead><tbody>{body}</tbody></table>'


_MIG_RULES = {
    'near_to_crit': 'near-critical (1–10 d) before, critical now',
    'safe_to_crit': 'float above 10 d before, critical now',
    'safe_to_near': 'float above 10 d before, 1–10 d now',
    'crit_to_recovered': 'critical before, not critical now (still open)',
    'held_crit': 'critical in both',
}
_MIG_BANDS_NOTE = ("Bands are P6's own filters: Critical = P6 Critical filter (In Progress + Not Started that "
                   "P6 flags Critical; never LOE / WBS Summary) · Near-critical = Total Float within 1d – 10d · "
                   "Safe = the other open activities with float. Completed activities are in no band; milestones "
                   "are counted, as in P6. Matched by Activity ID.")


def _mig_recon(report):
    """'N activities turned critical ... Of the X critical now: held + turned (+ in no band before).'"""
    m = report.get('float_migration') or {}
    c, t = m.get('counts', {}) or {}, m.get('totals')
    base = 'the baseline' if report.get('float_migration_base') == 'baseline' else 'last period'
    turned = c.get('turned_crit', (c.get('near_to_crit', 0) or 0) + (c.get('safe_to_crit', 0) or 0))
    out = (f"{turned:,} activities turned critical vs {base} ({c.get('near_to_crit', 0) or 0} from near + "
           f"{c.get('safe_to_crit', 0) or 0} from safe).")
    if t:
        other = t['current']['critical'] - (c.get('held_crit', 0) or 0) - turned
        out += (f" Of the {t['current']['critical']:,} critical now: {c.get('held_crit', 0) or 0:,} held + {turned:,} turned critical"
                + (f" + {other:,} in no band {base} (not in that file, completed there, or without float)" if other else '') + '.')
    return out


_MIG_B = (('crit', 'Critical'), ('near', 'Near-critical 1–10 d'), ('safe', 'Safe >10 d'))
_MIG_KEY = ("Bands - Critical = P6 Critical filter (total float ≤ 0; In Progress + Not Started; never LOE / WBS "
            "Summary) · Near-critical = Total Float within 1d – 10d · Safe = Total Float above 10 d. Only open "
            "activities (P6 lists completed ones in no band); milestones counted, as in P6. Matched by Activity ID.")
_MIG_READ = ("Read a row across: the band last period -> the band now. Red = lost all float, now critical · "
             "Amber = Safe -> near-critical: float dropped from above 10 d to 1–10 d - not critical yet, the early "
             "warning · Green = recovered (float gained).")


def _mig_rows_from(mx):
    return list(_MIG_B) + ([('none', 'In no band*')] if any(mx.get(f'none>{t}') for t, _ in _MIG_B) else [])


def _fronts_for(report):
    """The work fronts as the screen shows them: filtered by the activity-code value picked, with
    that code's values per front. Returns (fronts, code type or None)."""
    m = report.get('float_migration') or {}
    pc = report.get('mig_front_code') or {}
    t, v = pc.get('type') or None, pc.get('value') or None
    if not t:
        return (m.get('fronts') or []), None
    fr = {}
    for r in m.get('rows') or []:
        if r.get('kind') not in ('near_to_crit', 'safe_to_crit', 'safe_to_near'):
            continue
        val = (r.get('codes') or {}).get(t) or '(no value)'
        if v and val != v:
            continue
        f = fr.setdefault((r.get('front'), r.get('front_parent')), {'front': r.get('front') or '—', 'parent': r.get('front_parent') or '',
                                                                   'turned_crit': 0, 'safe_to_near': 0, 'vals': {}})
        f['safe_to_near' if r['kind'] == 'safe_to_near' else 'turned_crit'] += 1
        f['vals'][val] = f['vals'].get(val, 0) + 1
    out = sorted(fr.values(), key=lambda f: (-(f['turned_crit'] + f['safe_to_near']), -f['turned_crit'], f['front']))
    return out, t


def _code_div(code_t, f):
    if not code_t or not f.get('vals'):
        return ''
    vals = sorted(f['vals'].items(), key=lambda x: -x[1])
    txt = ', '.join(f'{k} ({n})' if len(vals) > 1 else k for k, n in vals)
    return f'<div class="note" style="color:{_ACCENT}">{_e(code_t)}: {_e(txt)}</div>'


def _advice_html(report):
    """③ Recommendation by building and trade (the codes picked on screen)."""
    from p6_critpath.migration_advice import advice, NO_VALUE
    m = report.get('float_migration') or {}
    if not m.get('rows') or not m.get('code_types'):
        return ''
    codes = report.get('mig_codes') or m.get('advice_codes') or {}
    a = advice(m, codes.get('location'), codes.get('trade'))
    locs, trs = a['locations'][:8], a['trades'][:6]
    mx = max([a['cells'].get(l, {}).get(t, 0) for l in locs for t in trs] or [1]) or 1

    def cell(l, t):
        n = a['cells'].get(l, {}).get(t, 0)
        if not n:
            return '<td></td>'
        alpha = round(0.1 + 0.5 * n / mx, 2)
        return (f'<td style="text-align:center;background:rgba(192,57,43,{alpha});-webkit-print-color-adjust:exact;'
                f'print-color-adjust:exact"><b>{n}</b></td>')
    table = (f'<table class="t" style="width:100%"><thead><tr><th>{_e(a["location"] or "")} \\ {_e(a["trade"] or "")}</th>'
             + ''.join(f'<th style="text-align:center">{_e(t)}</th>' for t in trs) + '<th class="num">Total</th></tr></thead><tbody>'
             + ''.join(f'<tr><td><b>{_e(l)}</b></td>' + ''.join(cell(l, t) for t in trs)
                       + f'<td class="num"><b>{a["loc_totals"].get(l, 0)}</b></td></tr>' for l in locs) + '</tbody></table>')
    nm = lambda x: ' — '.join(v for v in (x['location'], x['trade']) if v and v not in (NO_VALUE, '—')) or 'Activities with no building / trade code'
    items = ''.join(
        f'<div style="border:1px solid #d9dfe8;border-left:5px solid {_BAD};border-radius:6px;padding:6px 9px;margin:5px 0">'
        f'<b>{k + 1} · {_e(nm(i))}</b> — {i["turned_crit"]} activities turned critical'
        + (f', losing {_n1(i["avg_lost"])} d of float each on average' if i.get('avg_lost') is not None else '')
        + f'.<div><b style="color:{_GOOD}">Mitigation:</b> {_e(i["mitigation"])}.</div></div>' for k, i in enumerate(a['items']))
    worst = ''
    if a['worst']:
        worst = (f'<div style="border:1px solid #d9dfe8;border-left:5px solid {_WARN};border-radius:6px;padding:6px 9px;margin:5px 0">'
                 '<b>Deepest negative float now</b> — '
                 + _e(' · '.join(f"{nm(w)} ({_n1(w['min_tf'])} d, {w['activities']} critical)" for w in a['worst']))
                 + ': the furthest behind — recover them first.</div>')
    return ('<div data-part="float_migration.advice" data-part-label="Recommendation by building and trade">'
            '<h3 style="margin:12px 0 4px;font-size:13px">③ Recommendation — where the problem is and how to mitigate it</h3>'
            + table + items + worst
            + '<div class="note">Building, trade, counts and float are measured from the file; the mitigation is a planner\'s suggestion picked from the trade.</div></div>')


def _parent_div(f):
    return f'<div class="note">{_e(f["parent"])}</div>' if f.get('parent') else ''


def _migration(report):
    """Float migration, summarised (comments 91-92): three headline figures, one grid of band
    moves, the work fronts where float was lost. No activity list (the Excel export has it)."""
    m = report.get('float_migration')
    if not m:
        return '<div class="note">Load a previous update or a baseline to see how float moved.</div>'
    c, t, mx, fl = m.get('counts', {}) or {}, m.get('totals'), m.get('matrix') or {}, m.get('float_lost') or {}
    is_bl = report.get('float_migration_base') == 'baseline'
    base = 'the baseline' if is_bl else 'last period'
    dd = report.get('data_dates') or {}
    turned = c.get('turned_crit', (c.get('near_to_crit', 0) or 0) + (c.get('safe_to_crit', 0) or 0))
    edge = report_theme.var('rpt-edge')

    def big(col, v, t1, t2):
        return (f'<td style="border:1px solid {edge};border-left:5px solid {col};padding:8px 10px;vertical-align:top">'
                f'<div style="font-size:20px;font-weight:800;color:{col}">{v}</div>'
                f'<div class="note"><b>{_e(t1)}</b> {_e(t2)}</div></td>')
    heads = [big(_BAD, f'{turned:,}', 'activities turned critical',
                 f"vs {base} - {c.get('near_to_crit', 0) or 0} from near-critical, {c.get('safe_to_crit', 0) or 0} from safe")]
    if fl.get('avg') is not None:
        heads.append(big(_WARN, f"{_n1(fl['avg'])} d", 'average float lost', f"by each of them (largest {_n1(fl['max'])} d)"))
    if t:
        heads.append(big(_ACCENT, f"{t['base']['critical']:,} → {t['current']['critical']:,}",
                         'critical activities', f"(P6 Critical filter) · near-critical {t['base']['near']} → {t['current']['near']}"))
    head = '<table style="width:100%;border-collapse:separate;border-spacing:6px 0;margin-bottom:10px"><tr>' + ''.join(heads) + '</tr></table>'

    def cell(f, to):
        n = mx.get(f'{f}>{to}', 0)
        if not n:
            return '<td style="text-align:center;color:#bbb">0</td>'
        if f == to:
            col, bg = (_BAD, '#f6e4e1') if f == 'crit' else (_MUTED, '#eef1f5')
        elif to == 'crit':
            col, bg = _BAD, '#f9d8d4'
        elif f == 'safe' and to == 'near':
            col, bg = _WARN, '#fbe9cc'
        elif f == 'none':
            col, bg = _MUTED, '#eef1f5'
        else:
            col, bg = _GOOD, '#d6efe0'
        held = '<div style="font-size:9px;font-weight:600">held</div>' if f == to == 'crit' else ''
        return (f'<td style="text-align:center;font-weight:800;font-size:14px;color:{col};background:{bg};'
                f'-webkit-print-color-adjust:exact;print-color-adjust:exact">{n:,}{held}</td>')
    rows_from = _mig_rows_from(mx)
    bl = ('BASELINE' if is_bl else 'LAST PERIOD') + (f" — {dd.get('baseline' if is_bl else 'previous')}" if dd.get('baseline' if is_bl else 'previous') else '')
    grid = (f'<table class="t" style="width:100%"><thead><tr><th>{_e(bl)} ↓ / NOW{(" — " + _e(dd["current"])) if dd.get("current") else ""} →</th>'
            + ''.join(f'<th style="text-align:center">{_e(l)}</th>' for _, l in _MIG_B) + '</tr></thead><tbody>'
            + ''.join(f'<tr><td><b>{_e(lbl)}</b></td>' + ''.join(cell(f, to) for to, _ in _MIG_B) + '</tr>' for f, lbl in rows_from)
            + '<tr><td><b>Total now (P6 filter)</b></td>'
            + ''.join(f'<td style="text-align:center;font-weight:800;border-top:2px solid #888">{sum(mx.get(f"{f}>{to}", 0) for f, _ in rows_from):,}</td>' for to, _ in _MIG_B)
            + '</tr></tbody></table>')
    tot = lambda to: sum(mx.get(f'{f}>{to}', 0) for f, _ in rows_from)
    star = ' *not in the previous file, completed there, or without float.' if any(f == 'none' for f, _ in rows_from) else ''
    none = mx.get('none>crit', 0)
    base_in = 'in the baseline' if is_bl else 'last period'
    how = (f'<div class="note" style="border:1px solid #d9dfe8;border-radius:6px;padding:6px 9px;margin-top:6px">'
           f'<b>How the numbers are made</b> — each open activity of the current update is matched to the same Activity ID '
           f'{base_in} and put in one cell: its band then (row) → its band now (column).<br>'
           f"Turned critical = {c.get('near_to_crit', 0) or 0:,} (near → critical) + {c.get('safe_to_crit', 0) or 0:,} (safe → critical) = <b>{turned:,}</b><br>"
           + (f"Critical now = {c.get('held_crit', 0) or 0:,} held + {turned:,} turned"
              + (f" + {none} {'not in the baseline' if is_bl else 'in no band last period'}" if none else '')
              + f" = <b>{tot('crit'):,}</b> — P6 Critical filter in the current file<br>"
              + f"{'In the baseline' if is_bl else 'Last period'}: Critical {t['base']['critical']:,} · Near-critical {t['base']['near']:,} — the same P6 filters in that file" if t else '')
           + '</div>')
    grid_note = (how + f'<div class="note">{_e(_MIG_READ)} Columns add up to the totals now: Critical {tot("crit"):,}, '
                 f'Near-critical {tot("near"):,}.{_e(star)}</div>')
    fr, code_t = _fronts_for(report)
    top = max([f['turned_crit'] + f['safe_to_near'] for f in fr] or [1])
    shown = fr[:8]
    if fr:
        frows = ''.join(
            f'<tr><td>{_e(f["front"])}{_parent_div(f)}{_code_div(code_t, f)}</td>'
            f'<td style="width:45%"><div style="display:flex;height:10px;border-radius:5px;overflow:hidden;background:#eef1f5;-webkit-print-color-adjust:exact;print-color-adjust:exact">'
            f'<div style="width:{100 * f["turned_crit"] / top:.1f}%;background:{_BAD}"></div>'
            f'<div style="width:{100 * f["safe_to_near"] / top:.1f}%;background:{_WARN}"></div></div></td>'
            f'<td class="num"><b>{f["turned_crit"] + f["safe_to_near"]}</b></td></tr>' for f in shown)
        more = (f'<div class="note">+ {len(fr) - len(shown)} more work fronts - every one is in the Excel export.</div>'
                if len(fr) > len(shown) else '')
        fronts = (f'<table class="t" style="width:100%"><thead><tr><th>Work front (the WBS the activity sits in)</th>'
                  f'<th>turned critical (red) · safe → near-critical (amber)</th><th class="num">Activities</th></tr></thead>'
                  f'<tbody>{frows}</tbody></table>{more}')
    else:
        fronts = '<div class="note">No activity lost float into the near-critical or critical band.</div>'
    return (head
            + '<div data-part="float_migration.grid" data-part-label="Where every open activity moved"><h3 style="margin:8px 0 4px;font-size:13px">① Where every open activity moved</h3>' + grid + grid_note + '</div>'
            + '<div data-part="float_migration.fronts" data-part-label="Where float was lost - by work front"><h3 style="margin:12px 0 4px;font-size:13px">② Where float was lost — by work front</h3>' + fronts + '</div>'
            + _advice_html(report)
            + f'<div class="note" style="margin-top:8px">{_e(_MIG_KEY)}</div>')


def _recommendation(report):
    rec = ''.join(f'<li>{_e(r)}</li>' for r in report.get('recommendation', []))
    return (f'<div class="effect" data-part="recommendation.effect" data-part-label="Effect on completion">'
            f'{_e(report.get("effect"))}</div>'
            f'<div data-part="recommendation.list" data-part-label="Recommendation">'
            f'<div class="recoh">Recommendation</div><ol class="reco">{rec}</ol></div>')


def render_html(report, sections=None, milestone_ids=None, theme='light'):
    secs = [
        ('verdict', '', _banner(report), False),
        ('dashboard', 'Execution dashboard', _dashboard(report), False),
        ('driving_path', 'Critical Path Analyzer', _lanes(report, milestone_ids), True),
        ('census', 'Critical & near-critical census', _census(report), False),
        ('milestones', 'Every milestone · finish comparison & path health', _milestones(report), False),
        ('float_migration', 'Float migration', _migration(report), False),
        ('recommendation', 'Effect on completion & recommendation', _recommendation(report), False),
    ]
    keys = set(sections) if sections else None
    body = [_header(report)]
    for key, title, html, planner in secs:
        if keys is not None and key not in keys:
            continue
        t = f'<h2>{_e(title)}</h2>' if title else ''
        body.append(f'<section data-sec="{key}"{" class=pagebreak" if planner else ""}>{t}{html}</section>')
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 11mm; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; color: var(--rpt-ink); font-size: 12px; margin: 0; }}
      h1 {{ font-size: 18px; margin: 0; }} h2 {{ font-size: 13px; margin: 16px 0 8px; color: var(--rpt-accent); }}
      section.pagebreak {{ page-break-before: always; }}
      .rh {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid var(--rpt-edge); padding-bottom: 8px; }}
      .meta {{ color: var(--rpt-muted); font-size: 11px; margin-top: 3px; }}
      .ddstrip {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }}
      .ddpill {{ background: var(--rpt-surface-2); color: var(--rpt-ink-soft); font-size: 10px; border-radius: 5px; padding: 2px 8px; }}
      .ddpill b {{ color: var(--rpt-ink); }}
      .banner {{ display: flex; align-items: center; gap: 11px; border: 1px solid; border-radius: 9px; padding: 10px 14px; margin-top: 10px; }}
      .btag {{ color: var(--rpt-accent-ink); font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .5px; padding: 3px 9px; border-radius: 5px; }}
      .btext {{ font-size: 13px; font-weight: 600; }}
      .dash {{ display: flex; gap: 12px; }}
      .health {{ flex: 1; display: flex; gap: 12px; align-items: center; border: 1px solid var(--rpt-edge); border-left: 4px solid var(--rpt-bad); border-radius: 10px; padding: 10px 14px; }}
      .hgauge {{ flex: none; width: 74px; height: 74px; border-radius: 50%; border: 6px solid var(--rpt-edge); display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 19px; font-weight: 800; }}
      .hgauge span {{ font-size: 9px; font-weight: 600; color: var(--rpt-muted); }}
      .htitle {{ font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .4px; color: var(--rpt-muted); }}
      .hverdict {{ font-size: 12px; font-weight: 700; margin: 3px 0 5px; }}
      .hfactors {{ margin: 0; padding-left: 15px; font-size: 10.5px; color: var(--rpt-muted); line-height: 1.5; }}
      .kpis {{ flex: 1; display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }}
      .kpi {{ border: 1px solid var(--rpt-edge); border-radius: 9px; padding: 8px 11px; }}
      .kk {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: .3px; color: var(--rpt-muted); font-weight: 700; }}
      .kv {{ font-size: 19px; font-weight: 800; margin-top: 2px; }}
      .kv .kcur {{ font-size: 9px; font-weight: 700; color: var(--rpt-accent); text-transform: uppercase; letter-spacing: .3px; }}
      .kd {{ font-size: 11px; font-weight: 700; color: var(--rpt-muted); margin-top: 2px; }}
      .charts {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 12px; }}
      .chartcard {{ border: 1px solid var(--rpt-edge); border-radius: 10px; padding: 10px 12px; page-break-inside: avoid; }}
      .chartt {{ font-size: 10.5px; font-weight: 800; text-transform: uppercase; letter-spacing: .3px; color: var(--rpt-muted); margin-bottom: 6px; }}
      .chartlegend {{ font-size: 9.5px; color: var(--rpt-muted); margin-top: 4px; }}
      .chartlegend i {{ display: inline-block; width: 9px; height: 9px; border-radius: 2px; vertical-align: middle; margin: 0 3px 0 8px; }}
      .mvchart {{ display: flex; flex-direction: column; gap: 6px; }}
      .mvrow {{ font-size: 10px; }}
      .mvname {{ color: var(--rpt-ink-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px; }}
      .mvbar {{ display: flex; align-items: center; gap: 5px; }}
      .mvbar span {{ display: inline-block; height: 10px; border-radius: 3px; min-width: 1px; }}
      .mvbar b {{ font-size: 9.5px; white-space: nowrap; }}
      .mpblock {{ page-break-inside: avoid; margin-bottom: 14px; }}
      .mphdr {{ display: flex; justify-content: space-between; align-items: baseline; gap: 10px; border-bottom: 1px solid var(--rpt-edge); padding-bottom: 4px; margin-bottom: 8px; }}
      .mpname {{ font-size: 12px; font-weight: 800; color: var(--rpt-ink); }}
      .mpfin {{ font-size: 10px; color: var(--rpt-muted); }}
      .lane {{ margin-bottom: 12px; }} .lanehdr {{ display: flex; gap: 9px; align-items: center; margin-bottom: 6px; }}
      /* a title never ends a page: it reserves the height of one row of cards under itself
         (unbreakable block + a pulled-back spacer), so the title and its first cards move
         together - break-after:avoid alone is not honoured before a wrapping row of cards */
      @media print {{
        .lanekeep, .mpkeep {{ break-inside: avoid; page-break-inside: avoid; }}
        .lanekeep::after {{ content: ""; display: block; height: 150px; margin-bottom: -150px; }}
        .mpkeep::after {{ content: ""; display: block; height: 190px; margin-bottom: -190px; }}
      }}
      .lanetag {{ font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .5px; padding: 3px 9px; border-radius: 6px; }}
      .lt-baseline {{ background: var(--rpt-surface-2); color: var(--rpt-ink-soft); }} .lt-previous {{ background: var(--rpt-warn-bg); color: var(--rpt-warn); }} .lt-current {{ background: var(--rpt-accent-soft); color: var(--rpt-accent); }}
      .lanesub {{ color: var(--rpt-muted); font-size: 10.5px; }}
      .chain {{ display: flex; align-items: stretch; flex-wrap: wrap; gap: 5px; }}
      .arw {{ display: flex; align-items: center; color: var(--rpt-accent); font-weight: 900; font-size: 26px; padding: 0 1px; }}
      .msbox {{ flex: none; width: 150px; border: 2px solid var(--rpt-accent); border-radius: 10px; padding: 8px 10px; background: var(--rpt-accent-soft); }}
      .msflag {{ font-size: 9px; text-transform: uppercase; color: var(--rpt-accent); margin-bottom: 4px; }}
      .mst {{ font-size: 11.5px; font-weight: 800; color: var(--rpt-accent); margin-bottom: 5px; }}
      .msr {{ display: flex; justify-content: space-between; font-size: 10.5px; margin: 2px 0; }} .msr span {{ color: var(--rpt-muted); }}
      .box {{ flex: none; width: 176px; border: 1px solid var(--rpt-edge); border-radius: 9px; padding: 7px 9px; position: relative; }}
      .bgrid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 3px 8px; margin-top: 2px; }}
      .bgrid .bk {{ font-size: 8px; text-transform: uppercase; }} .bgrid .bv {{ font-size: 10.5px; }}
      .bfull {{ grid-column: 1 / -1; border-top: 1px dashed var(--rpt-edge); padding-top: 3px; margin-top: 1px; }}
      .box.bdone {{ border-color: var(--rpt-good); }}
      .box.bnew {{ border: 2px solid var(--rpt-bad); background: var(--rpt-bad-bg); }}
      .box.bleft {{ border: 1px dashed var(--rpt-hair-strong); background: var(--rpt-surface-2); }}
      /* the NEW ON PATH / LEFT PATH pill sits INSIDE the card, on its first line: hanging 8 px above the card it was left on the previous page whenever its row of cards opened a page (PDF and the Word page pictures) */
      .bflag {{ display: table; margin: 0 0 4px; color: var(--rpt-accent-ink); font-size: 8px; font-weight: 800; padding: 1px 6px; border-radius: 4px; }}
      .bfnew {{ background: var(--rpt-bad); }} .bfleft {{ background: var(--rpt-muted); color: var(--rpt-bg); }}
      .bt {{ font-size: 11px; font-weight: 700; }} .bcrumb {{ font-size: 8.5px; color: var(--rpt-muted); margin: 2px 0 6px; }}
      .brow {{ display: flex; justify-content: space-between; font-size: 10px; margin: 2px 0; }}
      .brow.last {{ border-top: 1px dashed var(--rpt-edge); padding-top: 3px; margin-top: 3px; }}
      .bk {{ color: var(--rpt-muted); }} .bv {{ font-weight: 700; }}
      .cplegend {{ font-size: 10px; color: var(--rpt-muted); margin-top: 6px; }}
      .cplegend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; vertical-align: middle; margin: 0 4px 0 12px; }}
      table.t {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
      table.t th, table.t td {{ padding: 6px 9px; text-align: left; border-bottom: 1px solid var(--rpt-edge); }}
      table.t th {{ font-size: 10px; text-transform: uppercase; letter-spacing: .3px; color: var(--rpt-muted); }}
      table.t th .thdd {{ text-transform: none; font-weight: 600; font-size: 9px; color: var(--rpt-muted); margin-top: 2px; }}
      table.t td.num, table.t th.num {{ text-align: right; }}
      table.t tr.gov td {{ font-weight: 800; }}
      .bands {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
      .band {{ border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 9px; text-align: center; }}
      .bandl {{ font-size: 10px; color: var(--rpt-muted); font-weight: 700; }} .bandv {{ font-size: 18px; font-weight: 800; margin-top: 3px; }} .bandt {{ font-size: 10px; font-weight: 700; margin-top: 2px; }}
      .effect {{ font-size: 12px; line-height: 1.5; background: var(--rpt-surface); border-left: 3px solid var(--rpt-accent); border-radius: 0 8px 8px 0; padding: 10px 13px; }}
      .recoh {{ font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .4px; color: var(--rpt-accent); margin: 12px 0 5px; }}
      .reco {{ margin: 0; padding-left: 18px; font-size: 11.5px; line-height: 1.6; }}
      .note {{ color: var(--rpt-muted); font-size: 11px; margin-top: 8px; }}
    </style>{report_theme.theme_style_tag(theme)}</head><body>{"".join(body)}</body></html>'''


# ── Excel ────────────────────────────────────────────────────────────────────
#
# The workbook MIRRORS the on-screen / PDF Critical Path Analyzer through the shared,
# dependency-free writer (p6_evm.xlsx_writer.write_sections_xlsx) — one sheet per section
# of the report's tables (Census · Milestones · Driving path · Float migration), with
# self-explaining headers WITH UNITS and the driving path's criticality colour-coded to
# match the on-screen badges (critical = red, near-critical = amber) via a severity column
# and a legend. The SERVER supplies the standard "<app> — Critical Path Analyzer / Project
# / Data date / Generated" header block through `meta`; this module never builds it (per the
# tool-wide export standard). No openpyxl — keeps the PyInstaller bundle small.

_ROLE_FINISH = {'baseline': 'Baseline finish', 'previous': 'Previous finish',
                'current': 'Current finish'}
_STATE_LABEL = {'new': 'New on path', 'left': 'Left path', 'done': 'Complete', 'stayed': 'On path'}
# Criticality colour = census/screen semantics: total float ≤ 0 → red (Critical),
# 0 < TF < 10 wd → amber (near-critical, the shared writer's 'High'), else grey.
_CRIT_LEGEND = [('Critical', 'On the critical path — total float 0 working days or less'),
                ('High', 'Near-critical — 0 < total float < 10 working days'),
                ('Low', 'Has spare float — not on or near the critical path')]


def _pct_cell(v):
    """A percentage as a string ('62.0%'), matching the on-screen census; em dash when
    unknown. (The writer keeps bare numbers numeric, so a percentage must be a string to
    read as one.)"""
    return '—' if v is None else f'{v}%'


def _pct_round(v):
    """A whole-percent string ('62%') for the driving-path boxes, matching the box grid."""
    return '—' if v is None else f'{round(v)}%'


def _num_cell(v):
    """Keep a number numeric (so figures stay computable); em dash when unknown."""
    return '—' if v is None else _n1(v)


def _crit_severity(driver_tf):
    """A work front's own total float → the shared severity word whose colour matches the
    on-screen critical (red) / near-critical (amber) badge. Same thresholds as the census
    (schedule_census) and the milestone fronts (milestones_table)."""
    if driver_tf is None:
        return ''
    if driver_tf <= 0:
        return 'Critical'
    if driver_tf < 10:
        return 'High'               # near-critical (0 < TF < 10 wd) — amber, like the screen
    return 'Low'                    # has float — grey


def _census_block(report):
    """The Critical & near-critical census — one measure per row, one column per loaded
    schedule (mirrors the on-screen census table). The crammed 'count · %' cells become
    two clearly-labelled rows apiece."""
    roles = report.get('roles', [])
    c = report.get('census', {})

    def vals(fn):
        return [fn(c.get(r, {}) or {}) for r in roles]

    rows = [
        ['Total activities counted'] + vals(lambda o: _num_cell(o.get('total_activities'))),
        ['Critical activities — count (P6 Critical filter)'] + vals(lambda o: _num_cell(o.get('critical'))),
        ['Critical activities — % of counted'] + vals(lambda o: _pct_cell(o.get('critical_pct'))),
        ['Near-critical — count (0 < total float < 10 wd)'] + vals(lambda o: _num_cell(o.get('near'))),
        ['Near-critical — % of counted'] + vals(lambda o: _pct_cell(o.get('near_pct'))),
        ['Critical path length — remaining (working days)'] + vals(lambda o: _num_cell(o.get('path_length_wd'))),
        ['Total float at finish milestone (working days)'] + vals(lambda o: _num_cell(o.get('total_float_wd'))),
        ['CPLI — Critical Path Length Index'] + vals(lambda o: _num_cell(o.get('cpli'))),
    ]
    dd = ' · '.join(f'{_ROLE_LABEL[r]} {c.get(r, {}).get("data_date")}'
                    for r in roles if c.get(r, {}).get('data_date'))
    note = 'Counts cover scheduled activities (milestones excluded).'
    if dd:
        note += f' Data dates — {dd}.'
    if any((c.get(r, {}) or {}).get('critical_source') == 'path' for r in roles):
        note += (' One or more schedules carry no activity float; for those the critical count is '
                 'the activities on the longest path to completion (not total float ≤ 0).')
    return {'title': 'Critical & near-critical census', 'note': note,
            'headers': ['Measure'] + [_ROLE_LABEL[r] for r in roles], 'rows': rows}


def _milestones_block(report):
    """Every finish milestone: each schedule's forecast finish, slip vs baseline / this
    period, milestone CPLI, and the count of critical / near-critical work fronts on its
    driving path (mirrors the on-screen milestone table)."""
    roles = report.get('roles', [])
    has_prev = 'previous' in roles
    headers = ['Milestone', 'Governing (drives completion)']
    headers += [_ROLE_FINISH[r] for r in roles]
    headers += ['Slip vs baseline (days, + = behind plan)']
    if has_prev:
        headers += ['Slip this period (days, + = behind)']
    headers += ['Milestone CPLI', 'Critical fronts on path (count)', 'Near-critical fronts on path (count)']

    rows = []
    for m in report.get('milestones', []):
        f = m.get('finishes', {})
        row = [m.get('name'), 'Yes' if m.get('is_governing') else '']
        row += [f.get(r) or '—' for r in roles]
        row += [_num_cell(m.get('var_vs_baseline_d'))]
        if has_prev:
            row += [_num_cell(m.get('var_this_period_d'))]
        row += [_num_cell(m.get('cpli')), _num_cell(m.get('crit_fronts')), _num_cell(m.get('near_fronts'))]
        rows.append(row)
    if not rows:
        rows = [['No finish milestones found.'] + [''] * (len(headers) - 1)]
    return {'title': 'Every milestone · finish comparison & path health',
            'note': 'One row per finish milestone. Slip is the current forecast finish against the '
                    'baseline / previous finish; positive means later than plan.',
            'headers': headers, 'rows': rows}


def _driving_path_sheet(report):
    """The current update's driving path to the governing milestone (as the current Excel
    exported), enriched to the on-screen box detail and with each front's criticality
    colour-coded. `severity_col` targets the Criticality column; the sheet carries the
    colour legend."""
    cur = next((l for l in report.get('lanes', []) if l.get('role') == 'current'), None)
    gov = next((m for m in report.get('milestones', []) if m.get('is_governing')), None)
    gov_name = gov.get('name') if gov else None
    ax = ' · approx' if report.get('baseline_approx') else ''   # own Planned dates stand in
    headers = ['Work front', 'Path / WBS', 'Change on critical path', 'Planned % complete' + ax,
               'Actual % complete', 'Baseline finish' + ax, 'Expected finish',
               'Slip vs baseline (days, + = behind plan)' + ax, 'Total float now (working days)', 'Criticality']
    rows = []
    for b in (cur.get('boxes', []) if cur else []):
        rows.append([
            b.get('name'), b.get('crumb') or '—',
            _STATE_LABEL.get(b.get('state', 'stayed'), 'On path'),
            _pct_round(b.get('planned')), _pct_round(b.get('pct')),
            b.get('bl_finish') or '—', b.get('exp_finish') or '—',
            _num_cell(b.get('slip_days')), _num_cell(b.get('driver_tf')),
            _crit_severity(b.get('driver_tf')),
        ])
    if not rows:
        rows = [['No governing critical path was found in these schedules.'] + [''] * (len(headers) - 1)]
    note = (f"Work fronts on the current update's critical path to {gov_name}." if gov_name
            else "Work fronts on the current update's critical path to the governing milestone.")
    note += ' "New on path" fronts are the reroute — the headline risk of the report.'
    return {'name': 'Driving path (current)', 'legend': _CRIT_LEGEND,
            'blocks': [{'title': 'Driving path — current update', 'note': note,
                        'headers': headers, 'rows': rows,
                        'severity_col': headers.index('Criticality')}]}


def _migration_block(report):
    """How activities moved between float bands from the comparison base (previous, else
    baseline) to the current update (mirrors the on-screen float-migration bands)."""
    cc = (report.get('float_migration') or {}).get('counts', {}) or {}
    base = 'the previous update' if report.get('float_migration_base') == 'previous' else 'the baseline'
    rows = [
        ['Near-critical → CRITICAL', _num_cell(cc.get('near_to_crit', 0)), 'Lost all float — worsened', _MIG_RULES['near_to_crit']],
        ['Safe → CRITICAL', _num_cell(cc.get('safe_to_crit', 0)), 'Lost all float — worsened', _MIG_RULES['safe_to_crit']],
        ['Safe → near-critical', _num_cell(cc.get('safe_to_near', 0)), 'Float dropped below 10 d - not critical yet, early warning', _MIG_RULES['safe_to_near']],
        ['Critical → recovered', _num_cell(cc.get('crit_to_recovered', 0)), 'Gained float — improved', _MIG_RULES['crit_to_recovered']],
        ['Held critical', _num_cell(cc.get('held_crit', 0)), 'Stayed critical — unchanged', _MIG_RULES['held_crit']],
    ]
    t = (report.get('float_migration') or {}).get('totals')
    if t:
        rows += [[f'Critical (P6 Critical filter) — {base}', _num_cell(t['base']['critical']), 'Total', 'tick in P6 in that file'],
                 ['Critical (P6 Critical filter) — current update', _num_cell(t['current']['critical']), 'Total', 'tick in P6 in this file'],
                 [f'Near-critical (TF 1–10 d) — {base}', _num_cell(t['base']['near']), 'Total', 'tick in P6 in that file'],
                 ['Near-critical (TF 1–10 d) — current update', _num_cell(t['current']['near']), 'Total', 'tick in P6 in this file']]
    return {'title': 'Float migration',
            'note': _mig_recon(report) + ' ' + _MIG_BANDS_NOTE,
            'headers': ['Float band move (matched by activity ID)', 'Activities (count)', 'Effect', 'Where the number comes from'],
            'rows': rows}


_MOVE_WORDS = {'near_to_crit': 'Near-critical → CRITICAL', 'safe_to_crit': 'Safe → CRITICAL', 'safe_to_near': 'Safe → near-critical',
               'crit_to_recovered': 'Critical → recovered', 'held_crit': 'Held critical'}
_BAND_WORDS = {'crit': 'Critical', 'near': 'Near-critical', 'safe': 'Safe'}
_MOVE_ORDER = ('near_to_crit', 'safe_to_crit', 'safe_to_near', 'crit_to_recovered', 'held_crit')


def _migration_summary_blocks(report):
    """The grid of band moves and the work fronts where float was lost (as the screen / PDF)."""
    m = report.get('float_migration') or {}
    mx = m.get('matrix') or {}
    out = []
    if mx:
        rf = _mig_rows_from(mx)
        out.append({'title': 'Where every open activity moved (band last period -> band now)',
                    'note': _MIG_READ,
                    'headers': ['Band last period / band now'] + [l for _, l in _MIG_B],
                    'rows': [[lbl] + [_num_cell(mx.get(f'{f}>{to}', 0)) for to, _ in _MIG_B] for f, lbl in rf]
                            + [['Total now'] + [_num_cell(sum(mx.get(f'{f}>{to}', 0) for f, _ in rf)) for to, _ in _MIG_B]]})
    fr, code_t = _fronts_for(report)
    if fr:
        out.append({'title': 'Where float was lost - by work front' + (f' ({code_t})' if code_t else ''),
                    'note': 'Work front = the WBS the activity sits in. Every activity that turned critical or dropped from safe to near-critical.',
                    'headers': ['Work front', 'WBS above it'] + ([code_t] if code_t else []) + ['Turned critical', 'Safe -> near-critical', 'Total'],
                    'rows': [[f['front'], f.get('parent') or '']
                             + ([', '.join(f'{k} ({n})' for k, n in sorted((f.get('vals') or {}).items(), key=lambda x: -x[1]))] if code_t else [])
                             + [_num_cell(f['turned_crit']), _num_cell(f['safe_to_near']), _num_cell(f['turned_crit'] + f['safe_to_near'])] for f in fr]})
    if m.get('rows') and m.get('code_types'):
        from p6_critpath.migration_advice import advice
        codes = report.get('mig_codes') or m.get('advice_codes') or {}
        a = advice(m, codes.get('location'), codes.get('trade'))
        trs = a['trades']
        out.append({'title': f"Where the activities that turned critical sit - {a['location']} x {a['trade']}",
                    'note': 'Count of activities that turned critical per building / location and trade (activity codes of the current update).',
                    'headers': [f"{a['location']} / {a['trade']}"] + trs + ['Total'],
                    'rows': [[l] + [_num_cell(a['cells'].get(l, {}).get(t, 0)) for t in trs] + [_num_cell(a['loc_totals'].get(l, 0))]
                             for l in a['locations']]})
        out.append({'title': 'Recommendation - where the problem is and how to mitigate it',
                    'headers': ['Building / location', 'Trade', 'Turned critical', 'Average float lost (d)', 'Mitigation'],
                    'rows': [[i['location'], i['trade'], _num_cell(i['turned_crit']), _num_cell(i['avg_lost']), i['mitigation']] for i in a['items']]
                            + [['Deepest negative float: ' + w['location'], w['trade'], _num_cell(w['activities']), _num_cell(w['min_tf']), 'recover first']
                               for w in a['worst']]})
    return out


def _migration_rows_block(report):
    """The activities behind the float-migration counts — every one, worst move first (owner
    comment 29: the workbook lists what the four tiles only count). None when there are none."""
    rows = (report.get('float_migration') or {}).get('rows') or []
    if not rows:
        return None
    base = 'previous update' if report.get('float_migration_base') == 'previous' else 'baseline'
    order = {k: i for i, k in enumerate(_MOVE_ORDER)}
    rows = sorted(rows, key=lambda r: (order.get(r.get('kind'), 9), str(r.get('id') or '')))
    return {'title': 'Activities behind the float migration',
            'note': f'{len(rows)} activities, matched by activity ID. Total float in working days.',
            'headers': ['Activity ID', 'Activity Name', 'Move', f'Band in the {base}',
                        'Band now', f'Total float in the {base} (d)', 'Total float now (d)'],
            'rows': [[r.get('id') or '', r.get('name') or '', _MOVE_WORDS.get(r.get('kind'), r.get('kind') or ''),
                      _BAND_WORDS.get(r.get('from'), r.get('from') or ''),
                      _BAND_WORDS.get(r.get('to'), r.get('to') or ''),
                      _num_cell(r.get('base_tf')), _num_cell(r.get('curr_tf'))] for r in rows]}


def critpath_excel_sections(report):
    """(the report dict the client holds) → the `sheets` list for write_sections_xlsx.

    One sheet per section of the on-screen / PDF report's tables — Census, Milestones,
    Driving path (current), and Float migration (only when a base schedule is loaded, as
    the report shows it). Headers are self-explaining with units; numbers stay numeric,
    percentages and dates are strings; the driving path's criticality is colour-coded
    (critical = red, near-critical = amber) via a severity column + legend. Never raises on
    empty data (placeholder rows are used instead). The server passes `meta` for the header
    block; do not build one here."""
    report = report or {}
    sheets = [
        {'name': 'Census', 'blocks': [_census_block(report)]},
        {'name': 'Milestones', 'blocks': [_milestones_block(report)]},
        _driving_path_sheet(report),
    ]
    if report.get('float_migration'):
        blocks = [_migration_block(report)] + _migration_summary_blocks(report)
        moved = _migration_rows_block(report)
        if moved:
            blocks.append(moved)
        sheets.append({'name': 'Float migration', 'blocks': blocks})
    return sheets


def to_excel(report, path):
    """Backwards-compatible entry point (kept so existing callers keep working): write the
    workbook via the shared dependency-free writer. Content comes from
    critpath_excel_sections(); the standard report header block is added by the server via
    `meta` — a direct/CLI call here still gets a valid, self-explaining workbook."""
    from p6_evm.xlsx_writer import write_sections_xlsx
    write_sections_xlsx(path, critpath_excel_sections(report))
    return path
