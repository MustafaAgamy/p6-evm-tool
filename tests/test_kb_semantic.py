"""Tests for the Semantic Mapping Layer (p6_kb/semantic.py).

Written test-first: maps one messy schedule activity to a normalized
construction-knowledge concept (a system_pattern id) via an ordered, pluggable
list of deterministic stages (tagger -> alias -> fuzzy). Offline, stdlib-only.
"""
from p6_kb import semantic
from p6_kb.patterns import load_system_patterns

# every dict returned by map_activity must carry exactly these documented keys
EXPECTED_KEYS = {
    'concept', 'concept_name', 'discipline', 'phase', 'confidence',
    'method', 'ambiguous', 'signals', 'alternatives',
}


def _act(name, wbs='', codes=None):
    return {'name': name, 'wbs_path': wbs, 'activity_codes': codes or {}}


def test_process_piping_maps_to_a_real_concept():
    patterns = load_system_patterns()
    res = semantic.map_activity(_act('Install Process Piping'))
    assert res['concept'] in patterns          # a real pattern id
    assert res['confidence'] in {'high', 'medium', 'low'}
    assert res['confidence'] != 'none'
    assert res['concept_name']                 # non-empty
    assert res['method'] in {'code', 'name', 'alias', 'fuzzy'}


def test_structural_steel_activity_maps_to_a_steel_concept():
    patterns = load_system_patterns()
    res = semantic.map_activity(_act('Structural Steel Erection - Area A'))
    assert res['concept'] in patterns
    cid = res['concept'].lower()
    assert 'steel' in cid or 'struct' in cid
    assert res['confidence'] != 'none'


def test_unknown_activity_maps_to_nothing():
    res = semantic.map_activity(_act('zzzz qqqq'))
    assert res['concept'] is None
    assert res['concept_name'] is None
    assert res['confidence'] == 'none'
    assert res['method'] == 'none'
    assert res['alternatives'] == []
    assert semantic.status_for('none') == 'not_assessed'


def test_status_for_maps_confidence_to_status():
    assert semantic.status_for('high') == 'knowledge_available'
    assert semantic.status_for('medium') == 'knowledge_available'
    assert semantic.status_for('low') == 'potentially_relevant'
    assert semantic.status_for('none') == 'not_assessed'
    assert semantic.status_for('anything-else') == 'not_assessed'


def test_every_result_has_all_documented_keys():
    for name in ('Install Process Piping', 'Structural Steel Erection',
                 'zzzz qqqq', 'Commissioning of chilled water system',
                 'Erect pipe rack'):
        res = semantic.map_activity(_act(name))
        assert set(res.keys()) == EXPECTED_KEYS, name
        assert isinstance(res['signals'], list)
        assert isinstance(res['alternatives'], list)
        for alt in res['alternatives']:
            assert set(alt.keys()) == {'concept', 'concept_name', 'confidence'}


def test_default_patterns_are_loaded_when_omitted():
    # passing patterns explicitly must give the same concept as the default load
    patterns = load_system_patterns()
    a = semantic.map_activity(_act('Install Process Piping'))
    b = semantic.map_activity(_act('Install Process Piping'), patterns)
    assert a['concept'] == b['concept']
