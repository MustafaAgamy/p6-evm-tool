"""The narrative writes a valid, editable .docx with real content."""
import os

from docx import Document

from p6_calendar.audit import calendar_audit
from p6_evm.parser import parse_file
from p6_narrative.builder import build_narrative
from p6_narrative.docx_writer import write_docx

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def test_writes_openable_docx_with_headings_and_tables(tmp_path):
    data = parse_file(FIX)
    doc = build_narrative(data, calendar_audit(data)).to_dict()
    out = os.path.join(str(tmp_path), 'narrative.docx')
    write_docx(doc, out)
    assert os.path.exists(out) and os.path.getsize(out) > 0

    reopened = Document(out)
    text = '\n'.join(p.text for p in reopened.paragraphs)
    assert 'Test Project' in text
    assert any('Introduction' in p.text for p in reopened.paragraphs)
    assert any('Cash flow' in p.text for p in reopened.paragraphs)
    # native editable tables (project brief, cost, cash flow, calendars, …)
    assert len(reopened.tables) >= 4
