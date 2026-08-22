"""Constructability Review exporters — PDF (HTML → Chrome) and Excel.

`render_html(report)` lays out the Execution-Readiness dashboard + the detail
tables (illogical relationships, missing activities, WBS review) as a print-ready
A4 landscape page. `findings_excel(report)` flattens every finding into one
filterable sheet. Nothing here computes a number — it renders what the engine
produced.
"""
import html

_BAND_HEX = {'green': '#16a34a', 'amber': '#d97706', 'orange': '#ea580c', 'red': '#dc2626'}


def _e(v):
    return html.escape(str(v if v is not None else ''))


def _hex(band):
    return _BAND_HEX.get(band, '#94a3b8')


def _links(lst):
    if not lst:
        return '—'
    out = []
    for l in lst:
        rel = f" [{l.get('rel')}]" if l.get('rel') else ''
        tag = {'add': 'ADD ', 'remove': 'REMOVE ', 'change': '→FS '}.get(l.get('kind'), '')
        out.append(f"{tag}{l.get('id', '')} {l.get('name', '')}{rel}".strip())
    return ' / '.join(out)


# ── Excel: one flat findings sheet ──────────────────────────────────────────

_HEADERS = ['Type', 'ID / Suggested ID', 'Activity / Item', 'WBS',
            'Issue / Why', 'Suggested fix', 'Impact / Severity', 'Source']


def findings_excel(report):
    rows = []
    for r in report.get('illogical', []) or []:
        rows.append(['Illogical link', r.get('activity_id', ''), r.get('activity_name', ''),
                     r.get('wbs_path', ''), r.get('why', ''),
                     _links(r.get('suggested_preds')), r.get('impact', ''), r.get('source', '')])
    for m in report.get('missing', []) or []:
        wbs = (m.get('wbs', '') + (' (new branch)' if m.get('new_wbs') else ''))
        fix = f"pred {_links(m.get('preds'))} · succ {_links(m.get('succs'))}"
        rows.append(['Missing activity', m.get('suggested_id', ''), m.get('name', ''),
                     wbs, m.get('why', ''), fix, 'Scope gap', m.get('basis', '')])
    for w in report.get('missing_wbs', []) or []:
        rows.append(['Missing WBS', '', w.get('name', ''), w.get('name', ''),
                     w.get('why', ''), 'Add standard WBS branch', 'Structure', ''])
    return _HEADERS, rows


# ── PDF: HTML → Chrome ──────────────────────────────────────────────────────

def _band_legend(score):
    bands = [(50, '#dc2626', 'Major', '0–49'), (20, '#ea580c', 'Significant', '50–69'),
             (15, '#d97706', 'Minor', '70–84'), (15, '#16a34a', 'Ready', '85–100')]
    segs = ''.join(f'<div class="lseg" style="width:{w}%;background:{c}"><b>{t}</b><span>{r}</span></div>'
                   for w, c, t, r in bands)
    pos = max(0, min(100, score))
    return (f'<div class="legwrap"><div class="lmark" style="left:{pos}%">'
            f'<div class="bub">Score {score}</div><div class="arw"></div></div>'
            f'<div class="lbar">{segs}</div></div>')


def _tiles(report):
    d = report.get('dashboard', {}) or {}
    def t(v, lbl, sub):
        return f'<div class="tile"><div class="tv">{_e(v)}</div><div class="tl">{_e(lbl)}</div><div class="ts">{_e(sub)}</div></div>'
    return ('<div class="tiles">'
            + t(f"{d.get('illogical_count', 0)} ({d.get('illogical_pct', 0)}%)", 'Illogical links', f"of {d.get('total_relationships', 0)}")
            + t(f"{d.get('missing_count', 0)} ({d.get('missing_pct', 0)}%)", 'Missing activities', 'vs standard')
            + t(d.get('missing_wbs', 0), 'Missing WBS', 'standard branches')
            + t('Yes' if d.get('critical_affected') else 'No', 'Critical path', f"{d.get('critical_count', 0)} on CP")
            + t(f"{d.get('coverage', 0)}%", 'Scope coverage', 'std activities present')
            + '</div>')


def _dims(s):
    def bar(lbl, v):
        return (f'<div class="dim"><div class="dh"><span>{lbl}</span><b>{v}/100</b></div>'
                f'<div class="track"><i style="width:{max(0, min(100, v))}%"></i></div></div>')
    return ('<div class="dims">' + bar('Sequence logic (45%)', s.get('logic', 0))
            + bar('Scope completeness (45%)', s.get('completeness', 0))
            + bar('Structure &amp; load (10%)', s.get('structure', 0)) + '</div>')


def _issues_by_wbs(report):
    lst = report.get('issues_by_wbs', []) or []
    if not lst:
        return '<p class="note">No phase concentrations.</p>'
    mx = max((x.get('count', 0) for x in lst), default=1) or 1
    return '<div class="wbsbars">' + ''.join(
        f'<div class="wbsrow"><span class="nm">{_e(x.get("name"))}</span>'
        f'<span class="bar"><i style="width:{round(100 * x.get("count", 0) / mx)}%"></i></span>'
        f'<span class="c">{_e(x.get("count"))}</span></div>' for x in lst) + '</div>'


def _priority(report):
    lst = report.get('priority_fixes', []) or []
    if not lst:
        return '<p class="note">Nothing critical to fix first.</p>'
    body = ''.join(
        f'<tr><td class="rk">{i + 1}</td><td><b>{_e(p.get("title"))}</b><div class="pd">{_e(p.get("detail"))}</div></td>'
        f'<td class="sev">{_e(p.get("severity"))}</td></tr>' for i, p in enumerate(lst))
    return f'<table class="data prio"><tbody>{body}</tbody></table>'


def _illogical_table(report):
    rows = report.get('illogical', []) or []
    if not rows:
        return '<p class="note">No illogical relationships flagged.</p>'
    rank = {'Critical': 0, 'Near-critical': 1}
    rows = sorted(rows, key=lambda r: rank.get(r.get('impact'), 2))   # major first
    body = ''.join(
        f'<tr><td class="sn">{i + 1}</td><td class="mono">{_e(r.get("activity_id"))}</td><td>{_e(r.get("activity_name"))}</td>'
        f'<td class="mut">{_e(r.get("wbs_path"))}</td>'
        f'<td class="mono">{_e(_links(r.get("current_preds")))}</td>'
        f'<td class="mono">{_e(_links(r.get("current_succs")))}</td>'
        f'<td>{_e(r.get("why"))}</td>'
        f'<td class="mono chg">{_e(_links(r.get("suggested_preds")))}</td>'
        f'<td class="mono chg">{_e(_links(r.get("suggested_succs")))}</td>'
        f'<td>{_e(r.get("impact"))}</td></tr>' for i, r in enumerate(rows))
    return ('<table class="data"><thead><tr><th>#</th><th>Activity ID</th><th>Activity</th><th>WBS path</th>'
            '<th>Current preds</th><th>Current succs</th><th>Why it\'s illogical</th>'
            '<th>Suggested preds</th><th>Suggested succs</th><th>Impact</th></tr></thead><tbody>'
            + body + '</tbody></table>')


def _missing_table(report):
    rows = report.get('missing', []) or []
    if not rows:
        return '<p class="note">No missing activities against the standard.</p>'
    body = ''.join(
        f'<tr><td class="mono">{_e(r.get("suggested_id"))}</td><td>{_e(r.get("name"))}</td>'
        f'<td>{("+ new " if r.get("new_wbs") else "") + _e(r.get("wbs"))}</td>'
        f'<td class="mono">{_e(_links(r.get("preds")))}</td>'
        f'<td class="mono">{_e(_links(r.get("succs")))}</td>'
        f'<td>{_e(r.get("why"))}</td></tr>' for r in rows)
    return ('<table class="data"><thead><tr><th>Suggested ID</th><th>Activity</th><th>Where it belongs (WBS)</th>'
            '<th>Pred</th><th>Succ</th><th>Why it\'s normally needed</th></tr></thead><tbody>'
            + body + '</tbody></table>')


def _wbs_review(report):
    rows = report.get('wbs_review', []) or []
    if not rows:
        return ''
    items = ''.join(
        f'<div class="wbsr {("miss" if w.get("status") == "missing" else "")}">'
        f'{"⚠" if w.get("status") == "missing" else "✓"} {_e(w.get("name"))}'
        f'{(" — " + _e(w.get("note"))) if w.get("note") else ""}</div>' for w in rows)
    return f'<div class="wbsrev">{items}</div>'


def render_html(report):
    s = report.get('score') or {}
    v = report.get('verdict') or {}
    hex_ = _hex(s.get('band'))
    proj = report.get('projected')
    conf = report.get('confidence') or {}
    proj_html = (f'<div class="proj">What-if: correcting the flagged logic would raise the score to '
                 f'~<b>{proj.get("overall")}</b> ({_e(proj.get("band_label"))}) — {_e(proj.get("basis"))}.</div>'
                 if proj else '')
    conf_html = ('Type chosen manually' if conf.get('forced')
                 else f"Detection confidence: {_e(conf.get('level'))} "
                      f"({conf.get('hits')}/{conf.get('signatures')} keywords)")
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 landscape; margin: 11mm; }}
      * {{ box-sizing: border-box; }}
      body {{ font-family: system-ui, -apple-system, Arial, sans-serif; color: #1e293b; font-size: 11.5px; margin: 0; }}
      h1 {{ font-size: 19px; margin: 0 0 2px; }}
      h2 {{ font-size: 13px; margin: 15px 0 7px; border-bottom: 2px solid #1e2d40; padding-bottom: 3px; }}
      .sub {{ color: #64748b; font-size: 11px; margin-bottom: 10px; }}
      .verdict {{ display: flex; gap: 12px; align-items: center; border: 1px solid {hex_}55; background: {hex_}12; border-radius: 9px; padding: 10px 14px; margin-bottom: 12px; }}
      .verdict .vt {{ font-size: 15px; font-weight: 800; color: {hex_}; }}
      .verdict .vd {{ font-size: 11px; color: #475569; margin-top: 2px; }}
      .verdict .vr {{ margin-left: auto; text-align: right; font-size: 11px; }}
      .verdict .vr b {{ font-size: 13px; }}
      .hero {{ display: flex; gap: 16px; align-items: center; margin-bottom: 10px; }}
      .scorebox {{ text-align: center; border: 1px solid #e2e8f0; border-radius: 9px; padding: 10px 18px; min-width: 130px; }}
      .scorebox .n {{ font-size: 40px; font-weight: 800; color: {hex_}; line-height: 1; }}
      .scorebox .b {{ display: inline-block; margin-top: 4px; font-size: 11px; font-weight: 700; padding: 2px 10px; border-radius: 20px; background: {hex_}22; color: {hex_}; }}
      .scorebox .sl {{ font-size: 8.5px; text-transform: uppercase; letter-spacing: .5px; color: #94a3b8; margin-top: 5px; }}
      .dims {{ flex: 1; }}
      .dim {{ margin-bottom: 7px; }} .dim .dh {{ display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 3px; }}
      .track {{ height: 8px; background: #eef2f7; border-radius: 5px; overflow: hidden; }} .track i {{ display: block; height: 100%; background: {hex_}; }}
      .legwrap {{ position: relative; padding-top: 20px; margin: 6px 0 4px; }}
      .lbar {{ display: flex; height: 26px; border-radius: 6px; overflow: hidden; }}
      .lseg {{ display: flex; flex-direction: column; align-items: center; justify-content: center; color: #fff; font-size: 9px; line-height: 1.1; }}
      .lseg b {{ font-size: 10px; }}
      .lmark {{ position: absolute; top: 0; transform: translateX(-50%); text-align: center; }}
      .lmark .bub {{ background: #1e293b; color: #fff; font-size: 10px; font-weight: 700; padding: 1px 7px; border-radius: 5px; white-space: nowrap; }}
      .lmark .arw {{ width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #1e293b; margin: 0 auto; }}
      .proj {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 7px; padding: 7px 11px; font-size: 11px; margin: 8px 0; }}
      .tiles {{ display: flex; gap: 8px; margin: 8px 0; }}
      .tile {{ flex: 1; border: 1px solid #e2e8f0; border-radius: 8px; padding: 7px 10px; }}
      .tile .tv {{ font-size: 17px; font-weight: 800; }} .tile .tl {{ font-size: 10px; font-weight: 700; margin-top: 2px; }} .tile .ts {{ font-size: 9px; color: #64748b; }}
      .two {{ display: flex; gap: 14px; }} .two > div {{ flex: 1; }}
      .wbsrow {{ display: flex; align-items: center; gap: 8px; font-size: 11px; margin-bottom: 5px; }}
      .wbsrow .nm {{ width: 150px; }} .wbsrow .bar {{ flex: 1; height: 13px; background: #eef2f7; border-radius: 4px; overflow: hidden; }}
      .wbsrow .bar i {{ display: block; height: 100%; background: linear-gradient(90deg,#dc2626,#f59e0b); }} .wbsrow .c {{ width: 22px; text-align: right; font-weight: 700; }}
      table.data {{ width: 100%; border-collapse: collapse; font-size: 9.5px; margin: 5px 0; }}
      table.data th {{ background: #26517d; color: #fff; text-align: left; padding: 4px 6px; font-weight: 600; }}
      table.data td {{ border-bottom: 1px solid #e2e8f0; padding: 3px 6px; vertical-align: top; }}
      .mono {{ font-family: Consolas, monospace; }} .mut {{ color: #64748b; }} .chg {{ color: #b91c1c; }}
      .sn {{ text-align: center; color: #64748b; font-weight: 700; width: 16px; }}
      .prio td {{ padding: 5px 6px; }} .prio .rk {{ width: 20px; font-weight: 800; color: #dc2626; }} .prio .pd {{ color: #64748b; font-size: 9px; }} .prio .sev {{ white-space: nowrap; font-weight: 700; }}
      .wbsrev {{ font-size: 10.5px; }} .wbsr {{ padding: 2px 0; }} .wbsr.miss {{ color: #b45309; }}
      .note {{ color: #64748b; font-style: italic; }}
      .foot {{ margin-top: 14px; font-size: 9.5px; color: #94a3b8; font-style: italic; border-top: 1px solid #e2e8f0; padding-top: 6px; }}
    </style></head><body>
      <h1>Constructability Review — Execution Readiness</h1>
      <div class="sub">{_e(report.get('project_type'))} · {conf_html} · Rule + Knowledge Base · offline</div>
      <div class="verdict"><div><div class="vt">{_e(v.get('title'))}</div><div class="vd">{_e(v.get('detail') or v.get('text'))}</div></div>
        <div class="vr"><b>{_e(report.get('project_type'))}</b></div></div>
      <div class="hero">
        <div class="scorebox"><div class="n">{_e(s.get('overall'))}</div><div class="b">{_e(s.get('band_label'))}</div><div class="sl">Constructability Score</div></div>
        {_dims(s)}
      </div>
      {_band_legend(s.get('overall', 0))}
      {proj_html}
      {_tiles(report)}
      <h2>Issues by WBS phase</h2>
      {_issues_by_wbs(report)}
      <h2>Illogical relationships &amp; better logic</h2>
      {_illogical_table(report)}
      <h2>Missing activities</h2>
      {_missing_table(report)}
      <h2>WBS review</h2>
      {_wbs_review(report)}
      <div class="foot">{_e(report.get('conclusion'))}</div>
    </body></html>'''
