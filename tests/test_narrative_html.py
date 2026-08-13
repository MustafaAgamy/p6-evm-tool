"""The narrative renders to HTML without error and carries its content."""
import os

from p6_calendar.audit import calendar_audit
from p6_evm.parser import parse_file
from p6_narrative.builder import build_narrative
from p6_narrative.html import page_html, render_narrative_html

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def test_render_contains_key_content():
    data = parse_file(FIX)
    doc = build_narrative(data, calendar_audit(data)).to_dict()
    h = render_narrative_html(doc)
    assert 'Test Project' in h
    assert 'Introduction' in h and 'Cash flow' in h
    assert 'class="bn-doc"' in h


def test_page_html_is_standalone_document():
    data = parse_file(FIX)
    doc = build_narrative(data).to_dict()
    p = page_html(doc)
    assert p.startswith('<!doctype html>') and '</html>' in p
