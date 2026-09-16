"""The v5 Narrative Report writes a valid, editable .docx with real content, driven
through the SLICE-B/C/D furniture + chart + calendar modules."""
import os
import re

import pytest
from docx import Document

from p6_evm.parser import parse_file
from p6_narrative.docx_writer import write_docx
from p6_narrative.report import build_report
from tests import intel_fixtures as F

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def _working_chrome_or_none():
    """Return a Chrome path only if it can ACTUALLY rasterise a chart on this machine,
    else None. A path alone is not enough — CI has no browser, and some local
    Chromium builds fail to launch — so we probe a trivial render and skip unless a
    real PNG comes back."""
    try:
        from server import _find_chrome
        chrome = _find_chrome()
    except Exception:
        return None
    from p6_narrative import docx_charts
    probe = docx_charts.chart_png('sequence_flow', {'sequence': ['A', 'B']}, chrome)
    return chrome if probe else None


def test_writes_openable_docx_from_minimal(tmp_path):
    doc = build_report(parse_file(FIX)).to_dict()
    out = os.path.join(str(tmp_path), 'narrative.docx')
    write_docx(doc, out)
    assert os.path.exists(out) and os.path.getsize(out) > 0
    text = '\n'.join(p.text for p in Document(out).paragraphs)
    assert 'Test Project' in text
    assert 'Project Overview' in text


def test_writes_editable_tables_on_a_rich_schedule(tmp_path):
    # a matrix-EPC schedule has real scope worlds -> the breakdown renders as a Word table
    doc = build_report(F.matrix_epc(4)).to_dict()
    out = os.path.join(str(tmp_path), 'rich.docx')
    write_docx(doc, out)
    reopened = Document(out)
    paras = [p.text for p in reopened.paragraphs]
    assert any('Work Breakdown Structure' in t for t in paras)
    assert any('Scope of Work' in t for t in paras)
    # native editable table(s), not flattened images
    assert len(reopened.tables) >= 1


def test_cover_toc_and_numbered_headings_present(tmp_path):
    """The furniture lands: the cover carries the project name, a REAL native Word TOC
    field is written (so Word fills in the true page number of every section on open —
    the static PAGEREF approach resolved to 'page 1' on the planner's Word), the
    'Table of Contents' title is NOT itself a Heading (so the field never self-lists),
    and each section heading is Heading 1 and numbered like '1)'."""
    from docx.oxml.ns import qn
    doc = build_report(F.matrix_epc(4)).to_dict()
    project = doc['meta'].get('project_name')
    assert project
    out = os.path.join(str(tmp_path), 'furniture.docx')
    write_docx(doc, out)
    reopened = Document(out)

    # cover: the project name appears in the body text
    text = '\n'.join(p.text for p in reopened.paragraphs)
    assert project in text

    # a native, updatable Word TOC field is present, and Word is told to refresh fields on open
    assert 'Table of Contents' in text
    instr = [t.text for t in reopened.element.iter(qn('w:instrText')) if t.text and 'TOC' in t.text]
    assert instr, 'expected a native Word TOC field (w:instrText containing "TOC")'
    uf = reopened.settings.element.findall(qn('w:updateFields'))
    assert any(e.get(qn('w:val')) == 'true' for e in uf), 'updateFields must be true'

    # the 'Table of Contents' title must NOT be a Heading (else the TOC lists itself)
    toc_titles = [p for p in reopened.paragraphs if (p.text or '').strip() == 'Table of Contents']
    assert toc_titles and all(not (p.style and p.style.name.startswith('Heading'))
                              for p in toc_titles)

    # every section title lands as a Heading-1 body heading, numbered like '1)'
    titles = [s.get('title') for s in doc['sections'] if s]
    h1 = [p.text for p in reopened.paragraphs if p.style and p.style.name == 'Heading 1']
    assert len(h1) == len(titles), 'each section should be one Heading-1 (all 10 in the TOC)'
    for t in titles:
        assert any(t in row for row in h1), 'section %r missing as a Heading-1' % t
    assert any(re.match(r'^\d+\)\s', row) for row in h1), \
        'expected a numbered section heading like "1) ..."'


def test_calendar_section_renders_tables(tmp_path):
    """Section 5 (calendars) comes through the delegated docx_calendar renderer and
    lands native tables; the export does not raise."""
    doc = build_report(F.matrix_epc(4)).to_dict()
    has_calendar = any(
        (s.get('payload') or {}).get('view') == 'calendars' for s in doc['sections'])
    out = os.path.join(str(tmp_path), 'calendars.docx')
    write_docx(doc, out)                       # must not raise
    reopened = Document(out)
    if has_calendar:
        # the calendar section emits at least one styled table
        assert len(reopened.tables) >= 1
        text = '\n'.join(p.text for p in reopened.paragraphs)
        assert any('alendar' in p.text for p in reopened.paragraphs) or 'Calendar' in text


def test_chrome_present_embeds_images(tmp_path):
    """When a real Chrome is available, chart kinds embed images (InlineShapes) — the
    orchestrator actually uses the passed chrome. Skipped in CI (no browser)."""
    chrome = _working_chrome_or_none()
    if not chrome:
        pytest.skip('no working Chrome/Chromium available on this machine')
    doc = build_report(F.matrix_epc(4)).to_dict()
    out = os.path.join(str(tmp_path), 'charts.docx')
    write_docx(doc, out, chrome=chrome)
    reopened = Document(out)
    # at least one rasterised chart embedded as an inline image (WBS smartart / seq /
    # donut / costbars / timeline / cashflow)
    assert len(reopened.inline_shapes) >= 1
