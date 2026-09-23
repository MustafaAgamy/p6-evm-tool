"""§15 Volume of Work — planned value-of-work distribution + cumulative S-curve.

Spreads each activity's budgeted cost (``data.bac_by_activity``) LINEARLY across its working
days — the same P6 Resource-Usage time distribution the resource loading uses (see
``resload._wd_spread``) — and sums by month, giving the monthly value of work and the running
cumulative S-curve (planned value). Generic: derived from any loaded file, nothing hardcoded.
Currency is read from the file (XER ``CURRTYPE``); with none it degrades to a plain number.
"""
from collections import defaultdict

from p6_narrative import resload

BAR_HEX = '1F4E79'         # navy columns — monthly value of work
CURVE_HEX = 'E8A33D'       # amber line — cumulative S-curve


# ── currency (generic, from the file) ─────────────────────────────────────────
def read_currency(path):
    """``(symbol|None, name|None)`` for the base currency, read from the XER ``CURRTYPE`` table
    (base = the row whose ``base_exch_rate`` is closest to 1.0). Prefers the human currency
    ``curr_type`` for the descriptive note. Returns ``(None, None)`` for XML / no currency."""
    if not path or not str(path).lower().endswith('.xer'):
        return None, None
    try:
        from p6_evm.xer import read_xer_tables
        rows = (read_xer_tables(path) or {}).get('CURRTYPE') or []
        if not rows:
            return None, None

        def _drate(r):
            try:
                return abs(float(r.get('base_exch_rate') or 0) - 1.0)
            except (TypeError, ValueError):
                return 9e9
        base = min(rows, key=_drate)
        sym = (base.get('curr_symbol') or '').strip()
        name = (base.get('curr_type') or base.get('curr_short_name') or '').strip()
        return (sym or None), (name or None)
    except Exception:
        return None, None


def _money(v, sym):
    n = '{:,.0f}'.format(round(float(v or 0)))
    return (sym + n) if sym else n


def _unit_note(sym, name):
    if sym and name:
        return 'in %s (%s)' % (name, sym)
    if sym:
        return 'in the schedule currency (%s)' % sym
    if name:
        return 'in %s' % name
    return 'as cost-loaded (no currency defined in the file)'


# ── computation ───────────────────────────────────────────────────────────────
def _compute(data):
    """Monthly value of work + cumulative, via linear working-day spread of each activity's
    budgeted cost. Returns None when the schedule carries no cost loading with dates."""
    monthly = defaultdict(float)
    total_cost = 0.0
    n_act = 0
    activities = getattr(data, 'activities', None) or {}
    calendars = getattr(data, 'calendars', None) or {}
    for oid, bac in (getattr(data, 'bac_by_activity', None) or {}).items():
        try:
            bac = float(bac or 0)
        except (TypeError, ValueError):
            continue
        if bac == 0:
            continue
        act = activities.get(oid)
        if not act:
            continue
        ps, pf = act.get('planned_start'), act.get('planned_finish')
        if not ps or not pf:
            continue
        cal = calendars.get(act.get('calendar_id'))
        for k, v in resload._wd_spread(bac, ps, pf, cal).items():
            monthly[k] += v
        total_cost += bac
        n_act += 1
    keys = sorted(monthly.keys())
    if not keys:
        return None
    span = resload._month_span(keys[0], keys[-1])
    values = [round(monthly.get(k, 0.0)) for k in span]
    labels = [resload._mlabel(*k) for k in span]
    cum, run = [], 0.0
    for v in values:
        run += v
        cum.append(round(run))
    pi = max(range(len(values)), key=lambda i: values[i])
    return {
        'labels': labels, 'values': values, 'cum': cum,
        'total_cost': total_cost, 'peak_val': values[pi],
        'peak_label': resload._mfull(*span[pi]),
        'window': '%s – %s' % (resload._mfull(*span[0]), resload._mfull(*span[-1])),
        'n_months': len(span), 'n_act': n_act,
    }


# ── public entry ──────────────────────────────────────────────────────────────
def volume_of_work(data, path=None):
    """The §15 payload consumed by both renderers, or ``{'available': False}`` when the schedule
    is not cost-loaded. One combo chart (monthly value-of-work columns + cumulative S-curve) and
    a two-row summary. Chart labels are in whole millions; the summary shows full figures."""
    cf = _compute(data)
    if not cf:
        return {'available': False}
    sym, name = read_currency(path)
    money = lambda v: _money(v, sym)
    # Word chart number format — whole millions with the currency symbol ($138M).
    num_fmt = ('"%s"#,##0,,"M"' % sym) if sym else '#,##0,,"M"'
    return {
        'available': True,
        'intro': ('The planned volume of work derived from the baseline cost loading. Each '
                  'activity’s budgeted value is spread linearly across its working days '
                  '(P6’s Resource Usage time distribution) and summed by month, giving the '
                  'monthly value of work and the cumulative S-curve. Figures are %s.'
                  % _unit_note(sym, name)),
        'chart': {
            'labels': cf['labels'], 'values': cf['values'], 'cum': cf['cum'],
            'bar_color': BAR_HEX, 'line_color': CURVE_HEX, 'num_fmt': num_fmt,
            'sym': sym or '',
            # pre-formatted rows for the no-chart fallback (both renderers)
            'table_headers': ['Month', 'Value of work', 'Cumulative'],
            'table_rows': [[lb, money(v), money(c)]
                           for lb, v, c in zip(cf['labels'], cf['values'], cf['cum'])],
        },
        'caption': ('The monthly value of work (columns, left axis) with the running cumulative '
                    'value (the S-curve, right axis). The final point of the S-curve equals the '
                    'total value of work. Values on the chart are shown in millions.'),
        'end_caption': 'Total value of work (final cumulative point): %s.' % money(cf['total_cost']),
        'summary_headers': ['Metric', 'Value'],
        'summary_rows': [
            ['Total value of work', money(cf['total_cost'])],
            ['Peak monthly value of work', '%s  (%s)' % (cf['peak_label'], money(cf['peak_val']))],
        ],
    }
