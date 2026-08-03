"""Standalone consultant-grade report for a single Schedule Audit module.

One module = one report. Never mixed with another module, EVM, cost, or
progress. Rendered to HTML, then to PDF by the caller (Chrome headless).
Detailed-findings tables use <thead>, so headers repeat on every printed page.
"""
import html as _html

_SEV = {'Critical': '#c0392b', 'High': '#e07b1a', 'Medium': '#c9a227', 'Low': '#6b7a8d'}
_GRADE = {'Excellent': '#2e8b57', 'Acceptable': '#c9a227',
          'Needs Attention': '#e07b1a', 'Critical': '#c0392b'}

_DCMA = {
    'dangling': 'DCMA Metric 3 — Missing Logic (target: 0 activities)',
    'float':    'DCMA Metric 5 — High Float, &gt;44 working days (target: &lt;5% of activities)',
}


def short_wbs(path, n=3):
    """Last n WBS levels for readability; full path travels as a tooltip."""
    if not path:
        return ''
    parts = [p.strip() for p in path.split('>')]
    return ' > '.join(parts[-n:])


def _esc(v):
    return _html.escape('' if v is None else str(v))


def _sev_badge(sev):
    return f'<span class="sev" style="background:{_SEV.get(sev, "#6b7a8d")}">{_esc(sev)}</span>'


def _kpi(label, value, note=''):
    note_html = f'<div class="n">{_esc(note)}</div>' if note else ''
    return f'<div class="kpi"><div class="k">{_esc(label)}</div><div class="v">{_esc(value)}</div>{note_html}</div>'


def _dashboard(m, verdict):
    grade = m.get('grade', '')
    score = m.get('score', 0)
    color = _GRADE.get(grade, '#6b7a8d')
    if m['module'] == 'dangling':
        k = m['kpis']
        tiles = [
            _kpi('Total Activities', f"{k.get('total_activities', 0):,}"),
            _kpi('Total Dangling', k.get('total_dangling', 0), 'unique activities'),
            _kpi('Dangling %', f"{k.get('dangling_pct', 0)}%"),
            _kpi('Dangling Start', k.get('start_dangling', 0)),
            _kpi('Dangling Finish', k.get('finish_dangling', 0)),
            _kpi('Start + Finish', k.get('both_dangling', 0)),
        ]
    else:
        k = m['kpis']
        tiles = [
            _kpi('Total Activities', f"{k.get('total_activities', 0):,}"),
            _kpi('Above Threshold', k.get('above_threshold', 0), f"&gt; {k.get('threshold', 44)} days"),
            _kpi('Float %', f"{k.get('float_pct', 0)}%"),
            _kpi('Max Float', f"{k.get('max_float', 0)} d"),
            _kpi('Average Float', f"{k.get('avg_float', 0)} d"),
            _kpi('Threshold', f"{k.get('threshold', 44)} d"),
        ]
    return f'''
      <div class="dash">
        <div class="grade-card">
          <div class="score-num" style="color:{color}">{score}</div>
          <div class="score-den">Module Score / 100</div>
          <div class="grade-badge" style="background:{color}">{_esc(grade)}</div>
          <div class="verdict">{verdict}</div>
        </div>
        <div class="kpis">{''.join(tiles)}</div>
      </div>
      <div class="dcma">{_DCMA.get(m['module'], '')}</div>'''


def _summary_stats(m):
    k = m.get('kpis', {})
    n_findings = len(m.get('findings', []))
    if m['module'] == 'dangling':
        stats = [('Total Activities', f"{k.get('total_activities', 0):,}"),
                 ('Total Dangling Findings', n_findings),
                 ('Dangling Percentage', f"{k.get('dangling_pct', 0)}%"),
                 ('Schedule Logic Score', f"{m.get('score', 0)} / 100 ({_esc(m.get('grade', ''))})")]
    else:
        stats = [('Total Activities', f"{k.get('total_activities', 0):,}"),
                 ('Activities Above Threshold', k.get('above_threshold', 0)),
                 ('Float Percentage', f"{k.get('float_pct', 0)}%"),
                 ('Float Analysis Score', f"{m.get('score', 0)} / 100 ({_esc(m.get('grade', ''))})")]
    rows = ''.join(f'<tr><td>{_esc(lbl)}</td><td class="num">{_esc(val)}</td></tr>' for lbl, val in stats)
    return f'''
      <h2 class="sec">Summary Statistics</h2>
      <table class="summary"><thead><tr><th>KPI</th><th class="num">Value</th></tr></thead>
        <tbody>{rows}</tbody></table>'''


def _wbs_summary(m):
    ws = m.get('wbs_summary', [])
    if not ws:
        return ''
    rows = []
    for r in ws[:12]:
        rows.append(
            f'<tr><td>{_esc(short_wbs(r.get("wbs", ""), 4))}</td>'
            f'<td class="num">{r.get("activities", "")}</td>'
            f'<td class="num">{r.get("high", "")}</td>'
            f'<td class="num">{r.get("pct", "")}%</td>'
            f'<td>{_sev_badge(_grade_to_sev(r.get("grade")))}</td></tr>')
    return f'''
      <h2 class="sec">WBS Summary — where the excessive float concentrates</h2>
      <table><thead><tr><th>WBS Package</th><th class="num">Activities</th>
        <th class="num">High-Float</th><th class="num">% of Package</th><th>Concentration</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table>'''


def _grade_to_sev(grade):
    return {'Critical': 'Critical', 'Needs Attention': 'High',
            'Acceptable': 'Medium', 'Excellent': 'Low'}.get(grade, 'Low')


def _findings_table(m):
    findings = m.get('findings', [])
    if not findings:
        return '<p class="empty">No findings — this module passed all checks.</p>'
    if m['module'] == 'dangling':
        head = ('<th>#</th><th>Activity ID</th><th>Activity Name</th><th>WBS Path</th>'
                '<th>Severity</th><th>Logic Issue</th><th>Predecessor(s)</th>'
                '<th>Successor(s)</th><th>Suggested Logic Fix</th><th>Recommendation</th>')
        rows = []
        for i, f in enumerate(findings, 1):
            rows.append(
                f'<tr><td class="num">{i}</td><td class="mono">{_esc(f.get("activity_id"))}</td>'
                f'<td>{_esc(f.get("activity_name"))}</td>'
                f'<td title="{_esc(f.get("wbs_path"))}">{_esc(short_wbs(f.get("wbs_path")))}</td>'
                f'<td>{_sev_badge(f.get("severity"))}</td>'
                f'<td>{_esc(f.get("logic_issue"))}</td>'
                f'<td class="mut">{_esc(f.get("predecessors"))}</td>'
                f'<td class="mut">{_esc(f.get("successors"))}</td>'
                f'<td>{_esc(f.get("suggested_fix"))}</td>'
                f'<td class="mut">{_esc(f.get("recommendation"))}</td></tr>')
    else:
        head = ('<th>#</th><th>Activity ID</th><th>Activity Name</th><th>WBS Path</th>'
                '<th class="num">Total Float</th><th class="num">Threshold</th><th class="num">Impact</th>'
                '<th>Status</th><th>Severity</th><th>Recommendation</th>')
        rows = []
        for i, f in enumerate(findings, 1):
            impact = f.get('impact')
            impact_s = f'{impact}×' if impact is not None else '—'
            rows.append(
                f'<tr><td class="num">{i}</td><td class="mono">{_esc(f.get("activity_id"))}</td>'
                f'<td>{_esc(f.get("activity_name"))}</td>'
                f'<td title="{_esc(f.get("wbs_path"))}">{_esc(short_wbs(f.get("wbs_path")))}</td>'
                f'<td class="num">{_esc(f.get("total_float_days"))} d</td>'
                f'<td class="num">{_esc(f.get("threshold"))} d</td>'
                f'<td class="num">{impact_s}</td>'
                f'<td>{_esc(f.get("status"))}</td>'
                f'<td>{_sev_badge(f.get("severity"))}</td>'
                f'<td class="mut">{_esc(f.get("recommendation"))}</td></tr>')
    return f'''
      <h2 class="sec">Detailed Findings</h2>
      <table class="findings"><thead><tr>{head}</tr></thead>
        <tbody>{''.join(rows)}</tbody></table>'''


def _verdict(m):
    pct = m.get('pct', 0)
    if m['module'] == 'dangling':
        return f"{pct}% of activities have broken start/finish logic."
    return f"{pct}% of activities carry total float above the threshold."


def render_module_report(module_result, meta):
    m = module_result
    name = m.get('name', 'Schedule Audit')
    subtitle = ('Open / Broken Logic Assessment' if m['module'] == 'dangling'
                else 'Excessive Total Float Assessment')
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{_esc(name)} — {_esc(meta.get('project_name', ''))}</title>
<style>
  @page {{ margin: 20mm 14mm; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1f2a37; font-size: 11px; margin: 0; }}
  .head {{ border-bottom: 3px solid #17457a; padding-bottom: 12px; margin-bottom: 18px; }}
  .kicker {{ font-size: 10px; letter-spacing: 2px; color: #17457a; font-weight: 700; text-transform: uppercase; }}
  .title {{ font-size: 24px; font-weight: 800; color: #0f2440; margin: 3px 0 1px; }}
  .subtitle {{ font-size: 12px; color: #5b6472; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 3px 26px; margin-top: 10px; font-size: 11px; }}
  .meta span {{ color: #8a93a0; }}
  h2.sec {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #17457a;
            border-bottom: 1px solid #dbe1e8; padding-bottom: 4px; margin: 22px 0 10px; }}
  .dash {{ display: flex; gap: 14px; align-items: stretch; }}
  .grade-card {{ border: 1px solid #e2e7ee; border-radius: 8px; padding: 15px 16px; width: 200px;
                 flex-shrink: 0; text-align: center; background: #fafbfc; }}
  .score-num {{ font-size: 42px; font-weight: 800; line-height: 1; }}
  .score-den {{ font-size: 11px; color: #8a93a0; }}
  .grade-badge {{ display: inline-block; margin-top: 8px; padding: 4px 14px; border-radius: 20px;
                  font-size: 12px; font-weight: 700; color: #fff; }}
  .verdict {{ font-size: 10.5px; color: #5b6472; margin-top: 9px; line-height: 1.4; }}
  .kpis {{ flex: 1; display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; }}
  .kpi {{ border: 1px solid #e8ecf1; border-radius: 8px; padding: 10px 12px; }}
  .kpi .k {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: .5px; color: #8a93a0; font-weight: 700; }}
  .kpi .v {{ font-size: 21px; font-weight: 800; margin-top: 2px; color: #0f2440; }}
  .kpi .n {{ font-size: 9.5px; color: #8a93a0; margin-top: 1px; }}
  .dcma {{ font-size: 10px; color: #5b6472; margin-top: 8px; font-style: italic; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10px; margin-top: 2px; }}
  thead {{ display: table-header-group; }}   /* repeat header on every printed page */
  th {{ background: #26517d; color: #fff; text-align: left; padding: 7px 8px; font-weight: 600; font-size: 9.5px; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #eef1f5; vertical-align: top; }}
  tbody tr:nth-child(even) {{ background: #f7f9fb; }}
  table.summary {{ max-width: 420px; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .mono {{ font-family: 'Consolas', monospace; white-space: nowrap; }}
  .mut {{ color: #6b7480; font-size: 9.5px; }}
  .sev {{ display: inline-block; padding: 1px 7px; border-radius: 4px; color: #fff; font-weight: 700; font-size: 9px; white-space: nowrap; }}
  .empty {{ color: #6b7480; font-style: italic; }}
  .foot {{ border-top: 1px solid #dbe1e8; margin-top: 20px; padding-top: 8px; font-size: 9px; color: #8a93a0; line-height: 1.5; }}
</style></head>
<body>
  <div class="head">
    <div class="kicker">Schedule Audit · Module Report</div>
    <div class="title">{_esc(name)}</div>
    <div class="subtitle">{_esc(subtitle)}</div>
    <div class="meta">
      <div><span>Project:</span> {_esc(meta.get('project_name', ''))}</div>
      <div><span>Data Date:</span> {_esc(meta.get('data_date', ''))}</div>
      <div><span>Report Date:</span> {_esc(meta.get('report_date', ''))}</div>
      <div><span>Schedule File:</span> {_esc(meta.get('source_file', ''))}</div>
    </div>
  </div>

  <h2 class="sec">Executive Dashboard</h2>
  {_dashboard(m, _verdict(m))}

  {_summary_stats(m)}

  {_wbs_summary(m)}

  {_findings_table(m)}

  <div class="foot">
    This report covers the <b>{_esc(name)}</b> module only, in isolation from other Schedule Audit
    checks and from cost / earned-value / progress. Module score is derived from the module KPI
    percentage on the approved band curve. Findings are engineering guidance and require planner
    verification. &nbsp;·&nbsp; {_esc(meta.get('project_name', ''))} · {_esc(name)}
  </div>
</body></html>'''
