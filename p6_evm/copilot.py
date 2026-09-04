"""AI Copilot · TIA — the deterministic, offline core.

Two things, both computed from the already-known result (no LLM, no key):
  • a Time-Impact Analysis (TIA): how far the finish has slipped from baseline and
    what is driving it — slippage to date, performance-projected slip, weather;
  • prioritised copilot insights: the findings that matter, most severe first,
    each with a recommended action.

The optional AI narrative (the existing key-gated AI review) is layered on top in
the UI; everything here works with no account.
"""
from .forecast import build_forecast


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _scen(fc, key):
    return next((s for s in fc.get('scenarios', []) if s['key'] == key), None)


def build_tia(fc):
    """Decompose the finish slip into to-date / performance / weather components."""
    best, likely, worst = _scen(fc, 'best'), _scen(fc, 'likely'), _scen(fc, 'worst')
    to_date = best['delta_days'] if best else None          # baseline → current forecast finish
    perf = (likely['delta_days'] - best['delta_days']) if (likely and best and
            likely['delta_days'] is not None and best['delta_days'] is not None) else None
    weather = (worst['delta_days'] - likely['delta_days']) if (worst and likely and
               worst['delta_days'] is not None and likely['delta_days'] is not None) else None
    components = []
    if to_date is not None:
        components.append({'key': 'to_date', 'label': 'Slippage to date',
                           'days': to_date, 'basis': 'Current forecast finish vs the baseline finish.'})
    if perf:
        components.append({'key': 'performance', 'label': 'Performance-projected',
                           'days': perf, 'basis': 'Extra slip if the current SPI continues to completion.'})
    if weather:
        components.append({'key': 'weather', 'label': 'Weather',
                           'days': weather, 'basis': 'Expected weather impact, reused from Calendar Audit.'})
    return {
        'baseline_finish': fc.get('baseline_finish'),
        'forecast_finish': fc.get('forecast_finish'),
        'likely_finish':   likely['date'] if likely else None,
        'likely_slip':     likely['delta_days'] if likely else None,
        'worst_finish':    worst['date'] if worst else None,
        'worst_slip':      worst['delta_days'] if worst else None,
        'components':      components,
    }


def _pct(frac):
    f = _num(frac)
    return None if f is None else round(f * 100)


def build_insights(result, fc):
    result = result or {}
    out = []
    spi = _num(result.get('spi'))
    cpi = _num(result.get('cpi'))
    best = _scen(fc, 'best')
    delay = best['delta_days'] if best else result.get('delay_days')

    # schedule
    if spi is not None:
        behind = round((1 - spi) * 100)
        if spi < 0.85:
            out.append(('high', f'Significantly behind schedule (SPI {spi:.2f})',
                        f'The project is earning about {behind}% less value than planned for the time elapsed. '
                        f'Re-sequence or add resource to the critical path and build a recovery plan.'))
        elif spi < 0.95:
            out.append(('med', f'Behind schedule (SPI {spi:.2f})',
                        f'About {behind}% under the planned earn rate. Target the areas behind plan before the variance widens.'))
        elif spi < 1.0:
            out.append(('low', f'Marginally behind schedule (SPI {spi:.2f})',
                        'A small shortfall against plan — monitor the critical path.'))
        else:
            out.append(('low', f'On or ahead of schedule (SPI {spi:.2f})',
                        'Schedule performance is healthy; hold the plan and watch for new critical risks.'))

    # finish slip
    if delay is not None and delay > 0:
        sev = 'high' if delay > 45 else ('med' if delay > 10 else 'low')
        out.append((sev, f'Finish forecast {delay} days late',
                    'The current forecast finish is later than the baseline. Recovery of this slip should be the focus.'))
    elif delay is not None and delay < 0:
        out.append(('low', f'Finish forecast {abs(delay)} days early',
                    'The current forecast finishes ahead of the baseline — a positive schedule position.'))

    # cost
    if cpi is not None and cpi < 0.95:
        out.append(('med', f'Over budget (CPI {cpi:.2f})',
                    'Actual cost is outrunning earned value. Review the cost drivers on the lagging areas.'))

    # worst category
    cats = result.get('categories') or {}
    ranked = sorted(((n, _num(c.get('planned_pct')), _num(c.get('actual_pct'))) for n, c in cats.items()),
                    key=lambda t: ((t[2] or 0) - (t[1] or 0)))
    behind_cat = next((t for t in ranked if t[1] is not None and t[2] is not None and (t[2] - t[1]) < -0.05), None)
    if behind_cat:
        out.append(('med', f'{behind_cat[0]} is the area furthest behind',
                    f'{_pct(behind_cat[2])}% actual against {_pct(behind_cat[1])}% planned. Prioritise it in the recovery plan.'))

    if not out:
        out.append(('low', 'Not enough data for insights',
                    'Import a schedule with metrics to generate copilot insights.'))

    rank = {'high': 0, 'med': 1, 'low': 2}
    out.sort(key=lambda t: rank[t[0]])
    return [{'severity': s, 'title': t, 'detail': d} for (s, t, d) in out]


def build_copilot(result, weather=None):
    fc = build_forecast(result, weather)
    return {
        'tia': build_tia(fc),
        'insights': build_insights(result, fc),
        'has_forecast': bool(fc.get('scenarios')),
    }
