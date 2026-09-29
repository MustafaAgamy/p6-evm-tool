"""Tests for the reference-assembly layer (p6_kb/reference.py).

Written test-first: assembles the System-Pattern knowledge base into UI-ready
shapes (a browsable index, a per-pattern detail, an activity->knowledge join)
and a small, ordered status vocabulary. Deterministic, stdlib-only.
"""
from p6_kb import reference
from p6_kb.patterns import load_system_patterns

STATUS_KEYS = {v['key'] for v in reference.STATUS_VOCAB}

INDEX_SYSTEM_KEYS = {
    'system', 'name', 'discipline', 'stage_count', 'relationship_count',
    'interface_count', 'aliases', 'summary',
}


def _act(name, wbs='', codes=None):
    return {'name': name, 'wbs_path': wbs, 'activity_codes': codes or {}}


def test_status_vocab_is_the_documented_five():
    assert STATUS_KEYS == {
        'knowledge_available', 'potentially_relevant', 'insufficient_evidence',
        'not_assessed', 'planner_review',
    }
    for v in reference.STATUS_VOCAB:
        assert set(v.keys()) == {'key', 'label', 'desc'}
        assert v['label'] and v['desc']


def test_evidence_grade():
    assert reference.evidence_grade('strong') == {'key': 'strong', 'label': 'Strong evidence'}
    assert reference.evidence_grade('moderate') == {'key': 'moderate', 'label': 'Moderate'}
    for weak in ('weak', None, '', 'other'):
        g = reference.evidence_grade(weak)
        assert g == {'key': 'emerging', 'label': 'Emerging'}


def test_discipline_label_is_short_and_deterministic():
    lbl = reference.discipline_label('MECHANICAL_PIPING')
    assert isinstance(lbl, str) and lbl
    assert '_' not in lbl
    # long parenthetical/slashed labels get trimmed to a short head
    long = reference.discipline_label(
        'STRUCTURAL / STEELWORK (EQUIPMENT SUPPORT, PIPE-RACK & ACCESS STEEL)')
    assert '(' not in long and '/' not in long
    assert reference.discipline_label('MECHANICAL_PIPING') == \
        reference.discipline_label('MECHANICAL_PIPING')


def test_knowledge_index_shape_and_counts():
    patterns = load_system_patterns()
    idx = reference.knowledge_index()
    assert idx['disciplines']                          # non-empty
    total_rel = 0
    seen_systems = 0
    for disc in idx['disciplines']:
        assert disc['discipline'] and disc['label']
        assert disc['systems']
        for sysentry in disc['systems']:
            assert set(sysentry.keys()) == INDEX_SYSTEM_KEYS
            assert isinstance(sysentry['stage_count'], int)
            assert isinstance(sysentry['relationship_count'], int)
            assert isinstance(sysentry['interface_count'], int)
            assert isinstance(sysentry['aliases'], list)
            total_rel += sysentry['relationship_count']
            seen_systems += 1
    assert seen_systems == len(patterns)
    assert idx['counts']['systems'] == len(patterns)
    assert idx['counts']['relationships'] == total_rel
    assert idx['archetypes']                           # non-empty
    assert idx['counts']['archetypes'] == len(idx['archetypes'])


def test_pattern_detail_normalizes_for_display():
    patterns = load_system_patterns()
    sid = 'process_piping'
    assert sid in patterns
    det = reference.pattern_detail(sid)
    assert det is not None
    assert det['system'] == sid
    assert det['sequence'] and det['relationships'] and det['interfaces']
    assert det['evidence']
    assert set(det['provenance'].keys()) == {'source', 'status', 'label'}
    assert det['status'] == 'knowledge_available'
    for s in det['sequence']:
        assert set(s.keys()) == {'stage', 'activities', 'note'}
    for r in det['relationships']:
        assert 'strength_grade' in r
        assert set(r['strength_grade'].keys()) == {'key', 'label'}
        assert 'rel' in r
    # interfaces: with_name resolves to the target pattern's name when known
    for i in det['interfaces']:
        assert set(i.keys()) == {
            'with', 'with_name', 'requirement', 'type', 'phase',
            'strength', 'strength_grade',
        }
        if i['with'] in patterns:
            assert i['with_name'] == patterns[i['with']]['name']
    for w in det['work_components']:
        assert set(w.keys()) == {'wp', 'discipline', 'interface', 'note'}
        assert isinstance(w['interface'], bool)


def test_pattern_detail_unknown_id_is_none():
    assert reference.pattern_detail('not_a_real_system') is None


def test_activity_knowledge_join():
    known = reference.activity_knowledge(_act('Install Process Piping'))
    assert known['knowledge'] is not None
    assert known['status'] in STATUS_KEYS
    assert known['match']['concept'] in load_system_patterns()

    unknown = reference.activity_knowledge(_act('zzzz qqqq'))
    assert unknown['knowledge'] is None
    assert unknown['status'] == 'not_assessed'
