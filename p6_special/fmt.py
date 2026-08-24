"""Shared formatters for Special Report providers.

EVM percentages in this tool are 0..1 fractions (displayed x100). SPI/CPI are
ratios. PV/EV/AC are absolute money. Keep every provider on these so the report
reads consistently.
"""

DASH = '—'


def pct01(x, dp=1):
    """Format a 0..1 fraction as a percent (e.g. 0.614 -> '61.4%')."""
    return DASH if x is None else f'{x * 100:.{dp}f}%'


def signed_pct01(x, dp=1):
    return DASH if x is None else f'{x * 100:+.{dp}f}%'


def pct100(x, dp=1):
    """Format a value already on a 0..100 scale as a percent."""
    return DASH if x is None else f'{x:.{dp}f}%'


def ratio(x, dp=2):
    """SPI / CPI style ratio (e.g. 0.60)."""
    return DASH if x is None else f'{x:.{dp}f}'


def num(x, dp=0):
    return DASH if x is None else f'{x:,.{dp}f}'


def money(x):
    """Compact money like the EVM tab: B / M (2dp) / comma-grouped."""
    if x is None:
        return DASH
    a = abs(x)
    if a >= 1e9:
        return f'{x / 1e9:.2f}B'
    if a >= 1e6:
        return f'{x / 1e6:.2f}M'
    return f'{x:,.0f}'


def days(x):
    if x is None:
        return DASH
    n = int(round(x))
    return f'{n} day' + ('' if n == 1 else 's')
