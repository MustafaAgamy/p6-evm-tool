"""SLICE B — NATIVE, EDITABLE WBS org-chart + Sequence process (p6_narrative.docx_native).

``add_org_chart`` and ``add_process`` inject REAL, click-to-edit Word content — a
``wpg:wgp`` group of ``wps:wsp`` text-box + line-connector shapes — NOT a flattened
PNG picture. The tests build a Document, add both diagrams, save + reopen without
error, then unzip the package and assert the body carries the native group/shape
OOXML (``wpg:``/``wps:``) and that NO new image part was added for these diagrams.

Everything must be None-safe: an empty tree / empty step list returns None and
never raises, so a diagram failure can never crash the export.
"""
import os
import zipfile

from docx import Document

from p6_narrative import docx_native as dn


# ── helpers ───────────────────────────────────────────────────────────────────
def _save_reopen(document, tmp_path, name='diagram.docx'):
    out = os.path.join(str(tmp_path), name)
    document.save(out)
    Document(out)          # must reopen without raising (well-formed package)
    return out


def _names(path):
    with zipfile.ZipFile(path) as z:
        return z.namelist()


def _read(path, member):
    with zipfile.ZipFile(path) as z:
        return z.read(member).decode('utf-8')


_TREE = {
    'name': 'Project',
    'children': [
        {'name': 'Civil', 'children': [
            {'name': 'Foundations'},
            {'name': 'Structures'},
        ]},
        {'name': 'Mechanical', 'children': [
            {'name': 'Piping'},
        ]},
    ],
}


# ── the org-chart + process produce native group/shape XML, no image ──────────
def test_org_chart_and_process_are_native_shapes(tmp_path):
    doc = Document()
    doc.add_heading('Native diagrams', 0)
    a = dn.add_org_chart(doc, _TREE)
    b = dn.add_process(doc, ['A', 'B', 'C'])
    assert a is not None and b is not None

    out = _save_reopen(doc, tmp_path)
    names = _names(out)

    # NO rasterised image part was added for these diagrams
    media = [n for n in names if n.startswith('word/media/')]
    assert media == [], media

    body = _read(out, 'word/document.xml')
    # native, editable DrawingML group + shapes (SmartArt-style, not a picture)
    assert 'wpg:wgp' in body
    assert 'wps:wsp' in body
    assert 'wps:txbx' in body               # real text boxes the user can edit
    assert '<a:blip' not in body            # NOT a picture blip
    # the wordprocessingGroup extension namespace is wired in
    assert 'wordprocessingGroup' in body


# ── org-chart: a box per node, blue per-depth palette, line connectors ────────
def test_org_chart_boxes_palette_and_connectors(tmp_path):
    doc = Document()
    dn.add_org_chart(doc, _TREE)
    out = _save_reopen(doc, tmp_path)
    body = _read(out, 'word/document.xml')
    # 5 nodes → at least 5 rounded-rectangle boxes
    assert body.count('prst="roundRect"') >= 5
    # per-depth blue palette (root #1F4E79, level-1 #2E75B6, level-2 #4472C4)
    assert '1F4E79' in body
    assert '2E75B6' in body
    assert '4472C4' in body
    # elbow connectors drawn as native line shapes
    assert 'prst="line"' in body
    # node labels are real editable text
    assert 'Foundations' in body
    assert 'Mechanical' in body


# ── process: left-to-right chevrons (blue), first is a home-plate ─────────────
def test_process_chevrons(tmp_path):
    doc = Document()
    dn.add_process(doc, ['Design', 'Procure', 'Construct', 'Commission'])
    out = _save_reopen(doc, tmp_path)
    body = _read(out, 'word/document.xml')
    # first step is a home-plate pentagon, the rest are chevrons
    assert 'prst="homePlate"' in body
    assert body.count('prst="chevron"') >= 3
    # blue gradient palette from docx_charts.sequence_flow_svg
    assert '1F4E79' in body
    assert '2E75B6' in body
    # step labels are editable text
    assert 'Commission' in body


# ── multiple diagrams in one doc get distinct, non-clashing shape ids ─────────
def test_multiple_diagrams_distinct_ids(tmp_path):
    import re
    doc = Document()
    dn.add_org_chart(doc, _TREE)
    dn.add_process(doc, ['A', 'B', 'C'])
    dn.add_org_chart(doc, {'name': 'Second', 'children': [{'name': 'X'}]})
    out = _save_reopen(doc, tmp_path)
    body = _read(out, 'word/document.xml')
    # top-level drawing frames must have unique ids (Word rejects duplicates)
    docpr_ids = re.findall(r'<wp:docPr id="(\d+)"', body)
    assert len(docpr_ids) == len(set(docpr_ids)), docpr_ids


# ── None-safety: bad / empty inputs return None and never raise ────────────────
def test_none_safe_org_chart():
    doc = Document()
    assert dn.add_org_chart(None, _TREE) is None
    assert dn.add_org_chart(doc, None) is None
    assert dn.add_org_chart(doc, {}) is None
    assert dn.add_org_chart(doc, {'name': None, 'children': []}) is None
    # a single lonely root (name only, no children) still renders one box
    assert dn.add_org_chart(doc, {'name': 'Solo'}) is not None


def test_none_safe_process():
    doc = Document()
    assert dn.add_process(None, ['A']) is None
    assert dn.add_process(doc, None) is None
    assert dn.add_process(doc, []) is None
    assert dn.add_process(doc, [None, '', '   ']) is None
    # non-string steps are coerced, not crashed on
    assert dn.add_process(doc, [1, 2, 3]) is not None


# ── a diagram adds exactly one inline drawing paragraph ────────────────────────
def test_diagram_adds_inline_drawing(tmp_path):
    doc = Document()
    before = len(doc.paragraphs)
    dn.add_org_chart(doc, _TREE)
    dn.add_process(doc, ['A', 'B'])
    assert len(doc.paragraphs) == before + 2
    out = _save_reopen(doc, tmp_path)
    body = _read(out, 'word/document.xml')
    assert body.count('<w:drawing') == 2
    assert 'graphicData' in body
