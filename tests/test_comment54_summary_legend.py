"""Comment 54 — the Summary's overall score shows its legend. Ibrahim kept the 80% submission
rule (81.2 = 'Acceptable to submit'), and the legend also says where the same score falls on the
per-check bands (Critical < 90 · Review 90–95 · Pass ≥ 95), so 81.2 is never read as a pass."""
from p6_audit.health import score_legend


def test_legend_keeps_the_80_rule_and_places_the_score_on_the_check_bands():
    lg = score_legend(81.2)
    assert ('Acceptable to submit', '80–90') in lg['submission']
    assert lg['checks'] == [('Critical', '< 90'), ('Review', '90–95'), ('Pass', '≥ 95')]
    assert lg['check_band'] == 'Critical'
    assert '81.2 would be Critical' in lg['note']
    assert score_legend(92.0)['check_band'] == 'Review' and score_legend(96.3)['check_band'] == 'Pass'
    assert score_legend(None)['note'] is None


def test_summary_pdf_prints_the_legend_under_the_score():
    from p6_audit.report import _overall_legend
    html = _overall_legend(81.2)
    assert 'Acceptable to submit 80–90' in html and 'the overall 81.2 would be <b>Critical</b>' in html


def test_screen_draws_the_same_legend():
    import pathlib
    js = pathlib.Path(__file__).resolve().parent.parent.joinpath('ui', 'modules', 'audit.js').read_text(encoding='utf-8')
    assert '${overallLegendHtml(score)}' in js and 'Acceptable to submit 80–90' in js
