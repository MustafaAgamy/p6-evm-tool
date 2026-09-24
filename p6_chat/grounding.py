"""Turn the tool's already-computed result for the open project into a compact,
plain-text grounding block the offline brain answers from.

Input is the dict from ``db.get_project_result(project_id)`` — the stored
``metrics.compute()`` shape (data_date, categories, overall %s, pv/ev/ac, spi,
cpi, variance, delay_days) enriched on parse with project_name / activity_count.
We never re-parse or re-compute here — this is the read path. Everything is
guarded so a partial result still yields whatever figures exist; the model is
told to say so when a figure is absent rather than invent it.
"""
from datetime import datetime, date


def _num(v, dp=2):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, dp)


def _pct(v):
    n = _num(v, 1)
    return None if n is None else ('%s%%' % n)


def _money(v):
    n = _num(v, 0)
    if n is None:
        return None
    return '{:,.0f}'.format(n)


def _date(v):
    if v in (None, ''):
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime('%d %b %Y')
    s = str(v)
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).strftime('%d %b %Y')
    except ValueError:
        return s


def available(result):
    """True when there is enough computed data to ground an answer."""
    return bool(result) and any(
        result.get(k) is not None for k in ('spi', 'cpi', 'delay_days',
                                            'overall_actual_pct', 'categories'))


def build(result):
    """A plain-text grounding block, or '' when nothing is computed yet."""
    if not result:
        return ''
    L = []
    proj = result.get('project_name') or result.get('project')
    if proj:
        L.append('Project: %s' % proj)
    dd = _date(result.get('data_date'))
    if dd:
        L.append('Data date: %s' % dd)
    ac = result.get('activity_count')
    if ac:
        L.append('Activities: %s' % ac)

    # headline performance
    perf = []
    if result.get('spi') is not None:
        perf.append('SPI %s' % _num(result.get('spi')))
    if result.get('cpi') is not None:
        perf.append('CPI %s' % _num(result.get('cpi')))
    op, oa = _pct(result.get('overall_planned_pct')), _pct(result.get('overall_actual_pct'))
    if op or oa:
        perf.append('progress %s actual vs %s planned' % (oa or '?', op or '?'))
    if perf:
        L.append('Performance: ' + '; '.join(perf))

    # earned-value money
    ev_bits = []
    for label, key in (('PV', 'pv'), ('EV', 'ev'), ('AC', 'ac')):
        m = _money(result.get(key))
        if m is not None:
            ev_bits.append('%s %s' % (label, m))
    if result.get('variance') is not None:
        ev_bits.append('schedule variance %s' % _money(result.get('variance')))
    if ev_bits:
        L.append('Earned value: ' + '; '.join(ev_bits))

    # delay (sign-aware: positive = behind, negative = ahead)
    dl = result.get('delay_days')
    if dl is not None:
        try:
            dln = int(dl)
        except (TypeError, ValueError):
            dln = None
        if dln is not None:
            if dln > 0:
                phrase = '%d working days behind baseline finish' % dln
            elif dln < 0:
                phrase = '%d working days ahead of baseline finish' % abs(dln)
            else:
                phrase = 'on the baseline finish (no delay)'
            L.append("Delay: %s (the tool's computed figure; the exact F9 delay "
                     "comes from Consultant Review / Critical Path)." % phrase)

    # per-category / discipline breakdown
    cats = result.get('categories') or {}
    if isinstance(cats, dict) and cats:
        rows = []
        for name, c in cats.items():
            if not isinstance(c, dict):
                continue
            w = _pct(c.get('weight'))
            pl = _pct(c.get('planned_pct'))
            aa = _pct(c.get('actual_pct'))
            bits = [b for b in (('weight ' + w) if w else None,
                                ('planned ' + pl) if pl else None,
                                ('actual ' + aa) if aa else None) if b]
            rows.append('  - %s: %s' % (name, ', '.join(bits) if bits else 'no data'))
        if rows:
            L.append('By discipline/category (name: weight, planned %, actual %):\n'
                     + '\n'.join(rows))

    return '\n'.join(L).strip()
