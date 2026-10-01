"""Owner comment 28 — dark-mode PDFs must not print a white frame round the page.

``report_theme.theme_style_tag`` paints the page box (``@page { background }``) for every
appearance mode whose page is not white, so the margins match the page. That only works for
a report that USES the shared theme. This guard walks the source: every module that sets up
a printed page (``@page``) must either take the shared theme, or be listed below as a
document that is always light by design (with the reason). A new report that adds its own
``@page`` without the theme fails here instead of shipping a white-framed dark PDF.

Measured on the real tool (GBT schedule, Chrome): Schedule Health summary + float, P6
Calendar Audit, Bad Weather, Earned Value, the Reporting Studio document and the Report
Contents picker's one-document export — every page of all 42 PDFs (6 modes x 7 reports) has
the mode's page colour right to the sheet edge; Word exported from a dark mode is white.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Takes the shared theme one of these ways (each ends in report_theme.theme_style_tag).
THEMED_MARKERS = ('theme_style_tag', 'page_background_rule', 'with_pagination')

# Always light by design — the page is white in every appearance mode, so there is no
# dark page for a white margin to frame.
ALWAYS_LIGHT = {
    'p6_narrative/html.py': 'Baseline Narrative: fixed company report template (white A4 sheets, zero page margin)',
    'p6_export/css.py': 'reads a report\'s @page for the Word / Excel page setup; emits no page of its own',
    'p6_export/pdf.py': 'prints the HTML it is given; the theme travels inside that HTML',
    'p6_export/svg_raster.py': 'rasterises one SVG for Word / Excel (always light)',
    'p6_export/to_docx.py': 'Word export: always the standard light style (owner decision, comment 30)',
    'p6_special/reuse.py': 'drops a reused feature\'s @page; the Reporting Studio document sets the themed one',
    'p6_special/word_export.py': 'Word export: always the standard light style (owner decision, comment 30)',
    'report_theme.py': 'the shared theme itself',
}

SKIP_DIRS = {'tests', 'mockups', 'node_modules', '.git', 'build', 'dist', '__pycache__', '.venv', 'venv'}


def _page_modules():
    out = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            if not f.endswith('.py'):
                continue
            path = os.path.join(root, f)
            try:
                src = open(path, encoding='utf-8').read()
            except (OSError, UnicodeDecodeError):
                continue
            if '@page' in src:
                out.append((os.path.relpath(path, REPO).replace(os.sep, '/'), src))
    return out


def test_there_are_page_reports_to_guard():
    names = [n for n, _ in _page_modules()]
    assert 'p6_evm/evm_report.py' in names and 'p6_special/render_html.py' in names


def test_every_printed_report_takes_the_shared_theme_or_is_declared_light():
    missing = [name for name, src in _page_modules()
               if name not in ALWAYS_LIGHT and not any(m in src for m in THEMED_MARKERS)]
    assert not missing, (
        'these reports set up a printed page (@page) without the shared theme, so a dark '
        'appearance mode would print a white frame round every page: '
        + ', '.join(missing)
        + ' — add report_theme.theme_style_tag(theme) to the report\'s <head>, or list the '
          'module in ALWAYS_LIGHT with the reason it is always light')


def test_the_always_light_list_is_current():
    """An entry whose module no longer has an @page (or no longer exists) is removed, so the
    list never hides a report that later becomes themed-but-broken."""
    names = {n for n, _ in _page_modules()}
    stale = sorted(n for n in ALWAYS_LIGHT if n not in names)
    assert not stale, f'remove from ALWAYS_LIGHT (no @page there any more): {stale}'


def test_no_report_repaints_the_page_box_white():
    """A report-level ``@page { background: #fff }`` would defeat the theme's page colour."""
    import re
    bad = []
    for name, src in _page_modules():
        if name == 'report_theme.py':
            continue
        for m in re.finditer(r'@page[^{}]*\{[^{}]*background[^{}]*\}', src):
            bad.append(f'{name}: {m.group(0)[:70]}')
    assert not bad, f'a report paints its own page box: {bad}'
