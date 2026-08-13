"""The full chain the server handler runs: parse → code catalog → build → render.
Locks the pieces the unit tests don't cover together (code_catalog + page_html)."""
import os

from p6_calendar.audit import calendar_audit
from p6_evm.parser import parse_file
from p6_narrative.builder import build_narrative
from p6_narrative.codes import read_code_catalog
from p6_narrative.html import page_html, render_narrative_html

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def test_handler_chain_parse_catalog_build_render():
    data = parse_file(FIX)
    catalog = read_code_catalog(FIX)           # separate reader (handler uses it)
    doc = build_narrative(data, calendar_audit(data), catalog).to_dict()

    # page_html is a full standalone document (Chrome → PDF source)
    page = page_html(doc)
    assert page.lstrip().lower().startswith('<!doctype html>')
    assert '</body></html>' in page

    # the on-screen fragment carries the cover + provenance chips + a sequence chart
    frag = render_narrative_html(doc)
    assert 'bn-cover' in frag
    assert 'bn-chip' in frag
    assert 'bn-chart' in frag


def test_code_catalog_when_present_drives_the_codes_section():
    data = parse_file(FIX)
    catalog = read_code_catalog(FIX)
    doc = build_narrative(data, None, catalog)
    codes = next(s for s in doc.sections if s.number == '7')
    # every catalog dimension becomes a table (or the graceful fallback ran)
    assert 'tables' in codes.payload
