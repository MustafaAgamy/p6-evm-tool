"""The Word renderers are wired to NATIVE charts/diagrams, not pictures.

These tests drive the ``docx_writer`` / ``docx_calendar`` section renderers of the approved
report (§6 contract value, §8 calendar timeline, §9 WBS, §11 sequence) and assert the produced
.docx carries REAL Word objects — native charts (``word/charts/chartN.xml``) and grouped
shapes (``wpg:wgp`` / ``wps:wsp``) — with NO rasterised image part (``word/media/*``,
``<a:blip``), and WITHOUT any Chrome (native objects never need one). So every figure stays
editable in Word.

Every renderer must also stay None-safe: when a drawing cannot be built it falls back to an
editable table / text line and the export never raises.
"""
import os
import zipfile

from docx import Document

from p6_narrative import docx_calendar, docx_native
from p6_narrative import docx_writer as W
from p6_narrative.report import build_report
from tests import intel_fixtures as F


# ── helpers ───────────────────────────────────────────────────────────────────
def _save_reopen(document, tmp_path, name='out.docx'):
    out = os.path.join(str(tmp_path), name)
    document.save(out)
    Document(out)          # must reopen without raising
    return out


def _names(path):
    with zipfile.ZipFile(path) as z:
        return z.namelist()


def _read(path, member):
    with zipfile.ZipFile(path) as z:
        return z.read(member).decode('utf-8')


def _chart_xml(path):
    """Concatenated text of every word/charts/chartN.xml part."""
    return '\n'.join(_read(path, n) for n in _names(path)
                     if n.startswith('word/charts/chart') and n.endswith('.xml'))


def _no_raster(path):
    """No rasterised picture anywhere: no media parts, no blip in the body."""
    names = _names(path)
    assert [n for n in names if n.startswith('word/media/')] == [], names
    assert '<a:blip' not in _read(path, 'word/document.xml')


def _text(path):
    return '\n'.join(p.text for p in Document(path).paragraphs)


_VALUE = {'total': 100.0, 'unit': 'EGP', 'rows': [
    {'name': 'Civil', 'amount': 56.0, 'pct': 56.0},
    {'name': 'Mechanical', 'amount': 28.0, 'pct': 28.0},
    {'name': 'Electrical', 'amount': 16.0, 'pct': 16.0},
]}

# §9 payload: the overview (project → main WBS) and one branch as Level-2 columns
# [name, [[Level-3 name, [Level-4 names]], …]]
_WBS = {'overview': {'name': 'Project', 'children': [{'name': 'Civil'}, {'name': 'Mechanical'}]},
        'branches': [{'name': 'Civil', 'depth': 4,
                      'columns': [['Foundations', [['Piling', ['Bored piles']]]],
                                  ['Structures', []]]}]}

# §11 payload: one single-code sequence and one grouped (per building) sequence
_SEQ = {'analyses': [
    {'codes': ['Type of Work'], 'kind': 'single', 'title': 'General sequence — Type of Work',
     'narrative': 'Read from the baseline logic.',
     'steps': [{'name': 'Excavation', 'count': 4}, {'name': 'Foundation', 'count': 4},
               {'name': 'Columns', 'count': 4}, {'name': 'Slab', 'count': 4}]},
    {'codes': ['Building', 'Work'], 'kind': 'grouped', 'title': 'Sequence by building',
     'narrative': 'Each building follows its own order.',
     'groups': [{'label': 'Building 01', 'count': 2,
                 'steps': [{'name': 'Raft', 'count': 2}, {'name': 'Walls', 'count': 2}]}]},
]}

_CAL = {'header': {'calendar_count': 1, 'activity_count': 12},
        'dashboard': {'total_calendar_days': 59, 'total_working_days': 42, 'total_nonworking_days': 17,
                      'total_holidays': 1, 'avg_working_days_per_month': 21.0,
                      'avg_working_hours_per_day': 8.0},
        'calendars': [{'name': '5 Days/Week', 'activity_count': 12,
                       'months': ['Jan 2025', 'Feb 2025'], 'net_working_days': [22, 20],
                       'nonworking_days': [9, 8], 'working_days': 42,
                       'monthly': [{'label': 'Jan 2025', 'working_days': 22, 'nonworking_days': 9},
                                   {'label': 'Feb 2025', 'working_days': 20, 'nonworking_days': 8}]}],
        'holidays': [{'date': '08 Jan 2025', 'description': 'Holiday'}],
        'hours_profiles': [{'name': '5 Days/Week', 'hours': '08:00–16:00', 'sub': '5 days/week'}]}


# ── §6 value: native GROUPED-SHAPE doughnut (not a c:chart) + the legend table beneath ──
def test_value_is_native_doughnut_group_plus_table(tmp_path):
    # the contract-value doughnut is an editable wpg:wgp group of real Word shapes (annular
    # custGeom sectors + text boxes + leader polylines + a centre-hole ellipse) — NOT a
    # c:doughnutChart and never a picture — with the amount legend table beneath.
    doc = Document()
    W._render_value_bars(doc, _VALUE, 6, None)
    out = _save_reopen(doc, tmp_path)
    body = _read(out, 'word/document.xml')
    assert 'wpg:wgp' in body and 'wps:wsp' in body, 'value donut is not a grouped shape'
    assert 'a:custGeom' in body, 'doughnut slices are not custom-geometry annular sectors'
    assert '<c:doughnutChart' not in body, 'the donut must no longer be a native c:chart'
    assert _chart_xml(out).count('c:doughnutChart') == 0
    # the amount legend/table is kept beneath the doughnut (PDF shows both)
    assert len(Document(out).tables) >= 1
    _no_raster(out)


# ── §9 wbs_tree: native tree drawings (overview + one per branch), no image ───────────
def test_wbs_tree_is_native_drawings_overview_plus_branch(tmp_path):
    doc = Document()
    W._render_wbs_tree(doc, _WBS, 9, None)
    out = _save_reopen(doc, tmp_path)
    body = _read(out, 'word/document.xml')
    assert 'wpg:wgp' in body and 'wps:wsp' in body
    assert body.count('<w:drawing') >= 2, 'expected the overview tree + the branch tree'
    for name in ('Project', 'Civil', 'Mechanical', 'Foundations', 'Piling', 'Bored piles', 'Structures'):
        assert name in body, name
    text = _text(out)
    assert '9.1  WBS OVERVIEW' in text and '9.2  CIVIL — BREAKDOWN' in text       # sub-headings print in capitals
    _no_raster(out)


# ── §11 sequence: native chevron flows (single + per building), never a picture ───────
def test_sequence_is_native_chevron_flows(tmp_path):
    doc = Document()
    W._render_sequence(doc, _SEQ, 11, None)
    out = _save_reopen(doc, tmp_path)
    body = _read(out, 'word/document.xml')
    assert 'wpg:wgp' in body and 'prst="chevron"' in body
    assert body.count('<w:drawing') >= 2, 'one flow for the single sequence + one for the building'
    for step in ('Excavation', 'Foundation', 'Columns', 'Slab', 'Raft', 'Walls'):
        assert step in body, step
    text = _text(out)
    assert '11.1  GENERAL SEQUENCE — TYPE OF WORK' in text
    assert '11.2  SEQUENCE BY BUILDING' in text and 'Building 01 (×2)' in text   # identical buildings shown once
    assert 'dependency' in text                                   # read from the logic, said so
    _no_raster(out)


# ── §8 calendar timeline: a native Word column chart per calendar, no image ───────────
def test_calendar_timeline_is_a_native_chart(tmp_path):
    doc = Document()
    docx_calendar.render_calendar(doc, _CAL, None, 8)
    out = _save_reopen(doc, tmp_path)
    xml = _chart_xml(out)
    assert '<c:barChart>' in xml
    assert 'Jan 2025' in xml and 'Feb 2025' in xml                # the months are chart categories
    assert '22' in xml and '9' in xml                             # working + non-working values
    _no_raster(out)


# ── the WHOLE report: every figure native, the file reopens ───────────────────────────
def test_the_whole_word_report_has_no_picture_of_a_chart(tmp_path):
    doc = build_report(F.matrix_epc(4)).to_dict()
    out = os.path.join(str(tmp_path), 'report.docx')
    W.write_docx(doc, out, chrome=None)                           # no browser needed
    Document(out)
    body = _read(out, 'word/document.xml')
    assert 'wpg:wgp' in body, 'no native drawing in the report'
    # the only pictures allowed are the cover / header logos the planner supplies (none here)
    assert [n for n in _names(out) if n.startswith('word/media/')] == []
    text = _text(out)
    for title in ('Project Overview', 'Work Breakdown Structure', 'Sequence of Work', 'Activity IDs'):
        assert title in text, title


# ══ fallbacks: a degenerate payload falls back to an editable table / text line ════════
def test_value_fallback_table_on_bad_rows(tmp_path):
    # rows with no usable amount → the doughnut cannot be drawn, the value legend still lands
    doc = Document()
    bad = {'total': None, 'rows': [{'name': 'X', 'amount': None, 'pct': None}]}
    W._render_value_bars(doc, bad, 6, None)                       # must not raise
    out = _save_reopen(doc, tmp_path)
    assert len(Document(out).tables) >= 1
    empty = Document()
    W._render_value_bars(empty, {'total': None, 'rows': []}, 6, None)
    assert 'No cost-loading information' in '\n'.join(p.text for p in empty.paragraphs)


def test_wbs_tree_fallback_table(tmp_path, monkeypatch):
    # if the native tree cannot be built, the same WBS lands as an indented editable table
    monkeypatch.setattr(docx_native, 'add_wbs_tree', lambda *a, **k: None)
    doc = Document()
    W._render_wbs_tree(doc, _WBS, 9, None)
    out = _save_reopen(doc, tmp_path, 'fallback.docx')
    cells = [c.text for t in Document(out).tables for r in t.rows for c in r.cells]
    for name in ('Project', 'Civil', 'Foundations', 'Piling', 'Bored piles'):
        assert name in cells, name
    _no_raster(out)


def test_sequence_fallback_arrow_line(tmp_path, monkeypatch):
    monkeypatch.setattr(docx_native, 'add_chevron_flow', lambda *a, **k: None)
    doc = Document()
    W._render_sequence(doc, _SEQ, 11, None)
    out = _save_reopen(doc, tmp_path, 'seqfb.docx')
    text = _text(out)
    assert 'Excavation → Foundation → Columns → Slab' in text     # arrow-line fallback carries the steps
    assert 'Raft → Walls' in text


def test_empty_payloads_say_so_and_never_raise(tmp_path):
    doc = Document()
    W._render_sequence(doc, {'analyses': []}, 11, None)
    W._render_wbs_tree(doc, {}, 9, None)
    docx_calendar.render_calendar(doc, {}, None, 8)
    out = _save_reopen(doc, tmp_path, 'empty.docx')
    text = _text(out)
    assert 'No sequence-of-work analysis could be derived' in text
    assert 'No work breakdown structure is defined' in text
