"""Consultant Review exporters — PDF (HTML → Chrome) and Excel.

`render_html` builds a print-ready, landscape consultant page from the comparison
report (and the optional before/after impact). `logic_excel` flattens the driving
logic & lag change table into (headers, rows) for the single-sheet xlsx writer.

Nothing here computes a number — it only lays out what the engine already produced.
"""
import html

_GREY = '#888781'
_BLUE = '#2a78d6'
_RED = '#e24b4a'

# Manager-report PDF: cap each table so the PDF stays a readable few pages (was ~470 on a
# real project); the complete row-by-row detail goes to the Excel export.
_PDF_ROW_CAP = 50


def _e(v):
    return html.escape(str(v if v is not None else ''))


def _links_str(links, key):
    """Flatten one activity's driving links (list of {code,name,type,lag_days,status})
    into a single cell string, one link per line."""
    if not links:
        return '—'
    out = []
    for l in links:
        if key == 'id':
            out.append(str(l.get('code', '')))
        elif key == 'name':
            out.append(str(l.get('name', '')))
        else:
            t = l.get('type', 'FS')
            lag = round(l.get('lag_days', 0) or 0)
            out.append(t if not lag else f"{t}{'+' if lag > 0 else ''}{lag}")
    return ' / '.join(out)


# ── Excel: the driving logic & lag change table ─────────────────────────────

_LOGIC_HEADERS = [
    '#', 'Activity ID', 'Activity name', 'Change',
    'Baseline pred ID', 'Baseline pred rel', 'Baseline pred name',
    'Baseline succ ID', 'Baseline succ rel', 'Baseline succ name',
    'Update pred ID', 'Update pred rel', 'Update pred name',
    'Update succ ID', 'Update succ rel', 'Update succ name',
]


def logic_excel(report):
    """(headers, rows) for the driving logic change table; multi-driving links joined.
    Rows carry a leading 1-based serial number matching the on-screen table."""
    rows = []
    for i, r in enumerate((report.get('logic', {}) or {}).get('rows', []), start=1):
        rows.append([
            i, r.get('activity_id', ''), r.get('activity_name', ''), r.get('change_label', ''),
            _links_str(r.get('baseline_preds'), 'id'), _links_str(r.get('baseline_preds'), 'rel'), _links_str(r.get('baseline_preds'), 'name'),
            _links_str(r.get('baseline_succs'), 'id'), _links_str(r.get('baseline_succs'), 'rel'), _links_str(r.get('baseline_succs'), 'name'),
            _links_str(r.get('update_preds'), 'id'), _links_str(r.get('update_preds'), 'rel'), _links_str(r.get('update_preds'), 'name'),
            _links_str(r.get('update_succs'), 'id'), _links_str(r.get('update_succs'), 'rel'), _links_str(r.get('update_succs'), 'name'),
        ])
    return _LOGIC_HEADERS, rows


# ── PDF: HTML → Chrome ──────────────────────────────────────────────────────

def _scurve_svg(sc):
    periods = sc.get('periods') or []
    if len(periods) < 2:
        return ''
    x0, x1, y0, y1 = 45, 900, 250, 20
    n = len(periods)
    xat = lambda i: x0 + (x1 - x0) * (i / (n - 1))
    yat = lambda p: y0 - (y0 - y1) * (max(0.0, min(100.0, p or 0)) / 100.0)

    def poly(arr, color, dash=None):
        if not arr:
            return ''
        pts = ' '.join(f'{xat(i):.1f},{yat(p):.1f}' for i, p in enumerate(arr))
        d = f' stroke-dasharray="{dash}"' if dash else ''
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"{d}/>'

    step = max(1, round(n / 10))
    xlab = ''.join(
        f'<text x="{xat(i):.1f}" y="{y0 + 18}" text-anchor="middle" font-size="11" fill="#666">{_e(periods[i])}</text>'
        for i in range(0, n, step))
    return f'''<svg viewBox="0 0 940 285" width="100%">
      <line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#ccc"/>
      <line x1="{x0}" y1="{y1}" x2="{x0}" y2="{y0}" stroke="#ccc"/>
      <text x="{x0 - 6}" y="{y1 + 4}" text-anchor="end" font-size="11" fill="#666">100%</text>
      <text x="{x0 - 6}" y="{(y0 + y1) / 2:.0f}" text-anchor="end" font-size="11" fill="#666">50%</text>
      <text x="{x0 - 6}" y="{y0}" text-anchor="end" font-size="11" fill="#666">0%</text>
      {poly(sc.get('baseline'), _GREY, '5 3')}
      {poly(sc.get('after'), _RED)}
      {poly(sc.get('before'), _BLUE)}
      {xlab}
    </svg>'''


def _tile(label, value, sub=None):
    s = f'<div class="tsub">{_e(sub)}</div>' if sub else ''
    return f'<div class="tile"><div class="tl">{_e(label)}</div><div class="tv">{_e(value)}</div>{s}</div>'


def _logic_table_html(report, cap=_PDF_ROW_CAP):
    rows = (report.get('logic', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No driving relationship or lag changes vs the baseline.</p>'
    shown, total = rows[:cap], len(rows)
    body = []
    for i, r in enumerate(shown, start=1):
        body.append(
            '<tr>'
            f'<td class="num">{i}</td>'
            f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
            f'<td>{_e(r.get("change_label"))}</td>'
            f'<td class="mono">{_e(_links_str(r.get("baseline_preds"), "id"))}</td>'
            f'<td class="mono">{_e(_links_str(r.get("baseline_preds"), "rel"))}</td>'
            f'<td>{_e(_links_str(r.get("baseline_preds"), "name"))}</td>'
            f'<td class="mono">{_e(_links_str(r.get("baseline_succs"), "id"))}</td>'
            f'<td class="mono">{_e(_links_str(r.get("baseline_succs"), "rel"))}</td>'
            f'<td>{_e(_links_str(r.get("baseline_succs"), "name"))}</td>'
            f'<td class="mono">{_e(_links_str(r.get("update_preds"), "id"))}</td>'
            f'<td class="mono chg">{_e(_links_str(r.get("update_preds"), "rel"))}</td>'
            f'<td>{_e(_links_str(r.get("update_preds"), "name"))}</td>'
            f'<td class="mono">{_e(_links_str(r.get("update_succs"), "id"))}</td>'
            f'<td class="mono chg">{_e(_links_str(r.get("update_succs"), "rel"))}</td>'
            f'<td>{_e(_links_str(r.get("update_succs"), "name"))}</td>'
            '</tr>')
    return (
        '<table class="data"><thead><tr>'
        '<th rowspan="2">#</th><th rowspan="2">Activity ID</th><th rowspan="2">Activity name</th><th rowspan="2">Change</th>'
        '<th colspan="6" class="grp">Baseline — driving links</th>'
        '<th colspan="6" class="grpu">Update — driving links</th></tr>'
        '<tr><th>Pred ID</th><th>Pred rel</th><th>Pred name</th><th>Succ ID</th><th>Succ rel</th><th>Succ name</th>'
        '<th>Pred ID</th><th>Pred rel</th><th>Pred name</th><th>Succ ID</th><th>Succ rel</th><th>Succ name</th></tr>'
        '</thead><tbody>' + ''.join(body) + '</tbody></table>'
        + (f'<p class="note">Showing the first {cap} of {total} logic / lag changes — the '
           f'complete list is in the Excel export.</p>' if total > cap else ''))


def _duration_table_html(report, cap=_PDF_ROW_CAP):
    rows = (report.get('durations', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No duration or remaining changes vs the baseline.</p>'
    total = len(rows)
    body = ''.join(
        '<tr>'
        f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
        f'<td class="num">{_e(r.get("baseline_orig_days"))} d</td>'
        f'<td class="num">{_e(r.get("update_orig_days"))} d</td>'
        f'<td class="num">{_e(r.get("remaining_days"))} d</td>'
        f'<td class="num">{_e(r.get("remaining_minus_baseline_days"))} d</td>'
        f'<td>{_e(r.get("status"))}</td>'
        f'<td>{_e(_impact_word(r.get("impact")))}</td></tr>'
        for r in rows[:cap])
    more = (f'<p class="note">Showing the {cap} largest of {total} duration / remaining changes — '
            f'the full list is in the Excel export.</p>' if total > cap else '')
    return ('<table class="data"><thead><tr><th>Activity ID</th><th>Activity name</th>'
            '<th>Baseline orig.</th><th>Update orig.</th><th>Remaining</th><th>Rem − baseline</th>'
            '<th>Status</th><th>Impact on finish</th></tr></thead><tbody>' + body + '</tbody></table>'
            + _duration_legend_html() + more)


def _duration_legend_html():
    return ('<div class="legend2">'
            '<div><b>Columns —</b> <b>Baseline orig.</b> original duration in the baseline · '
            '<b>Update orig.</b> original duration now · <b>Remaining</b> left at the data date · '
            '<b>Rem − baseline</b> remaining minus the baseline original (positive = more work left than the '
            'baseline allowed).</div>'
            '<div><b>Impact on finish —</b> <b>Direct</b> on the critical path, pushes the finish · '
            '<b>Potential</b> near-critical (≤ 10 wd float) · <b>Float absorbs</b> enough float to swallow it · '
            '<b>—</b> the export carries no float for that activity, so it can\'t be judged.</div></div>')


def _impact_word(impact):
    return {'Direct': 'Direct', 'Potential': 'Potential', 'None': 'Float absorbs'}.get(impact, '—')


def _impact_html(impact):
    if not impact:
        return ''
    f = impact.get('forecast', {}) or {}
    scurve = _scurve_svg(impact.get('scurve', {}) or {})
    scurve_block = (f'<h2>S-curve — baseline vs reported vs but-for</h2>'
                    f'<div class="legend"><span><i style="background:{_GREY}"></i>Baseline plan</span>'
                    f'<span><i style="background:{_RED}"></i>Reported (update)</span>'
                    f'<span><i style="background:{_BLUE}"></i>But-for (corrected)</span></div>'
                    f'{scurve}') if scurve else ''
    return f'''
      <h2>Impact — reported vs but-for delay</h2>
      <div class="tiles">
        {_tile('Reported delay (as submitted)', _days(impact.get('delay_after')))}
        {_tile('But-for delay (baseline logic)', _days(impact.get('delay_before')))}
        {_tile('Manufactured', _days(impact.get('manufactured_days')))}
      </div>
      <p class="fc">Overall completion — baseline <b>{_e(f.get('baseline'))}</b> · reported (update) <b>{_e(f.get('after'))}</b> · but-for (corrected) <b>{_e(f.get('before'))}</b></p>
      {scurve_block}
      <h2>Consultant recommendation</h2>
      <div class="reco">{_e(impact.get('recommendation'))}</div>'''


def _charts_html(report):
    """Executive-dashboard charts for the PDF: change-type bars, finish-slip timeline,
    changed-activity donut. Static HTML/SVG (light theme) mirroring the on-screen charts."""
    dash = report.get('dashboard', {}) or {}
    total = dash.get('changed_activities', 0) or 0
    logic_n = dash.get('logic_changed', 0) or 0
    dur_n = dash.get('duration_only', 0) or 0

    # 1) change-type bars — logic-group items, biggest first
    items = [it for it in (report.get('change_summary', {}) or {}).get('items', [])
             if it.get('group') == 'logic' and (it.get('count') or 0) > 0]
    items.sort(key=lambda it: -(it.get('count') or 0))
    if items:
        mx = items[0].get('count') or 1
        bars = ''.join(
            f'<div class="cbar"><div class="cbl">{_e(it.get("label"))}</div>'
            f'<div class="cbt"><div class="cbf" style="width:{round((it.get("count") or 0) / mx * 100)}%"></div></div>'
            f'<div class="cbv">{_e(it.get("count"))}</div></div>' for it in items)
    else:
        bars = '<p class="note">No driving-logic or lag changes.</p>'

    # 2) delay — finish-date variance vs baseline, in working days (the honest delay)
    slip = dash.get('delay_working_days')
    if slip is None:
        snum, sword, scol, sline = '—', 'no finish date', '#64748b', ''
    elif slip > 0:
        snum, sword, scol = f'+{slip}', 'working days behind the baseline finish', _RED
        sline = f'<line x1="150" y1="30" x2="268" y2="30" stroke="{_RED}" stroke-width="6" stroke-linecap="round"/>'
    elif slip < 0:
        snum, sword, scol = f'−{-slip}', 'working days ahead of the baseline finish', '#16a34a'
        sline = f'<line x1="150" y1="30" x2="268" y2="30" stroke="#16a34a" stroke-width="6" stroke-linecap="round"/>'
    else:
        snum, sword, scol, sline = '0', 'on the baseline finish', '#64748b', ''
    dd, bf, uf = _e(report.get('data_date') or '—'), _e(report.get('baseline_finish') or '—'), _e(report.get('update_finish') or '—')
    slip_svg = (f'<div class="slh"><span class="sln" style="color:{scol}">{snum}</span>'
                f'<span class="slc">{sword}</span></div>'
                '<svg viewBox="0 0 300 64" width="100%">'
                '<line x1="14" y1="30" x2="286" y2="30" stroke="#cbd5e1" stroke-width="2" stroke-linecap="round"/>'
                f'{sline}'
                '<circle cx="36" cy="30" r="4.5" fill="#94a3b8"/>'
                '<text x="36" y="48" text-anchor="middle" font-size="8.5" fill="#64748b">Data date</text>'
                f'<text x="36" y="59" text-anchor="middle" font-size="8.5" font-weight="700" fill="#1e293b">{dd}</text>'
                f'<circle cx="150" cy="30" r="5.5" fill="#fff" stroke="{_BLUE}" stroke-width="3"/>'
                '<text x="150" y="15" text-anchor="middle" font-size="8.5" fill="#64748b">Baseline</text>'
                f'<text x="150" y="48" text-anchor="middle" font-size="8.5" font-weight="700" fill="#1e293b">{bf}</text>'
                f'<circle cx="268" cy="30" r="5.5" fill="{_RED}"/>'
                f'<text x="268" y="15" text-anchor="middle" font-size="8.5" font-weight="700" fill="{_RED}">Update</text>'
                f'<text x="268" y="48" text-anchor="middle" font-size="8.5" font-weight="700" fill="#1e293b">{uf}</text>'
                '</svg>')

    # 3) changed-activity donut
    C = 326.726
    t = logic_n + dur_n
    lf, df = (logic_n / t, dur_n / t) if t else (0.0, 0.0)
    gap = 2 if (lf > 0 and df > 0) else 0
    la, da = max(0.0, lf * C - gap), max(0.0, df * C - gap)
    donut = (f'<div class="dnw"><svg viewBox="0 0 130 130" width="104" height="104">'
             '<circle cx="65" cy="65" r="52" fill="none" stroke="#e2e8f0" stroke-width="20"/>'
             f'<circle cx="65" cy="65" r="52" fill="none" stroke="{_BLUE}" stroke-width="20" stroke-dasharray="{la:.1f} {C - la:.1f}" transform="rotate(-90 65 65)"/>'
             f'<circle cx="65" cy="65" r="52" fill="none" stroke="#eb6834" stroke-width="20" stroke-dasharray="{da:.1f} {C - da:.1f}" stroke-dashoffset="{-lf * C:.1f}" transform="rotate(-90 65 65)"/>'
             f'<text x="65" y="61" text-anchor="middle" font-size="20" font-weight="800" fill="#1e293b">{total}</text>'
             '<text x="65" y="78" text-anchor="middle" font-size="9" fill="#64748b">changed</text></svg>'
             f'<div class="dnl"><div><i style="background:{_BLUE}"></i><b>{logic_n}</b> logic / lag <span>({round(lf * 100)}%)</span></div>'
             f'<div><i style="background:#eb6834"></i><b>{dur_n}</b> duration only <span>({round(df * 100)}%)</span></div></div></div>')

    # but-for (instant, no-F9 estimate): how much of the delay the edits manufactured
    bf_wd, mfd = dash.get('butfor_delay_working_days'), dash.get('manufactured_working_days')
    if bf_wd is not None and mfd is not None:
        if mfd > 0:
            verdict = (f"{mfd} of the {slip or 0} working days were manufactured — reverting the flagged "
                       f"changes pulls the finish in to {_e(dash.get('butfor_finish') or '—')}.")
        elif mfd == 0:
            verdict = (f"Reverting the flagged changes doesn't move the finish — the {slip or 0}-working-day "
                       f"delay is genuine, not manufactured.")
        else:
            verdict = "Reverting the flagged changes does not reduce the delay."
        hot = ' style="background:#fdeaea;border-color:#f3c1c1"' if mfd and mfd > 0 else ''
        butfor_pdf = (f'<div class="butfor"{hot}><b>But-for delay: {bf_wd} wd · {mfd} manufactured</b>'
                      f'<div class="bfn">{verdict} Instant estimate — tool-scheduled, no F9.</div></div>')
    else:
        butfor_pdf = ''

    return (f'<div class="charts">'
            f'<div class="chart"><div class="ct">How the logic was changed</div><div class="cs">Every driving-logic / lag change, by type.</div>{bars}</div>'
            f'<div class="chart"><div class="ct">Delay vs baseline</div><div class="cs">Finish date vs baseline, in working days — the honest delay.</div>{slip_svg}{butfor_pdf}</div>'
            f'<div class="chart"><div class="ct">Changed activities</div><div class="cs">The {total} split by what changed.</div>{donut}</div>'
            f'</div>')


def render_html(report, impact=None):
    cs = report.get('change_summary', {}) or {}
    pills = ''.join(f'<span class="pill">{it.get("count")} {_e(it.get("label"))}</span>'
                    for it in cs.get('items', [])) or '<span class="note">No changes vs the baseline.</span>'
    dash = _impact_dashboard(report, impact)
    dboard = report.get('dashboard') or {}
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 12mm; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: system-ui, -apple-system, Arial, sans-serif; color: #1e293b; font-size: 12px; margin: 0; }}
      h1 {{ font-size: 20px; margin: 0 0 2px; }}
      h2 {{ font-size: 14px; margin: 18px 0 8px; border-bottom: 2px solid #1e2d40; padding-bottom: 4px; }}
      .sub {{ color: #64748b; font-size: 12px; margin-bottom: 10px; }}
      .tiles {{ display: flex; gap: 10px; margin: 8px 0; }}
      .tile {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 14px; min-width: 150px; }}
      .tl {{ font-size: 10px; text-transform: uppercase; letter-spacing: .5px; color: #64748b; font-weight: 700; }}
      .tv {{ font-size: 20px; font-weight: 800; margin-top: 2px; }}
      .tsub {{ font-size: 10.5px; color: #475569; font-weight: 600; margin-top: 4px; }}
      .recon {{ font-size: 11.5px; color: #334155; margin: 2px 0 6px; }} .recon b {{ color: #1e293b; }}
      .pill {{ display: inline-block; background: #eef2ff; color: #1e3a8a; border-radius: 12px; padding: 2px 10px; font-size: 11px; margin: 0 6px 6px 0; }}
      table.data {{ width: 100%; border-collapse: collapse; font-size: 10.5px; margin: 6px 0; }}
      table.data th {{ background: #26517d; color: #fff; text-align: left; padding: 5px 6px; font-weight: 600; }}
      table.data th.grp {{ background: #445; }} table.data th.grpu {{ background: #1e3a8a; }}
      table.data td {{ border-bottom: 1px solid #e2e8f0; padding: 4px 6px; vertical-align: top; }}
      .mono {{ font-family: Consolas, monospace; }}
      .num {{ text-align: right; }}
      .chg {{ color: #b91c1c; font-weight: 700; }}
      .note {{ color: #64748b; font-style: italic; }}
      .fc {{ color: #334155; }}
      .legend {{ font-size: 11px; color: #64748b; margin: 4px 0; }}
      .legend span {{ margin-right: 16px; }} .legend i {{ display: inline-block; width: 16px; height: 3px; vertical-align: middle; margin-right: 5px; }}
      .reco {{ border: 1px solid #e2e8f0; border-left: 4px solid #16a34a; border-radius: 0 8px 8px 0; padding: 10px 14px; line-height: 1.6; }}
      .charts {{ display: grid; grid-template-columns: 1.5fr 1.15fr 1fr; gap: 10px; margin: 10px 0; }}
      .chart {{ border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; }}
      .ct {{ font-size: 12px; font-weight: 800; }}
      .cs {{ font-size: 10px; color: #64748b; margin: 2px 0 9px; }}
      .cbar {{ display: grid; grid-template-columns: 120px 1fr 30px; align-items: center; gap: 7px; margin-bottom: 6px; }}
      .cbl {{ font-size: 9.5px; color: #475569; text-align: right; line-height: 1.15; }}
      .cbt {{ height: 12px; background: #eef1f5; border-radius: 6px; overflow: hidden; }}
      .cbf {{ height: 100%; background: #2a78d6; border-radius: 6px; }}
      .cbv {{ font-size: 10px; font-weight: 800; text-align: right; }}
      .slh {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }}
      .sln {{ font-size: 24px; font-weight: 800; line-height: 1; }}
      .slc {{ font-size: 10px; color: #64748b; font-weight: 600; }}
      .dnw {{ display: flex; align-items: center; gap: 10px; }}
      .dnl {{ font-size: 10.5px; }}
      .dnl div {{ display: flex; align-items: center; gap: 6px; margin: 4px 0; }}
      .dnl i {{ width: 10px; height: 10px; border-radius: 2px; }}
      .dnl span {{ color: #64748b; }}
      .butfor {{ margin-top: 8px; padding: 6px 9px; border: 1px solid #e2e8f0; border-radius: 7px; font-size: 10px; line-height: 1.35; background: #f8fafc; }}
      .butfor b {{ color: #1e293b; }}
      .bfn {{ color: #64748b; margin-top: 2px; }}
      table.data tr {{ page-break-inside: avoid; }}
      table.data thead {{ display: table-header-group; }}
      .newscope {{ display: inline-block; font-size: 8px; font-weight: 700; padding: 0 4px; border-radius: 8px; background: #fdeccb; color: #8a5a00; }}
      .legend2 {{ font-size: 9.5px; color: #64748b; line-height: 1.5; margin: 5px 0 2px; }}
      .legend2 b {{ color: #1e293b; }}
    </style></head><body>
      <h1>Consultant Review — Baseline vs Current Update</h1>
      <div class="sub">{_e(report.get('project_name'))} · data date {_e(report.get('data_date'))} · baseline {_e(report.get('baseline_file'))} vs {_e(report.get('update_file'))}</div>
      {dash}
      {_charts_html(report)}
      <h2>Driving logic &amp; lag changes vs baseline</h2>
      <p class="recon">Activities with driving-logic / lag changes: <b>{dboard.get('logic_changed', 0)}</b> — of the {dboard.get('changed_activities', 0)} total changed (the other {dboard.get('duration_only', 0)} changed in duration only).</p>
      <div>{pills}</div>
      {_logic_table_html(report)}
      <h2>Duration &amp; remaining changes vs baseline</h2>
      {_duration_table_html(report)}
      {_impact_html(impact)}
    </body></html>'''


def _days(v):
    return f'{v} d' if v is not None else '—'


def _impact_dashboard(report, impact):
    bf = report.get('baseline_finish') or '—'
    uf = report.get('update_finish') or '—'
    if impact and impact.get('delay_after') is not None:
        return ('<div class="tiles">'
                + _tile('Reported delay', _days(impact.get('delay_after')))
                + _tile('But-for delay', _days(impact.get('delay_before')))
                + _tile('Manufactured', _days(impact.get('manufactured_days')))
                + _tile('Baseline finish', bf) + _tile('Update finish', uf) + '</div>')
    dash = report.get('dashboard', {}) or {}
    sub = f"{dash.get('logic_changed', 0)} logic/lag · {dash.get('duration_only', 0)} duration"
    return ('<div class="tiles">'
            + _tile('Changed activities', dash.get('changed_activities', 0), sub)
            + _tile('Baseline finish', bf) + _tile('Update finish', uf)
            + _tile('Data date', report.get('data_date') or '—') + '</div>')
