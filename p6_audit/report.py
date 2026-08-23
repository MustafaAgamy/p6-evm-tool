"""Standalone consultant-grade report for a single Schedule Audit module.

One module = one report. Never mixed with another module, EVM, cost, or
progress. Rendered to HTML, then to PDF by the caller (Chrome headless).
Detailed-findings tables use <thead>, so headers repeat on every printed page.
"""
import html as _html

from p6_audit.presentation import build_presentation

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


# ── Lag & Lead — Consultant Review Report sections ─────────────────────────

def _lag_summary(m):
    k = m.get('kpis', {})
    total = k.get('lagged_count', 0)
    need = k.get('need_justification_count', 0)
    thr = k.get('long_threshold_days', 14)
    return (f'<div class="lagsum"><b>{total:,}</b> lags across the schedule &nbsp;·&nbsp; '
            f'<b>{need:,}</b> need a justification (lag over {thr} working days, or a lead) '
            f'&nbsp;·&nbsp; listed worst first</div>')


def _lag_bars(rows, label_key, count_key, stacked=False):
    """Horizontal bars. stacked=True puts the (long) label on its own line above a full-width
    bar — used for the WBS-area chart so names are never trimmed (a PDF has no hover tooltip)."""
    if not rows:
        return '<div class="lmut">No lags to distribute.</div>'
    mx = max([1] + [r.get(count_key, 0) for r in rows])
    out = []
    for r in rows:
        c = r.get(count_key, 0)
        w = round(100 * c / mx)
        label = _esc(str(r.get(label_key, "")))
        val = f'{c} &middot; {r.get("pct", 0)}%'
        if stacked:
            out.append(f'<div class="lbarS"><div class="lblS">{label}</div>'
                       f'<div class="lineS"><span class="trk"><i style="width:{w}%"></i></span>'
                       f'<span class="lval">{val}</span></div></div>')
        else:
            out.append(f'<div class="lbar"><span class="lbl">{label}</span>'
                       f'<span class="trk"><i style="width:{w}%"></i></span>'
                       f'<span class="lval">{val}</span></div>')
    return ''.join(out)


def _lag_donut(m):
    k = m.get('kpis', {})
    normal, longp, leads = k.get('normal_count', 0), k.get('long_positive_count', 0), k.get('leads_count', 0)
    total = normal + longp + leads
    need = k.get('need_justification_count', longp + leads)
    thr = k.get('long_threshold_days', 14)
    C, off, segs = 251.33, 0.0, []
    for val, color in ((normal, '#8a93a0'), (longp, '#e0a11a'), (leads, '#d0433b')):
        if val and total:
            ln = C * val / total
            segs.append(f'<circle cx="50" cy="50" r="40" fill="none" stroke="{color}" stroke-width="15" '
                        f'stroke-dasharray="{ln:.1f} {C:.1f}" stroke-dashoffset="{-off:.1f}"/>')
            off += ln
    return (f'<div class="ldonut"><svg width="86" height="86" viewBox="0 0 100 100">'
            f'<g transform="rotate(-90 50 50)">{"".join(segs)}</g>'
            f'<text x="50" y="48" text-anchor="middle" font-size="18" font-weight="800" fill="#0f2440">{need}</text>'
            f'<text x="50" y="62" text-anchor="middle" font-size="8" fill="#8a93a0">to justify</text></svg>'
            f'<div class="lleg">'
            f'<div><span class="d" style="background:#8a93a0"></span>Normal &le;{thr} wd <b>{normal}</b></div>'
            f'<div><span class="d" style="background:#e0a11a"></span>Long &gt;{thr} wd <b>{longp}</b></div>'
            f'<div><span class="d" style="background:#d0433b"></span>Leads <b>{leads}</b></div>'
            f'<div><span class="d" style="background:#26517d"></span>On critical path <b>{k.get("critical_count", 0)}</b></div>'
            f'</div></div>')


def _lag_charts(m):
    k = m.get('kpis', {})
    by_type = k.get('by_type', [])
    ws = [{'wbs': short_wbs(r.get('wbs', ''), 3), 'pct': r.get('pct', 0), 'lagged': r.get('lagged', 0)}
          for r in m.get('wbs_summary', [])[:10]]
    if not by_type and not ws:
        return ''
    return (f'<h2 class="sec">Lag charts</h2><div class="lcharts">'
            f'<div class="lcard"><div class="lch">Lags by relationship type</div>'
            f'{_lag_bars(by_type, "type", "count")}</div>'
            f'<div class="lcard"><div class="lch">Lags by WBS area</div>'
            f'{_lag_bars(ws, "wbs", "lagged", stacked=True)}</div>'
            f'<div class="lcard"><div class="lch">Lag makeup</div>{_lag_donut(m)}</div>'
            f'</div>')


def _lag_flags_cell(f):
    chips = []
    if f.get('is_lead'):
        chips.append('<span class="badge2 c">Lead</span>')
    if f.get('is_long'):
        chips.append('<span class="pill change">Long</span>')
    if f.get('criticality') == 'Critical':
        chips.append('<span class="badge2 c">Crit</span>')
    elif f.get('criticality') == 'Near-Critical':
        chips.append('<span class="badge2 n">Near</span>')
    return ' '.join(chips)


def _lag_register(m):
    findings = m.get('findings', [])
    if not findings:
        return ('<h2 class="sec">Lag &amp; Lead Register</h2>'
                '<p class="empty">No lags or leads &mdash; every relationship drives directly.</p>')
    head = ('<th>#</th><th>Activity ID</th><th>Activity Name</th>'
            '<th>Pred. Relationship</th><th>Pred. Name</th>'
            '<th>Succ. Relationship</th><th>Succ. Name</th>'
            '<th>Justification</th>')
    rows = ''.join(
        f'<tr><td class="num">{i}</td><td class="mono">{_esc(f.get("activity_id"))}</td>'
        f'<td>{_esc(f.get("activity_name"))}</td>'
        f'<td class="mono">{_esc(f.get("pred_rel"))} {_lag_flags_cell(f)}</td>'
        f'<td class="mut">{_esc(f.get("pred_name"))}</td>'
        f'<td class="mono">{_esc(f.get("succ_rel")) or "&mdash;"}</td>'
        f'<td class="mut">{_esc(f.get("succ_name")) or "&mdash;"}</td>'
        f'<td>{_esc(f.get("justification"))}</td></tr>'
        for i, f in enumerate(findings, 1))
    return f'''
      <h2 class="sec">Lag &amp; Lead Register — all project lags (worst first)</h2>
      <table class="findings"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>'''


def _pcell(cell):
    """One normalized presentation cell -> a <td>. A severity chip is wrapped in
    its OWN <td> so the table columns stay aligned — returning a bare <span> made
    Chrome hoist every badge out of the table into a block above it."""
    if cell.get('badge'):
        return f'<td>{_sev_badge(cell.get("text"))}</td>'
    cls = cell.get('cls', '')
    cls_attr = f' class="{cls}"' if cls else ''
    title_attr = f' title="{_esc(cell.get("title"))}"' if cell.get('title') else ''
    return f'<td{cls_attr}{title_attr}>{_esc(cell.get("text"))}</td>'


def _presentation_dashboard(m):
    """Gauge + KPI tiles from the single-source presentation — same values as the screen."""
    p = m.get('presentation') or build_presentation(m)
    grade = m.get('grade', '')
    score = m.get('score', 0)
    color = _GRADE.get(grade, '#6b7a8d')
    score_txt = '—' if score is None else score
    tiles = ''.join(_kpi(t['label'], t['value']) for t in p.get('tiles', []))
    return f'''
      <div class="dash">
        <div class="grade-card">
          <div class="score-num" style="color:{color}">{score_txt}</div>
          <div class="score-den">Module Score / 100</div>
          <div class="grade-badge" style="background:{color}">{_esc(grade)}</div>
          <div class="verdict">{_esc(p.get('verdict', ''))}</div>
        </div>
        <div class="kpis">{tiles}</div>
      </div>
      <div class="dcma">{_DCMA.get(m['module'], '')}</div>'''


def _presentation_table(m):
    """Findings table from the single-source presentation columns + rows — identical
    to the on-screen table (same columns, order, cells and totals)."""
    p = m.get('presentation') or build_presentation(m)
    cols = p.get('columns', [])
    rows = p.get('rows', [])
    if not rows:
        return '<h2 class="sec">Detailed Findings</h2><p class="empty">No findings — this module passed all checks.</p>'
    head = '<th>#</th>' + ''.join(
        (f'<th class="num">{_esc(c["label"])}</th>' if c.get('align') == 'num' else f'<th>{_esc(c["label"])}</th>')
        for c in cols)
    body = ''.join(
        f'<tr><td class="num">{i}</td>{"".join(_pcell(c) for c in row)}</tr>'
        for i, row in enumerate(rows, 1))
    return f'''
      <h2 class="sec">Detailed Findings</h2>
      <table class="findings"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'''


def _scoring_legend(m):
    """How this score is calculated — the same transparent legend as the screen
    (formula + this schedule's derivation + bands + the DCMA benchmark, kept
    separate from the 0-100 score)."""
    p = m.get('presentation') or build_presentation(m)
    s = p.get('scoring')
    if not s:
        return ''
    bands = f'<div><b>Score bands:</b> {_esc(s["bands"])}</div>' if s.get('bands') else ''
    bench = (f'<div style="margin-top:5px"><b>Benchmark:</b> {_esc(s["benchmark"])}</div>'
             if s.get('benchmark') else '')
    return (f'<div class="slegend"><div class="t">How this score is calculated</div>'
            f'<div class="d"><b>Formula:</b> {_esc(s["formula"])}<br>'
            f'<b>This schedule:</b> {_esc(s["derivation"])}</div>{bands}{bench}</div>')


def _severity_legend(m):
    """What makes a finding Critical/High/Medium/Low — the same criteria as the
    screen, straight from the rule engine. Skipped when the check has no findings."""
    if not m.get('findings'):
        return ''
    p = m.get('presentation') or build_presentation(m)
    sev = p.get('severity')
    if not sev or not sev.get('levels'):
        return ''
    rows = ''.join(f'<tr><td style="white-space:nowrap">{_sev_badge(l["level"])}</td>'
                   f'<td>{_esc(l["criteria"])}</td></tr>' for l in sev['levels'])
    basis = f'<div class="d" style="margin-top:5px">{_esc(sev["basis"])}</div>' if sev.get('basis') else ''
    return (f'<div class="slegend"><div class="t">What the severity levels mean</div>'
            f'<table style="max-width:540px;margin-top:4px"><tbody>{rows}</tbody></table>{basis}</div>')


def _recommendations_section(m):
    """A de-duplicated list of the check's recommendations — the actions to take.
    Skipped when the check has no findings (no empty section printed)."""
    seen, items = set(), []
    for f in m.get('findings') or []:
        rec = f.get('recommendation') or f.get('suggested_fix')
        if rec and rec not in seen:
            seen.add(rec)
            items.append(rec)
    if not items:
        return ''
    lis = ''.join(f'<li>{_esc(r)}</li>' for r in items)
    return f'<h2 class="sec">Recommendations</h2><ul class="recs">{lis}</ul>'


def _cpli_driving_chart(m):
    """A print-friendly driving-path bar chart for the CPLI PDF — one bar per critical
    activity across the schedule range (the printed form of the on-screen Gantt).
    Red = critical, blue = near-critical, green diamond = a genuine P6 milestone."""
    import datetime as _dt
    def _t(s):
        try:
            return _dt.datetime.strptime(str(s)[:10], '%Y-%m-%d')
        except (ValueError, TypeError):
            return None
    dated = [(f, _t(f.get('start')), _t(f.get('finish'))) for f in (m.get('findings') or [])]
    dated = [(f, s, e) for f, s, e in dated if s and e]
    if not dated:
        return ''
    lo = min(s for _, s, _ in dated)
    hi = max(e for _, _, e in dated)
    span = max(1, (hi - lo).days)
    fm_id = (m.get('kpis') or {}).get('finish_milestone_id')

    rows = []
    for f, s, e in dated:                        # ALL critical activities — same as the on-screen Gantt
        x = 100.0 * (s - lo).days / span
        w = max(0.6, 100.0 * (e - s).days / span)
        # a genuine P6 milestone OR the completion milestone CPLI identified -> diamond
        is_ms = bool(f.get('is_milestone')) or (fm_id is not None and f.get('activity_id') == fm_id)
        if is_ms:
            bar = f'<span style="position:absolute;left:{x:.1f}%;top:2px;width:9px;height:9px;background:#2e8b57;transform:translateX(-50%) rotate(45deg)"></span>'
        else:
            color = '#c0392b' if (f.get('total_float_days') or 0) <= 0 else '#17457a'
            bar = f'<span style="position:absolute;left:{x:.1f}%;width:{min(w, 100 - x):.1f}%;top:4px;height:7px;background:{color};border-radius:2px"></span>'
        dur = f.get('duration_days')
        rows.append(
            f'<tr><td class="mono">{_esc(f.get("activity_id"))}</td>'
            f'<td>{_esc(f.get("activity_name"))}{" &#9670;" if is_ms else ""}</td>'
            f'<td class="num">{_esc(f.get("start"))}</td><td class="num">{_esc(f.get("finish"))}</td>'
            f'<td class="num">{"—" if dur is None else str(dur) + " wd"}</td>'
            f'<td style="position:relative;height:15px;min-width:200px">{bar}</td></tr>')

    # Month axis in the Timeline header — repeats on every printed page (dates like the screen).
    ticks = []
    total_months = max(1, (hi.year - lo.year) * 12 + (hi.month - lo.month))
    step = max(1, total_months // 10 + 1)
    d = _dt.datetime(lo.year, lo.month, 1)
    while d <= hi:
        pos = 100.0 * (d - lo).days / span
        if -2 <= pos <= 102:
            ticks.append(f'<span style="position:absolute;left:{max(0.0, min(100.0, pos)):.1f}%;top:4px;'
                         f'font-size:7.5px;color:#eaf1fb;font-weight:400;transform:translateX(-50%);white-space:nowrap">'
                         f'{d.strftime("%b %y")}</span>')
        mo = d.month - 1 + step
        d = _dt.datetime(d.year + mo // 12, mo % 12 + 1, 1)
    axis = ''.join(ticks)

    return ('<h2 class="sec">Driving Path</h2>'
            f'<div class="dcma">{len(dated)} critical activities, in sequence — every one shown '
            '(red = critical, blue = near-critical, green diamond = milestone).</div>'
            '<table><thead><tr><th>Activity ID</th><th>Activity Name</th><th class="num">Start</th>'
            f'<th class="num">Finish</th><th class="num">Dur</th>'
            f'<th style="position:relative;min-width:200px;height:18px">{axis}</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def _cpli_context_note(m):
    """CPLI ratio + baseline-float rule — CONTEXT indicators for the CPLI PDF. The
    sub-feature score itself is the critical-path density (see the scoring legend)."""
    k = m.get('kpis') or {}
    ratio = k.get('cpli_pct')
    tf = k.get('project_total_float_days')
    if ratio is None and tf is None:
        return ''
    rule_txt = ('Baseline rule met — total float &ge; 0' if k.get('baseline_rule_met')
                else 'Negative float — re-plan (baseline must be &ge; 0)')
    ratio_txt = '—' if ratio is None else f'{_pnum(ratio)}%'
    tf_txt = '—' if tf is None else f'{_pnum(tf)} d'
    return (f'<div class="slegend"><div class="t">CPLI ratio &amp; baseline rule — context, not the score</div>'
            f'<div class="d">CPLI (CPL + TF) &divide; CPL = <b>{_esc(ratio_txt)}</b> (DCMA target &ge; 95%); '
            f'completion total float = <b>{_esc(tf_txt)}</b>. {rule_txt}. '
            f'The sub-feature score above is the critical-path density.</div></div>')


def _sections(m, sections=None):
    """Body sections for a module report — respecting the user's report-content
    selection (Preview = PDF = Print) and skipping sections with no data. OOS and
    Lag & Lead keep their bespoke order; every other check renders from the single
    source, so the PDF matches the screen exactly."""
    want = set(sections) if sections else None

    def on(key):
        return want is None or key in want

    mod = m.get('module')
    if mod == 'out_of_sequence':
        parts = []
        if on('executive'):
            parts.append(f'<h2 class="sec">Executive Dashboard</h2>{_oos_dashboard(m)}')
        if on('wbs'):
            parts.append(_oos_wbs(m))
        if on('findings'):
            parts.append(_oos_review_log(m))
        if on('cpi'):
            parts.append(_oos_cpi(m))
        if on('conclusion'):
            parts.append(_oos_conclusion(m))
        return ''.join(parts)
    if mod == 'lag_lead':
        parts = []
        if on('summary'):
            parts.append(_lag_summary(m))
        if on('charts'):
            parts.append(_lag_charts(m))
        if on('findings'):
            parts.append(_lag_register(m))
        return ''.join(parts)

    parts = []
    if on('executive'):
        parts.append(f'<h2 class="sec">Executive Dashboard</h2>{_presentation_dashboard(m)}')
        if mod == 'cpli':
            parts.append(_cpli_context_note(m))
    if on('scoring'):
        parts.append(_scoring_legend(m))
    if on('severity'):
        parts.append(_severity_legend(m))
    if on('findings'):
        parts.append(_wbs_summary(m))
        if mod == 'cpli':
            parts.append(_cpli_driving_chart(m))     # the bar chart IS the driving path (all activities) — no separate table
        else:
            parts.append(_presentation_table(m))
    if on('recommendations'):
        parts.append(_recommendations_section(m))
    return ''.join(parts)


def _pnum(v):
    """Mirror the screen's JS number formatting: 78.0 -> '78', 6.8 -> '6.8', None -> '—'."""
    if v is None:
        return '—'
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def render_summary_report(health, meta, sections=None, modules=None):
    """Standalone PDF for the Schedule Health Review Summary — the weighted roll-up.
    Mirrors the on-screen dashboard exactly: overall score + verdict, checks-status
    (counts + circular gate + status bands), headline stats (incl. completion total
    float), sub-feature composition, problem areas, fix-first and conclusion."""
    h = health or {}
    meta = meta or {}
    modules = modules or {}
    score = h.get('score')
    score_txt = _pnum(score)
    grade = h.get('grade', '') or ''
    color = _GRADE.get(grade, '#17457a')
    verdict = h.get('verdict', '') or ''
    statement = h.get('statement', '') or ''
    counts = h.get('counts', {}) or {}
    subs = h.get('sub_features', []) or []
    gate = h.get('gate', {}) or {}
    gate_clear = not gate.get('blocking')
    weight_covered = h.get('weight_covered', 100)
    total = h.get('total_count') or len(subs) or 1
    p_n, r_n, c_n, nc_n = (counts.get('Pass', 0), counts.get('Review', 0),
                           counts.get('Critical', 0), counts.get('Not computed', 0))
    comp_float = ((modules.get('cpli') or {}).get('kpis') or {}).get('project_total_float_days')

    def _tone(s):
        return '#8a93a0' if s is None else ('#2e8b57' if s >= 85 else '#e07b1a' if s >= 60 else '#c0392b')

    _stc = {'Pass': '#2e8b57', 'Review': '#e07b1a', 'Critical': '#c0392b'}
    comp = ''
    for s in subs:
        sc = '—' if s.get('score') is None else f"{_pnum(s['score'])}%"
        pts = _pnum(s.get('points'))
        st = s.get('status', '')
        needs = st in ('Review', 'Critical')
        prov = ' <span style="color:#c0392b;font-size:8px">(provisional)</span>' if s.get('provisional') else ''
        rowbg = ' style="background:#fdf6ee"' if needs else ''
        comp += (f'<tr{rowbg}><td>{_esc(s.get("name"))}{prov}</td><td class="num">{sc}</td>'
                 f'<td class="num">{_pnum(s.get("weight"))}</td><td class="num">{pts}</td>'
                 f'<td><span class="sev" style="background:{_stc.get(st, "#6b7a8d")}">{_esc(st)}</span></td></tr>')
    comp += (f'<tr><td>Circular logic <i>(gate)</i></td><td class="num">—</td><td class="num">—</td>'
             f'<td class="num">—</td><td><span class="sev" style="background:{"#2e8b57" if gate_clear else "#c0392b"}">'
             f'gate · {"clear" if gate_clear else "blocking"}</span></td></tr>')
    comp += (f'<tr style="background:#eef3f9;font-weight:700"><td>Overall Schedule Health</td>'
             f'<td class="num">{score_txt}%</td><td class="num">{_pnum(weight_covered)}</td>'
             f'<td class="num">—</td><td></td></tr>')

    # Checks-status chips + circular gate
    chips = (f'<span class="chip" style="background:#2e8b57">Pass {p_n}</span>'
             f'<span class="chip" style="background:#e07b1a">Review {r_n}</span>'
             f'<span class="chip" style="background:#c0392b">Critical {c_n}</span>'
             + (f'<span class="chip" style="background:#8a93a0">Not computed {nc_n}</span>' if nc_n else '')
             + f'<span class="chip" style="background:{"#2e8b57" if gate_clear else "#c0392b"}">'
               f'Circular gate {"clear" if gate_clear else "blocking"}</span>')

    # Headline stat cards
    cf_txt = '—' if comp_float is None else f'{_pnum(comp_float)} d'
    cf_col = '#8a93a0' if comp_float is None else ('#c0392b' if comp_float < 0 else '#2e8b57')
    headline = (
        f'<div class="stat"><div class="sv" style="color:{_tone(score)}">{score_txt}'
        f'<span>/100</span></div><div class="sk">Baseline health score</div></div>'
        f'<div class="stat"><div class="sv" style="color:{"#c0392b" if c_n else "#2e8b57"}">{c_n}</div>'
        f'<div class="sk">Critical sub-features</div></div>'
        f'<div class="stat"><div class="sv" style="color:{cf_col}">{cf_txt}</div>'
        f'<div class="sk">Completion total float (rule &ge; 0)</div></div>')

    areas = (h.get('problem_areas', {}) or {}).get('areas', [])
    area_rows = ''.join(f'<tr><td>{_esc(a.get("name"))}</td><td class="num">{a.get("findings")}</td>'
                        f'<td class="num">{_pnum(a.get("pct"))}%</td></tr>' for a in areas) \
        or '<tr><td colspan="3" class="empty">No findings to place — the logic is clean.</td></tr>'
    fixes = h.get('fix_first', [])
    fix_rows = ''.join(f'<tr><td class="num">{i + 1}</td><td>{_esc(f.get("name"))} ({_pnum(f.get("score"))}%)</td>'
                       f'<td class="num">{_pnum(f.get("weight"))}</td><td>{_esc(f.get("recommendation"))}</td>'
                       f'<td class="num">+~{_pnum(f.get("lift"))}</td></tr>' for i, f in enumerate(fixes)) \
        or '<tr><td colspan="5" class="empty">Every check is at target — nothing to fix first.</td></tr>'

    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Schedule Health Review — Summary — {_esc(meta.get('project_name', ''))}</title>
<style>
  @page {{ margin: 20mm 14mm; }}
  body {{ font-family:'Segoe UI',Arial,sans-serif; color:#1f2a37; font-size:11px; margin:0; }}
  .head {{ border-bottom:3px solid #17457a; padding-bottom:12px; margin-bottom:18px; }}
  .kicker {{ font-size:10px; letter-spacing:2px; color:#17457a; font-weight:700; text-transform:uppercase; }}
  .title {{ font-size:24px; font-weight:800; color:#0f2440; margin:3px 0 1px; }}
  .subtitle {{ font-size:12px; color:#5b6472; }}
  .meta {{ display:flex; flex-wrap:wrap; gap:3px 26px; margin-top:10px; font-size:11px; }}
  .meta span {{ color:#8a93a0; }}
  h2.sec {{ font-size:12px; text-transform:uppercase; letter-spacing:1px; color:#17457a; border-bottom:1px solid #dbe1e8; padding-bottom:4px; margin:22px 0 10px; }}
  .top3 {{ display:flex; gap:12px; align-items:stretch; }}
  .card3 {{ border:1px solid #e2e7ee; border-radius:8px; padding:13px 15px; background:#fafbfc; }}
  .card3.gauge {{ flex:1.5; display:flex; gap:18px; align-items:center; }}
  .card3.mid {{ flex:1.1; }} .card3.head3 {{ flex:1; }}
  .ct {{ font-size:9.5px; text-transform:uppercase; letter-spacing:.6px; color:#17457a; font-weight:700; margin-bottom:9px; }}
  .score-num {{ font-size:46px; font-weight:800; line-height:1; }}
  .score-den {{ font-size:11px; color:#8a93a0; }}
  .verdict-badge {{ display:inline-block; padding:4px 14px; border-radius:20px; font-size:12px; font-weight:700; color:#fff; }}
  .statement {{ font-size:11px; color:#31414f; line-height:1.55; margin-top:8px; }}
  .chip {{ display:inline-block; padding:3px 9px; border-radius:12px; font-size:9px; font-weight:700; color:#fff; margin:0 4px 5px 0; }}
  .bands {{ display:flex; gap:4px; margin-top:6px; }}
  .bd {{ flex:1; text-align:center; font-size:8.5px; font-weight:700; padding:3px 2px; border-radius:4px; color:#fff; }}
  .bd-c {{ background:#c0392b; }} .bd-r {{ background:#e07b1a; }} .bd-p {{ background:#2e8b57; }}
  .bnote {{ font-size:8.5px; color:#8a93a0; margin-top:6px; line-height:1.45; }}
  .stat {{ display:flex; align-items:baseline; gap:9px; padding:6px 0; border-bottom:1px solid #eef1f5; }}
  .stat:last-child {{ border-bottom:0; }}
  .stat .sv {{ font-size:22px; font-weight:800; }} .stat .sv span {{ font-size:11px; color:#8a93a0; font-weight:600; }}
  .stat .sk {{ font-size:9.5px; color:#8a93a0; }}
  table {{ width:100%; border-collapse:collapse; font-size:10.5px; margin-top:4px; }}
  thead {{ display:table-header-group; }}
  th {{ background:#26517d; color:#fff; text-align:left; padding:7px 9px; font-weight:600; font-size:9.5px; }}
  td {{ padding:6px 9px; border-bottom:1px solid #eef1f5; vertical-align:top; }}
  tbody tr:nth-child(even) {{ background:#f7f9fb; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .sev {{ display:inline-block; padding:1px 8px; border-radius:4px; color:#fff; font-weight:700; font-size:9px; }}
  .empty {{ color:#6b7480; font-style:italic; text-align:center; padding:12px; }}
  .grid2 {{ display:flex; gap:16px; align-items:flex-start; }} .grid2 > div {{ flex:1; }}
  .concl {{ border-left:4px solid #17457a; background:#f4f8fd; border-radius:0 8px 8px 0; padding:13px 16px; font-size:11.5px; line-height:1.6; color:#25313f; margin-top:6px; }}
  .dcma {{ font-size:10px; color:#5b6472; font-style:italic; margin-top:6px; }}
  .foot {{ border-top:1px solid #dbe1e8; margin-top:20px; padding-top:8px; font-size:9px; color:#8a93a0; }}
</style></head>
<body>
  <div class="head">
    <div class="kicker">Schedule Health Review · Summary</div>
    <div class="title">Overall Schedule Health</div>
    <div class="subtitle">The weighted roll-up of every sub-feature</div>
    <div class="meta">
      <div><span>Project:</span> {_esc(meta.get('project_name', ''))}</div>
      <div><span>Data Date:</span> {_esc(meta.get('data_date', ''))}</div>
      <div><span>Report Date:</span> {_esc(meta.get('report_date', ''))}</div>
      <div><span>Schedule File:</span> {_esc(meta.get('source_file', ''))}</div>
    </div>
  </div>

  <div class="top3">
    <div class="card3 gauge">
      <div style="text-align:center">
        <div class="score-num" style="color:{color}">{score_txt}</div>
        <div class="score-den">/ 100 · {_esc(grade)}</div>
      </div>
      <div>
        <div class="verdict-badge" style="background:{color}">{_esc(verdict)}</div>
        <div class="statement">Overall <b>Schedule Health</b> — the weighted roll-up of every sub-feature.<br>{_esc(statement)}</div>
      </div>
    </div>
    <div class="card3 mid">
      <div class="ct">Checks status &nbsp;·&nbsp; {total} sub-features</div>
      <div>{chips}</div>
      <div class="bands"><div class="bd bd-c">Critical &lt; 90</div><div class="bd bd-r">Review 90–95</div><div class="bd bd-p">Pass &ge; 95</div></div>
      <div class="bnote">How status is decided — each check's score against the per-check bands. A check below 95 needs review; below 90 is critical. Per-check targets adjust where DCMA differs — e.g. FS &ge; 90%. The overall baseline is submit-ready at &ge; 80%.</div>
    </div>
    <div class="card3 head3">
      <div class="ct">Headline</div>
      {headline}
    </div>
  </div>

  <h2 class="sec">Sub-feature scores &times; your weights (worst first)</h2>
  <table><thead><tr><th>Sub-feature</th><th class="num">Score</th><th class="num">Weight</th><th class="num">Points</th><th>Status</th></tr></thead>
    <tbody>{comp}</tbody></table>
  <div class="dcma">Overall Schedule Health = &Sigma; (score &times; weight) over the {_pnum(weight_covered)} weight covered = <b>{score_txt}</b>. Amber rows are the sub-features to review before submission.</div>

  <div class="grid2">
    <div>
      <h2 class="sec">Where the problems are</h2>
      <table><thead><tr><th>Discipline</th><th class="num">Findings</th><th class="num">% of total</th></tr></thead>
        <tbody>{area_rows}</tbody></table>
    </div>
    <div>
      <h2 class="sec">Fix these first</h2>
      <table><thead><tr><th class="num">#</th><th>Sub-feature</th><th class="num">Wt</th><th>Recommendation</th><th class="num">Lift</th></tr></thead>
        <tbody>{fix_rows}</tbody></table>
    </div>
  </div>

  <h2 class="sec">Conclusion</h2>
  <div class="concl">{_esc(statement)}</div>

  <div class="foot">Schedule Health Review &middot; Summary &nbsp;&middot;&nbsp; {_esc(meta.get('project_name', ''))}</div>
</body></html>'''


def render_module_report(module_result, meta, sections=None):
    m = module_result
    # Float Analysis has its own management-dashboard layout (V2 redesign).
    if m.get('module') == 'float':
        from p6_audit.float_report import render_float_report
        return render_float_report(m, meta, sections)
    name = m.get('name', 'Schedule Health Review')
    subtitle = ('Open / Broken Logic Assessment' if m['module'] == 'dangling'
                else 'Excessive Total Float Assessment' if m['module'] == 'float'
                else 'Every relationship lag & lead, with a planner justification' if m['module'] == 'lag_lead'
                else 'Consultant Review Report — Schedule Logic Inconsistency Assessment')
    is_lag = m['module'] == 'lag_lead'
    kicker = 'Lag Report' if is_lag else 'Schedule Health Review · Module Report'
    title_txt = 'Lag Report' if is_lag else name
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
  ul.recs {{ margin: 4px 0 0; padding-left: 18px; }}
  ul.recs li {{ margin: 3px 0; font-size: 11px; }}
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
  .lagsum {{ font-size: 12px; color: #5b6472; margin: 2px 0 6px; }}
  .lagsum b {{ color: #0f2440; }}
  .lcharts {{ display: flex; gap: 12px; align-items: stretch; flex-wrap: wrap; }}
  .lcard {{ flex: 1; min-width: 200px; border: 1px solid #e8ecf1; border-radius: 8px; padding: 11px 13px; }}
  .lch {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: .5px; color: #8a93a0; font-weight: 700; margin-bottom: 10px; }}
  .lbar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }}
  .lbar .lbl {{ width: 76px; font-size: 10px; color: #25313f; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .lbar .trk {{ flex: 1; height: 8px; background: #eef1f5; border-radius: 4px; overflow: hidden; }}
  .lbar .trk i {{ display: block; height: 100%; background: #26517d; border-radius: 4px; }}
  .lbar .lval {{ width: 56px; text-align: right; font-size: 9.5px; color: #6b7480; white-space: nowrap; }}
  .lbarS {{ margin-bottom: 9px; }}
  .lblS {{ font-size: 10px; color: #25313f; margin-bottom: 3px; line-height: 1.3; }}
  .lineS {{ display: flex; align-items: center; gap: 8px; }}
  .lineS .trk {{ flex: 1; height: 8px; background: #eef1f5; border-radius: 4px; overflow: hidden; }}
  .lineS .trk i {{ display: block; height: 100%; background: #26517d; border-radius: 4px; }}
  .lineS .lval {{ width: 56px; text-align: right; font-size: 9.5px; color: #6b7480; white-space: nowrap; }}
  .lmut {{ color: #8a93a0; font-size: 10px; }}
  .ldonut {{ display: flex; align-items: center; gap: 12px; }}
  .lleg {{ font-size: 10px; color: #25313f; flex: 1; }}
  .lleg > div {{ display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }}
  .lleg .d {{ width: 8px; height: 8px; border-radius: 2px; display: inline-block; }}
  .lleg b {{ margin-left: auto; font-weight: 700; }}
</style></head>
<body>
  <div class="head">
    <div class="kicker">{_esc(kicker)}</div>
    <div class="title">{_esc(title_txt)}</div>
    <div class="subtitle">{_esc(subtitle)}</div>
    <div class="meta">
      <div><span>Project:</span> {_esc(meta.get('project_name', ''))}</div>
      <div><span>Data Date:</span> {_esc(meta.get('data_date', ''))}</div>
      <div><span>Report Date:</span> {_esc(meta.get('report_date', ''))}</div>
      <div><span>Schedule File:</span> {_esc(meta.get('source_file', ''))}</div>
    </div>
  </div>

  {_sections(m, sections)}

  <div class="foot">
    {'This Lag Report lists every relationship lag and lead in the schedule, worst first, with the planner&rsquo;s own justification for the ones over the long-lag threshold or using a lead. Advisory only &mdash; schedule logic is never edited.' if is_lag else f'This report covers the <b>{_esc(name)}</b> module only, in isolation from other Schedule Audit checks and from cost / earned-value / progress. Module score is derived from the module KPI percentage on the approved band curve. Findings are engineering guidance and require planner verification.' + _scope_note(m)} &nbsp;·&nbsp; {_esc(meta.get('project_name', ''))} · {_esc(title_txt)}
  </div>
</body></html>'''
