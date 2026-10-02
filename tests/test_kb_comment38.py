"""Owner comment 38 — "Knowledge Base: add many more projects — Industrial + Infrastructure;
infrastructure must include all infrastructure networks."

48 project types were added (77 → 125):
  * a new **Infrastructure Networks** shelf where every network is its own type — potable water,
    sewerage, stormwater, irrigation / TSE, fire water, overhead transmission line, underground
    cables, MV / LV distribution, street lighting, telecom / fibre, gas distribution, cross-country
    pipeline, district cooling, traffic signals & ITS, utility tunnel, and the complete site
    infrastructure (roads + all networks);
  * 22 industrial plants (precast, ready-mix, asphalt, brick & block, ceramic tile, gypsum board,
    MDF, rebar mill, pipe, cable, automotive, battery, semiconductor, textile, sugar, tyre, plastics,
    paint, furniture, aluminium smelter, shipyard, steel structures);
  * energy and process types that had a starter baseline but no page (BESS, green hydrogen,
    hydropower, nuclear, CSP, EV charging, fertilizer / ammonia, offshore platform), plus light
    rail / tram and irrigation canals.

Every type is a full curated playbook (brief, scope, glossary, components, sequence by trade, WBS,
basis of planning) and produces a detailed baseline XER.  The baseline generator now homes each
trade on the WBS branch that carries its name.
"""
import pytest

from p6_evm.xer import parse_xer
from p6_kb import playbooks
from p6_kb.patterns import load_archetypes
from p6_kb.starter_xer import _home_wbs, _name_words, _projwbs_rows, build_detailed_xer

NETWORKS = ['water_supply_network', 'sewerage_network', 'stormwater_drainage_network', 'irrigation_network',
            'fire_water_network', 'overhead_transmission_line', 'underground_cable_network',
            'power_distribution_network', 'street_lighting_network', 'telecom_fibre_network',
            'gas_distribution_network', 'cross_country_pipeline', 'district_cooling_network',
            'its_traffic_systems', 'utility_tunnel', 'site_infrastructure_networks']
INDUSTRIAL = ['precast_concrete_factory', 'readymix_batching_plant', 'asphalt_plant', 'brick_block_factory',
              'ceramic_tile_factory', 'gypsum_board_factory', 'mdf_wood_panel_factory', 'rebar_rolling_mill',
              'pipe_factory', 'cable_wire_factory', 'automotive_plant', 'battery_gigafactory',
              'semiconductor_fab', 'textile_factory', 'sugar_factory', 'tyre_factory', 'plastics_factory',
              'paint_coatings_factory', 'furniture_factory', 'aluminium_smelter', 'shipyard',
              'steel_structure_project']
ENERGY_PROCESS = ['battery_energy_storage', 'green_hydrogen_plant', 'hydropower_plant', 'nuclear_power_plant',
                  'csp_solar_plant', 'ev_charging_infrastructure', 'fertilizer_ammonia_plant', 'offshore_platform']
OTHER = ['light_rail_tram', 'irrigation_canals']
NEW = NETWORKS + INDUSTRIAL + ENERGY_PROCESS + OTHER


def test_the_library_grew_to_125_types_with_a_networks_shelf():
    lib = playbooks.library()
    assert lib['counts']['types'] == len(load_archetypes()) >= 125
    assert len(NEW) == 48 and set(NEW) <= set(load_archetypes())
    by_key = {s['key']: s for s in lib['sectors']}
    net = by_key['networks']
    assert net['label'] == 'Infrastructure Networks'
    ids = {t['archetype'] for t in net['types']}
    assert set(NETWORKS) <= ids and 'utilities_network' in ids          # the old generic card moved here
    assert by_key['industrial']['count'] >= 12 + len(INDUSTRIAL)
    labels = [s['label'] for s in lib['sectors']]
    assert labels.index('Infrastructure Networks') == labels.index('Water') + 1


def test_every_infrastructure_network_is_its_own_type():
    """The owner's condition: infrastructure must include ALL the networks."""
    names = {a: playbooks.playbook(a)['name'].lower() for a in NETWORKS}
    for word, aid in (('water', 'water_supply_network'), ('sewer', 'sewerage_network'),
                      ('stormwater', 'stormwater_drainage_network'), ('irrigation', 'irrigation_network'),
                      ('fire water', 'fire_water_network'), ('transmission', 'overhead_transmission_line'),
                      ('cable', 'underground_cable_network'), ('distribution', 'power_distribution_network'),
                      ('lighting', 'street_lighting_network'), ('fibre', 'telecom_fibre_network'),
                      ('gas', 'gas_distribution_network'), ('pipeline', 'cross_country_pipeline'),
                      ('cooling', 'district_cooling_network'), ('traffic', 'its_traffic_systems'),
                      ('tunnel', 'utility_tunnel'), ('all utility networks', 'site_infrastructure_networks')):
        assert word in names[aid], (word, names[aid])


@pytest.mark.parametrize('aid', NEW)
def test_each_new_type_is_a_complete_curated_playbook(aid):
    pb = playbooks.playbook(aid)
    assert pb is not None and pb['is_curated'] and pb['sequence']['steps']
    assert pb['baseline']['available'], 'every new type links to a starter-baseline entry'
    cur = pb['curated']
    assert cur['schema'] == 2 and cur['archetype'] == aid
    brief = cur['brief']
    assert brief['intro'].startswith('New to this project type?') and len(brief['intro']) > 400
    assert len(brief['scope']) >= 8 and len(brief['glossary']) >= 7 and len(brief['must_get_right']) == 4
    assert 5 <= len(cur['components']) <= 8 and 5 <= len(cur['trades']) <= 8
    for t in cur['trades']:
        assert 4 <= len(t['steps']) <= 7 and t['disc'] and t['kind']
        assert all(0 <= h < len(t['steps']) for h in t['holds'])
    assert len(cur['sequence_chart']['lanes']) == len(cur['trades'])
    for lane in cur['sequence_chart']['lanes']:
        assert 0 <= lane['start'] and lane['start'] + lane['width'] <= 100
    codes = [w['code'] for w in cur['wbs']]
    assert len(codes) >= 24 and len(codes) == len(set(codes))
    assert all(w['code'].rsplit('.', 1)[0] in codes for w in cur['wbs'][1:]), 'every WBS row has its parent'
    sections = cur['basis_of_planning']['sections']
    assert len(sections) == 8 and all(s['heading'] and s['body'] for s in sections)
    lead = next(s['table'] for s in sections if s.get('table'))
    assert lead['columns'][0] == 'Item' and len(lead['rows']) >= 3
    # reference-first: no score, no verdict anywhere in the content
    text = str(cur).lower()
    assert '/100' not in text and 'score' not in text


@pytest.mark.parametrize('aid', NEW)
def test_each_new_type_builds_a_detailed_baseline_with_every_trade_on_a_real_branch(aid):
    pb = playbooks.playbook(aid)
    cur = pb['curated']
    text, summary = build_detailed_xer(pb['name'], cur)
    assert summary['activities'] >= 1000 and summary['relationships'] > summary['activities']
    _pw, code_to_id, root_id, rows = _projwbs_rows(cur['wbs'], '1', pb['name'])
    id_to_code = {v: k for k, v in code_to_id.items()}
    for t in cur['trades']:
        home = _home_wbs(t, rows, code_to_id, root_id)
        assert home != root_id, t['name']
        main = next(w['name'] for w in cur['wbs'] if w['code'] == '.'.join(id_to_code[home].split('.')[:2]))
        assert 'procurement' not in main.lower() and 'project management' not in main.lower(), (t['name'], main)


def test_a_detailed_baseline_of_a_new_type_round_trips_through_the_xer_reader(tmp_path):
    pb = playbooks.playbook('sewerage_network')
    text, summary = build_detailed_xer(pb['name'], pb['curated'])
    path = tmp_path / 'sewer.xer'
    path.write_text(text, encoding='utf-8')
    data = parse_xer(str(path))
    assert len(data.activities) == summary['activities'] and data.relationships
    names = {a.get('name') for a in data.activities.values()}
    assert any(n.startswith('Lay & joint pipe to line and gradient') for n in names)
    assert any(n.startswith('Procure & deliver — Submersible pumps') for n in names)


def test_the_baseline_generator_homes_a_trade_on_the_branch_that_carries_its_name():
    rows = [{'code': 'X', 'name': 'Project', 'level': 1},
            {'code': 'X.01', 'name': 'Project Management & Preliminaries', 'level': 2},
            {'code': 'X.03', 'name': 'Procurement', 'level': 2},
            {'code': 'X.03.10', 'name': 'Fire pumps & controllers', 'level': 3},
            {'code': 'X.04', 'name': 'Civil Works — Trenching & Thrust Blocks', 'level': 2},
            {'code': 'X.05', 'name': 'Fire Water Tank (Mechanical)', 'level': 2},
            {'code': 'X.06', 'name': 'Fire Pump House (Pump Equipment)', 'level': 2},
            {'code': 'X.07', 'name': 'Ring Main (Piping)', 'level': 2},
            {'code': 'X.08', 'name': 'Cranes (STS / RTG)', 'level': 2},
            {'code': 'X.09', 'name': 'Electrical & Fuel Management', 'level': 2},
            {'code': 'X.10', 'name': 'Testing & Commissioning', 'level': 2}]
    _pw, c2i, root, usable = _projwbs_rows(rows, '1', 'Project')
    name = {v: next(r['name'] for r in rows if r['code'] == k) for k, v in c2i.items()}

    def home(trade_name, kind, disc):
        return name[_home_wbs({'name': trade_name, 'kind': [kind], 'disc': disc}, usable, c2i, root)]

    # by name — not all mechanical trades onto the first mechanical branch
    assert home('Ring Main — Pipe Laying', 'mechanical', 'Mechanical') == 'Ring Main (Piping)'
    assert home('Fire Water Tank & Pump House', 'mechanical', 'Mechanical') == 'Fire Water Tank (Mechanical)'
    # never under Procurement, even though 'Fire pumps & controllers' shares two words
    assert home('Fire Pumps Installation', 'mechanical', 'Mechanical') == 'Fire Pump House (Pump Equipment)'
    # one distinctive word that only one branch has
    assert home('Cranes (Mechanical Equipment)', 'mechanical', 'Mechanical') == 'Cranes (STS / RTG)'
    # 'Management' inside a real work branch does not hide it (only Project Management is excluded)
    assert home('Electrical & Fuel Management', 'electrical', 'Electrical') == 'Electrical & Fuel Management'
    # nothing by name → the discipline's main branch
    assert home('Civil', 'civil', 'Civil') == 'Civil Works — Trenching & Thrust Blocks'
    assert home('Commissioning', 'comm', 'Commissioning') == 'Testing & Commissioning'
    assert _name_words('Gravity Sewers — Pipe Laying') == {'gravity', 'sewer', 'pipe', 'laying'}


def test_no_trade_of_any_library_type_is_left_at_the_project_root():
    for aid in load_archetypes():
        pb = playbooks.playbook(aid)
        cur = pb.get('curated')
        _pw, c2i, root, rows = _projwbs_rows(cur['wbs'], '1', pb['name'])
        for t in cur['trades']:
            assert _home_wbs(t, rows, c2i, root) != root, (aid, t['name'])


def test_kb_type_links_a_page_to_a_starter_baseline_worded_differently():
    arcs = load_archetypes()
    assert arcs['overhead_transmission_line']['kb_type'] == 'Transmission Line (Overhead)'
    pb = playbooks.playbook('overhead_transmission_line')
    assert pb['baseline']['available'] and pb['baseline']['type'] == 'Transmission Line (Overhead)'
    assert pb['baseline']['wbs_count'] > 0 and pb['baseline']['milestones']
    # a type with no such link and no matching entry simply has no starter baseline
    assert playbooks._entry_for({'archetype': 'nope', 'name': 'Nope', 'kb_type': 'Not a type'}, {}) is None


def test_the_new_starter_baseline_entries_are_valid_and_detectable():
    from p6_kb import kb
    entries = kb.load_kb()
    by_type = {e['type']: e for e in (entries.values() if isinstance(entries, dict) else entries)}
    for t in ('Potable Water Supply Network', 'Sewerage Network', 'Stormwater Drainage Network',
              'Irrigation & TSE Network', 'Fire Water Ring Main & Hydrant Network',
              'Underground Power Cable Circuits (HV / MV)', 'Power Distribution Network (MV / LV)',
              'Street Lighting Network', 'Gas Distribution Network', 'Traffic Signals & ITS Network',
              'District Cooling Distribution Network', 'Common Utility Tunnel / Service Corridor',
              'Site Infrastructure — Roads & All Utility Networks'):
        e = by_type[t]
        assert e['category'] == 'Infrastructure' and len(e['signatures']) >= 12
        wbs_names = {w['name'] for w in e['wbs']}
        assert len(wbs_names) >= 8
        assert len(e['activities']) >= 4 and all(a['wbs'] in wbs_names for a in e['activities'])
        assert len(e['logic_rules']) >= 4 and all(r['impact'] in ('Critical', 'Near-critical') for r in e['logic_rules'])
        assert len(e['milestones']) >= 5 and len(e['common_issues']) >= 4


def test_kb_workbook_carries_the_overview_the_chart_figures_and_the_standards(test_server, tmp_path):
    """The Knowledge Base Excel left out the two overview pictures and the standards list
    (found by the comment-29 check; fixed with the new types)."""
    import re
    import zipfile
    from tests.test_server import _post_json
    out = tmp_path / 'sewer.xlsx'
    _, data = _post_json(test_server, '/api/kb/excel', {'type': 'sewerage_network', 'output_path': str(out)})
    assert data['ok'], data
    with zipfile.ZipFile(out) as z:
        names = re.findall(r'<sheet [^>]*name="([^"]*)"', z.read('xl/workbook.xml').decode('utf-8'))
        text = {n: z.read('xl/worksheets/sheet%d.xml' % i).decode('utf-8') for i, n in enumerate(names, 1)}
    assert names == ['Brief &amp; Scope', 'Sequence by trade', 'WBS', 'Basis of Planning']
    assert 'Knowledge Base' in text['Brief &amp; Scope'] and 'Infrastructure Networks' in text['Brief &amp; Scope']
    seq = text['Sequence by trade']
    assert 'Sequence of work — overview' in seq and 'Outfall &amp; Pumping Station Civil' in seq
    assert 'Sequence of work — chart by trade' in seq and 'Starts at (%)' in seq
    assert 'Typical sequence of work' in seq
    bop = text['Basis of Planning']
    assert 'Standards used' in bop and 'EN 1610' in bop and 'Typical lead time' in bop
