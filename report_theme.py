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
  * Word and Excel are ALWAYS light (:func:`force_light`) — the mode is a screen + PDF choice.
"""
import re

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


def _theme_block(mode):
    """The ``<style id="rpt-theme">`` palette block alone (what :func:`force_light` swaps)."""
    m = normalize(mode)
    body = '\n'.join(f'  --{k}: {THEMES[m][k]};' for k in _TOKEN_ORDER)
    return (
        f'<style id="rpt-theme" data-rpt-theme="{m}">\n'
        f':root {{\n{body}\n}}\n'
        '* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }\n'
        'html, body { background: var(--rpt-bg); color: var(--rpt-ink); }\n'
        f'{page_background_rule(m)}'
        '</style>'
    )


def theme_style_tag(mode=DEFAULT_MODE):
    """A ``<style>`` block to drop at the END of a report's ``<head>``.

    Emits the ``:root { --rpt-*: … }`` palette for the mode, the page background,
    and the print-colour-adjust rule so dark backgrounds survive the PDF export.
    Placed last in <head> so its ``html, body { background: var(--rpt-bg) }`` also
    acts as a safety net for any rule a renderer forgot to convert to a token.

    It is followed by the shared page-composition layer (:func:`pagination_tag`), so every
    renderer that themes its report also gets the ONE set of pagination rules (headings
    kept with their content, charts / KPI rows moved whole, tables with a repeated header
    and never 1–2 stranded rows) — print-only, the screen is unchanged.
    """
    return _theme_block(mode) + pagination_tag()
def page_background_rule(mode=DEFAULT_MODE):
    """``@page { background: <page colour> }`` for every mode whose page is not white.

    Chrome prints a report's ``@page`` margin area (20 mm / 11 mm ...) OUTSIDE ``html``, so
    painting only ``html, body`` left a white frame round every Dark / Midnight / Blueprint /
    Sepia PDF page. A background on the page box paints the margins too (checked with Chrome,
    Edge and the Playwright headless shell) and leaves each report's own margins and its
    ``@page`` margin-box page counters untouched. A concrete hex: the page context does not
    reliably see ``:root`` custom properties. A white page (Light, High-contrast) emits
    nothing, so light PDFs and Word / Excel (always light, :func:`force_light`) are
    unchanged."""
    bg = THEMES[normalize(mode)]['rpt-bg']
    if bg.lower() in ('#fff', '#ffffff'):
        return ''
    return f'@page {{ background: {bg}; }}\n'


# OWNER DECISION (Tool-Wide Enhancement, comment 30): the appearance mode is reflected on
# SCREEN and in the PDF only. Word (.docx / .doc) and Excel ALWAYS use the standard LIGHT
# style — the Word page is never dark — with the same structure and values as the PDF.
DOCUMENT_MODE = 'light'

_THEME_TAG_RE = re.compile(r'<style\b[^>]*\bid=["\']rpt-theme["\'][^>]*>.*?</style>',
                           re.IGNORECASE | re.DOTALL)


def force_light(html):
    """Return ``html`` re-themed to the standard light palette (for Word / Excel).

    Every report reads its colours from the ONE ``<style id="rpt-theme">`` block
    (:func:`theme_style_tag`), so swapping that block for the light one re-colours the whole
    report — tables, tiles, SVG charts — while every section, heading, table, column, value
    and number / date format stays exactly as the preview / PDF shows it. HTML without the
    block (a report that never used the tokens) is returned unchanged."""
    if not isinstance(html, str) or 'rpt-theme' not in html:
        return html
    light = _theme_block(DOCUMENT_MODE)
    return _THEME_TAG_RE.sub(lambda _m: light, html)


def var(token, fallback=None):
    """Convenience for building inline SVG/style strings:
    ``var('rpt-series-1')`` -> ``'var(--rpt-series-1)'``.
    """
    token = token[2:] if token.startswith('--') else token
    return f'var(--{token}, {fallback})' if fallback else f'var(--{token})'


def theme_meta():
    """List of {id, label, description} in picker order — for the UI / an API."""
    return [{'id': m, 'label': LABELS[m][0], 'description': LABELS[m][1]} for m in MODES]


# ══ Shared page composition / pagination (owner point 14) ═══════════════════════
# ONE set of print rules every report renderer shares (it rides along with
# theme_style_tag; renderers that do not theme — the Baseline Narrative, the UI
# printView, the chat report — include pagination_tag() themselves, and the
# one-document PDF export runs every document through with_pagination()).
#
#   * headings never end a page: every heading (h1–h6 + the renderers' heading classes)
#     is break-after:avoid, and so is a short intro paragraph right under it — the
#     heading travels with its first content block (measured: Chrome 154 honours this in
#     block, flex and grid flows once no tall "avoid" block is in the way);
#   * charts, diagrams, pictures, KPI tiles / cards, month grids: moved WHOLE;
#   * tables: the header repeats on every page (thead = table-header-group), a row never
#     splits, the first 3 and the last 3 body rows stay together — so a page never holds
#     only 1–2 rows of a table; a table that fits in about a third of a page is kept whole;
#   * the print-time composer (pagination_script) measures blocks just before printing:
#     EVERY heading — the selectors below plus any heading-LIKE line a renderer styled
#     itself (short, bold or larger than the body text) — is paired with its first content
#     block (the keep-together pair: the heading may not end the page and that block, or
#     the first block inside it when it is big, is kept whole — no DOM node is moved);
#     a block taller than a page is let to flow (never pushed whole to leave a blank
#     page), a small table / part / list is kept whole, a thead-less long table gets its
#     header row promoted so it repeats, and an over-wide table is scaled to the page
#     width instead of being cut. It runs on ``beforeprint`` only (headless Chrome fires
#     it for --print-to-pdf), so the SCREEN is never touched, and undoes itself after.
# Everything is inside @media print — the on-screen report is unchanged.

# Elements that act as headings (a heading must never be the last thing on a page).
# ``p.rescap`` only: the Narrative's <p class="rescap"> is a lead-in ABOVE a chart group,
# but its <div class="rescap"> ("Peak 7,653 m3 in June 2026.") is the caption UNDER a
# chart, the last child of the .calfig — a break-after:avoid there propagates to the
# figure, forbids every break between a run of figures, and Chrome then cuts the next
# figure itself across the page (finding NARR-PDF-5, §14 material charts).
HEADING_SELECTORS = (
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'caption', '[role="heading"]', '[data-rpt-heading]',
    'div.sec', 'div.sub', '.sub2', '.subhd', '.subblue', '.subctr', '.ct', '.calname',
    'p.rescap', '.mgrid-t', '.sr-sec-h', '.seq-glabel', '.chart-h', '.chartt', '.chartlab',
    # Critical Path Analyzer: a milestone group's title row and a lane's title row, each over
    # the lane's chain of cards (STUDIO-RICH-10)
    '.mphdr', '.lanehdr',
    '.h3title', '.h3sub', '.scope-h', '.rr-h', '.defs-h', '.rc-calhead', '.rc-assignhead',
    '.pr-h', '.flagh', '.rf-h2',
)

# Always kept whole (small by nature, or cannot be split anyway).
KEEP_WHOLE_SELECTORS = (
    'svg', 'img', 'canvas', 'figure', '.rpt-keep', '[data-export="tile"]', '.tile', '.kpi',
    '.vcard', '.lcard', '.grade-card', '.costcard', '.flagcard', '.chartcard', '.chartwrap',
    '.chart2', '.mvchart', '.calfig', '.mgrid-wrap', '.rc-calcard', '.seqflow > div',
    # one bar of a before / after bars list (label + Rev.00 bar + Rev.01 bar) and one row of
    # a diverging trade chart (name + resource id + bar) - never parted (STUDIO-RICH-4)
    '.barow', '.rc-trow',
    # a WBS branch band with its first child (and grandchild ...) - a page never ends on a
    # branch whose children start the next page (Baseline Revision WBS comparison; STUDIO-RICH-8)
    '.p6chain',
    # small cards a page break must never part (STUDIO-RICH-10): a driving-path activity /
    # milestone card (Update Analysis, Critical Path Analyzer - the milestone's title was left
    # on one page, its dates on the next), the Float Health score card and its 'how the score
    # is calculated' legend (the colour key was left alone on the next page)
    '.chain > .box', '.chain > .msbox', '.fh', '.scorelegend',
)

# Measured by the print-time composer: kept whole when small (<= FIT of a page), let to
# flow when taller than a page (their own break-inside:avoid would push them to a new
# page and leave a large blank area), left alone in between.
MEASURED_SELECTORS = (
    'table', 'tr', '[data-part]', '[data-export]', '.rpt-measure', '.tiles', '.kpis',
    '.kpi-row', '.cards', '.vcards', '.card', '.card3', '.charts', '.lcharts', '.chart',
    '.grid2', '.dt', '.codetbl', '.seqflow', '.mgrids', 'ul', 'ol', 'li', 'dl', 'pre', 'blockquote',
    '.rpt-group',
) + KEEP_WHOLE_SELECTORS

PAGINATION_FIT = 0.35        # a block up to 35 % of the page height is always kept whole
PAGINATION_KEEP_TABLE = 0.45 # a table its renderer marked ``rpt-keep`` (a short summary table
                             # under its own section heading) is kept whole up to 45 % - and so
                             # is a renderer's ``rpt-group`` (a sub-section: its heading, chart,
                             # caption and short totals table), else it breaks as usual
PAGINATION_FLOW = 0.92       # a block taller than 92 % of the page height is let to flow
PAGINATION_MIN_ROWS = 3      # a table fragment never holds fewer than 3 body rows
PAGINATION_HEAD_MAX_PX = 80  # a heading-LIKE line (styled by a renderer) is at most ~2 lines …
PAGINATION_HEAD_MAX_CHARS = 160   # … and short (a title, not a paragraph)


def _sel(items, suffix=''):
    return ',\n  '.join(s + suffix for s in items)


def pagination_css():
    """The shared print rules (a CSS string, everything inside ``@media print``).

    Deliberately free of ``:is()`` / comma-in-parentheses selectors, so the Reporting
    Studio's CSS scoper and the Word export's CSS engine read it safely."""
    n = PAGINATION_MIN_ROWS
    heads = _sel(HEADING_SELECTORS)
    intro = _sel([h + ' + p' for h in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div.sub', '.sub2', '.ct')]
                 + [h + ' + .h3sub' for h in ('h2', 'h3', '.chartt')])
    keep = _sel(KEEP_WHOLE_SELECTORS)
    return (
        '@media print {\n'
        '  /* 1 · a heading (and the short intro right under it) never ends a page */\n'
        f'  {heads} {{\n    break-after: avoid; page-break-after: avoid;'
        ' break-inside: avoid; page-break-inside: avoid;\n  }}\n'
        f'  {intro} {{ break-after: avoid; page-break-after: avoid; }}\n'
        '  figcaption, .figcaption, .figcap { break-before: avoid; page-break-before: avoid; }\n'
        # a chart's legend under its bars never opens a page alone (STUDIO-RICH-4)
        '  .rc-tdiv + .legend { break-before: avoid; page-break-before: avoid; }\n'
        # a band row titling the rows under it inside a table ('Non-working days - all listed,
        # differences highlighted') never ends a page: it keeps with its first rows (STUDIO-RICH-6)
        '  tr.rc-lband, tr.rc-lband + tr:not(:last-child),'
        ' tr.rc-lband + tr + tr:not(:last-child) { break-after: avoid; page-break-after: avoid; }\n'
        '  /* 2 · charts, diagrams, pictures, KPI tiles / cards, month grids: moved whole */\n'
        f'  {keep} {{\n    break-inside: avoid; page-break-inside: avoid;\n  }}\n'
        '  /* 3 · tables: header repeated, rows never split, never 1-2 stranded rows */\n'
        '  thead { display: table-header-group; }\n'
        '  tfoot { display: table-footer-group; }\n'
        '  tr { break-inside: avoid; page-break-inside: avoid; }\n'
        # never on a table's LAST row (resp. FIRST row): Chrome propagates a last child's
        # break-after (first child's break-before) to the table and on up to its wrappers, so
        # a 1-3 row table would forbid the break AFTER itself — a run of small tables (the
        # Narrative's activity-code pairs) then chains into one block pushed to a new page,
        # leaving the page before it 60 % blank (finding NARR-PDF-3)
        f'  tbody > tr:nth-child(-n+{n}):not(:last-child) {{ break-after: avoid; page-break-after: avoid; }}\n'
        f'  tbody > tr:nth-last-child(-n+{n - 1}):not(:first-child) {{ break-before: avoid;'
        ' page-break-before: avoid; }\n'
        '  /* composer marks (set just before printing, removed after) */\n'
        '  .rpt-fit { break-inside: avoid; page-break-inside: avoid; }\n'
        '  .rpt-head { break-after: avoid; page-break-after: avoid;'
        ' break-inside: avoid; page-break-inside: avoid; }\n'
        '  .rpt-flow { break-inside: auto !important; page-break-inside: auto !important; }\n'
        '  /* 4 · text: no 1-2 line orphans / widows */\n'
        '  p, li, dd, blockquote { orphans: 3; widows: 3; }\n'
        '  li { break-inside: avoid; page-break-inside: avoid; }\n'
        # a nested list's first item stays with its parent item's label (a tree node never
        # ends a page with its children on the next; Chrome carries a first child's
        # break-before up to the nested list, i.e. to the break right under the label)
        '  li > ul > li:first-child, li > ol > li:first-child {'
        ' break-before: avoid; page-break-before: avoid; }\n'
        '  /* 5 · screen scroll boxes print in full (no scrollbar, no clipped columns) */\n'
        '  .table-wrap, .tbl-wrap, .tblwrap, .scroll-x, .xscroll,\n'
        '  [style*="overflow-x"], [style*="overflow-y"], [style*="overflow:auto"],'
        ' [style*="overflow: auto"], [style*="overflow:scroll"], [style*="overflow: scroll"] {\n'
        '    overflow: visible !important; max-height: none !important;\n  }\n'
        '}\n'
    )


def pagination_script():
    """The print-time composer (JavaScript, no ``</script>`` inside). See the module notes."""
    measured = ','.join(MEASURED_SELECTORS).replace("'", "\\'")
    heads = ','.join(HEADING_SELECTORS).replace("'", "\\'")
    kept = ','.join(KEEP_WHOLE_SELECTORS).replace("'", "\\'")
    return (
        "(function(){\n"
        "if(window.__rptPagination)return;window.__rptPagination=1;\n"
        f"var SEL='{measured}',FIT={PAGINATION_FIT},FLOW={PAGINATION_FLOW},"
        f"KT={PAGINATION_KEEP_TABLE},MM=96/25.4;\n"
        f"var HSEL='{heads}',HMAX={PAGINATION_HEAD_MAX_PX},HTXT={PAGINATION_HEAD_MAX_CHARS};\n"
        f"var KSEL='{kept}';\n"
        "var SIZES={a3:[297,420],a4:[210,297],a5:[148,210],b5:[176,250],letter:[215.9,279.4],"
        "legal:[215.9,355.6],ledger:[279.4,431.8]};\n"
        "function mm(v,d){var m=/^(-?[\\d.]+)(mm|cm|in|px|pt)?$/.exec(String(v||'').trim());"
        "if(!m)return d;var n=parseFloat(m[1]),u=m[2]||'px';"
        "return u==='mm'?n:u==='cm'?n*10:u==='in'?n*25.4:u==='pt'?n*25.4/72:n/MM;}\n"
        "function pageRules(list,out){for(var i=0;i<list.length;i++){var r=list[i];"
        "if(r.type===6){if(!r.selectorText)out.push(r.style);}"
        "else if(r.cssRules){if(r.type===4&&/screen/i.test(r.media.mediaText)"
        "&&!/print/i.test(r.media.mediaText))continue;pageRules(r.cssRules,out);}}}\n"
        "function pageHeight(){var w=210,h=297,mt=10,mb=10,st=[];"
        "for(var s=0;s<document.styleSheets.length;s++){"
        "try{pageRules(document.styleSheets[s].cssRules||[],st);}catch(e){}}"
        "st.forEach(function(x){var size=(x.getPropertyValue('size')||'').toLowerCase().trim();"
        "if(size){var t=size.split(/\\s+/),nm=null,l=[];t.forEach(function(k){if(SIZES[k])nm=SIZES[k];"
        "else{var v=mm(k,null);if(v!=null)l.push(v);}});if(nm){w=nm[0];h=nm[1];}"
        "if(l.length===2){w=l[0];h=l[1];}else if(l.length===1){w=h=l[0];}"
        "if(t.indexOf('landscape')>=0){h=Math.min(w,h);}"
        "else if(t.indexOf('portrait')>=0){h=Math.max(w,h);}}"
        "var a=x.getPropertyValue('margin-top'),b=x.getPropertyValue('margin-bottom');"
        "if(a)mt=mm(a,mt);if(b)mb=mm(b,mb);});"
        # a report that paints its page furniture INSIDE the page area (a fixed frame /
        # logo band) declares how much of each page it takes: --rpt-page-reserve on :root
        "var rv=0;try{rv=mm(getComputedStyle(document.documentElement)"
        ".getPropertyValue('--rpt-page-reserve'),0)||0;}catch(e){}"
        "return Math.max(200,(h-mt-mb-rv)*MM);}\n"
        "var marks=[],moved=[],zoomed=[];\n"
        "function bgOf(r){if(!r)return'';var c=r.cells&&r.cells[0];"
        "return getComputedStyle(r).backgroundColor+'|'+(c?getComputedStyle(c).backgroundColor:'');}\n"
        "var SKIP={SCRIPT:1,STYLE:1,TEMPLATE:1,LINK:1,META:1,BR:1,WBR:1};\n"
        "function hOf(e){return e.getBoundingClientRect().height;}\n"
        # a document SHELL (the Reporting Studio wraps its whole body in one table cell so
        # the running header / footer repeat) is not a data table: a cell taller than a page
        # is a page container, so the rules apply inside it as in the body (STUDIO-PDF-1)
        "var FLOWPX=1e9;\n"
        "function inCell(e){var c=e.parentElement&&e.parentElement.closest('td,th');"
        "while(c){if(hOf(c)<=FLOWPX)return true;c=c.parentElement&&c.parentElement.closest('td,th');}"
        "return false;}\n"
        "function shell(t){if(t.tagName!=='TABLE'||t.rows.length>6||hOf(t)<=FLOWPX||inCell(t))return false;"
        "for(var i=0;i<t.rows.length;i++){if(hOf(t.rows[i])>FLOWPX)return true;}return false;}\n"
        "function shellReserve(){var r=0,ts=document.querySelectorAll('table');"
        "for(var i=0;i<ts.length;i++){if(!shell(ts[i]))continue;"
        "r=Math.max(r,(ts[i].tHead?hOf(ts[i].tHead):0)+(ts[i].tFoot?hOf(ts[i].tFoot):0));}return r;}\n"
        "function visible(e){return !!e&&!SKIP[e.tagName]&&hOf(e)>0;}\n"
        "function nextBlock(h){var n=h;for(var up=0;up<4&&n&&n!==document.body;up++){"
        "var s=n.nextElementSibling;while(s&&!visible(s))s=s.nextElementSibling;"
        "if(s)return s;n=n.parentElement;}return null;}\n"
        "function firstBlock(e){var c=e.firstElementChild;while(c&&!visible(c))c=c.nextElementSibling;"
        "return c;}\n"
        "function sideBySide(e){var p=e.parentElement;if(!p)return false;var cs=getComputedStyle(p);"
        "if(/flex/.test(cs.display))return !/column/.test(cs.flexDirection);"
        "if(/grid/.test(cs.display))return String(cs.gridTemplateColumns||'').trim().split(/\\s+/).length>1;"
        "return false;}\n"
        "var NOHEAD={TABLE:1,svg:1,SVG:1,PRE:1,CANVAS:1,SELECT:1,UL:1,OL:1,DL:1,FIGURE:1,IMG:1,"
        "TEXTAREA:1,BUTTON:1,SCRIPT:1,STYLE:1,TEMPLATE:1};\n"
        # a title INSIDE a small kept-whole block (a bar's bold label, a tile's caption) is not
        # paired: the block travels whole anyway, and the pair's break-after:avoid on its last
        # child is carried up by Chrome to the block itself - every bar of a 377-bar list then
        # forbade the break after it and Chrome split bars instead (STUDIO-RICH-7)
        "function inKept(n,fit){var k=n.parentElement&&n.parentElement.closest(KSEL);"
        "return !!k&&hOf(k)<=fit;}\n"
        "function headings(fit){var out=[],seen=new Set(),i,n;\n"
        "try{var hs=document.querySelectorAll(HSEL);for(i=0;i<hs.length;i++){"
        "if(!inCell(hs[i])&&!inKept(hs[i],fit)){out.push([hs[i],1]);seen.add(hs[i]);}}}catch(e){}\n"
        "var bfs=parseFloat(getComputedStyle(document.body).fontSize)||12;"
        "var tw=document.createTreeWalker(document.body,1,{acceptNode:function(x){"
        "if(x.tagName==='THEAD'||x.tagName==='TFOOT')return 2;"
        "return (NOHEAD[x.tagName]||NOHEAD[x.localName])?(shell(x)?3:2):1;}});\n"
        "while((n=tw.nextNode())){if(seen.has(n)||n.childElementCount>4)continue;var hg=hOf(n);"
        "if(!hg||hg>HMAX)continue;var tx=n.textContent;if(!tx||tx.length>HTXT*3)continue;tx=tx.trim();"
        "if(!tx||tx.length>HTXT)continue;var cs=getComputedStyle(n);"
        "if(!/^(block|flex|grid|list-item|flow-root|table-caption)$/.test(cs.display))continue;"
        "if((parseInt(cs.fontWeight,10)||400)<600&&(parseFloat(cs.fontSize)||bfs)<bfs*1.15)continue;"
        "if(sideBySide(n)||inKept(n,fit))continue;out.push([n,0]);seen.add(n);}\n"
        "return out;}\n"
        # a lead-in: a <p>, or a short text-only <div> (one or two lines of inline text - no
        # block, table, chart or picture inside): the intro line ('410 critical activities, in
        # sequence ...') or the legend pills a renderer puts between a heading and its table /
        # bars (STUDIO-RICH-3)
        "function leadIn(c){if(c.tagName==='P')return true;"
        "if(c.tagName!=='DIV'||hOf(c)>HMAX||!(c.textContent||'').trim())return false;"
        "return !c.querySelector('div,p,table,svg,img,canvas,ul,ol,dl,pre,figure,section,select,textarea');}\n"
        "function pairHeads(todo,fit){var hs=headings(fit);for(var i=0;i<hs.length;i++){"
        "var h=hs[i][0],b=nextBlock(h);if(!b)continue;var hh=hOf(h);"
        "if(!hs[i][1])todo.push([h,'rpt-head']);"
        "for(var c=b,d=0,led=0;c&&d<4;d++){var ch=hOf(c),tg=c.tagName;"
        # a short lead-in paragraph ("The major milestones ... are listed below") belongs to
        # the heading: it may not end the page either, so heading + lead-in + the start of
        # the next block (a table's first rows, a chart) travel together (STUDIO-PDF-1); up to
        # two short lead-ins (an intro line + a row of legend pills) chain on (STUDIO-RICH-3)
        "if(led<2&&(!led||tg==='DIV')&&ch<=HMAX*2&&hh+ch<=fit){var s=c.nextElementSibling;"
        "while(s&&!visible(s))s=s.nextElementSibling;"
        "if(s&&leadIn(c)){todo.push([c,'rpt-head']);hh+=ch;led++;c=s;continue;}}"
        "if(hh+ch<=fit){if(tg!=='TR'&&tg!=='TBODY'&&tg!=='THEAD')todo.push([c,'rpt-fit']);break;}"
        "if(tg==='TABLE'||tg==='P'||tg==='UL'||tg==='OL'||tg==='PRE')break;"
        "c=firstBlock(c);}}}\n"
        "function compose(){undo();var H=pageHeight();FLOWPX=H*FLOW;"
        "H=Math.max(200,H-shellReserve());var fit=H*FIT,flow=H*FLOW,todo=[],i;FLOWPX=flow;\n"
        "var els=document.querySelectorAll(SEL);\n"
        "for(i=0;i<els.length;i++){var el=els[i],r=el.getBoundingClientRect(),hg=r.height;if(!hg)continue;"
        "if(hg>flow)todo.push([el,'rpt-flow']);"
        "else if(hg<=fit&&el.tagName!=='TR')todo.push([el,'rpt-fit']);"
        # a renderer's sub-section group (heading + chart + caption + short totals table) is
        # kept whole up to KT of a page, so its table never opens a page alone (NARRFIX §13.2)
        "else if(hg<=H*KT&&el.classList.contains('rpt-group'))todo.push([el,'rpt-fit']);"
        # a content card bigger than a third of a page (title + bars + a table) continues
        # between its blocks instead of being pushed whole under a half-blank page; its chart /
        # rows keep their own rules (STUDIO-RICH-8: 'Where the money moved' left 50 % blank)
        "else if(hg<=flow&&el.classList.contains('card')&&el.children.length>1&&!inCell(el)"
        "&&!sideBySide(el))todo.push([el,'rpt-flow']);"
        "if((el.tagName==='UL'||el.tagName==='OL')&&hg>fit&&hg<=flow&&!inCell(el)){"
        "todo.push([el,'rpt-flow']);for(var a2=el.parentElement,d2=0;a2&&a2!==document.body&&d2<3;"
        "d2++,a2=a2.parentElement){if(hOf(a2)>flow)break;todo.push([a2,'rpt-flow']);}}"
        "if(el.tagName==='LI'&&hg>fit&&hg<=flow)todo.push([el,'rpt-flow']);"
        "if(el.tagName==='TABLE'){var kt=el.classList.contains('rpt-keep')&&hg<=H*KT;"
        "if(hg>fit&&!el.tHead)todo.push([el,'@head']);"
        # finding FLOAT-PDF-1: a short summary table its renderer marked rpt-keep (one row per
        # WBS, under its own heading) is kept whole up to KT of a page instead of continuing
        "if(kt)todo.push([el,'rpt-fit']);else "
        # a table too big to be "small" continues on the next page with its header repeated
        # (owner: keep a table together when it fits, otherwise continue it intentionally) —
        # never pushed whole to leave the page above it half blank. The renderer's own
        # keep-whole on the table and on its thin wrappers (label + table blocks, flex
        # pairs) is lifted; rows still never split and never strand 1-2 rows.
        "if(hg>fit&&hg<=flow&&!inCell(el)){todo.push([el,'rpt-flow']);"
        "for(var a=el.parentElement,d=0;a&&a!==document.body&&d<3;d++,a=a.parentElement){"
        "if(hOf(a)>flow)break;todo.push([a,'rpt-flow']);}}"
        "var host=el.parentElement,cs=host?getComputedStyle(host):null,"
        "avail=host?host.clientWidth-(parseFloat(cs.paddingLeft)||0)-(parseFloat(cs.paddingRight)||0):0;"
        "if(avail>80&&r.width>avail+2)todo.push([el,'@zoom',Math.max(0.55,avail/r.width)]);}}\n"
        # the "tall spine": ANY block taller than a page flows, whatever the renderer set on it
        # (only the chain of tall ancestors is walked — cheap even on long registers)
        "var stack=[document.body];while(stack.length){var pn=stack.pop();if(!pn)continue;"
        "var kids=pn.children;for(var k=0;k<kids.length;k++){var kc=kids[k],tg=kc.tagName;"
        "if(tg==='SCRIPT'||tg==='STYLE'||tg==='TEMPLATE')continue;var kh=kc.getBoundingClientRect().height;"
        "if(kh>flow){todo.push([kc,'rpt-flow']);stack.push(kc);}"
        "else if(!kh&&kc.children.length&&getComputedStyle(kc).display==='contents')stack.push(kc);}}\n"
        # heading <-> first content block (the keep-together pair, without moving any node):
        # EVERY heading — the shared selectors, plus any heading-LIKE line a renderer styled
        # itself (short, bold or larger than the body text) — may not end a page, and its
        # first content block (or, when that block is big, the block's own first block) is
        # kept whole, so the heading always travels with the start of its content.
        "pairHeads(todo,fit);\n"
        "for(i=0;i<todo.length;i++){var t=todo[i],e=t[0];\n"
        "if(t[1]==='@head'){var row=e.rows[0];if(!row||!row.cells.length)continue;var allTh=true;"
        "for(var c=0;c<row.cells.length;c++){if(row.cells[c].tagName!=='TH'){allTh=false;break;}}"
        "if(!allTh||row.parentNode.tagName!=='TBODY')continue;"
        "var body=row.parentNode,probe=e.rows[2],before=bgOf(probe);"
        "var th=e.createTHead();th.appendChild(row);"
        "if(probe&&bgOf(probe)!==before){body.insertBefore(row,body.firstChild);e.deleteTHead();continue;}"
        "moved.push([e,row,body]);}\n"
        "else if(t[1]==='@zoom'){zoomed.push([e,e.style.zoom]);e.style.zoom=String(t[2]);}\n"
        "else if(!e.classList.contains(t[1])){e.classList.add(t[1]);marks.push(t);}}}\n"
        "function undo(){var i;for(i=0;i<marks.length;i++)marks[i][0].classList.remove(marks[i][1]);"
        "for(i=moved.length-1;i>=0;i--){var m=moved[i];m[2].insertBefore(m[1],m[2].firstChild);"
        "if(m[0].tHead&&!m[0].tHead.rows.length)m[0].deleteTHead();}"
        "for(i=0;i<zoomed.length;i++)zoomed[i][0].style.zoom=zoomed[i][1]||'';"
        "marks=[];moved=[];zoomed=[];}\n"
        "window.__rptCompose=compose;window.__rptUncompose=undo;\n"
        "window.addEventListener('beforeprint',compose);window.addEventListener('afterprint',undo);\n"
        "})();"
    )


PAGINATION_STYLE_ID = 'rpt-pagination'


def word_pagination_css():
    """The same rules for Word's own HTML engine (the Office-HTML ``.doc`` exports).

    Word ignores ``@media print`` (so :func:`pagination_css` never reaches it) and honours
    only simple selectors. Measured on Word 16 (COM): ``page-break-after:avoid`` on a
    heading / ``p.class`` / ``div.class`` → *Keep with next*; ``page-break-inside:avoid``
    on a ``tr`` → the row never splits; ``<thead>`` rows → *Repeat as header row*. A
    ``tr`` rule is limited to data tables (``tbody`` / ``table.sr-dt``) so a tall layout
    row is never made unbreakable (Word would clip it)."""
    heads = []
    for s in HEADING_SELECTORS:
        if s.startswith('[') or s in ('caption', '.sr-sec-h'):
            continue
        heads.extend(['p' + s, 'div' + s] if s.startswith('.') else [s])
    heads += ['p.rpt-kwn', 'div.rpt-kwn', 'p.rpt-head', 'p.sr-sec-hp']
    return (
        f'{", ".join(heads)} {{ page-break-after: avoid; }}\n'
        'table.sr-dt tr, tbody tr { page-break-inside: avoid; }\n'
    )


def pagination_tag():
    """``<style id="rpt-pagination">`` (the rules) + ``<script id="rpt-pagination-js">``
    (the print-time composer) — drop into a report's ``<head>``."""
    return (f'<style id="{PAGINATION_STYLE_ID}">\n{pagination_css()}</style>'
            f'<script id="{PAGINATION_STYLE_ID}-js">{pagination_script()}</script>')


_HEAD_CLOSE_RE = re.compile(r'</head\s*>', re.IGNORECASE)
_HEAD_OPEN_RE = re.compile(r'<head\b[^>]*>', re.IGNORECASE)
_PAGE_SIZE_RE = re.compile(r'@page\b[^{]*\{[^}]*\bsize\s*:', re.IGNORECASE)


def with_pagination(html, page_size='A4 portrait'):
    """Return ``html`` carrying the shared pagination layer exactly once (idempotent), and
    an ``@page { size: A4 portrait }`` when the report never declared a page size (Chrome's
    default is US Letter — the PDF must paginate like the A4 Word export). The size rule is
    placed FIRST in ``<head>`` so the report's own ``@page`` margins still apply."""
    if not isinstance(html, str) or not html:
        return html
    doc = html
    if f'id="{PAGINATION_STYLE_ID}"' not in doc:
        m = _HEAD_CLOSE_RE.search(doc)
        tag = pagination_tag()
        doc = doc[:m.start()] + tag + doc[m.start():] if m else tag + doc
    if page_size and not _PAGE_SIZE_RE.search(doc):
        size_tag = f'<style id="rpt-page-size">@page {{ size: {page_size}; }}</style>'
        m = _HEAD_OPEN_RE.search(doc)
        doc = doc[:m.end()] + size_tag + doc[m.end():] if m else size_tag + doc
    return doc


def keep_together(*blocks, cls=''):
    """Wrap a heading and its first content block (or any small group) in ONE block that
    is never split across pages — for renderers that know a group belongs together."""
    extra = f' {cls}' if cls else ''
    return f'<div class="rpt-keep{extra}">' + ''.join(b for b in blocks if b) + '</div>'
