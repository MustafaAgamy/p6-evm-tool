"""Update-Analysis exporters — PDF (HTML → Chrome headless) and Excel.

`render_html` lays out the four sections in the house consultant style: Time Status
(donut + PV/EV/Variance), Planned vs Actual by activity code (one chart per selected
code), the Driving Path Analyzer (the governing milestone's driving path as work-front
boxes), and Planned vs Actual by activity count. `report_excel` mirrors them.
Nothing here computes a number — it only presents what `p6_update.analysis` produced.
"""
import html
from datetime import datetime

_BLUE = '#26517d'
_PLAN = '#e0912f'
_ACT = '#2a78d6'
_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _e(v):
    return html.escape(str(v if v is not None else ''))


def _fdate(iso):
    """ISO date → '9 Feb 2027'."""
    if not iso:
        return '—'
    try:
        d = datetime.strptime(str(iso)[:10], '%Y-%m-%d')
        return f'{d.day} {_MONTHS[d.month - 1]} {d.year}'
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
    lab = f'{actual:.0f}%' if actual is not None else '—'
    return f'''<svg width="140" height="140" viewBox="0 0 150 150">
      <circle cx="75" cy="75" r="58" fill="none" stroke="#eef2f7" stroke-width="18"/>
      <circle cx="75" cy="75" r="58" fill="none" stroke="{_ACT}" stroke-width="18" stroke-dasharray="{arc(58, elapsed)}" transform="rotate(-90 75 75)"/>
      <circle cx="75" cy="75" r="40" fill="none" stroke="#eef2f7" stroke-width="10"/>
      <circle cx="75" cy="75" r="40" fill="none" stroke="#16a34a" stroke-width="10" stroke-dasharray="{arc(40, actual)}" transform="rotate(-90 75 75)"/>
      <text x="75" y="70" text-anchor="middle" font-size="17" font-weight="700" fill="#1e293b">{_e(lab)}</text>
      <text x="75" y="88" text-anchor="middle" font-size="10" fill="#94a3b8">earned</text>
    </svg>'''


def _timestatus_html(report):
    ts = report.get('time_status', {}) or {}
    ep, pp, ap = ts.get('elapsed_pct'), ts.get('planned_pct'), ts.get('actual_pct')
    elapsed_txt = '—'
    if ep is not None:
        elapsed_txt = f'{ep:.0f}%'
        if ts.get('exceeded_days'):
            elapsed_txt = f'100% — baseline exceeded by {ts["exceeded_days"]} days'
    sentence = (f'<b>{elapsed_txt}</b> of the baseline time has elapsed, but only '
                f'<b>{_pct(ap)}</b> of the work is earned (planned to be at <b>{_pct(pp)}</b> by now).')
    verdicts = ''
    if ts.get('behind_plan') is not None and pp is not None and ap is not None:
        v = ts['behind_plan']
        tag = 'bad' if v > 0 else 'good'
        verb = 'short of' if v > 0 else 'ahead of'
        verdicts += (f'<div class="vrow"><span class="vtag {tag}">Behind plan · {abs(v)}</span>'
                     f'<span>You planned to have earned <b>{_pct(pp)}</b> by the data date; you’ve earned '
                     f'<b>{_pct(ap)}</b> — {abs(v):.0f} points {verb} the plan.</span></div>')
    if ts.get('behind_clock') is not None and ep is not None and ap is not None:
        v = ts['behind_clock']
        tag = 'bad' if v > 0 else 'good'
        verdicts += (f'<div class="vrow"><span class="vtag {tag}">Behind clock · {abs(v)}</span>'
                     f'<span><b>{_pct(ep)}</b> of the baseline calendar is used up, but only <b>{_pct(ap)}</b> '
                     f'of the work is done — {abs(v):.0f} points {"less" if v > 0 else "more"} work than time spent.</span></div>')
    cost = (f'<div class="cost">'
            f'<div class="costcard"><div class="cl">Planned Value (PV)</div><div class="cv">{_num(ts.get("pv"))}</div></div>'
            f'<div class="costcard"><div class="cl">Earned Value (EV)</div><div class="cv">{_num(ts.get("ev"))}</div></div>'
            f'<div class="costcard"><div class="cl">Variance = EV − PV</div>'
            f'<div class="cv {"neg" if (ts.get("cost_variance") or 0) < 0 else ""}">{_num(ts.get("cost_variance"))}</div></div>'
            f'</div>')
    return (f'<div class="ts"><div>{_donut(ep, pp, ap)}</div>'
            f'<div class="ts-body"><div class="ts-sentence">{sentence}</div>'
            f'<div class="verdicts">{verdicts}</div></div></div>{cost}')


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
    for t in types:
        blocks.append(f'<div class="chart2"><h3>{_e(t)}</h3>{_bars_for(by[t])}</div>')
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
    for chart in cp['charts']:
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
        out.append(f'<div class="chain">{"".join(parts)}</div>')
    return ''.join(out)


# ── Section 5 · Scope weight & recommendation ───────────────────────────────

def _scope_html(report, code_type=None):
    scope = report.get('scope', {}) or {}
    if not scope:
        return '<p class="note">No cost-loaded activity codes to weigh in this update.</p>'
    ct = code_type if code_type in scope else (report.get('scope_default') if report.get('scope_default') in scope else next(iter(scope)))
    s = scope[ct]
    rows = s.get('rows', [])
    mx = max((r['weight_pct'] for r in rows), default=1) or 1
    bars = []
    for i, r in enumerate(rows[:12]):
        cls = ' top' if i == 0 else ''
        bars.append(f'<div class="wrow{cls}"><div class="wname">{_e(r["value"])}</div>'
                    f'<div class="wtrack"><div class="wfill" style="width:{r["weight_pct"] / mx * 100:.1f}%"></div></div>'
                    f'<div class="wpct">{r["weight_pct"]:.1f}%</div></div>')
    recs = ''.join(f'<p><span class="star">★</span> {_e(t)}</p>' for t in s.get('recommendation', []))
    rec = f'<div class="rec"><h4>◆ Recommendation — by weight</h4>{recs}</div>' if recs else ''
    return (f'<div class="scope-h">Weighting by <b>{_e(ct)}</b> · share of the cost-loaded scope</div>'
            + ''.join(bars) + rec)


# ── Section 4 · Planned vs Actual by activity count ─────────────────────────

def _counts_html(report):
    c = report.get('counts', {}) or {}
    if not c or not c.get('total'):
        return '<p class="note">No construction/execution activities to count in this update.</p>'
    mx = max(c.get('total', 1), 1)
    rows = [
        ('Completed', c.get('planned_completed', 0), c.get('actual_completed', 0)),
        ('In Progress', c.get('planned_in_progress', 0), c.get('actual_in_progress', 0)),
        ('Not Started', c.get('planned_not_started', 0), c.get('actual_not_started', 0)),
    ]
    body = []
    for label, pn, an in rows:
        body.append(
            f'<div class="cn-row"><div class="cn-lbl">{label}</div>'
            f'<div class="cn-bars">'
            f'<div class="cn-track"><div class="cn-pl" style="width:{pn / mx * 100:.1f}%"></div><span>Planned {pn}</span></div>'
            f'<div class="cn-track"><div class="cn-ac" style="width:{an / mx * 100:.1f}%"></div><span>Actual {an}</span></div>'
            f'</div></div>')
    total = (f'<div class="cn-total">Construction / execution activities: <b>{c.get("total", 0)}</b> '
             f'(planned baseline dates on <b>{c.get("planned_total", 0)}</b>)</div>')
    leg = (f'<div class="bc-leg"><span><i style="background:{_PLAN}"></i>Planned (count)</span>'
           f'<span><i style="background:{_ACT}"></i>Actual (count)</span></div>')
    return total + '<div class="cn">' + ''.join(body) + '</div>' + leg


# ── Assembly ────────────────────────────────────────────────────────────────

def render_html(report, sections=None, code_filter=None, scope_code=None):
    """`sections` = list of keys to include (None = all): conclusion · time · bycode ·
    driving · counts · scope. `code_filter` = {'types': [...]} picks Section 2's charts;
    `scope_code` picks Section 5's activity-code dimension."""
    header = (f'<div class="rh"><div><h1>Update Analysis</h1>'
              f'<div class="meta">{_e(report.get("project_name"))} · single-update read against its baseline</div></div>'
              f'<div class="win">Data date<br><b>{_fdate(report.get("data_date"))}</b>'
              f'<br>{_e(report.get("file") or "")}</div></div>')
    secs = [
        ('conclusion', 'Executive read', f'<div class="reco">{_e(report.get("conclusion"))}</div>'),
        ('time', '1 · Time Status', _timestatus_html(report)),
        ('bycode', '2 · Planned vs Actual — by activity code', _bycode_html(report, code_filter)),
        ('driving', '3 · Driving Path Analyzer', _driving_html(report)),
        ('counts', '4 · Planned vs Actual — by activity count', _counts_html(report)),
        ('scope', '5 · Scope Weight & Recommendation', _scope_html(report, scope_code)),
    ]
    keys = set(sections) if sections else None
    body = [header]
    for key, title, htmls in secs:
        if keys is not None and key not in keys:
            continue
        body.append(f'<section data-sec="{key}"><h2>{_e(title)}</h2>{htmls}</section>')
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 11mm; }}
      * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      body {{ font-family: system-ui, -apple-system, Arial, sans-serif; color: #1e293b; font-size: 12px; margin: 0; }}
      h1 {{ font-size: 21px; margin: 0 0 2px; }}
      h2 {{ font-size: 14px; margin: 18px 0 8px; color: {_BLUE}; border-bottom: 2px solid {_BLUE}; padding-bottom: 4px; }}
      h3 {{ font-size: 13px; margin: 0 0 10px; color: {_BLUE}; }}
      .rh {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid {_BLUE}; padding-bottom: 10px; margin-bottom: 12px; }}
      .rh .meta {{ color: #64748b; font-size: 11.5px; }} .rh .win {{ text-align: right; font-size: 11.5px; color: #64748b; }} .rh .win b {{ color: #1e293b; font-size: 13px; }}
      section {{ page-break-inside: avoid; }}
      .reco {{ border: 1px solid #e2e8f0; border-left: 4px solid {_BLUE}; border-radius: 0 8px 8px 0; padding: 10px 14px; line-height: 1.6; }}
      .note {{ color: #64748b; font-style: italic; }}
      .mono {{ font-variant-numeric: tabular-nums; }} .neg {{ color: #b91c1c; }} .pos {{ color: #15803d; }}
      /* Time status */
      .ts {{ display: flex; gap: 22px; align-items: center; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; }}
      .ts-sentence {{ font-size: 15px; line-height: 1.5; }}
      .verdicts {{ margin-top: 10px; display: flex; flex-direction: column; gap: 7px; }}
      .vrow {{ display: flex; gap: 10px; font-size: 12.5px; }} .vtag {{ flex: none; width: 108px; font-weight: 700; }}
      .vtag.bad {{ color: #b91c1c; }} .vtag.good {{ color: #15803d; }}
      .cost {{ margin-top: 12px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
      .costcard {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 13px; }}
      .costcard .cl {{ font-size: 10.5px; color: #64748b; text-transform: uppercase; letter-spacing: .3px; }}
      .costcard .cv {{ font-size: 17px; font-weight: 800; margin-top: 3px; font-variant-numeric: tabular-nums; }}
      /* By code */
      .chart2 {{ border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 14px; margin-bottom: 12px; }}
      .bc-row {{ margin-bottom: 12px; }} .bc-name {{ font-size: 12px; font-weight: 600; margin-bottom: 3px; }}
      .bc-track {{ height: 13px; background: #eef2f7; border-radius: 3px; overflow: hidden; margin-bottom: 3px; }}
      .bc-pl {{ height: 100%; background: {_PLAN}; }} .bc-ac {{ height: 100%; background: {_ACT}; }}
      .bc-num {{ font-size: 11px; color: #64748b; }}
      .bc-leg {{ font-size: 11px; color: #64748b; margin-top: 4px; }} .bc-leg span {{ margin-right: 16px; }}
      .bc-leg i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: middle; margin-right: 6px; }}
      /* Driving path */
      .dphead {{ background: #eef4fb; border: 1px solid #c9ddf3; border-radius: 8px; padding: 10px 14px; font-size: 12.5px; line-height: 1.5; margin-bottom: 12px; }}
      .chain {{ display: flex; align-items: stretch; flex-wrap: wrap; gap: 5px; margin-bottom: 8px; }}
      .arw {{ display: flex; align-items: center; color: #94a3b8; font-weight: 900; font-size: 15px; }}
      .msbox {{ flex: none; width: 188px; border: 2px solid {_BLUE}; border-radius: 10px; padding: 10px 11px; background: #eef4fb; }}
      .msbox.start {{ border-color: #3c7a49; background: #eafaf0; }}
      .msbox.start .msflag, .msbox.start .mst {{ color: #166534; }}
      .msbox .msflag {{ font-size: 9px; text-transform: uppercase; letter-spacing: .4px; color: {_BLUE}; opacity: .8; margin-bottom: 6px; }}
      .msbox .mst {{ font-size: 12px; font-weight: 800; color: {_BLUE}; line-height: 1.2; margin-bottom: 6px; }}
      .msbox .r {{ display: flex; justify-content: space-between; font-size: 11px; margin: 2px 0; }} .msbox .r span {{ color: #64748b; }}
      .box {{ flex: none; width: 184px; border: 1px solid #e2e8f0; border-radius: 10px; padding: 9px 11px; }}
      .box.done {{ border-color: #b7d5be; background: #eafaf0; }}
      .box .bt {{ font-size: 12px; font-weight: 700; line-height: 1.2; }} .box .bc {{ font-size: 9.5px; color: #94a3b8; margin: 3px 0 8px; }}
      .bx-tag {{ font-size: 8px; color: #b45309; font-weight: 600; }}
      .b4 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 8px; }}
      .b4 .k {{ font-size: 9px; color: #94a3b8; text-transform: uppercase; letter-spacing: .3px; }}
      .b4 .v {{ font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; }} .b4 .full {{ grid-column: 1 / -1; border-top: 1px dashed #e2e8f0; padding-top: 4px; }}
      /* Counts */
      .cn-total {{ font-size: 12.5px; margin-bottom: 10px; }}
      .cn-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}
      .cn-lbl {{ flex: none; width: 110px; font-size: 12.5px; font-weight: 600; }}
      .cn-bars {{ flex: 1; }}
      .cn-track {{ position: relative; height: 18px; background: #eef2f7; border-radius: 4px; margin: 3px 0; overflow: hidden; }}
      .cn-track span {{ position: absolute; left: 8px; top: 1px; font-size: 11px; font-weight: 700; color: #1e293b; }}
      .cn-pl {{ height: 100%; background: {_PLAN}; opacity: .85; }} .cn-ac {{ height: 100%; background: {_ACT}; opacity: .85; }}
      /* Scope */
      .scope-h {{ font-size: 12.5px; color: #64748b; margin-bottom: 12px; }}
      .wrow {{ display: flex; align-items: center; gap: 12px; margin-bottom: 7px; }}
      .wname {{ flex: none; width: 220px; font-size: 12px; }}
      .wtrack {{ flex: 1; height: 17px; background: #eef2f7; border-radius: 4px; overflow: hidden; }}
      .wfill {{ height: 100%; background: #bcd6f5; }} .wrow.top .wfill {{ background: {_ACT}; }}
      .wpct {{ flex: none; width: 50px; text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }}
      .rec {{ margin-top: 14px; background: #eef4fb; border: 1px solid #c9ddf3; border-radius: 10px; padding: 12px 15px; }}
      .rec h4 {{ margin: 0 0 6px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .4px; color: {_BLUE}; }}
      .rec p {{ margin: 5px 0; font-size: 13px; }} .rec .star {{ color: {_BLUE}; font-weight: 800; margin-right: 6px; }}
    </style></head><body>{"".join(body)}</body></html>'''


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
