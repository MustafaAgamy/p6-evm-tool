"""The Manager Report — a plain-English executive one-pager built from the update's analysis,
for a manager with no Primavera / project-control background. Manager-first order: the one
line, then finish-date-vs-promise and money, who it's coming from, what the manager must
decide — the how/why detail sits at the bottom. Every figure comes from the schedule; time
is spoken in weeks/months, never "working days"; no jargon.
"""
import html as _html
from datetime import datetime, date


def _to_date(v):
    """Parse the many date shapes the report sees (datetime, ISO string, '15-Aug-2027') to a
    date. None on anything unparseable — the caller degrades gracefully."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        pass
    for fmt in ('%d-%b-%Y', '%d-%b.%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _fmt_d(v):
    d = _to_date(v)
    return d.strftime('%d-%b-%Y') if d else None


def _pct100(v):
    """A stored progress value -> 0..100. The DB keeps these as 0-1 fractions; a value already
    on a 0-100 scale is passed through, so a scale change can't silently 100x the chart."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f <= 1.5:
        f *= 100
    return max(0.0, min(100.0, f))


def build_scurve(history, baseline_finish, forecast_finish):
    """Plot series for the progress S-curve from the stored planned/actual history + the finish
    dates. Returns None when there isn't enough to draw it honestly (no history, or no finish)."""
    ff, bf = _to_date(forecast_finish), _to_date(baseline_finish)
    pts = []
    for h in (history or []):
        d = _to_date(h.get('date'))
        if d is not None:
            pts.append((d, _pct100(h.get('planned')), _pct100(h.get('actual'))))
    pts.sort(key=lambda t: t[0])
    if not pts or ff is None:
        return None
    planned = [(d, p) for (d, p, a) in pts if p is not None]
    actual = [(d, a) for (d, p, a) in pts if a is not None]
    if not actual:
        return None
    if bf is not None:
        planned = planned + [(bf, 100.0)]
    last_d, last_a = actual[-1]
    forecast = [(last_d, last_a), (ff, 100.0)]
    xs = [d for d, _ in planned] + [d for d, _ in actual] + [ff] + ([bf] if bf else [])
    return {'planned': planned, 'actual': actual, 'forecast': forecast,
            'x0': min(xs), 'x1': max(xs), 'baseline_finish': bf, 'forecast_finish': ff, 'data_date': last_d}


def render_scurve_svg(sc):
    """The S-curve as a self-contained inline SVG (renders on screen and through Chrome PDF)."""
    if not sc:
        return ''
    x0, x1 = sc['x0'].toordinal(), sc['x1'].toordinal()
    span = max(1, x1 - x0)

    def X(d):
        return 40 + (d.toordinal() - x0) / span * 580

    def Y(p):
        return 210 - (max(0.0, min(100.0, p)) / 100) * 190

    def poly(series):
        return ' '.join(f'{X(d):.1f},{Y(p):.1f}' for d, p in series)

    grid = ''.join(f'<line x1="40" y1="{y}" x2="620" y2="{y}"/>' for y in (210, 162.5, 115, 67.5, 20))
    ylabels = ''.join(f'<text x="34" y="{y + 3}">{p}%</text>'
                      for y, p in ((210, 0), (162.5, 25), (115, 50), (67.5, 75), (20, 100)))
    dd, bf, ff = sc['data_date'], sc['baseline_finish'], sc['forecast_finish']
    marks = ''
    if bf is not None:
        marks += (f'<line x1="{X(bf):.1f}" y1="20" x2="{X(bf):.1f}" y2="222" stroke="#94a3b8" stroke-width="1" stroke-dasharray="2 2"/>'
                  f'<text x="{X(bf):.1f}" y="234" fill="#94a3b8" font-size="9" text-anchor="middle">Promised {_fmt_d(bf)}</text>')
    marks += (f'<line x1="{X(ff):.1f}" y1="20" x2="{X(ff):.1f}" y2="222" stroke="#dc2626" stroke-width="1" stroke-dasharray="2 2"/>'
              f'<text x="{X(ff):.1f}" y="234" fill="#dc2626" font-size="9" text-anchor="middle">Forecast {_fmt_d(ff)}</text>')
    return (f'<svg viewBox="0 0 660 250" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI,Arial,sans-serif">'
            f'<g stroke="#eef2f7" stroke-width="1">{grid}</g>'
            f'<g fill="#94a3b8" font-size="9" text-anchor="end">{ylabels}</g>'
            f'<polyline fill="none" stroke="#94a3b8" stroke-width="2.5" points="{poly(sc["planned"])}"/>'
            f'<polyline fill="none" stroke="#1d4ed8" stroke-width="2.5" points="{poly(sc["actual"])}"/>'
            f'<polyline fill="none" stroke="#1d4ed8" stroke-width="2.5" stroke-dasharray="5 4" points="{poly(sc["forecast"])}"/>'
            f'<circle cx="{X(dd):.1f}" cy="{Y(sc["actual"][-1][1]):.1f}" r="3.5" fill="#1d4ed8"/>'
            f'<line x1="{X(dd):.1f}" y1="20" x2="{X(dd):.1f}" y2="210" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="3 3"/>'
            f'<text x="{X(dd):.1f}" y="14" fill="#64748b" font-size="9" text-anchor="middle">Data date · {_fmt_d(dd)}</text>'
            f'{marks}</svg>')


def _plain_time(days):
    """Working days -> plain calendar language a manager thinks in."""
    if days is None:
        return None
    d = abs(days)
    months, weeks = round(d / 21), max(1, round(d / 5))
    if months >= 2:
        return f"about {months} months"
    if weeks >= 2:
        return f"about {weeks} weeks"
    return f"about {d} day(s)"


def _status(delay):
    if delay is None:
        return ('Unknown', 'muted')
    if delay <= 0:
        return ('On track', 'good')
    if delay <= 10:
        return ('Slipping', 'warn')
    return ('Behind', 'bad')


def build_manager_report(ctx):
    """Turn the project 'brain' into the manager-first report structure (all plain text)."""
    delay = ctx.get('delay_days')
    status, tone = _status(delay)
    worst = ctx.get('worst_discipline')
    driver = worst['name'] if worst else 'the works in progress'
    plain = _plain_time(delay)

    if delay is None:
        one_line = ("There isn't enough finish-date information in this update yet — import an "
                    "updated schedule with a finish milestone and I'll brief you.")
    elif delay <= 0:
        one_line = f"{ctx['project_name']} is on track to finish on time. Keep protecting the pace on the areas furthest along."
    else:
        one_line = (f"We're {plain} behind — mainly the {driver} — and it will keep slipping unless we act now. "
                    f"I need your decision on a recovery push.")

    finish = None
    if ctx.get('baseline_finish') and ctx.get('forecast_finish'):
        finish = {'promised': ctx['baseline_finish'], 'forecast': ctx['forecast_finish'], 'later': plain}

    trend = None
    t = ctx.get('trend')
    if t:
        prev_plain = _plain_time(t['prev_delay'])
        if t['direction'] == 'worse':
            trend = {'dir': 'worse', 'text': f"Getting worse — {prev_plain} late last update, {plain} now."}
        elif t['direction'] == 'better':
            trend = {'dir': 'better', 'text': f"Improving — down from {prev_plain} late last update to {plain} now."}
        else:
            trend = {'dir': 'same', 'text': "About the same as the last update."}

    money = fault = None
    actions = []
    detail = {}
    if delay and delay > 0:
        money = ("Every extra month on site adds cost (extended overheads, and possible penalties under the "
                 "contract). There may be grounds to claim some time back — and we may owe the contractor an "
                 "extension too. This needs a commercial review.")
        # 'Where it's coming from' — grounded in what the schedule shows; client-side causes are noted, not invented.
        oos = ctx.get('oos_count')
        exec_bit = (f"{oos} activities were started out of their proper order — an execution / contractor-side signal. "
                    if oos else "")
        fault = (f"What the schedule shows: the {driver} is the furthest behind. {exec_bit}"
                 "Any client-side causes (e.g. late access, late information) aren't in the schedule — note them in "
                 "the Claims tool to complete the ownership picture.")
        actions = [
            f"Approve a recovery push (overtime / a second crew) on the {driver}.",
            "Get a written recovery plan from the contractor, with dates.",
            "Re-forecast after the plan (use the what-if for an exact new finish date).",
            "Approve a commercial review of the claim position — both directions.",
        ]
        behind = None
        if worst:
            behind = (f"The {driver} is about {worst['actual']}% done against {worst['planned']}% planned — the biggest "
                      "gap. ")
        risks = [f"The {driver} slipping further — the biggest single threat to the finish date."]
        if ctx.get('oos_count'):
            risks.append(f"{ctx['oos_count']} activities out of order — a rework and coordination risk.")
        if ctx.get('float_grade') in ('Critical', 'Needs Attention'):
            risks.append("Very little spare time left in the plan to absorb new problems.")
        detail = {
            'behind': (behind or "") + ("Work is getting done at about "
                       f"{ctx['pace_pct']}% of the planned speed." if ctx.get('pace_pct') is not None else ""),
            'risks': risks,
            'forecast_note': (f"The {plain}-behind figure assumes the {driver} finishes on its current forecast; to see "
                              "the finish date if it slips to a specific date, the Copilot's what-if gives the exact number."),
        }

    return {
        'project_name': ctx.get('project_name'),
        'data_date': ctx.get('data_date'),
        'status': status, 'tone': tone,
        'one_line': one_line,
        'finish': finish, 'trend': trend, 'money': money, 'fault': fault,
        'actions': actions, 'detail': detail,
        # V2 report additions (drivers/recovery attached by the report route, which re-parses):
        'scurve': build_scurve(ctx.get('history'), ctx.get('baseline_finish'), ctx.get('forecast_finish')),
        'drivers': ctx.get('drivers') or [],
        'recovery': ctx.get('recovery'),
    }


# ── printable HTML (on-screen preview + Chrome-headless PDF) ────────────────

_TONE = {'bad': '#dc2626', 'warn': '#d97706', 'good': '#16a34a', 'muted': '#64748b'}


def render_manager_report_html(report, meta=None):
    meta = meta or {}
    e = _html.escape
    tone = _TONE.get(report.get('tone'), _TONE['muted'])
    r = report

    def _list(items, ordered=False):
        if not items:
            return ''
        tag = 'ol' if ordered else 'ul'
        lis = ''.join(f'<li>{e(x)}</li>' for x in items)
        return f'<{tag}>{lis}</{tag}>'

    finish_html = ''
    if r.get('finish'):
        f = r['finish']
        finish_html = (f'<div class="tile"><div class="tl">Finish date</div>'
                       f'<div class="tv">{e(f["forecast"])}</div>'
                       f'<div class="tn">promised {e(f["promised"])} · {e(f["later"] or "")} later</div></div>')
    trend_html = ''
    if r.get('trend'):
        trend_html = (f'<div class="tile"><div class="tl">Direction</div>'
                      f'<div class="tv">{e(r["trend"]["text"].split(" — ")[0])}</div>'
                      f'<div class="tn">{e(r["trend"]["text"])}</div></div>')

    money_html = f'<div class="band money"><b>Money &amp; exposure:</b> {e(r["money"])}</div>' if r.get('money') else ''

    # NEW · the progress S-curve (leads the where/how detail)
    chart_html = ''
    if r.get('scurve'):
        chart_html = (f'<div class="chart"><div class="chart-h">Progress — planned vs actual, with the forecast to finish</div>'
                      f'{render_scurve_svg(r["scurve"])}'
                      f'<div class="legend"><span><i style="border-color:#94a3b8"></i>Planned</span>'
                      f'<span><i style="border-color:#1d4ed8"></i>Actual</span>'
                      f'<span><i style="border-color:#1d4ed8;border-top-style:dashed"></i>Forecast to finish</span></div></div>')

    # NEW · recovery line with a real number (from the what-if engine)
    recovery_html = ''
    rec = r.get('recovery')
    if rec:
        newf = _fmt_d(rec.get('new_finish'))
        to = (f" — bringing completion in from {e(r['finish']['forecast'])} to about {e(newf)}"
              if newf and r.get('finish') else "")
        recovery_html = (f'<div class="recovery"><div class="rh">↩ Recovery opportunity</div>'
                         f'Adding a second crew to <b>{e(rec["activity"])}</b> could recover about '
                         f'<b>{e(str(rec["recovered"]))} working days</b>{to}. An estimate from this update; '
                         f'confirm the exact date with a P6 recalculation before committing.</div>')

    # NEW · the named critical activities, folded into "where it's coming from"
    drivers_html = ''
    for d in (r.get('drivers') or []):
        tag = ' <span class="nwtag">driving</span>' if d.get('driving') else ''
        val = f'{d["late"]} wd late' if d.get('late') else 'on the critical path'
        drivers_html += f'<li><span class="dn">{e(d.get("name") or "")}{tag}</span><span class="dd">{e(val)}</span></li>'
    if drivers_html:
        drivers_html = f'<ul class="drivers">{drivers_html}</ul>'
    fault_inner = e(r["fault"]) if r.get('fault') else ''
    fault_html = (f'<div class="band"><b>Where it\'s coming from:</b> {fault_inner}{drivers_html}</div>'
                  if (r.get('fault') or drivers_html) else '')

    actions_html = (f'<div class="ask"><div class="ask-h">What I need from you</div>{_list(r["actions"], True)}</div>'
                    if r.get('actions') else '')

    detail = r.get('detail') or {}
    detail_html = ''
    if detail:
        detail_html = f'''<div class="divider">The detail — for whoever wants it</div>
      <p><b>What's behind:</b> {e(detail.get('behind', ''))}</p>
      <div><b>Biggest risks:</b>{_list(detail.get('risks'))}</div>
      <p><b>Forecast:</b> {e(detail.get('forecast_note', ''))}</p>'''

    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
    body{{font-family:Segoe UI,Arial,sans-serif;color:#1e293b;max-width:720px;margin:24px auto;padding:0 20px;font-size:14px;line-height:1.6}}
    h1{{font-size:20px;margin:0}} .sub{{color:#64748b;font-size:12px;margin:2px 0 16px}}
    .one{{border-left:4px solid {tone};background:{tone}14;border-radius:0 8px 8px 0;padding:12px 14px;margin-bottom:16px}}
    .one .k{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:{tone}}}
    .one .t{{font-size:16px;font-weight:600;color:{tone};margin-top:3px}}
    .tiles{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}} .tile{{flex:1;min-width:150px;background:#f1f5f9;border-radius:8px;padding:9px 12px}}
    .tl{{font-size:10px;text-transform:uppercase;letter-spacing:.4px;color:#94a3b8}} .tv{{font-size:15px;font-weight:600}} .tn{{font-size:11px;color:#64748b;margin-top:2px}}
    .status{{color:{tone};font-weight:700}}
    .band{{background:#f8fafc;border-radius:8px;padding:10px 13px;margin-bottom:10px;font-size:13px}} .band.money{{background:#fffbeb}}
    .ask{{border:1px solid #bfdbfe;background:#eff6ff;border-radius:9px;padding:11px 14px;margin:6px 0}} .ask-h{{font-weight:700;color:#1d4ed8;margin-bottom:5px}}
    .ask ol,.band ul{{margin:4px 0;padding-left:20px}} ul,ol{{margin:4px 0;padding-left:20px}}
    .divider{{text-align:center;color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin:18px 0 10px;border-top:1px solid #e2e8f0;padding-top:12px}}
    .foot{{color:#94a3b8;font-size:11px;text-align:center;margin-top:16px}}
    .chart{{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:11px 14px 8px;margin-bottom:12px}}
    .chart-h{{font-size:12px;font-weight:700;color:#334155;margin-bottom:6px}}
    .legend{{font-size:10.5px;color:#64748b;font-weight:600;display:flex;gap:14px;margin-top:2px}}
    .legend i{{display:inline-block;width:16px;height:0;border-top:2.5px solid;vertical-align:middle;margin-right:5px}}
    .recovery{{border:1px solid #bbf7d0;background:#f0fdf4;border-radius:9px;padding:11px 14px;margin-bottom:10px;font-size:13px}}
    .recovery .rh{{font-weight:700;color:#16a34a;margin-bottom:3px}} .recovery b{{color:#166534}}
    .drivers{{margin:7px 0 0;padding:0;list-style:none}}
    .drivers li{{display:flex;justify-content:space-between;font-size:12.5px;padding:4px 0;border-top:1px solid #eef2f7}}
    .drivers li:first-child{{border-top:none}} .drivers .dn{{color:#334155}} .drivers .dd{{color:#dc2626;font-weight:600}}
    .nwtag{{display:inline-block;font-size:9px;font-weight:800;color:#fff;background:#1d4ed8;border-radius:4px;padding:1px 5px;margin-left:6px;text-transform:uppercase;letter-spacing:.4px;vertical-align:middle}}
    </style></head><body>
    <h1>Manager Report — {e(r.get('project_name') or 'Project')}</h1>
    <div class="sub">Plain-English management summary · from the update of {e(r.get('data_date') or '—')}</div>
    <div class="one"><div class="k">If you read one thing</div><div class="t">{e(r.get('one_line') or '')}</div></div>
    <div class="tiles">
      <div class="tile"><div class="tl">Status</div><div class="tv status">{e(r.get('status') or '')}</div></div>
      {finish_html}{trend_html}
    </div>
    {chart_html}{money_html}{recovery_html}{fault_html}{actions_html}{detail_html}
    <div class="foot">Every figure is from your P6 update · plain English, no jargon · a management summary, not legal advice.</div>
    </body></html>'''
