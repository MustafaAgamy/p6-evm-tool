"""Tests for the Special Report renderer + Word export (PDF/Word parity)."""
import report_theme
from p6_special import payloads as P
from p6_special.render_html import build_document, document_parts, _feature_css_head
from p6_special.word_export import build_word_document, _resolve_theme_colors

MODES = ('light', 'dark', 'midnight', 'sepia', 'contrast', 'blueprint')


def test_feature_css_dedup_keeps_distinct_blocks():
    """One feature can ship different stylesheets for different sections (audit
    Float vs OOS). _feature_css_head must keep every DISTINCT block (deduping only
    identical ones), or the later section renders unstyled."""
    rendered = [
        {'payload': {'kind': 'html', 'feature': 'audit', 'css': '.srf-audit .fh{color:#f00}'}},
        {'payload': {'kind': 'html', 'feature': 'audit', 'css': '.srf-audit .dash{color:#00f}'}},
        {'payload': {'kind': 'html', 'feature': 'audit', 'css': '.srf-audit .fh{color:#f00}'}},
    ]
    head = _feature_css_head(rendered, 'light')
    assert '.fh{color:#f00}' in head      # first distinct block kept
    assert '.dash{color:#00f}' in head    # second distinct block ALSO kept (was dropped before)
    assert head.count('.fh{color:#f00}') == 1   # identical block emitted once


def test_word_resolves_theme_vars_and_color_mix_to_hex():
    """Word ignores var()/color-mix, so the Word path must resolve reused-section
    colours to concrete hex for every appearance mode."""
    accent = report_theme.theme_vars('midnight')['rpt-accent']
    out = _resolve_theme_colors('a{color:var(--rpt-accent)}', 'midnight')
    assert 'var(' not in out and accent.lower() in out.lower()
    mixed = _resolve_theme_colors(
        'b{background:color-mix(in srgb, var(--rpt-warn) 45%, transparent)}', 'midnight')
    assert 'var(' not in mixed and 'color-mix' not in mixed and '#' in mixed


def _rendered():
    return [
        {'id': 'evm:planned_pct', 'title': 'Planned % — overall', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'kpi',
         'payload': P.kpi_group([P.kpi('Planned %', '61.4%', tone='accent')])},
        {'id': 'evm:category_table', 'title': 'By category', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'table',
         'payload': P.table(['Category', 'Planned %'], [['Construction', '58.0%']])},
    ]


def _meta():
    return {'project_name': 'Grain Bulk Terminal', 'data_date': '2026-10-19'}


def test_document_has_cover_toc_and_sections():
    html = build_document('October Board Report', _meta(), _rendered(), 'light')
    assert 'October Board Report' in html          # cover name
    assert 'Table of contents' in html
    assert 'Grain Bulk Terminal' in html           # cover meta
    assert 'Planned % — overall' in html           # section 1 title
    assert '61.4%' in html
    assert 'Construction' in html


def test_sections_numbered_in_order():
    html = build_document('R', _meta(), _rendered(), 'light')
    # section 1 appears before section 2's title
    assert html.index('Planned % — overall') < html.index('By category')


def test_no_css_variables_in_output_pdf_and_word():
    r = _rendered()
    pdf = build_document('R', _meta(), r, 'dark')
    doc = build_word_document('R', _meta(), r, 'dark')
    # Word ignores CSS var(); renderer must emit concrete hex only, in BOTH.
    assert 'var(--' not in pdf
    assert 'var(--' not in doc


def test_word_has_office_wrapper_and_same_content():
    r = _rendered()
    doc = build_word_document('October Board Report', _meta(), r, 'light')
    assert 'urn:schemas-microsoft-com:office:word' in doc
    assert 'WordSection1' in doc
    assert 'October Board Report' in doc
    assert '61.4%' in doc                          # same content as PDF
    assert 'Construction' in doc


def test_all_six_modes_render_concrete_hex():
    for mode in MODES:
        doc = build_word_document('R', _meta(), _rendered(), mode)
        pdf = build_document('R', _meta(), _rendered(), mode)
        assert 'var(--' not in doc and 'var(--' not in pdf
        assert '#' in doc                          # concrete colours present


def test_empty_selection_message():
    html = build_document('R', _meta(), [], 'light')
    assert 'No results selected' in html


def test_no_data_payload_renders_friendly_line():
    r = [{'id': 'x', 'title': 'X', 'feature': 'x', 'feature_title': 'X', 'ctype': 'kpi',
          'payload': {'kind': 'no_data'}}]
    html = build_document('R', _meta(), r, 'light')
    assert 'No data available' in html
