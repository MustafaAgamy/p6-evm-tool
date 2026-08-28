"""Shared helpers for providers — generic, defensive rendering of the data
shapes features expose (dicts of KPIs, lists of findings, lists of row-dicts),
so a provider maps a feature's result to payloads without hand-coding every key.
"""
from p6_special import payloads as P
from p6_special import fmt

_LABELS = {
    'total_activities': 'Total activities', 'total_dangling': 'Dangling activities',
    'dangling_pct': 'Dangling %', 'oos_pct': 'Out-of-sequence %', 'lagged_pct': 'Lagged %',
    'float_pct': 'High-float %', 'illogical_count': 'Illogical links',
    'illogical_pct': 'Illogical %', 'missing_count': 'Missing activities',
    'missing_pct': 'Missing %', 'total_relationships': 'Relationships',
    'critical_affected': 'Critical path affected', 'critical_count': 'Critical',
    'near_critical_count': 'Near-critical', 'expected_bad_days_total': 'Bad-weather days',
    'net_finish_delay': 'Weather delay (days)', 'weather_adjusted_finish': 'Weather-adjusted finish',
}


def humanize(key):
    return _LABELS.get(key) or str(key).replace('_', ' ').strip().capitalize()


def _fmt_value(key, v):
    if isinstance(v, bool):
        return 'Yes' if v else 'No'
    if isinstance(v, (int, float)):
        if key.endswith('_pct') or key.endswith('_percent'):
            return f'{v:.1f}%'
        return fmt.num(v)
    return '—' if v is None else str(v)


def kpi_from_dict(d, order=None, tone_key=None):
    """A kpi_group from a flat dict of scalars."""
    if not d:
        return P.NO_DATA
    keys = order or [k for k, v in d.items() if isinstance(v, (int, float, str, bool)) or v is None]
    items = [P.kpi(humanize(k), _fmt_value(k, d.get(k))) for k in keys if k in d]
    return P.kpi_group(items) if items else P.NO_DATA


def table_from_dicts(rows, columns=None, cap=40):
    """A table from a list of uniform-ish dicts. ``columns`` = list of keys."""
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    if not rows:
        return P.NO_DATA
    cols = columns or list(rows[0].keys())
    numeric = {c: all(isinstance(r.get(c), (int, float)) or r.get(c) is None for r in rows) for c in cols}
    body = []
    for r in rows[:cap]:
        body.append([_fmt_value(c, r.get(c)) for c in cols])
    aligns = ['r' if numeric.get(c) else 'l' for c in cols]
    return P.table([humanize(c) for c in cols], body, aligns=aligns)


_SEV_MAP = {'critical': 'high', 'high': 'high', 'medium': 'medium', 'moderate': 'medium',
            'low': 'low', 'info': 'info'}
_TITLE_KEYS = ('title', 'issue', 'activity_name', 'name', 'activity_id', 'wbs', 'description', 'label')
_DETAIL_KEYS = ('detail', 'reason', 'description', 'note', 'recommendation', 'suggestion', 'why')


def _first(d, keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


def findings_from_list(items, cap=12, empty='No findings.'):
    items = [f for f in (items or []) if isinstance(f, dict)]
    out = []
    for f in items[:cap]:
        sev = _SEV_MAP.get(str(f.get('severity', 'info')).lower(), 'info')
        out.append({'severity': sev,
                    'title': str(_first(f, _TITLE_KEYS) or 'Finding'),
                    'detail': (_first(f, [k for k in _DETAIL_KEYS if k != 'description'])
                               or (f.get('description') if _first(f, _TITLE_KEYS) != f.get('description') else None))})
    payload = P.findings(out, empty=empty)
    if len(items) > cap:
        payload = P.group([payload, P.note(f'… and {len(items) - cap} more.', 'info')])
    return payload
