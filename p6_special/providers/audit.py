"""Schedule Audit provider — Float / Out-of-Sequence / Lag & Lead / Dangling.

Parse-free: reads the four isolated modules straight from ``ctx.audit`` ==
db.get_audit_modules_for_snapshot(). Each module carries score (0..100), grade,
a flat ``kpis`` dict, ``findings`` and ``wbs_summary``.
"""
from p6_special import payloads as P
from p6_special import fmt
from p6_special.registry import Item
from p6_special.providers import _util as U

FEATURE = 'audit'
FEATURE_TITLE = 'Schedule Audit'
MODULES = [('float', 'Float Analysis'), ('out_of_sequence', 'Out of Sequence'),
           ('lag_lead', 'Lag & Lead'), ('dangling', 'Dangling Activities')]


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
        sub = f'Grade {g}' if g else None
        return P.kpi_group([P.kpi(m.get('name') or key,
                                  f'{fmt.num(s)}/100' if s is not None else '—',
                                  sub=sub, tone=_score_tone(s))])
    return produce


def _kpis(key):
    def produce(ctx):
        m = _mod(ctx, key)
        return U.kpi_from_dict(m.get('kpis') or {}) if m else P.NO_DATA
    return produce


def _findings(key):
    def produce(ctx):
        m = _mod(ctx, key)
        return U.findings_from_list(m.get('findings') or [], empty='No issues flagged.') if m else P.NO_DATA
    return produce


def _wbs(key):
    def produce(ctx):
        m = _mod(ctx, key)
        return U.table_from_dicts(m.get('wbs_summary') or []) if m else P.NO_DATA
    return produce


def provide(ctx):
    items = []
    for key, label in MODULES:
        A = _avail(key)
        items += [
            Item(f'audit:{key}_score', FEATURE, FEATURE_TITLE, f'{label} — score', 'score', _score(key), A),
            Item(f'audit:{key}_kpis', FEATURE, FEATURE_TITLE, f'{label} — key figures', 'kpi', _kpis(key), A),
            Item(f'audit:{key}_findings', FEATURE, FEATURE_TITLE, f'{label} — findings', 'findings', _findings(key), A),
            Item(f'audit:{key}_wbs', FEATURE, FEATURE_TITLE, f'{label} — by WBS', 'table', _wbs(key), A),
        ]
    return items
