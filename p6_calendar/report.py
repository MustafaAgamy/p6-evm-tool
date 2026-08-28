"""Consultant-grade Calendar Audit report → HTML (Chrome headless makes the PDF).
Sections follow the spec order: Executive Dashboard, Timeline, Monthly Statistics,
Monthly Calendar View, Exceptions, Working Hours, Comparison, Usage, Conflicts,
[Weather — Slice B], Executive Conclusion. Tables use <thead> so headers repeat
across printed pages."""
import html as _html

import report_theme

# Day-status swatch colours — 'work' reads as good, 'weekend' as a neutral non-working
# grey, 'holiday'/'shutdown' as bad (a full day lost), 'special' (modified hours) as accent.
_STATUS_COLOR = {'work': report_theme.var('rpt-good'), 'weekend': report_theme.var('rpt-hair-strong'),
                 'holiday': report_theme.var('rpt-bad'), 'shutdown': report_theme.var('rpt-bad'),
                 'special': report_theme.var('rpt-accent')}
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


def _dashboard(d, weather=None):
    # Feature 1 (Calendar Audit) carries NO weather: the Weather-Adjusted Finish tile is only
    # added when a weather estimate is supplied (Feature 2 / the combined preview).
    date_tiles = [
        _tile('Baseline Start', _fmt(d.get('baseline_start'))),
        _tile('Baseline Finish', _fmt(d.get('baseline_finish')), 'plan of record'),
        _tile('Data Date', _fmt(d.get('data_date'))),
        _tile('Forecast Finish (P6)', _fmt(d.get('project_finish'))),
    ]
    if weather:
        date_tiles.append(_tile('Weather-Adjusted Finish',
                                _fmt(weather['weather_adjusted_finish']),
                                f"+{weather['net_finish_delay']} wd from weather"))
    dates = ''.join(date_tiles)
    dates_grid = 'k5' if weather else 'k4'
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
            f'<div class="sub2">Key Dates</div><div class="kpis {dates_grid}">{dates}</div>'
            f'<div class="sub2">Calendar Statistics</div><div class="kpis k4">{stats}</div>')


def _monthly_stats(months):
    rows = ''.join(
        f'<tr><td>{_esc(m["label"])}</td><td class="num">{m["working_days"]}</td>'
        f'<td class="num">{m["holidays"]}</td><td class="num">{m["exceptions"]}</td>'
        f'<td class="num">{m["working_hours"]}</td></tr>' for m in months)
    return ('<h2 class="sec">3 · Monthly Calendar Statistics</h2>'
            '<table><thead><tr><th>Month</th><th class="num">Working Days</th>'
            '<th class="num">Holidays</th><th class="num">Exceptions</th>'
            f'<th class="num">Working Hours</th></tr></thead><tbody>{rows}</tbody></table>')


def _working_hist(months):
    """§2 as a working vs non-working days-per-month histogram (Ibrahim's restructure —
    replaces the crude colour strip; the exact numbers are the §3 table)."""
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
        cols += (f'<div class="whc"><div class="wht">{tot}</div>'
                 f'<div class="whcol"><div class="whn" style="height:{nwpx}px"></div>'
                 f'<div class="whw" style="height:{wpx}px"></div></div>'
                 f'<div class="whl">{_esc(m["label"])}</div></div>')
    legend = (f'<div class="whleg"><span><i style="background:{report_theme.var("rpt-good")}"></i>Working days</span>'
              f'<span><i style="background:{report_theme.var("rpt-hair-strong")}"></i>Non-working (weekends + holidays + shutdowns)</span></div>')
    return legend + f'<div class="whist">{cols}</div>'


def _month_grids(months, hidden_months=0, tl_from=None):
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
                                     ('Holiday', _STATUS_COLOR['holiday']), ('Shutdown', _STATUS_COLOR['shutdown']),
                                     ('Special hours', _STATUS_COLOR['special'])])
              + '</div>')
    if hidden_months:
        sub = (f'— working vs non-working days per month, from the data date ({_fmt(tl_from)}) · '
               f'{hidden_months} earlier month{"s" if hidden_months != 1 else ""} hidden')
    else:
        sub = '— working vs non-working days per month'
    return ('<h2 class="sec">2 · Calendar Timeline '
            f'<span style="font-weight:400;font-size:9.5px;color:{report_theme.var("rpt-muted")};text-transform:none;letter-spacing:0">'
            f'{_esc(sub)}</span></h2>'
            + _working_hist(months)
            + '<div class="sub2">Each month’s calendar — holiday / shutdown names shown in the day cells</div>'
            + legend + f'<div class="mgrids">{"".join(blocks)}</div>')


def _exceptions(exc):
    def tbl(title, color, rows_html, headers):
        if not rows_html:                 # hide a group with no results (Ibrahim: PDF drops empties)
            return ''
        cells = []
        for label, is_num in headers:
            cls = ' class="num"' if is_num else ''
            cells.append(f'<th{cls}>{_esc(label)}</th>')
        h = ''.join(cells)
        return (f'<div class="grp"><span class="pill" style="background:{color}">{_esc(title)}</span></div>'
                f'<table><thead><tr>{h}</tr></thead><tbody>{rows_html}</tbody></table>')
    hol = ''.join(f'<tr><td>{_esc(x["description"])}</td><td class="num">{x["days"]}</td>'
                  f'<td>{_esc(x.get("reason") or "—")}</td></tr>' for x in exc.get('holidays', []))
    sp = ''.join(f'<tr><td>{_esc(x["description"])}</td><td class="num">{x["days"]}</td>'
                 f'<td>{_esc(x.get("hours") or "")}</td></tr>' for x in exc.get('special', []))
    sh = ''.join(f'<tr><td>{_esc(x["description"])}</td><td class="num">{x["days"]}</td>'
                 f'<td>{("[added] " if x.get("source") == "manual" else "") + (x.get("reason") or "—")}</td></tr>'
                 for x in exc.get('shutdowns', []))
    groups = (tbl('Holidays & Vacations', report_theme.var('rpt-bad'), hol,
                  [('Date', 0), ('Days', 1), ('Description', 0)])
              + tbl('Reduced / Special Working Hours', report_theme.var('rpt-accent'), sp,
                    [('Date', 0), ('Days', 1), ('Hours', 0)])
              + tbl('Shutdowns', report_theme.var('rpt-bad'), sh,
                    [('Date', 0), ('Days', 1), ('Reason', 0)]))
    if not groups:                        # no exceptions ahead → drop the whole section
        return ''
    return '<h2 class="sec">4 · Calendar Exceptions</h2>' + groups


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
    def _card(p):
        # The planner's justification note (e.g. "Summer / Ramadan reduced hours") prints
        # under the profile when set; hidden when blank (Ibrahim: don't print empty rows).
        note = (p.get('note') or '').strip()
        note_html = f'<div class="hpn">✎ {_esc(note)}</div>' if note else ''
        return (f'<div class="hp"><div class="t">{_esc(p["name"])}</div>'
                f'<div class="h">{_esc(p["hours"])}</div>'
                f'<div class="s">{_esc(p["hours_per_day"])} hrs · {_esc(p.get("sub", ""))}</div>'
                f'{note_html}</div>')
    cards = ''.join(_card(p) for p in profiles)
    return ('<h2 class="sec">5 · Working Hours Profile</h2>'
            '<p class="lg">Your <b>standard working day</b>, used all year — different from the '
            '<i>Reduced / Special Working Hours</i> in section 4, which are specific dates whose hours '
            'differ from this standard (differences under 5 minutes are ignored).</p>'
            f'<div class="hours">{cards}</div>')


def _comparison(cmp, usage=None, period_note=''):
    # Merged Calendar Comparison & Usage (matches the screen): hours/day, days/week, activities
    # assigned, % of activities, non-working days ahead, and role — one row per calendar.
    umap = {u['name']: u for u in (usage or [])}
    rows = ''
    for c in cmp:
        u = umap.get(c['name'], {})
        acts = u.get('activities', 0)
        pct = '—' if u.get('role') == 'Unused' or u.get('pct') is None else f'{u["pct"]}%'
        role = _esc(u.get('role', ''))
        rows += (f'<tr><td>{_esc(c["name"])}{" (default)" if c.get("is_default") else ""}</td>'
                 f'<td class="num">{c["hours_per_day"]}</td><td class="num">{c["days_per_week"]}</td>'
                 f'<td class="num">{acts}</td><td class="num">{pct}</td>'
                 f'<td class="num">{c.get("nonworking_days", 0)}</td><td>{role}</td></tr>')
    note = (f'<p class="lg"><b>% of Activities</b> — share of the schedule\'s activities on each '
            f'calendar. <b>Non-Working Days</b> — weekends, holidays and shutdowns still ahead, '
            f'{_esc(period_note)}. <b>Unused</b> calendars carry no activity and can be removed.</p>'
            ) if period_note else ''
    return ('<h2 class="sec">6 · Calendar Comparison &amp; Usage</h2>'
            '<table><thead><tr><th>Calendar</th><th class="num">Hours/Day</th>'
            '<th class="num">Days/Week</th><th class="num">Assigned to</th>'
            '<th class="num">% of Activities</th><th class="num">Non-Working Days</th><th>Role</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>{note}')


def _conflicts(conflicts):
    if not conflicts:
        return '<h2 class="sec">7 · Calendar Conflicts</h2><p class="ok">✓ No calendar conflicts detected — assignments look clean.</p>'
    lines = ''.join(f'<li><b>{_esc(c["title"])}</b> — {_esc(c["detail"])}</li>' for c in conflicts)
    n = len(conflicts)
    return (f'<h2 class="sec">7 · Calendar Conflicts</h2>'
            f'<p style="margin:0 0 6px;font-size:11px">Summary: <b>{n}</b> issue{"" if n == 1 else "s"} found.</p>'
            f'<ul style="margin:0;padding-left:18px">{lines}</ul>')


def _wx_monthly_bars(monthly):
    """Section 9 histogram — expected bad-weather days per month (the mockup's
    'When the risk falls'). Print-friendly CSS bars; peak month highlighted red."""
    monthly = monthly or []
    if not monthly:
        return ''
    mx = max((m.get('count', 0) for m in monthly), default=0) or 1
    bars = ''.join(
        f'<div class="wxb"><div class="wxb-v">{m.get("count") or ""}</div>'
        f'<div class="wxb-bar{" pk" if m.get("count", 0) == mx and mx > 0 else ""}" '
        f'style="height:{max(3, round(m.get("count", 0) / mx * 62))}px"></div>'
        f'<div class="wxb-l">{_esc(m.get("label", ""))}</div></div>' for m in monthly)
    return (f'<div class="grp"><span class="pill" style="background:{report_theme.var("rpt-warn")}">When the Risk Falls'
            ' — bad-weather days by month</span></div>'
            f'<div class="wxbars">{bars}</div>')


def _weather_section(weather):
    """Section 9 — Weather Impact (only when a location/weather estimate exists)."""
    if not weather:
        return ''
    w = weather
    total = w.get('expected_bad_days_total', 0) or 0
    kpis = ''.join([
        _tile('Bad-weather days (remaining)', total),
        _tile('Net weather delay to finish', f"+{w.get('net_finish_delay', 0)} wd"),
        _tile('Weather-adjusted finish', _fmt(w.get('weather_adjusted_finish'))),
    ])
    monthly_bars = _wx_monthly_bars(w.get('monthly'))
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
        'already off (weekend / holiday / shutdown) is never double-counted.</div>')
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
            f'<div class="grp"><span class="pill" style="background:{report_theme.var("rpt-accent")}">'
            'Why This Result — How Each Limit Performed</span></div>'
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
        f'<div class="grp"><span class="pill" style="background:{report_theme.var("rpt-warn")}">What&rsquo;s Causing the Lost Days — by Weather Type</span></div>'
        '<p class="lg">Of all the bad-weather days, which condition causes them — so you know what to '
        'plan around (heat-driven → shift the working day earlier; rain-driven → drainage / protection).</p>'
        '<table><thead><tr><th>Cause</th><th class="num">Days</th><th class="num">Share of flagged days</th>'
        f'</tr></thead><tbody>{cause_rows or _empty(3)}</tbody></table>')
    ms = ''.join(
        f'<tr><td>{_esc(m["name"])}</td><td>{_fmt(m["planned"])}</td>'
        f'<td class="num">{m["bad_days_before"]}</td><td class="num">{m["already_allowed"]}</td>'
        f'<td class="num">+{m["net_delay"]} d</td><td>{_fmt(m["adjusted"])}</td></tr>'
        for m in w.get('milestones', []))
    rec = ''.join(
        f'<tr><td>{_esc(r["period"])}</td><td class="num">{r["days"]} d</td>'
        f'<td>{_esc(r["option_longer_days"])}</td><td>{_esc(r["option_extra_days"])}</td>'
        f'<td>{_esc(r["option_shift"])}</td></tr>' for r in w.get('recovery', []))
    days = ''.join(
        f'<tr><td>{_fmt(d["date"])}</td><td>{_esc(d.get("day_name",""))}</td>'
        f'<td>{_esc(d.get("condition",""))}</td>'
        f'<td>{"Forecast" if d.get("confidence") == "forecast" else "Expected"}</td>'
        f'<td>{_acts_cell(d)}</td></tr>' for d in w.get('bad_days', []))
    # Empty sub-tables are dropped from the PDF (Ibrahim: don't print a section with no results).
    days_table = (
        f'<div class="grp"><span class="pill" style="background:{report_theme.var("rpt-accent")}">Upcoming Bad-Weather Days</span></div>'
        '<table><thead><tr><th>Date</th><th>Day</th><th>Why it’s a lost day (measured)</th>'
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
        ref_rows = ''.join(f'<tr><td>{_esc(k)}</td><td>{v}</td></tr>' for k, v in ref_pairs)
        source_ref = (
            f'<div class="grp"><span class="pill" style="background:{report_theme.var("rpt-good")}">Where These Bad-Weather Days Come From</span></div>'
            '<p class="lg">The data source &amp; climate reference — so the numbers can be trusted and checked. '
            'Beyond ~16 days these are <b>climate-based expectations</b> (multi-year history for this site), '
            'not a guaranteed forecast — kept separate from the exact P6 Delay.</p>'
            '<table><thead><tr><th>Feed</th><th>Reference</th></tr></thead>'
            f'<tbody>{ref_rows}</tbody></table>')
    ms_table = (
        f'<div class="grp"><span class="pill" style="background:{report_theme.var("rpt-warn")}">Impact on Milestone Completion</span></div>'
        '<table><thead><tr><th>Milestone</th><th>Planned completion</th><th class="num">Bad-weather days before it</th>'
        '<th class="num">Already in calendar</th><th class="num">Net weather delay</th>'
        f'<th>Weather-adjusted completion</th></tr></thead><tbody>{ms}</tbody></table>'
        '<p class="lg"><b>How to read this table.</b> <b>Bad-weather days before it</b> — expected '
        'bad-weather days between the data date and the milestone’s planned finish. '
        '<b>Already in calendar</b> — of those, the ones landing on a day already off '
        '(weekend / holiday / shutdown), so they cost nothing extra. <b>Net weather delay</b> — the '
        'rest, hitting real working days (<b>Net = Before − Already in calendar</b>): the actual days '
        'weather adds, which push the <b>Weather-adjusted completion</b> out. '
        '<i>Example — 6 bad-weather days fall before finish; 4 land on Fridays/holidays already off, '
        'so only 2 hit working days → +2 working days.</i></p>') if ms else ''
    rec_table = (
        f'<div class="grp"><span class="pill" style="background:{report_theme.var("rpt-good")}">Recovery Recommendations</span></div>'
        '<table><thead><tr><th>Period / milestone</th><th class="num">Days</th><th>Longer days</th>'
        f'<th>Extra working days</th><th>Add shift</th></tr></thead><tbody>{rec}</tbody></table>') if rec else ''
    conclusion = ''
    if w.get('conclusion'):
        conclusion = (
            f'<div class="grp"><span class="pill" style="background:{report_theme.var("rpt-warn")}">Weather Conclusion</span></div>'
            f'<div class="concl" style="border-left-color:{report_theme.var("rpt-warn")};background:{report_theme.var("rpt-warn-bg")}">'
            f'<p style="margin:0;font-size:10.5px;line-height:1.5">{_esc(w["conclusion"])}</p></div>')
    return (
        '<h2 class="sec">1 · Weather Impact '
        f'<span style="font-weight:400;font-size:9.5px;color:{report_theme.var("rpt-warn")};text-transform:none;letter-spacing:0">'
        '— estimate, not a P6 figure</span></h2>'
        f'{method}{criteria_block}'
        f'<div class="kpis" style="grid-template-columns:repeat(3,1fr);margin-bottom:10px">{kpis}</div>'
        f'{why_block}{monthly_bars}{source_ref}{cause_table}{days_table}{ms_table}{rec_table}{conclusion}')


def _conclusion(bullets, weather=None):
    items = ''.join(f'<li>{_esc(b)}</li>' for b in bullets)
    wx = (f'<li><b>Weather:</b> ~{weather["expected_bad_days_total"]} bad-weather days expected; '
          f'net estimated +{weather["net_finish_delay"]} working days to the finish.</li>') if weather else ''
    return (f'<h2 class="sec">8 · Executive Conclusion</h2>'
            f'<div class="concl"><ul>{items}{wx}</ul></div>')


def render_calendar_report(result, meta, weather=None, sections=None, theme='light',
                           feature='calendar'):
    d = result.get('dashboard', {})
    proj = result.get('project', {}) or {}
    primary = result.get('primary_calendar_id')
    bc = (result.get('by_calendar') or {}).get(primary, {})
    months = bc.get('monthly_stats', [])
    exc = bc.get('exceptions', {'holidays': [], 'special': [], 'shutdowns': []})
    profiles = bc.get('hours_profiles', [])
    cal_name = next((c['name'] for c in result.get('assigned_calendars', [])
                     if c['object_id'] == primary), '')
    # The two features print different reports (Ibrahim's split): the P6 Calendar Audit
    # (feature='calendar') never includes weather; the Bad Weather report (feature='weather')
    # is weather-only. `sections` (the in-preview picker) still filters within the feature.
    is_weather = (feature == 'weather')
    if sections is None:
        sections = (['weather'] if is_weather else
                    ['dashboard', 'timeline', 'stats', 'exceptions', 'hours',
                     'comparison', 'conflicts', 'conclusion'])
    inc = lambda k: k in sections
    # Feature 1's dashboard/conclusion carry no weather (weather lives in the Bad Weather report).
    dash_weather = weather if is_weather else None
    period_note = f"from the data date ({_fmt(d.get('data_date'))}) to finish"

    def _wrap(key, html):
        return f'<div data-sec="{key}">{html}</div>' if html else ''
    body = ''.join([
        _wrap('dashboard', _dashboard(d, dash_weather)) if inc('dashboard') else '',
        _wrap('timeline', _month_grids(months, proj.get('hidden_months', 0), proj.get('timeline_start'))) if inc('timeline') else '',
        _wrap('stats', _monthly_stats(months)) if inc('stats') else '',
        _wrap('exceptions', _exceptions(exc)) if inc('exceptions') else '',
        _wrap('hours', _hours(profiles)) if inc('hours') else '',
        _wrap('comparison', _comparison(result.get('comparison', []), result.get('usage', []), period_note)) if inc('comparison') else '',
        _wrap('conflicts', _conflicts(result.get('conflicts', []))) if inc('conflicts') else '',
        _wrap('weather', _weather_section(weather)) if inc('weather') else '',
        _wrap('conclusion', _conclusion(result.get('conclusion', []), dash_weather)) if inc('conclusion') else '',
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
        subtitle = 'Project working calendar, holidays, shutdowns &amp; working-hour analysis'
        cal_label = 'Calendar'
        foot = (f'Calendar Audit for <b>{proj_name}</b> · calendar "{_esc(cal_name)}". '
                f'Working days, holidays, exceptions and working hours are read directly from the P6 calendar.')
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{doc_title} — {proj_name}</title>
<style>
  @page {{ margin: 18mm 12mm; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: var(--rpt-ink); font-size: 11px; margin: 0; }}
  .head {{ border-bottom: 3px solid var(--rpt-accent); padding-bottom: 12px; margin-bottom: 16px; }}
  .kicker {{ font-size: 10px; letter-spacing: 2px; color: var(--rpt-accent); font-weight: 700; text-transform: uppercase; }}
  .title {{ font-size: 24px; font-weight: 800; color: var(--rpt-ink); margin: 3px 0 1px; }}
  .subtitle {{ font-size: 12px; color: var(--rpt-ink-soft); }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 3px 26px; margin-top: 10px; font-size: 11px; }}
  .meta span {{ color: var(--rpt-muted); }}
  h2.sec {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--rpt-accent);
            border-bottom: 1px solid var(--rpt-hair); padding-bottom: 4px; margin: 20px 0 10px; page-break-after: avoid; }}
  .sub2 {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: .5px; color: var(--rpt-muted); font-weight: 700; margin: 8px 0 6px; }}
  .kpis {{ display: grid; gap: 8px; }}
  .kpis.k5 {{ grid-template-columns: repeat(5, 1fr); }}
  .kpis.k4 {{ grid-template-columns: repeat(4, 1fr); }}
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
  .whist {{ display: flex; align-items: flex-end; gap: 8px; height: 118px; border-bottom: 1.5px solid var(--rpt-hair); padding: 0 2px; margin-bottom: 10px; }}
  .whc {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; }}
  .wht {{ font-size: 8px; font-weight: 800; color: var(--rpt-ink); margin-bottom: 2px; }}
  .whcol {{ width: 62%; max-width: 34px; }}
  .whn {{ background: var(--rpt-hair-strong); }}
  .whw {{ background: var(--rpt-good); border-radius: 3px 3px 0 0; }}
  .whl {{ font-size: 7.5px; color: var(--rpt-muted); margin-top: 3px; }}
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
  .wxbars {{ display: flex; align-items: flex-end; gap: 8px; height: 92px; border-bottom: 1.5px solid var(--rpt-hair); padding: 0 4px; margin: 2px 0 8px; }}
  .wxb {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; }}
  .wxb-v {{ font-size: 9px; font-weight: 800; color: var(--rpt-warn); margin-bottom: 2px; }}
  .wxb-bar {{ width: 62%; max-width: 30px; background: linear-gradient(180deg, var(--rpt-warn), color-mix(in srgb, var(--rpt-warn) 45%, transparent)); border-radius: 3px 3px 0 0; }}
  .wxb-bar.pk {{ background: linear-gradient(180deg, var(--rpt-bad), color-mix(in srgb, var(--rpt-bad) 50%, transparent)); }}
  .wxb-l {{ font-size: 8px; color: var(--rpt-muted); margin-top: 3px; }}
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
