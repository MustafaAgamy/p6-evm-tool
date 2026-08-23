"""Redesigned Float Analysis report — a one-page management dashboard.

Renders from the module result's `mgmt` block (see modules/float_management.py):
Float Health gauge + DCMA legend, Schedule Statistics, Construction Float
Indicators, an all-WBS Float Distribution table, and an Executive Conclusion.
No score/grade badge and no detailed activity table (that lives in Excel).

Dispatched from report.render_module_report when module == 'float'. Rendered to
HTML here, then to PDF by the caller (Chrome headless).
"""
import html as _html

_RED, _AMBER, _GREEN = '#c0392b', '#e07b1a', '#2e8b57'


def _esc(v):
    return _html.escape('' if v is None else str(v))


def _num(v):
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return _esc(v)


def _wd(v):
    try:
        return f"{float(v):g} WD"
    except (TypeError, ValueError):
        return '0 WD'


def _bar_width(pct, max_pct):
    max_pct = max_pct or 1
    return max(0, min(100, round(100.0 * (pct or 0) / max_pct)))


def _tile(k, v_html, note='', hot=False, vclass=''):
    """One KPI tile. `k`/`note` are plain text (escaped here); `v_html` is trusted markup."""
    note_html = f'<div class="n">{_esc(note)}</div>' if note else ''
    vcls = f' {vclass}' if vclass else ''
    return (f'<div class="kpi{" hot" if hot else ""}"><div class="k">{_esc(k)}</div>'
            f'<div class="v{vcls}">{v_html}</div>{note_html}</div>')


def _gauge(mgmt):
    score = mgmt.get('float_health', 0)
    color = mgmt.get('fh_color', 'red')
    high = mgmt.get('high', {}) or {}
    thr = (mgmt.get('indicators', {}) or {}).get('threshold', 44)
    hw = _bar_width(high.get('pct', 0), 25)
    return f'''
      <div class="fh">
        <div class="fh-score">
          <div class="fh-num {_esc(color)}">{_esc(score)}</div>
          <div class="fh-den">Float Health · / 100</div>
        </div>
        <div class="fh-drivers">
          <div class="fh-d">
            <div class="fh-dl">High Float &gt; {_esc(thr)} WD — construction
              <span>the score driver — 100 − this %</span></div>
            <div class="fh-bar2"><i style="width:{hw}%;background:{_RED}"></i></div>
            <div class="fh-dv">{_esc(_num(high.get("pct", 0)))}% <small>−{_esc(high.get("penalty", 0))}</small></div>
          </div>
          <div class="fh-note">Score = 100 − the construction High-Float defect above.</div>
        </div>
      </div>'''


def _legend(mgmt):
    high = mgmt.get('high', {}) or {}
    thr = (mgmt.get('indicators', {}) or {}).get('threshold', 44)
    within = _num(high.get('dcma_within_pct', 95))
    dmax = _num(high.get('dcma_max_pct', 5))
    return f'''
      <div class="scorelegend">
        <div class="sl-title">How the Float Health score is calculated <span>— Schedule Health Review linear model</span></div>
        <div class="sl-formula">Float Health = 100 − construction excess-float defect%</div>
        <div class="sl-rows">
          <div class="sl-row"><b>Defect%</b> = construction activities with total float &gt; {_esc(thr)} WD ÷ all construction activities.
            Each 1% of defect costs 1 point — here {_esc(_num(high.get("pct", 0)))}% &rarr; <b>{_esc(mgmt.get("float_health", 0))}</b>.</div>
          <div class="sl-row sl-ref"><b>DCMA reference — not the score.</b> DCMA Metric 5 benchmark: at least {within}% of activities within the float threshold (high float &lt; {dmax}%). Shown for reference; it does not set the score.</div>
        </div>
        <div class="sl-colours"><span><i class="dot g"></i>Green ≥ 85</span><span><i class="dot a"></i>Amber 60–84</span><span><i class="dot r"></i>Red &lt; 60</span></div>
      </div>'''


def _stats_tiles(mgmt):
    s = mgmt.get('stats', {}) or {}
    band = s.get('near_band', 10)
    return ''.join([
        _tile(s.get('total_label', 'Total Activities'), f"{s.get('total', 0):,}", 'task-dependent'),
        _tile('Critical Activities', str(s.get('critical', 0)), 'flagged Critical in P6'),
        _tile('Critical %', f"{_num(s.get('critical_pct', 0))}%"),
        _tile('Near-Critical Activities', str(s.get('near_critical', 0)), f'float 1–{band} working days'),
        _tile('Near-Critical %', f"{_num(s.get('near_critical_pct', 0))}%"),
    ])


def _indicator_tiles(mgmt):
    i = mgmt.get('indicators', {}) or {}
    thr = i.get('threshold', 44)
    highest = f'{_wd(i.get("highest_float", 0))}<div class="wbsline">{_esc(i.get("highest_float_wbs", ""))}</div>'
    return ''.join([
        _tile(f'Construction · Float > {thr} WD', str(i.get('constr_over', 0)),
              f"of {i.get('constr_total', 0):,} construction activities", hot=True, vclass='amber'),
        _tile(f'% of Construction > {thr} WD', f"{_num(i.get('constr_over_pct', 0))}%",
              f'threshold = {thr} working days', hot=True, vclass='amber'),
        _tile('Top WBS by Float Concentration',
              f'<span class="tilewbs">{_esc(i.get("top_wbs", "—"))}</span>',
              f"{_num(i.get('top_wbs_pct', 0))}% of its activities > {thr} WD"),
        _tile('Highest Float (single activity)', highest),
    ])


def _wbs_rows(mgmt):
    rows = []
    for r in mgmt.get('wbs', [])[:16]:
        tag = ('<span class="tag con">Constr.</span>' if r.get('is_construction')
               else '<span class="tag non">Excl.</span>')
        rows.append(
            f'<tr><td title="{_esc(r.get("wbs", ""))}">{_esc(r.get("short", ""))} {tag}</td>'
            f'<td class="num">{r.get("activities", 0)}</td>'
            f'<td class="num">{_wd(r.get("avg_float", 0))}</td>'
            f'<td class="num">{_wd(r.get("max_float", 0))}</td>'
            f'<td class="num">{r.get("over_44", 0)}</td>'
            f'<td class="num">{_num(r.get("pct", 0))}%<div class="bar"><i style="width:{_bar_width(r.get("pct", 0), 100)}%"></i></div></td></tr>')
    if not rows:
        rows.append('<tr><td colspan="6" class="empty">No activities with assessable float.</td></tr>')
    return ''.join(rows)


def _notice(name, meta, msg):
    """Clean 'no data' page — never show a zeroed dashboard as if it were a real result."""
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{_esc(name)} — {_esc(meta.get('project_name', ''))}</title>
<style>
  @page {{ margin: 18mm 14mm; }}
  body {{ font-family:'Segoe UI',Arial,sans-serif; color:#1f2a37; font-size:12px; margin:0; }}
  .head {{ border-bottom:3px solid #17457a; padding-bottom:12px; margin-bottom:18px; }}
  .kicker {{ font-size:10px; letter-spacing:2px; color:#17457a; font-weight:700; text-transform:uppercase; }}
  .title {{ font-size:24px; font-weight:800; color:#0f2440; margin:3px 0 1px; }}
  .subtitle {{ font-size:12px; color:#5b6472; }}
  .notice {{ border:1px solid #e6e0c8; border-left:4px solid #c9a227; background:#fffdf5; border-radius:8px;
             padding:18px 20px; font-size:13px; color:#5b4a1a; line-height:1.6; margin-top:24px; }}
</style></head>
<body>
  <div class="head"><div class="kicker">Schedule Health Review · Management Report</div>
    <div class="title">{_esc(name)}</div>
    <div class="subtitle">Schedule Stability &amp; Float Distribution — Management Dashboard</div></div>
  <div class="notice"><b>Float dashboard unavailable.</b><br>{_esc(msg)}</div>
</body></html>'''


def render_float_report(module_result, meta, sections=None):
    m = module_result or {}
    mgmt = m.get('mgmt') or {}
    meta = meta or {}
    name = m.get('name', 'Float Analysis')
    if not m.get('mgmt'):
        return _notice(name, meta, 'This schedule was imported before the Float dashboard was added — '
                                   're-import it to generate the management report.')
    if not (mgmt.get('stats') or {}).get('total'):
        return _notice(name, meta, 'No activities with assessable total float were found in this schedule, '
                                   'so no float indicators can be shown.')
    thr = (mgmt.get('indicators', {}) or {}).get('threshold', 44)
    conclusion = mgmt.get('conclusion') or 'No conclusion available for this schedule.'

    # Report-content picker: include only the selected sections (Preview = PDF = Print).
    want = set(sections) if sections else None

    def on(key):
        return want is None or key in want

    exec_html = f'<h2 class="sec">Executive Dashboard</h2>{_gauge(mgmt)}{_legend(mgmt)}' if on('executive') else ''
    stats_html = (f'<div class="subhd">Schedule Statistics <span>— whole schedule</span></div>'
                  f'<div class="tiles g5">{_stats_tiles(mgmt)}</div>') if on('statistics') else ''
    ind_html = (f'<div class="subhd">Float Indicators <span>— Construction scope only '
                f'(Engineering / Procurement / Design excluded)</span></div>'
                f'<div class="tiles g4">{_indicator_tiles(mgmt)}</div>'
                f'<div class="hovernote">Average Float and Maximum Float are always shown '
                f'<b>per&nbsp;WBS</b> below — never as a single project-wide figure.</div>') if on('indicators') else ''
    wbs_html = (f'<h2 class="sec">Float Distribution by WBS</h2>'
                f'<table><thead><tr><th>WBS Package</th><th class="num">Activities</th>'
                f'<th class="num">Average Float</th><th class="num">Maximum Float</th>'
                f'<th class="num">Activities &gt; {_esc(thr)} WD</th>'
                f'<th class="num" style="min-width:120px">% &gt; {_esc(thr)} WD</th></tr></thead>'
                f'<tbody>{_wbs_rows(mgmt)}</tbody></table>'
                f'<div class="hovernote">Sorted by % over threshold (highest first) · shows the last 2–3 WBS levels · '
                f'full WBS path on hover (on screen) · <span class="tag con">Constr.</span> counts toward the '
                f'Construction KPIs, <span class="tag non">Excl.</span> is shown for context only.</div>') if on('wbs') else ''
    concl_html = (f'<h2 class="sec">Executive Conclusion</h2>'
                  f'<div class="concl">{_esc(conclusion)}</div>') if on('conclusion') else ''
    body = exec_html + stats_html + ind_html + wbs_html + concl_html
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{_esc(name)} — {_esc(meta.get('project_name', ''))}</title>
<style>
  @page {{ margin: 18mm 14mm; }}
  body {{ font-family:'Segoe UI',Arial,sans-serif; color:#1f2a37; font-size:11px; margin:0; }}
  .head {{ border-bottom:3px solid #17457a; padding-bottom:12px; margin-bottom:16px; }}
  .kicker {{ font-size:10px; letter-spacing:2px; color:#17457a; font-weight:700; text-transform:uppercase; }}
  .title {{ font-size:24px; font-weight:800; color:#0f2440; margin:3px 0 1px; }}
  .subtitle {{ font-size:12px; color:#5b6472; }}
  .meta {{ display:flex; flex-wrap:wrap; gap:3px 26px; margin-top:10px; font-size:11px; }}
  .meta span {{ color:#8a93a0; }}
  h2.sec {{ font-size:12px; text-transform:uppercase; letter-spacing:1px; color:#17457a;
            border-bottom:1px solid #dbe1e8; padding-bottom:4px; margin:20px 0 10px; }}
  .subhd {{ font-size:10.5px; text-transform:uppercase; letter-spacing:.7px; color:#8a93a0; font-weight:700; margin:14px 0 7px; }}
  .subhd span {{ text-transform:none; font-weight:400; color:#a2abb6; }}
  .tiles {{ display:grid; gap:9px; }}
  .g5 {{ grid-template-columns:repeat(5,1fr); }} .g4 {{ grid-template-columns:repeat(4,1fr); }}
  .kpi {{ border:1px solid #e8ecf1; border-radius:8px; padding:11px 12px; background:#fafbfc; }}
  .kpi.hot {{ border-color:#f0c9a8; background:#fff8f1; }}
  .kpi .k {{ font-size:9px; text-transform:uppercase; letter-spacing:.5px; color:#8a93a0; font-weight:700; line-height:1.3; }}
  .kpi .v {{ font-size:22px; font-weight:800; margin-top:3px; color:#0f2440; }}
  .kpi .v.amber {{ color:#c0651a; }}
  .kpi .v .tilewbs {{ font-size:14px; line-height:1.2; display:inline-block; }}
  .kpi .v .wbsline {{ font-size:12px; font-weight:700; color:#31414f; margin-top:2px; }}
  .kpi .n {{ font-size:9px; color:#8a93a0; margin-top:2px; }}
  .fh {{ display:flex; gap:18px; align-items:stretch; border:1px solid #e2e7ee; border-radius:8px; background:#fafbfc; padding:14px 16px; margin-bottom:10px; }}
  .fh-score {{ text-align:center; flex-shrink:0; width:150px; border-right:1px solid #e6ebf0; display:flex; flex-direction:column; justify-content:center; }}
  .fh-num {{ font-size:46px; font-weight:800; line-height:1; }}
  .fh-num.red{{ color:#c0392b; }} .fh-num.amber{{ color:#e07b1a; }} .fh-num.green{{ color:#2e8b57; }}
  .fh-den {{ font-size:10px; color:#8a93a0; margin-top:4px; letter-spacing:.3px; }}
  .fh-drivers {{ flex:1; display:flex; flex-direction:column; justify-content:center; gap:9px; }}
  .fh-d {{ display:grid; grid-template-columns:1fr 150px 78px; align-items:center; gap:10px; }}
  .fh-dl {{ font-size:10.5px; color:#31414f; font-weight:600; }}
  .fh-dl span {{ display:block; font-size:8.5px; color:#a2abb6; font-weight:400; }}
  .fh-bar2 {{ height:8px; background:#eef1f5; border-radius:4px; overflow:hidden; }}
  .fh-bar2 > i {{ display:block; height:100%; border-radius:4px; }}
  .fh-dv {{ font-size:12.5px; font-weight:800; color:#0f2440; text-align:right; white-space:nowrap; }}
  .fh-dv small {{ font-size:9px; font-weight:700; color:#8a93a0; }}
  .fh-note {{ font-size:8.5px; color:#a2abb6; line-height:1.5; margin-top:3px; }}
  .scorelegend {{ border:1px solid #e6ebf0; border-radius:8px; background:#fff; padding:11px 14px; margin-bottom:14px; }}
  .sl-title {{ font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.6px; color:#17457a; }}
  .sl-title span {{ text-transform:none; letter-spacing:0; font-weight:400; color:#a2abb6; }}
  .sl-formula {{ font-family:'Consolas',monospace; font-size:11px; color:#0f2440; background:#f4f7fa; border-radius:4px; padding:6px 9px; margin:7px 0; display:inline-block; }}
  .sl-rows {{ display:flex; flex-direction:column; gap:3px; }}
  .sl-row {{ font-size:10px; color:#31414f; line-height:1.5; }} .sl-row b {{ color:#0f2440; }}
  .sl-ref {{ background:#f3f6f4; border-left:3px solid #2e8b57; border-radius:0 5px 5px 0; padding:6px 9px; }}
  .sl-t {{ color:#2e7d4f; font-weight:600; }}
  .sl-colours {{ display:flex; gap:18px; margin-top:8px; font-size:9.5px; color:#5b6472; }}
  .sl-colours i.dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:5px; vertical-align:middle; }}
  .dot.g{{ background:#2e8b57; }} .dot.a{{ background:#e07b1a; }} .dot.r{{ background:#c0392b; }}
  table {{ width:100%; border-collapse:collapse; font-size:10.5px; margin-top:4px; }}
  thead {{ display:table-header-group; }}
  th {{ background:#26517d; color:#fff; text-align:left; padding:7px 9px; font-weight:600; font-size:9.5px; }}
  th.num,td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  td {{ padding:6px 9px; border-bottom:1px solid #eef1f5; vertical-align:middle; }}
  tbody tr:nth-child(even){{ background:#f7f9fb; }}
  .tag {{ display:inline-block; font-size:8px; font-weight:700; letter-spacing:.4px; padding:1px 6px; border-radius:9px; text-transform:uppercase; }}
  .tag.con {{ background:#e5efe8; color:#2e7d4f; }} .tag.non {{ background:#eef0f3; color:#7a8494; }}
  .bar {{ position:relative; height:6px; background:#eef1f5; border-radius:4px; overflow:hidden; min-width:60px; margin-top:3px; }}
  .bar > i {{ position:absolute; left:0; top:0; bottom:0; background:#c0651a; border-radius:4px; }}
  .concl {{ border:1px solid #e2e7ee; border-left:4px solid #17457a; border-radius:6px; background:#f7f9fb; padding:13px 16px; font-size:11.5px; line-height:1.6; color:#31414f; }}
  .hovernote {{ font-size:9px; color:#a2abb6; font-style:italic; margin-top:3px; }}
  .empty {{ color:#6b7480; font-style:italic; text-align:center; padding:14px; }}
  .foot {{ border-top:1px solid #dbe1e8; margin-top:20px; padding-top:8px; font-size:9px; color:#8a93a0; line-height:1.55; }}
</style></head>
<body>
  <div class="head">
    <div class="kicker">Schedule Health Review · Management Report</div>
    <div class="title">{_esc(name)}</div>
    <div class="subtitle">Schedule Stability &amp; Float Distribution — Management Dashboard</div>
    <div class="meta">
      <div><span>Project:</span> {_esc(meta.get('project_name', ''))}</div>
      <div><span>Data Date:</span> {_esc(meta.get('data_date', ''))}</div>
      <div><span>Report Date:</span> {_esc(meta.get('report_date', ''))}</div>
      <div><span>Schedule File:</span> {_esc(meta.get('source_file', ''))}</div>
    </div>
  </div>

  {body}

  <div class="foot">
    The <b>Float Health score</b> = 100 − the construction excess-float defect% (activities over the threshold), a fully
    transparent linear number; the DCMA Metric 5 benchmark (high float &lt; 5%) is shown as a reference only, not the score.
    Construction KPIs exclude Engineering, Procurement, Vendor Documentation and Long-Lead scope.
    Activity-by-activity detail (Activity ID, Name, Float, Recommendation) is available in the separate <b>Excel export</b>.
    &nbsp;·&nbsp; {_esc(meta.get('project_name', ''))} · {_esc(name)}
  </div>
</body></html>'''
