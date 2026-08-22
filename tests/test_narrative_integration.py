"""The full chain the server handler runs: parse → build_report → render. Locks the
pieces the unit tests don't cover together (page_html + the on-screen fragment)."""
import os

from p6_evm.parser import parse_file
from p6_narrative.html import page_html, render_narrative_html
from p6_narrative.report import build_report

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def test_handler_chain_parse_build_render():
    data = parse_file(FIX)
    doc = build_report(data).to_dict()

    # page_html is a full standalone document (Chrome → PDF source)
    page = page_html(doc)
    assert page.lstrip().lower().startswith('<!doctype html>')
    assert '</html>' in page

    # the on-screen fragment carries the cover and every v5 section
    frag = render_narrative_html(doc)
    assert 'Baseline Schedule' in frag
    for title in ('Project Overview', 'Major Milestones', 'Work Breakdown Structure',
                  'Sequence of Work', 'Interfaces'):
        assert title in frag


def test_report_sections_are_the_locked_five():
    doc = build_report(parse_file(FIX))
    assert [s.number for s in doc.sections] == ['1', '2', '3', '4', '5']
