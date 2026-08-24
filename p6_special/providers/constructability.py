"""Constructability Review provider.

Single file, recomputed on demand: ``run_review(ctx.parsed())``. Score is a dict
with 'overall' (0..100) + 'band_label'; findings come from 'illogical' + 'missing'.
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special.registry import Item
from p6_special.providers import _util as U

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


def _type(ctx):
    r = _review(ctx)
    if not r or not r.get('project_type'):
        return P.NO_DATA
    conf = r.get('confidence') or {}
    return P.keyvals([
        ('Detected type', r.get('project_type')),
        ('Confidence', conf.get('level') or '—'),
        ('Signature hits', conf.get('hits')),
    ])


def _dimensions(ctx):
    r = _review(ctx)
    d = (r or {}).get('dashboard') or {}
    return U.kpi_from_dict(d) if d else P.NO_DATA


def _whatif(ctx):
    r = _review(ctx)
    pj = (r or {}).get('projected')
    if not pj:
        return P.NO_DATA
    return P.kpi_group([P.kpi('Projected score if fixed',
                              f"{fmt.num(pj.get('overall'))}/100",
                              sub=pj.get('basis'), tone='good')])


def _findings(ctx):
    r = _review(ctx)
    if not r:
        return P.NO_DATA
    items = list(r.get('illogical') or []) + list(r.get('missing') or [])
    return U.findings_from_list(items, empty='No constructability issues flagged.')


def provide(ctx):
    R = _ready
    return [
        Item('construct:score', FEATURE, FEATURE_TITLE, 'Constructability score', 'score', _score, R),
        Item('construct:type', FEATURE, FEATURE_TITLE, 'Detected project type', 'text', _type, R),
        Item('construct:dimensions', FEATURE, FEATURE_TITLE, 'Review breakdown', 'kpi', _dimensions, R),
        Item('construct:whatif', FEATURE, FEATURE_TITLE, 'Projected score if fixed', 'kpi', _whatif, R),
        Item('construct:findings', FEATURE, FEATURE_TITLE, 'Constructability findings', 'findings', _findings, R),
    ]
