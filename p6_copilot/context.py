"""Build the Copilot's 'project brain' — a normalized, plain summary of the modules'
results for the open project, so the offline answer engine can reason across them.

Reads the already-computed result dict (never re-derives a number). Progress figures
arrive as 0-1 fractions and are surfaced here as whole percents (0-100) ready to speak;
dates are surfaced as plain "03-Mar-2025" strings so answers can anchor to the cutoff.
"""
from datetime import datetime, date


def _pct(frac):
    """0-1 fraction -> whole percent (0-100), or None."""
    try:
        return round(float(frac) * 100)
    except (TypeError, ValueError):
        return None


def _fmt_date(v):
    """datetime / ISO string -> '03-Mar-2025', or None."""
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v)
        except ValueError:
            return v
    if isinstance(v, (datetime, date)):
        return v.strftime('%d-%b-%Y')
    return str(v)


def build_context(result, audit=None, prev_delay=None):
    """Normalize a compute()/DB result dict into the facts the answer engine speaks from.

    `audit` = the stored audit_modules dict (for risk facts). `prev_delay` = the previous
    update's delay in working days (for the trend). Both optional.
    """
    result = result or {}
    cats = result.get('categories') or {}

    disciplines = []
    for name, c in cats.items():
        if (c.get('weight') or 0) <= 0:
            continue  # structural rows (milestones / summary) aren't project scope
        planned, actual = _pct(c.get('planned_pct')), _pct(c.get('actual_pct'))
        if planned is None or actual is None:
            continue
        disciplines.append({'name': name, 'weight': c.get('weight'),
                            'planned': planned, 'actual': actual, 'gap': planned - actual})
    disciplines.sort(key=lambda d: d['gap'], reverse=True)
    worst = disciplines[0] if disciplines and disciplines[0]['gap'] > 0 else None

    delay = result.get('delay_days')
    spi = result.get('spi')
    ctx = {
        'project_name': result.get('project_name') or 'the project',
        'data_date': _fmt_date(result.get('data_date')),          # the update/cutoff date
        'baseline_finish': _fmt_date(result.get('baseline_finish')),
        'forecast_finish': _fmt_date(result.get('expected_finish')),
        'delay_days': delay,
        'behind': delay is not None and delay > 0,
        'ahead': delay is not None and delay < 0,
        'pace_pct': round(spi * 100) if spi is not None else None,   # SPI as "% of planned speed"
        'planned_pct': _pct(result.get('overall_planned_pct')),
        'actual_pct': _pct(result.get('overall_actual_pct')),
        'disciplines': disciplines,
        'worst_discipline': worst,
        'trend': None,
        'oos_count': None,
        'float_grade': None,
    }
    # Trend vs the previous update — managers care about direction as much as the number.
    if prev_delay is not None and delay is not None:
        delta = delay - prev_delay
        ctx['trend'] = {'prev_delay': prev_delay, 'delta': delta,
                        'direction': 'worse' if delta > 0 else ('better' if delta < 0 else 'same')}
    # Risk facts from the audit modules (defensive — any part may be absent).
    if isinstance(audit, dict):
        mods = audit.get('modules') or {}
        ctx['oos_count'] = ((mods.get('out_of_sequence') or {}).get('kpis') or {}).get('oos_count')
        ctx['float_grade'] = (mods.get('float') or {}).get('grade')
    return ctx
