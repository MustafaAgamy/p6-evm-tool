"""Gate for the v5 Narrative Report producer (p6_narrative/report.py). Locks the section
contract, JSON-serialisability, determinism, adaptive WBS, and sequence consolidation —
independent of the HTML/DOCX renderers."""
import json

from p6_narrative.report import build_report, consolidate_seq
from tests import intel_fixtures as F

EXPECTED_KINDS = ['overview', 'ms_table', 'wbs_tree', 'seq', 'interfaces']


def _doc(fixture):
    return build_report(fixture).to_dict()


def test_report_has_the_five_locked_sections_in_order():
    doc = _doc(F.matrix_epc(4))
    assert [s['kind'] for s in doc['sections']] == EXPECTED_KINDS
    assert [s['number'] for s in doc['sections']] == ['1', '2', '3', '4', '5']
    assert [s['title'] for s in doc['sections']] == [
        'Project Overview', 'Major Milestones', 'Work Breakdown Structure',
        'Sequence of Work', 'Interfaces & Dependencies']


def test_report_is_json_serialisable_and_deterministic():
    a = json.dumps(_doc(F.matrix_epc(4)), sort_keys=True)
    b = json.dumps(_doc(F.matrix_epc(4)), sort_keys=True)
    assert a == b and len(a) > 100


def test_overview_is_executive_without_internal_front_counts():
    ov = _doc(F.matrix_epc(4))['sections'][0]['payload']
    assert ov['paragraphs'] and ov['total'] > 0 and ov['breakdown']
    assert 'front' not in ' '.join(ov['paragraphs']).lower(), \
        'overview must not expose the internal front count'


def test_wbs_layout_is_adaptive_and_a_real_tree():
    for w in _doc(F.matrix_epc(4))['sections'][2]['payload']['worlds']:
        assert w['layout'] in ('tree', 'columns')
        assert 'root' in w and 'children' in w['root']


def test_sequence_carries_packages_and_traceable_activities():
    seq = _doc(F.matrix_epc(4))['sections'][3]['payload']['worlds']
    assert seq
    for w in seq:
        for f in w['fronts']:
            assert 'sequence' in f and 'instances' in f
            assert f['activities'] and all(a.get('id') for a in f['activities'])


def test_consolidate_collapses_docctrl_but_keeps_distinct_stages():
    doc_ctrl = ['Detailed Structural Shop Drawing Submittal',
                'Detailed Steel Shop Drawing Submittal',
                'Detailed Structural Shop Drawing Approval',
                'Detailed Steel Shop Drawing Approval']
    assert consolidate_seq(doc_ctrl) == ['Shop Drawing Submittal', 'Shop Drawing Approval']
    distinct = ['Excavation', 'Soil Replacement', 'Concrete', 'Footing', 'Columns', 'Backfilling']
    assert consolidate_seq(distinct) == distinct


def test_report_builds_on_a_general_non_epc_schedule():
    doc = _doc(F.road(12))  # code-less → general detector → same section contract
    assert [s['kind'] for s in doc['sections']] == EXPECTED_KINDS
    json.dumps(doc)
