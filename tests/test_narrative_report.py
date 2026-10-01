"""Gate for the Narrative Report producer (p6_narrative/report.py): the approved section set
(the section-by-section review, §1–§19), JSON-serialisability, determinism, the per-branch WBS
and the logic-ordered sequence — independent of the HTML/DOCX renderers."""
import json

from p6_narrative.report import build_report, consolidate_seq
from tests import intel_fixtures as F

# The report as approved section by section: (kind, title) in print order. A change here is a
# change to the owner's approved report — update it deliberately, with the Reporting Studio's
# list (p6_special/providers/narrative.SECS), never to make a test pass.
SECTIONS = [
    ('overview',     'Project Overview'),
    ('image',        'Project Layout'),
    ('keyvals',      'Project Brief'),
    ('ms_table',     'Major Milestones'),
    ('ms_table',     'Key Dates'),
    ('value_bars',   'Contract Value'),
    ('scope',        'Scope of Work'),
    ('table',        'Project Calendars & Holidays'),
    ('wbs_tree',     'Work Breakdown Structure'),
    ('codes',        'Activity Codes'),
    ('sequence',     'Sequence of Work'),
    ('activity_ids', 'Activity IDs'),
    ('resload',      'Resource Loading'),
    ('materials',    'Material Resources'),
    ('prodrate',     'Productivity Rates & Resources Assigned'),
    ('volwork',      'Volume of Work'),
    ('critpath',     'Appendix (Critical Path)'),
    ('mapsheet',     'Appendix (Critical Path From P6)'),
    ('mapsheet',     'Appendix (Mapping Sheet)'),
]


def _doc(fixture):
    return build_report(fixture).to_dict()


def test_report_has_the_approved_sections_in_order():
    doc = _doc(F.matrix_epc(4))
    assert [(s['kind'], s['title']) for s in doc['sections']] == SECTIONS
    assert doc['sections'][0]['kind'] == 'overview'            # overview leads
    # sections are contiguously numbered 1..N
    assert [s['number'] for s in doc['sections']] == [str(i) for i in range(1, len(doc['sections']) + 1)]


def test_the_reporting_studio_offers_exactly_these_sections():
    from p6_special.providers.narrative import SECS
    assert [title for _slug, title in SECS] == [title for _kind, title in SECTIONS]
    assert len({slug for slug, _title in SECS}) == len(SECS)   # stable, unique item ids


def test_report_is_json_serialisable_and_deterministic():
    a = json.dumps(_doc(F.matrix_epc(4)), sort_keys=True)
    b = json.dumps(_doc(F.matrix_epc(4)), sort_keys=True)
    assert a == b and len(a) > 100


def test_overview_is_executive_without_internal_front_counts():
    ov = next(s for s in _doc(F.matrix_epc(4))['sections'] if s['kind'] == 'overview')['payload']
    assert ov['paragraphs'] and ov['total'] > 0 and ov['breakdown']
    assert 'front' not in ' '.join(ov['paragraphs']).lower()


def test_wbs_is_an_overview_plus_one_adaptive_branch_per_main_wbs():
    wbs = next(s for s in _doc(F.matrix_epc(4))['sections'] if s['kind'] == 'wbs_tree')['payload']
    # the first picture: the project and its main WBS branches
    assert wbs['overview']['name'] == 'Factory'
    main = [c['name'] for c in wbs['overview']['children']]
    assert main == ['Engineering', 'Construction']
    # then one picture per main branch, each a real tree: columns of [name, children]
    assert [b['name'] for b in wbs['branches']] == main
    for b in wbs['branches']:
        assert b['depth'] >= 1 and b['columns']
        for name, kids in b['columns']:
            assert isinstance(name, str) and name and isinstance(kids, list)


def test_sequence_is_read_from_the_logic_and_says_so():
    seq = next(s for s in _doc(F.matrix_epc(4))['sections'] if s['kind'] == 'sequence')['payload']
    assert seq['analyses']
    first = seq['analyses'][0]
    assert first['codes'] == ['Type of Work'] and first['kind'] == 'single'
    assert [st['name'] for st in first['steps']] == ['Engineering', 'Construction']     # logic order
    assert all(st['count'] > 0 for st in first['steps'])                                # traceable to activities
    assert 'dependency links' in first['narrative']                                     # taken from logic, not assumed


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
    assert [(s['kind'], s['title']) for s in doc['sections']] == SECTIONS
    wbs = next(s for s in doc['sections'] if s['kind'] == 'wbs_tree')['payload']
    assert len(wbs['branches'][0]['columns']) == 12            # the 12 chainages, none dropped
    # a schedule with no activity codes has no code-based sequence: an empty list, never invented
    assert next(s for s in doc['sections'] if s['kind'] == 'sequence')['payload'] == {'analyses': []}
    json.dumps(doc)
