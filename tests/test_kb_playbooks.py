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


def test_data_center_uses_curated_content():
    pb = playbooks.playbook('data_center')
    assert pb.get('is_curated') is True and pb.get('curated')
    cur = pb['curated']
    assert cur.get('schema') == 2
    assert [t['name'] for t in cur['trades']][:2] == ['Civil / Structural', 'Electrical Power']
    assert len(cur['components']) == 6 and len(cur['trades']) == 7
    assert cur['trades'][1]['steps'][0].startswith('Long-lead procurement')


def test_data_center_schema2_sections_present():
    """The 6-part playbook: scope-teaching brief, MEP, sequence chart, deep WBS, Basis of Planning."""
    cur = playbooks.playbook('data_center')['curated']
    b = cur['brief']
    assert isinstance(b, dict) and b['intro'] and b['scope'] and b['glossary'] and b['must_get_right']
    assert len(cur['mep_systems']) == 4 and all(m['discipline'] and m['items'] for m in cur['mep_systems'])
    assert cur['sequence_chart']['lanes'] and all(t.get('kind') for t in cur['trades'])
    assert max(w['level'] for w in cur['wbs']) >= 6           # P6 tree goes past level 5
    bop = cur['basis_of_planning']
    assert bop['sections'] and any('table' in s for s in bop['sections'])


def test_starter_xer_round_trips_and_matches_curated_wbs(tmp_path):
    """The baseline XER imports through the tool's own parser and its WBS == the screen WBS."""
    from p6_kb.starter_xer import write_starter_xer
    from p6_evm.xer import parse_xer, read_xer_tables
    pb = playbooks.playbook('data_center')
    out = str(tmp_path / 'dc.xer')
    write_starter_xer(pb['name'], pb['curated']['wbs'], out)
    tabs = read_xer_tables(out)
    assert len(tabs['PROJWBS']) == len(pb['curated']['wbs'])
    assert sum(1 for w in tabs['PROJWBS'] if w['proj_node_flag'] == 'Y') == 1
    assert not [w for w in tabs['PROJWBS'] if w['proj_node_flag'] != 'Y' and not w['parent_wbs_id']]
    data = parse_xer(out)
    assert len(data.wbs) == len(pb['curated']['wbs'])
    assert data.activities and data.relationships


def test_derived_fallback_when_no_curated_file():
    """The whole library is curated now, but the derived fallback must still work:
    load_curated returns None for a type with no file, and playbook() always
    provides the derived overview/sequence/wbs regardless of curation."""
    assert playbooks.load_curated('a_type_with_no_curated_file') is None
    pb = playbooks.playbook('villa')
    assert pb is not None and pb['sequence']['steps'] and pb['wbs']['branches'] is not None


def test_whole_library_is_curated_and_renders():
    """Every archetype now has a valid schema-2 curated playbook."""
    curated = 0
    for aid in load_archetypes():
        pb = playbooks.playbook(aid)
        assert pb is not None and pb['sequence']['steps']
        cur = pb.get('curated')
        if cur:
            curated += 1
            assert cur.get('trades') and cur.get('wbs') and cur.get('brief')
    assert curated == len(load_archetypes())          # all types authored


def test_every_archetype_builds_a_playbook():
    """No archetype should crash the assembly (they vary in coverage)."""
    for aid in load_archetypes():
        pb = playbooks.playbook(aid)
        assert pb is not None and pb['sequence']['steps']
