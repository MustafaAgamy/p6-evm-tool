"""Tests for the PDF-exact Word (.docx) export (:mod:`p6_special.docx_pdf`) and the
``assemble.docx`` fallback.

The preferred Word export renders the SAME HTML the PDF uses, prints it to a PDF via
Chrome, and drops each PDF page into the document as a full-page image — so Word is a
pixel-exact copy of the PDF. That path needs Chrome (unavailable in CI), so here we test
the guard (no Chrome -> raises, so the caller can fall back) and that ``assemble.docx``
falls back to the native builder and still writes a valid ``.docx`` when Chrome is absent.
"""
import zipfile

import pytest

from p6_special import registry
from tests.test_special_providers import _seed


def test_build_docx_from_pdf_requires_chrome(tmp_path):
    """Without a chrome executable the PDF-exact builder raises (never writes a broken
    file) so ``assemble.docx`` can fall back to the native builder."""
    from p6_special.docx_pdf import build_docx_from_pdf
    out = tmp_path / 'x.docx'
    with pytest.raises(Exception):
        build_docx_from_pdf(str(out), '<html><body>hi</body></html>', None)
    assert not out.exists()


def test_assemble_docx_falls_back_to_native_without_chrome(temp_db, xml_path):
    """``assemble.docx`` with ``chrome=None`` skips the PDF-exact path and uses the
    native python-docx builder, still producing a valid .docx package."""
    from p6_special import assemble
    registry.clear_providers()
    pid = _seed(xml_path)
    out = tmp_path = None
    import tempfile, os
    fd, out = tempfile.mkstemp(suffix='.docx'); os.close(fd)
    try:
        assemble.docx(out, pid, ['evm:planned_pct', 'evm:actual_pct'],
                      report_name='Fallback', meta={}, chrome=None, mode='light')
        assert zipfile.is_zipfile(out)
        with zipfile.ZipFile(out) as z:
            assert 'word/document.xml' in z.namelist()
    finally:
        try:
            os.remove(out)
        except OSError:
            pass
