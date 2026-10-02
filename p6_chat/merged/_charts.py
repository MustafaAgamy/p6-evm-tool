"""Charts for the 15 chat answers (owner comment 33) — "build more charts when answering".

Each answer gets the one or two charts that FIT its question, drawn from the same grounded facts
as its words (F = stored results, N = the schedule file re-read) — a chart never shows a number
the tool did not compute. When the facts for a chart are not there, the chart is simply left out.

Four chart kinds (the screen draws all of them with the app's own colour tokens, so they follow
every appearance mode):

    {'type': 'kpi',   'title', 'items': [{'label', 'value', 'tone', 'hint'}]}
    {'type': 'bars',  'title', 'legend', 'items': [{'name', 'planned', 'actual'}]}          # % vs %
    {'type': 'pairs', 'title', 'legend': [a, b], 'unit', 'items': [{'name', 'a', 'b', 'la', 'lb'}]}
    {'type': 'hbar',  'title', 'unit', 'items': [{'name', 'value', 'label', 'tone'}], 'note'}

tone: 'bad' | 'warn' | 'good' | 'info'.
"""
from p6_chat.qa import _kit as K

from . import _brief as B

MAX_ROWS = 8


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _nok(N):
    return bool(N and N.get('ok'))


def _label(x, limit=46):
    """'Drilling For Piles (CONS.PL.S9.1000)' kept short enough for a chart row."""
    name, aid = (x.get('name') or '').strip(), (x.get('id') or '').strip()
    if len(name) > limit:
        name = name[:limit - 1].rstrip() + '…'
    return f"{name} ({aid})" if name and aid else (name or aid)


# ── the building blocks ─────────────────────────────────────────────────────────

def c_kpis(F, N):
    items = []
    spi, d = _num(F.get('spi')), _num(F.get('delay_days'))
    if spi is not None:
        items.append({'label': 'SPI', 'value': K.ratio(spi), 'hint': 'work done ÷ work planned',
                      'tone': 'good' if spi >= 0.98 else ('warn' if spi >= 0.9 else 'bad')})
    a, p = _num(F.get('actual_pct')), _num(F.get('planned_pct'))
    if a is not None and p is not None:
        items.append({'label': 'Progress', 'value': K.pct(a), 'hint': f"planned {K.pct(p)}",
                      'tone': 'good' if a >= p - 1 else ('warn' if a >= p - 8 else 'bad')})
    if d is not None:
        d = int(round(d))
        items.append({'label': 'Finish', 'value': ('on time' if d == 0 else f"{abs(d)} days {'late' if d > 0 else 'early'}"),
                      'hint': 'working days, against the baseline', 'tone': 'good' if d <= 0 else ('warn' if d <= 10 else 'bad')})
    cpi = _num(F.get('cpi'))
    if cpi is not None and not F.get('cost_derived'):
        items.append({'label': 'CPI', 'value': K.ratio(cpi), 'hint': 'work done ÷ actual cost',
                      'tone': 'good' if cpi >= 0.98 else ('warn' if cpi >= 0.9 else 'bad')})
    return {'type': 'kpi', 'title': 'Where the project stands', 'items': items} if items else None


def c_disciplines(F, only=None, title='Progress by discipline — done against planned'):
    rows = [x for x in (F.get('disciplines') or []) if x.get('name')]
    if only:
        rows = [x for x in rows if only(x)]
    rows = sorted(rows, key=lambda x: -(_num(x.get('weight')) or 0))[:MAX_ROWS]
    items = [{'name': x['name'], 'planned': _num(x.get('planned')) or 0, 'actual': _num(x.get('actual')) or 0}
             for x in rows]
    return {'type': 'bars', 'title': title, 'legend': 'solid = done · light = planned (%)', 'items': items} if items else None


def c_late_milestones(N, title='Milestones — working days late'):
    if not _nok(N):
        return None
    ms = sorted([m for m in (N.get('milestones_open_late') or []) if (_num(m.get('slip_wd')) or 0) > 0],
                key=lambda m: (0 if m.get('type') == 'FinishMilestone' else 1, -(_num(m.get('slip_wd')) or 0)))[:MAX_ROWS]
    items = [{'name': _label(m), 'value': int(_num(m['slip_wd'])), 'label': f"{int(_num(m['slip_wd']))} days",
              'tone': 'bad' if _num(m['slip_wd']) > 20 else 'warn'} for m in ms]
    return ({'type': 'hbar', 'title': title, 'unit': 'working days late', 'items': items,
             'note': 'Planned date against forecast date, open milestones only.'} if items else None)


def c_client_inputs(N):
    if not _nok(N):
        return None
    lo = sorted(N.get('client_inputs_late_open') or [], key=lambda x: -(_num(x.get('slip_wd')) or 0))[:MAX_ROWS]
    items = [{'name': _label(x), 'value': int(_num(x.get('slip_wd')) or 0), 'label': f"{int(_num(x.get('slip_wd')) or 0)} days",
              'tone': 'bad'} for x in lo if (_num(x.get('slip_wd')) or 0) > 0]
    return ({'type': 'hbar', 'title': 'Client items still open — working days late', 'unit': 'working days late',
             'items': items, 'note': 'Items the client must provide, late at the data date.'} if items else None)


def c_path_areas(N):
    """Where the critical path is: how many of its activities sit in each area."""
    ch = (N.get('chain') or []) if _nok(N) else []
    if not ch:
        return None
    counts = {}
    for x in ch:
        a = B._area(x) or 'no WBS'
        c = counts.setdefault(a, {'n': 0, 'open': 0})
        c['n'] += 1
        c['open'] += 0 if x.get('pct') else 1
    rows = sorted(counts.items(), key=lambda kv: -kv[1]['n'])[:MAX_ROWS]
    items = [{'name': a, 'value': c['n'], 'tone': 'bad' if c['open'] == c['n'] else 'warn',
              'label': f"{c['n']} activit{'y' if c['n'] == 1 else 'ies'}" + (' · none started' if c['open'] == c['n'] else f" · {c['open']} not started")}
             for a, c in rows]
    return {'type': 'hbar', 'title': 'The critical path — activities by area', 'unit': 'activities', 'items': items,
            'note': 'Only the activities that decide the finish date.'}


def c_path_first(N):
    """The first critical activities and how late each is."""
    ch = (N.get('chain') or []) if _nok(N) else []
    rows = [x for x in ch if (_num(x.get('slip_wd')) or 0) > 0][:MAX_ROWS]
    items = [{'name': _label(x), 'value': int(_num(x['slip_wd'])), 'label': f"{int(_num(x['slip_wd']))} days",
              'tone': 'bad'} for x in rows]
    return ({'type': 'hbar', 'title': 'First activities on the critical path — working days late', 'unit': 'working days late',
             'items': items, 'note': 'In the order the path runs.'} if items else None)


def c_float_bands(F):
    total, neg, hi = _num(F.get('activity_count')), _num(F.get('neg_float_count')), _num(F.get('float_above'))
    if not total or neg is None:
        return None
    hi = hi or 0
    mid = max(0, total - neg - hi)
    thr = F.get('float_threshold') or 44
    items = [{'name': 'Negative total float (behind)', 'value': int(neg), 'label': f"{int(neg):,}", 'tone': 'bad'},
             {'name': f'0 to {thr} days of total float', 'value': int(mid), 'label': f"{int(mid):,}", 'tone': 'info'},
             {'name': f'More than {thr} days of total float', 'value': int(hi), 'label': f"{int(hi):,}", 'tone': 'warn'}]
    return {'type': 'hbar', 'title': 'Total float — how the activities are spread', 'unit': 'activities', 'items': items,
            'note': 'Activities not yet finished.'}


def c_health(F):
    lag = ((F.get('audit') or {}).get('lag_lead') or {}).get('kpis') or {}
    rows = [('Activities with a missing link', F.get('dangling_count'), 'warn'),
            ('Critical activities out of sequence', F.get('critical_oos'), 'bad'),
            ('Lags longer than %s days' % (lag.get('long_threshold_days') or 14), lag.get('need_justification_count'), 'warn'),
            ('Lags on the critical path', lag.get('critical_count'), 'warn'),
            ('Activities with no predecessor or successor', F.get('open_ends'), 'bad')]
    items = [{'name': n, 'value': int(v), 'label': f"{int(v):,}", 'tone': t} for n, v, t in rows if _num(v)]
    return ({'type': 'hbar', 'title': 'Schedule logic — what to fix', 'unit': 'count', 'items': items,
             'note': 'From Schedule Health.'} if items else None)


def c_value_packages(F):
    vg = F.get('value_gap') or {}
    groups = [g for g in (vg.get('groups') or []) if (_num(g.get('pv')) or 0) > 0][:MAX_ROWS]
    items = [{'name': str(g.get('code')), 'a': _num(g.get('pv')) or 0, 'b': _num(g.get('ev')) or 0,
              'la': B._money(g.get('pv')), 'lb': B._money(g.get('ev'))} for g in groups]
    return ({'type': 'pairs', 'title': f"Value of work by {vg.get('dimension') or 'package'} — planned against done",
             'legend': ['planned by the data date', 'done'], 'unit': "the schedule's own cost unit", 'items': items}
            if items else None)


def c_value_gap(F):
    vg = F.get('value_gap') or {}
    groups = [g for g in (vg.get('groups') or []) if (_num(g.get('gap')) or 0) > 0 and (_num(g.get('pct_of_gap')) or 0) >= 1][:MAX_ROWS]
    items = [{'name': str(g.get('code')), 'value': _num(g.get('gap')), 'label': B._money(g.get('gap')), 'tone': 'bad'}
             for g in groups]
    return ({'type': 'hbar', 'title': f"Work behind plan — by {vg.get('dimension') or 'package'}", 'unit': 'value not done',
             'items': items, 'note': 'Planned value less the value done, at the data date.'} if items else None)


def c_submittals(F):
    rows = [s for s in (F.get('submittals') or []) if (_num(s.get('planned_appr')) or 0) > 0][:MAX_ROWS]
    items = [{'name': f"{s.get('trade')} — {s.get('submittal_type')}", 'a': _num(s.get('planned_appr')) or 0,
              'b': _num(s.get('actual_appr')) or 0, 'la': str(int(_num(s.get('planned_appr')) or 0)),
              'lb': str(int(_num(s.get('actual_appr')) or 0))} for s in rows]
    return ({'type': 'pairs', 'title': 'Design approvals — planned against received', 'legend': ['planned', 'received'],
             'unit': 'approvals', 'items': items} if items else None)


def _is_eng(x):
    import re
    return bool(re.search(r'design|engineer|procure|submittal|shop draw', x.get('name') or '', re.I))


# ── which charts fit which question ─────────────────────────────────────────────
# each entry is a function of (F, N) → one chart or None
_PLAN = {
    'q01': [c_kpis, lambda F, N: c_disciplines(F)],
    'q02': [lambda F, N: c_late_milestones(N)],
    'q03': [lambda F, N: c_path_first(N), lambda F, N: c_client_inputs(N)],
    'q04': [lambda F, N: c_path_areas(N), lambda F, N: c_float_bands(F)],
    'q05': [lambda F, N: c_path_areas(N), lambda F, N: c_client_inputs(N)],
    'q06': [lambda F, N: c_health(F), lambda F, N: c_float_bands(F)],
    'q07': [lambda F, N: c_late_milestones(N, 'What moved against the baseline — working days late')],
    'q08': [lambda F, N: c_value_packages(F), lambda F, N: c_value_gap(F)],
    'q09': [lambda F, N: c_path_areas(N)],
    'q10': [lambda F, N: c_disciplines(F, _is_eng, 'Engineering and procurement — done against planned'),
            lambda F, N: c_submittals(F)],
    'q11': [lambda F, N: c_value_gap(F), lambda F, N: c_path_areas(N)],
    'q12': [lambda F, N: c_health(F)],
    'q13': [lambda F, N: c_client_inputs(N), lambda F, N: c_path_first(N)],
    'q14': [],
    'q15': [c_kpis, lambda F, N: c_disciplines(F)],
}


def build(qid, F, N):
    """The charts for one answer ([] when none fits). Never raises; one chart failing never
    takes the others (or the answer) with it."""
    if qid not in _PLAN or not (F or {}).get('ok'):
        return []
    out = []
    for fn in _PLAN[qid]:
        try:
            c = fn(F, N or {'ok': False})
        except Exception:
            c = None
        if c and c.get('items'):
            out.append(c)
    return out[:2]


# ── the same charts as print-safe HTML (the Manager's briefing and its PDF) ─────────────────
# The screen draws a chart from these dicts with the app's colour tokens (ui/modules/chat.js
# chartHtml).  A briefing printed to PDF has no app stylesheet, so it gets the same layout with
# fixed light colours here — the same rows, values and labels as the screen.
_TONE_HEX = {'bad': '#dc2626', 'warn': '#d97706', 'good': '#16a34a', 'info': '#1d4ed8'}

CHART_CSS = (
    '.qc{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px 8px;margin-bottom:12px;'
    'break-inside:avoid}'
    '.qc-h{font-size:12px;font-weight:700;color:#334155;margin-bottom:6px}'
    '.qc-r{display:flex;align-items:center;gap:10px;font-size:11.5px;padding:2px 0}'
    '.qc-n{flex:0 0 38%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#334155}'
    '.qc-t{position:relative;flex:1;height:10px;background:#f1f5f9;border-radius:3px;overflow:hidden}'
    '.qc-t2{flex:1;display:flex;flex-direction:column;gap:2px}'
    '.qc-t i{position:absolute;left:0;top:0;bottom:0;border-radius:3px}'
    '.qc-t i.pl{background:#bfdbfe}.qc-t i.ac{background:#1d4ed8}'
    '.qc-v{flex:0 0 auto;min-width:74px;text-align:right;font-weight:600;color:#1e293b}'
    '.qc-v small{font-weight:400;color:#64748b}'
    '.qc-f{font-size:10.5px;color:#64748b;margin-top:4px}'
    '.qc-k{display:flex;gap:8px;flex-wrap:wrap}'
    '.qc-ki{flex:1;min-width:120px;border:1px solid #e2e8f0;border-left:3px solid;border-radius:6px;padding:6px 9px}'
    '.qc-ki .k{font-size:9.5px;text-transform:uppercase;letter-spacing:.4px;color:#94a3b8;font-weight:700}'
    '.qc-ki .v{font-size:14px;font-weight:700}.qc-ki .h{font-size:10.5px;color:#64748b}'
    '.qc-t i, .qc-ki{-webkit-print-color-adjust:exact;print-color-adjust:exact}')


def _pc(v, mx):
    v = _num(v) or 0.0
    return '%.1f' % (max(0.0, min(100.0, v / mx * 100.0)) if mx and mx > 0 else 0.0)


def chart_html(c):
    """One chart dict (see the module docstring) → print-safe HTML ('' when it has no rows)."""
    import html as _h
    e = lambda v: _h.escape('' if v is None else str(v))
    if not isinstance(c, dict):
        return ''
    items = [x for x in (c.get('items') or []) if isinstance(x, dict)]
    if not items:
        return ''
    t = c.get('type')
    row = lambda n, track, v: (f'<div class="qc-r"><div class="qc-n" title="{e(n)}">{e(n)}</div>{track}'
                               f'<div class="qc-v">{v}</div></div>')
    foot = ''
    if t == 'kpi':
        body = '<div class="qc-k">' + ''.join(
            f'<div class="qc-ki" style="border-left-color:{_TONE_HEX.get(x.get("tone"), _TONE_HEX["info"])}">'
            f'<div class="k">{e(x.get("label"))}</div>'
            f'<div class="v" style="color:{_TONE_HEX.get(x.get("tone"), "#1e293b")}">{e(x.get("value"))}</div>'
            f'<div class="h">{e(x.get("hint") or "")}</div></div>' for x in items) + '</div>'
    elif t == 'bars':
        body = ''.join(row(x.get('name'),
                           f'<div class="qc-t"><i class="pl" style="width:{_pc(x.get("planned"), 100)}%"></i>'
                           f'<i class="ac" style="width:{_pc(x.get("actual"), 100)}%"></i></div>',
                           f'{round(_num(x.get("actual")) or 0)}% <small>of {round(_num(x.get("planned")) or 0)}%</small>')
                       for x in items)
        foot = c.get('legend') or ''
    elif t == 'pairs':
        mx = max([_num(x.get('a')) or 0 for x in items] + [_num(x.get('b')) or 0 for x in items] + [0])
        body = ''.join(row(x.get('name'),
                           f'<div class="qc-t2"><div class="qc-t"><i class="pl" style="width:{_pc(x.get("a"), mx)}%"></i></div>'
                           f'<div class="qc-t"><i class="ac" style="width:{_pc(x.get("b"), mx)}%"></i></div></div>',
                           f'{e(x.get("lb"))} <small>of {e(x.get("la"))}</small>') for x in items)
        lg = c.get('legend') or []
        foot = ((f'upper bar = {lg[0]} · lower bar = {lg[1]}' if len(lg) == 2 else '')
                + (f' · in {c["unit"]}' if c.get('unit') else ''))
    elif t == 'hbar':
        mx = max([abs(_num(x.get('value')) or 0) for x in items] + [0])
        body = ''.join(row(x.get('name'),
                           f'<div class="qc-t"><i style="width:{_pc(abs(_num(x.get("value")) or 0), mx)}%;'
                           f'background:{_TONE_HEX.get(x.get("tone"), _TONE_HEX["info"])}"></i></div>',
                           e(x.get('label') if x.get('label') is not None else x.get('value'))) for x in items)
        foot = c.get('note') or ''
    else:
        return ''
    return (f'<div class="qc" data-chart="{e(t)}"><div class="qc-h">{e(c.get("title") or "")}</div>{body}'
            + (f'<div class="qc-f">{e(foot)}</div>' if foot else '') + '</div>')


def for_briefing(F, N):
    """The charts a manager's briefing carries under its S-curve: progress by discipline, then
    the milestones running late (or, when none are, the client items overdue).  [] when the
    facts are not there.  Never raises."""
    out = []
    for fn in (lambda: c_disciplines(F), lambda: c_late_milestones(N) or c_client_inputs(N)):
        try:
            c = fn()
        except Exception:
            c = None
        if c and c.get('items'):
            out.append(c)
    return out
