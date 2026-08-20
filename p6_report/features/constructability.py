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


def _evidence_findings(report):
    """The R1–R7 evidence-graded rule-engine findings, each as a full auditable chain:
    existing → expected → reason → evidence → strength → impact → recommendation."""
    fs = report.get('v2_findings') or []
    if not fs:
        return ''
    body = ''
    for i, f in enumerate(fs, 1):
        hex_ = _STRENGTH_HEX.get(f.get('strength'), '#64748b')
        acts = ', '.join(str(x) for x in (f.get('activities') or [])) or '—'
        body += (
            f'<tr>'
            f'<td class="sn">{i}</td>'
            f'<td><span class="schip" style="background:{hex_}1a;color:{hex_};border-color:{hex_}55">'
            f'{X._e(f.get("strength"))}</span></td>'
            f'<td class="mono">{X._e(f.get("system"))}</td>'
            f'<td><b>{X._e(f.get("title"))}</b>'
            f'<div class="mut">{X._e(f.get("existing"))}</div></td>'
            f'<td>{X._e(f.get("expected"))}<div class="mut">{X._e(f.get("reason"))}</div></td>'
            f'<td class="mut">{X._e(f.get("evidence"))}</td>'
            f'<td>{X._e(f.get("impact"))}</td>'
            f'<td class="chg">{X._e(f.get("recommendation"))}</td>'
            f'<td class="mono">{X._e(acts)}</td>'
            f'</tr>')
    return ('<table class="data"><colgroup>'
            '<col style="width:3%"><col style="width:7%"><col style="width:9%"><col style="width:19%">'
            '<col style="width:17%"><col style="width:15%"><col style="width:12%"><col style="width:12%">'
            '<col style="width:6%"></colgroup>'
            '<thead><tr><th>#</th><th>Strength</th><th>System</th><th>Finding</th>'
            '<th>Expected &amp; why</th><th>Evidence</th><th>Impact</th>'
            '<th>Recommendation</th><th>Activities</th></tr></thead><tbody>'
            + body + '</tbody></table>')


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
