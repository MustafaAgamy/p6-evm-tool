"""Update-vs-Update exporters — PDF (HTML -> Chrome) and Excel.

`render_html` lays out a landscape consultant page from the period report (+ optional
milestone trend). `progress_excel` flattens the Progress-by-activity table into
(headers, rows) for the single-sheet xlsx writer. Nothing here computes a number.
"""
import html
from datetime import datetime

_BLUE = '#2a78d6'
_AMBER = '#d97706'
_PALETTE = ['#e24b4a', '#16a34a', '#2a78d6', '#d97706', '#7c3aed', '#db2777', '#0891b2', '#ea580c']


def _e(v):
    return html.escape(str(v if v is not None else ''))


def _tile(label, value, sub=''):
    s = f'<div class="ts">{_e(sub)}</div>' if sub else ''
    return f'<div class="tile"><div class="tl">{_e(label)}</div><div class="tv">{_e(value)}</div>{s}</div>'


def _signpct(v):
    if v is None:
        return '—'
    return f'+{v:.1f}%' if v > 0 else f'{v:.1f}%'


# ── Excel: the progress-by-activity table ───────────────────────────────────

_PROGRESS_HEADERS = ['Activity ID', 'Activity name', 'Previous %', 'Current %', 'Variance', 'Note']


def progress_excel(report):
    """(headers, rows) for the Progress-by-activity % variance table."""
    rows = []
    for r in (report.get('progress', {}) or {}).get('rows', []):
        note = 'finished' if r.get('finished') else ('started' if r.get('started')
               else ('progress reversed' if r.get('reversal') else ''))
        rows.append([r.get('activity_id', ''), r.get('activity_name', ''),
                     r.get('prev_pct', 0), r.get('curr_pct', 0), r.get('variance', 0), note])
    return _PROGRESS_HEADERS, rows


# ── PDF: HTML → Chrome ──────────────────────────────────────────────────────

def _dashboard_html(report):
    s = report.get('summary', {}) or {}
    ach = s.get('forecast_achievement')
    ach_txt = f'{round(ach * 100)}%' if ach is not None else '—'
    slip = s.get('finish_slip_days')
    slip_txt = '—' if slip is None else (f'slipped {slip} d' if slip > 0 else (f'pulled in {-slip} d' if slip < 0 else 'no change'))
    dch = s.get('delay_change')
    dch_txt = '' if dch is None else (f'{"+"if dch>0 else ""}{dch} wd this period')
    return ('<div class="tiles">'
            + _tile('Overall complete', f"{s.get('actual_prev')}% → {s.get('actual_now')}%", f"{_signpct(s.get('period_earned'))} earned")
            + _tile('Vs last forecast', f"{s.get('actual_now')}% / {s.get('forecast_at_now')}%", f"achievement {ach_txt}")
            + _tile('Forecast finish', s.get('forecast_finish_now') or '—', slip_txt)
            + _tile('Delay vs baseline', '—' if s.get('delay_now') is None else f"{s.get('delay_now')} wd", dch_txt)
            + '</div>')


def _progress_table_html(report):
    rows = (report.get('progress', {}) or {}).get('rows', [])
    if not rows:
        return '<p class="note">No activity changed its % complete between the two updates.</p>'
    body = ''.join(
        '<tr>'
        f'<td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
        f'<td class="num">{_e(r.get("prev_pct"))}%</td><td class="num">{_e(r.get("curr_pct"))}%</td>'
        f'<td class="num {"neg" if r.get("reversal") else "pos"}">{_signpct(r.get("variance"))}</td>'
        f'<td>{"finished" if r.get("finished") else ("started" if r.get("started") else ("reversed" if r.get("reversal") else ""))}</td>'
        '</tr>' for r in rows)
    return ('<table class="data"><thead><tr><th>Activity ID</th><th>Activity name</th>'
            '<th>Prev %</th><th>Current %</th><th>Variance</th><th>Note</th></tr></thead><tbody>'
            + body + '</tbody></table>')


def _critical_table_html(report):
    cm = report.get('critical_movement', {}) or {}
    rows = cm.get('rows', [])
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
            '<th>Finish (prev)</th><th>Finish (now)</th><th>Slip</th><th>Float</th>'
            '<th>Driver</th><th>Critical</th></tr></thead><tbody>' + body + '</tbody></table>')


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
    x0, x1, y0, y1, n = 60, 900, 250, 24, len(periods)
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
        lbl = datetime.fromordinal(int(t)).strftime('%b-%y')
        yticks += (f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#eee"/>'
                   f'<text x="{x0 - 6}" y="{y + 3:.1f}" text-anchor="end" font-size="10" fill="#666">{lbl}</text>')
    legend = ''.join(f'<span><i style="background:{_PALETTE[si % len(_PALETTE)]}"></i>{_e(s.get("name"))}</span>'
                     for si, s in enumerate(series))
    return (f'<div class="legend">{legend}</div>'
            f'<svg viewBox="0 0 940 275" width="100%">{yticks}'
            f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#ccc"/>'
            f'<line x1="{x0}" y1="{y1}" x2="{x0}" y2="{y0}" stroke="#ccc"/>'
            f'{"".join(lines)}</svg>')


def render_html(report, trend=None):
    s = report.get('summary', {}) or {}
    trend_svg = _trend_svg(trend)
    trend_block = (f'<h2>Milestone finish trend — every update so far</h2>{trend_svg}'
                   f'<p class="note">Rising line = that milestone\'s finish keeps slipping later.</p>') if trend_svg else ''
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 12mm; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: system-ui, -apple-system, Arial, sans-serif; color: #1e293b; font-size: 12px; margin: 0; }}
      h1 {{ font-size: 20px; margin: 0 0 2px; }}
      h2 {{ font-size: 14px; margin: 18px 0 8px; border-bottom: 2px solid #1e2d40; padding-bottom: 4px; }}
      .sub {{ color: #64748b; font-size: 12px; margin-bottom: 10px; }}
      .tiles {{ display: flex; gap: 10px; margin: 8px 0; flex-wrap: wrap; }}
      .tile {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 14px; min-width: 165px; }}
      .tl {{ font-size: 10px; text-transform: uppercase; letter-spacing: .5px; color: #64748b; font-weight: 700; }}
      .tv {{ font-size: 19px; font-weight: 800; margin-top: 2px; }}
      .ts {{ font-size: 11px; color: #64748b; margin-top: 2px; }}
      .pills {{ margin: 4px 0; }}
      .pill {{ display: inline-block; background: #eef2ff; color: #1e3a8a; border-radius: 12px; padding: 2px 10px; font-size: 11px; margin: 0 6px 6px 0; }}
      table.data {{ width: 100%; border-collapse: collapse; font-size: 10.5px; margin: 6px 0; }}
      table.data th {{ background: #26517d; color: #fff; text-align: left; padding: 5px 6px; font-weight: 600; }}
      table.data td {{ border-bottom: 1px solid #e2e8f0; padding: 4px 6px; vertical-align: top; }}
      .mono {{ font-family: Consolas, monospace; }} .num {{ text-align: right; }}
      .pos {{ color: #15803d; font-weight: 700; }} .neg {{ color: #b91c1c; font-weight: 700; }}
      .note {{ color: #64748b; font-style: italic; }}
      .legend {{ font-size: 11px; color: #64748b; margin: 4px 0; }}
      .legend span {{ margin-right: 16px; }} .legend i {{ display: inline-block; width: 16px; height: 3px; vertical-align: middle; margin-right: 5px; }}
      .reco {{ border: 1px solid #e2e8f0; border-left: 4px solid #16a34a; border-radius: 0 8px 8px 0; padding: 10px 14px; line-height: 1.6; }}
    </style></head><body>
      <h1>Update vs Update — Windows Analysis</h1>
      <div class="sub">{_e(report.get('project_name'))} · previous {_e(report.get('prev_file'))} ({_e(report.get('data_date_prev'))}) → current {_e(report.get('update_file'))} ({_e(report.get('data_date_now'))})</div>
      <h2>Executive dashboard — progress this period</h2>
      {_dashboard_html(report)}
      <h2>Progress by activity — % complete this period</h2>
      {_progress_table_html(report)}
      <h2>Critical-path movement in this window</h2>
      {_critical_table_html(report)}
      <h2>What moved this period</h2>
      {_buckets_html(report)}
      {trend_block}
      <h2>Executive conclusion</h2>
      <div class="reco">{_e(report.get('conclusion'))}</div>
    </body></html>'''
