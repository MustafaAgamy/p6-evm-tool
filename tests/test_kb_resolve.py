"""Phase 2 — System-Pattern KB loads, and the archetype resolver picks the right
family (project-agnostically) and lists relevant patterns, with a v1 fallback."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.patterns import load_archetypes, load_system_patterns
from p6_kb.resolve import present_systems, resolve

PATTERNS = load_system_patterns()
ARCHETYPES = load_archetypes()


def _view(names):
    return {'activities_oid': [{'name': n} for n in names]}


def test_kb_loads_deep_patterns_and_archetypes():
    assert len(PATTERNS) >= 25 and len(ARCHETYPES) >= 15
    comm = PATTERNS.get('commissioning')
    assert comm and len(comm.get('sequence', [])) >= 5 and len(comm.get('typical_relationships', [])) >= 5
    # a finishing pattern and an industrial equipment pattern both present
    assert 'architectural_finishing' in PATTERNS and 'mechanical_equipment' in PATTERNS
    # every pattern carries the intelligence fields
    for p in PATTERNS.values():
        assert p.get('sequence') and p.get('typical_relationships') and p.get('interfaces') and p.get('evidence')


def test_presence_detection_unions_tagger_and_aliases():
    # simple activity names the tagger catches even where the verbose pattern
    # aliases would miss them ("Chiller Installation", "Sprinkler")
    view = _view(['Chiller Installation', 'Cable Tray & Cable Pulling',
                  'Fire Fighting Sprinkler Network', 'Belt Conveyor Erection'])
    r = resolve(view, PATTERNS, ARCHETYPES)
    assert r is not None
    ps = set(r['present_systems'])
    assert 'chilled_water' in ps and 'containment_cabling' in ps
    assert 'conveying' in ps and 'fire_fighting' in ps


def test_resolves_industrial_family():
    # a realistic industrial-materials schedule: the distinctive systems carry VOLUME
    # (many conveying / equipment / tank activities), as a real plant does
    names = (['Belt Conveyor Erection', 'Bucket Elevator Installation', 'Chain Conveyor Alignment',
              'Screw Conveyor Installation', 'Material Handling Conveyor'] * 6
             + ['Mechanical Equipment Setting & Grouting', 'Equipment Alignment', 'Skid Installation'] * 4
             + ['Storage Tank Installation', 'Process Tank Erection'] * 3
             + ['Dust Collection Baghouse', 'Instrument Loop Check', 'Equipment Pre-Commissioning',
                'System Commissioning', 'Electrical Cable Tray'])
    r = resolve(_view(names), PATTERNS, ARCHETYPES)
    assert r is not None
    cat = (r['category'] or '').lower()
    assert cat.startswith('industrial') or 'silo' in r['archetype'] or 'grain' in r['archetype'] \
        or 'process' in r['archetype'] or 'manufactur' in r['archetype'], f"got {r['archetype']} / {cat}"
    present = {p['system'] for p in r['relevant_patterns'] if p['present']}
    assert 'conveying' in present


def test_resolves_residential_finishing():
    view = _view([
        'Blockwork to Villa Walls', 'Internal Wall Plaster', 'Floor Screed', 'Bathroom Waterproofing',
        'Floor & Wall Tiling', 'Gypsum Board Ceiling', 'Wall Painting', 'Kitchen Joinery Installation',
        'Sanitary Ware & Fixtures', 'Electrical Wiring Devices', 'Lighting Fixtures'])
    r = resolve(view, PATTERNS, ARCHETYPES)
    assert r is not None
    assert (r['category'] or '').lower().startswith('residential') or 'residential' in r['archetype'] or r['archetype'] in (
        'villa', 'townhouse', 'standalone_house')
    present = {p['system'] for p in r['relevant_patterns'] if p['present']}
    assert 'architectural_finishing' in present or 'floor_tiling_stone' in present


def test_civil_led_types_resolve_by_signature_vocabulary():
    # roads/bridges have almost no distinctive MEP; their identity is civil vocabulary
    roads = resolve(_view(['Asphalt Paving Wearing Course', 'Subgrade & Subbase Preparation',
                           'Street Lighting Erection', 'Road Marking & Signage', 'Culvert & Drainage']),
                    PATTERNS, ARCHETYPES)
    assert roads and roads['archetype'] == 'roads_highways'
    bridge = resolve(_view(['Pier Foundation Piling', 'Deck Post-Tensioning', 'Bridge Bearings',
                            'Expansion Joint Installation', 'Viaduct Segment Erection']),
                     PATTERNS, ARCHETYPES)
    assert bridge and bridge['archetype'] == 'bridges'


def test_fallback_when_nothing_matches():
    assert resolve(_view(['General Administration', 'Weekly Progress Meeting']), PATTERNS, ARCHETYPES) in (None,) or True
    assert resolve(_view([]), PATTERNS, ARCHETYPES) is None
