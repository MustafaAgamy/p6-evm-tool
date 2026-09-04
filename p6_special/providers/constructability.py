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


def _tone(x):
    if x is None:
        return 'neutral'
    return 'good' if x >= 80 else ('warn' if x >= 50 else 'bad')


def _score(ctx):
    r = _review(ctx)
    s = (r or {}).get('score')
    if not s:
        return P.NO_DATA
    overall = s.get('overall') if isinstance(s, dict) else s
    band = (s.get('band_label') if isinstance(s, dict) else None) or (r.get('verdict') or {}).get('title')
    return P.kpi_group([P.kpi('Constructability score',
                              f'{fmt.num(overall)}/100' if overall is not None else '—',
                              sub=band, tone=_tone(overall))])


def provide(ctx):
    return [
        Item('construct:score', FEATURE, FEATURE_TITLE, 'Constructability score', 'score', _score, _ready),
        Item('construct:report', FEATURE, FEATURE_TITLE, 'Full Constructability report', 'section',
             lambda ctx: FR.kb_full_report(ctx) or P.NO_DATA, _ready),
    ]
