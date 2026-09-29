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


# ── owner point 14 (NARR-PDF-4, Word twin): a tall vertical tree continues in parts ──────
def _tall_tree(subs=5, leaves=6):
    return {'name': 'Phase I Inputs Required From Client (a deliberately long label)', 'level': 1,
            'children': [{'name': 'Sub-branch %d with a long label' % k, 'level': 2,
                          'children': [{'name': 'Leaf %d-%02d with a long label' % (k, i), 'level': 3,
                                        'children': []} for i in range(1, leaves + 1)]}
                         for k in range(1, subs + 1)]}


def _drawings(doc):
    body = doc.element.body
    return [d for d in body.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing')]


def test_tall_vertical_wbs_tree_is_drawn_in_parts_of_about_a_third_of_a_page():
    from p6_export.docx_pagination import FIT, _body_height_pt
    doc = Document()
    assert dn.add_wbs_tree(doc, [_tall_tree()]) is not None
    parts = _drawings(doc)
    assert len(parts) >= 2                                        # 36 rows: several parts
    limit_pt = _body_height_pt(doc) * FIT
    heights = [int(d.find('.//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent')
                   .get('cy')) / 12700.0 for d in parts]
    assert all(h <= limit_pt + 1 for h in heights), (heights, limit_pt)
    # every box drawn exactly once across the parts; parts sit edge to edge (no spacing)
    text = ' '.join(t.text or '' for d in parts
                    for t in d.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
    for k in range(1, 6):
        assert text.count('Sub-branch %d with' % k) == 1
        assert text.count('Leaf %d-06 with' % k) == 1
    for p in doc.paragraphs[-len(parts):]:
        assert p.paragraph_format.space_before == 0 and p.paragraph_format.space_after == 0


def test_tree_parts_never_part_a_label_from_its_first_child_or_strand_a_tail():
    seq = []

    def dfs(n):
        seq.append({'node': n, 'level': n['level'], 'row': len(seq)})
        for c in n['children']:
            dfs(c)
    dfs(_tall_tree(4, 5))                                        # 25 rows
    for max_rows in (6, 7, 8, 10, 11):
        parts = dn._tree_parts(seq, max_rows)
        assert parts[0][0] == 0 and parts[-1][1] == len(seq)
        assert all(a[1] == b[0] for a, b in zip(parts, parts[1:]))
        for r0, r1 in parts:
            assert r1 - r0 >= 3, (max_rows, parts)
            if r1 < len(seq):                                   # the part's last row is no label
                assert not seq[r1 - 1]['node']['children'], (max_rows, parts)
    # a tree that fits is one part — drawn exactly as before
    assert dn._tree_parts(seq[:8], 10) == [(0, 8)]
    doc = Document()
    dn.add_wbs_tree(doc, [_tall_tree(1, 4)])
    assert len(_drawings(doc)) == 1
