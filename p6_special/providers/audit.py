"""Schedule Audit provider — each module's OWN full report (detailed tables +
charts, reused from the module renderer), parse-free from ``ctx.audit``; plus a
quick score figure per module."""
from p6_special import payloads as P
from p6_special import fmt
from p6_special import feature_reports as FR
from p6_special.registry import Item

FEATURE = 'audit'
FEATURE_TITLE = 'Schedule Audit'


def _mod(ctx, key):
    return ((ctx.audit or {}).get('modules') or {}).get(key)


def _avail(key):
    return lambda ctx: 'ready' if _mod(ctx, key) else 'no_data'


def _score_tone(s):
    if s is None:
        return 'neutral'
    return 'good' if s >= 80 else ('warn' if s >= 50 else 'bad')


def _score(key):
    def produce(ctx):
        m = _mod(ctx, key)
        if not m:
            return P.NO_DATA
        s, g = m.get('score'), m.get('grade')
        return P.kpi_group([P.kpi(m.get('name') or key,
                                  f'{fmt.num(s)}/100' if s is not None else '—',
                                  sub=(f'Grade {g}' if g else None), tone=_score_tone(s))])
    return produce


def _full(key):
    return lambda ctx, k=key: FR.audit_module(ctx, k) or P.NO_DATA


def provide(ctx):
    items = []
    for key, label in FR.AUDIT_MODULES:
        A = _avail(key)
        items.append(Item(f'audit:{key}_score', FEATURE, FEATURE_TITLE, f'{label} — score', 'score', _score(key), A))
        items.append(Item(f'audit:{key}_report', FEATURE, FEATURE_TITLE, f'{label} — full report', 'section', _full(key), A))
    return items
