"""PDF-2: in the dark appearance modes the PDF page MARGINS printed white.

Chrome prints a report's ``@page`` margin area outside ``html``; the theme painted only
``html, body``, so Dark / Midnight / Blueprint / Sepia PDFs had a white frame round every
page. ``report_theme.theme_style_tag`` now also paints the page box
(``@page { background: <page colour> }``) for every mode whose page is not white.

The static tests pin the rule; the Chrome test prints a real multi-page PDF with a report's
own ``@page`` margins and an ``@page`` margin-box page counter and checks the corner pixel
of every page (skipped when no working Chrome / Edge / headless shell or no pymupdf).
"""
import os

import pytest

import report_theme as rt

WHITE_PAGE_MODES = [m for m in rt.MODES if rt.THEMES[m]['rpt-bg'].lower() == '#ffffff']
COLOURED_PAGE_MODES = [m for m in rt.MODES if m not in WHITE_PAGE_MODES]


def test_dark_modes_are_covered():
    assert {'dark', 'midnight', 'blueprint', 'sepia'} <= set(COLOURED_PAGE_MODES)
    assert 'light' in WHITE_PAGE_MODES


@pytest.mark.parametrize('mode', COLOURED_PAGE_MODES)
def test_coloured_mode_paints_the_page_box(mode):
    tag = rt.theme_style_tag(mode)
    bg = rt.THEMES[mode]['rpt-bg']
    assert f'@page {{ background: {bg}; }}' in tag
    assert 'var(' not in rt.page_background_rule(mode)       # concrete hex only
    # inside the one theme block, so force_light() swaps it out with the rest
    assert tag.rstrip().endswith('</style>') and tag.index('@page') < tag.index('</style>')


@pytest.mark.parametrize('mode', WHITE_PAGE_MODES)
def test_white_page_modes_are_unchanged(mode):
    assert '@page' not in rt.theme_style_tag(mode)
    assert rt.page_background_rule(mode) == ''


def test_word_and_excel_stay_light_with_no_page_background():
    html = ('<html><head><style>@page { margin: 20mm 14mm; }</style>'
            + rt.theme_style_tag('midnight') + '</head><body>x</body></html>')
    light = rt.force_light(html)
    assert rt.THEMES['midnight']['rpt-bg'] not in light
    assert '@page { background' not in light
    assert '@page { margin: 20mm 14mm; }' in light          # the report's own page setup kept


def test_word_page_setup_ignores_the_background():
    """p6_export reads the report's @page for Word/Excel page setup: margins unchanged."""
    lxml_html = pytest.importorskip('lxml.html')
    from p6_export import css as pcss
    html = ('<html><head><style>@page { size: A4 landscape; margin: 11mm; }</style>'
            + rt.theme_style_tag('dark') + '</head><body>x</body></html>')
    setup = pcss.page_setup(pcss.stylesheet_for(lxml_html.fromstring(html)))
    assert setup['orientation'] == 'landscape'
    assert tuple(round(v, 1) for v in setup['margins_mm']) == (11.0, 11.0, 11.0, 11.0)


def _chrome():
    try:
        from p6_export import pdf
        return pdf, pdf.find_working_chrome()
    except Exception:
        return None, None


@pytest.mark.parametrize('mode,margin', [('dark', '20mm 14mm'), ('midnight', '11mm')])
def test_real_pdf_margins_are_themed(tmp_path, mode, margin):
    pymupdf = pytest.importorskip('pymupdf')
    pdf, chrome = _chrome()
    if not chrome:
        pytest.skip('no working Chrome / Edge / headless shell on this machine')
    rows = ''.join(f'<p>Row {i} — activity text that fills the page</p>' for i in range(150))
    html = ('<!doctype html><html><head><meta charset="utf-8"><style>'
            f'@page {{ size: A4 landscape; margin: {margin}; }}'
            '@page { @bottom-right { content: "Page " counter(page) " of " counter(pages); } }'
            '</style>' + rt.theme_style_tag(mode) + '</head><body>' + rows + '</body></html>')
    out = os.path.join(str(tmp_path), f'{mode}.pdf')
    pdf.html_to_pdf(html, out, chrome=chrome)
    bg = rt.THEMES[mode]['rpt-bg'].lstrip('#')
    want = tuple(int(bg[i:i + 2], 16) for i in (0, 2, 4))
    doc = pymupdf.open(out)
    try:
        assert doc.page_count >= 2
        for page in doc:
            pix = page.get_pixmap(dpi=36)
            for x, y in ((1, 1), (pix.width - 2, 1), (1, pix.height - 2),
                         (pix.width - 2, pix.height - 2), (pix.width // 2, pix.height // 2)):
                got = pix.pixel(x, y)
                assert max(abs(a - b) for a, b in zip(got, want)) <= 3, (mode, page.number, x, y, got)
        # the report's @page margin-box counter still prints
        assert f'Page 2 of {doc.page_count}' in doc[1].get_text()
    finally:
        doc.close()
