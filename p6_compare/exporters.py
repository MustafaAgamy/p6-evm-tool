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
    'Activity ID', 'Activity name', 'Change',
    'Baseline pred ID', 'Baseline pred rel', 'Baseline pred name',
    'Baseline succ ID', 'Baseline succ rel', 'Baseline succ name',
    'Update pred ID', 'Update pred rel', 'Update pred name',
    'Update succ ID', 'Update succ rel', 'Update succ name',
]


def logic_excel(report):
    """(headers, rows) for the driving logic change table; multi-driving links joined."""
    rows = []
    for r in (report.get('logic', {}) or {}).get('rows', []):
        rows.append([
            r.get('activity_id', ''), r.get('activity_name', ''), r.get('change_label', ''),
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


def _tile(label, value):
    return f'<div class="tile"><div class="tl">{_e(label)}</div><div class="tv">{_e(value)}</div></div>'


def _logic_table_html(report):
    rows = (report.get('logic', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No driving relationship or lag changes vs the baseline.</p>'
    body = []
    for r in rows:
        body.append(
            '<tr>'
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
        '<th rowspan="2">Activity ID</th><th rowspan="2">Activity name</th><th rowspan="2">Change</th>'
        '<th colspan="6" class="grp">Baseline — driving links</th>'
        '<th colspan="6" class="grpu">Update — driving links</th></tr>'
        '<tr><th>Pred ID</th><th>Pred rel</th><th>Pred name</th><th>Succ ID</th><th>Succ rel</th><th>Succ name</th>'
        '<th>Pred ID</th><th>Pred rel</th><th>Pred name</th><th>Succ ID</th><th>Succ rel</th><th>Succ name</th></tr>'
        '</thead><tbody>' + ''.join(body) + '</tbody></table>')


def _duration_table_html(report):
    rows = (report.get('durations', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No duration or remaining changes vs the baseline.</p>'
    body = ''.join(
        '<tr>'
        f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
        f'<td class="num">{_e(r.get("baseline_orig_days"))} d</td>'
        f'<td class="num">{_e(r.get("update_orig_days"))} d</td>'
        f'<td class="num">{_e(r.get("remaining_days"))} d</td>'
        f'<td class="num">{_e(r.get("remaining_minus_baseline_days"))} d</td>'
        f'<td>{_e(r.get("status"))}</td>'
        f'<td>{_e(_impact_word(r.get("impact")))}</td></tr>'
        for r in rows)
    return ('<table class="data"><thead><tr><th>Activity ID</th><th>Activity name</th>'
            '<th>Baseline orig.</th><th>Update orig.</th><th>Remaining</th><th>Rem − baseline</th>'
            '<th>Status</th><th>Impact on finish</th></tr></thead><tbody>' + body + '</tbody></table>')


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


def render_html(report, impact=None):
    cs = report.get('change_summary', {}) or {}
    pills = ''.join(f'<span class="pill">{it.get("count")} {_e(it.get("label"))}</span>'
                    for it in cs.get('items', [])) or '<span class="note">No changes vs the baseline.</span>'
    dash = _impact_dashboard(report, impact)
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
    </style></head><body>
      <h1>Consultant Review — Baseline vs Current Update</h1>
      <div class="sub">{_e(report.get('project_name'))} · data date {_e(report.get('data_date'))} · baseline {_e(report.get('baseline_file'))} vs {_e(report.get('update_file'))}</div>
      {dash}
      <h2>Driving logic &amp; lag changes vs baseline</h2>
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
    return ('<div class="tiles">'
            + _tile('Changed activities', dash.get('changed_activities', 0))
            + _tile('Baseline finish', bf) + _tile('Update finish', uf)
            + _tile('Data date', report.get('data_date') or '—') + '</div>')
