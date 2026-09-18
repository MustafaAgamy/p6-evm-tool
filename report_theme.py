"""Report appearance themes — the ONE shared source of report colour.

Every report renderer (p6_evm, p6_compare, p6_period, p6_update, p6_calendar,
p6_kb, p6_audit …) injects ``theme_style_tag(mode)`` into its ``<head>`` and reads
every colour from the ``--rpt-*`` CSS custom properties defined here. That makes the
whole set of appearance modes work for every current report — and any future report
gets them for free, just by using the same tokens.

Modes are named palettes only; they never change a single number. ``light`` is the
default. The on-screen preview and the exported PDF share this exact CSS, so what you
preview is what you print.

Design notes baked in:
  * Dark modes are slate/navy, not pure black; cards sit slightly above the page.
  * Chart series and accents are brightened / desaturated per background so they stay
    legible (WCAG-ish contrast) on light AND dark grounds.
  * ``print-color-adjust: exact`` is emitted so Chrome ``--print-to-pdf`` keeps the
    background fills of the dark modes instead of dropping them to white.
"""

# ── Canonical token vocabulary (every mode must define every key) ────────────
#   surfaces / text / lines / accent / table header / semantic / charts
_TOKEN_ORDER = (
    'rpt-bg', 'rpt-surface', 'rpt-surface-2', 'rpt-edge',
    'rpt-ink', 'rpt-ink-soft', 'rpt-muted',
    'rpt-hair', 'rpt-hair-strong',
    'rpt-accent', 'rpt-accent-ink', 'rpt-accent-soft',
    'rpt-th-bg', 'rpt-th-ink',
    'rpt-good', 'rpt-good-bg', 'rpt-warn', 'rpt-warn-bg', 'rpt-bad', 'rpt-bad-bg',
    'rpt-chart-grid', 'rpt-chart-axis',
    'rpt-series-1', 'rpt-series-2', 'rpt-series-3',
    'rpt-series-4', 'rpt-series-5', 'rpt-series-6',
)

# ── The six palettes (ordered — this order drives the UI picker) ─────────────
THEMES = {
    'light': {
        'rpt-bg': '#ffffff', 'rpt-surface': '#f7f9fc', 'rpt-surface-2': '#eef2f7', 'rpt-edge': '#d9dee6',
        'rpt-ink': '#182231', 'rpt-ink-soft': '#41506a', 'rpt-muted': '#6b7688',
        'rpt-hair': '#e6eaf1', 'rpt-hair-strong': '#d2d8e2',
        'rpt-accent': '#2563eb', 'rpt-accent-ink': '#ffffff', 'rpt-accent-soft': '#dbe6ff',
        'rpt-th-bg': '#dde6f0', 'rpt-th-ink': '#1e2d40',
        'rpt-good': '#15803d', 'rpt-good-bg': '#dcf3e4', 'rpt-warn': '#b45309', 'rpt-warn-bg': '#fbeccf',
        'rpt-bad': '#c02626', 'rpt-bad-bg': '#fadddd',
        'rpt-chart-grid': '#e8ecf3', 'rpt-chart-axis': '#5b6675',
        'rpt-series-1': '#3b6fa8', 'rpt-series-2': '#7ba63c', 'rpt-series-3': '#c0764a',
        'rpt-series-4': '#6b5bbd', 'rpt-series-5': '#2f9c9c', 'rpt-series-6': '#b8497f',
    },
    'dark': {
        'rpt-bg': '#131922', 'rpt-surface': '#1a212c', 'rpt-surface-2': '#212a37', 'rpt-edge': '#2a3442',
        'rpt-ink': '#e8eef6', 'rpt-ink-soft': '#aeb9c9', 'rpt-muted': '#8090a2',
        'rpt-hair': '#28323f', 'rpt-hair-strong': '#37424f',
        'rpt-accent': '#5b9bff', 'rpt-accent-ink': '#0b0f16', 'rpt-accent-soft': '#1d2c44',
        'rpt-th-bg': '#223244', 'rpt-th-ink': '#dfe8f2',
        'rpt-good': '#48c26a', 'rpt-good-bg': '#16301f', 'rpt-warn': '#e6a53a', 'rpt-warn-bg': '#33290f',
        'rpt-bad': '#f2707a', 'rpt-bad-bg': '#351a1d',
        'rpt-chart-grid': '#28323f', 'rpt-chart-axis': '#7a8797',
        'rpt-series-1': '#5b9bff', 'rpt-series-2': '#78c257', 'rpt-series-3': '#e0925a',
        'rpt-series-4': '#a68bff', 'rpt-series-5': '#4fc7c7', 'rpt-series-6': '#f06fa6',
    },
    'midnight': {
        'rpt-bg': '#0f1830', 'rpt-surface': '#14203f', 'rpt-surface-2': '#1a2848', 'rpt-edge': '#273760',
        'rpt-ink': '#eaf0ff', 'rpt-ink-soft': '#b6c4e6', 'rpt-muted': '#7c8cb5',
        'rpt-hair': '#223056', 'rpt-hair-strong': '#2e4070',
        'rpt-accent': '#6ea8ff', 'rpt-accent-ink': '#071022', 'rpt-accent-soft': '#16274d',
        'rpt-th-bg': '#1a2a50', 'rpt-th-ink': '#e6eeff',
        'rpt-good': '#4fd1a0', 'rpt-good-bg': '#0e2b28', 'rpt-warn': '#f0b429', 'rpt-warn-bg': '#2e2610',
        'rpt-bad': '#ff7a8a', 'rpt-bad-bg': '#331722',
        'rpt-chart-grid': '#1f2e52', 'rpt-chart-axis': '#6b7ba8',
        'rpt-series-1': '#6ea8ff', 'rpt-series-2': '#63d19b', 'rpt-series-3': '#f0b45f',
        'rpt-series-4': '#b18bff', 'rpt-series-5': '#46c7d8', 'rpt-series-6': '#ff87b0',
    },
    'sepia': {
        'rpt-bg': '#f8f2e6', 'rpt-surface': '#f1e9d8', 'rpt-surface-2': '#ece2cd', 'rpt-edge': '#e2d6bf',
        'rpt-ink': '#3a2f22', 'rpt-ink-soft': '#5c4b36', 'rpt-muted': '#8a7859',
        'rpt-hair': '#e6dcc7', 'rpt-hair-strong': '#d8ccb0',
        'rpt-accent': '#a8631f', 'rpt-accent-ink': '#ffffff', 'rpt-accent-soft': '#f0e2cc',
        'rpt-th-bg': '#e7dcc3', 'rpt-th-ink': '#4a3c28',
        'rpt-good': '#5f7d3b', 'rpt-good-bg': '#e6ecd4', 'rpt-warn': '#b07016', 'rpt-warn-bg': '#f3e6c8',
        'rpt-bad': '#a83a2a', 'rpt-bad-bg': '#f2ddd3',
        'rpt-chart-grid': '#e6dcc7', 'rpt-chart-axis': '#8a7859',
        'rpt-series-1': '#3f6f9c', 'rpt-series-2': '#6f8b3a', 'rpt-series-3': '#b0651f',
        'rpt-series-4': '#7a5a9c', 'rpt-series-5': '#2e8f8a', 'rpt-series-6': '#a8476a',
    },
    'contrast': {
        'rpt-bg': '#ffffff', 'rpt-surface': '#ffffff', 'rpt-surface-2': '#f2f2f2', 'rpt-edge': '#000000',
        'rpt-ink': '#000000', 'rpt-ink-soft': '#1a1a1a', 'rpt-muted': '#3a3a3a',
        'rpt-hair': '#1c1c1c', 'rpt-hair-strong': '#000000',
        'rpt-accent': '#0033cc', 'rpt-accent-ink': '#ffffff', 'rpt-accent-soft': '#d7e0ff',
        'rpt-th-bg': '#000000', 'rpt-th-ink': '#ffffff',
        'rpt-good': '#006622', 'rpt-good-bg': '#cdeecf', 'rpt-warn': '#8a4b00', 'rpt-warn-bg': '#ffe4bf',
        'rpt-bad': '#b00018', 'rpt-bad-bg': '#ffd6da',
        'rpt-chart-grid': '#b0b0b0', 'rpt-chart-axis': '#000000',
        'rpt-series-1': '#0033cc', 'rpt-series-2': '#006622', 'rpt-series-3': '#b35900',
        'rpt-series-4': '#6a1b9a', 'rpt-series-5': '#006d75', 'rpt-series-6': '#a3005c',
    },
    'blueprint': {
        'rpt-bg': '#0f3560', 'rpt-surface': '#0d2e53', 'rpt-surface-2': '#123c66', 'rpt-edge': '#2a5f8f',
        'rpt-ink': '#eaf6ff', 'rpt-ink-soft': '#c2e0f4', 'rpt-muted': '#7fb4d6',
        'rpt-hair': '#245078', 'rpt-hair-strong': '#356a97',
        'rpt-accent': '#7fdfff', 'rpt-accent-ink': '#06263c', 'rpt-accent-soft': '#0e3255',
        'rpt-th-bg': '#12406b', 'rpt-th-ink': '#eaf6ff',
        'rpt-good': '#6be0b0', 'rpt-good-bg': '#0c3340', 'rpt-warn': '#ffd166', 'rpt-warn-bg': '#33301a',
        'rpt-bad': '#ff97a8', 'rpt-bad-bg': '#3a2030',
        'rpt-chart-grid': '#1c4a76', 'rpt-chart-axis': '#6ba0c8',
        'rpt-series-1': '#7fdfff', 'rpt-series-2': '#7ff0c0', 'rpt-series-3': '#ffd166',
        'rpt-series-4': '#c3a0ff', 'rpt-series-5': '#5fd0e0', 'rpt-series-6': '#ff9ec4',
    },
}

# Human-readable label + one-line purpose (also used by the UI picker / Help).
LABELS = {
    'light':     ('Light',         'Clean executive default — prints to paper cleanly.'),
    'dark':      ('Dark',          'Slate reading mode for screens and digital sharing.'),
    'midnight':  ('Midnight',      'Deep-navy boardroom look for on-screen presenting.'),
    'sepia':     ('Sepia',         'Warm, low-glare paper tone — easy on the eyes.'),
    'contrast':  ('High-contrast', 'Maximum legibility — accessibility & ink-safe printing.'),
    'blueprint': ('Blueprint',     'Engineering-drawing look — construction character.'),
}

DEFAULT_MODE = 'light'
MODES = tuple(THEMES.keys())            # ('light', 'dark', 'midnight', 'sepia', 'contrast', 'blueprint')
TOKENS = _TOKEN_ORDER


def normalize(mode):
    """Any unknown / falsy mode falls back to the default (light) — never raises."""
    return mode if mode in THEMES else DEFAULT_MODE


def theme_vars(mode=DEFAULT_MODE):
    """Return the {token: hex} mapping for a mode (normalized)."""
    return dict(THEMES[normalize(mode)])


def theme_style_tag(mode=DEFAULT_MODE):
    """A ``<style>`` block to drop at the END of a report's ``<head>``.

    Emits the ``:root { --rpt-*: … }`` palette for the mode, the page background,
    and the print-colour-adjust rule so dark backgrounds survive the PDF export.
    Placed last in <head> so its ``html, body { background: var(--rpt-bg) }`` also
    acts as a safety net for any rule a renderer forgot to convert to a token.
    """
    m = normalize(mode)
    body = '\n'.join(f'  --{k}: {THEMES[m][k]};' for k in _TOKEN_ORDER)
    return (
        f'<style id="rpt-theme" data-rpt-theme="{m}">\n'
        f':root {{\n{body}\n}}\n'
        '* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }\n'
        'html, body { background: var(--rpt-bg); color: var(--rpt-ink); }\n'
        '</style>'
    )


def var(token, fallback=None):
    """Convenience for building inline SVG/style strings:
    ``var('rpt-series-1')`` -> ``'var(--rpt-series-1)'``.
    """
    token = token[2:] if token.startswith('--') else token
    return f'var(--{token}, {fallback})' if fallback else f'var(--{token})'


def theme_meta():
    """List of {id, label, description} in picker order — for the UI / an API."""
    return [{'id': m, 'label': LABELS[m][0], 'description': LABELS[m][1]} for m in MODES]
