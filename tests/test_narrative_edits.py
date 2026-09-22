"""In-app prose edits merge into the document via apply_edits — only editable
sections change, and non-editable / unknown sections are left untouched."""
import os

from p6_evm.parser import parse_file
from p6_narrative.builder import build_narrative, apply_edits

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def _doc():
    return build_narrative(parse_file(FIX)).to_dict()


def test_edits_update_editable_prose():
    doc = _doc()
    edits = {'1': {'paragraphs': ['My own introduction wording.']}}
    out = apply_edits(doc, edits)
    intro = next(s for s in out['sections'] if s['number'] == '1')
    assert intro['payload']['paragraphs'] == ['My own introduction wording.']


def test_edits_ignore_non_editable_section():
    doc = _doc()
    before = next(s for s in doc['sections'] if s['number'] == '3')['payload']['rows']
    apply_edits(doc, {'3': {'paragraphs': ['hack']}})   # §3 (brief) is not editable
    after = next(s for s in doc['sections'] if s['number'] == '3')['payload']['rows']
    assert after == before


def test_edits_ignore_unknown_section_and_none():
    doc = _doc()
    apply_edits(doc, {'999': {'paragraphs': ['nope']}})   # unknown → ignored
    apply_edits(doc, None)                                 # no edits → no-op
    assert next(s for s in doc['sections'] if s['number'] == '1')['payload']['paragraphs']
