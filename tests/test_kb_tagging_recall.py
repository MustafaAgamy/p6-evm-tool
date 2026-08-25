"""Tagging recall + false-positive guards, from REAL project schedules.

Broadening system tagging (WBS/code fallback) and removing the archetype gate raised
recall on real schedules — but naive broadening mis-classified silo/structural work as
MEP and mis-phased procurement/delivery activities, manufacturing false findings. These
lock the guards that keep recall high while holding false positives at zero.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.tagging import tag_activity


def _tag(name, wbs='', codes=None):
    return tag_activity({'name': name, 'wbs_path': wbs, 'activity_codes': codes or {}})


# ── recall gains: WBS/code fills in when the NAME alone gives no system ──

def test_wbs_specific_system_is_recovered():
    # a generic activity name under a specific-system WBS branch is tagged from the WBS
    t = _tag('Install ductwork level 2', wbs='MEP Works > HVAC System > Level 2')
    assert t['system'] == 'hvac'
    t2 = _tag('Second fix works', wbs='Electrical > Transformer & Switchgear Room')
    assert t2['system'] == 'electrical_power'   # 'transformer' is a specific term in the WBS


# ── FP guard 1: generic discipline words in a WBS must NOT tag an MEP system ──

def test_generic_mechanical_wbs_does_not_tag_equipment():
    # real Grain Bulk case: silo sheet erection under a "Mechanical Works" branch was
    # wrongly tagged mechanical_equipment -> false 'testing before installation'
    t = _tag('Erection Of Silos Sheets', wbs='CONSTRUCTION > Mechanical Works > Silo S1',
             codes={'Discipline': 'MECH'})
    assert t['system'] != 'mechanical_equipment'
    t2 = _tag('Roof Water Testing', wbs='CONSTRUCTION > Mechanical Works > Silo S1',
              codes={'Discipline': 'MECH'})
    assert t2['system'] != 'mechanical_equipment'


# ── FP guard 2: 'insulation' as a MODIFIER must not set the late INSULATION phase ──

def test_insulation_modifier_does_not_set_insulation_phase():
    # real Alstom cases — delivery / install / procurement of material that happens to
    # mention insulation must take the pre-execution phase, not INSULATION
    assert _tag('Copper pipes & insulation - Delivery to Site')['phase'] == 'DELIVERY'
    assert _tag('Duct Thermal Insulation & Accessories - Purchase Orders')['phase'] in (
        'PROCUREMENT', 'DESIGN')
    assert _tag('Drainage Pipes Above Insulation Installation Works')['phase'] == 'ERECTION_INSTALL'


def test_genuine_insulation_activity_stays_insulation_phase():
    # the real thing must still be INSULATION so R6 (cover-before-hydrotest) keeps working
    assert _tag('Process Pipe Insulation')['phase'] == 'INSULATION'
    assert _tag('Pipe lagging works')['phase'] == 'INSULATION'
