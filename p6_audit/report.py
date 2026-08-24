"""Standalone consultant-grade report for a single Schedule Audit module.

One module = one report. Never mixed with another module, EVM, cost, or
progress. Rendered to HTML, then to PDF by the caller (Chrome headless).
Detailed-findings tables use <thead>, so headers repeat on every printed page.
"""
import html as _html

from p6_audit.presentation import build_presentation
import report_theme

_SEV = {'Critical': report_theme.var('rpt-bad'), 'High': report_theme.var('rpt-warn'),
        'Medium': report_theme.var('rpt-warn'), 'Low': report_theme.var('rpt-muted')}
_GRADE = {'Excellent': report_theme.var('rpt-good'), 'Acceptable': report_theme.var('rpt-warn'),
          'Needs Attention': report_theme.var('rpt-warn'), 'Critical': report_theme.var('rpt-bad')}

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
    return f'<span class="sev" style="background:{_SEV.get(sev, report_theme.var("rpt-muted"))}">{_esc(sev)}</span>'


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
    color = _GRADE.get(grade, report_theme.var('rpt-muted'))
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
    color = _GRADE.get(grade, report_theme.var('rpt-muted'))
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
          <span><span class="dot" style="background:{report_theme.var('rpt-good')}"></span>Excellent &le; 2%</span>
          <span><span class="dot" style="background:{report_theme.var('rpt-warn')}"></span>Acceptable 2&ndash;5%</span>
          <span><span class="dot" style="background:{report_theme.var('rpt-warn')}"></span>Needs Attention 5&ndash;8%</span>
          <span><span class="dot" style="background:{report_theme.var('rpt-bad')}"></span>Critical &gt; 8%</span>
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
    cpi_color = report_theme.var('rpt-bad') if cpi == 'Yes' else report_theme.var('rpt-good')
    cdi_color = {'Direct Impact': report_theme.var('rpt-bad'), 'Potential Impact': report_theme.var('rpt-warn'),
                 'No Impact': report_theme.var('rpt-good')}.get(cdi, report_theme.var('rpt-muted'))
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
    _muted, _warn, _bad, _thbg = (report_theme.var('rpt-muted'), report_theme.var('rpt-warn'),
                                   report_theme.var('rpt-bad'), report_theme.var('rpt-th-bg'))
    for val, color in ((normal, _muted), (longp, _warn), (leads, _bad)):
        if val and total:
            ln = C * val / total
            segs.append(f'<circle cx="50" cy="50" r="40" fill="none" stroke="{color}" stroke-width="15" '
                        f'stroke-dasharray="{ln:.1f} {C:.1f}" stroke-dashoffset="{-off:.1f}"/>')
            off += ln
    return (f'<div class="ldonut"><svg width="86" height="86" viewBox="0 0 100 100">'
            f'<g transform="rotate(-90 50 50)">{"".join(segs)}</g>'
            f'<text x="50" y="48" text-anchor="middle" font-size="18" font-weight="800" fill="{report_theme.var("rpt-ink")}">{need}</text>'
            f'<text x="50" y="62" text-anchor="middle" font-size="8" fill="{_muted}">to justify</text></svg>'
            f'<div class="lleg">'
            f'<div><span class="d" style="background:{_muted}"></span>Normal &le;{thr} wd <b>{normal}</b></div>'
            f'<div><span class="d" style="background:{_warn}"></span>Long &gt;{thr} wd <b>{longp}</b></div>'
            f'<div><span class="d" style="background:{_bad}"></span>Leads <b>{leads}</b></div>'
            f'<div><span class="d" style="background:{_thbg}"></span>On critical path <b>{k.get("critical_count", 0)}</b></div>'
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
    color = _GRADE.get(grade, report_theme.var('rpt-muted'))
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
            bar = f'<span style="position:absolute;left:{x:.1f}%;top:2px;width:9px;height:9px;background:{report_theme.var("rpt-good")};transform:translateX(-50%) rotate(45deg)"></span>'
        else:
            color = report_theme.var('rpt-bad') if (f.get('total_float_days') or 0) <= 0 else report_theme.var('rpt-accent')
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
                         f'font-size:7.5px;color:{report_theme.var("rpt-th-ink")};font-weight:400;transform:translateX(-50%);white-space:nowrap">'
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


def render_summary_report(health, meta, sections=None, modules=None, completion_float=None, theme='light'):
    """Standalone PDF for the Schedule Health Review Summary — the weighted roll-up.
    Mirrors the on-screen dashboard exactly: overall score + verdict, checks-status
    (donut + counts + circular gate + status bands), headline stats (incl. completion
    total float), sub-feature composition, problem areas, fix-first and conclusion."""
    h = health or {}
    meta = meta or {}
    modules = modules or {}
    score = h.get('score')
    score_txt = _pnum(score)
    grade = h.get('grade', '') or ''
    color = _GRADE.get(grade, report_theme.var('rpt-accent'))
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
    comp_float = (completion_float if completion_float is not None
                  else ((modules.get('cpli') or {}).get('kpis') or {}).get('project_total_float_days'))

    # Checks-status donut (conic-gradient) — the same chart the screen shows.
    _t = max(1, total)
    a1 = 100.0 * p_n / _t
    a2 = a1 + 100.0 * r_n / _t
    a3 = a2 + 100.0 * c_n / _t
    _GOOD, _WARN, _BAD, _MUT = ('var(--rpt-good)', 'var(--rpt-warn)', 'var(--rpt-bad)', 'var(--rpt-muted)')
    _ACC, _GOODBG, _WARNBG, _BADBG, _ACCSOFT = ('var(--rpt-accent)', 'var(--rpt-good-bg)',
                                                'var(--rpt-warn-bg)', 'var(--rpt-bad-bg)', 'var(--rpt-accent-soft)')
    donut = (f'<div style="width:74px;height:74px;border-radius:50%;flex-shrink:0;'
             f'background:conic-gradient({_GOOD} 0 {a1:.1f}%,{_WARN} {a1:.1f}% {a2:.1f}%,'
             f'{_BAD} {a2:.1f}% {a3:.1f}%,{_MUT} {a3:.1f}% 100%)">'
             f'<div style="width:46px;height:46px;margin:14px;background:var(--rpt-bg);border-radius:50%;'
             f'display:flex;flex-direction:column;align-items:center;justify-content:center">'
             f'<b style="font-size:17px;color:var(--rpt-ink);line-height:1">{p_n}</b>'
             f'<span style="font-size:7px;color:var(--rpt-muted)">of {total} pass</span></div></div>')
    _leg = [(_GOOD, 'Pass', p_n), (_WARN, 'Review', r_n), (_BAD, 'Critical', c_n)]
    if nc_n:
        _leg.append((_MUT, 'Not computed', nc_n))
    _leg.append((_GOOD if gate_clear else _BAD, 'Circular gate', 'clear' if gate_clear else 'blocking'))
    donut_legend = ''.join(
        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;font-size:9.5px">'
        f'<span style="width:9px;height:9px;border-radius:2px;background:{col};display:inline-block"></span>'
        f'{lab} <b style="margin-left:auto">{val}</b></div>' for col, lab, val in _leg)

    def _tone(s):
        return _MUT if s is None else (_GOOD if s >= 85 else _WARN if s >= 60 else _BAD)

    def _scol(st):
        return {'Pass': _GOOD, 'Review': _WARN, 'Critical': _BAD}.get(st, _MUT)

    # Sub-feature composition as BARS — the same layout the screen shows (not a table).
    comp = ('<div class="chead"><span>Sub-feature</span><span>Score</span>'
            '<span>Score</span><span>Wt</span><span>Pts</span></div>')
    for s in subs:
        st = s.get('status', '')
        sc_val = s.get('score')
        barw = 0.0 if sc_val is None else max(0.0, min(100.0, sc_val))
        col = _scol(st)
        sc = '—' if sc_val is None else f"{_pnum(sc_val)}%"
        needs = st in ('Review', 'Critical')
        revtag = (f'<span class="revtag" style="background:{_BADBG if st == "Critical" else _WARNBG};'
                  f'color:{col}">{"needs review" if st == "Critical" else "review"}</span>') if needs else ''
        prov = f' <span style="color:{_BAD};font-size:8px">(provisional)</span>' if s.get('provisional') else ''
        comp += (f'<div class="crow{" crow-review" if needs else ""}">'
                 f'<div class="nm"><span class="dot" style="background:{col}"></span>{_esc(s.get("name"))}{prov} {revtag}</div>'
                 f'<div class="bar"><i style="width:{barw:.0f}%;background:{col}"></i></div>'
                 f'<div class="sc">{sc}</div><div class="wt">{_pnum(s.get("weight"))}</div>'
                 f'<div class="pt">{_pnum(s.get("points"))}</div></div>')
    gcol = _GOOD if gate_clear else _BAD
    comp += (f'<div class="crow"><div class="nm"><span class="dot" style="background:{gcol}"></span>'
             f'Circular logic <span class="revtag" style="background:{_ACCSOFT};color:{gcol}">'
             f'gate · {"clear" if gate_clear else "blocking"}</span></div>'
             f'<div class="bar"><i style="width:{100 if gate_clear else 0}%;background:{gcol}"></i></div>'
             f'<div class="sc">—</div><div class="wt">—</div><div class="pt">—</div></div>')
    comp_total = (f'<div class="ctot"><div class="tl">Overall Schedule Health</div><div></div><div></div>'
                  f'<div class="tw">{_pnum(weight_covered)}</div>'
                  f'<div class="tv" style="color:{_tone(score)}">{score_txt}</div></div>')

    # Headline stat cards
    cf_txt = '—' if comp_float is None else f'{_pnum(comp_float)} d'
    cf_col = _MUT if comp_float is None else (_BAD if comp_float < 0 else _GOOD)
    headline = (
        f'<div class="stat"><div class="sv" style="color:{_tone(score)}">{score_txt}'
        f'<span>/100</span></div><div class="sk">Baseline health score</div></div>'
        f'<div class="stat"><div class="sv" style="color:{_BAD if c_n else _GOOD}">{c_n}</div>'
        f'<div class="sk">Critical sub-features</div></div>'
        f'<div class="stat"><div class="sv" style="color:{cf_col}">{cf_txt}</div>'
        f'<div class="sk">Completion total float (rule &ge; 0)</div></div>')

    # Where the problems are — horizontal bars (defect share), like the screen.
    areas = (h.get('problem_areas', {}) or {}).get('areas', [])
    pa_max = max([1.0] + [(a.get('pct') or 0) for a in areas])
    problem_bars = ''.join(
        f'<div class="wb"><div class="l" title="{_esc(a.get("name"))}">{_esc(a.get("name"))}</div>'
        f'<div class="wbt"><i style="width:{round(100.0 * (a.get("pct") or 0) / pa_max)}%;'
        f'background:{_BAD if i == 0 else (_WARN if i < 3 else _ACC)}"></i></div>'
        f'<div class="c">{_pnum(a.get("pct"))}%</div></div>' for i, a in enumerate(areas)) \
        or '<div class="empty2">No findings to place — the logic is clean.</div>'

    # Fix these first — ranked list with a lift badge, like the screen.
    fixes = h.get('fix_first', [])
    fix_list = ''.join(
        f'<div class="fix"><div class="rk">{i + 1}</div>'
        f'<div class="fx"><b>{_esc(f.get("name"))} {_pnum(f.get("score"))}%</b> '
        f'<span class="sub">(wt {_pnum(f.get("weight"))})</span>'
        f'<div class="sub">{_esc(f.get("recommendation"))}</div></div>'
        f'<span class="lift">+~{_pnum(f.get("lift"))}</span></div>' for i, f in enumerate(fixes)) \
        or '<div class="empty2">Every check is at target — nothing to fix first.</div>'

    # ── Report-content selector (Preview = PDF = Print): render only ticked parts ──
    sel = set(sections) if sections else None
    def on(key):
        return sel is None or key in sel

    top_cards = []
    if on('overview'):
        top_cards.append(f'''<div class="card3 gauge">
      <div style="text-align:center">
        <div class="score-num" style="color:{color}">{score_txt}</div>
        <div class="score-den">/ 100 · {_esc(grade)}</div>
      </div>
      <div>
        <div class="verdict-badge" style="background:{color}">{_esc(verdict)}</div>
        <div class="statement">Overall <b>Schedule Health</b> — the weighted roll-up of every sub-feature.<br>{_esc(statement)}</div>
      </div>
    </div>''')
    if on('checks'):
        top_cards.append(f'''<div class="card3 mid">
      <div class="ct">Checks status &nbsp;·&nbsp; {total} sub-features</div>
      <div style="display:flex;gap:14px;align-items:center">{donut}<div style="flex:1">{donut_legend}</div></div>
      <div class="bands"><div class="bd bd-c">Critical &lt; 90</div><div class="bd bd-r">Review 90–95</div><div class="bd bd-p">Pass &ge; 95</div></div>
      <div class="bnote">How status is decided — each check's score against the per-check bands. A check below 95 needs review; below 90 is critical. Per-check targets adjust where DCMA differs — e.g. FS &ge; 90%. The overall baseline is submit-ready at &ge; 80%.</div>
    </div>''')
    if on('headline'):
        top_cards.append(f'''<div class="card3 head3">
      <div class="ct">Headline</div>
      {headline}
    </div>''')
    top_html = f'<div class="top3">{"".join(top_cards)}</div>' if top_cards else ''

    composition_html = ''
    if on('composition'):
        composition_html = (
            '<h2 class="sec">Sub-feature scores &times; your weights (worst first)</h2>'
            f'<div class="comp">{comp}{comp_total}</div>'
            f'<div class="dcma">Overall Schedule Health = &Sigma; (score &times; weight) over the '
            f'{_pnum(weight_covered)} weight covered = <b>{score_txt}</b>. '
            'Amber rows are the sub-features to review before submission.</div>')

    grid_cells = []
    if on('problems'):
        grid_cells.append('<div><h2 class="sec">Where the problems are '
                          '<span class="rlab">defect share by discipline</span></h2>'
                          f'{problem_bars}</div>')
    if on('fixes'):
        grid_cells.append('<div><h2 class="sec">Fix these first '
                          '<span class="rlab">biggest lift</span></h2>'
                          f'{fix_list}</div>')
    grid_html = f'<div class="grid2">{"".join(grid_cells)}</div>' if grid_cells else ''

    conclusion_html = (f'<h2 class="sec">Conclusion</h2><div class="concl">{_esc(statement)}</div>'
                       if on('conclusion') else '')

    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Schedule Health Review — Summary — {_esc(meta.get('project_name', ''))}</title>
<style>
  @page {{ margin: 20mm 14mm; }}
  body {{ font-family:'Segoe UI',Arial,sans-serif; color:var(--rpt-ink); font-size:11px; margin:0; }}
  .head {{ border-bottom:3px solid var(--rpt-accent); padding-bottom:12px; margin-bottom:18px; }}
  .kicker {{ font-size:10px; letter-spacing:2px; color:var(--rpt-accent); font-weight:700; text-transform:uppercase; }}
  .title {{ font-size:24px; font-weight:800; color:var(--rpt-ink); margin:3px 0 1px; }}
  .subtitle {{ font-size:12px; color:var(--rpt-ink-soft); }}
  .meta {{ display:flex; flex-wrap:wrap; gap:3px 26px; margin-top:10px; font-size:11px; }}
  .meta span {{ color:var(--rpt-muted); }}
  h2.sec {{ font-size:12px; text-transform:uppercase; letter-spacing:1px; color:var(--rpt-accent); border-bottom:1px solid var(--rpt-hair-strong); padding-bottom:4px; margin:22px 0 10px; }}
  .top3 {{ display:flex; gap:12px; align-items:stretch; }}
  .card3 {{ border:1px solid var(--rpt-edge); border-radius:8px; padding:13px 15px; background:var(--rpt-surface); flex:1; }}
  .card3.gauge {{ flex:1.5; display:flex; gap:18px; align-items:center; }}
  .card3.mid {{ flex:1.1; }} .card3.head3 {{ flex:1; }}
  .ct {{ font-size:9.5px; text-transform:uppercase; letter-spacing:.6px; color:var(--rpt-accent); font-weight:700; margin-bottom:9px; }}
  .score-num {{ font-size:46px; font-weight:800; line-height:1; }}
  .score-den {{ font-size:11px; color:var(--rpt-muted); }}
  .verdict-badge {{ display:inline-block; padding:4px 14px; border-radius:20px; font-size:12px; font-weight:700; color:var(--rpt-accent-ink); }}
  .statement {{ font-size:11px; color:var(--rpt-ink-soft); line-height:1.55; margin-top:8px; }}
  .bands {{ display:flex; gap:4px; margin-top:6px; }}
  .bd {{ flex:1; text-align:center; font-size:8.5px; font-weight:700; padding:3px 2px; border-radius:4px; color:var(--rpt-accent-ink); }}
  .bd-c {{ background:var(--rpt-bad); }} .bd-r {{ background:var(--rpt-warn); }} .bd-p {{ background:var(--rpt-good); }}
  .bnote {{ font-size:8.5px; color:var(--rpt-muted); margin-top:6px; line-height:1.45; }}
  .stat {{ display:flex; align-items:baseline; gap:9px; padding:6px 0; border-bottom:1px solid var(--rpt-hair); }}
  .stat:last-child {{ border-bottom:0; }}
  .stat .sv {{ font-size:22px; font-weight:800; }} .stat .sv span {{ font-size:11px; color:var(--rpt-muted); font-weight:600; }}
  .stat .sk {{ font-size:9.5px; color:var(--rpt-muted); }}
  table {{ width:100%; border-collapse:collapse; font-size:10.5px; margin-top:4px; }}
  thead {{ display:table-header-group; }}
  th {{ background:var(--rpt-th-bg); color:var(--rpt-th-ink); text-align:left; padding:7px 9px; font-weight:600; font-size:9.5px; }}
  td {{ padding:6px 9px; border-bottom:1px solid var(--rpt-hair); vertical-align:top; }}
  tbody tr:nth-child(even) {{ background:var(--rpt-surface); }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .sev {{ display:inline-block; padding:1px 8px; border-radius:4px; color:var(--rpt-accent-ink); font-weight:700; font-size:9px; }}
  .empty {{ color:var(--rpt-muted); font-style:italic; text-align:center; padding:12px; }}
  .empty2 {{ color:var(--rpt-muted); font-style:italic; font-size:10px; padding:8px 0; }}
  .rlab {{ font-size:9px; font-weight:600; color:var(--rpt-muted); text-transform:none; letter-spacing:0; }}
  /* Sub-feature composition — bars (mirrors the on-screen layout) */
  .chead, .crow, .ctot {{ display:grid; grid-template-columns:1.7fr 2fr 52px 32px 40px; align-items:center; gap:12px; }}
  .chead {{ font-size:8.5px; color:var(--rpt-muted); text-transform:uppercase; letter-spacing:.4px; font-weight:700; padding-bottom:6px; border-bottom:1px solid var(--rpt-hair-strong); }}
  .chead span:nth-child(n+2) {{ text-align:right; }}
  .crow {{ padding:6px 0; border-bottom:1px solid var(--rpt-hair); }}
  .crow-review {{ background:var(--rpt-warn-bg); }}
  .nm {{ font-size:10.5px; font-weight:600; display:flex; align-items:center; gap:7px; }}
  .dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; display:inline-block; }}
  .revtag {{ font-size:8px; font-weight:700; padding:1px 6px; border-radius:8px; white-space:nowrap; }}
  .bar {{ height:8px; background:var(--rpt-hair); border-radius:5px; overflow:hidden; }} .bar > i {{ display:block; height:100%; border-radius:5px; }}
  .sc {{ text-align:right; font-size:11px; font-weight:800; }} .wt {{ text-align:right; font-size:9.5px; color:var(--rpt-muted); }} .pt {{ text-align:right; font-size:10px; font-weight:700; color:var(--rpt-accent); }}
  .ctot {{ padding-top:9px; margin-top:2px; border-top:2px solid var(--rpt-hair-strong); }}
  .ctot .tl {{ font-size:11px; font-weight:800; }} .ctot .tw {{ text-align:right; font-weight:700; font-size:10px; }} .ctot .tv {{ text-align:right; font-size:14px; font-weight:800; }}
  /* Where the problems are — bars */
  .wb {{ display:grid; grid-template-columns:152px 1fr 40px; align-items:center; gap:10px; margin:7px 0; }}
  .wb .l {{ font-size:10px; font-weight:600; white-space:normal; overflow-wrap:anywhere; line-height:1.2; }} .wb .c {{ text-align:right; font-size:10px; color:var(--rpt-ink-soft); font-weight:700; }}
  .wbt {{ height:12px; background:var(--rpt-hair); border-radius:4px; overflow:hidden; }} .wbt > i {{ display:block; height:100%; border-radius:4px; }}
  /* Fix these first — ranked list */
  .fix {{ display:flex; gap:10px; padding:7px 0; border-bottom:1px solid var(--rpt-hair); font-size:10.5px; align-items:flex-start; }}
  .fix .rk {{ width:19px; height:19px; flex:none; border-radius:50%; background:var(--rpt-accent-soft); border:1px solid var(--rpt-hair-strong); display:flex; align-items:center; justify-content:center; font-size:9.5px; font-weight:700; color:var(--rpt-ink-soft); }}
  .fix .sub {{ color:var(--rpt-ink-soft); font-size:9.5px; }} .fix .lift {{ margin-left:auto; font-size:9px; font-weight:700; color:var(--rpt-good); background:var(--rpt-good-bg); border-radius:5px; padding:2px 8px; white-space:nowrap; align-self:center; }}
  .grid2 {{ display:flex; gap:16px; align-items:flex-start; }} .grid2 > div {{ flex:1; }}
  .concl {{ border-left:4px solid var(--rpt-accent); background:var(--rpt-accent-soft); border-radius:0 8px 8px 0; padding:13px 16px; font-size:11.5px; line-height:1.6; color:var(--rpt-ink); margin-top:6px; }}
  .dcma {{ font-size:10px; color:var(--rpt-ink-soft); font-style:italic; margin-top:6px; }}
  .foot {{ border-top:1px solid var(--rpt-hair-strong); margin-top:20px; padding-top:8px; font-size:9px; color:var(--rpt-muted); }}
</style>
{report_theme.theme_style_tag(theme)}
</head>
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
  {top_html}
  {composition_html}
  {grid_html}
  {conclusion_html}
  <div class="foot">Schedule Health Review &middot; Summary &nbsp;&middot;&nbsp; {_esc(meta.get('project_name', ''))}</div>
</body></html>'''


def render_module_report(module_result, meta, sections=None, theme='light'):
    m = module_result
    # Float Analysis has its own management-dashboard layout (V2 redesign).
    if m.get('module') == 'float':
        from p6_audit.float_report import render_float_report
        return render_float_report(m, meta, sections=sections, theme=theme)
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
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: var(--rpt-ink); font-size: 11px; margin: 0; }}
  .head {{ border-bottom: 3px solid var(--rpt-accent); padding-bottom: 12px; margin-bottom: 18px; }}
  .kicker {{ font-size: 10px; letter-spacing: 2px; color: var(--rpt-accent); font-weight: 700; text-transform: uppercase; }}
  .title {{ font-size: 24px; font-weight: 800; color: var(--rpt-ink); margin: 3px 0 1px; }}
  .subtitle {{ font-size: 12px; color: var(--rpt-ink-soft); }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 3px 26px; margin-top: 10px; font-size: 11px; }}
  .meta span {{ color: var(--rpt-muted); }}
  h2.sec {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--rpt-accent);
            border-bottom: 1px solid var(--rpt-hair); padding-bottom: 4px; margin: 22px 0 10px; }}
  .dash {{ display: flex; gap: 14px; align-items: stretch; }}
  .grade-card {{ border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 15px 16px; width: 200px;
                 flex-shrink: 0; text-align: center; background: var(--rpt-surface); }}
  .score-num {{ font-size: 42px; font-weight: 800; line-height: 1; }}
  .score-den {{ font-size: 11px; color: var(--rpt-muted); }}
  .grade-badge {{ display: inline-block; margin-top: 8px; padding: 4px 14px; border-radius: 20px;
                  font-size: 12px; font-weight: 700; color: var(--rpt-accent-ink); }}
  .verdict {{ font-size: 10.5px; color: var(--rpt-ink-soft); margin-top: 9px; line-height: 1.4; }}
  .kpis {{ flex: 1; display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; }}
  .kpi {{ border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 10px 12px; }}
  .kpi .k {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: .5px; color: var(--rpt-muted); font-weight: 700; }}
  .kpi .v {{ font-size: 21px; font-weight: 800; margin-top: 2px; color: var(--rpt-ink); }}
  .kpi .n {{ font-size: 9.5px; color: var(--rpt-muted); margin-top: 1px; }}
  .dcma {{ font-size: 10px; color: var(--rpt-ink-soft); margin-top: 8px; font-style: italic; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10px; margin-top: 2px; }}
  thead {{ display: table-header-group; }}   /* repeat header on every printed page */
  th {{ background: var(--rpt-th-bg); color: var(--rpt-th-ink); text-align: left; padding: 7px 8px; font-weight: 600; font-size: 9.5px; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid var(--rpt-hair); vertical-align: top; }}
  tbody tr:nth-child(even) {{ background: var(--rpt-surface); }}
  table.summary {{ max-width: 420px; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
  .mono {{ font-family: 'Consolas', monospace; white-space: nowrap; }}
  .mut {{ color: var(--rpt-muted); font-size: 9.5px; }}
  .sev {{ display: inline-block; padding: 1px 7px; border-radius: 4px; color: var(--rpt-accent-ink); font-weight: 700; font-size: 9px; white-space: nowrap; }}
  .empty {{ color: var(--rpt-muted); font-style: italic; }}
  ul.recs {{ margin: 4px 0 0; padding-left: 18px; }}
  ul.recs li {{ margin: 3px 0; font-size: 11px; }}
  .foot {{ border-top: 1px solid var(--rpt-hair); margin-top: 20px; padding-top: 8px; font-size: 9px; color: var(--rpt-muted); line-height: 1.5; }}
  /* Out of Sequence module */
  .kpis.k4 {{ grid-template-columns: repeat(4, 1fr); }}
  .kpi.crit {{ border-color: var(--rpt-bad); background: var(--rpt-bad-bg); }}
  .kpi.crit .v {{ color: var(--rpt-bad); }}
  .kpi.near {{ border-color: var(--rpt-warn); background: var(--rpt-warn-bg); }}
  .kpi.near .v {{ color: var(--rpt-warn); }}
  .slegend {{ border: 1px solid var(--rpt-edge); background: var(--rpt-surface); border-radius: 8px; padding: 9px 12px; margin-top: 10px; font-size: 9.5px; }}
  .slegend .t {{ font-size: 9px; text-transform: uppercase; letter-spacing: .6px; color: var(--rpt-accent); font-weight: 700; }}
  .slegend .d {{ color: var(--rpt-ink-soft); margin: 3px 0 6px; line-height: 1.4; }}
  .slegend .bands span {{ margin-right: 14px; }}
  .slegend .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 2px; vertical-align: -1px; margin-right: 3px; }}
  .stdref {{ font-size: 9.5px; color: var(--rpt-ink-soft); font-style: italic; margin-top: 9px; padding: 7px 11px;
             background: var(--rpt-accent-soft); border-left: 3px solid var(--rpt-accent); border-radius: 0 6px 6px 0; line-height: 1.45; }}
  .stdref b {{ color: var(--rpt-accent); font-style: normal; }}
  .pill {{ display: inline-block; padding: 1px 6px; border-radius: 10px; font-weight: 700; font-size: 8.5px; }}
  .pill.same {{ color: var(--rpt-muted); background: transparent; padding: 0; }}
  .pill.na {{ color: var(--rpt-muted); background: transparent; padding: 0; font-style: italic; }}
  .pill.change {{ color: var(--rpt-accent); background: var(--rpt-accent-soft); }}
  .pill.remove {{ color: var(--rpt-bad); background: var(--rpt-bad-bg); }}
  .badge2 {{ display: inline-block; padding: 1px 6px; border-radius: 4px; color: var(--rpt-accent-ink); font-weight: 700; font-size: 8px; white-space: nowrap; }}
  .badge2.c {{ background: var(--rpt-bad); }}
  .badge2.n {{ background: var(--rpt-warn); }}
  .cpi-wrap {{ display: flex; gap: 14px; align-items: stretch; flex-wrap: wrap; }}
  .cpi-wrap table {{ max-width: 360px; }}
  .vcards {{ display: flex; flex-direction: column; gap: 8px; justify-content: center; }}
  .vcard {{ border-radius: 8px; padding: 9px 14px; color: var(--rpt-accent-ink); min-width: 200px; }}
  .vcard .l {{ font-size: 8.5px; text-transform: uppercase; letter-spacing: .5px; opacity: .9; font-weight: 700; }}
  .vcard .v2 {{ font-size: 14px; font-weight: 800; margin-top: 1px; }}
  .concl {{ border-left: 4px solid var(--rpt-accent); background: var(--rpt-accent-soft); border-radius: 0 8px 8px 0; padding: 11px 15px; font-size: 11px; line-height: 1.55; color: var(--rpt-ink); }}
  .lagsum {{ font-size: 12px; color: var(--rpt-ink-soft); margin: 2px 0 6px; }}
  .lagsum b {{ color: var(--rpt-ink); }}
  .lcharts {{ display: flex; gap: 12px; align-items: stretch; flex-wrap: wrap; }}
  .lcard {{ flex: 1; min-width: 200px; border: 1px solid var(--rpt-edge); border-radius: 8px; padding: 11px 13px; }}
  .lch {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: .5px; color: var(--rpt-muted); font-weight: 700; margin-bottom: 10px; }}
  .lbar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }}
  .lbar .lbl {{ width: 76px; font-size: 10px; color: var(--rpt-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .lbar .trk {{ flex: 1; height: 8px; background: var(--rpt-chart-grid); border-radius: 4px; overflow: hidden; }}
  .lbar .trk i {{ display: block; height: 100%; background: var(--rpt-th-bg); border-radius: 4px; }}
  .lbar .lval {{ width: 56px; text-align: right; font-size: 9.5px; color: var(--rpt-muted); white-space: nowrap; }}
  .lbarS {{ margin-bottom: 9px; }}
  .lblS {{ font-size: 10px; color: var(--rpt-ink); margin-bottom: 3px; line-height: 1.3; }}
  .lineS {{ display: flex; align-items: center; gap: 8px; }}
  .lineS .trk {{ flex: 1; height: 8px; background: var(--rpt-chart-grid); border-radius: 4px; overflow: hidden; }}
  .lineS .trk i {{ display: block; height: 100%; background: var(--rpt-th-bg); border-radius: 4px; }}
  .lineS .lval {{ width: 56px; text-align: right; font-size: 9.5px; color: var(--rpt-muted); white-space: nowrap; }}
  .lmut {{ color: var(--rpt-muted); font-size: 10px; }}
  .ldonut {{ display: flex; align-items: center; gap: 12px; }}
  .lleg {{ font-size: 10px; color: var(--rpt-ink); flex: 1; }}
  .lleg > div {{ display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }}
  .lleg .d {{ width: 8px; height: 8px; border-radius: 2px; display: inline-block; }}
  .lleg b {{ margin-left: auto; font-weight: 700; }}
</style>
{report_theme.theme_style_tag(theme)}
</head>
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
