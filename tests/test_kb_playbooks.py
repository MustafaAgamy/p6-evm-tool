"""Project Type Playbooks assembly — reference-only, real KB data."""
from p6_kb import playbooks
from p6_kb.patterns import load_archetypes


def test_library_groups_types_into_sectors():
    lib = playbooks.library()
    assert lib['sectors'], 'expected at least one sector'
    assert lib['counts']['types'] == len(load_archetypes())
    for sec in lib['sectors']:
        assert sec['label'] and sec['types']
        for card in sec['types']:
            for key in ('archetype', 'name', 'sector', 'driver', 'system_count',
                        'baseline_available', 'coverage'):
                assert key in card
            assert len(card['coverage']) == 4


def test_data_center_playbook_is_complete():
    pb = playbooks.playbook('data_center')
    assert pb is not None
    assert pb['name'] and pb['sector_label']
    ov = pb['overview']
    assert ov['notes'] and ov['primary_systems']
    assert ov['commissioning_focus'] and ov['civil_interfaces']
    steps = pb['sequence']['steps']
    assert steps and steps[0]['n'] == 1
    assert steps[0]['key'] == 'eng' and steps[-1]['key'] == 'commissioning'
    for s in steps:
        assert s['name'] and 'disciplines' in s
    assert pb['wbs']['branches']                     # a suggested WBS exists
    assert pb['baseline']['available'] is True       # data_center has a curated standard
    assert pb['baseline']['milestones']
    assert isinstance(pb['hold_points'], list)
    assert pb['commissioning']['rungs']              # commissioning focus -> rungs
    assert pb['evidence']['patterns']
    assert len(pb['evidence']['status_vocab']) == 5


def test_wbs_matches_baseline_source_when_curated():
    pb = playbooks.playbook('data_center')
    assert pb['wbs']['source'] == 'curated'
    # the suggested WBS branch count equals the curated wbs the file is built from
    assert len(pb['wbs']['branches']) == pb['baseline']['wbs_count']


def test_unknown_archetype_returns_none():
    assert playbooks.playbook('does_not_exist') is None


def test_every_archetype_builds_a_playbook():
    """No archetype should crash the assembly (they vary in coverage)."""
    for aid in load_archetypes():
        pb = playbooks.playbook(aid)
        assert pb is not None and pb['sequence']['steps']
