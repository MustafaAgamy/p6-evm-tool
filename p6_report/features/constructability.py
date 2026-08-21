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


_STRENGTH_HEX = {'strong': '#dc2626', 'moderate': '#d97706', 'weak': '#64748b', 'insufficient': '#94a3b8'}
_BAND_HEX = {'green': '#16a34a', 'amber': '#d97706', 'orange': '#ea580c', 'red': '#dc2626'}


def _evidence_score(report):
    """The MEP-first evidence-weighted score — a second, distinct score beside the KB
    Constructability score, computed only from the R1–R7 findings."""
    s = report.get('v2_score') or {}
    if not s:
        return ''
    hexb = _BAND_HEX.get(s.get('band'), '#64748b')
    bys = s.get('by_strength', {})
    chips = ' '.join(
        f'<span class="schip" style="background:{_STRENGTH_HEX.get(k, "#64748b")}1a;'
        f'color:{_STRENGTH_HEX.get(k, "#64748b")};border-color:{_STRENGTH_HEX.get(k, "#64748b")}55">'
        f'{n} {X._e(k)}</span>'
        for k, n in bys.items())
    ded = ''
    for d in s.get('deductions', [])[:8]:
        ded += (f'<tr><td class="mono">−{d.get("points")}</td>'
                f'<td class="mono">{X._e(d.get("system"))}</td>'
                f'<td>{X._e(d.get("strength"))} · {X._e(d.get("discipline_class"))}</td>'
                f'<td>{X._e(d.get("title"))}</td></tr>')
    ded_tbl = (('<table class="data" style="margin-top:6px"><thead><tr><th>Points</th>'
                '<th>System</th><th>Weight basis</th><th>Finding</th></tr></thead><tbody>'
                + ded + '</tbody></table>') if ded else '')
    return (f'<div class="escore">'
            f'<div class="esbadge" style="border-color:{hexb};color:{hexb}">'
            f'<div class="esnum">{s.get("overall")}</div><div class="esden">/ 100</div></div>'
            f'<div class="esbody">'
            f'<div class="esband" style="color:{hexb}">{X._e(s.get("band_label"))}</div>'
            f'<div class="esmeta">{s.get("finding_count")} evidence-graded finding(s) · '
            f'−{s.get("total_deducted")} points · {X._e(s.get("basis"))}</div>'
            f'<div class="eschips">{chips}</div>'
            f'</div></div>{ded_tbl}')


def _archetype_summary(report):
    """The MEP-first archetype resolution: what kind of project the engine sees, how
    confident it is, the systems present, and the systems it expected but did not find."""
    a = report.get('archetype') or {}
    if not a:
        return ''
    present = ', '.join(a.get('present_systems', []) or []) or '—'
    absent = ', '.join(a.get('expected_but_absent', []) or []) or 'none'
    terms = ', '.join(a.get('signature_terms', []) or [])
    amb = ' <b>(ambiguous — planner review)</b>' if a.get('ambiguous') else ''
    return (f'<div class="arcbox">'
            f'<div class="arcrow"><span class="ak">Resolved project type</span>'
            f'<span class="av"><b>{X._e(a.get("archetype_name") or a.get("archetype"))}</b> '
            f'· confidence {X._e(a.get("confidence"))}{amb}</span></div>'
            f'<div class="arcrow"><span class="ak">Identified by</span><span class="av">{X._e(terms)}</span></div>'
            f'<div class="arcrow"><span class="ak">Systems present</span><span class="av">{X._e(present)}</span></div>'
            f'<div class="arcrow"><span class="ak">Expected but absent</span><span class="av">{X._e(absent)}</span></div>'
            f'</div>')


def _rel_cell(rels):
    """Render a list of predecessor/successor links as compact lines: each is the linked
    activity's ID + name + relationship type (FS/SS/FF/SF) and lag — the actual schedule
    logic behind the finding."""
    if not rels:
        return '<span class="mut">— none —</span>'
    out = []
    for r in rels:
        lag = f' <b>{X._e(r.get("lag"))}</b>' if r.get('lag') else ''
        out.append(f'<span class="mono">{X._e(r.get("id"))}</span> {X._e(r.get("name"))} '
                   f'<span class="rtype">{X._e(r.get("type"))}</span>{lag}')
    return '<br>'.join(out)


def _p6_logic_table(p6):
    """The finding's schedule logic: for each involved activity, its ID, name, and its
    CURRENT predecessors and successors (type + lag). This is the drill-down detail."""
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


def _evidence_findings(report):
    """The R1–R7 evidence-graded findings. Each is a readable summary line (severity ·
    system · finding · impact · recommendation) with an expandable drill-down carrying
    the full evidence chain and the P6 schedule logic (activity IDs, predecessors,
    successors, relationship types and lags) behind it."""
    fs = report.get('v2_findings') or []
    if not fs:
        return ''
    cards = ''
    for i, f in enumerate(fs, 1):
        hex_ = _STRENGTH_HEX.get(f.get('strength'), '#64748b')
        cards += (
            f'<div class="efind">'
            f'<div class="efhead">'
            f'<span class="efn">{i}</span>'
            f'<span class="schip" style="background:{hex_}1a;color:{hex_};border-color:{hex_}55">'
            f'{X._e(f.get("strength"))}</span>'
            f'<span class="efsys mono">{X._e(f.get("system"))}</span>'
            f'<span class="eftitle">{X._e(f.get("title"))}</span></div>'
            f'<div class="efline"><span class="efk">Impact</span>'
            f'<span class="efv">{X._e(f.get("impact"))}</span></div>'
            f'<div class="efline"><span class="efk">Recommendation</span>'
            f'<span class="efv chg">{X._e(f.get("recommendation"))}</span></div>'
            f'<details open class="efdetail"><summary>Schedule logic &amp; evidence</summary>'
            f'<div class="efline"><span class="efk">Existing</span>'
            f'<span class="efv">{X._e(f.get("existing"))}</span></div>'
            f'<div class="efline"><span class="efk">Expected / why</span>'
            f'<span class="efv">{X._e(f.get("expected"))} — {X._e(f.get("reason"))}</span></div>'
            f'<div class="efline"><span class="efk">Evidence</span>'
            f'<span class="efv mut">{X._e(f.get("evidence"))}</span></div>'
            f'{_p6_logic_table(f.get("p6"))}'
            f'</details></div>')
    return f'<div class="efinds">{cards}</div>'


# Extra CSS for the two new components (archetype box + strength chip), appended to
# the shared Constructability CSS so the framework document styles them.
_EXTRA_CSS = '''
      .arcbox { border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 12px; margin: 4px 0 6px; }
      .arcrow { display: flex; gap: 10px; font-size: 11px; padding: 2px 0; }
      .arcrow .ak { width: 150px; color: #64748b; flex: 0 0 auto; }
      .arcrow .av { color: #1e293b; }
      .schip { display: inline-block; font-size: 9px; font-weight: 700; text-transform: uppercase;
               letter-spacing: .3px; padding: 1px 7px; border-radius: 20px; border: 1px solid; }
      .escore { display: flex; align-items: center; gap: 14px; }
      .esbadge { display: flex; flex-direction: column; align-items: center; justify-content: center;
                 width: 78px; height: 78px; border: 3px solid; border-radius: 12px; flex: 0 0 auto; }
      .esnum { font-size: 30px; font-weight: 800; line-height: 1; }
      .esden { font-size: 10px; opacity: .7; }
      .esband { font-size: 15px; font-weight: 700; }
      .esmeta { font-size: 11px; color: #64748b; margin: 2px 0 5px; }
      .eschips .schip { margin-right: 4px; }
      .efinds { display: flex; flex-direction: column; gap: 8px; }
      .efind { border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 11px; break-inside: avoid; }
      .efhead { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
      .efn { font-weight: 700; color: #94a3b8; font-size: 11px; }
      .efsys { font-size: 10px; color: #475569; }
      .eftitle { font-weight: 700; font-size: 12.5px; color: #0f172a; }
      .efline { display: flex; gap: 8px; font-size: 11px; padding: 2px 0; }
      .efline .efk { width: 118px; flex: 0 0 auto; color: #64748b; text-transform: uppercase;
                     letter-spacing: .3px; font-size: 9.5px; padding-top: 1px; }
      .efline .efv { color: #1e293b; }
      .efdetail { margin-top: 4px; }
      .efdetail > summary { font-size: 10px; color: #64748b; cursor: pointer; padding: 3px 0;
                            list-style: none; font-weight: 600; }
      .efdetail > summary::-webkit-details-marker { display: none; }
      table.p6log { width: 100%; border-collapse: collapse; margin-top: 5px; font-size: 10.5px; }
      table.p6log th { text-align: left; background: #f1f5f9; color: #475569; font-weight: 600;
                       padding: 3px 6px; border: 1px solid #e2e8f0; }
      table.p6log td { padding: 3px 6px; border: 1px solid #e2e8f0; vertical-align: top; }
      .rtype { display: inline-block; font-size: 9px; font-weight: 700; color: #0369a1;
               background: #e0f2fe; border-radius: 3px; padding: 0 4px; }
'''


def build_spec(report):
    s = report.get('score') or {}
    hex_ = X._hex(s.get('band'))
    conf = report.get('confidence') or {}
    conf_line = ('Type chosen manually' if conf.get('forced')
                 else f"Detection confidence: {conf.get('level', '')} "
                      f"({conf.get('hits', 0)}/{conf.get('signatures', 0)} keywords)")
    meta = f"{report.get('project_type', '')} · {conf_line} · Rule + Knowledge Base · offline"

    components = [
        ReportComponent('verdict', 'Verdict', 'summary', render=_verdict,
                        has_data=lambda r: bool(r.get('verdict')),
                        description='Overall readiness statement and project type'),
        ReportComponent('scorecard', 'Constructability Score', 'summary', render=_scorecard,
                        has_data=lambda r: bool(r.get('score')),
                        description='Headline score and the three scoring dimensions'),
        ReportComponent('readiness_legend', 'Readiness Band', 'chart', render=_legend,
                        has_data=lambda r: bool(r.get('score')),
                        description='Where the score sits on the readiness scale'),
        # projection defaults ON only when the engine produced one — matching the
        # legacy report, which omitted the What-If line entirely when absent rather
        # than showing an empty section.
        ReportComponent('projection', 'What-If Projection', 'text', render=_projection,
                        default=bool(report.get('projected')),
                        has_data=lambda r: bool(r.get('projected')),
                        description='Score achievable if the flagged logic is corrected'),
        ReportComponent('tiles', 'Key Metrics', 'summary', render=X._tiles,
                        has_data=lambda r: bool(r.get('dashboard')),
                        description='Illogical links, missing activities, coverage, critical path'),
        # These three render their OWN graceful "none flagged" note when empty, so
        # they carry no has_data gate — the friendly wording shows instead of the
        # framework's generic placeholder (matches the approved legacy report).
        ReportComponent('issues_by_wbs', 'Issues by WBS Phase', 'chart', render=X._issues_by_wbs,
                        description='Where the problems concentrate across the schedule'),
        ReportComponent('illogical', 'Illogical Relationships', 'table', render=X._illogical_table,
                        description='Flagged links with the better logic suggested'),
        ReportComponent('missing', 'Missing Activities', 'table', render=X._missing_table,
                        description='Activities normally expected against the standard'),
        ReportComponent('wbs_review', 'WBS Review', 'table', render=X._wbs_review,
                        has_data=lambda r: bool(r.get('wbs_review')),
                        description='Standard WBS branches present or missing'),
        # MEP-first rule engine (Phase 3) — resolution + evidence-graded findings, each
        # a first-class selectable component per the Global Reporting standard.
        ReportComponent('archetype_summary', 'Project-Type Resolution', 'summary',
                        render=_archetype_summary, has_data=lambda r: bool(r.get('archetype')),
                        description='MEP-first archetype the engine resolved, and the systems present/absent'),
        ReportComponent('evidence_score', 'MEP-First Execution-Logic Score', 'summary',
                        render=_evidence_score, has_data=lambda r: bool(r.get('v2_score')),
                        description='Second score, strength × MEP-priority weighted, from the R1–R7 findings'),
        ReportComponent('evidence_findings', 'Evidence-Graded Findings (R1–R7)', 'findings',
                        render=_evidence_findings, has_data=lambda r: bool(r.get('v2_findings')),
                        description='Deterministic rule-engine findings with the full evidence chain'),
        ReportComponent('conclusion', 'Conclusion', 'text', render=_conclusion,
                        has_data=lambda r: bool(r.get('conclusion')),
                        description='Closing summary line'),
    ]

    return ReportSpec(
        feature=FEATURE,
        title='Constructability Review — Execution Readiness',
        meta_line=meta,
        css=X.component_css(hex_) + _EXTRA_CSS,
        orientation='landscape',
        components=components,
    )


register(FEATURE, build_spec)
