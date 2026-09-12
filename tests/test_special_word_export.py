"""Tests for the Reporting Studio Word (.doc) export — the Baseline-Narrative
house style translated to Office-Word HTML.

The Word export is an Office-HTML ``.doc`` (HTML wrapped so Word opens it). These
tests assert the narrative chrome the wrapper adds around the shared
``render_html.document_parts`` content: an A4-portrait ``@page`` with a navy double
page border, a running header + page-number footer (``mso-element:header`` /
``mso-element:footer`` referenced from the ``@page``, with a live ``PAGE`` field),
navy section badges, navy-fill zebra tables, and separate cover / contents pages —
plus that every reused-feature ``var()`` / ``color-mix`` is resolved to concrete hex.
"""
import report_theme
from p6_special import payloads as P
from p6_special.word_export import build_word_document, _resolve_theme_colors

MODES = ('light', 'dark', 'midnight', 'sepia', 'contrast', 'blueprint')
NAVY = '#1f3b63'


def _meta():
    return {'project_name': 'Grain Bulk Terminal', 'data_date': '2026-10-19'}


def _letterhead():
    return {'kicker': 'Weekly Report', 'company': 'Acme Marine JV',
            'logos': {'owner': None, 'consultant': None, 'contractor': None},
            'prepared_by': 'Planning Dept'}


def _rendered():
    """A small report: one KPI group, one data table, and one REUSED feature-report
    ``html`` section whose CSS + markup carry ``var()`` (must be resolved for Word)."""
    return [
        {'id': 'evm:planned_pct', 'title': 'Planned % — overall', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'kpi',
         'payload': P.kpi_group([P.kpi('Planned %', '61.4%', tone='accent')])},
        {'id': 'evm:category_table', 'title': 'By category', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'table',
         'payload': P.table(['Category', 'Planned %'], [['Construction', '58.0%']])},
        {'id': 'audit:float', 'title': 'Float health', 'feature': 'audit',
         'feature_title': 'Schedule Audit', 'ctype': 'html',
         'payload': {'kind': 'html', 'css': '.srf-audit .fh{color:var(--rpt-ink)}',
                     'html': '<div class="srf-audit fh" '
                             'style="color:var(--rpt-accent);'
                             'background:color-mix(in srgb, var(--rpt-warn) 40%, transparent)">'
                             'Reused audit section</div>'}},
    ]


def _doc(mode='light'):
    return build_word_document('October Board Report', _meta(), _rendered(), mode,
                               letterhead=_letterhead())


# ── Office wrapper + shared content ──────────────────────────────────────────
def test_office_html_wrapper_present():
    doc = _doc()
    assert 'urn:schemas-microsoft-com:office:word' in doc
    assert 'WordSection1' in doc
    assert '<w:WordDocument>' in doc
    # shared content from document_parts still flows through unchanged
    assert 'October Board Report' in doc          # cover title
    assert 'Grain Bulk Terminal' in doc           # project meta
    assert '61.4%' in doc and 'Construction' in doc


# ── A4 portrait page + navy double border ────────────────────────────────────
def test_page_is_a4_portrait_with_navy_border():
    doc = _doc()
    assert '@page WordSection1' in doc
    assert '595.3pt 841.9pt' in doc               # A4 portrait
    # navy page border (double requested; CSS `border` is a solid-capable fallback)
    assert f'border: 1.5pt double {NAVY}' in doc
    assert f'mso-border-alt: double {NAVY} 1.5pt' in doc
    assert 'mso-page-border-surround-header: no' in doc


# ── running header + page-number footer ──────────────────────────────────────
def test_header_and_footer_directives_present():
    doc = _doc()
    # @page references (both spellings emitted; Word honours whichever it supports)
    assert 'mso-header: h1' in doc and 'mso-footer: f1' in doc
    assert 'mso-header-data: h1' in doc and 'mso-footer-data: f1' in doc
    # the element divs the refs point at
    assert 'mso-element:header' in doc and 'id="h1"' in doc
    assert 'mso-element:footer' in doc and 'id="f1"' in doc


def test_footer_has_live_page_field():
    doc = _doc()
    assert 'mso-field-code:PAGE' in doc            # live Word PAGE field
    assert 'Page <span' in doc                     # 'Page N' footer text


def test_header_shows_project_name():
    doc = _doc()
    # project name appears in the header band (as well as on the cover)
    assert doc.count('Grain Bulk Terminal') >= 2
    assert 'Weekly Report' in doc                  # kicker from letterhead


# ── navy chrome: badges, table headers, cover / contents pages ───────────────
def test_navy_present_in_chrome_and_tables():
    doc = _doc()
    assert NAVY in doc                             # fixed structural navy
    # navy-fill data-table header (parity with the on-screen shell CSS)
    assert f'table.sr-dt th {{ background:{NAVY} !important; color:#ffffff !important;' in doc


def test_cover_and_contents_are_separate_pages():
    doc = _doc()
    assert 'Table of contents' in doc
    # cover + contents each break to their own page
    assert 'page-break-after:always' in doc
    # the break sits between the cover title and the contents heading
    cover_i = doc.index('October Board Report')
    break_i = doc.index('page-break-after:always')
    toc_i = doc.index('Table of contents')
    assert cover_i < break_i < toc_i


# ── theme resolution: no var()/color-mix left for Word ───────────────────────
def test_reused_section_vars_resolved_to_hex():
    doc = _doc()
    assert 'var(--' not in doc                     # Word can't resolve custom props
    assert 'color-mix' not in doc                  # nor color-mix()
    # the reused section's accent resolved to the light-mode concrete hex
    assert report_theme.theme_vars('light')['rpt-accent'].lower() in doc.lower()


def test_all_six_modes_resolve_to_concrete_hex():
    for mode in MODES:
        doc = _doc(mode)
        assert 'var(--' not in doc and 'color-mix' not in doc
        assert '@page WordSection1' in doc
        assert 'mso-element:header' in doc and 'mso-element:footer' in doc
        assert 'mso-field-code:PAGE' in doc


def test_resolve_theme_colors_unit():
    """The color-resolution helper is preserved and still resolves var()+color-mix."""
    accent = report_theme.theme_vars('midnight')['rpt-accent']
    out = _resolve_theme_colors('a{color:var(--rpt-accent)}', 'midnight')
    assert 'var(' not in out and accent.lower() in out.lower()
    mixed = _resolve_theme_colors(
        'b{background:color-mix(in srgb, var(--rpt-warn) 45%, transparent)}', 'midnight')
    assert 'var(' not in mixed and 'color-mix' not in mixed and '#' in mixed
