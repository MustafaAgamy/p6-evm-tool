"""Build the Copilot's 'project brain' — a normalized, plain summary of the modules'
results for the open project, so the offline answer engine can reason across them.

Reads the already-computed result dict (never re-derives a number). Progress figures
arrive as 0-1 fractions and are surfaced here as whole percents (0-100) ready to speak.
"""


def _pct(frac):
    """0-1 fraction -> whole percent (0-100), or None."""
    try:
        return round(float(frac) * 100)
    except (TypeError, ValueError):
        return None


def build_context(result):
    """Normalize a compute()/DB result dict into the facts the answer engine speaks from."""
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
    return {
        'project_name': result.get('project_name') or 'the project',
        'delay_days': delay,
        'behind': delay is not None and delay > 0,
        'ahead': delay is not None and delay < 0,
        'pace_pct': round(spi * 100) if spi is not None else None,   # SPI as "% of planned speed"
        'planned_pct': _pct(result.get('overall_planned_pct')),
        'actual_pct': _pct(result.get('overall_actual_pct')),
        'disciplines': disciplines,
        'worst_discipline': worst,
    }
