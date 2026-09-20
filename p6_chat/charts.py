"""Grounded charts to accompany a chat answer.

The chat's words come from the local brain; the *charts* are computed here
deterministically from the same project result the answer is grounded in — so a
figure in a chart is always the tool's real number, never something the model
drew. Charts are chosen by the question's intent and by what data exists; when
nothing fits (or no project is loaded) the list is simply empty.

Two chart kinds are emitted (the UI renders both as themed SVG):
  * 'kpi'  — a strip of headline stat tiles (SPI / CPI / progress / delay)
  * 'bars' — planned-vs-actual horizontal bars by discipline/category
"""
import re


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _wants(q, pattern):
    return bool(re.search(pattern, q or ''))


def _kpis(result):
    items = []
    spi = _f(result.get('spi'))
    if spi is not None:
        items.append({'label': 'SPI', 'value': ('%.2f' % spi),
                      'tone': 'good' if spi >= 0.98 else ('warn' if spi >= 0.9 else 'bad'),
                      'hint': 'schedule performance'})
    cpi = _f(result.get('cpi'))
    if cpi is not None:
        items.append({'label': 'CPI', 'value': ('%.2f' % cpi),
                      'tone': 'good' if cpi >= 0.98 else ('warn' if cpi >= 0.9 else 'bad'),
                      'hint': 'cost performance'})
    oa = _f(result.get('overall_actual_pct'))
    op = _f(result.get('overall_planned_pct'))
    if oa is not None:
        hint = ('vs %.1f%% planned' % op) if op is not None else 'complete'
        tone = 'good'
        if op is not None:
            tone = 'good' if oa >= op - 1 else ('warn' if oa >= op - 8 else 'bad')
        items.append({'label': 'Progress', 'value': ('%.1f%%' % oa), 'tone': tone, 'hint': hint})
    dl = result.get('delay_days')
    if dl is not None:
        try:
            dln = int(dl)
        except (TypeError, ValueError):
            dln = None
        if dln is not None:
            items.append({'label': 'Delay', 'value': ('%+d wd' % dln),
                          'tone': 'good' if dln <= 0 else ('warn' if dln <= 10 else 'bad'),
                          'hint': 'vs baseline finish'})
    return items


def _discipline_bars(result, limit=8):
    cats = result.get('categories') or {}
    if not isinstance(cats, dict):
        return []
    rows = []
    for name, c in cats.items():
        if not isinstance(c, dict):
            continue
        pl = _f(c.get('planned_pct'))
        aa = _f(c.get('actual_pct'))
        w = _f(c.get('weight')) or 0
        if pl is None and aa is None:
            continue
        rows.append({'name': name, 'planned': round(pl or 0, 1), 'actual': round(aa or 0, 1), '_w': w})
    # most material disciplines first, then trim
    rows.sort(key=lambda r: r['_w'], reverse=True)
    for r in rows:
        r.pop('_w', None)
    return rows[:limit]


def charts_for(question, result):
    """Return a list of grounded chart specs suited to `question`, or []."""
    if not result:
        return []
    q = (question or '').lower()
    out = []
    kpis = _kpis(result)
    if kpis and _wants(q, r'perform|\bspi\b|\bcpi\b|\bstand|status|how are we|headline|behind|ahead|delay|\blate\b|progress|budget|\bcost|\bkpi|report|recover|risk|forecast|finish'):
        out.append({'type': 'kpi', 'title': 'Headline KPIs (from your schedule)', 'items': kpis})
    bars = _discipline_bars(result)
    if bars and _wants(q, r'disciplin|categor|progress|where|driving|which wbs|breakdown|by area|behind|engineering|procurement|construction|scope'):
        out.append({'type': 'bars', 'title': 'Progress by discipline — planned vs actual (%)', 'items': bars})
    return out
