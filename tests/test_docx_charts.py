"""SLICE C — the Word chart SVG builders + PNG dispatch.

The builders are pure string generation (verifiable offline); the PNG dispatch
no-ops without Chrome, so the whole module is testable on any machine.
"""
from p6_narrative import docx_charts as dc


# ── sample payloads ───────────────────────────────────────────────────────────
VALUE = {'total': 1234567, 'rows': [
    {'name': 'Civil', 'cost': 700000, 'pct': 56},
    {'name': 'Mechanical', 'cost': 350000, 'pct': 28},
    {'name': 'Electrical', 'cost': 184567, 'pct': 16},
]}
TIMELINE = {'items': [
    {'label': 'NTP', 'date': '2026-01-01', 'milestone': True},
    {'label': 'Foundations', 'date': '2026-04-01'},
    {'label': 'Handover', 'date': '2026-12-01', 'milestone': True},
]}
COSTBARS = {'rows': [
    {'name': 'Civil', 'pct': 56},
    {'name': 'Mechanical', 'pct': 28},
    {'name': 'Electrical', 'pct': 16},
]}
WBS = {'name': 'Project', 'children': [
    {'name': 'Area 1', 'children': [{'name': 'Civil'}, {'name': 'Steel'}]},
    {'name': 'Area 2', 'children': [{'name': 'Mech'}]},
]}
FRONT = {'sequence': ['Excavate', 'Pour', 'Erect', 'Fit-out']}
FRONT2 = {'sequence': ['Excavate', 'Pour']}


# ── chart_png no-ops without Chrome (every kind) ──────────────────────────────
def test_chart_png_none_without_chrome():
    cases = {
        'donut': VALUE, 'value': VALUE, 'timeline': TIMELINE,
        'costbars': COSTBARS, 'wbs_smartart': WBS, 'sequence_flow': FRONT,
    }
    for kind, data in cases.items():
        assert dc.chart_png(kind, data, chrome=None) is None


def test_chart_png_unknown_kind_is_none():
    assert dc.chart_png('nope', {}, chrome='chrome.exe') is None


def test_chart_png_empty_data_is_none_even_with_chrome():
    # empty payloads → '' svg → None, without ever invoking Chrome
    assert dc.chart_png('donut', {'rows': []}, chrome='chrome.exe') is None
    assert dc.chart_png('sequence_flow', {}, chrome='chrome.exe') is None


# ── every *_svg builds a self-contained SVG on sample data ─────────────────────
def test_all_svgs_are_self_contained():
    for svg in (dc.donut_svg(VALUE), dc.timeline_svg(TIMELINE),
                dc.costbars_svg(COSTBARS), dc.wbs_smartart_svg(WBS),
                dc.sequence_flow_svg(FRONT)):
        assert svg
        assert 'xmlns' in svg
        assert '<svg' in svg
        # opaque white ground so the raster is clean
        assert 'fill="#ffffff"' in svg


# ── empty inputs return '' ─────────────────────────────────────────────────────
def test_empty_inputs_return_blank():
    assert dc.donut_svg({}) == ''
    assert dc.donut_svg({'rows': []}) == ''
    assert dc.timeline_svg({}) == ''
    assert dc.costbars_svg({}) == ''
    assert dc.wbs_smartart_svg({}) == ''
    assert dc.sequence_flow_svg({}) == ''
    assert dc.sequence_flow_svg({'sequence': []}) == ''


# ── donut emits one stroked circle per branch ──────────────────────────────────
def test_donut_emits_multiple_stroked_circles():
    svg = dc.donut_svg(VALUE)
    assert svg.count('<circle') >= len(VALUE['rows'])
    assert svg.count('stroke=') >= len(VALUE['rows'])


# ── sequence flow emits one chevron box per step (>=2 for a 2-step front) ──────
def test_sequence_flow_emits_step_boxes():
    two = dc.sequence_flow_svg(FRONT2)
    assert two.count('<polygon') >= 2
    four = dc.sequence_flow_svg(FRONT)
    assert four.count('<polygon') == 4


# ── wbs smartart uses the blue palette + elbow connectors ─────────────────────
def test_wbs_smartart_coloured_and_connected():
    svg = dc.wbs_smartart_svg(WBS)
    assert '#1F4E79' in svg          # per-depth blue palette (root)
    assert '<path' in svg            # elbow connectors
    assert svg.count('<rect') >= 5   # one filled box per node (+ white ground)


# ── stream wraps bytes for python-docx ────────────────────────────────────────
def test_stream_wraps_bytes():
    buf = dc.stream(b'\x89PNG-data')
    assert buf.read() == b'\x89PNG-data'
