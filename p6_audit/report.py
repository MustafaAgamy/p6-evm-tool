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


def _sug_cell(text, kind):
    """Suggested-fix cell — grey for No Change / N/A, blue for a recommended change,
    red for Remove Relationship."""
    if kind in ('same', 'na'):
        return f'<span class="pill {kind}">{_esc(text)}</span>'
    cls = 'remove' if kind == 'remove' else 'change'
    return f'<span class="pill {cls}">{_esc(text)}</span>'


def _crit_cell(c):
    if c == 'Critical':
        return '<span class="badge2 c">Critical</span>'
    if c == 'Near-Critical':
        return '<span class="badge2 n">Near-Critical</span>'
    return '—'


def _oos_tile(label, value, cls='', note=''):
    note_html = f'<div class="n">{_esc(note)}</div>' if note else ''
    c = f' {cls}' if cls else ''
    return (f'<div class="kpi{c}"><div class="k">{_esc(label)}</div>'
            f'<div class="v">{_esc(value)}</div>{note_html}</div>')


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
            _kpi('Total Activities', f"{k.get('total_activities', 0):,}", 'task-dependent'),
            _kpi('Total Dangling', k.get('total_dangling', 0), 'unique activities'),
            _kpi('Dangling %', f"{k.get('dangling_pct', 0)}%"),
            _kpi('Dangling Start', k.get('start_dangling', 0)),
            _kpi('Dangling Finish', k.get('finish_dangling', 0)),
            _kpi('Dangling Start + Dangling Finish', k.get('both_dangling', 0)),
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
                '<th>Successor(s)</th><th>Suggested Logic Fix</th><th>Suggested Logic Fix 2</th>')
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
                f'<td class="mut">{_esc(f.get("suggested_fix_2"))}</td></tr>')
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


def _scope_note(m):
    if m['module'] == 'dangling':
        return (' The assessment population is <b>Task-Dependent</b> activities; Start/Finish '
                'Milestones and Level-of-Effort are excluded, as they legitimately carry open ends.')
    return ''


def _verdict(m):
    pct = m.get('pct', 0)
    if m['module'] == 'dangling':
        return f"{pct}% of activities have broken start/finish logic."
    return f"{pct}% of activities carry total float above the threshold."


# ── Out of Sequence — Consultant Review Report sections ────────────────────

def _oos_dashboard(m):
    k = m.get('kpis', {})
    grade = m.get('grade', '')
    score = m.get('score', 0)
    color = _GRADE.get(grade, '#6b7a8d')
    pct = m.get('pct', 0)
    tiles = [
        _oos_tile('Total Activities', f"{k.get('total_activities', 0):,}"),
        _oos_tile('Out-of-Sequence Activities', k.get('oos_count', 0)),
        _oos_tile('Out-of-Sequence %', f"{k.get('oos_pct', 0)}%", note='of all activities'),
        _oos_tile('Critical OOS', k.get('critical_oos', 0), 'crit'),
        _oos_tile('Critical OOS %', f"{k.get('critical_oos_pct', 0)}%", 'crit', 'of all activities'),
        _oos_tile('Near-Critical OOS', k.get('near_critical_oos', 0), 'near'),
        _oos_tile('Near-Critical OOS %', f"{k.get('near_critical_oos_pct', 0)}%", 'near', 'of all activities'),
    ]
    dash = f'''
      <div class="dash">
        <div class="grade-card">
          <div class="score-num" style="color:{color}">{score}</div>
          <div class="score-den">Module Score / 100</div>
          <div class="grade-badge" style="background:{color}">{_esc(grade)}</div>
          <div class="verdict">{pct}% of activities progressed out of logical sequence.</div>
        </div>
        <div class="kpis k4">{''.join(tiles)}</div>
      </div>'''
    legend = f'''
      <div class="slegend">
        <div class="t">How the Module Score is calculated</div>
        <div class="d">Driven by the Out-of-Sequence % (fewer out-of-sequence activities &rarr; higher score),
          mapped on the approved band curve (0%&rarr;100 &middot; 2%&rarr;90 &middot; 5%&rarr;75 &middot; 8%&rarr;50 &middot; 20%&rarr;0).
          This schedule: <b>{pct}% &rarr; {_esc(grade)} &rarr; {score} / 100</b>.</div>
        <div class="bands">
          <span><span class="dot" style="background:#2e8b57"></span>Excellent &le; 2%</span>
          <span><span class="dot" style="background:#c9a227"></span>Acceptable 2&ndash;5%</span>
          <span><span class="dot" style="background:#e07b1a"></span>Needs Attention 5&ndash;8%</span>
          <span><span class="dot" style="background:#c0392b"></span>Critical &gt; 8%</span>
        </div>
      </div>'''
    stdref = '''
      <div class="stdref"><b>Standard Reference:</b> Based on the <b>DCMA 14-Point Schedule Assessment</b>
        framework for schedule logic quality &mdash; the same methodology as the sibling modules (Dangling Logic &rarr; Metric 3,
        Float &rarr; Metric 5). Out-of-sequence is a recognised logic-quality check within this framework, complementing the
        14 core metrics. <b>Detection basis:</b> Primavera P6 out-of-sequence progress &mdash; Retained Logic / Progress Override,
        Schedule Log (F9); best-practice per GAO Schedule Assessment Guide, Best Practice 4 (Sequence all activities).</div>'''
    return dash + legend + stdref


def _oos_wbs(m):
    ws = m.get('wbs_summary', [])
    if not ws:
        return ''
    rows = ''.join(
        f'<tr><td>{_esc(r.get("wbs", ""))}</td>'
        f'<td class="num">{r.get("activities", "")}</td>'
        f'<td class="num">{r.get("oos", "")}</td>'
        f'<td class="num">{r.get("pct", "")}%</td>'
        f'<td class="num">{r.get("critical_oos", 0)}</td>'
        f'<td class="num">{r.get("near_critical_oos", 0)}</td></tr>'
        for r in ws)
    return f'''
      <h2 class="sec">Distribution by WBS Category</h2>
      <table><thead><tr><th>WBS Category</th><th class="num">Activities</th>
        <th class="num">Out-of-Sequence</th><th class="num">%</th>
        <th class="num">Critical OOS</th><th class="num">Near-Critical OOS</th></tr></thead>
        <tbody>{rows}</tbody></table>'''


def _oos_review_log(m):
    findings = m.get('findings', [])
    if not findings:
        return ('<h2 class="sec">Out-of-Sequence Review Log</h2>'
                '<p class="empty">No out-of-sequence activities &mdash; schedule progress is consistent '
                'with the network logic.</p>')
    cutoff = _esc(m.get('kpis', {}).get('data_date', ''))
    head = ('<th>#</th><th>Activity ID</th><th>Activity Name</th><th>WBS Path</th>'
            '<th>Current Pred. Rel.</th><th>Current Predecessor Activity</th>'
            '<th>Current Succ. Rel.</th><th>Current Successor Activity</th><th>Cutoff Date</th>'
            '<th>Suggested Predecessor</th><th>Suggested Successor</th>'
            '<th>Root Cause</th><th>Planning Review Comment</th><th>Criticality</th>')
    rows = ''.join(
        f'<tr><td class="num">{i}</td><td class="mono">{_esc(f.get("activity_id"))}</td>'
        f'<td>{_esc(f.get("activity_name"))}</td>'
        f'<td title="{_esc(f.get("wbs_path"))}">{_esc(short_wbs(f.get("wbs_path")))}</td>'
        f'<td>{_esc(f.get("current_pred_rel"))}</td>'
        f'<td class="mut">{_esc(f.get("current_pred_activity"))}</td>'
        f'<td>{_esc(f.get("current_succ_rel"))}</td>'
        f'<td class="mut">{_esc(f.get("current_succ_activity"))}</td>'
        f'<td class="mut">{cutoff}</td>'
        f'<td>{_sug_cell(f.get("suggested_predecessor"), f.get("suggested_predecessor_kind"))}</td>'
        f'<td>{_sug_cell(f.get("suggested_successor"), f.get("suggested_successor_kind"))}</td>'
        f'<td class="mut">{_esc(f.get("root_cause"))}</td>'
        f'<td class="mut">{_esc(f.get("planning_review_comment"))}</td>'
        f'<td>{_crit_cell(f.get("criticality"))}</td></tr>'
        for i, f in enumerate(findings, 1))
    return f'''
      <h2 class="sec">Out-of-Sequence Review Log</h2>
      <table class="findings"><thead><tr>{head}</tr></thead>
        <tbody>{rows}</tbody></table>'''


def _oos_cpi(m):
    k = m.get('kpis', {})
    cpi = k.get('critical_path_impact', 'No')
    cdi = k.get('completion_date_impact', 'No Impact')
    cpi_color = '#c0392b' if cpi == 'Yes' else '#2e8b57'
    cdi_color = {'Direct Impact': '#a93226', 'Potential Impact': '#e07b1a',
                 'No Impact': '#2e8b57'}.get(cdi, '#6b7a8d')
    return f'''
      <h2 class="sec">Critical Path Impact Assessment</h2>
      <div class="cpi-wrap">
        <table><thead><tr><th>Indicator</th><th class="num">Result</th></tr></thead><tbody>
          <tr><td>Total Out-of-Sequence Activities</td><td class="num">{k.get('oos_count', 0)}</td></tr>
          <tr><td>Critical Out-of-Sequence Activities</td><td class="num">{k.get('critical_oos', 0)}</td></tr>
          <tr><td>Near-Critical Out-of-Sequence Activities</td><td class="num">{k.get('near_critical_oos', 0)}</td></tr>
        </tbody></table>
        <div class="vcards">
          <div class="vcard" style="background:{cpi_color}"><div class="l">Critical Path Impact</div><div class="v2">{_esc(cpi)}</div></div>
          <div class="vcard" style="background:{cdi_color}"><div class="l">Completion Date Impact</div><div class="v2">{_esc(cdi)}</div></div>
        </div>
      </div>
      <div class="dcma">Classification only &mdash; the module does not predict a number of delay days.</div>'''


def _oos_conclusion(m):
    c = m.get('kpis', {}).get('executive_conclusion', '')
    if not c:
        return ''
    return f'<h2 class="sec">Executive Conclusion</h2><div class="concl">{_esc(c)}</div>'


def _sections(m):
    """Body sections for a module report — OOS uses its own five-section order."""
    if m.get('module') == 'out_of_sequence':
        return (f'<h2 class="sec">Executive Dashboard</h2>{_oos_dashboard(m)}'
                f'{_oos_wbs(m)}{_oos_review_log(m)}{_oos_cpi(m)}{_oos_conclusion(m)}')
    return (f'<h2 class="sec">Executive Dashboard</h2>{_dashboard(m, _verdict(m))}'
            f'{_summary_stats(m)}{_wbs_summary(m)}{_findings_table(m)}')


def render_module_report(module_result, meta):
    m = module_result
    # Float Analysis has its own management-dashboard layout (V2 redesign).
    if m.get('module') == 'float':
        from p6_audit.float_report import render_float_report
        return render_float_report(m, meta)
    name = m.get('name', 'Schedule Audit')
    subtitle = ('Open / Broken Logic Assessment' if m['module'] == 'dangling'
                else 'Excessive Total Float Assessment' if m['module'] == 'float'
                else 'Consultant Review Report — Schedule Logic Inconsistency Assessment')
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
  /* Out of Sequence module */
  .kpis.k4 {{ grid-template-columns: repeat(4, 1fr); }}
  .kpi.crit {{ border-color: #eec9c4; background: #fdf5f4; }}
  .kpi.crit .v {{ color: #c0392b; }}
  .kpi.near {{ border-color: #f0dcc0; background: #fdf8f1; }}
  .kpi.near .v {{ color: #e07b1a; }}
  .slegend {{ border: 1px solid #e2e7ee; background: #fafbfc; border-radius: 8px; padding: 9px 12px; margin-top: 10px; font-size: 9.5px; }}
  .slegend .t {{ font-size: 9px; text-transform: uppercase; letter-spacing: .6px; color: #17457a; font-weight: 700; }}
  .slegend .d {{ color: #5b6472; margin: 3px 0 6px; line-height: 1.4; }}
  .slegend .bands span {{ margin-right: 14px; }}
  .slegend .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 2px; vertical-align: -1px; margin-right: 3px; }}
  .stdref {{ font-size: 9.5px; color: #5b6472; font-style: italic; margin-top: 9px; padding: 7px 11px;
             background: #f2f6fb; border-left: 3px solid #17457a; border-radius: 0 6px 6px 0; line-height: 1.45; }}
  .stdref b {{ color: #17457a; font-style: normal; }}
  .pill {{ display: inline-block; padding: 1px 6px; border-radius: 10px; font-weight: 700; font-size: 8.5px; }}
  .pill.same {{ color: #6b7480; background: transparent; padding: 0; }}
  .pill.na {{ color: #9aa3ad; background: transparent; padding: 0; font-style: italic; }}
  .pill.change {{ color: #17457a; background: #e7effb; }}
  .pill.remove {{ color: #c0392b; background: #fdeeec; }}
  .badge2 {{ display: inline-block; padding: 1px 6px; border-radius: 4px; color: #fff; font-weight: 700; font-size: 8px; white-space: nowrap; }}
  .badge2.c {{ background: #c0392b; }}
  .badge2.n {{ background: #e07b1a; }}
  .cpi-wrap {{ display: flex; gap: 14px; align-items: stretch; flex-wrap: wrap; }}
  .cpi-wrap table {{ max-width: 360px; }}
  .vcards {{ display: flex; flex-direction: column; gap: 8px; justify-content: center; }}
  .vcard {{ border-radius: 8px; padding: 9px 14px; color: #fff; min-width: 200px; }}
  .vcard .l {{ font-size: 8.5px; text-transform: uppercase; letter-spacing: .5px; opacity: .9; font-weight: 700; }}
  .vcard .v2 {{ font-size: 14px; font-weight: 800; margin-top: 1px; }}
  .concl {{ border-left: 4px solid #17457a; background: #f4f8fd; border-radius: 0 8px 8px 0; padding: 11px 15px; font-size: 11px; line-height: 1.55; color: #25313f; }}
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

  {_sections(m)}

  <div class="foot">
    This report covers the <b>{_esc(name)}</b> module only, in isolation from other Schedule Audit
    checks and from cost / earned-value / progress. Module score is derived from the module KPI
    percentage on the approved band curve. Findings are engineering guidance and require planner
    verification.{_scope_note(m)} &nbsp;·&nbsp; {_esc(meta.get('project_name', ''))} · {_esc(name)}
  </div>
</body></html>'''
