"""The v5 Narrative Report renders to HTML without error and carries its content."""
import os

from p6_evm.parser import parse_file
from p6_narrative.html import page_html, render_narrative_html
from p6_narrative.report import build_report

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def test_render_contains_the_v5_sections():
    doc = build_report(parse_file(FIX)).to_dict()
    h = render_narrative_html(doc)
    assert 'Test Project' in h
    for title in ('Project Overview', 'Major Milestones', 'Work Breakdown Structure',
                  'Sequence of Work', 'Interfaces'):
        assert title in h
    assert 'Baseline Schedule' in h            # cover kicker


def test_page_html_is_standalone_document():
    doc = build_report(parse_file(FIX)).to_dict()
    p = page_html(doc)
    assert p.lstrip().lower().startswith('<!doctype html>') and '</html>' in p
