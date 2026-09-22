"""Project setup (parties + logos + layout) flows into the document and the Word file."""
import os

from docx import Document

from p6_evm.parser import parse_file
from p6_narrative.builder import build_narrative
from p6_narrative.docx_writer import write_docx

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')
# a valid 1x1 transparent PNG as a data URL
PNG = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0'
       'lEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==')


def _doc(setup):
    return build_narrative(parse_file(FIX), setup=setup).to_dict()


def test_setup_adds_parties_layout_and_logos():
    doc = _doc({'owner': 'ACME', 'consultant': 'Premier', 'contractor': 'RME',
                'owner_logo': PNG, 'layout': PNG})
    sec2 = next(s for s in doc['sections'] if s['number'] == '2')
    assert sec2['kind'] == 'image' and sec2['payload']['image'] == PNG
    sec3 = next(s for s in doc['sections'] if s['number'] == '3')
    labels = [r['k'] for r in sec3['payload']['rows']]
    assert labels[:3] == ['Owner', 'Consultant', 'Contractor']
    assert doc['meta']['logos']['owner'] == PNG


def test_no_setup_still_builds_without_parties():
    doc = _doc(None)
    sec3 = next(s for s in doc['sections'] if s['number'] == '3')
    assert 'Owner' not in [r['k'] for r in sec3['payload']['rows']]
    assert 'logos' not in doc['meta']


def test_docx_writes_with_logos_and_layout(tmp_path):
    doc = _doc({'owner': 'ACME', 'owner_logo': PNG, 'consultant_logo': PNG,
                'contractor_logo': PNG, 'layout': PNG})
    out = os.path.join(str(tmp_path), 'n.docx')
    write_docx(doc, out)
    assert os.path.exists(out) and os.path.getsize(out) > 0
    Document(out)   # opens cleanly with the header image + layout picture
