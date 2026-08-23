"""Guard the whole-app appearance system: every one of the six modes must define the FULL
set of app CSS tokens. A missing token would silently fall back to another mode's value and
paint one element in the wrong palette — the classic theming bug. Also checks the toolbar
control replaced the old sun/moon toggle and no `.light`-class rules linger.
"""
import os
import re

CSS = open(os.path.join(os.path.dirname(__file__), '..', 'ui', 'style.css'), encoding='utf-8').read()

MODES = ('light', 'dark', 'midnight', 'sepia', 'contrast', 'blueprint')
TOKENS = (
    '--bg', '--sidebar-bg', '--sidebar-ink', '--sidebar-ink-dim', '--card-bg', '--border', '--hair',
    '--text', '--ink-soft', '--muted', '--accent', '--accent-dark', '--accent-soft',
    '--danger', '--danger-bg', '--success', '--success-bg', '--warning', '--warning-bg', '--row-hover',
    '--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5', '--chart-6', '--chart-grid', '--chart-axis',
)


def _block(mode):
    m = re.search(r'\[data-appearance="%s"\][^{]*\{([^}]*)\}' % mode, CSS)
    return m.group(1) if m else None


def test_every_mode_block_exists():
    for mode in MODES:
        assert _block(mode) is not None, f'no :root[data-appearance="{mode}"] palette block'


def test_every_mode_defines_every_token():
    for mode in MODES:
        body = _block(mode)
        missing = [t for t in TOKENS if not re.search(re.escape(t) + r'\s*:', body)]
        assert not missing, f'{mode} palette is missing tokens: {missing}'


def test_no_duplicate_token_in_a_mode():
    for mode in MODES:
        body = _block(mode)
        for t in TOKENS:
            n = len(re.findall(re.escape(t) + r'\s*:', body))
            assert n == 1, f'{mode} defines {t} {n} times (expected once)'


def test_token_values_are_valid_css_colours():
    hexre = re.compile(r'^#[0-9a-fA-F]{3,8}$')
    for mode in MODES:
        body = _block(mode)
        for t in TOKENS:
            val = re.search(re.escape(t) + r'\s*:\s*([^;]+);', body).group(1).strip()
            ok = hexre.match(val) or val.startswith('rgb') or val.startswith('hsl')
            assert ok, f'{mode} {t} = {val!r} is not a colour'


def test_old_light_class_system_fully_migrated():
    # The `.light` class was replaced by the data-appearance attribute; none should remain.
    assert '.light' not in CSS, 'a legacy .light-class rule still exists in style.css'


def test_dead_toggle_css_removed():
    assert '.theme-toggle' not in CSS and '.icon-moon' not in CSS, 'dead sun/moon toggle CSS remains'
