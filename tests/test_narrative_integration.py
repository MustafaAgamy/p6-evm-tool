"""The full chain the server handler runs: parse → build_report → render. Locks the
pieces the unit tests don't cover together (page_html + the on-screen fragment)."""
import os

from p6_evm.parser import parse_file
from p6_narrative.html import page_html, render_narrative_html
from p6_narrative.report import build_report
from tests.test_narrative_report import SECTIONS

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def test_handler_chain_parse_build_render():
    data = parse_file(FIX)
    doc = build_report(data).to_dict()

    # page_html is a full standalone document (Chrome → PDF source)
    page = page_html(doc)
    assert page.lstrip().lower().startswith('<!doctype html>')
    assert '</html>' in page

    # the on-screen fragment carries the cover, the contents list and every approved section
    frag = render_narrative_html(doc)
    assert 'BASELINE' in frag and 'NARRATIVE REPORT' in frag
    assert 'Test Project' in frag and 'Table of Contents' in frag
    for _kind, title in SECTIONS:
        assert title.replace('&', '&amp;') in frag, title
    # one page-section per report section, keyed by its number (the Reporting Studio slices on it)
    for n in range(1, len(SECTIONS) + 1):
        assert 'data-section="%d"' % n in frag, n


def test_report_sections_are_the_full_approved_set():
    doc = build_report(parse_file(FIX))
    assert [(s.kind, s.title) for s in doc.sections] == SECTIONS
    # contiguously numbered 1..N
    assert [s.number for s in doc.sections] == [str(i) for i in range(1, len(doc.sections) + 1)]
