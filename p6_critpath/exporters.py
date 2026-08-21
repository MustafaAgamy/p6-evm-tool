"""PDF (print HTML) and Excel exporters for the Critical Path Analyzer.

render_html builds a landscape, print-ready page from the report the client already
holds (no re-parse). Every section is wrapped in <section data-sec="KEY"> so the
preview's Report Contents picker can toggle it and the PDF re-flows. Print colours are
literal hex (the PDF renders on white), mirroring the other module exporters.
"""

_ROLE_LABEL = {'baseline': 'Baseline', 'previous': 'Previous update', 'current': 'Current update'}
_STATUS_HEX = {'good': ('#16a34a', '#eafaf0'), 'warn': ('#d97706', '#fff6e9'), 'bad': ('#dc2626', '#fdecec')}


def _e(v):
    if v is None:
        return ''
    return (str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _sd(v, suffix=' d'):
    return '—' if v is None else f"{'+' if v > 0 else ''}{v}{suffix}"


def _cpli(v):
    return 'n/a' if v is None else f"{v:.2f}"


# ── Sections ─────────────────────────────────────────────────────────────────

def _header(report):
    files = report.get('files', {})
    parts = []
    for role in ('baseline', 'previous', 'current'):
        if role in files:
            parts.append(f"{_ROLE_LABEL[role]}: <b>{_e(files[role])}</b>")
    return (f'<div class="rh"><div><h1>Critical Path Analyzer</h1>'
            f'<div class="meta">{" &nbsp;·&nbsp; ".join(parts)}</div></div></div>')


def _banner(report):
    d = report.get('dashboard', {})
    status = d.get('status', 'warn')
    hexc, bg = _STATUS_HEX.get(status, _STATUS_HEX['warn'])
    return (f'<div class="banner" style="background:{bg};border-color:{hexc}">'
            f'<span class="btag" style="background:{hexc}">{_e(d.get("status_label"))}</span>'
            f'<span class="btext">{_e(report.get("conclusion") or d.get("verdict"))}</span></div>')


def _dashboard(report):
    d = report.get('dashboard', {})
    kpi_cells = []
    for k in d.get('kpis', []):
        if k['value'] is None:
            val = 'n/a'
        elif k['key'] == 'cpli':
            val = f"{k['value']:.2f}"
        else:
            val = k['value']
        unit = ' wd' if k['key'] == 'length' else ''
        delta = '' if k.get('delta') is None else _sd(k['delta'], '')
        kpi_cells.append(f'<div class="kpi"><div class="kk">{_e(k["label"])}</div>'
                         f'<div class="kv">{val}{unit}</div><div class="kd">{delta}</div></div>')
    factors = ''.join(f'<li>{_e(f)}</li>' for f in d.get('factors', []))
    return (f'<div class="dash"><div class="health"><div class="hgauge">{_cpli(d.get("cpli"))}<span>CPLI</span></div>'
            f'<div><div class="htitle">Critical Path Health</div>'
            f'<div class="hverdict">{_e(d.get("verdict"))}</div><ul class="hfactors">{factors}</ul></div></div>'
            f'<div class="kpis">{"".join(kpi_cells)}</div></div>')


def _lane(lane):
    role = lane.get('role')
    ms = lane.get('milestone') or {}
    fin = ms.get('baseline_finish') if role == 'baseline' else ms.get('expected_finish')
    boxes = [f'<div class="msbox"><div class="msflag">◆ Milestone</div><div class="mst">{_e(ms.get("name"))}</div>'
             f'<div class="msr"><span>{"BL Finish" if role == "baseline" else "Exp Finish"}</span><b>{_e(fin)}</b></div>'
             f'<div class="msr"><span>Delay</span><b>{_sd(ms.get("slip_days"))}</b></div></div>']
    for b in lane.get('boxes', []):
        st = b.get('state', 'stayed')
        cls = {'new': 'bnew', 'left': 'bleft', 'done': 'bdone'}.get(st, '')
        flag = ('<div class="bflag bfnew">NEW ON PATH</div>' if st == 'new'
                else '<div class="bflag bfleft">LEFT PATH</div>' if st == 'left' else '')
        if st == 'left':
            tf = '—' if b.get('driver_tf') is None else _sd(b.get('driver_tf'), ' wd')
            last = f'<span class="bk">Float now</span><span class="bv" style="color:#16a34a">{tf}</span>'
        else:
            last = f'<span class="bk">Slip</span><span class="bv">{_sd(b.get("slip_days"))}</span>'
        boxes.append(
            f'<div class="arw">▸</div><div class="box {cls}">{flag}<div class="bt">{_e(b.get("name"))}</div>'
            f'<div class="bcrumb">{_e(b.get("crumb"))}</div>'
            f'<div class="brow"><span class="bk">Actual</span><span class="bv">{round(b.get("pct") or 0)}%</span></div>'
            f'<div class="brow"><span class="bk">Exp Finish</span><span class="bv">{_e(b.get("exp_finish"))}</span></div>'
            f'<div class="brow last">{last}</div></div>')
    return (f'<div class="lane"><div class="lanehdr"><span class="lanetag lt-{role}">{_e(_ROLE_LABEL.get(role))}</span>'
            f'<span class="lanesub">{_e(lane.get("sub"))}</span></div><div class="chain">{"".join(boxes)}</div></div>')


def _lanes(report):
    lanes = report.get('lanes', [])
    if not any(l.get('boxes') for l in lanes):
        return '<div class="note">No governing critical path was found in these schedules.</div>'
    legend = ('<div class="cplegend"><i style="background:#fdecec;border:2px solid #dc2626"></i>New on critical path '
              '<i style="background:#f4f4f5;border:1px dashed #94a3b8"></i>Left the path '
              '<i style="background:#fff;border:1px solid #e2e8f0"></i>Stayed '
              '<i style="background:#fff;border:1px solid #16a34a"></i>Complete</div>')
    return ''.join(_lane(l) for l in lanes) + legend


def _census(report):
    c = report.get('census', {})
    roles = report.get('roles', [])
    has = lambda r: r in roles
    cur, prev, bl = c.get('current', {}), c.get('previous', {}), c.get('baseline', {})

    def cell(r, txt):
        return f'<td class="num">{txt}</td>' if has(r) else ''

    def cnt(o, n, p):
        return '—' if o.get(n) is None else f"{o[n]} · <b>{o[p]}%</b>"

    def dvar(a, b, unit, bad_up):
        if a is None or b is None:
            return '<td class="num">—</td>'
        dd = round(a - b, 2)
        col = '#dc2626' if (dd > 0) == bad_up and dd != 0 else ('#16a34a' if dd != 0 else '#94a3b8')
        return f'<td class="num" style="color:{col};font-weight:700">{"+" if dd > 0 else ""}{dd}{unit}</td>'

    rows = [
        ('Critical activities (TF ≤ 0)', lambda o: cnt(o, 'critical', 'critical_pct'), 'critical_pct', ' pts', True),
        ('Near-critical (0 &lt; TF &lt; 10 wd)', lambda o: cnt(o, 'near', 'near_pct'), 'near_pct', ' pts', True),
        ('Critical path length (remaining, wd)', lambda o: '—' if o.get('path_length_wd') is None else f"{o['path_length_wd']} wd", 'path_length_wd', ' wd', True),
        ('Total float · finish (wd)', lambda o: '—' if o.get('total_float_wd') is None else f"{o['total_float_wd']} wd", 'total_float_wd', ' wd', False),
        ('CPLI · project finish', lambda o: _cpli(o.get('cpli')), 'cpli', '', False),
    ]
    head = ('<tr><th>Measure</th>' + ('<th class="num">Baseline</th>' if has('baseline') else '')
            + ('<th class="num">Previous</th>' if has('previous') else '')
            + ('<th class="num">Current</th>' if has('current') else '')
            + ('<th class="num">Δ period</th>' if has('previous') else '')
            + ('<th class="num">Δ baseline</th>' if has('baseline') else '') + '</tr>')
    body = ''
    for label, get, key, unit, bad_up in rows:
        body += ('<tr><td>' + label + '</td>'
                 + cell('baseline', get(bl)) + cell('previous', get(prev)) + cell('current', get(cur))
                 + (dvar(cur.get(key), prev.get(key), unit, bad_up) if has('previous') else '')
                 + (dvar(cur.get(key), bl.get(key), unit, bad_up) if has('baseline') else '') + '</tr>')
    return f'<table class="t"><thead>{head}</thead><tbody>{body}</tbody></table>'


def _milestones(report):
    rows = report.get('milestones', [])
    roles = report.get('roles', [])
    has = lambda r: r in roles
    if not rows:
        return '<div class="note">No finish milestones found.</div>'

    def slip(v):
        if v is None:
            return '—'
        col = '#dc2626' if v > 0 else '#16a34a' if v < 0 else '#94a3b8'
        return f'<span style="color:{col};font-weight:700">{"+" if v > 0 else ""}{v} d</span>'

    def cplic(v):
        if v is None:
            return 'n/a'
        col = '#16a34a' if v >= 1.0 else '#d97706' if v >= 0.95 else '#dc2626'
        return f'<span style="color:{col};font-weight:700">{v:.2f}</span>'

    head = ('<tr><th>Milestone</th>' + ('<th class="num">Baseline</th>' if has('baseline') else '')
            + ('<th class="num">Previous</th>' if has('previous') else '')
            + ('<th class="num">Current</th>' if has('current') else '')
            + '<th class="num">vs Baseline</th>' + ('<th class="num">This period</th>' if has('previous') else '')
            + '<th class="num">CPLI</th><th class="num">Crit/Near fronts</th></tr>')
    body = ''
    for m in rows:
        f = m.get('finishes', {})
        fronts = '—' if m.get('crit_fronts') is None else f"{m['crit_fronts']} / {m['near_fronts']}"
        body += ('<tr' + (' class="gov"' if m.get('is_governing') else '') + '><td>'
                 + ('◆ ' if m.get('is_governing') else '') + _e(m.get('name')) + '</td>'
                 + (f'<td class="num">{_e(f.get("baseline"))}</td>' if has('baseline') else '')
                 + (f'<td class="num">{_e(f.get("previous"))}</td>' if has('previous') else '')
                 + (f'<td class="num">{_e(f.get("current"))}</td>' if has('current') else '')
                 + f'<td class="num">{slip(m.get("var_vs_baseline_d"))}</td>'
                 + (f'<td class="num">{slip(m.get("var_this_period_d"))}</td>' if has('previous') else '')
                 + f'<td class="num">{cplic(m.get("cpli"))}</td>'
                 + f'<td class="num">{fronts}</td></tr>')
    return f'<table class="t"><thead>{head}</thead><tbody>{body}</tbody></table>'


def _migration(report):
    m = report.get('float_migration')
    if not m:
        return '<div class="note">Load a previous update or a baseline to see how float moved.</div>'
    c = m.get('counts', {})
    base = 'baseline' if report.get('float_migration_base') == 'baseline' else 'last period'
    cards = [('Near → CRITICAL', c.get('near_to_crit', 0), '#dc2626', 'worsened'),
             ('Safe → near', c.get('safe_to_near', 0), '#d97706', 'eroding'),
             ('Critical → recovered', c.get('crit_to_recovered', 0), '#16a34a', 'improved'),
             ('Held critical', c.get('held_crit', 0), '#94a3b8', 'unchanged')]
    cells = ''.join(f'<div class="band"><div class="bandl">{_e(lbl)}</div>'
                    f'<div class="bandv" style="color:{col}">{n}</div>'
                    f'<div class="bandt" style="color:{col}">{tag}</div></div>' for lbl, n, col, tag in cards)
    toward = (c.get('near_to_crit', 0) or 0) + (c.get('safe_to_near', 0) or 0)
    return (f'<div class="bands">{cells}</div>'
            f'<div class="note">{toward} activities lost float toward the critical path vs {base}. Matched by activity ID.</div>')


def _recommendation(report):
    rec = ''.join(f'<li>{_e(r)}</li>' for r in report.get('recommendation', []))
    return (f'<div class="effect">{_e(report.get("effect"))}</div>'
            f'<div class="recoh">Recommendation</div><ol class="reco">{rec}</ol>')


def render_html(report, sections=None):
    secs = [
        ('verdict', '', _banner(report), False),
        ('dashboard', 'Execution dashboard', _dashboard(report), False),
        ('driving_path', 'Driving path — schedule by schedule', _lanes(report), True),
        ('census', 'Critical & near-critical census', _census(report), False),
        ('milestones', 'Every milestone · finish comparison & path health', _milestones(report), False),
        ('float_migration', 'Float migration', _migration(report), False),
        ('recommendation', 'Effect on completion & recommendation', _recommendation(report), False),
    ]
    keys = set(sections) if sections else None
    body = [_header(report)]
    for key, title, html, planner in secs:
        if keys is not None and key not in keys:
            continue
        t = f'<h2>{_e(title)}</h2>' if title else ''
        body.append(f'<section data-sec="{key}"{" class=pagebreak" if planner else ""}>{t}{html}</section>')
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 11mm; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; color: #1e293b; font-size: 12px; margin: 0; }}
      h1 {{ font-size: 18px; margin: 0; }} h2 {{ font-size: 13px; margin: 16px 0 8px; color: #1d4ed8; }}
      section.pagebreak {{ page-break-before: always; }}
      .rh {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; }}
      .meta {{ color: #64748b; font-size: 11px; margin-top: 3px; }}
      .banner {{ display: flex; align-items: center; gap: 11px; border: 1px solid; border-radius: 9px; padding: 10px 14px; margin-top: 10px; }}
      .btag {{ color: #fff; font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .5px; padding: 3px 9px; border-radius: 5px; }}
      .btext {{ font-size: 13px; font-weight: 600; }}
      .dash {{ display: flex; gap: 12px; }}
      .health {{ flex: 1; display: flex; gap: 12px; align-items: center; border: 1px solid #e2e8f0; border-left: 4px solid #dc2626; border-radius: 10px; padding: 10px 14px; }}
      .hgauge {{ flex: none; width: 74px; height: 74px; border-radius: 50%; border: 6px solid #e2e8f0; display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 19px; font-weight: 800; }}
      .hgauge span {{ font-size: 9px; font-weight: 600; color: #94a3b8; }}
      .htitle {{ font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .4px; color: #64748b; }}
      .hverdict {{ font-size: 12px; font-weight: 700; margin: 3px 0 5px; }}
      .hfactors {{ margin: 0; padding-left: 15px; font-size: 10.5px; color: #64748b; line-height: 1.5; }}
      .kpis {{ flex: 1; display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }}
      .kpi {{ border: 1px solid #e2e8f0; border-radius: 9px; padding: 8px 11px; }}
      .kk {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: .3px; color: #94a3b8; font-weight: 700; }}
      .kv {{ font-size: 19px; font-weight: 800; margin-top: 2px; }}
      .kd {{ font-size: 11px; font-weight: 700; color: #64748b; margin-top: 2px; }}
      .lane {{ margin-bottom: 12px; }} .lanehdr {{ display: flex; gap: 9px; align-items: center; margin-bottom: 6px; }}
      .lanetag {{ font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .5px; padding: 3px 9px; border-radius: 6px; }}
      .lt-baseline {{ background: #eef2f7; color: #475569; }} .lt-previous {{ background: #fff6e9; color: #b45309; }} .lt-current {{ background: #eff6ff; color: #1d4ed8; }}
      .lanesub {{ color: #64748b; font-size: 10.5px; }}
      .chain {{ display: flex; align-items: stretch; flex-wrap: wrap; gap: 5px; }}
      .arw {{ display: flex; align-items: center; color: #94a3b8; font-weight: 800; font-size: 15px; }}
      .msbox {{ flex: none; width: 150px; border: 2px solid #1d4ed8; border-radius: 10px; padding: 8px 10px; background: #eff6ff; }}
      .msflag {{ font-size: 9px; text-transform: uppercase; color: #1d4ed8; margin-bottom: 4px; }}
      .mst {{ font-size: 11.5px; font-weight: 800; color: #1d4ed8; margin-bottom: 5px; }}
      .msr {{ display: flex; justify-content: space-between; font-size: 10.5px; margin: 2px 0; }} .msr span {{ color: #94a3b8; }}
      .box {{ flex: none; width: 150px; border: 1px solid #e2e8f0; border-radius: 9px; padding: 7px 9px; position: relative; }}
      .box.bdone {{ border-color: #16a34a; }}
      .box.bnew {{ border: 2px solid #dc2626; background: #fdf4f4; }}
      .box.bleft {{ border: 1px dashed #cbd5e1; background: #f6f7f9; }}
      .bflag {{ position: absolute; top: -8px; left: 8px; color: #fff; font-size: 8px; font-weight: 800; padding: 1px 6px; border-radius: 4px; }}
      .bfnew {{ background: #dc2626; }} .bfleft {{ background: #94a3b8; }}
      .bt {{ font-size: 11px; font-weight: 700; }} .bcrumb {{ font-size: 8.5px; color: #94a3b8; margin: 2px 0 6px; }}
      .brow {{ display: flex; justify-content: space-between; font-size: 10px; margin: 2px 0; }}
      .brow.last {{ border-top: 1px dashed #e2e8f0; padding-top: 3px; margin-top: 3px; }}
      .bk {{ color: #94a3b8; }} .bv {{ font-weight: 700; }}
      .cplegend {{ font-size: 10px; color: #64748b; margin-top: 6px; }}
      .cplegend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; vertical-align: middle; margin: 0 4px 0 12px; }}
      table.t {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
      table.t th, table.t td {{ padding: 6px 9px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
      table.t th {{ font-size: 10px; text-transform: uppercase; letter-spacing: .3px; color: #94a3b8; }}
      table.t td.num, table.t th.num {{ text-align: right; }}
      table.t tr.gov td {{ font-weight: 800; }}
      .bands {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
      .band {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 9px; text-align: center; }}
      .bandl {{ font-size: 10px; color: #64748b; font-weight: 700; }} .bandv {{ font-size: 18px; font-weight: 800; margin-top: 3px; }} .bandt {{ font-size: 10px; font-weight: 700; margin-top: 2px; }}
      .effect {{ font-size: 12px; line-height: 1.5; background: #f8fafc; border-left: 3px solid #1d4ed8; border-radius: 0 8px 8px 0; padding: 10px 13px; }}
      .recoh {{ font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .4px; color: #1d4ed8; margin: 12px 0 5px; }}
      .reco {{ margin: 0; padding-left: 18px; font-size: 11.5px; line-height: 1.6; }}
      .note {{ color: #64748b; font-size: 11px; margin-top: 8px; }}
    </style></head><body>{"".join(body)}</body></html>'''


# ── Excel ────────────────────────────────────────────────────────────────────

def to_excel(report, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    bold = Font(bold=True)
    roles = report.get('roles', [])
    c = report.get('census', {})

    ws = wb.active
    ws.title = 'Census'
    ws.append(['Measure'] + [_ROLE_LABEL[r] for r in roles])
    for cell in ws[1]:
        cell.font = bold

    def crow(label, key, pct=None):
        row = [label]
        for r in roles:
            o = c.get(r, {})
            if pct is None:
                row.append(o.get(key))
            else:
                row.append(f"{o.get(key)} ({o.get(pct)}%)" if o.get(key) is not None else None)
        ws.append(row)

    crow('Critical activities', 'critical', 'critical_pct')
    crow('Near-critical', 'near', 'near_pct')
    crow('Critical path length (wd)', 'path_length_wd')
    crow('Total float · finish (wd)', 'total_float_wd')
    crow('CPLI', 'cpli')

    wm = wb.create_sheet('Milestones')
    wm.append(['Milestone', 'Governing'] + [_ROLE_LABEL[r] for r in roles]
              + ['vs Baseline (d)', 'This period (d)', 'CPLI', 'Crit fronts', 'Near fronts'])
    for cell in wm[1]:
        cell.font = bold
    for m in report.get('milestones', []):
        f = m.get('finishes', {})
        wm.append([m.get('name'), 'Yes' if m.get('is_governing') else ''] + [f.get(r) for r in roles]
                  + [m.get('var_vs_baseline_d'), m.get('var_this_period_d'), m.get('cpli'),
                     m.get('crit_fronts'), m.get('near_fronts')])

    wp = wb.create_sheet('Driving path (current)')
    wp.append(['Work front', 'State', 'Actual %', 'Exp finish', 'Slip (d)', 'Float now (wd)'])
    for cell in wp[1]:
        cell.font = bold
    cur_lane = next((l for l in report.get('lanes', []) if l.get('role') == 'current'), None)
    if cur_lane:
        for b in cur_lane.get('boxes', []):
            wp.append([b.get('name'), b.get('state'), round(b.get('pct') or 0), b.get('exp_finish'),
                       b.get('slip_days'), b.get('driver_tf') if b.get('state') == 'left' else None])

    mig = report.get('float_migration')
    if mig:
        wf = wb.create_sheet('Float migration')
        wf.append(['Move', 'Count'])
        wf['A1'].font = bold
        wf['B1'].font = bold
        cc = mig.get('counts', {})
        for lbl, key in [('Near → Critical', 'near_to_crit'), ('Safe → near', 'safe_to_near'),
                         ('Critical → recovered', 'crit_to_recovered'), ('Held critical', 'held_crit')]:
            wf.append([lbl, cc.get(key, 0)])

    wb.save(path)
    return path
