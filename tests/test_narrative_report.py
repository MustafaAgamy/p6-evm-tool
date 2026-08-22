"""Gate for the Narrative Report producer (p6_narrative/report.py), reconciled to the Golden
Reference: full section set, JSON-serialisability, determinism, adaptive full-depth WBS, and
logic-ordered / consolidated sequences — independent of the HTML/DOCX renderers."""
import json

from p6_narrative.report import build_report, consolidate_seq
from tests import intel_fixtures as F


def _doc(fixture):
    return build_report(fixture).to_dict()


def test_report_has_the_core_sections_reconciled_to_reference():
    doc = _doc(F.matrix_epc(4))
    kinds = [s['kind'] for s in doc['sections']]
    # overview leads; the intelligence sections and the content-breadth sections are present
    assert doc['sections'][0]['kind'] == 'overview'
    for k in ('overview', 'wbs_tree', 'seq', 'interfaces', 'scope', 'codes'):
        assert k in kinds, 'missing section kind: ' + k
    # sections are contiguously numbered 1..N
    assert [s['number'] for s in doc['sections']] == [str(i) for i in range(1, len(doc['sections']) + 1)]


def test_report_is_json_serialisable_and_deterministic():
    a = json.dumps(_doc(F.matrix_epc(4)), sort_keys=True)
    b = json.dumps(_doc(F.matrix_epc(4)), sort_keys=True)
    assert a == b and len(a) > 100


def test_overview_is_executive_without_internal_front_counts():
    ov = next(s for s in _doc(F.matrix_epc(4))['sections'] if s['kind'] == 'overview')['payload']
    assert ov['paragraphs'] and ov['total'] > 0 and ov['breakdown']
    assert 'front' not in ' '.join(ov['paragraphs']).lower()


def test_wbs_is_per_branch_adaptive_and_a_real_tree():
    wbs = next(s for s in _doc(F.matrix_epc(4))['sections'] if s['kind'] == 'wbs_tree')['payload']
    assert wbs['worlds']
    for w in wbs['worlds']:
        assert w['layout'] in ('tree', 'columns')
        assert 'root' in w and 'children' in w['root']


def test_sequence_carries_packages_and_traceable_activities():
    for s in _doc(F.matrix_epc(4))['sections']:
        if s['kind'] != 'seq':
            continue
        for w in s['payload']['worlds']:
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
    doc = _doc(F.road(12))
    kinds = [s['kind'] for s in doc['sections']]
    assert 'wbs_tree' in kinds and 'seq' in kinds
    json.dumps(doc)
