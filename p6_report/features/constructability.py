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
        ReportComponent('projection', 'What-If Projection', 'text', render=_projection,
                        has_data=lambda r: bool(r.get('projected')),
                        description='Score achievable if the flagged logic is corrected'),
        ReportComponent('tiles', 'Key Metrics', 'summary', render=X._tiles,
                        has_data=lambda r: bool(r.get('dashboard')),
                        description='Illogical links, missing activities, coverage, critical path'),
        ReportComponent('issues_by_wbs', 'Issues by WBS Phase', 'chart', render=X._issues_by_wbs,
                        has_data=lambda r: bool(r.get('issues_by_wbs')),
                        description='Where the problems concentrate across the schedule'),
        ReportComponent('illogical', 'Illogical Relationships', 'table', render=X._illogical_table,
                        has_data=lambda r: bool(r.get('illogical')),
                        description='Flagged links with the better logic suggested'),
        ReportComponent('missing', 'Missing Activities', 'table', render=X._missing_table,
                        has_data=lambda r: bool(r.get('missing')),
                        description='Activities normally expected against the standard'),
        ReportComponent('wbs_review', 'WBS Review', 'table', render=X._wbs_review,
                        has_data=lambda r: bool(r.get('wbs_review')),
                        description='Standard WBS branches present or missing'),
        ReportComponent('conclusion', 'Conclusion', 'text', render=_conclusion,
                        has_data=lambda r: bool(r.get('conclusion')),
                        description='Closing summary line'),
    ]

    return ReportSpec(
        feature=FEATURE,
        title='Constructability Review — Execution Readiness',
        meta_line=meta,
        css=X.component_css(hex_),
        orientation='landscape',
        components=components,
    )


register(FEATURE, build_spec)
