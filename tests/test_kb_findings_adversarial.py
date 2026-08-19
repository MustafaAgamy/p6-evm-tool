"""Permanent regression guard from the R1–R7 adversarial validation gate.

An independent adversarial sweep (7 agents, 68 schedules across project families, each
run through the real engine) surfaced 28 engine-confirmed FALSE POSITIVES and a set of
FALSE NEGATIVES. Every root cause is pinned here so it can never silently return:

  FALSE POSITIVES the engine must NOT raise (each is a legitimate, buildable sequence):
    • R1  — power reaches commissioning transitively (2 hops), or via an energization
            activity that tags to its own system (fire pump / HVAC energization).
    • R2/R4 — a Factory Acceptance Test legitimately precedes site installation.
    • R3  — a standalone tank hydrotest legitimately precedes its piping/instrument tie-in.
    • R4  — post-flush reinstatement of in-line items is the correct order (per R6).
    • R5  — an '<equipment> foundation' (tagger demotes it to system=None) still counts
            as the machine's foundation.
    • R6  — pre-test 'final bolt-up' is required make-up, not a post-test cover.
    • R7  — a construction handover / snagging / close-out is not an integration test.

  FALSE NEGATIVES the engine MUST raise (each is a real, unbuildable defect):
    • R6 transitive (insulation → MC → hydrotest); R6 on non-'piping' hydronic systems.
    • R4 on INSULATION driving erection; R4 on COMMISSIONING driving an earlier commission
      phase (same group).
    • R5 per-activity (one pump founded does not clear an unfounded pump beside it).
    • R1 on a conveyor (a non-'MECH'-spelled discipline) commissioned with power unlinked.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.findings import generate_findings
from p6_kb.resolve import resolve
from p6_kb.tagging import tag_view


def mkview(activities, rels=()):
    oid = [{'object_id': f'O{i}', 'id': f'A{i:03d}', 'name': n, 'wbs_path': '',
            'activity_codes': {}, 'task_type': 'Task'} for i, n in enumerate(activities)]
    view = {
        'activities_oid': oid, 'by_oid': {a['object_id']: a for a in oid},
        'relationships_oid': [{'pred_oid': f'O{p}', 'succ_oid': f'O{s}', 'type': 'FS',
                               'lag_days': 0, 'lag_hours': 0} for p, s in rels],
        'activities': oid, 'by_code': {a['id']: a for a in oid},
        'relationships': [], 'wbs': [], 'activity_count': len(oid),
        'relationship_count': len(rels), 'activity_code_types': [],
    }
    tag_view(view)
    return view


def fire(activities, rels, kind=None, system=None):
    f = generate_findings(mkview(activities, rels), resolve(mkview(activities, rels)))
    if kind:
        f = [x for x in f if x['kind'] == kind]
    if system:
        f = [x for x in f if x['system'] == system]
    return f


# ─────────────────────────── FALSE POSITIVES — must stay SILENT ───────────────

def test_FP_R1_power_is_transitive():
    # foundation → install → ENERGIZE → align → pre-comm → commission: power is 2 hops
    # upstream of commissioning, so it IS available — R1 must not fire.
    acts = ['Equipment foundation and anchor bolts', 'Install centrifugal process pump',
            'Energize main switchgear', 'Pump final alignment and coupling',
            'Pump pre-commissioning checks', 'Pump commissioning']
    rels = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
    assert not fire(acts, rels, kind='missing_interface', system='rotating_equipment')


def test_FP_R1_energization_tags_own_system():
    # 'Fire pump energization' tags fire_fighting (not electrical_power) but is a real
    # POWER_AVAILABLE step — R1 must accept it and stay silent.
    acts = ['MV switchgear installation', 'Fire pump energization', 'Fire pump commissioning']
    rels = [(0, 1), (1, 2)]
    assert not fire(acts, rels, kind='missing_interface', system='fire_fighting')


def test_FP_R2R4_factory_acceptance_test_precedes_install():
    acts = ['Switchgear Factory Acceptance Test (FAT)', 'Switchgear Delivery to Site',
            'Switchgear installation']
    rels = [(0, 1), (1, 2)]
    assert not fire(acts, rels, kind='out_of_sequence', system='electrical_power')


def test_FP_R3_tank_hydrotest_precedes_piping_tiein():
    # API-650: a tank is hydrotested standalone before its process-piping tie-in.
    acts = ['Erect storage tank shell and roof', 'Storage tank hydrostatic settlement test',
            'Erect process piping tie-in to tank nozzles']
    rels = [(0, 1), (1, 2)]
    assert not fire(acts, rels, kind='out_of_sequence', system='tanks_vessels')


def test_FP_R4_flush_before_reinstate_is_correct():
    acts = ['Process pipe spool erection', 'Chemical cleaning and flushing of piping',
            'Reinstate in-line control valves and instruments']
    rels = [(0, 1), (1, 2)]
    assert not fire(acts, rels, kind='out_of_sequence', system='piping')


def test_FP_R5_equipment_foundation_named_activity_clears():
    # 'Pump foundation …' tags system=None (equipment word + civil word) but is still the
    # machine's foundation — R5 must clear on the name.
    acts = ['Pump foundation and anchor bolts', 'Install centrifugal process pump']
    rels = [(0, 1)]
    assert not fire(acts, rels, kind='missing_interface', system='rotating_equipment')


def test_FP_R6_pretest_bolt_up_is_not_a_cover():
    acts = ['Process pipe spool erection', 'Final bolt-up of flanged joints',
            'Process pipe hydrotest']
    rels = [(0, 1), (1, 2)]
    assert not fire(acts, rels, kind='out_of_sequence', system='piping')


def test_FP_R7_construction_handover_is_not_integration():
    acts = ['Structural steel fabrication', 'Structural steel erection',
            'Snagging and close-out of steel works']
    rels = [(0, 1), (1, 2)]
    assert not fire(acts, rels, kind='sequence_gap')


def test_FP_R7_tenant_handover_with_commissioning_elsewhere():
    # a base-build shell handed to tenants before central-plant commissioning; the bare
    # HANDOVER must not read as an integration test even though commissioning exists.
    acts = ['Central chiller plant installation', 'Central chiller plant commissioning',
            'Shell and core completion', 'Tenant handover for fit-out']
    rels = [(0, 1), (2, 3)]
    assert not fire(acts, rels, kind='sequence_gap')


# ─────────────────────────── FALSE NEGATIVES — must FIRE ──────────────────────

def test_FN_R6_insulation_before_hydrotest_transitive():
    acts = ['Process pipe spool erection', 'Insulation and lagging of process piping',
            'Process piping subsystem mechanical completion', 'Hydrotest of process piping test pack']
    rels = [(0, 1), (1, 2), (2, 3)]
    assert fire(acts, rels, kind='out_of_sequence', system='piping'), \
        'R6 must catch insulation → MC → hydrotest (cover before test, transitively)'


def test_FN_R6_on_hydronic_non_piping_system():
    acts = ['Chilled water pipework installation', 'Chilled water pipework insulation and lagging',
            'Chilled water pipework pressure test']
    rels = [(0, 1), (1, 2)]
    assert fire(acts, rels, kind='out_of_sequence', system='chilled_water'), \
        'R6 must run on chilled-water (not only system id "piping")'


def test_FN_R4_insulation_drives_erection():
    acts = ['Kiln refractory lagging', 'Kiln erection and setting']
    rels = [(0, 1)]
    assert fire(acts, rels, kind='out_of_sequence', system='process_equipment'), \
        'R4 must catch INSULATION driving an earlier erection activity'


def test_FN_R4_commissioning_drives_earlier_commission_phase():
    acts = ['Chiller installation', 'Chiller commissioning', 'Chilled water system flushing and cleaning']
    rels = [(1, 2)]
    assert fire(acts, rels, kind='out_of_sequence', system='chilled_water'), \
        'R4 must catch COMMISSIONING driving flushing/pre-comm (same group)'


def test_FN_R5_per_activity_one_founded_one_not():
    # boiler-feed pump IS founded; condensate pump is set on nothing — R5 must still fire
    # for the unfounded one (system-level clearing would wrongly silence it).
    acts = ['Boiler feed pump foundation', 'Boiler feed pump installation',
            'Condensate extraction pump installation']
    rels = [(0, 1)]
    assert fire(acts, rels, kind='missing_interface', system='rotating_equipment'), \
        'R5 must evaluate support per install activity, not system-wide'


def test_FN_R1_conveyor_commissioned_with_power_unlinked():
    # conveying discipline is spelled 'MECHANICAL / BULK MATERIAL HANDLING' — R1 must
    # still recognise it as MEP and fire when power is present but not linked.
    acts = ['MV switchgear and MDB installation', 'Belt conveyor installation',
            'Belt conveyor commissioning']
    rels = [(1, 2)]   # switchgear present but NOT linked to the conveyor
    assert fire(acts, rels, kind='missing_interface', system='conveying'), \
        'R1 must fire for a conveyor commissioned with permanent power unlinked'


# ══════════════════════════════════════════════════════════════════════════════
#  Round-2 confirmation sweep (96 fresh schedules against the hardened engine).
#  The round-1 fixes had over-reached; these pin the second wave of root causes.
# ══════════════════════════════════════════════════════════════════════════════

# ── FALSE POSITIVES — must stay SILENT ──

def test_FP2_R6_reinstate_then_service_leak_test():
    # strength hydrotest passes FIRST; a LATER service leak test after reinstatement is
    # not the gating test — R6 must not read the reinstatement as a cover-before-test.
    acts = ['Process pipe spool erection', 'Process piping hydrotest', 'Process piping flushing',
            'Reinstate in-line items on process piping', 'Process piping service leak test']
    rels = [(0, 1), (1, 2), (2, 3), (3, 4)]
    assert not fire(acts, rels, kind='out_of_sequence', system='piping')


def test_FP2_R6_cross_line_transitive():
    # Line A tested then insulated; crew moves to Line B — B's hydrotest must not be
    # flagged as covered by A's insulation.
    acts = ['Cooling water pipe erection line A', 'Cooling water pipe hydrotest line A',
            'Cooling water pipe insulation line A', 'Cooling water pipe erection line B',
            'Cooling water pipe hydrotest line B']
    rels = [(0, 1), (1, 2), (2, 3), (3, 4)]
    assert not fire(acts, rels, kind='out_of_sequence', system='utilities')


def test_FP2_R6_sectional_hydrotest_direct_cross_zone():
    # Zone A tested then insulated; the insulation directly drives Zone B's hydrotest.
    # Different zones ⇒ crew sequencing, not a covered-before-tested defect.
    acts = ['CHW piping hydrotest Zone A', 'CHW piping insulation Zone A', 'CHW piping hydrotest Zone B']
    rels = [(0, 1), (1, 2)]
    assert not fire(acts, rels, kind='out_of_sequence', system='chilled_water')


def test_FP2_R1_hydrotest_needs_no_power():
    # A fire-water ring-main strength hydrotest needs no electrical power, even though
    # electrical_power is in the project.
    acts = ['Fire fighting ring main pipe erection', 'Fire fighting ring main hydrotest',
            'MV switchgear installation and energization']
    rels = [(0, 1)]
    assert not fire(acts, rels, kind='missing_interface', system='fire_fighting')


def test_FP2_R1_flush_and_pressure_test_no_power():
    acts = ['Chiller installation', 'CHW distribution pipework erection', 'CHW system flushing',
            'CHW pipework hydrostatic pressure test', 'Transformer energization']
    rels = [(0, 1), (1, 2), (2, 3)]
    assert not fire(acts, rels, kind='missing_interface', system='chilled_water')


def test_FP2_R1_earthing_megger_no_power():
    acts = ['Traction Power Substation Installation', 'Earth Mat Installation', 'Earthing System Megger Test']
    rels = [(1, 2)]
    assert not fire(acts, rels, kind='missing_interface', system='earthing')


def test_FP2_R5_base_slab_named_foundation():
    for name in ('Reinforced concrete base slab for Boiler No.1', 'Ground bearing slab for condensate transfer pump',
                 'Substructure concrete for K-101 compressor', 'Quay Crane Rail Beam Concrete Casting'):
        acts = [name, 'Equipment installation and setting']
        assert not fire(acts, [(0, 1)], kind='missing_interface'), f'{name!r} is a foundation'


def test_FP2_R7_finishing_functional_test():
    acts = ['Install automatic sliding doors at main entrance', 'Functional test of automatic sliding doors']
    rels = [(0, 1)]
    assert not fire(acts, rels, kind='sequence_gap')


# ── FALSE NEGATIVES — must FIRE ──

def test_FN2_R4_pressure_test_of_erected_piping():
    # 'Pressure test of erected process piping' is a test, not an install — the mid-name
    # 'erected' must not silence the real test-before-install inversion.
    acts = ['Pressure test of erected process piping', 'Process pipe spool erection']
    rels = [(0, 1)]
    assert fire(acts, rels, kind='out_of_sequence', system='piping')


def test_FN2_R4_onsite_witness_test_before_install():
    acts = ['Witness test of process pipe spool line 10', 'Process pipe spool erection line 10']
    rels = [(0, 1)]
    assert fire(acts, rels, kind='out_of_sequence', system='piping')


def test_FN2_R1_per_activity_one_unpowered():
    # AHU-1 is powered; AHU-2 is not — R1 must fire for AHU-2 (per-activity, not any).
    acts = ['Substation energization', 'AHU-1 installation', 'AHU-1 commissioning',
            'AHU-2 installation', 'AHU-2 commissioning']
    rels = [(0, 1), (1, 2), (3, 4)]
    assert fire(acts, rels, kind='missing_interface', system='hvac')


def test_FN2_R1_unrelated_energization_does_not_count():
    # a chiller commissioned with only a fire-pump energization upstream is unpowered.
    acts = ['Common site enabling milestone', 'Fire pump energization', 'Chiller installation',
            'Chiller commissioning', 'Transformer delivery to site']
    rels = [(0, 1), (0, 2), (1, 3), (2, 3)]
    assert fire(acts, rels, kind='missing_interface', system='chilled_water')


def test_FN2_R7_performance_test_zero_commissioning():
    # a plant performance test with only install + insulation behind it (no commissioning)
    # must fire — pipe insulation is not commissioning.
    acts = ['Chiller installation', 'CHW pipework insulation', 'Plant performance test']
    rels = [(0, 1), (1, 2)]
    assert fire(acts, rels, kind='sequence_gap')


def test_FN2_R5_finishing_grout_does_not_clear():
    # a booster pump whose only predecessor is 'floor tile grouting' is unfounded — the
    # finishing 'grout' must not clear R5.
    acts = ['Floor tile grouting to lobby', 'Booster pump installation']
    rels = [(0, 1)]
    assert fire(acts, rels, kind='missing_interface', system='rotating_equipment')
