"""Tests for the Special Report renderer + Word export (PDF/Word parity)."""
from p6_special import payloads as P
from p6_special.render_html import build_document, document_parts
from p6_special.word_export import build_word_document

MODES = ('light', 'dark', 'midnight', 'sepia', 'contrast', 'blueprint')


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
