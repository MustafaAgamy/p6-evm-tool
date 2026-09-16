"""Two-pass PDF rendering for the Special Report so the contents page shows REAL
page numbers.

An HTML→Chrome PDF cannot know, at build time, which printed page each section lands
on — Chrome does not implement CSS ``target-counter`` — so a single pass can only print
a nominal guess (which drifts whenever a section spans more or fewer than one page). This
renders the document twice: pass 1 with no numbers, then PyMuPDF finds each section's real
page from an invisible ``SECPGMARK-<i>-`` marker :func:`render_html.render_section` embeds,
and pass 2 rebuilds the contents with those real numbers. The layout is identical between
passes (a page number is the same width whether it reads 3 or 4), so the detected pages
stay valid.

Used by the PDF export (server ``/api/special/pdf``) and, via the same PDF, by the
PDF-exact Word export (:mod:`p6_special.docx_pdf`), so both show the same correct numbers.
If PyMuPDF is unavailable or no markers are found, pass 1 stands (nominal numbers) — the
export never fails.
"""
import os
import re
import subprocess
import tempfile

_MARKER_RE = re.compile(r'SECPGMARK-(\d+)-')


def chrome_pdf(html, chrome, pdf_path, timeout=180):
    """Print ``html`` to ``pdf_path`` with the canonical Special-Report Chrome flags
    (``--headless --print-to-pdf --no-pdf-header-footer``)."""
    html_path = None
    try:
        fd, html_path = tempfile.mkstemp(suffix='.html')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(html)
        subprocess.run(
            [chrome, '--headless', '--disable-gpu', '--no-sandbox',
             f'--print-to-pdf={pdf_path}', '--no-pdf-header-footer',
             f'file:///{html_path.replace(os.sep, "/")}'],
            check=True, capture_output=True, timeout=timeout)
    finally:
        if html_path and os.path.exists(html_path):
            try:
                os.remove(html_path)
            except OSError:
                pass


def _detect_section_pages(pdf_path):
    """Return ``{section_index: printed_page_no}`` (both 1-based) by finding each
    section's invisible marker in the rendered PDF's text layer. ``{}`` if PyMuPDF is
    unavailable or no markers are found (whitespace is stripped first, since Chrome may
    split a run across line boxes)."""
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
    except ImportError:
        return {}
    pages = {}
    doc = fitz.open(pdf_path)
    try:
        for pno in range(doc.page_count):
            text = re.sub(r'\s+', '', doc[pno].get_text())
            for m in _MARKER_RE.findall(text):
                idx = int(m)
                if idx not in pages:            # first page the section appears on
                    pages[idx] = pno + 1
    finally:
        doc.close()
    return pages


def render_document_pdf(pdf_path, build_html, chrome, timeout=180):
    """Render the document to ``pdf_path`` with correct contents-page numbers.

    ``build_html(page_numbers)`` must return the full document HTML — called with
    ``None`` for pass 1 and with the detected ``{index: page}`` map for pass 2. Returns
    ``pdf_path``. Falls back to the pass-1 PDF (nominal numbers) if no markers resolve.
    """
    chrome_pdf(build_html(None), chrome, pdf_path, timeout)
    pages = _detect_section_pages(pdf_path)
    if not pages:
        return pdf_path
    chrome_pdf(build_html(pages), chrome, pdf_path, timeout)
    return pdf_path
