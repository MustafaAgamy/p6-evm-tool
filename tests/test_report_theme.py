"""The shared report-appearance theming layer — the one source of report colour.

Pins the contract every renderer + the UI picker rely on: the six modes, a complete
and identical token set per mode, valid hex values, the injectable <style> tag, the
print-colour-adjust rule (so dark PDFs keep their backgrounds), and safe fallback.
"""
import re

import pytest

import report_theme as rt


EXPECTED_MODES = ('light', 'dark', 'midnight', 'sepia', 'contrast', 'blueprint')
_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


def test_six_modes_in_order():
    assert rt.MODES == EXPECTED_MODES
    assert rt.DEFAULT_MODE == 'light'
    assert set(rt.THEMES) == set(EXPECTED_MODES)


def test_every_mode_defines_every_token():
    for mode in EXPECTED_MODES:
        keys = set(rt.THEMES[mode])
        assert keys == set(rt.TOKENS), f'{mode} token set differs from canonical'
        # order-complete too
        assert len(rt.THEMES[mode]) == len(rt.TOKENS)


def test_all_values_are_valid_hex():
    for mode in EXPECTED_MODES:
        for token, value in rt.THEMES[mode].items():
            assert _HEX.match(value), f'{mode}.{token} = {value!r} is not a #rrggbb hex'


def test_token_vocabulary_covers_needed_roles():
    # A renderer converting hardcoded hex needs these role tokens to exist.
    needed = {
        'rpt-bg', 'rpt-surface', 'rpt-edge', 'rpt-ink', 'rpt-ink-soft', 'rpt-muted',
        'rpt-hair', 'rpt-hair-strong', 'rpt-accent', 'rpt-accent-ink', 'rpt-th-bg',
        'rpt-good', 'rpt-warn', 'rpt-bad', 'rpt-chart-grid', 'rpt-chart-axis',
        'rpt-series-1', 'rpt-series-2', 'rpt-series-3',
    }
    assert needed <= set(rt.TOKENS)


def test_style_tag_contains_root_and_all_vars():
    css = rt.theme_style_tag('dark')
    assert css.startswith('<style id="rpt-theme"')
    assert 'data-rpt-theme="dark"' in css
    assert ':root' in css
    for token in rt.TOKENS:
        assert f'--{token}:' in css, f'{token} missing from emitted CSS'
    # dark accent value present
    assert rt.THEMES['dark']['rpt-accent'] in css


def test_style_tag_has_print_color_adjust_and_bg():
    """Without print-color-adjust, Chrome --print-to-pdf drops dark backgrounds."""
    css = rt.theme_style_tag('midnight')
    assert 'print-color-adjust: exact' in css
    assert '-webkit-print-color-adjust: exact' in css
    assert 'background: var(--rpt-bg)' in css


def test_light_and_dark_differ():
    assert rt.theme_style_tag('light') != rt.theme_style_tag('dark')
    assert rt.THEMES['light']['rpt-bg'] != rt.THEMES['dark']['rpt-bg']


@pytest.mark.parametrize('bad', ['', None, 'neon', 'DARK', 'lite', 123, 'light ', 'Light'])
def test_unknown_mode_falls_back_to_light(bad):
    assert rt.normalize(bad) == 'light'
    # style tag never raises and yields the light palette
    assert rt.theme_style_tag(bad) == rt.theme_style_tag('light')


def test_theme_vars_is_a_copy():
    v = rt.theme_vars('dark')
    v['rpt-bg'] = '#000000'
    assert rt.THEMES['dark']['rpt-bg'] != '#000000'  # mutating the copy must not leak


def test_var_helper():
    assert rt.var('rpt-series-1') == 'var(--rpt-series-1)'
    assert rt.var('--rpt-ink') == 'var(--rpt-ink)'
    assert rt.var('rpt-bg', '#fff') == 'var(--rpt-bg, #fff)'


def test_theme_meta_shape():
    meta = rt.theme_meta()
    assert [m['id'] for m in meta] == list(EXPECTED_MODES)
    for m in meta:
        assert m['label'] and m['description']
