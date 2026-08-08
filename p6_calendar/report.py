"""Consultant-grade Calendar Audit report → HTML (Chrome headless makes the PDF).
Sections follow the spec order: Executive Dashboard, Timeline, Monthly Statistics,
Monthly Calendar View, Exceptions, Working Hours, Comparison, Usage, Conflicts,
[Weather — Slice B], Executive Conclusion. Tables use <thead> so headers repeat
across printed pages."""
import html as _html

_STATUS_COLOR = {'work': '#22c55e', 'weekend': '#cbd5e1', 'holiday': '#ef4444',
                 'shutdown': '#f59e0b', 'special': '#3b82f6'}
_DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
_MON = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _esc(v):
    return _html.escape('' if v is None else str(v))


def _fmt(iso):
    if not iso:
        return '—'
    s = str(iso)[:10]
    try:
        y, m, d = s.split('-')
        return f'{int(d):02d} {_MON[int(m)]} {y}'
    except (ValueError, IndexError):
        return s


def _tile(lab, val, sub=''):
    sub_html = f'<div class="n">{_esc(sub)}</div>' if sub else ''
    return f'<div class="kpi"><div class="k">{_esc(lab)}</div><div class="v">{_esc(val)}</div>{sub_html}</div>'


def _dashboard(d):
    dates = ''.join([
        _tile('Project Start', _fmt(d.get('project_start'))),
        _tile('Project Finish', _fmt(d.get('project_finish'))),
        _tile('Baseline Start', _fmt(d.get('baseline_start'))),
        _tile('Baseline Finish', _fmt(d.get('baseline_finish'))),
        _tile('Data Date', _fmt(d.get('data_date'))),
    ])
    stats = ''.join([
        _tile('Total Calendar Days', d.get('total_calendar_days')),
        _tile('Working Days', d.get('total_working_days')),
        _tile('Non-Working Days', d.get('total_nonworking_days')),
        _tile('Holidays', d.get('total_holidays')),
        _tile('Exceptions', d.get('total_exceptions')),
        _tile('Shutdown Periods', d.get('shutdown_periods')),
        _tile('Avg Working Days / Month', d.get('avg_working_days_per_month')),
        _tile('Avg Working Hours / Day', f"{d.get('avg_working_hours_per_day')} hrs"),
    ])
    return (f'<h2 class="sec">1 · Executive Dashboard</h2>'
            f'<div class="sub2">Key Dates</div><div class="kpis k5">{dates}</div>'
            f'<div class="sub2">Calendar Statistics</div><div class="kpis k4">{stats}</div>')


def _timeline(months):
    strips = []
    for m in months:
        cells = ''.join(
            f'<i style="background:{_STATUS_COLOR.get(day["status"], "#22c55e")}"></i>'
            for day in m.get('days', []))
        flag = ''
        if m.get('flag'):
            col = '#f59e0b' if m['flag'].startswith('Shutdown') else '#3b82f6'
            flag = f'<div class="tlflag" style="color:{col}">{_esc(m["flag"])}</div>'
        strips.append(f'<div class="tlm"><div class="tlh">{_esc(m["label"])}'
                      f'<span>{m["working_days"]}d</span></div>'
                      f'<div class="dg">{cells}</div>{flag}</div>')
    legend = ('<div class="legend">'
              + ''.join(f'<span><i style="background:{c}"></i>{_esc(n)}</span>'
                        for n, c in [('Working', '#22c55e'), ('Weekend', '#cbd5e1'),
                                     ('Holiday', '#ef4444'), ('Shutdown', '#f59e0b'),
                                     ('Special hours', '#3b82f6')])
              + '</div>')
    return (f'<h2 class="sec">2 · Calendar Timeline</h2>{legend}'
            f'<div class="timeline">{"".join(strips)}</div>')


def _monthly_stats(months):
    rows = ''.join(
        f'<tr><td>{_esc(m["label"])}</td><td class="num">{m["working_days"]}</td>'
        f'<td class="num">{m["holidays"]}</td><td class="num">{m["exceptions"]}</td>'
        f'<td class="num">{m["working_hours"]}</td></tr>' for m in months)
    return ('<h2 class="sec">3 · Monthly Calendar Statistics</h2>'
            '<table><thead><tr><th>Month</th><th class="num">Working Days</th>'
            '<th class="num">Holidays</th><th class="num">Exceptions</th>'
            f'<th class="num">Working Hours</th></tr></thead><tbody>{rows}</tbody></table>')


def _month_grids(months):
    blocks = []
    for m in months:
        head = ''.join(f'<div class="mh">{d}</div>' for d in _DOW)
        pad = ((m.get('first_weekday', 0) % 7) + 7) % 7
        cells = ''.join('<div class="mc blank"></div>' for _ in range(pad))
        for day in m.get('days', []):
            col = _STATUS_COLOR.get(day['status'], '#22c55e')
            faded = 'style="background:%s22;border-color:%s"' % (col, col) if day['status'] != 'work' else ''
            cells += f'<div class="mc" {faded}>{day["d"]}</div>'
        blocks.append(f'<div class="mgrid-wrap"><div class="mgrid-t">{_esc(m["label"])}</div>'
                      f'<div class="mgrid">{head}{cells}</div></div>')
    return ('<h2 class="sec">4 · Monthly Calendar View</h2>'
            f'<div class="mgrids">{"".join(blocks)}</div>')


def _exceptions(exc):
    def tbl(title, color, rows_html, headers):
        cells = []
        for label, is_num in headers:
            cls = ' class="num"' if is_num else ''
            cells.append(f'<th{cls}>{_esc(label)}</th>')
        h = ''.join(cells)
        return (f'<div class="grp"><span class="pill" style="background:{color}">{_esc(title)}</span></div>'
                f'<table><thead><tr>{h}</tr></thead><tbody>{rows_html or _empty(len(headers))}</tbody></table>')
    hol = ''.join(f'<tr><td>{_esc(x["description"])}</td><td class="num">{x["days"]}</td>'
                  f'<td>{_esc(x.get("reason") or "—")}</td></tr>' for x in exc.get('holidays', []))
    sp = ''.join(f'<tr><td>{_esc(x["description"])}</td><td class="num">{x["days"]}</td>'
                 f'<td>{_esc(x.get("hours") or "")}</td></tr>' for x in exc.get('special', []))
    sh = ''.join(f'<tr><td>{_esc(x["description"])}</td><td class="num">{x["days"]}</td>'
                 f'<td>{("[added] " if x.get("source") == "manual" else "") + (x.get("reason") or "—")}</td></tr>'
                 for x in exc.get('shutdowns', []))
    return ('<h2 class="sec">5 · Calendar Exceptions</h2>'
            + tbl('Holidays & Vacations', '#c0392b', hol,
                  [('Date', 0), ('Days', 1), ('Description', 0)])
            + tbl('Reduced / Special Working Hours', '#2563eb', sp,
                  [('Date', 0), ('Days', 1), ('Hours', 0)])
            + tbl('Shutdowns', '#e07b1a', sh,
                  [('Date', 0), ('Days', 1), ('Reason', 0)]))


def _empty(cols):
    return f'<tr><td colspan="{cols}" class="empty">None.</td></tr>'


def _hours(profiles):
    cards = ''.join(f'<div class="hp"><div class="t">{_esc(p["name"])}</div>'
                    f'<div class="h">{_esc(p["hours"])}</div>'
                    f'<div class="s">{_esc(p["hours_per_day"])} hrs · {_esc(p.get("sub", ""))}</div></div>'
                    for p in profiles)
    return f'<h2 class="sec">6 · Working Hours Profile</h2><div class="hours">{cards}</div>'


def _comparison(cmp):
    rows = ''.join(
        f'<tr><td>{_esc(c["name"])}{" (default)" if c.get("is_default") else ""}</td>'
        f'<td class="num">{c["hours_per_day"]}</td><td class="num">{c["days_per_week"]}</td>'
        f'<td class="num">{c["activities"]}</td><td class="num">{c["exceptions"]}</td></tr>' for c in cmp)
    return ('<h2 class="sec">7 · Calendar Comparison</h2>'
            '<table><thead><tr><th>Calendar</th><th class="num">Hours/Day</th>'
            '<th class="num">Days/Week</th><th class="num">Activities</th>'
            f'<th class="num">Exceptions</th></tr></thead><tbody>{rows}</tbody></table>')


def _usage(usage):
    rows = ''.join(
        f'<tr><td>{_esc(u["name"])}</td><td class="num">{u["activities"]}</td>'
        f'<td class="num">{"—" if u["role"] == "Unused" else str(u["pct"]) + "%"}</td>'
        f'<td>{_esc(u["role"])}</td></tr>' for u in usage)
    return ('<h2 class="sec">8 · Calendar Usage</h2>'
            '<table><thead><tr><th>Calendar</th><th class="num">Activities</th>'
            f'<th class="num">% of Activities</th><th>Role</th></tr></thead><tbody>{rows}</tbody></table>')


def _conflicts(conflicts):
    if not conflicts:
        return '<h2 class="sec">9 · Calendar Conflicts</h2><p class="ok">No calendar conflicts detected.</p>'
    items = ''.join(f'<div class="conf"><div class="ct">{_esc(c["title"])}</div>'
                    f'<div class="cd">{_esc(c["detail"])}</div></div>' for c in conflicts)
    return f'<h2 class="sec">9 · Calendar Conflicts</h2>{items}'


def _conclusion(bullets, weather_html=''):
    items = ''.join(f'<li>{_esc(b)}</li>' for b in bullets)
    return (f'{weather_html}'
            f'<h2 class="sec">{"11" if weather_html else "10"} · Executive Conclusion</h2>'
            f'<div class="concl"><ul>{items}</ul></div>')


def render_calendar_report(result, meta, weather_html=''):
    d = result.get('dashboard', {})
    primary = result.get('primary_calendar_id')
    bc = (result.get('by_calendar') or {}).get(primary, {})
    months = bc.get('monthly_stats', [])
    exc = bc.get('exceptions', {'holidays': [], 'special': [], 'shutdowns': []})
    profiles = bc.get('hours_profiles', [])
    cal_name = next((c['name'] for c in result.get('assigned_calendars', [])
                     if c['object_id'] == primary), '')
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Calendar Audit — {_esc(meta.get('project_name', ''))}</title>
<style>
  @page {{ margin: 18mm 12mm; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1f2a37; font-size: 11px; margin: 0; }}
  .head {{ border-bottom: 3px solid #17457a; padding-bottom: 12px; margin-bottom: 16px; }}
  .kicker {{ font-size: 10px; letter-spacing: 2px; color: #17457a; font-weight: 700; text-transform: uppercase; }}
  .title {{ font-size: 24px; font-weight: 800; color: #0f2440; margin: 3px 0 1px; }}
  .subtitle {{ font-size: 12px; color: #5b6472; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 3px 26px; margin-top: 10px; font-size: 11px; }}
  .meta span {{ color: #8a93a0; }}
  h2.sec {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #17457a;
            border-bottom: 1px solid #dbe1e8; padding-bottom: 4px; margin: 20px 0 10px; page-break-after: avoid; }}
  .sub2 {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: .5px; color: #8a93a0; font-weight: 700; margin: 8px 0 6px; }}
  .kpis {{ display: grid; gap: 8px; }}
  .kpis.k5 {{ grid-template-columns: repeat(5, 1fr); }}
  .kpis.k4 {{ grid-template-columns: repeat(4, 1fr); }}
  .kpi {{ border: 1px solid #e8ecf1; border-radius: 8px; padding: 9px 11px; }}
  .kpi .k {{ font-size: 9px; text-transform: uppercase; letter-spacing: .4px; color: #8a93a0; font-weight: 700; }}
  .kpi .v {{ font-size: 17px; font-weight: 800; margin-top: 2px; color: #0f2440; }}
  .kpi .n {{ font-size: 9px; color: #8a93a0; margin-top: 1px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10px; margin-top: 2px; }}
  thead {{ display: table-header-group; }}
  th {{ background: #26517d; color: #fff; text-align: left; padding: 6px 8px; font-weight: 600; font-size: 9.5px; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #eef1f5; vertical-align: top; }}
  tbody tr:nth-child(even) {{ background: #f7f9fb; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .empty {{ color: #6b7480; font-style: italic; }}
  .legend {{ display: flex; gap: 14px; flex-wrap: wrap; margin: 4px 0 10px; font-size: 9.5px; color: #5b6472; }}
  .legend span {{ display: inline-flex; align-items: center; gap: 4px; }}
  .legend i {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
  .timeline {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .tlm {{ width: 118px; border: 1px solid #e8ecf1; border-radius: 8px; padding: 8px; }}
  .tlh {{ font-size: 10px; font-weight: 700; display: flex; justify-content: space-between; margin-bottom: 6px; }}
  .tlh span {{ color: #8a93a0; font-weight: 600; }}
  .dg {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }}
  .dg i {{ aspect-ratio: 1; border-radius: 2px; display: block; }}
  .tlflag {{ margin-top: 6px; font-size: 8.5px; font-weight: 700; text-align: center; }}
  .grp {{ margin: 12px 0 6px; }}
  .pill {{ display: inline-block; padding: 2px 9px; border-radius: 20px; color: #fff; font-weight: 700; font-size: 9px; }}
  .hours {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
  .hp {{ border: 1px solid #e8ecf1; border-radius: 8px; padding: 11px; }}
  .hp .t {{ font-weight: 700; }}
  .hp .h {{ font-size: 17px; font-weight: 800; color: #17457a; margin-top: 2px; }}
  .hp .s {{ font-size: 9px; color: #8a93a0; margin-top: 3px; }}
  .mgrids {{ display: flex; flex-wrap: wrap; gap: 12px; }}
  .mgrid-wrap {{ width: 230px; }}
  .mgrid-t {{ font-size: 10px; font-weight: 700; margin-bottom: 4px; }}
  .mgrid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }}
  .mh {{ font-size: 8px; font-weight: 700; color: #8a93a0; text-align: center; }}
  .mc {{ aspect-ratio: 1.2; border: 1px solid #e8ecf1; border-radius: 4px; font-size: 8.5px; padding: 2px 3px; }}
  .mc.blank {{ border: none; }}
  .conf {{ border: 1px solid #e8ecf1; border-left: 3px solid #e07b1a; border-radius: 0 6px 6px 0;
           padding: 8px 11px; margin-bottom: 6px; }}
  .conf .ct {{ font-weight: 700; font-size: 11px; }}
  .conf .cd {{ font-size: 10px; color: #5b6472; margin-top: 2px; }}
  .ok {{ color: #2e8b57; font-size: 11px; }}
  .concl {{ border-left: 4px solid #17457a; background: #f4f8fd; border-radius: 0 8px 8px 0; padding: 10px 15px; }}
  .concl ul {{ margin: 0; padding-left: 18px; }}
  .concl li {{ font-size: 11px; line-height: 1.5; margin-bottom: 5px; }}
  .foot {{ border-top: 1px solid #dbe1e8; margin-top: 20px; padding-top: 8px; font-size: 9px; color: #8a93a0; line-height: 1.5; }}
</style></head>
<body>
  <div class="head">
    <div class="kicker">Project Calendar Report</div>
    <div class="title">Calendar Audit</div>
    <div class="subtitle">Project working calendar, holidays, shutdowns &amp; working-hour analysis</div>
    <div class="meta">
      <div><span>Project:</span> {_esc(meta.get('project_name', ''))}</div>
      <div><span>Data Date:</span> {_esc(_fmt(meta.get('data_date', '')))}</div>
      <div><span>Report Date:</span> {_esc(meta.get('report_date', ''))}</div>
      <div><span>Schedule File:</span> {_esc(meta.get('source_file', ''))}</div>
      <div><span>Calendar:</span> {_esc(cal_name)}</div>
    </div>
  </div>
  {_dashboard(d)}
  {_timeline(months)}
  {_monthly_stats(months)}
  {_month_grids(months)}
  {_exceptions(exc)}
  {_hours(profiles)}
  {_comparison(result.get('comparison', []))}
  {_usage(result.get('usage', []))}
  {_conflicts(result.get('conflicts', []))}
  {_conclusion(result.get('conclusion', []), weather_html)}
  <div class="foot">
    Calendar Audit for <b>{_esc(meta.get('project_name', ''))}</b> · calendar "{_esc(cal_name)}".
    Working days, holidays, exceptions and working hours are read directly from the P6 calendar.
  </div>
</body></html>'''
