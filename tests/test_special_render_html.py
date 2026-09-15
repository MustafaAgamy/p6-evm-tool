"""Tests for the narrative-styled Studio Document shell (screen preview + Chrome PDF).

These assert that :func:`build_document` wraps the report in the Baseline-Narrative
house style — an A4-portrait double navy page frame, a repeating running
header/footer, a separate cover page and contents page, then numbered navy
sections — while the SHARED :func:`document_parts` (the Word wrapper's only source)
keeps its ``body`` / return shape so the Word path is unaffected.

Colours still come from the appearance-mode tokens except the fixed structural
navy, which is emitted as concrete hex (declared once as ``--sr-navy``), never as
``var(--sr-navy)`` — the cover/contents/section markup is shared with Word, whose
HTML engine cannot resolve custom properties.
"""
from p6_special import payloads as P
from p6_special.render_html import build_document, document_parts


def _meta():
    return {'project_name': 'Grain Bulk Terminal', 'data_date': '2026-10-19 00:00:00'}


def _letterhead():
    return {'kicker': 'Weekly Progress Report', 'prepared_by': 'Planning'}


def _rendered():
    """A small fake selection shaped like ``registry.render`` output — includes a
    payload ``table``, a ``kpi_group``, and a reused feature ``html`` section."""
    return [
        {'id': 'evm:cat', 'title': 'Planned vs Actual — by category', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'table',
         'payload': P.table(['Category', 'Planned %', 'Actual %'],
                            [['Construction', '70.0%', '45.0%'],
                             ['Engineering', '88.0%', '74.0%']])},
        {'id': 'evm:kpi', 'title': 'Overall performance', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'kpi',
         'payload': P.kpi_group([P.kpi('SPI', '0.94', tone='warn')])},
        {'id': 'audit:reuse', 'title': 'Schedule Audit — findings', 'feature': 'audit',
         'feature_title': 'Schedule Audit', 'ctype': 'html',
         'payload': {'kind': 'html', 'feature': 'audit',
                     'html': '<div class="srf-audit"><table><tr><td>reused section</td></tr></table></div>',
                     'css': '.srf-audit td{color:#334155}'}},
    ]


def test_shell_frame_page_and_wrapping_table():
    html = build_document('Weekly Report', _meta(), _rendered(), 'light', letterhead=_letterhead())
    assert 'class="sr-frame"' in html          # fixed print page frame
    assert 'class="sr-page sr-sheet' in html   # bordered paper sheets = double frame on screen
    assert 'sr-cover-sheet' in html and 'sr-toc-sheet' in html   # cover + contents each their own page
    assert 'class="sr-doc"' in html            # wrapping table (thead/tfoot repeat per page)


def test_running_header_in_thead_carries_project():
    html = build_document('Weekly Report', _meta(), _rendered(), 'light', letterhead=_letterhead())
    head = html.split('<tbody>')[0]            # everything before the body cell
    assert '<thead>' in head
    assert 'class="sr-head"' in head and 'class="sr-kicker"' in head
    assert 'Grain Bulk Terminal' in head       # project name in the running header
    # footer band in the tfoot
    assert '<tfoot>' in html and 'class="sr-foot"' in html


def test_cover_and_contents_each_break_to_own_page():
    html = build_document('Weekly Report', _meta(), _rendered(), 'light', letterhead=_letterhead())
    # cover sits OUTSIDE (before) the wrapping table so the running header skips it
    assert html.index('class="sr-cover"') < html.index('class="sr-doc"')
    # cover breaks after itself (it is a plain div — a break there is clean); the
    # sections start on a fresh page via a break-before on the sheet, NOT a break inside
    # the contents table (which would spill a phantom blank page). Contents therefore
    # ends up alone on its own page between the two.
    assert 'page-break-after:always' in html               # cover break
    assert 'sr-body-sheet' in html and 'break-before:page' in html  # sections start a new page
    assert 'Table of contents' in html
    assert 'Weekly Report' in html                          # cover report name
    assert 'EVM Report' in html                             # source-feature tag kept in contents


def test_sections_carry_page_markers_and_contents_uses_real_pages():
    """Each section embeds an invisible SECPGMARK-<i>- marker (so a two-pass PDF render
    can find its real page), and when ``page_numbers`` is supplied the contents shows
    those real pages, not the nominal ``i + 2`` guess."""
    rendered = _rendered()
    # nominal (no page_numbers): section 2 would read page 4 (i+2)
    nominal = build_document('R', _meta(), rendered, 'light')
    assert 'SECPGMARK-1-' in nominal and 'SECPGMARK-2-' in nominal
    # supplied real pages: section 2 is actually on page 9 -> must override the nominal 4
    html = build_document('R', _meta(), rendered, 'light', page_numbers={1: 3, 2: 9})
    assert '>9</td>' in html            # real page shown in the contents cell
    assert '>4</td>' not in html        # the nominal i+2 for section 2 is gone


def test_no_page_break_inside_the_contents_table():
    """The break that starts the sections must be on the sheet (sr-body-sheet /
    break-before:page), never a page-break-after inside the contents layout table —
    that spilled a phantom blank page (fixed 2026-09-15)."""
    html = build_document('R', _meta(), _rendered(), 'light')
    toc_start = html.index('Table of contents')
    toc_end = html.index('sr-body-sheet')
    assert 'page-break-after:always' not in html[toc_start:toc_end]


def test_numbered_navy_section_badge_and_order():
    html = build_document('R', _meta(), _rendered(), 'light')
    assert 'class="sr-num"' in html                         # navy number badge
    assert 'class="sr-sec-h"' in html                       # navy heading + underline
    # sections numbered in the user's pick order
    assert html.index('Planned vs Actual — by category') < html.index('Overall performance')


def test_print_block_a4_portrait_and_page_counter():
    html = build_document('R', _meta(), _rendered(), 'light')
    assert '@page' in html and 'size:A4 portrait' in html
    assert 'counter(page)' in html and 'counter(pages)' in html
    assert '--sr-navy' in html                              # structural navy declared on root


def test_navy_adapts_per_mode():
    light = build_document('R', _meta(), _rendered(), 'light').replace(' ', '')
    dark = build_document('R', _meta(), _rendered(), 'dark').replace(' ', '')
    assert '--sr-navy:#1f3b63' in light                     # navy on the light ground
    assert '--sr-navy:#4a72a8' in dark                      # lighter navy on the dark ground


def test_navy_header_zebra_scoped_to_payload_tables():
    html = build_document('R', _meta(), _rendered(), 'light')
    assert 'table.sr-dt th' in html            # payload tables get a navy header
    assert 'class="sr-dt"' in html             # the payload table carries the marker
    assert 'srf-audit' in html                 # reused section keeps its own scoped markup


def test_empty_selection_still_renders_cover():
    html = build_document('Empty Report', _meta(), [], 'light', letterhead=_letterhead())
    assert 'class="sr-cover"' in html
    assert 'Empty Report' in html
    assert 'No results selected' in html
    assert 'class="sr-frame"' in html


def test_logo_placeholders_and_supplied_logos():
    # no logos -> 'LOGO' placeholder slots
    ph = build_document('R', _meta(), _rendered(), 'light', letterhead={'kicker': 'K'})
    assert 'LOGO' in ph
    # supplied logo -> the image src is used
    lh = {'logos': {'owner': 'data:image/png;base64,AAA', 'consultant': None, 'contractor': None}}
    used = build_document('R', _meta(), _rendered(), 'light', letterhead=lh)
    assert 'data:image/png;base64,AAA' in used


def test_varfree_selection_stays_hex_only():
    """A selection with no reused ``html`` section must stay ``var()``-free in the
    PDF (so the Word wrapper, which shares ``document_parts.body``, is hex-only)."""
    r = [{'id': 'evm:kpi', 'title': 'K', 'feature': 'evm', 'feature_title': 'EVM',
          'ctype': 'kpi', 'payload': P.kpi_group([P.kpi('SPI', '0.94')])}]
    html = build_document('R', _meta(), r, 'dark')
    assert 'var(--' not in html


def test_document_parts_shape_preserved_for_word():
    parts = document_parts('R', _meta(), _rendered(), 'light', letterhead=_letterhead())
    for k in ('colors', 'css', 'head_extra', 'body', 'title'):
        assert k in parts                       # Word wrapper reads these
    # body = cover + contents + sections; the sr-doc/sr-frame SHELL is HTML/PDF only
    assert 'sr-cover' in parts['body']
    assert 'sr-doc' not in parts['body'] and 'sr-frame' not in parts['body']
    assert parts['cover'] and parts['inner']    # additive pieces the shell places


if __name__ == '__main__':   # pragma: no cover — eyeball a sample render
    import os
    out = os.path.join(os.path.dirname(__file__), '..', 'mockups', '_doc_render_check.html')
    with open(os.path.abspath(out), 'w', encoding='utf-8') as f:
        f.write(build_document('Weekly Progress & Performance Report', _meta(),
                               _rendered(), 'light', letterhead=_letterhead()))
    print('wrote', os.path.abspath(out))
