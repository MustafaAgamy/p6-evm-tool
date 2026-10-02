"""The AI Chat Professional Dashboard as an Excel workbook (comments 2 / 29: every feature's
screen = PDF = Excel; the cost answer even tells the planner to "export the one-pager to Excel").

The page posts the dashboard payload it is showing (``p6_chat.dashboard.build`` — the same dict
the screen drew), so every figure in the workbook is the one on screen; nothing is recomputed.

    sheets(payload) → the ``sheets`` list for ``p6_evm.xlsx_writer.write_sections_xlsx``

Sheet 'Dashboard': the headline (verdict, message, schedule variance), the KPI tiles, the SPI /
CPI gauges and the time status.  'Progress': planned vs actual by discipline and the EV vs PV
gap by activity code.  'S-Curve': the monthly planned / earned / expected percentages behind
the chart.  An empty part is left out, never invented.
"""


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _r(v, nd=2):
    n = _num(v)
    return '—' if n is None else round(n, nd)


def sheets(payload):
    p = payload if isinstance(payload, dict) else {}
    meta, health = p.get('meta') or {}, p.get('health') or {}
    ts, sc = p.get('time_status') or {}, p.get('scurve') or {}
    head = [
        ['Project', meta.get('project') or '—'],
        ['Data date', meta.get('data_date') or '—'],
        ['Baseline finish', meta.get('baseline_finish') or '—'],
        ['Forecast finish', meta.get('forecast_finish') or '—'],
        ['Weighting', 'Cost-loaded schedule' if meta.get('cost_loaded') else 'Duration-weighted (not cost-loaded)'],
        ['Verdict', (health.get('verdict') or '—') + (f" · SPI {_num(health['spi']):.2f}" if _num(health.get('spi')) is not None else '')],
        ['In short', health.get('message') or '—'],
    ]
    if _num(meta.get('bac_m')):
        head.append(['Budget at completion (M)', _r(meta.get('bac_m'), 3)])
    if _num(health.get('schedule_variance_m')) is not None:
        head.append(['Schedule variance (EV − PV, M)', _r(health.get('schedule_variance_m'), 3)])
    dash = [{'title': 'Professional Dashboard — Earned Value Command Board', 'headers': ['Item', 'Value'], 'rows': head}]
    kpis = [[k.get('k') or '', k.get('v') or '—', k.get('h') or ''] for k in (p.get('kpis') or []) if isinstance(k, dict)]
    if kpis:
        dash.append({'title': 'Key figures', 'headers': ['Figure', 'Value', 'Meaning'], 'rows': kpis})
    gauges = [[g.get('label') or '', _r(g.get('value'))] for g in (p.get('gauges') or []) if isinstance(g, dict)]
    if gauges:
        dash.append({'title': 'Performance indices — 1.00 is on plan', 'headers': ['Index', 'Value'], 'rows': gauges})
    trows = []
    for lab, key in (('Start', 'start'), ('Finish', 'finish')):
        if ts.get(key):
            trows.append([lab, ts[key]])
    for lab, key in (('Duration elapsed (%)', 'elapsed_pct'), ('Value earned (%)', 'earned_pct')):
        if _num(ts.get(key)) is not None:
            trows.append([lab, _r(ts.get(key), 1)])
    if ts.get('exceeded_days'):
        trows.append(['Days past the baseline finish', ts['exceeded_days']])
    if trows:
        dash.append({'title': 'Time status', 'headers': ['Item', 'Value'], 'rows': trows})
    out = [{'name': 'Dashboard', 'blocks': dash}]

    prog = []
    disc = [[d.get('name') or '', _r(d.get('planned'), 1), _r(d.get('actual'), 1),
             _r((_num(d.get('actual')) or 0) - (_num(d.get('planned')) or 0), 1)]
            for d in (p.get('disciplines') or []) if isinstance(d, dict)]
    if disc:
        prog.append({'title': 'Planned vs actual — by discipline', 'headers':
                     ['Discipline', 'Planned %', 'Actual %', 'Actual − planned (points)'], 'rows': disc})
    gap = p.get('gap_by_code') or {}
    grows = [[g.get('code') or '', _r(g.get('gap_m'), 3), 'behind' if (_num(g.get('gap_m')) or 0) > 0 else 'ahead']
             for g in (gap.get('rows') or []) if isinstance(g, dict)]
    if grows:
        grows.append(['Total schedule variance (PV − EV)', _r(gap.get('total_m'), 3), ''])
        prog.append({'title': 'EV vs PV gap — by activity code', 'note': gap.get('label') or None,
                     'headers': ['Code value', 'PV − EV (M)', 'Position'], 'rows': grows})
    if prog:
        out.append({'name': 'Progress', 'blocks': prog})

    months = sc.get('months') or []
    if months:
        col = lambda k, i: _r((sc.get(k) or [None] * len(months))[i] if i < len(sc.get(k) or []) else None, 1)
        dd = sc.get('dd_index')
        rows = [[m, col('plan', i), col('earn', i), col('fore', i), 'data date' if i == dd else '']
                for i, m in enumerate(months)]
        out.append({'name': 'S-Curve', 'blocks': [{
            'title': 'Value of work — cumulative % of budget by month',
            'headers': ['Month', 'Planned value %', 'Earned value %', 'Expected / forecast %', ''], 'rows': rows}]})
    return out
