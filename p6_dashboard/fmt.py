"""Small display formatters shared by dashboard providers. Providers pre-format
KPI/score values to strings so the client renderer stays generic."""


def pct(x, dp=1):
    return '—' if x is None else f'{x:.{dp}f}%'


def num2(x):
    return '—' if x is None else f'{x:.2f}'


def money(x):
    """Compact currency: 156.5 M / 950 K / 420."""
    if x is None:
        return '—'
    a = abs(x)
    sign = '-' if x < 0 else ''
    if a >= 1e6:
        return f'{sign}{a / 1e6:.1f} M'
    if a >= 1e3:
        return f'{sign}{a / 1e3:.0f} K'
    return f'{sign}{a:.0f}'


def signed_days(x):
    if x is None:
        return '—'
    n = int(round(x))
    return '0 d' if n == 0 else (f'+{n} d' if n > 0 else f'{n} d')


def spi_status(v):
    if v is None:
        return 'neutral'
    if v >= 0.95:
        return 'good'
    if v >= 0.85:
        return 'warn'
    return 'bad'


def band_status(overall):
    """Map a 0-100 score to a semantic status."""
    if overall is None:
        return 'neutral'
    if overall >= 85:
        return 'good'
    if overall >= 60:
        return 'warn'
    return 'bad'
