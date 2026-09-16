"""Constructability Review provider — the feature's OWN full report (score,
dimensions, findings, charts), recomputed on demand; plus a quick score figure."""
from p6_special import payloads as P
from p6_special import fmt
from p6_special import feature_reports as FR
from p6_special.registry import Item

FEATURE = 'constructability'
FEATURE_TITLE = 'Constructability Review'


def _ready(ctx):
    return 'ready' if ctx.has_xml() else 'no_data'


def _review(ctx):
    def build():
        data = ctx.parsed()
        if data is None:
            return None
        from p6_kb.review import run_review
        return run_review(data)
    return ctx.memo('kb_review', build)


def _risk_tone(x):
    # Evidence Risk bands (p6_kb.scoring EVIDENCE_BANDS / the on-screen colours): higher
    # score = lower risk. Low Risk >=80 (green), Moderate >=60 (amber), else higher risk.
    if x is None:
        return 'neutral'
    return 'good' if x >= 80 else ('warn' if x >= 60 else 'bad')


def _score(ctx):
    r = _review(ctx)
    # Match the on-screen headline: the v2 evidence-based Constructability Risk Score
    # (NOT the legacy 45/45/10 KB rubric score, which the screen deliberately hides).
    v2 = (r or {}).get('v2_score')
    if not isinstance(v2, dict) or v2.get('overall') is None:
        return P.NO_DATA
    overall = v2.get('overall')
    return P.kpi_group([P.kpi('Constructability Risk Score',
                              f'{fmt.num(overall)}/100',
                              sub=v2.get('band_label'), tone=_risk_tone(overall))])


def provide(ctx):
    return [
        Item('construct:score', FEATURE, FEATURE_TITLE, 'Constructability Risk Score', 'score', _score, _ready),
        Item('construct:report', FEATURE, FEATURE_TITLE, 'Full Constructability report', 'section',
             lambda ctx: FR.kb_v2_report(ctx) or P.NO_DATA, _ready),
    ]
