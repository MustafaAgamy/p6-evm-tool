"""Consultant-grade Calendar Audit report → HTML (Chrome headless makes the PDF).
Sections follow the spec order: Executive Dashboard, Timeline, Monthly Statistics,
Monthly Calendar View, Exceptions, Working Hours, Comparison, Usage, Conflicts,
[Weather — Slice B], Executive Conclusion. Tables use <thead> so headers repeat
across printed pages."""
import html as _html

import json

import report_theme
from utils import date_text as _date_text

# Day-status swatch colours — 'work' reads as good, 'weekend' as a neutral non-working
# grey, 'holiday'/'shutdown' as bad (a full day lost), 'special' (modified hours) as accent.
_STATUS_COLOR = {'work': report_theme.var('rpt-good'), 'weekend': report_theme.var('rpt-hair-strong'),
                 'holiday': report_theme.var('rpt-bad'), 'shutdown': report_theme.var('rpt-bad'),
                 'special': report_theme.var('rpt-accent')}
_DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
_MON = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _esc(v):
    v = _date_text(v)                     # an ISO date shows as 03-Dec.2026 (comment 46)
    return _html.escape('' if v is None else str(v))


def _fmt(iso):
    if not iso:
        return '—'
    s = str(iso)[:10]
    try:
        y, m, d = s.split('-')
        return f'{int(d):02d}-{_MON[int(m)]}.{y}'          # 03-Dec.2026 (comment 46)
    except (ValueError, IndexError):
        return s


def _part(key, label, html, export=None, headers=None, rows=None):
    """One selectable report PART (Report Contents picker, 2nd level) — see
    docs/report-picker-adoption.md. ``data-export="image"`` marks a CSS chart Word gets as a
    picture; ``data-chart-*`` carry the numbers behind it (Excel)."""
    if not html:
        return ''
    attrs = f' data-part="{key}" data-part-label="{_esc(label)}"'
    if export:
        attrs += f' data-export="{export}"'
    if headers is not None and rows is not None:
        attrs += (f" data-chart-headers='{_esc(json.dumps(headers))}'"
                  f" data-chart-data='{_esc(json.dumps(rows))}'")
    return f'<div{attrs}>{html}</div>'


def _tile(lab, val, sub=''):
    sub_html = f'<div class="n">{_esc(sub)}</div>' if sub else ''
    return f'<div class="kpi"><div class="k">{_esc(lab)}</div><div class="v">{_esc(val)}</div>{sub_html}</div>'


def _baseline_line(d):
    """The one 'Baseline: …' line under the Key Dates when the update's own Planned dates stand
    in for its baseline (the screen shows the same line) — '' otherwise."""
    if not (d or {}).get('baseline_approx'):
        return ''
    lbl = d.get('baseline_label') or ("not in the file and none attached — the update's own "
                                      "Planned dates stand in (approximate)")
    return f'<p class="lg">Baseline: {_esc(lbl)}</p>'


def _dashboard(d, weather=None):
    # Feature 1 (Calendar Audit) carries NO weather. Key Dates: Baseline Start + Finish, then
    # the two dates every statistic below runs between — the Data Date and the Project
    # Completion of the imported file (comments 74 / 75).
    date_tiles = [
        _tile('Baseline Start', _fmt(d.get('baseline_start')), 'approx' if d.get('baseline_approx') else ''),
        _tile('Baseline Finish', _fmt(d.get('baseline_finish')),
              'Baseline (approx)' if d.get('baseline_approx') else 'plan of record'),
        _tile('Data Date', _fmt(d.get('data_date')), 'statistics start here'),
        _tile('Project Completion', _fmt(d.get('window_finish') or d.get('project_finish')),
              'finish of the imported file — statistics end here'),
    ]
    if weather:
        date_tiles.append(_tile('Weather-Adjusted Finish',
                                _fmt(weather['weather_adjusted_finish']),
                                f"+{weather['net_finish_delay']} wd from weather"))
    dates = ''.join(date_tiles)
    dates_grid = 'k5' if weather else 'k4'
    rest, hol = d.get('total_rest_days'), d.get('total_holidays')
    stats = ''.join([
        _tile('Total Calendar Days', d.get('total_calendar_days'), 'Data Date → Project Completion'),
        _tile('Working Days', d.get('total_working_days')),
        _tile('Non-Working Days', d.get('total_nonworking_days'),
              f'{rest} weekly rest days + {hol} holidays' if rest is not None else ''),
        _tile('Holidays', hol),
        _tile('Avg Working Days / Month', d.get('avg_working_days_per_month')),
        _tile('Avg Working Hours / Day', f"{d.get('avg_working_hours_per_day')} hrs"),
        _tile('Normal Hours', d.get('normal_hours') or '—'),
    ])
    return (f'<h2 class="sec">1 · Execution Dashboard</h2>'
            + _part('dashboard.dates', 'Key dates',
                    f'<div class="sub2">Key Dates</div><div class="kpis {dates_grid}">{dates}</div>'
                    + _baseline_line(d))
            + _part('dashboard.stats', 'Calendar statistics',
                    f'<div class="sub2">Calendar Statistics</div><div class="kpis k4">{stats}</div>'))


def _working_hist(months, name='', idx=0):
    """§2 working vs non-working days-per-month histogram of ONE calendar. The number above
    each bar is the NET working days that month, the number under the month its non-working
    days (matches the screen). `idx` > 0 = a further selected calendar (comment 77)."""
    if not months:
        return ''
    mx = max((m['working_days'] + m.get('nonworking_days', 0) for m in months), default=0) or 1
    cols = ''
    for m in months:
        wd = m['working_days']
        nw = m.get('nonworking_days', 0)
        tot = wd + nw
        totpx = round(tot / mx * 92)
        nwpx = round(nw / tot * totpx) if tot else 0
        wpx = max(0, totpx - nwpx)
        cols += (f'<div class="whc"><div class="wht">{wd}</div>'
                 f'<div class="whcol"><div class="whn" style="height:{nwpx}px"></div>'
                 f'<div class="whw" style="height:{wpx}px"></div></div>'
                 f'<div class="whl">{_esc(m["label"])}<br>{nw} off</div></div>')
    total_hours = round(sum(m.get('working_hours', 0) for m in months))
    t_wd = sum(m['working_days'] for m in months)
    t_nw = sum(m.get('nonworking_days', 0) for m in months)
    tot_line = (f'<div class="whtot">{("<b>" + _esc(name) + "</b> — ") if name else ""}'
                f'Working days: <b>{t_wd:,}</b> · Non-working days: <b>{t_nw:,}</b> · '
                f'Total working hours: <b>{total_hours:,} hrs</b></div>')
    legend = (f'<div class="whleg"><span><i style="background:{report_theme.var("rpt-good")}"></i>Working days</span>'
              f'<span><i style="background:{report_theme.var("rpt-hair-strong")}"></i>Non-working (weekends + holidays)</span>'
              f'<span>▲ number above bar = <b>net working days</b> · number under the month = <b>non-working days</b></span></div>')
    key = 'timeline.histogram' if not idx else f'timeline.histogram.{idx}'
    label = 'Working vs non-working days per month — chart' + (f' — {name}' if idx and name else '')
    # heading-with-content: the totals line, the legend and the bars never split across pages
    return _part(key, label,
                 '<div class="keep">' + tot_line + (legend if not idx else '')
                 + f'<div class="whist">{cols}</div></div>', export='image',
                 headers=['Month', 'Net working days', 'Non-working days', 'Working hours'],
                 rows=[[m['label'], m['working_days'], m.get('nonworking_days', 0),
                        round(m.get('working_hours', 0), 1)] for m in months])


def _month_grids(months, hidden_months=0, tl_from=None, name='', others=()):
    """§2 — the main calendar's histogram + month grids, then one histogram for each further
    selected calendar (`others` = [(name, months)], comment 77)."""
    blocks = []
    for m in months:
        head = ''.join(f'<div class="mh">{d}</div>' for d in _DOW)
        pad = ((m.get('first_weekday', 0) % 7) + 7) % 7
        cells = ''.join('<div class="mc blank"></div>' for _ in range(pad))
        for day in m.get('days', []):
            col = _STATUS_COLOR.get(day['status'], report_theme.var('rpt-good'))
            # var() can't take a hex alpha suffix like the old "%s22" trick, so blend via
            # color-mix() instead — same ~13% tint effect, still colour-only.
            faded = ('style="background:color-mix(in srgb, %s 13%%, transparent);border-color:%s"'
                     % (col, col)) if day['status'] != 'work' else ''
            nm = day.get('name')
            nm_html = f'<div class="cn">{_esc(nm)}</div>' if nm else ''
            cells += f'<div class="mc" {faded}><span class="dn">{day["d"]}</span>{nm_html}</div>'
        blocks.append(f'<div class="mgrid-wrap"><div class="mgrid-t">{_esc(m["label"])}</div>'
                      f'<div class="mgrid">{head}{cells}</div></div>')
    legend = ('<div class="legend">'
              + ''.join(f'<span><i style="background:{c}"></i>{_esc(n)}</span>'
                        for n, c in [('Working', _STATUS_COLOR['work']), ('Weekend', _STATUS_COLOR['weekend']),
                                     ('Holiday', _STATUS_COLOR['holiday']),
                                     ('Special hours', _STATUS_COLOR['special'])])
              + '</div>')
    if hidden_months:
        sub = (f'— working vs non-working days per month, from the data date ({_fmt(tl_from)}) · '
               f'{hidden_months} earlier month{"s" if hidden_months != 1 else ""} hidden')
    else:
        sub = '— working vs non-working days per month'
    def _month_row(m):
        cnt = {}
        for day in m.get('days', []):
            cnt[day['status']] = cnt.get(day['status'], 0) + 1
        names = sorted({day['name'] for day in m.get('days', []) if day.get('name')})
        # a P6 calendar has no 'shutdown': every non-working exception day is a holiday
        return [m['label'], cnt.get('work', 0), cnt.get('weekend', 0),
                cnt.get('holiday', 0) + cnt.get('shutdown', 0), cnt.get('special', 0), '; '.join(names)]
    grids = _part('timeline.months', 'Month-by-month calendars',
                  '<div class="sub2">Each month’s calendar — holiday names shown in the day cells</div>'
                  + legend + f'<div class="mgrids">{"".join(blocks)}</div>', export='image',
                  headers=['Month', 'Working', 'Weekend', 'Holiday', 'Special hours',
                           'Holiday names'],
                  rows=[_month_row(m) for m in months])
    return ('<h2 class="sec">2 · Calendar Timeline &amp; Statistics '
            f'<span style="font-weight:400;font-size:9.5px;color:{report_theme.var("rpt-muted")};text-transform:none;letter-spacing:0">'
            f'{_esc(sub)}</span></h2>'
            + _working_hist(months, name)
            + ''.join(_working_hist(m2, n2, i) for i, (n2, m2) in enumerate(others, 1))
            + grids)


def month_split_rows(months):
    """§3.1 rows — one per month + a Total row: [Month, Calendar days, Working days, Weekly
    rest days, Holidays, Total non-working]. The same numbers the histogram draws (comment 76);
    shared with the Excel export."""
    rows = []
    for m in months or []:
        wd, nw = m.get('working_days', 0), m.get('nonworking_days', 0)
        off = m.get('off_days', m.get('holidays', 0))
        rows.append([m.get('label', ''), m.get('calendar_days', wd + nw), wd,
                     m.get('rest_days', nw - off), off, nw])
    if rows:
        rows.append(['Total'] + [sum(r[i] for r in rows) for i in range(1, 6)])
    return rows


def _exceptions(exc, months=None, rest_weekdays=None):
    """§3 Calendar Non-working days — 3.1 the non-working days month by month (the histogram's
    own numbers: weekly rest days + holidays) and 3.2 every holiday DATE of the period
    (Date | Day | Description) — every non-working date of the P6 calendar is a holiday,
    a long run included (comment 76)."""
    hd = exc.get('holiday_dates', [])
    split = month_split_rows(months)
    if not hd and not split:
        return ''
    muted = report_theme.var('rpt-muted')
    rest_lab = 'Weekly rest days' + (f' ({", ".join(n[:3] for n in rest_weekdays)})' if rest_weekdays else '')
    t31 = ''
    if split:
        body = ''.join(
            '<tr%s><td>%s</td>%s</tr>' % (
                ' style="font-weight:700"' if r[0] == 'Total' else '', _esc(r[0]),
                ''.join(f'<td class="num">{v}</td>' for v in r[1:])) for r in split)
        t31 = _part('exceptions.months', 'Non-working days per month table', (
            '<div class="keep"><div class="sub2">3.1 · Non-working days per month</div>'
            '<table><thead><tr><th>Month</th><th class="num">Calendar days</th>'
            f'<th class="num">Working days</th><th class="num">{_esc(rest_lab)}</th>'
            '<th class="num">Holidays</th><th class="num">Total non-working</th></tr></thead>'
            f'<tbody>{body}</tbody></table>'
            '<p class="lg">Calendar days = Working days + Weekly rest days + Holidays. '
            'Total non-working is the figure drawn in the histogram of section 2.</p></div>'))
    t32 = ''
    if hd:
        rows = ''.join(
            f'<tr><td>{_fmt(x["date"])}</td><td>{_esc(x.get("weekday", ""))}</td>'
            f'<td>{_esc(x.get("reason") or "—")}</td></tr>' for x in hd)
        t32 = _part('exceptions.holidays', 'Holidays table', (
            '<div class="sub2">3.2 · Holiday dates</div>'
            '<table><thead><tr><th>Date</th><th>Day</th><th>Description</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
            f'<p class="lg">Total holidays: <b>{len(hd)}</b> — each non-working date of the P6 calendar '
            'and its weekday (the weekly rest days are not listed one by one). '
            'The Description is the planner-typed holiday name, saved with the project.</p>'))
    return (('<h2 class="sec">3 · Calendar Non-working days '
            f'<span style="font-weight:400;font-size:9.5px;color:{muted};'
            'text-transform:none;letter-spacing:0">Data Date → Project Completion</span></h2>')
            + t31 + t32)


def _empty(cols):
    return f'<tr><td colspan="{cols}" class="empty">None.</td></tr>'


def _acts_cell(d):
    """The construction activities a bad-weather day hits (#07)."""
    names = d.get('activities') or []
    extra = d.get('activities_count', len(names)) - len(names)
    muted = report_theme.var('rpt-muted')
    if names:
        return (_esc(', '.join(names))
                + (f' <span style="color:{muted}">(+{extra} more)</span>' if extra > 0 else ''))
    if str(d.get('effect', '')).startswith('Non-working'):
        return f'<span style="color:{muted}">No construction activity scheduled</span>'
    return f'<span style="color:{muted}">{_esc(d.get("effect", ""))}</span>'


def _hours(profiles):
    """§4 Working-hours Profile as a TABLE: Period | Hours | Days/week | Hrs/day | Note.
    One row per distinct working-time profile; the planner's Note prints when set."""
    rows = ''.join(
        f'<tr><td>{_esc(p["name"])}</td><td>{_esc(p["hours"])}</td>'
        f'<td class="num">{_esc(p.get("days_per_week", ""))}</td>'
        f'<td class="num">{_esc(p["hours_per_day"])}</td>'
        f'<td>{_esc((p.get("note") or "").strip() or "—")}</td></tr>' for p in profiles)
    return ('<h2 class="sec">4 · Working-hours Profile</h2>'
            + _part('hours.profile', 'Working-hours profile table', (
                '<p class="lg">Each distinct working-time period in the calendar (P6 calendars can change '
                'hours over time). The <b>Note</b> is the planner\'s justification for a reduced-hours '
                'period, saved with the project.</p>'
                '<table><thead><tr><th>Period</th><th>Hours</th><th class="num">Days / week</th>'
                '<th class="num">Hrs / day</th><th>Note</th></tr></thead>'
                f'<tbody>{rows}</tbody></table>')))


def _comparison(cmp, usage=None, period_note='', conflicts=None):
    # Merged Calendar Comparison & Usage (matches the screen): hours/day, days/week, activities
    # assigned, % of activities and non-working days ahead — one row per calendar (the Role
    # column was removed, comment 79). The
    # "Calendar Conflicts — to be removed" list is appended inside this section (§5).
    umap = {u['name']: u for u in (usage or [])}
    rows = ''
    for c in cmp:
        u = umap.get(c['name'], {})
        acts = u.get('activities', 0)
        pct = '—' if u.get('role') == 'Unused' or u.get('pct') is None else f'{u["pct"]}%'
        rows += (f'<tr><td>{_esc(c["name"])}{" (default)" if c.get("is_default") else ""}</td>'
                 f'<td class="num">{c["hours_per_day"]}</td><td class="num">{c["days_per_week"]}</td>'
                 f'<td class="num">{acts}</td><td class="num">{pct}</td>'
                 f'<td class="num">{c.get("nonworking_days", 0)}</td></tr>')
    note = (f'<p class="lg"><b>% of Activities</b> — share of the schedule\'s activities on each '
            f'calendar. <b>Non-Working Days</b> — weekends and holidays still ahead, '
            f'{_esc(period_note)}. A calendar with 0 activities is unused and can be removed.</p>'
            ) if period_note else ''
    conf = ''
    if conflicts:
        def _pill(t):
            if t == 'unused':
                return f'<span class="pill" style="background:{report_theme.var("rpt-bad")}">Unused</span>'
            return f'<span class="pill" style="background:{report_theme.var("rpt-warn")}">Review</span>'
        lines = ''.join(
            f'<li>{_pill(c.get("type"))} <b>{_esc(c["title"])}</b> — {_esc(c["detail"])}</li>'
            for c in conflicts)
        conf = ('<div class="grp"><span class="pill" style="background:'
                f'{report_theme.var("rpt-bad")}">Calendar Conflicts — to be removed</span></div>'
                f'<ul class="conflist">{lines}</ul>')
    return ('<h2 class="sec">5 · Calendar Comparison &amp; Usage</h2>'
            + _part('comparison.table', 'Calendar comparison & usage table', (
                '<table><thead><tr><th>Calendar</th><th class="num">Hours/Day</th>'
                '<th class="num">Days/Week</th><th class="num">Assigned to</th>'
                '<th class="num">% of Activities</th><th class="num">Non-Working Days</th>'
                f'</tr></thead><tbody>{rows}</tbody></table>{note}'))
            + _part('comparison.conflicts', 'Calendar conflicts — to be removed', conf))


def _days_between(a, b):
    """Calendar days b − a from two ISO date strings; 0 if either missing/unparseable."""
    from datetime import date
    try:
        ya, ma, da = str(a)[:10].split('-')
        yb, mb, db = str(b)[:10].split('-')
        return (date(int(yb), int(mb), int(db)) - date(int(ya), int(ma), int(da))).days
    except (ValueError, AttributeError):
        return 0


def _weather_waterfall(d, w):
    """§1 Execution Dashboard — a 3-tile waterfall matching the screen: Baseline Finish →
    Forecast Completion → Bad-weather Completion, with the schedule's own slip and, separately,
    what weather adds, shown on the arrows. Print-safe (flex + colour-only)."""
    d = d or {}
    slip = _days_between(d.get('baseline_finish'), d.get('project_finish'))   # schedule's own slip
    wx_add = w.get('net_finish_delay', 0) or 0                                # weather adds (working days)
    slip_cls = 'pos' if slip > 0 else 'zero'
    wx_cls = 'pos' if wx_add > 0 else 'zero'
    return (
        '<h2 class="sec">1 · Execution Dashboard '
        f'<span style="font-weight:400;font-size:9.5px;color:{report_theme.var("rpt-warn")};text-transform:none;letter-spacing:0">'
        '— estimate, not a P6 figure</span></h2>'
        '<div class="wf">'
        f'<div class="wf-step bl"><div class="k">Baseline Finish{" · approx" if d.get("baseline_approx") else ""}</div><div class="v">{_fmt(d.get("baseline_finish"))}</div></div>'
        f'<div class="wf-arr"><div class="l">Schedule slip</div><div class="var {slip_cls}">{"+" if slip > 0 else ""}{slip} d</div><div class="a">→</div></div>'
        f'<div class="wf-step fc"><div class="k">Forecast Completion</div><div class="v">{_fmt(d.get("project_finish"))}</div></div>'
        f'<div class="wf-arr"><div class="l">Weather adds</div><div class="var {wx_cls}">+{wx_add} wd</div><div class="a">→</div></div>'
        f'<div class="wf-step bw"><div class="k">Bad-weather Completion</div><div class="v">{_fmt(w.get("weather_adjusted_finish"))}</div></div>'
        '</div>'
        '<p class="lg">Reads left → right: the <b>baseline</b> finish, the schedule&rsquo;s own <b>forecast</b> '
        'finish, then the <b>weather-adjusted</b> finish. Each arrow shows that step&rsquo;s variance — the '
        'schedule&rsquo;s own slip, then, separately, what bad weather adds.</p>'
        + _baseline_line(d))


# Headings of the 7 Bad-Weather sub-sections, used when a TICKED sub-section has nothing to
# show (no estimate saved - e.g. the first Calculate ran offline, which saves nothing rather
# than an invented zero - or an estimate without that part). Owner rule: a ticked-but-empty
# part keeps its heading and says "No data available"; it never vanishes or invents numbers.
_WX_TITLES = {
    'wx_dashboard': '1 · Execution Dashboard',
    'wx_timeline': '2 · Calendar Timeline &amp; Statistics',
    'wx_why': '3 · Why This Result — How Each Limit Performed',
    'wx_upcoming': '4 · Upcoming Bad-Weather Days',
    'wx_causes': '5 · What&rsquo;s Causing the Lost Days — by Weather Type',
    'wx_milestones': '6 · Impact on Milestone Completion',
    'wx_recovery': '7 · Conclusion & Recovery Recommendation',
}


def _wx_nodata(key):
    return (f'<h2 class="sec">{_WX_TITLES.get(key, "")}</h2>'
            '<div class="rpt-nodata">No data available</div>')


def _wx_hist3(histogram, scope=''):
    """§2 Calendar Timeline & Statistics — the 3-colour monthly histogram (net working / bad-weather
    / non-working), matching the screen. Reads weather['histogram']. Print-safe stacked CSS bars."""
    rows = histogram or []
    if not rows:
        return ''
    H = 96
    mx = max((r.get('net', 0) + r.get('bad', 0) + r.get('nonworking', 0) for r in rows), default=0) or 1
    def _px(v):
        return round((v or 0) / mx * H)
    bars = ''.join(
        f'<div class="h3c"><div class="h3v">{r.get("net", 0)}</div>'
        f'<div class="h3col">'
        f'<div class="s-bad" style="height:{_px(r.get("bad"))}px"></div>'
        f'<div class="s-nw" style="height:{_px(r.get("nonworking"))}px"></div>'
        f'<div class="s-net" style="height:{_px(r.get("net"))}px"></div></div>'
        f'<div class="h3l">{_esc(r.get("label", ""))}</div></div>' for r in rows)
    legend = (
        f'<div class="whleg"><span><i style="background:{report_theme.var("rpt-good")}"></i>Net working days</span>'
        f'<span><i style="background:{report_theme.var("rpt-bad")}"></i>Non-working days</span>'
        f'<span><i style="background:{report_theme.var("rpt-warn")}"></i>Bad-weather days (expected)</span></div>')
    title = f'<div class="h3title">{_esc(scope)}</div>' if scope else ''
    return (
        '<h2 class="sec">2 · Calendar Timeline &amp; Statistics</h2>'
        f'{title}'
        '<div class="h3sub">Working / non-working / bad-weather days per month · the number above each '
        'bar = <b>net working days</b> (working − bad-weather) · every month is shown to its end, so the '
        'month of the bad-weather completion shows all its working days</div>'
        f'{legend}<div class="h3bars">{bars}</div>')


def _weather_section(weather, dashboard=None, scope=''):
    """Bad Weather report body, split into 7 individually-selectable subsections.

    Returns ``(sections, footnotes)`` where ``sections`` is an ordered list of
    ``(data-sec key, html)`` pairs — wx_dashboard (§1 waterfall), wx_timeline (§2 3-colour
    histogram), wx_why (§3 Why This Result, with the how/criteria preamble), wx_upcoming
    (§4 upcoming bad-weather days — note the §4/§5 SWAP), wx_causes (§5 cause breakdown),
    wx_milestones (§6), wx_recovery (§7) — and ``footnotes`` (the auto weather-conclusion +
    climate/source reference) which ALWAYS renders and is not selectable. render_calendar_report
    wraps each section in its own ``<div data-sec="…">`` and filters by the ticked `sections`."""
    if not weather:
        return [], ''
    w = weather
    total = w.get('expected_bad_days_total', 0) or 0
    waterfall = _weather_waterfall(dashboard, w)          # §1 (replaces the old KPI tiles)
    hist3 = _wx_hist3(w.get('histogram'), scope)          # §2 (replaces the bad-days-only bars)
    # Stop-work limits applied → readable line, reused in the "how it works" note.
    t = w.get('thresholds') or {}
    lim = []
    if t.get('rain_mm') is not None:
        lim.append(f'rain ≥ {t["rain_mm"]:g} mm')
    if t.get('temp_max_c') is not None:
        lim.append(f'heat ≥ {t["temp_max_c"]:g} °C')
    lim.append(f'wind ≥ {t["wind_kmh"]:g} km/h' if t.get('wind_kmh') is not None else 'wind off')
    lim.append('dust on' if t.get('dust', True) else 'dust off')
    # The clarification Ibrahim asked for — how the source works, and what "bad weather" means.
    ref0 = w.get('climate_reference') or {}
    _yrs = ref0.get('years', 5)
    method = (
        '<div class="wxm">'
        '<b>How this estimate is built.</b> Weather is pulled for the project location from '
        '<b>Open-Meteo</b> (free, open, no key): a live ~16-day <b>forecast</b>, then for the rest of '
        f'the run a <b>multi-year climate history</b> — the last {_yrs} years of actual recorded '
        'weather (ERA5), with the day-list following a <b>typical (representative) year</b> and the '
        'monthly view showing the <b>5-year average and range</b> (shown as <i>Expected</i>), plus an '
        'air-quality feed for <b>dust</b>.<br>'
        '<b>What counts as a bad-weather day:</b> a construction day is counted lost when <b>any</b> '
        f'of your stop-work limits is met — {_esc(" · ".join(lim))}. Each flagged day below shows the '
        'measured value against your limit. Applied to <b>construction</b> activities only; a day '
        'already off (weekend / holiday) is never double-counted.</div>')
    # Site type + the stop-work criteria shown IN FULL (what stops work here), so a
    # consultant reading the report sees exactly how every lost day was decided.
    criteria_block = ''
    crit = w.get('criteria') or []
    if crit:
        label = (w.get('site_type_label')
                 or ('Custom limits' if w.get('site_type') == 'custom'
                     else 'Default limits (Desert / inland)'))
        crows = ''.join(
            f'<tr><td>{_esc(c["icon"])} {_esc(c["label"])}</td>'
            f'<td>{_esc(c["value"])}</td><td>{_esc(c["explain"])}'
            f'{"" if c.get("on") else " (not counted)"}</td></tr>' for c in crit)
        criteria_block = (
            f'<div class="grp"><span class="pill" style="background:{report_theme.var("rpt-accent")}">'
            f'Stop-Work Criteria — {_esc(label)}</span></div>'
            '<p class="lg">A construction working day between the data date and finish is counted lost when '
            '<b>any</b> limit below is met.</p>'
            '<table><thead><tr><th>Limit</th><th>Value</th><th>What work it stops</th></tr></thead>'
            f'<tbody>{crows}</tbody></table>')
    # Why this result — how each limit performed over the window (explain a near-zero).
    why_block = ''
    perf = w.get('limit_performance') or []
    if perf:
        def _perf_txt(p):
            unit = f' {p["unit"]}' if p.get('unit') else ''
            if not p.get('on'):
                pk = f' — highest seen {p["peak"]}{unit}' if p.get('peak') is not None else ''
                return f'off (not counted){pk}'
            lim = f' ≥ {p["limit"]}{unit}' if p.get('limit') is not None else ''
            pk = f' · peak {p["peak"]}{unit}' if p.get('peak') is not None else ''
            return f'limit{lim} → flagged {p.get("flagged", 0)} day(s){pk}'
        prows = ''.join(
            f'<tr><td>{_esc(p["label"])}</td><td>{_esc(_perf_txt(p))}</td></tr>' for p in perf)
        why_block = (
            '<h2 class="sec">3 · Why This Result — How Each Limit Performed</h2>'
            '<p class="lg">Over the project window, so a near-zero estimate is explained rather than hidden.</p>'
            '<table><thead><tr><th>Limit</th><th>Result</th></tr></thead>'
            f'<tbody>{prows}</tbody></table>')
    # What's driving the lost days (cause breakdown).
    cause_rows = ''
    for c in w.get('by_cause', []):
        if c.get('off'):
            cnt, share = 'off', '—'
        else:
            cnt = c.get('count', 0)
            share = f'{round(cnt / total * 100)}%' if total else '—'
        cause_rows += (f'<tr><td>{_esc(c["label"])}</td><td class="num">{cnt}</td>'
                       f'<td class="num">{share}</td></tr>')
    cause_table = (
        '<h2 class="sec">5 · What&rsquo;s Causing the Lost Days — by Weather Type</h2>'
        '<p class="lg">Of all the bad-weather days, which condition causes them — so you know what to '
        'plan around (heat-driven → shift the working day earlier; rain-driven → drainage / protection).</p>'
        '<table><thead><tr><th>Cause</th><th class="num">Days</th><th class="num">Share of flagged days</th>'
        f'</tr></thead><tbody>{cause_rows or _empty(3)}</tbody></table>')
    ms = ''.join(
        f'<tr><td>{_esc(m["name"])}</td><td>{_fmt(m["planned"])}</td>'
        f'<td class="num">{m["bad_days_before"]}</td><td class="num">{m["already_allowed"]}</td>'
        f'<td class="num">+{m["net_delay"]} d</td><td>{_fmt(m["adjusted"])}</td></tr>'
        for m in w.get('milestones', []))
    days = ''.join(
        f'<tr><td class="num">{i}</td><td>{_fmt(d["date"])}</td><td>{_esc(d.get("day_name",""))}</td>'
        f'<td>{_esc(d.get("condition",""))}</td>'
        f'<td>{"Forecast" if d.get("confidence") == "forecast" else "Expected"}</td>'
        f'<td>{_acts_cell(d)}</td></tr>' for i, d in enumerate(w.get('bad_days', []), 1))
    # Empty sub-tables are dropped from the PDF (Ibrahim: don't print a section with no results).
    days_table = (
        '<h2 class="sec">4 · Upcoming Bad-Weather Days</h2>'
        '<table><thead><tr><th>#</th><th>Date</th><th>Day</th><th>Why it’s a lost day (measured)</th>'
        f'<th>Confidence</th><th>Affected work (by WBS)</th></tr></thead>'
        f'<tbody>{days}</tbody></table>') if days else ''
    # Source & climate reference — where the bad-weather days come from (Ibrahim: shown in the PDF too).
    source_ref = ''
    ref = w.get('climate_reference') or {}
    if ref:
        loc = ''
        if ref.get('lat') is not None and ref.get('lon') is not None:
            loc = f'{ref["lat"]:.3f}, {ref["lon"]:.3f}'
            if ref.get('place_name'):
                loc = f'{_esc(ref["place_name"])} ({loc})'
        yrs = (f'{ref.get("year_start")}–{ref.get("year_end")}'
               if ref.get('year_start') and ref.get('year_end') else f'last {ref.get("years", 5)} years')
        ref_pairs = [
            ('Climate history', f'<b>{_esc(ref.get("history_source", ""))}</b> — {_esc(ref.get("history_url", ""))}'),
            ('History window', f'{_esc(str(yrs))} · day-list uses a typical year; months show the {ref.get("years", 5)}-year average &amp; range'),
            ('Live forecast', f'{_esc(ref.get("forecast_source", ""))} — {_esc(ref.get("forecast_url", ""))} (next ~16 days)'),
            ('Dust / sandstorm', _esc(ref.get('dust_source', ''))),
        ]
        if loc:
            ref_pairs.append(('Location', loc))
        # What the estimate ran without (the online forecast / dust feed was unavailable) —
        # the same lines the screen shows, so the reader knows the gap.
        for g in (ref.get('gaps') or []):
            ref_pairs.append(('Data gap', _esc(str(g))))
        ref_rows = ''.join(f'<tr><td>{_esc(k)}</td><td>{v}</td></tr>' for k, v in ref_pairs)
        source_ref = (
            f'<div class="grp"><span class="pill" style="background:{report_theme.var("rpt-good")}">Where These Bad-Weather Days Come From</span></div>'
            '<p class="lg">The data source &amp; climate reference — so the numbers can be trusted and checked. '
            'Beyond ~16 days these are <b>climate-based expectations</b> (multi-year history for this site), '
            'not a guaranteed forecast — kept separate from the exact P6 Delay.</p>'
            '<table><thead><tr><th>Feed</th><th>Reference</th></tr></thead>'
            f'<tbody>{ref_rows}</tbody></table>')
    ms_table = (
        '<h2 class="sec">6 · Impact on Milestone Completion</h2>'
        '<table><thead><tr><th>Milestone</th><th>Planned completion</th><th class="num">Bad-weather days before it</th>'
        '<th class="num">Already in calendar</th><th class="num">Net weather delay</th>'
        f'<th>Weather-adjusted completion</th></tr></thead><tbody>{ms}</tbody></table>'
        '<p class="lg"><b>How to read this table.</b> <b>Bad-weather days before it</b> — expected '
        'bad-weather days between the data date and the milestone’s weather-adjusted completion '
        '(the days it is pushed into are checked too). '
        '<b>Already in calendar</b> — of those, the ones landing on a day already off '
        '(weekend / holiday), so they cost nothing extra. <b>Net weather delay</b> — the '
        'rest, hitting real working days (<b>Net = Before − Already in calendar</b>): the actual days '
        'weather adds, which push the <b>Weather-adjusted completion</b> out. '
        '<i>Example — 6 bad-weather days fall before finish; 4 land on Fridays/holidays already off, '
        'so only 2 hit working days → +2 working days.</i></p>') if ms else ''
    # §7 — the conclusion and the recovery recommendation as ONE summary (owner comment 58):
    # the total weather impact, the second shift that recovers it, then the conclusion text.
    from p6_calendar.weather import recovery_summary
    rs = w.get('recovery_summary') or recovery_summary(w)
    concl_p = (f'<p class="rsum-c">{_esc(w["conclusion"])}</p>' if w.get('conclusion') else '')
    if rs:
        fin = (f'{_fmt(rs["planned_finish"])} → {_fmt(rs["adjusted_finish"])}' if rs.get('planned_finish')
               else f'weather-adjusted finish {_fmt(rs["adjusted_finish"])}')
        rec_body = (
            '<table class="rsum"><tr>'
            f'<td class="rsum-big"><div class="rsum-k">Total weather impact</div>'
            f'<div class="rsum-v">+{rs["days"]} wd</div>'
            f'<div class="rsum-s">on project finish<br><b>{fin}</b></div>'
            + (f'<div class="rsum-b">{_esc(rs["basis"])}</div>' if rs.get('basis') else '') + '</td>'
            f'<td class="rsum-rec"><div class="rsum-k">Recovery recommendation · second shift</div>'
            f'<div class="rsum-t">{_esc(rs["text"])}</div></td></tr></table>')
    else:
        rec_body = '<p class="lg"><b>No recovery needed</b> — bad weather adds no working days to the project finish.</p>'
    # heading + tiles + conclusion stay on one page (the page-coordination standard)
    rec_table = ('<div style="break-inside:avoid;page-break-inside:avoid">'
                 '<h2 class="sec">7 · Conclusion &amp; Recovery Recommendation</h2>' + rec_body + concl_p
                 + '</div>') if (rs or concl_p) else ''
    # Seven individually-selectable subsections, each returned under its own data-sec key.
    # The how/criteria preamble rides inside wx_why (it explains "why this result"); the §4/§5
    # SWAP puts Upcoming (§4) ahead of Causes (§5). The source-reference + auto conclusion are
    # returned separately as footnotes — always rendered, never selectable.
    sections = [
        ('wx_dashboard', waterfall),                       # §1 Execution Dashboard
        ('wx_timeline', hist3),                            # §2 Calendar Timeline & Statistics
        ('wx_why', method + criteria_block + why_block),   # §3 Why This Result
        ('wx_upcoming', days_table),                       # §4 Upcoming Bad-Weather Days (SWAP)
        ('wx_causes', cause_table),                        # §5 What's Causing the Lost Days (SWAP)
        ('wx_milestones', ms_table),                       # §6 Impact on Milestone Completion
        ('wx_recovery', rec_table),                        # §7 Conclusion & Recovery Recommendation
    ]
    footnotes = source_ref            # the conclusion now sits in §7 with the recovery
    return sections, footnotes


def render_calendar_report(result, meta, weather=None, sections=None, theme='light',
                           feature='calendar', calendars=None):
    d = result.get('dashboard', {})
    proj = result.get('project', {}) or {}
    primary = result.get('primary_calendar_id')
    by_cal = result.get('by_calendar') or {}
    names = {c['object_id']: c['name'] for c in result.get('assigned_calendars', [])}
    # `calendars` = the calendars picked on screen (§2 chips, comment 77): the first one drives
    # §2 grids / §3 / §4, every one gets its histogram. None → the main calendar first, then
    # every other assigned calendar.
    picked = [c for c in (calendars or []) if c in by_cal]
    if not picked:
        picked = ([primary] if primary in by_cal else []) + [c for c in names if c != primary and c in by_cal]
    main = picked[0] if picked else primary
    bc = by_cal.get(main, {})
    months = bc.get('monthly_stats', [])
    exc = bc.get('exceptions', {'holidays': [], 'special': [], 'shutdowns': []})
    profiles = bc.get('hours_profiles', [])
    cal_name = names.get(main, '')
    others = [(names.get(c, ''), by_cal[c].get('monthly_stats', [])) for c in picked[1:]]
    # The two features print different reports (Ibrahim's split): the P6 Calendar Audit
    # (feature='calendar') never includes weather; the Bad Weather report (feature='weather')
    # is weather-only. `sections` (the in-preview picker) still filters within the feature.
    is_weather = (feature == 'weather')
    # The Bad Weather report is split into 7 individually-selectable subsections (its own
    # data-sec each) — the shared contract with the screen's WEATHER_SECTIONS. The Calendar
    # Audit keeps its five section keys. `sections` (the in-preview picker) filters within.
    WX_KEYS = ['wx_dashboard', 'wx_timeline', 'wx_why', 'wx_upcoming',
               'wx_causes', 'wx_milestones', 'wx_recovery']
    if sections is None:
        sections = (WX_KEYS if is_weather else
                    ['dashboard', 'timeline', 'exceptions', 'hours', 'comparison'])
    inc = lambda k: k in sections
    # Feature 1's dashboard carries no weather (weather lives in the Bad Weather report).
    dash_weather = weather if is_weather else None
    period_note = (f"from the Data Date ({_fmt(d.get('data_date'))}) to Project Completion "
                   f"({_fmt(d.get('window_finish') or d.get('project_finish'))})")

    def _wrap(key, html):
        return f'<div data-sec="{key}">{html}</div>' if html else ''
    # The 7 selectable weather subsections + the always-rendered footnotes (built once; empty
    # when no weather is supplied).
    wx_sections, wx_footnotes = _weather_section(weather, d, meta.get('project_name', ''))
    if is_weather:
        # Each subsection gets its own data-sec wrapper so the live preview can toggle it
        # client-side; the `sections` filter makes the SAVED pdf honour the ticks. The
        # footnotes (auto conclusion + climate/source reference) always render, not selectable.
        got = dict(wx_sections)
        body = ''.join(_wrap(k, got.get(k) or _wx_nodata(k))
                       for k in WX_KEYS if inc(k)) + wx_footnotes
    else:
        # Legacy single 'weather' key — the Special Report's Calendar & Weather provider requests
        # the weather body under feature='calendar'. It renders as one block ONLY when explicitly
        # ticked; the Calendar Audit's own default sections never include 'weather', so the audit
        # itself stays weather-free.
        legacy_weather = ''.join(h for _, h in wx_sections) + wx_footnotes
        body = ''.join([
            _wrap('dashboard', _dashboard(d, dash_weather)) if inc('dashboard') else '',
            _wrap('timeline', _month_grids(months, proj.get('hidden_months', 0), proj.get('timeline_start'), cal_name, others)) if inc('timeline') else '',
            _wrap('exceptions', _exceptions(exc, months, bc.get('rest_weekdays'))) if inc('exceptions') else '',
            _wrap('hours', _hours(profiles)) if inc('hours') else '',
            _wrap('comparison', _comparison(result.get('comparison', []), result.get('usage', []),
                                            period_note)) if inc('comparison') else '',
            _wrap('weather', legacy_weather) if inc('weather') else '',
        ])
    # Feature-aware document branding — the Bad Weather report is its own document, not a
    # Calendar Audit (the review caught calendar branding bleeding into Feature 2).
    proj_name = _esc(meta.get('project_name', ''))
    if is_weather:
        doc_title, kicker = 'Bad Weather effect on Forecast Finish', 'Weather Impact Report'
        subtitle = 'Expected bad-weather days, milestone impact &amp; recovery — a forward-looking estimate'
        cal_label = 'Construction calendar'
        foot = (f'Bad-weather forecast for <b>{proj_name}</b>. A forward-looking estimate from '
                f'Open-Meteo climate history — an estimate, kept separate from the exact P6 dates.')
    else:
        doc_title, kicker = 'Calendar Audit', 'Project Calendar Report'
        subtitle = 'Project working calendar, holidays &amp; working-hour analysis'
        cal_label = 'Calendar'
        foot = (f'Calendar Audit for <b>{proj_name}</b> · calendar "{_esc(cal_name)}". '
                f'Working days, holidays, exceptions and working hours are read directly from the P6 calendar.')
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{doc_title} — {proj_name}</title>
<style>
  @page {{ size: A4 portrait; margin: 18mm 12mm; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: var(--rpt-ink); font-size: 11px; margin: 0; }}
  .head {{ border-bottom: 3px solid var(--rpt-accent); padding-bottom: 12px; margin-bottom: 16px; }}
  .kicker {{ font-size: 10px; letter-spacing: 2px; color: var(--rpt-accent); font-weight: 700; text-transform: uppercase; }}
  .title {{ font-size: 24px; font-weight: 800; color: var(--rpt-ink); margin: 3px 0 1px; }}
  .subtitle {{ font-size: 12px; color: var(--rpt-ink-soft); }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 3px 26px; margin-top: 10px; font-size: 11px; }}
  .meta span {{ color: var(--rpt-muted); }}
  h2.sec {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--rpt-accent);
            border-bottom: 1px solid var(--rpt-hair); padding-bottom: 4px; margin: 20px 0 10px; page-break-after: avoid; break-after: avoid; }}
  .sub2 {{ break-after: avoid; page-break-after: avoid; }}
  .rpt-nodata {{ font-size: 10px; color: var(--rpt-muted); font-style: italic; padding: 6px 0; }}
  .sub2 {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: .5px; color: var(--rpt-muted); font-weight: 700; margin: 8px 0 6px; }}
  .kpis {{ display: grid; gap: 8px; }}
  .kpis.k5 {{ grid-template-columns: repeat(5, 1fr); }}
  .kpis.k4 {{ grid-template-columns: repeat(4, 1fr); }}
  .kpis.k3 {{ grid-template-columns: repeat(3, 1fr); }}
  .kpis.k2 {{ grid-template-columns: repeat(2, 1fr); }}
  .whtot {{ font-size: 10px; color: var(--rpt-ink-soft); margin: 2px 0 6px; }}
  .keep {{ break-inside: avoid; page-break-inside: avoid; }}
  .whtot b {{ color: var(--rpt-ink); }}
  .conflist {{ margin: 4px 0 0; padding-left: 18px; font-size: 10px; line-height: 1.6; }}
  .conflist li {{ margin-bottom: 4px; }}
  .kpi {{ border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 9px 11px; }}
  .kpi .k {{ font-size: 9px; text-transform: uppercase; letter-spacing: .4px; color: var(--rpt-muted); font-weight: 700; }}
  .kpi .v {{ font-size: 17px; font-weight: 800; margin-top: 2px; color: var(--rpt-ink); }}
  .kpi .n {{ font-size: 9px; color: var(--rpt-muted); margin-top: 1px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10px; margin-top: 2px; }}
  thead {{ display: table-header-group; }}
  th {{ background: var(--rpt-th-bg); color: var(--rpt-th-ink); text-align: left; padding: 6px 8px; font-weight: 600; font-size: 9.5px; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid var(--rpt-hair); vertical-align: top; }}
  tbody tr:nth-child(even) {{ background: var(--rpt-surface); }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .empty {{ color: var(--rpt-muted); font-style: italic; }}
  .legend {{ display: flex; gap: 14px; flex-wrap: wrap; margin: 4px 0 10px; font-size: 9.5px; color: var(--rpt-ink-soft); }}
  .legend span {{ display: inline-flex; align-items: center; gap: 4px; }}
  .legend i {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
  .timeline {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .tlm {{ width: 118px; border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 8px; }}
  .tlh {{ font-size: 10px; font-weight: 700; display: flex; justify-content: space-between; margin-bottom: 6px; }}
  .tlh span {{ color: var(--rpt-muted); font-weight: 600; }}
  .dg {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }}
  .dg i {{ aspect-ratio: 1; border-radius: 2px; display: block; }}
  .tlflag {{ margin-top: 6px; font-size: 8.5px; font-weight: 700; text-align: center; }}
  .grp {{ margin: 12px 0 6px; }}
  .pill {{ display: inline-block; padding: 2px 9px; border-radius: 20px; color: var(--rpt-accent-ink); font-weight: 700; font-size: 9px; }}
  .hours {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
  .hp {{ border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 11px; }}
  .hp .t {{ font-weight: 700; }}
  .hp .h {{ font-size: 17px; font-weight: 800; color: var(--rpt-accent); margin-top: 2px; }}
  .hp .s {{ font-size: 9px; color: var(--rpt-muted); margin-top: 3px; }}
  .hp .hpn {{ font-size: 9.5px; color: var(--rpt-ink-soft); margin-top: 6px; font-style: italic;
              border-top: 1px solid var(--rpt-hair); padding-top: 5px; }}
  .mgrids {{ display: flex; flex-wrap: wrap; gap: 12px; }}
  .whleg {{ display: flex; gap: 14px; margin: 4px 0 8px; font-size: 9px; color: var(--rpt-ink-soft); }}
  .whleg span {{ display: inline-flex; align-items: center; gap: 4px; }}
  .whleg i {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
  .whist {{ display: flex; align-items: flex-end; gap: 8px; height: 128px; border-bottom: 1.5px solid var(--rpt-hair); padding: 0 2px; margin-bottom: 10px; }}
  .whc {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; }}
  .wht {{ font-size: 8px; font-weight: 800; color: var(--rpt-ink); margin-bottom: 2px; }}
  .whcol {{ width: 62%; max-width: 34px; }}
  .whn {{ background: var(--rpt-hair-strong); }}
  .whw {{ background: var(--rpt-good); border-radius: 3px 3px 0 0; }}
  .whl {{ font-size: 7.5px; color: var(--rpt-muted); margin-top: 3px; text-align: center; line-height: 1.25; }}
  .mgrid-wrap {{ width: 230px; }}
  .mgrid-t {{ font-size: 10px; font-weight: 700; margin-bottom: 4px; }}
  .mgrid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }}
  .mh {{ font-size: 8px; font-weight: 700; color: var(--rpt-muted); text-align: center; }}
  .mc {{ min-height: 22px; border: 1px solid var(--rpt-edge); border-radius: 4px; font-size: 8.5px; padding: 2px 3px; overflow: hidden; }}
  .mc.blank {{ border: none; }}
  .mc .dn {{ font-weight: 700; }}
  .mc .cn {{ font-size: 6.3px; line-height: 1.12; color: var(--rpt-warn); font-weight: 600; margin-top: 1px; }}
  .lg {{ font-size: 9px; color: var(--rpt-ink-soft); line-height: 1.5; margin: 4px 0 8px; background: var(--rpt-surface); border-left: 3px solid var(--rpt-accent-soft); padding: 6px 9px; border-radius: 0 5px 5px 0; }}
  .lg b {{ color: var(--rpt-ink); }}
  .conf {{ border: 1px solid var(--rpt-edge); border-left: 3px solid var(--rpt-bad); border-radius: 0 6px 6px 0;
           padding: 8px 11px; margin-bottom: 6px; }}
  .conf .ct {{ font-weight: 700; font-size: 11px; }}
  .conf .cd {{ font-size: 10px; color: var(--rpt-ink-soft); margin-top: 2px; }}
  .ok {{ color: var(--rpt-good); font-size: 11px; }}
  .wxm {{ border: 1px solid var(--rpt-edge); background: var(--rpt-surface); border-radius: 6px; padding: 9px 12px;
          font-size: 9.8px; line-height: 1.55; color: var(--rpt-ink-soft); margin-bottom: 10px; }}
  /* Feature 2 §1 — Execution Dashboard waterfall (print-safe, colour-only) */
  .wf {{ display: flex; align-items: stretch; flex-wrap: wrap; margin: 2px 0 6px; }}
  .wf-step {{ flex: 1; min-width: 130px; border: 1px solid var(--rpt-edge); border-radius: 9px; padding: 9px 11px; }}
  .wf-step.bl {{ border-color: var(--rpt-ink-soft); }}
  .wf-step.fc {{ border-color: var(--rpt-accent); }}
  .wf-step.bw {{ border-color: var(--rpt-warn); }}
  .wf-step .k {{ font-size: 8.5px; text-transform: uppercase; letter-spacing: .4px; color: var(--rpt-muted); font-weight: 700; }}
  .wf-step .v {{ font-size: 15px; font-weight: 800; margin-top: 2px; color: var(--rpt-ink); }}
  .wf-step.bw .v {{ color: var(--rpt-warn); }}
  .wf-arr {{ display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 0 8px; min-width: 78px; }}
  .wf-arr .l {{ font-size: 8px; text-transform: uppercase; letter-spacing: .3px; color: var(--rpt-muted); }}
  .wf-arr .var {{ font-size: 12px; font-weight: 800; margin-top: 1px; }}
  .wf-arr .var.zero {{ color: var(--rpt-good); }}
  .wf-arr .var.pos {{ color: var(--rpt-warn); }}
  .wf-arr .a {{ font-size: 14px; color: var(--rpt-muted); }}
  /* Feature 2 §2 — 3-colour monthly histogram (net working / bad-weather / non-working) */
  .h3title {{ font-size: 12px; font-weight: 800; color: var(--rpt-warn); }}
  .h3sub {{ font-size: 9px; color: var(--rpt-muted); margin: 1px 0 8px; }}
  .h3sub b {{ color: var(--rpt-good); }}
  .h3bars {{ display: flex; align-items: flex-end; gap: 8px; height: 118px; border-bottom: 1.5px solid var(--rpt-hair); padding: 0 2px; margin-bottom: 8px; }}
  .h3c {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; }}
  .h3v {{ font-size: 8.5px; font-weight: 800; color: var(--rpt-good); margin-bottom: 2px; }}
  .h3col {{ width: 62%; max-width: 34px; display: flex; flex-direction: column; justify-content: flex-end; }}
  .h3col .s-bad {{ background: var(--rpt-warn); border-radius: 3px 3px 0 0; }}
  .h3col .s-nw {{ background: var(--rpt-bad); }}
  .h3col .s-net {{ background: var(--rpt-good); }}
  .h3l {{ font-size: 7.5px; color: var(--rpt-muted); margin-top: 3px; }}
  table.rsum {{ width: 100%; border-collapse: separate; border-spacing: 0; margin: 4px 0 8px; }}
  table.rsum td {{ border: 0; vertical-align: top; padding: 10px 14px; }}
  table.rsum td.rsum-big {{ width: 30%; background: var(--rpt-bad-bg); border: 1px solid var(--rpt-bad); border-radius: 8px; }}
  table.rsum td.rsum-rec {{ border: 1px solid var(--rpt-edge); border-left: 10px solid var(--rpt-bg); border-radius: 8px; background: var(--rpt-surface); }}
  .rsum-k {{ font-size: 8.5px; font-weight: 800; letter-spacing: .5px; text-transform: uppercase; color: var(--rpt-muted); }}
  .rsum-big .rsum-k {{ color: var(--rpt-bad); }}
  .rsum-v {{ font-size: 26px; font-weight: 800; color: var(--rpt-bad); line-height: 1.15; margin: 3px 0 2px; }}
  .rsum-s {{ font-size: 10px; color: var(--rpt-ink-soft); }} .rsum-s b {{ color: var(--rpt-ink); }}
  .rsum-b {{ font-size: 9px; color: var(--rpt-ink); margin-top: 6px; padding-top: 5px; border-top: 1px dashed var(--rpt-bad); line-height: 1.4; }}
  .rsum-t {{ font-size: 12px; font-weight: 600; line-height: 1.5; margin-top: 4px; color: var(--rpt-ink); }}
  .rsum-c {{ font-size: 10.5px; line-height: 1.55; margin: 0 0 6px; border-left: 4px solid var(--rpt-warn); background: var(--rpt-warn-bg); border-radius: 0 8px 8px 0; padding: 9px 13px; }}
  .concl {{ border-left: 4px solid var(--rpt-accent); background: var(--rpt-surface); border-radius: 0 8px 8px 0; padding: 10px 15px; }}
  .concl ul {{ margin: 0; padding-left: 18px; }}
  .concl li {{ font-size: 11px; line-height: 1.5; margin-bottom: 5px; }}
  .foot {{ border-top: 1px solid var(--rpt-hair); margin-top: 20px; padding-top: 8px; font-size: 9px; color: var(--rpt-muted); line-height: 1.5; }}
</style>
{report_theme.theme_style_tag(theme)}
</head>
<body>
  <div class="head">
    <div class="kicker">{kicker}</div>
    <div class="title">{doc_title}</div>
    <div class="subtitle">{subtitle}</div>
    <div class="meta">
      <div><span>Project:</span> {proj_name}</div>
      <div><span>Data Date:</span> {_esc(_fmt(meta.get('data_date', '')))}</div>
      <div><span>Report Date:</span> {_esc(meta.get('report_date', ''))}</div>
      <div><span>Schedule File:</span> {_esc(meta.get('source_file', ''))}</div>
      <div><span>{cal_label}:</span> {_esc(cal_name)}</div>
    </div>
  </div>
  {body}
  <div class="foot">
    {foot}
  </div>
</body></html>'''
