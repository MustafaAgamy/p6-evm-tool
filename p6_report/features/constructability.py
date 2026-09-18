"""Constructability Review — registered into the Global Print-Preview framework.

Every section that the one-shot ``p6_kb.exporters.render_html`` produced is exposed
here as a selectable ``ReportComponent``, reusing the exact same fragment renderers
and CSS from ``p6_kb.exporters`` so the framework output matches the legacy PDF
section-for-section. What changes is only that the user can now pick which sections
go in, and in what order — the picked set drives preview and PDF alike.

This is also the worked example other modules copy: register a spec builder that
returns the feature's title, CSS and an ordered list of components.
"""
from p6_kb import exporters as X
from p6_kb.scoring import STRENGTH_DISPLAY
from p6_report.registry import ReportComponent, ReportSpec, register

FEATURE = 'constructability'


def _verdict(report):
    v = report.get('verdict') or {}
    return (f'<div class="verdict"><div>'
            f'<div class="vt">{X._e(v.get("title"))}</div>'
            f'<div class="vd">{X._e(v.get("detail") or v.get("text"))}</div></div>'
            f'<div class="vr"><b>{X._e(report.get("project_type"))}</b></div></div>')


def _scorecard(report):
    s = report.get('score') or {}
    return (f'<div class="hero"><div class="scorebox">'
            f'<div class="n">{X._e(s.get("overall"))}</div>'
            f'<div class="b">{X._e(s.get("band_label"))}</div>'
            f'<div class="sl">Constructability Score</div></div>'
            f'{X._dims(s)}</div>')


def _legend(report):
    return X._band_legend((report.get('score') or {}).get('overall', 0))


def _projection(report):
    proj = report.get('projected')
    if not proj:
        return ''
    return (f'<div class="proj">What-if: correcting the flagged logic would raise the score to '
            f'~<b>{X._e(proj.get("overall"))}</b> ({X._e(proj.get("band_label"))}) — '
            f'{X._e(proj.get("basis"))}.</div>')


def _conclusion(report):
    c = report.get('conclusion')
    return f'<div class="foot">{X._e(c)}</div>' if c else ''


# Semantic colours as appearance tokens — (text, tint-background) — so the chips and
# score theme in all 6 appearance modes instead of a fixed light-mode hex.
_STRENGTH_TOK = {'strong': ('var(--rpt-bad)', 'var(--rpt-bad-bg)'),
                 'moderate': ('var(--rpt-warn)', 'var(--rpt-warn-bg)'),
                 'weak': ('var(--rpt-ink-soft)', 'var(--rpt-surface-2)'),
                 'insufficient': ('var(--rpt-muted)', 'var(--rpt-surface-2)')}
_BAND_TOK = {'green': 'var(--rpt-good)', 'amber': 'var(--rpt-warn)',
             'orange': 'var(--rpt-bad)', 'red': 'var(--rpt-bad)'}
_CONF_TOK = {'high': ('var(--rpt-good)', 'var(--rpt-good-bg)'),
             'medium': ('var(--rpt-warn)', 'var(--rpt-warn-bg)'),
             'low': ('var(--rpt-ink-soft)', 'var(--rpt-surface-2)')}

_CONF_LEGEND = [('High', 'strong and consistent evidence from the schedule'),
                ('Medium', 'sufficient evidence, but some ambiguity remains'),
                ('Low', 'limited or conflicting evidence')]
_SCORE_LEGEND = [('green', '80–100', 'Low Risk'), ('amber', '60–79', 'Moderate Risk'),
                 ('orange', '40–59', 'Significant Risk'), ('red', '0–39', 'High Risk')]
_SEV_LEGEND = [('strong', 'Strong', 'significant execution / constructability risk'),
               ('moderate', 'Moderate', 'meaningful sequencing concern'),
               ('weak', 'Low', 'minor or lower-impact concern')]


def _sev_chip(strength):
    col, bg = _STRENGTH_TOK.get(strength, ('var(--rpt-ink-soft)', 'var(--rpt-surface-2)'))
    return (f'<span class="schip" style="background:{bg};color:{col};border-color:{col}">'
            f'{X._e(STRENGTH_DISPLAY.get(strength, strength))}</span>')


def _risk_summary_line(score, findings):
    """One plain sentence a junior planner can read at a glance."""
    n = len(findings)
    if not n:
        return "No constructability sequencing risks were detected against the current logic."
    strong = sum(1 for f in findings if f.get('strength') == 'strong')
    systems = []
    for f in findings:
        s = f.get('system')
        if s and s not in systems:
            systems.append(s)
    where = ', '.join(systems[:4]) + ('…' if len(systems) > 4 else '')
    lead = (f"{strong} strong " if strong else "") + f"of {n} finding(s)"
    band = (score or {}).get('band_label', '')
    tail = (" — resolve the strong findings before baseline." if strong
            else " — review before baseline.")
    return f"{band}: {lead} across {where}{tail}"


def _project_risk_summary(report):
    """Section 1 — a compact risk summary: project type, confidence (+legend), the
    constructability risk score (+legend + how-calculated), total findings, and a one-
    line overall risk statement. Everything a reader needs to orient in a few seconds."""
    a = report.get('archetype') or {}
    s = report.get('v2_score') or {}
    fs = report.get('v2_findings') or []
    if not a and not s:
        return ''
    conf = (a.get('confidence') or 'low').lower()
    cfg_col, cfg_bg = _CONF_TOK.get(conf, ('var(--rpt-ink-soft)', 'var(--rpt-surface-2)'))
    band_col = _BAND_TOK.get(s.get('band'), 'var(--rpt-ink-soft)')
    conf_leg = ' '.join(f'<span class="lgi"><b>{lbl}</b> — {X._e(desc)}</span>'
                        for lbl, desc in _CONF_LEGEND)
    score_leg = ''.join(
        f'<span class="lgi{" on" if b == s.get("band") else ""}">'
        f'<span class="esdot" style="background:{_BAND_TOK[b]}"></span>{rng} {X._e(lbl)}</span>'
        for b, rng, lbl in _SCORE_LEGEND)
    pts = s.get('total_severity_points', 0)
    acts = s.get('total_activities', 0)
    density = s.get('weighted_finding_density', 0)
    method = (
        '<details class="howcalc"><summary>How is this score calculated?</summary>'
        '<div class="howbody">The score is <b>independent of project size</b> — it uses '
        'finding-severity <b>density</b>, not a flat subtraction, so a large project with '
        'many findings is not unfairly driven to zero.<br>'
        'Severity points (per <b>finding</b>, never per activity): Strong = 10, '
        'Moderate = 5, Low = 2.<br>'
        'Weighted Finding Density = (Σ severity points ÷ total project activities) × 100.<br>'
        'Risk Score = 100 − Weighted Finding Density, clamped to 0–100.<br>'
        f'This project: {pts} severity point(s) ÷ {acts} activities × 100 = '
        f'{density} density → <b>{X._e(s.get("overall", "—"))}</b>/100.</div></details>')
    # severity summary (Strong / Moderate / Low counts)
    bys = s.get('by_strength', {})
    low = bys.get('weak', 0) + bys.get('insufficient', 0)
    sev_parts = []
    if bys.get('strong'):
        sev_parts.append(f'{bys["strong"]} Strong')
    if bys.get('moderate'):
        sev_parts.append(f'{bys["moderate"]} Moderate')
    if low:
        sev_parts.append(f'{low} Low')
    sev_summary = ' · '.join(sev_parts) or 'none'
    return (
        f'<div class="prs">'
        f'<div class="prsrow"><span class="prsk">Project Type</span>'
        f'<span class="prsv"><b>{X._e(a.get("archetype_name") or a.get("archetype") or "—")}</b></span>'
        f'<span class="prsk">Confidence</span>'
        f'<span class="schip" style="background:{cfg_bg};color:{cfg_col};border-color:{cfg_col}">'
        f'{X._e(conf.capitalize())}</span></div>'
        f'<div class="lgrow"><span class="lgt">Confidence</span>{conf_leg}</div>'
        f'<div class="scorehero">'
        f'<span class="shnum" style="color:{band_col}">{X._e(s.get("overall", "—"))}</span>'
        f'<span class="shden">/ 100</span>'
        f'<span class="shband" style="color:{band_col}">{X._e(s.get("band_label", ""))}</span>'
        f'<span class="shlabel">Constructability Risk Score</span></div>'
        f'<div class="lgrow"><span class="lgt">Score</span>{score_leg}</div>'
        f'{method}'
        f'<div class="prsrow"><span class="prsk">Total findings</span>'
        f'<span class="prsv"><b>{len(fs)}</b></span>'
        f'<span class="prsk">Severity</span><span class="prsv">{X._e(sev_summary)}</span></div>'
        f'{_coverage_line(report.get("v2_coverage"), len(fs))}'
        f'<div class="prssum">{X._e(_risk_summary_line(s, fs))}</div>'
        f'</div>')


def _coverage_line(cov, n_findings):
    """What the engine analysed — so a clean result reads as thoroughly checked."""
    if not cov:
        return ''
    sys = len(cov.get('systems') or [])
    line = (f'<div class="prscov">Analysed <b>{cov.get("activities", 0)}</b> activities · '
            f'<b>{cov.get("relationships", 0)}</b> relationships · <b>{cov.get("classified", 0)}</b> '
            f'classified into <b>{sys}</b> system(s) · all 7 constructability checks run</div>')
    clean = ('<div class="prsclean">✓ No sequencing risks found — the schedule is well-linked and '
             'correctly sequenced for the systems present. A clean result here means the logic is sound, '
             'not that nothing was checked.</div>') if n_findings == 0 else ''
    return line + clean


def _rel_cell(rels):
    """Predecessor/successor links as compact lines: linked activity ID + name +
    relationship type (FS/SS/FF/SF) and lag — the actual schedule logic."""
    if not rels:
        return '<span class="mut">— none —</span>'
    out = []
    for r in rels:
        lag = f' <b>{X._e(r.get("lag"))}</b>' if r.get('lag') else ''
        out.append(f'<span class="mono">{X._e(r.get("id"))}</span> {X._e(r.get("name"))} '
                   f'<span class="rtype">{X._e(r.get("type"))}</span>{lag}')
    return '<br>'.join(out)


def _p6_logic_table(p6):
    """Drill-down: each involved activity's ID/name and its CURRENT predecessors and
    successors (type + lag)."""
    if not p6:
        return ''
    rows = ''
    for c in p6:
        rows += (f'<tr>'
                 f'<td class="mono">{X._e(c.get("id"))}</td>'
                 f'<td>{X._e(c.get("name"))}<div class="mut">{X._e(c.get("phase"))}'
                 f'{" · " + X._e(c.get("system")) if c.get("system") else ""}</div></td>'
                 f'<td>{_rel_cell(c.get("preds"))}</td>'
                 f'<td>{_rel_cell(c.get("succs"))}</td>'
                 f'</tr>')
    return ('<table class="p6log"><colgroup><col style="width:11%"><col style="width:29%">'
            '<col style="width:30%"><col style="width:30%"></colgroup>'
            '<thead><tr><th>Activity ID</th><th>Activity</th>'
            '<th>Current predecessor · type · lag</th>'
            '<th>Current successor · type · lag</th></tr></thead><tbody>'
            + rows + '</tbody></table>')


def _node(aid, name):
    return f'<span class="mono">{X._e(aid)}</span> {X._e(name)}'


def _compact_logic(primary):
    """The current P6 sequence around the finding's primary activity, with IDs, names and
    relationship types (and lag), e.g. 'A001 Spool Erection (FS) → A002 Insulation (FS) →
    A003 Hydrotest' — readable without opening P6."""
    if not primary:
        return '—'
    preds = primary.get('preds') or []
    succs = primary.get('succs') or []
    chain = ''
    if preds:
        p = preds[0]
        lag = f' {X._e(p.get("lag"))}' if p.get('lag') else ''
        chain += f'{_node(p.get("id"), p.get("name"))} <span class="rtype">{X._e(p.get("type"))}{lag}</span> → '
    chain += f'<b>{_node(primary.get("id"), primary.get("name"))}</b>'
    if succs:
        sc = succs[0]
        lag = f' {X._e(sc.get("lag"))}' if sc.get('lag') else ''
        chain += f' <span class="rtype">{X._e(sc.get("type"))}{lag}</span> → {_node(sc.get("id"), sc.get("name"))}'
    return chain


def _fwe_block(f):
    """Finding / Why / Evidence / Knowledge Support, each clearly labelled in one cell."""
    parts = [f'<div class="fw"><span class="fwl">Finding:</span> {X._e(f.get("title"))}</div>',
             f'<div class="fw"><span class="fwl">Why:</span> {X._e(f.get("reason"))}</div>',
             f'<div class="fw"><span class="fwl">Evidence:</span> {X._e(f.get("existing"))}</div>']
    support = f.get('support') or {}
    if support:
        parts.append(f'<div class="fw"><span class="fwl">Knowledge Support:</span> '
                     f'<span class="supln">{X._e(support.get("label"))}</span></div>')
    return ''.join(parts)


def _activity_cell(p6, key):
    """All involved activities, one per line — never hidden behind '+N more'."""
    if not p6:
        return '—'
    css = 'mono' if key == 'id' else ''
    return '<br>'.join(f'<span class="{css}">{X._e(c.get(key, ""))}</span>' for c in p6)


def _constructability_findings(report):
    """Section 2 — ONE consolidated findings table, one row per finding:
    # · Severity · Activity ID · Activity Name · Current P6 Logic · Finding/Why/Evidence
    · Recommendation · Score Impact. All involved activities are shown (never '+N more').
    Full P6 traceability + a Current-vs-Recommended comparison are an expandable drill-down
    per finding so the main table stays clean. Findings come solely from the current XER."""
    fs = report.get('v2_findings') or []
    if not fs:
        return ''
    sev_leg = ' '.join(f'<span class="lgi">{_sev_chip(k)} {X._e(desc)}</span>'
                       for k, _lbl, desc in _SEV_LEGEND)
    rows = ''
    for i, f in enumerate(fs, 1):
        p6 = f.get('p6') or []
        primary = p6[0] if p6 else {}
        rec = f.get('recommended_sequence') or f.get('recommendation') or ''
        impact = f.get('score_impact')
        impact_txt = f'−{impact}' if impact is not None else '—'
        rows += (
            f'<tr class="cfrow">'
            f'<td class="sn">{i}</td>'
            f'<td>{_activity_cell(p6, "id")}</td>'
            f'<td>{_activity_cell(p6, "name")}</td>'
            f'<td class="cflogic">{_compact_logic(primary)}</td>'
            f'<td class="cfwe">{_fwe_block(f)}</td>'
            f'<td>{_sev_chip(f.get("strength"))}</td>'
            f'<td class="chg cfrec">{X._e(rec)}</td>'
            f'<td class="mono cfimpact">{impact_txt}</td>'
            f'</tr>'
            f'<tr class="cfdetailrow"><td></td><td colspan="7">'
            f'<details class="cfdetail"><summary>P6 traceability &amp; current vs recommended</summary>'
            f'<div class="cmp"><div class="cmpk">Current P6 Logic</div>'
            f'<div class="cmpv">{_compact_logic(primary)}</div></div>'
            f'<div class="cmp"><div class="cmpk rec">Recommended Sequence</div>'
            f'<div class="cmpv"><b>{X._e(rec)}</b></div></div>'
            f'{_p6_logic_table(p6)}</details></td></tr>')
    return (
        '<table class="data cfind"><colgroup>'
        '<col style="width:3%"><col style="width:8%"><col style="width:14%"><col style="width:16%">'
        '<col style="width:29%"><col style="width:7%"><col style="width:16%"><col style="width:7%">'
        '</colgroup><thead><tr><th>#</th><th>Activity ID</th><th>Activity Name</th>'
        '<th>Current P6 Logic</th><th>Finding / Why / Evidence</th><th>Severity</th><th>Recommendation</th>'
        '<th>Score Impact</th></tr></thead><tbody>' + rows + '</tbody></table>'
        f'<div class="lgrow"><span class="lgt">Severity</span>{sev_leg}</div>'
        '<div class="cfnote">Every finding is raised solely from the current XER\'s own '
        'schedule logic; supporting knowledge is corroboration only. Open a row for full '
        'P6 predecessors, successors, relationship types and lags.</div>')


# Extra CSS for the two final Constructability sections, appended to the shared CSS.
_EXTRA_CSS = '''
      .schip { display: inline-block; font-size: 9px; font-weight: 700; text-transform: uppercase;
               letter-spacing: .3px; padding: 1px 7px; border-radius: 20px; border: 1px solid; white-space: nowrap; }
      .esdot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
      .prs { border: 1px solid var(--rpt-hair); border-radius: 8px; padding: 10px 13px; }
      .prsrow { display: flex; align-items: baseline; gap: 10px; padding: 3px 0; font-size: 12px; }
      .prsrow .prsk { color: var(--rpt-ink-soft); text-transform: uppercase; letter-spacing: .3px; font-size: 10px; }
      .prsrow .prsv { color: var(--rpt-ink); }
      .scorehero { display: flex; align-items: baseline; gap: 8px; margin: 8px 0 2px; }
      .scorehero .shnum { font-size: 40px; font-weight: 800; line-height: 1; }
      .scorehero .shden { font-size: 13px; color: var(--rpt-muted); }
      .scorehero .shband { font-size: 16px; font-weight: 700; margin-left: 6px; }
      .scorehero .shlabel { font-size: 10px; color: var(--rpt-ink-soft); text-transform: uppercase;
                            letter-spacing: .3px; margin-left: auto; }
      .lgrow { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 3px 0;
               font-size: 10px; color: var(--rpt-ink-soft); }
      .lgrow .lgt { color: var(--rpt-muted); text-transform: uppercase; letter-spacing: .3px; font-weight: 700;
                    font-size: 9px; }
      .lgi { display: inline-flex; align-items: center; gap: 4px; opacity: .8; }
      .lgi.on { opacity: 1; font-weight: 700; color: var(--rpt-ink); }
      .howcalc { margin: 4px 0; }
      .howcalc > summary { font-size: 10.5px; color: var(--rpt-accent); cursor: pointer; font-weight: 600; }
      .howcalc .howbody { font-size: 10.5px; color: var(--rpt-ink-soft); padding: 5px 0 2px; line-height: 1.5; }
      .prscov { margin-top: 6px; font-size: 10.5px; color: var(--rpt-ink-soft); }
      .prsclean { margin-top: 5px; padding: 6px 10px; background: var(--rpt-good-bg); border: 1px solid var(--rpt-good);
                  border-radius: 6px; font-size: 11px; color: var(--rpt-good); font-weight: 600; }
      .prssum { margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--rpt-hair); font-size: 12px;
                color: var(--rpt-ink); font-weight: 600; }
      table.cfind { table-layout: fixed; width: 100%; border-collapse: collapse; }
      table.cfind th, table.cfind td { border: 1px solid var(--rpt-hair); padding: 4px 6px; }
      table.cfind td { vertical-align: top; overflow-wrap: anywhere; word-break: break-word; white-space: normal; }
      table.cfind td .mono, table.cfind td.cflogic, table.cfind td.cfrec { overflow-wrap: anywhere; word-break: break-word; }
      table.cfind td.cfwe { font-size: 10.5px; line-height: 1.5; }
      table.cfind td.cflogic { font-size: 10px; line-height: 1.5; }
      table.cfind td.cfrec { font-size: 10.5px; line-height: 1.5; }
      table.cfind td.cfimpact { text-align: right; font-weight: 700; color: var(--rpt-bad); white-space: nowrap; }
      .cfwe .fw { padding: 1px 0; }
      .cfwe .fwl { font-weight: 700; color: var(--rpt-ink-soft); text-transform: uppercase;
                   letter-spacing: .2px; font-size: 9px; }
      .cfwe .supln { color: var(--rpt-good); }
      .cmp { display: flex; gap: 8px; margin: 3px 0; font-size: 10.5px; }
      .cmp .cmpk { flex: 0 0 130px; color: var(--rpt-ink-soft); text-transform: uppercase; letter-spacing: .3px;
                   font-size: 9px; font-weight: 700; padding-top: 1px; }
      .cmp .cmpk.rec { color: var(--rpt-good); }
      .cmp .cmpv { color: var(--rpt-ink); }
      .cfdetailrow td { background: var(--rpt-surface); border-top: none; padding: 0 8px 8px; }
      .cfdetail > summary { font-size: 10px; color: var(--rpt-ink-soft); cursor: pointer; padding: 5px 0;
                            font-weight: 600; list-style: none; }
      .cfdetail > summary::-webkit-details-marker { display: none; }
      .cfdetail .recnote { font-size: 10.5px; color: var(--rpt-good); background: var(--rpt-good-bg);
                           border: 1px solid var(--rpt-good); border-radius: 5px; padding: 4px 8px; margin: 3px 0; }
      table.p6log { width: 100%; border-collapse: collapse; margin-top: 5px; font-size: 10px; }
      table.p6log th { text-align: left; background: var(--rpt-surface-2); color: var(--rpt-ink-soft); font-weight: 600;
                       padding: 3px 6px; border: 1px solid var(--rpt-hair); }
      table.p6log td { padding: 3px 6px; border: 1px solid var(--rpt-hair); vertical-align: top; }
      .rtype { display: inline-block; font-size: 9px; font-weight: 700; color: var(--rpt-accent);
               background: var(--rpt-accent-soft); border-radius: 3px; padding: 0 4px; }
      .cfnote { font-size: 9.5px; color: var(--rpt-muted); margin-top: 6px; font-style: italic; }
'''


def build_spec(report):
    s = report.get('score') or {}
    # Band accent as appearance tokens (not fixed hex) so the report themes in all 6 modes.
    accent = X._band_var(s.get('band'))
    accent_bg = X._band_bg_var(s.get('band'))
    conf = report.get('confidence') or {}
    conf_line = ('Type chosen manually' if conf.get('forced')
                 else f"Detection confidence: {conf.get('level', '')} "
                      f"({conf.get('hits', 0)}/{conf.get('signatures', 0)} keywords)")
    meta = f"{report.get('project_type', '')} · {conf_line} · Rule + Knowledge Base · offline"

    # ── The Constructability Review output = TWO sections, ONE score (Ibrahim's V1
    # spec). These default ON and are what the screen shows, so Print Preview / PDF ==
    # screen. The legacy KB-standard components (verdict/scorecard/illogical/missing/
    # WBS/conclusion — a SECOND, contradictory score) are kept selectable for anyone who
    # wants them, but default OFF so they never contradict the headline output. ──
    components = [
        ReportComponent('project_risk_summary', 'Project Risk Summary', 'summary',
                        render=_project_risk_summary,
                        has_data=lambda r: bool(r.get('archetype') or r.get('v2_score')),
                        description='Project type, confidence, constructability risk score with legends'),
        ReportComponent('constructability_findings', 'Constructability Findings', 'findings',
                        render=_constructability_findings,
                        has_data=lambda r: bool(r.get('v2_findings')),
                        description='One consolidated evidence-graded findings table with P6 drill-down'),
        # ── legacy KB-standard components — default OFF (optional) ──
        ReportComponent('verdict', 'Verdict (legacy)', 'summary', render=_verdict, default=False,
                        has_data=lambda r: bool(r.get('verdict')),
                        description='Legacy KB-standard readiness statement'),
        ReportComponent('scorecard', 'KB-Standard Score (legacy)', 'summary', render=_scorecard, default=False,
                        has_data=lambda r: bool(r.get('score')),
                        description='Legacy KB-standard score and its three dimensions'),
        ReportComponent('readiness_legend', 'Readiness Band (legacy)', 'chart', render=_legend, default=False,
                        has_data=lambda r: bool(r.get('score')),
                        description='Legacy readiness scale'),
        ReportComponent('projection', 'What-If Projection (legacy)', 'text', render=_projection, default=False,
                        has_data=lambda r: bool(r.get('projected')),
                        description='Legacy score achievable if the flagged logic is corrected'),
        ReportComponent('tiles', 'Key Metrics (legacy)', 'summary', render=X._tiles, default=False,
                        has_data=lambda r: bool(r.get('dashboard')),
                        description='Legacy illogical/missing/coverage tiles'),
        # these three render their OWN graceful "none flagged" note when empty (no has_data)
        ReportComponent('issues_by_wbs', 'Issues by WBS Phase (legacy)', 'chart', render=X._issues_by_wbs,
                        default=False, description='Legacy: where problems concentrate'),
        ReportComponent('illogical', 'Illogical Relationships (legacy)', 'table', render=X._illogical_table,
                        default=False, description='Legacy flagged links vs the KB standard'),
        ReportComponent('missing', 'Missing Activities (legacy)', 'table', render=X._missing_table,
                        default=False, description='Legacy: activities expected against the standard'),
        ReportComponent('wbs_review', 'WBS Review (legacy)', 'table', render=X._wbs_review, default=False,
                        has_data=lambda r: bool(r.get('wbs_review')),
                        description='Legacy standard WBS branches present or missing'),
        ReportComponent('conclusion', 'Conclusion (legacy)', 'text', render=_conclusion, default=False,
                        has_data=lambda r: bool(r.get('conclusion')),
                        description='Legacy closing summary line'),
    ]

    return ReportSpec(
        feature=FEATURE,
        title='Constructability Review — Execution Readiness',
        meta_line=meta,
        css=X.component_css(accent, accent_bg) + _EXTRA_CSS,
        orientation='landscape',
        components=components,
    )


register(FEATURE, build_spec)
