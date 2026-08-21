"""Constructability, driven through the Global Print-Preview framework.

Proves the feature is registered, that the default selection reproduces every section
the legacy one-shot PDF had, and that the framework's selection rules (drop / reorder /
No-data) work on real Constructability data.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import p6_report  # noqa: F401  (registers the feature)
from p6_report.render import build_document, manifest
from p6_report.registry import get_spec

REPORT = {
    'project_type': 'Silo / Grain Terminal',
    'confidence': {'level': 'high', 'hits': 5, 'signatures': 6},
    'score': {'overall': 72, 'band': 'amber', 'band_label': 'Minor',
              'logic': 70, 'completeness': 75, 'structure': 80},
    'verdict': {'title': 'Largely buildable', 'detail': 'A few logic gaps to close'},
    'projected': {'overall': 86, 'band_label': 'Ready', 'basis': 'correcting 3 links'},
    'dashboard': {'illogical_count': 3, 'illogical_pct': 2, 'total_relationships': 150,
                  'missing_count': 2, 'missing_pct': 1, 'missing_wbs': 1,
                  'critical_affected': True, 'critical_count': 4, 'coverage': 88},
    'issues_by_wbs': [{'name': 'Conveying', 'count': 5}, {'name': 'Piping', 'count': 3}],
    'illogical': [{'activity_id': 'A1000', 'activity_name': 'Conveyor test', 'wbs_path': 'Testing',
                   'why': 'Test precedes install', 'impact': 'Critical',
                   'current_preds': [], 'current_succs': [], 'suggested_preds': [], 'suggested_succs': []}],
    'missing': [{'suggested_id': 'NEW-01', 'name': 'Hydrotest', 'wbs': 'Piping',
                 'why': 'Normally required before commissioning', 'preds': [], 'succs': []}],
    'wbs_review': [{'status': 'missing', 'name': 'Pre-Commissioning', 'note': 'no branch'}],
    'conclusion': 'Address the flagged logic to reach execution readiness.',
}


def test_feature_is_registered():
    spec = get_spec('constructability', REPORT)
    assert spec is not None and spec.feature == 'constructability'
    assert 'Execution Readiness' in spec.title


def test_default_selection_includes_every_populated_section():
    spec = get_spec('constructability', REPORT)
    doc = build_document(spec, REPORT, selected_ids=None)
    for heading in ('Verdict', 'Constructability Score', 'Readiness Band', 'What-If Projection',
                    'Key Metrics', 'Issues by WBS Phase', 'Illogical Relationships',
                    'Missing Activities', 'WBS Review', 'Conclusion'):
        assert heading in doc, f'missing section: {heading}'
    # the underlying content rendered, not just the headings
    assert 'Conveyor test' in doc and 'Hydrotest' in doc
    assert 'Constructability Score</div>' in doc          # scorebox label from exporters


def test_user_can_drop_the_tables_and_keep_the_dashboard():
    spec = get_spec('constructability', REPORT)
    doc = build_document(spec, REPORT,
                         selected_ids=['verdict', 'scorecard', 'tiles'])
    assert 'Verdict' in doc and 'Key Metrics' in doc
    assert 'Illogical Relationships' not in doc
    assert 'Hydrotest' not in doc                         # missing table absent entirely


def test_user_can_reorder_tables_before_the_dashboard():
    spec = get_spec('constructability', REPORT)
    doc = build_document(spec, REPORT,
                         selected_ids=['illogical', 'scorecard'],
                         order=['illogical', 'scorecard'])
    assert doc.index('Illogical Relationships') < doc.index('Constructability Score')


def test_empty_table_shows_its_own_friendly_note_not_generic_placeholder():
    # the illogical table renders its own graceful message when empty — the approved
    # legacy wording, not the framework's generic "No data available"
    empty = dict(REPORT, illogical=[])
    spec = get_spec('constructability', empty)
    doc = build_document(spec, empty, selected_ids=['illogical'])
    assert 'Illogical Relationships' in doc
    assert 'No illogical relationships flagged' in doc


def test_section_that_renders_nothing_falls_back_to_no_data():
    # wbs_review renders '' when empty, so the framework placeholder is what shows
    empty = dict(REPORT, wbs_review=[])
    spec = get_spec('constructability', empty)
    doc = build_document(spec, empty, selected_ids=['wbs_review'])
    assert 'WBS Review' in doc and 'No data' in doc


def test_projection_defaults_off_when_the_engine_produced_none():
    # a report with no what-if projection must NOT show an empty projection section
    # in the default view (matches the legacy report's conditional inclusion)
    no_proj = {k: v for k, v in REPORT.items() if k != 'projected'}
    spec = get_spec('constructability', no_proj)
    doc = build_document(spec, no_proj, selected_ids=None)   # default selection
    assert 'What-If Projection' not in doc
    # but it is still offered in the selector, just unticked
    m = manifest(spec, no_proj)
    proj = next(c for c in m if c['id'] == 'projection')
    assert proj['default'] is False and proj['has_data'] is False


def test_projection_defaults_on_when_present():
    spec = get_spec('constructability', REPORT)
    doc = build_document(spec, REPORT, selected_ids=None)
    assert 'What-If Projection' in doc


def test_manifest_lists_all_sections_with_types():
    spec = get_spec('constructability', REPORT)
    m = manifest(spec, REPORT)
    assert len(m) == 13
    types = {c['id']: c['type'] for c in m}
    assert types['illogical'] == 'table' and types['readiness_legend'] == 'chart'
    assert types['verdict'] == 'summary' and types['conclusion'] == 'text'
    assert types['evidence_findings'] == 'findings' and types['archetype_summary'] == 'summary'
    assert types['evidence_score'] == 'summary'
    # projection present because this report has one
    assert next(c for c in m if c['id'] == 'projection')['has_data'] is True


def test_evidence_score_component_renders_second_score():
    report = dict(REPORT, v2_score={
        'overall': 72, 'band': 'amber', 'band_label': 'Minor sequence risks',
        'total_deducted': 28.0, 'finding_count': 4, 'by_strength': {'strong': 2, 'moderate': 2},
        'basis': 'MEP-first · strength × discipline weight',
        'deductions': [{'title': 'Chiller comm not tied to power', 'system': 'chilled_water',
                        'discipline_class': 'mep', 'strength': 'strong', 'points': 10.0}],
    })
    spec = get_spec('constructability', report)
    doc = build_document(spec, report, selected_ids=['evidence_score'])
    assert 'MEP-First Execution-Logic Score' in doc
    assert '72' in doc and 'Minor sequence risks' in doc
    assert 'Chiller comm not tied to power' in doc


def test_evidence_score_absent_shows_no_data():
    report = {k: v for k, v in REPORT.items() if k != 'v2_score'}
    spec = get_spec('constructability', report)
    doc = build_document(spec, report, selected_ids=['evidence_score'])
    assert 'MEP-First Execution-Logic Score' in doc and 'No data' in doc


def test_evidence_findings_component_renders_the_rule_engine_output():
    report = dict(REPORT, archetype={
        'archetype': 'process_oil_gas', 'archetype_name': 'Process / Oil & Gas Facility',
        'confidence': 'high', 'signature_terms': ['spool', 'hydrotest'],
        'present_systems': ['piping', 'electrical_power'], 'expected_but_absent': [], 'ambiguous': False,
    }, v2_findings=[{
        'kind': 'out_of_sequence', 'system': 'piping', 'discipline': 'PIPING',
        'title': 'Piping insulated before it was pressure-tested', 'existing': 'insulation drives hydrotest',
        'expected': 'Hydrotest first', 'reason': 'joints must be reachable', 'evidence': 'KB',
        'strength': 'strong', 'impact': 'rework', 'recommendation': 'test before insulate',
        'activities': ['A001', 'A002'],
        'p6': [{'id': 'A001', 'name': 'Pipe Insulation', 'system': 'piping', 'phase': 'INSULATION',
                'preds': [{'id': 'A000', 'name': 'Spool Erection', 'type': 'FS', 'lag': ''}],
                'succs': [{'id': 'A002', 'name': 'Hydrotest', 'type': 'SS', 'lag': '+2d'}]}],
    }])
    spec = get_spec('constructability', report)
    doc = build_document(spec, report, selected_ids=['archetype_summary', 'evidence_findings'])
    assert 'Project-Type Resolution' in doc and 'Process / Oil' in doc   # '&' is HTML-escaped
    assert 'Evidence-Graded Findings' in doc
    assert 'Piping insulated before it was pressure-tested' in doc
    assert 'strong' in doc and 'test before insulate' in doc
    # finding-level P6 traceability drills down to the actual schedule logic
    assert 'A000' in doc and 'Spool Erection' in doc      # the current predecessor
    assert 'SS' in doc and '+2d' in doc                   # relationship type + lag
    assert 'Current predecessor' in doc and 'Current successor' in doc


def test_evidence_findings_empty_shows_no_data():
    report = {k: v for k, v in REPORT.items()}
    report['v2_findings'] = []
    spec = get_spec('constructability', report)
    doc = build_document(spec, report, selected_ids=['evidence_findings'])
    assert 'Evidence-Graded Findings' in doc and 'No findings' in doc
