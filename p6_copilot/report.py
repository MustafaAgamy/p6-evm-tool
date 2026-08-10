"""The Manager Report — a plain-English executive one-pager built from the update's analysis,
for a manager with no Primavera / project-control background. Manager-first order: the one
line, then finish-date-vs-promise and money, who it's coming from, what the manager must
decide — the how/why detail sits at the bottom. Every figure comes from the schedule; time
is spoken in weeks/months, never "working days"; no jargon.
"""
import html as _html


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
    fault_html = f'<div class="band"><b>Where it\'s coming from:</b> {e(r["fault"])}</div>' if r.get('fault') else ''
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
    </style></head><body>
    <h1>Manager Report — {e(r.get('project_name') or 'Project')}</h1>
    <div class="sub">Plain-English management summary · from the update of {e(r.get('data_date') or '—')}</div>
    <div class="one"><div class="k">If you read one thing</div><div class="t">{e(r.get('one_line') or '')}</div></div>
    <div class="tiles">
      <div class="tile"><div class="tl">Status</div><div class="tv status">{e(r.get('status') or '')}</div></div>
      {finish_html}{trend_html}
    </div>
    {money_html}{fault_html}{actions_html}{detail_html}
    <div class="foot">Every figure is from your P6 update · plain English, no jargon · a management summary, not legal advice.</div>
    </body></html>'''
