"""Tests for the two-pass PDF page-number detector (:mod:`p6_special.pdf_render`).

The full two-pass render needs Chrome (unavailable in CI), so here we unit-test the
PyMuPDF-based marker detector on a synthetic PDF built in-process, and the graceful
empty-result behaviour. The end-to-end two-pass (correct contents numbers) is verified
manually against real Chrome.
"""
import pytest

pymupdf = pytest.importorskip('pymupdf')

from p6_special.pdf_render import _detect_section_pages


def _pdf_with_markers(path):
    """A 3-page PDF: section markers 1 & 2 on page 1, marker 3 on page 3 (page 2 has
    none) — mimics several short sections sharing a page and a later one further on."""
    doc = pymupdf.open()
    p1 = doc.new_page(); p1.insert_text((72, 72), 'SECPGMARK-1- intro SECPGMARK-2-')
    doc.new_page()                                   # page 2 — no marker
    p3 = doc.new_page(); p3.insert_text((72, 72), 'SECPGMARK-3- later')
    doc.save(str(path)); doc.close()


def test_detects_section_pages(tmp_path):
    pdf = tmp_path / 'marked.pdf'
    _pdf_with_markers(pdf)
    pages = _detect_section_pages(str(pdf))
    assert pages == {1: 1, 2: 1, 3: 3}      # 1-based printed pages; page 2 has none


def test_detect_returns_empty_on_unmarked_pdf(tmp_path):
    doc = pymupdf.open(); doc.new_page().insert_text((72, 72), 'no markers here');
    pdf = tmp_path / 'plain.pdf'; doc.save(str(pdf)); doc.close()
    assert _detect_section_pages(str(pdf)) == {}
