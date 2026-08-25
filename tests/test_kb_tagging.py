"""Phase 1 — the multi-signal identity tagger: discipline/system/phase/zone with
confidence, working without clean discipline codes, no over-tagging, no project
hardcoding."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.tagging import tag_activity, detect_systems, tag_view


def A(name, codes=None, wbs=''):
    return {'name': name, 'wbs_path': wbs, 'activity_codes': codes or {}, 'object_id': name}


def test_system_from_name_only():
    assert tag_activity(A('Chiller Installation & Alignment'))['system'] == 'chilled_water'
    assert tag_activity(A('Cable Tray Installation'))['system'] == 'containment_cabling'
    assert tag_activity(A('Fire Fighting Sprinkler Network'))['discipline'] == 'FIRE'
    assert tag_activity(A('HVAC Ductwork Installation'))['discipline'] == 'MECH'
    assert tag_activity(A('Transformer Installation'))['system'] == 'electrical_power'


def test_discipline_recovered_from_code_values_any_dimension():
    # different real conventions: "Type of Works", "Trade", "RME-Trade"
    assert tag_activity(A('Install works', {'Type of Works': 'Mechanical Installation Works'}))['discipline'] == 'MECH'
    assert tag_activity(A('Works', {'Trade': 'Steel Structure Works'}))['discipline'] == 'STRUCT'
    assert tag_activity(A('Works', {'RME-Trade': 'Electrical'}))['discipline'] == 'ELEC'
    assert tag_activity(A('Works', {'RME-Trade': 'Plumbing'}))['discipline'] == 'PLUMB'


def test_civil_code_vetoes_a_false_mep_name_match():
    # "conveyor" in the name, but the activity is concrete works (silo project)
    t = tag_activity(A('Concrete Pouring for Conveyor Foundation',
                       {'Type of Works': 'Civil Works'}))
    assert t['discipline'] == 'CIVIL'            # not promoted to MECH/conveying


def test_silo_zone_does_not_force_a_vessel_tag():
    # "Silo 7" is a zone, not an instruction to install a vessel
    t = tag_activity(A('Raft Concrete Pouring', {'Silos Area Name': 'Silo 7', 'Type of Works': 'Civil Works'}))
    assert t['discipline'] == 'CIVIL' and t['system'] != 'tanks_vessels'
    assert t['zone'] == 'Silo 7'                  # but the zone is still captured


def test_works_without_clean_codes():
    # NO discipline code at all — must still tag from the name
    t = tag_activity(A('LV Cable Pulling and Termination'))
    assert t['discipline'] == 'ELEC' and t['system'] == 'containment_cabling'
    assert t['confidence'] in ('medium', 'high')


def test_phase_and_confidence():
    assert tag_activity(A('Chiller Commissioning'))['phase'] == 'COMMISSIONING'
    assert tag_activity(A('CHW Piping Hydrotest'))['phase'] == 'TESTING'
    # code + name agree on discipline → high confidence
    t = tag_activity(A('HVAC Duct Installation', {'RME-Trade': 'HVAC'}))
    assert t['confidence'] == 'high'


def test_detect_systems_rollup():
    view = {'activities_oid': [
        A('Chiller Installation'), A('CHW Piping'), A('Cable Tray Install'),
        A('Fire Fighting Pump'), A('Concrete Raft', {'Type of Works': 'Civil Works'}),
        A('Some Admin Milestone')]}
    tag_view(view)
    d = detect_systems(view)
    syskeys = {s['system'] for s in d['systems_present']}
    assert 'chilled_water' in syskeys and 'containment_cabling' in syskeys and 'fire_fighting' in syskeys
    assert d['mep_activities'] >= 4 and d['total_activities'] == 6
    assert 0 <= d['tagged_pct'] <= 100
