"""The AI prompt + response schema.

Mode 1 (no reference) uses the AI's own construction knowledge. Mode 2 adds a
reference skeleton whose scope/logic must OUTRANK general knowledge — the prompt
must say so, and only when a reference is present.
"""
from p6_ai.prompt import RESPONSE_SCHEMA, build_request, SYSTEM


def _skeleton():
    return {'activity_count': 2, 'relationship_count': 1,
            'activities': [{'id': 'A100', 'name': 'Excavate', 'wbs_path': 'Civil',
                            'is_milestone': False, 'duration_days': 5}],
            'relationships': [{'pred': 'A100', 'succ': 'A200', 'type': 'FS', 'lag_days': 0}],
            'wbs': [{'name': 'Civil', 'path': 'Civil'}]}


def test_schema_has_the_report_sections():
    props = RESPONSE_SCHEMA['schema']['properties']
    for key in ('project_type', 'understood', 'illogical', 'missing', 'wbs_review', 'conclusion'):
        assert key in props


def test_request_carries_model_and_schema():
    req = build_request(_skeleton(), model='claude-opus-5')
    assert req['model'] == 'claude-opus-5'
    assert req['output_config']['format']['type'] == 'json_schema'
    # the skeleton is embedded in the user message
    body = req['messages'][0]['content']
    assert 'A100' in body


def test_mode1_has_no_reference_priority_text():
    req = build_request(_skeleton(), model='claude-opus-5')
    body = req['messages'][0]['content'].lower()
    assert 'reference' not in body or 'no reference' in body


def test_mode2_instructs_reference_outranks_knowledge():
    req = build_request(_skeleton(), model='claude-opus-5', reference=_skeleton())
    body = req['messages'][0]['content'].lower()
    assert 'reference' in body
    assert 'outrank' in body or 'takes priority' in body or 'higher priority' in body


def test_system_frames_advisory_baseline_review():
    s = SYSTEM.lower()
    assert 'baseline' in s and 'advisory' in s
