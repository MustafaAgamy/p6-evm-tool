"""Weather → Forecast — a finish-date forecast built from the schedule's own
figures plus the weather impact Calendar Audit already computed. No new weather
call: it reuses the saved `last_weather` estimate, so there is one weather engine.

build_forecast(result, weather) → three explainable finish-date scenarios:
  best   — the schedule holds its current plan from the data date (its forecast finish)
  likely — current schedule performance (SPI) continues to completion
  worst  — likely, plus the expected weather impact (when weather has been run)
Every input is guarded; missing pieces simply drop the scenarios that need them.
"""
from datetime import datetime, date, timedelta


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _parse(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v)[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def _iso(d):
    return d.isoformat() if isinstance(d, date) else None


def build_forecast(result, weather=None):
    result = result or {}
    dd = _parse(result.get('data_date'))
    f = _parse(result.get('expected_finish'))       # current forecast finish (schedule)
    b = _parse(result.get('baseline_finish'))       # target
    spi = _num(result.get('spi'))

    # Performance-adjusted finish: if the current SPI keeps up, the remaining span
    # from the data date stretches by 1/SPI.
    p = f
    if f and dd and spi and spi > 0 and f > dd:
        remaining = (f - dd).days
        p = dd + timedelta(days=round(remaining / spi))

    # Weather delta = the extra calendar days Calendar Audit's weather-adjusted
    # finish adds on top of the schedule's finish (reused, not recomputed).
    wdelta, wadj = 0, None
    if weather:
        wadj = _parse(weather.get('weather_adjusted_finish'))
        if wadj and f:
            wdelta = max(0, (wadj - f).days)
        elif weather.get('net_finish_delay') is not None:
            try:
                wdelta = max(0, int(weather['net_finish_delay']))   # working days ≈ days (fallback)
            except (TypeError, ValueError):
                wdelta = 0
    w = (p + timedelta(days=wdelta)) if (p and wdelta > 0) else None

    def delta(d):
        return None if (d is None or b is None) else (d - b).days

    scenarios = []
    if f:
        scenarios.append({'key': 'best', 'label': 'Best case', 'date': _iso(f), 'delta_days': delta(f),
                          'basis': 'The schedule holds its current plan from the data date.'})
    if p:
        scenarios.append({'key': 'likely', 'label': 'Likely', 'date': _iso(p), 'delta_days': delta(p),
                          'basis': 'Current schedule performance (SPI) continues to completion.'})
    if w:
        scenarios.append({'key': 'worst', 'label': 'Worst case', 'date': _iso(w), 'delta_days': delta(w),
                          'basis': 'Current performance plus the expected weather impact.'})

    return {
        'data_date':               _iso(dd),
        'baseline_finish':         _iso(b),
        'forecast_finish':         _iso(f),
        'spi':                     spi,
        'has_weather':             bool(w),
        'weather_days':            wdelta,
        'weather_adjusted_finish': _iso(wadj),
        'scenarios':               scenarios,
    }
