"""Update-Analysis exporters — PDF (HTML → Chrome headless) and Excel.

`render_html` lays out the same three sections as the screen — Time Status, Planned vs
Actual by activity code, and the Critical Path Analyzer — in the house consultant style
(shared with the Update-vs-Update report). `report_excel` mirrors them into one sheet.
Nothing here computes a number; it only presents what `p6_update.analysis` produced.
"""
import html

_BLUE = '#26517d'


def _e(v):
    return html.escape(str(v if v is not None else ''))


def _pct(v):
    return f'{v:.0f}%' if isinstance(v, (int, float)) else '—'


def _svar(v):
    if v is None:
        return '—'
    return f'+{v}' if v > 0 else str(v)


# ── Section 1 · Time Status ─────────────────────────────────────────────────

def _donut(elapsed, planned, actual):
    """Outer ring = time elapsed; inner faint ring = planned; inner solid = actual."""
    def arc(r, pct):
        c = 2 * 3.14159265 * r
        on = c * max(0.0, min(100.0, pct or 0)) / 100.0
        return f'{on:.1f} {c - on:.1f}', c
    (od, _), (pd, _), (ad, _) = arc(58, elapsed), arc(40, planned), arc(40, actual)
    lab = f'{actual:.0f}%' if actual is not None else '—'
    sub = f'of {planned:.0f}% planned' if planned is not None else ''
    return f'''<svg width="150" height="150" viewBox="0 0 150 150">
      <circle cx="75" cy="75" r="58" fill="none" stroke="#eef2f7" stroke-width="18"/>
      <circle cx="75" cy="75" r="58" fill="none" stroke="#2a78d6" stroke-width="18" stroke-dasharray="{od}" transform="rotate(-90 75 75)"/>
      <circle cx="75" cy="75" r="40" fill="none" stroke="#eef2f7" stroke-width="10"/>
      <circle cx="75" cy="75" r="40" fill="none" stroke="#a7e0bd" stroke-width="10" stroke-dasharray="{pd}" transform="rotate(-90 75 75)"/>
      <circle cx="75" cy="75" r="40" fill="none" stroke="#16a34a" stroke-width="10" stroke-dasharray="{ad}" transform="rotate(-90 75 75)"/>
      <text x="75" y="71" text-anchor="middle" font-size="16" font-weight="700" fill="#1e293b">{_e(lab)}</text>
      <text x="75" y="88" text-anchor="middle" font-size="10" fill="#94a3b8">{_e(sub)}</text>
    </svg>'''


def _timestatus_html(report):
    ts = report.get('time_status', {}) or {}
    ep, pp, ap = ts.get('elapsed_pct'), ts.get('planned_pct'), ts.get('actual_pct')
    elapsed_txt = '—'
    if ep is not None:
        elapsed_txt = f'{ep:.0f}%'
        if ts.get('exceeded_days'):
            elapsed_txt = f'100% — baseline exceeded by {ts["exceeded_days"]} days'
    sentence = (f'<b>{elapsed_txt}</b> of the baseline time has elapsed, and progress achieved is '
                f'<b>{_pct(ap)}</b> against <b>{_pct(pp)}</b> planned.')
    chips = []
    if ts.get('behind_clock') is not None:
        v = ts['behind_clock']
        chips.append(f'<span class="chip {"bad" if v > 0 else "good"}">'
                     f'{abs(v)} points {"behind" if v > 0 else "ahead of"} the clock</span>')
    if ts.get('behind_plan') is not None:
        v = ts['behind_plan']
        chips.append(f'<span class="chip {"bad" if v > 0 else "good"}">'
                     f'{abs(v)} points {"behind" if v > 0 else "ahead of"} plan</span>')
    legend = (f'<div class="ts-leg"><span><i style="background:#2a78d6"></i>Time elapsed '
              f'{_pct(ep) if ep is not None else "—"} — calendar days to baseline finish</span>'
              f'<span><i style="background:#a7e0bd"></i>Planned {_pct(pp)} — PV ÷ budget</span>'
              f'<span><i style="background:#16a34a"></i>Actual {_pct(ap)} — earned value ÷ budget</span></div>')
    return (f'<div class="ts"><div class="ts-donut">{_donut(ep, pp, ap)}</div>'
            f'<div class="ts-body"><div class="ts-sentence">{sentence}</div>'
            f'<div class="ts-chips">{"".join(chips)}</div>{legend}</div></div>')


# ── Section 2 · Planned vs Actual by activity code ──────────────────────────

def _bycode_rows(report, code_filter):
    """Return (label, rows) — either the filtered combination or a default single type."""
    if code_filter and code_filter.get('rows') is not None:
        return code_filter.get('label') or ' · '.join(code_filter.get('types') or []), code_filter['rows']
    by = report.get('by_code', {}) or {}
    if code_filter and code_filter.get('type') and code_filter['type'] in by:
        t = code_filter['type']
        return t, by[t]
    if by:
        t = next(iter(by))
        return t, by[t]
    return None, []


def _bycode_html(report, code_filter=None):
    label, rows = _bycode_rows(report, code_filter)
    if not rows:
        return '<p class="note">No activity codes found in this update to break progress down by.</p>'
    sel = f'<div class="bc-lbl">By <b>{_e(label)}</b> · planned vs actual, worst gap first</div>'
    bars = []
    for r in rows:
        var = r.get('variance', 0)
        cls = 'bad' if var <= -8 else ('warn' if var < 0 else 'good')
        bars.append(
            f'<div class="bc-row"><div class="bc-name">{_e(r.get("value"))}</div>'
            f'<div class="bc-track"><div class="bc-pl" style="width:{max(0, min(100, r.get("planned", 0)))}%"></div></div>'
            f'<div class="bc-track"><div class="bc-ac {cls}" style="width:{max(0, min(100, r.get("actual", 0)))}%"></div></div>'
            f'<div class="bc-num">planned {r.get("planned", 0):.0f}% · actual {r.get("actual", 0):.0f}% · '
            f'<b class="{cls}">{_svar(var)}</b></div></div>')
    leg = ('<div class="bc-leg"><span><i style="background:#e5ebf2;border:1px solid #cbd5e1"></i>Planned %</span>'
           '<span><i style="background:#2a78d6"></i>Actual % (colour = size of gap)</span></div>')
    return sel + '<div class="bc">' + ''.join(bars) + '</div>' + leg


# ── Section 3 · Critical Path Analyzer ──────────────────────────────────────

def _critical_html(report):
    cp = report.get('critical_path', {}) or {}
    if not cp.get('charts'):
        return '<p class="note">No governing completion milestone with a driving path was found in this update.</p>'
    out = []
    if cp.get('headline'):
        out.append(f'<div class="cpconcl warn"><div>{_e(cp["headline"])}</div></div>')
    for chart in cp['charts']:
        ms = chart.get('milestone', {}) or {}
        out.append(f'<div class="cprowlbl">Driving path → {_e(ms.get("name"))} '
                   f'(baseline {_e(ms.get("baseline_finish"))} → expected {_e(ms.get("expected_finish"))}, '
                   f'slip {_svar(ms.get("slip_days"))} wd)</div>')
        chain = []
        boxes = chart.get('boxes', [])
        for i, b in enumerate(boxes):
            cls = 'gone' if b.get('complete') else 'shared'
            chain.append(
                f'<div class="cpblk {cls}">{_e(b.get("name"))}'
                f'<small>{b.get("pct", 0):.0f}% · exp {_e(b.get("exp_finish"))}</small>'
                f'<small>{_e(b.get("crumb"))}</small></div>')
            if i < len(boxes) - 1:
                chain.append('<div class="cparw">▸</div>')
        out.append(f'<div class="cpchain">{"".join(chain)}</div>')
        # per-box table for the exact numbers
        trows = ''.join(
            f'<tr><td>{_e(b.get("crumb"))}</td><td class="cpt-fin">{_e(b.get("name"))}</td>'
            f'<td class="num">{b.get("pct", 0):.0f}%</td><td class="mono">{_e(b.get("bl_finish"))}</td>'
            f'<td class="mono cpt-fin">{_e(b.get("exp_finish"))}</td>'
            f'<td class="num {"neg" if (b.get("slip_days") or 0) > 0 else ""}">{_svar(b.get("slip_days"))}</td>'
            f'<td>{"complete" if b.get("complete") else "on path"}</td></tr>'
            for b in boxes)
        out.append('<table class="data"><thead><tr><th>Above (WBS)</th><th>Work front</th>'
                   '<th class="num">% complete</th><th>BL finish</th><th>Expected finish</th>'
                   '<th class="num">Slip (wd)</th><th>Status</th></tr></thead><tbody>' + trows + '</tbody></table>')
    return ''.join(out)


# ── Assembly ────────────────────────────────────────────────────────────────

def render_html(report, sections=None, code_filter=None):
    """`sections` = list of section keys to include (None = all): time · bycode · critical ·
    conclusion. `code_filter` picks which activity-code breakdown Section 2 shows."""
    header = (f'<div class="rh"><div><h1>Update Analysis</h1>'
              f'<div class="meta">{_e(report.get("project_name"))} · single-update read against its baseline</div></div>'
              f'<div class="win">Data date<br><b>{_e(report.get("data_date"))}</b>'
              f'<br>{_e(report.get("file") or "")}</div></div>')
    secs = [
        ('conclusion', 'Executive read', f'<div class="reco">{_e(report.get("conclusion"))}</div>'),
        ('time', '1 · Time Status', _timestatus_html(report)),
        ('bycode', '2 · Planned vs Actual — by activity code', _bycode_html(report, code_filter)),
        ('critical', '3 · Critical Path Analyzer', _critical_html(report)),
    ]
    keys = set(sections) if sections else None
    body = [header]
    for key, title, htmls in secs:
        if keys is not None and key not in keys:
            continue
        body.append(f'<section data-sec="{key}"><h2>{_e(title)}</h2>{htmls}</section>')
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 11mm; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: system-ui, -apple-system, Arial, sans-serif; color: #1e293b; font-size: 12px; margin: 0; }}
      h1 {{ font-size: 21px; margin: 0 0 2px; }}
      h2 {{ font-size: 14px; margin: 18px 0 8px; color: {_BLUE}; border-bottom: 2px solid {_BLUE}; padding-bottom: 4px; }}
      .rh {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid {_BLUE}; padding-bottom: 10px; margin-bottom: 12px; }}
      .rh .meta {{ color: #64748b; font-size: 11.5px; }} .rh .win {{ text-align: right; font-size: 11.5px; color: #64748b; }} .rh .win b {{ color: #1e293b; font-size: 13px; }}
      section {{ page-break-inside: avoid; }}
      .reco {{ border: 1px solid #e2e8f0; border-left: 4px solid {_BLUE}; border-radius: 0 8px 8px 0; padding: 10px 14px; line-height: 1.6; }}
      .note {{ color: #64748b; font-style: italic; }}
      .num {{ text-align: right; font-variant-numeric: tabular-nums; }} .mono {{ font-family: Consolas, monospace; }}
      .neg {{ color: #b91c1c; font-weight: 700; }} .pos {{ color: #15803d; font-weight: 700; }}
      .good {{ color: #15803d; }} .bad {{ color: #b91c1c; }} .warn {{ color: #b45309; }}
      /* Time status */
      .ts {{ display: flex; gap: 24px; align-items: center; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; }}
      .ts-sentence {{ font-size: 15px; line-height: 1.5; }}
      .ts-chips {{ margin: 10px 0; }}
      .chip {{ display: inline-block; border-radius: 20px; padding: 4px 12px; font-size: 12px; margin-right: 8px; }}
      .chip.bad {{ background: #fdecec; color: #b91c1c; border: 1px solid #f2b8b8; }}
      .chip.good {{ background: #eafaf0; color: #166534; border: 1px solid #a7e0bd; }}
      .ts-leg {{ font-size: 11px; color: #64748b; }} .ts-leg span {{ display: block; margin: 2px 0; }}
      .ts-leg i {{ display: inline-block; width: 11px; height: 11px; border-radius: 3px; vertical-align: middle; margin-right: 6px; }}
      /* By code */
      .bc-lbl {{ font-size: 12px; color: #475569; margin-bottom: 10px; }}
      .bc-row {{ margin-bottom: 14px; }}
      .bc-name {{ font-size: 12px; color: #334155; margin-bottom: 3px; font-weight: 600; }}
      .bc-track {{ height: 12px; background: #eef2f7; border-radius: 3px; overflow: hidden; margin-bottom: 3px; }}
      .bc-pl {{ height: 100%; background: #cbd5e1; }} .bc-ac {{ height: 100%; background: #2a78d6; }}
      .bc-ac.bad {{ background: #dc2626; }} .bc-ac.warn {{ background: #d97706; }} .bc-ac.good {{ background: #16a34a; }}
      .bc-num {{ font-size: 11px; color: #64748b; }}
      .bc-leg {{ font-size: 11px; color: #64748b; margin-top: 6px; }} .bc-leg span {{ margin-right: 16px; }}
      .bc-leg i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: middle; margin-right: 6px; }}
      /* Critical path */
      .cpconcl {{ border-radius: 8px; padding: 10px 14px; font-size: 12.5px; line-height: 1.5; margin-bottom: 13px; display: flex; gap: 9px; }}
      .cpconcl.warn {{ background: #fff6e9; color: #92400e; }}
      .cprowlbl {{ font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .4px; color: #64748b; margin: 10px 0 6px; }}
      .cpchain {{ display: flex; align-items: stretch; flex-wrap: wrap; gap: 2px; margin-bottom: 8px; }}
      .cpblk {{ flex: none; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 52px; border-radius: 7px; font-weight: 700; font-size: 11px; padding: 5px 8px; text-align: center; max-width: 150px; }}
      .cpblk small {{ font-weight: 500; font-size: 8.5px; opacity: .9; margin-top: 2px; }}
      .cpblk.shared {{ background: #bcd6f5; color: #1e3a8a; }} .cpblk.new {{ background: #f4a3a3; color: #7f1d1d; }} .cpblk.gone {{ background: #d7ead9; color: #166534; }}
      .cparw {{ flex: none; display: flex; align-items: center; color: #94a3b8; font-weight: 900; font-size: 14px; padding: 0 3px; }}
      table.data {{ width: 100%; border-collapse: collapse; font-size: 10.5px; margin: 6px 0; }}
      table.data th {{ background: {_BLUE}; color: #fff; text-align: left; padding: 5px 6px; font-weight: 600; }}
      table.data th.num {{ text-align: right; }}
      table.data td {{ border-bottom: 1px solid #e2e8f0; padding: 4px 6px; vertical-align: top; }}
      .cpt-fin {{ font-weight: 700; }}
    </style></head><body>{"".join(body)}</body></html>'''


# ── Excel: one sheet mirroring the three sections ───────────────────────────

_HEADERS = ['Section', 'Above (WBS)', 'Item / Work front', 'Planned %', 'Actual %',
            'Variance', 'Baseline finish', 'Expected finish', 'Slip (wd)']


def report_excel(report):
    """(headers, rows) for a single sheet mirroring the PDF: Time Status, Planned-vs-Actual
    by every activity code, then the Critical Path work fronts."""
    rows = []
    ts = report.get('time_status', {}) or {}
    elapsed = ('100% (exceeded by %d d)' % ts['exceeded_days']) if ts.get('exceeded_days') else (
        f'{ts.get("elapsed_pct")}%' if ts.get('elapsed_pct') is not None else '')
    rows.append(['Time Status', '', f'Time elapsed {elapsed}',
                 ts.get('planned_pct', ''), ts.get('actual_pct', ''),
                 ts.get('behind_plan', ''), ts.get('baseline_finish', ''), '', ''])

    for t, brows in (report.get('by_code', {}) or {}).items():
        for r in brows:
            rows.append([f'Planned vs Actual · {t}', '', r.get('value', ''),
                         r.get('planned', ''), r.get('actual', ''), r.get('variance', ''), '', '', ''])

    cp = report.get('critical_path', {}) or {}
    for chart in cp.get('charts', []):
        ms = chart.get('milestone', {}) or {}
        rows.append(['Critical Path — milestone', '', ms.get('name', ''),
                     '', '', '', ms.get('baseline_finish', ''), ms.get('expected_finish', ''),
                     ms.get('slip_days', '')])
        for b in chart.get('boxes', []):
            rows.append(['Critical Path — work front', b.get('crumb', ''), b.get('name', ''),
                         '', b.get('pct', ''), '', b.get('bl_finish', ''), b.get('exp_finish', ''),
                         b.get('slip_days', '')])
    return _HEADERS, rows
