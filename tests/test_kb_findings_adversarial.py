"""Adversarial regression battery for the R1–R7 constructability rule engine.

These 91 schedules were authored by independent adversarial reviewers (7 project
families, 3 sweep rounds) trying to BREAK the engine — each was run through the real
tag → resolve → generate_findings pipeline and confirmed. They are the permanent gate
that the binding requirement 'avoid false positives' stays satisfied as the rules
evolve. See CLAUDE.md / the constructability redesign.

  • FP cases  — a LEGITIMATE, buildable schedule the engine must NOT flag. The gate:
                 the intended wrong finding kind must not fire. 50 cases, all silent.
  • FN-fires  — a real defect the engine now catches; asserted to keep firing so future
                 hardening cannot silently gut a rule. 35 cases.
  • FN-silent — a real defect the engine conservatively MISSES (acceptable per the
                 binding 'insufficient evidence — planner review' rule). 6 cases, kept
                 as xfail so a future improvement that catches one is noticed.

Solo-runnable — no network, no subagents. Edit the adversarial sweep, not this file.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from p6_kb.findings import generate_findings
from p6_kb.resolve import resolve
from p6_kb.tagging import tag_view


def _mkview(activities, rels):
    oid = [{"object_id": f"O{i}", "id": f"A{i:03d}", "name": n, "wbs_path": "",
            "activity_codes": {}, "task_type": "Task"} for i, n in enumerate(activities)]
    view = {
        "activities_oid": oid, "by_oid": {a["object_id"]: a for a in oid},
        "relationships_oid": [{"pred_oid": f"O{p}", "succ_oid": f"O{s}", "type": "FS",
                               "lag_days": 0, "lag_hours": 0} for p, s in rels],
        "activities": oid, "by_code": {a["id"]: a for a in oid},
        "relationships": [], "wbs": [], "activity_count": len(oid),
        "relationship_count": len(rels), "activity_code_types": [],
    }
    tag_view(view)
    return view


def _run(case):
    v = _mkview(case["activities"], [tuple(r) for r in case["rels"]])
    return generate_findings(v, resolve(v))


CASES = json.loads(r"""
[
 {
  "id": "r1-FP1",
  "intent": "FP",
  "rule": "R1 missing_interface (testing/commission",
  "activities": [
   "Equipment foundation and anchor bolts",
   "Install centrifugal process pump and grout baseplate",
   "Energize main switchgear",
   "Pump final alignment and coupling",
   "Pump pre-commissioning checks",
   "Pump commissioning",
   "Fabricate process pipe spools",
   "Hydrotest process piping test pack"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ],
   [
    3,
    4
   ],
   [
    4,
    5
   ],
   [
    6,
    7
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP2",
  "intent": "FP",
  "rule": "R3 out_of_sequence (cross-system enabler",
  "activities": [
   "Tank equipment foundation and anchor bolts",
   "Erect storage tank shell and roof",
   "Storage tank hydrostatic settlement test",
   "Erect process piping tie-in to tank nozzles",
   "Hydrotest process piping tie-in lines"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ],
   [
    3,
    4
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r1-FP3",
  "intent": "FP",
  "rule": "R5 missing_interface (equipment set with",
  "activities": [
   "Pump foundation and anchor bolts",
   "Install centrifugal process pump",
   "Fabricate process pipe spools",
   "Hydrotest process piping"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP4",
  "intent": "FP",
  "rule": "R1",
  "activities": [
   "Transformer and switchgear installation",
   "Transformer energization / charging",
   "Chiller unit installation and alignment",
   "Chilled water pump installation",
   "Chiller commissioning",
   "CHW system pre-commissioning and flushing",
   "Cooling water make-up piping installation",
   "District cooling plant commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    4
   ],
   [
    5,
    4
   ],
   [
    3,
    2
   ],
   [
    2,
    5
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP5",
  "intent": "FP",
  "rule": "R2",
  "activities": [
   "Switchgear factory acceptance test (FAT)",
   "Switchgear installation",
   "Transformer installation",
   "Transformer energization",
   "Earthing grid installation",
   "Cable tray installation and cable pulling",
   "Substation commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    3
   ],
   [
    2,
    3
   ],
   [
    4,
    1
   ],
   [
    5,
    1
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r1-FP6",
  "intent": "FP",
  "rule": "R7",
  "activities": [
   "Boiler installation",
   "Steam turbine installation",
   "Switchgear installation",
   "Transformer energization",
   "Steam turbine commissioning",
   "Civil structure completion works",
   "Handover of concrete structure to MEP contractor"
  ],
  "rels": [
   [
    0,
    4
   ],
   [
    1,
    4
   ],
   [
    2,
    3
   ],
   [
    3,
    4
   ],
   [
    5,
    6
   ]
  ],
  "wrong_kind": "sequence_gap",
  "fires_now": true
 },
 {
  "id": "r1-FP7",
  "intent": "FP",
  "rule": "R4",
  "activities": [
   "Process piping erection and welding",
   "Process piping hydrotest",
   "Process piping chemical cleaning and flushing",
   "Process piping reinstatement and final assembly",
   "Steam turbine installation",
   "Switchgear installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ],
   [
    4,
    5
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r1-FP8",
  "intent": "FP",
  "rule": "R5",
  "activities": [
   "Boiler feed pump foundation",
   "Boiler feed pump installation",
   "Compressor foundation and grouting",
   "Air compressor installation and alignment",
   "Switchgear installation",
   "Transformer energization",
   "Generator installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    2,
    3
   ],
   [
    1,
    5
   ],
   [
    3,
    5
   ],
   [
    4,
    5
   ],
   [
    6,
    5
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP9",
  "intent": "FP",
  "rule": "R4 out_of_sequence (within-system phase-",
  "activities": [
   "Pump factory acceptance test",
   "Pump delivery to site",
   "Pump installation and alignment",
   "Concrete equipment foundation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    3,
    2
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r1-FP10",
  "intent": "FP",
  "rule": "R1 missing_interface (MEP testing/commis",
  "activities": [
   "Switchgear installation and energization",
   "Instrument loop check",
   "Pump installation",
   "Pump commissioning",
   "Concrete equipment foundation"
  ],
  "rels": [
   [
    4,
    2
   ],
   [
    2,
    3
   ],
   [
    0,
    1
   ],
   [
    1,
    3
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP11",
  "intent": "FP",
  "rule": "R6 out_of_sequence (piping covered/reins",
  "activities": [
   "Process piping erection and welding",
   "Process piping final bolt-up",
   "Process piping hydrotest"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r1-FP12",
  "intent": "FP",
  "rule": "R3 out_of_sequence (cross-system enabler",
  "activities": [
   "Concrete ringwall foundation and plinth",
   "Storage tank erection and installation",
   "Storage tank hydrotest",
   "Level transmitter installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r1-FP13",
  "intent": "FP",
  "rule": "R5 missing_interface (equipment set with",
  "activities": [
   "Pump foundation concrete pour",
   "Pump installation",
   "Pump discharge piping installation",
   "Pump commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP14",
  "intent": "FP",
  "rule": "R7 sequence_gap (integration/performance",
  "activities": [
   "Pump installation",
   "Pump station snagging",
   "Concrete equipment foundation"
  ],
  "rels": [
   [
    2,
    0
   ],
   [
    0,
    1
   ]
  ],
  "wrong_kind": "sequence_gap",
  "fires_now": false
 },
 {
  "id": "r1-FP15",
  "intent": "FP",
  "rule": "R2 (within-system out_of_sequence: testi",
  "activities": [
   "Chiller Factory Acceptance Test (FAT)",
   "Chiller Installation and Alignment",
   "Chilled Water System Commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r1-FP16",
  "intent": "FP",
  "rule": "R4 (within-system phase-GROUP inversion)",
  "activities": [
   "Install Chilled Water Flushing Bypass Station",
   "Cable Tray Installation for Chilled Water Plant",
   "Chiller Pump Alignment"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    0,
    2
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r1-FP17",
  "intent": "FP",
  "rule": "R7 (sequence_gap: integrated/performance",
  "activities": [
   "UPS Installation",
   "UPS Commissioning",
   "Chiller Installation",
   "Chilled Water Commissioning",
   "Busway Installation",
   "Containment Cable Tray Installation",
   "Fire Alarm Installation and Commissioning",
   "Final Documentation Compilation",
   "Client Taking Over and Handover"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    2,
    3
   ],
   [
    6,
    3
   ],
   [
    7,
    8
   ]
  ],
  "wrong_kind": "sequence_gap",
  "fires_now": true
 },
 {
  "id": "r1-FP18",
  "intent": "FP",
  "rule": "R1 missing_interface (MEP testing/commis",
  "activities": [
   "Metro Station Substation Switchgear Installation",
   "AHU Installation at Concourse",
   "HVAC System Energization",
   "AHU Testing and Balancing",
   "HVAC Commissioning",
   "Ductwork Installation",
   "Chiller Installation"
  ],
  "rels": [
   [
    0,
    2
   ],
   [
    1,
    3
   ],
   [
    2,
    4
   ],
   [
    3,
    4
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP19",
  "intent": "FP",
  "rule": "R4 out_of_sequence (within-system later ",
  "activities": [
   "Switchgear Factory Acceptance Test",
   "Switchgear Delivery to Site",
   "Switchgear Installation",
   "Power Cable Termination",
   "Earthing Grid Installation",
   "Switchgear Energization"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    5
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r1-FP20",
  "intent": "FP",
  "rule": "R5 missing_interface (equipment set with",
  "activities": [
   "Structural Steel Erection - Crane Portal Frame",
   "Grouting Works to Crane Baseplates",
   "Quay Crane Equipment Installation",
   "Container Terminal Lighting Installation",
   "Power Cable Laying"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP21",
  "intent": "FP",
  "rule": "R7 sequence_gap (group-3 integration/per",
  "activities": [
   "Quay Pavement Works",
   "Line Marking and Signage",
   "Snagging and Close Out",
   "Container Terminal Lighting Installation",
   "Belt Conveyor Installation",
   "Fire Pump Commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": "sequence_gap",
  "fires_now": false
 },
 {
  "id": "r1-FP22",
  "intent": "FP",
  "rule": "R2/R4 out_of_sequence (testing precedes ",
  "activities": [
   "Chiller unit Factory Acceptance Test (FAT) witnessing",
   "Chiller unit delivery to site",
   "Hotel central chiller plant installation and alignment on inertia base",
   "Hotel central chiller plant commissioning"
  ],
  "rels": [
   [
    0,
    2
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r1-FP23",
  "intent": "FP",
  "rule": "R7 sequence_gap (group-3 activity not pr",
  "activities": [
   "Structural steel frame erection to atrium",
   "Mall base-build shell handover to retail tenants and food court",
   "Central chiller plant installation",
   "Central chiller plant commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": "sequence_gap",
  "fires_now": false
 },
 {
  "id": "r1-FP24",
  "intent": "FP",
  "rule": "R1 missing_interface (testing/commission",
  "activities": [
   "MV switchgear and MDB installation",
   "Sprinkler pipework installation to tenant floors",
   "Fire pump energization",
   "Fire pump commissioning"
  ],
  "rels": [
   [
    0,
    2
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP25",
  "intent": "FP",
  "rule": "R5 missing_interface (equipment set with",
  "activities": [
   "Transfer pump foundation",
   "Transfer pump installation and alignment",
   "Transfer pump set commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP26",
  "intent": "FP",
  "rule": "R5 missing_interface (equipment set with",
  "activities": [
   "Kiln foundation concrete pour",
   "Kiln erection and setting",
   "Kiln process commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP27",
  "intent": "FP",
  "rule": "R1 missing_interface (MEP testing/commis",
  "activities": [
   "Substation energization - permanent power",
   "Equipment foundation - Area 300",
   "Kiln erection and setting",
   "Kiln mechanical completion",
   "Kiln hot commissioning"
  ],
  "rels": [
   [
    1,
    2
   ],
   [
    2,
    3
   ],
   [
    0,
    3
   ],
   [
    3,
    4
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r1-FP28",
  "intent": "FP",
  "rule": "R7 sequence_gap (integrated/performance ",
  "activities": [
   "Silo structural steel fabrication",
   "Silo structural steel erection",
   "Conveyor gallery structural steel erection",
   "Snagging and close-out of steel works"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    3
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": "sequence_gap",
  "fires_now": false
 },
 {
  "id": "r1-FN1",
  "intent": "FN",
  "rule": "R6 out_of_sequence (piping insulation be",
  "activities": [
   "Fabricate process pipe spools",
   "Erect process pipe spools on rack",
   "Install field instruments on process lines",
   "Insulation and lagging of process piping",
   "Process piping subsystem mechanical completion",
   "Hydrotest of process piping test pack"
  ],
  "rels": [
   [
    3,
    4
   ],
   [
    4,
    5
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN2",
  "intent": "FN",
  "rule": "R4 out_of_sequence (within-system, INSUL",
  "activities": [
   "Insulation and lagging of process piping subsystem A",
   "Erect process piping spools subsystem A",
   "Commission process piping line subsystem B with fluid",
   "Hydrotest process piping line subsystem B",
   "Install control valves on process piping"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN3",
  "intent": "FN",
  "rule": "R4 out_of_sequence (within-system, same-",
  "activities": [
   "Insulation and lagging of process piping subsystem A",
   "Erect process piping spools subsystem A",
   "Commission process piping line subsystem B with fluid",
   "Hydrotest process piping line subsystem B",
   "Install control valves on process piping"
  ],
  "rels": [
   [
    2,
    3
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN4",
  "intent": "FN",
  "rule": "R5 missing_interface (equipment with no ",
  "activities": [
   "Erect structural steel equipment support platform",
   "Install process blower on steel platform",
   "Install centrifugal process pump",
   "Fabricate process pipe spools",
   "Hydrotest process piping"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN5",
  "intent": "FN",
  "rule": "R3 out_of_sequence (cross-system enabler",
  "activities": [
   "Equipment foundation pad and anchor bolts",
   "Erect process reactor vessel",
   "Install reactor field instruments and transmitters",
   "Commission process reactor unit"
  ],
  "rels": [
   [
    3,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN6",
  "intent": "FN",
  "rule": "R5",
  "activities": [
   "Reinforced concrete foundations and anchor bolts Area 10",
   "Boiler feed water pump installation and alignment",
   "Condensate extraction pump installation and alignment",
   "Switchgear installation",
   "Transformer energization",
   "Boiler feed water pump commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    5
   ],
   [
    4,
    5
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN7",
  "intent": "FN",
  "rule": "R5",
  "activities": [
   "Structural steel support frame erection",
   "Air compressor installation and alignment",
   "Boiler feed water pump installation and alignment",
   "Switchgear installation",
   "Transformer energization",
   "Air compressor commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    5
   ],
   [
    2,
    5
   ],
   [
    4,
    5
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN8",
  "intent": "FN",
  "rule": "R4 / R2 within-system out-of-sequence (s",
  "activities": [
   "Pump installation",
   "Pump pre-commissioning flushing",
   "Pump commissioning",
   "Concrete equipment foundation"
  ],
  "rels": [
   [
    3,
    0
   ],
   [
    0,
    2
   ],
   [
    2,
    1
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN9",
  "intent": "FN",
  "rule": "R3 cross-system enabler inversion",
  "activities": [
   "Instrument loop check",
   "Pump commissioning",
   "Pump installation",
   "Instrument transmitter installation",
   "Concrete equipment foundation"
  ],
  "rels": [
   [
    2,
    1
   ],
   [
    3,
    0
   ],
   [
    1,
    0
   ],
   [
    4,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": false
 },
 {
  "id": "r1-FN10",
  "intent": "FN",
  "rule": "R4/R2 (within-system out-of-sequence): a",
  "activities": [
   "Chiller Installation and Alignment",
   "Chiller Commissioning",
   "Chilled Water System Flushing and Cleaning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN11",
  "intent": "FN",
  "rule": "R6 (cover/insulation before pressure tes",
  "activities": [
   "Chilled Water Pipework Erection",
   "Chilled Water Pipework Insulation and Lagging",
   "Chilled Water Pipework Pressure Test"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN12",
  "intent": "FN",
  "rule": "R5 missing_interface (equipment set with",
  "activities": [
   "Cable Trench Excavation",
   "Power Cable Laying in Trench",
   "Firewater Pump Installation",
   "Process Pipe Installation",
   "Instrument Calibration"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN13",
  "intent": "FN",
  "rule": "R6 (piping insulated/covered before pres",
  "activities": [
   "Plumbing domestic water riser installation",
   "Plumbing riser pipe insulation and lagging",
   "Plumbing domestic water riser pressure test"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN14",
  "intent": "FN",
  "rule": "R1 (commissioning not tied to permanent ",
  "activities": [
   "MV switchgear and MDB installation",
   "Back-of-house belt conveyor installation",
   "Back-of-house belt conveyor commissioning"
  ],
  "rels": [
   [
    1,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r1-FN15",
  "intent": "FN",
  "rule": "R1 missing_interface (MEP commissioning ",
  "activities": [
   "Substation energization - permanent power",
   "Transfer tower structural steel erection",
   "Belt conveyor installation",
   "Belt conveyor mechanical completion",
   "Belt conveyor no-load commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ],
   [
    3,
    4
   ]
  ],
  "wrong_kind": null,
  "fires_now": false
 },
 {
  "id": "r1-FN16",
  "intent": "FN",
  "rule": "R3 out_of_sequence (cross-system enabler",
  "activities": [
   "Transfer tower structural steel erection",
   "Belt conveyor installation",
   "Bucket elevator installation",
   "Silo storage tank erection",
   "Equipment foundation - Area 300"
  ],
  "rels": [
   [
    1,
    0
   ],
   [
    4,
    3
   ]
  ],
  "wrong_kind": null,
  "fires_now": false
 },
 {
  "id": "r1-FN17",
  "intent": "FN",
  "rule": "R4 out_of_sequence (within-system phase-",
  "activities": [
   "Equipment foundation - Area 300",
   "Kiln erection and setting",
   "Kiln refractory lagging",
   "Baghouse installation",
   "Silo structural steel erection",
   "Bucket elevator installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    0,
    3
   ],
   [
    2,
    1
   ],
   [
    4,
    5
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FP1",
  "intent": "FP",
  "rule": "R6",
  "activities": [
   "Process pipe spool erection line 6",
   "Process piping hydrotest line 6",
   "Process piping flushing line 6",
   "Reinstate in-line items on process piping line 6",
   "Process piping service leak test line 6"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ],
   [
    3,
    4
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r2-FP2",
  "intent": "FP",
  "rule": "R1",
  "activities": [
   "Fire fighting ring main pipe erection",
   "Fire fighting ring main hydrotest",
   "Reactor foundation",
   "Reactor installation",
   "MV switchgear installation and energization",
   "Process pipe spool erection unit 1"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r2-FP3",
  "intent": "FP",
  "rule": "R5",
  "activities": [
   "Substructure concrete for K-101 compressor",
   "Compressor installation"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r2-FP4",
  "intent": "FP",
  "rule": "R6",
  "activities": [
   "Cooling water pipe erection line A",
   "Cooling water pipe hydrotest line A",
   "Cooling water pipe insulation line A",
   "Cooling water pipe erection line B",
   "Cooling water pipe hydrotest line B"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ],
   [
    3,
    4
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r2-FP5",
  "intent": "FP",
  "rule": "R6",
  "activities": [
   "Fire fighting ring main pipe erection",
   "Fire fighting ring main hydrotest",
   "Fire fighting ring main external coating",
   "Fire fighting ring main flow test"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r2-FP6",
  "intent": "FP",
  "rule": "R6 out_of_sequence (pipe covered before ",
  "activities": [
   "CHW piping hydrotest Zone A",
   "CHW piping insulation Zone A",
   "CHW piping hydrotest Zone B"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r2-FP7",
  "intent": "FP",
  "rule": "R5 missing_interface (equipment set with",
  "activities": [
   "Reinforced concrete base slab for Boiler No.1",
   "Boiler installation",
   "Steam pipe erection",
   "Transformer installation and energization"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r2-FP8",
  "intent": "FP",
  "rule": "R1 missing_interface (MEP testing/commis",
  "activities": [
   "Chiller installation",
   "CHW distribution pipework erection",
   "CHW system flushing",
   "CHW pipework hydrostatic pressure test",
   "Transformer energization"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r2-FP9",
  "intent": "FP",
  "rule": "R1 (missing_interface, tanks_vessels)",
  "activities": [
   "MCC Building Switchgear Installation",
   "Site Substation Energization",
   "Clarifier Process Tank Foundation",
   "Clarifier Process Tank Erection",
   "Process Tank Hydrostatic Leak Test"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    2,
    3
   ],
   [
    3,
    4
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r2-FP10",
  "intent": "FP",
  "rule": "R6 (out_of_sequence, utilities) - cross-",
  "activities": [
   "Cooling Water Loop 1 Pipe Laying",
   "Cooling Water Loop 1 Hydrotest",
   "Cooling Water Loop 1 Insulation",
   "Cooling Water Loop 2 Pipe Laying",
   "Cooling Water Loop 2 Hydrotest",
   "Cooling Water Loop 2 Insulation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ],
   [
    3,
    4
   ],
   [
    4,
    5
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r2-FP11",
  "intent": "FP",
  "rule": "R4 (out_of_sequence, utilities) - same p",
  "activities": [
   "Cooling Water Loop 1 Pipe Laying",
   "Cooling Water Loop 1 Hydrotest",
   "Cooling Water Loop 1 Insulation",
   "Cooling Water Loop 2 Pipe Laying",
   "Cooling Water Loop 2 Hydrotest",
   "Cooling Water Loop 2 Insulation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ],
   [
    3,
    4
   ],
   [
    4,
    5
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r2-FP12",
  "intent": "FP",
  "rule": "R6 (out_of_sequence, piping) - reinstate",
  "activities": [
   "Process Pipeline Pressure Test",
   "Process Pipeline Reinstate In-Line Item",
   "Process Pipeline Reinstated Joint Leak Test"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r2-FP13",
  "intent": "FP",
  "rule": "R6",
  "activities": [
   "CHW piping loop A hydrotest",
   "CHW loop A pipe insulation",
   "CHW piping loop B hydrotest",
   "Chiller unit installation",
   "MV switchgear installation",
   "AHU installation",
   "Data hall busway installation"
  ],
  "rels": [
   [
    3,
    0
   ],
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    4,
    3
   ],
   [
    5,
    4
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r2-FP14",
  "intent": "FP",
  "rule": "R5",
  "activities": [
   "Ground bearing slab for condensate transfer pump",
   "Condensate transfer pump installation",
   "MV switchgear installation",
   "Chiller unit installation",
   "AHU installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    2,
    3
   ],
   [
    3,
    4
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r2-FP15",
  "intent": "FP",
  "rule": "R1",
  "activities": [
   "Sanitary drainage piping installation",
   "Drainage system leak test",
   "AHU installation",
   "MV switchgear installation",
   "Fire pump installation",
   "Chilled water piping installation"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r2-FP16",
  "intent": "FP",
  "rule": "R1",
  "activities": [
   "Sprinkler pipework installation",
   "Sprinkler hydrostatic pressure test",
   "MV switchgear installation",
   "AHU installation",
   "Chilled water piping installation"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r2-FP17",
  "intent": "FP",
  "rule": "R1 missing_interface",
  "activities": [
   "Traction Power Substation Installation",
   "Earth Mat Installation",
   "Earthing System Megger Test",
   "Signalling Cable Tray Installation",
   "Platform Cable Termination Works"
  ],
  "rels": [
   [
    1,
    2
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r2-FP18",
  "intent": "FP",
  "rule": "R5 missing_interface",
  "activities": [
   "Quay Crane Rail Beam Concrete Casting",
   "Quay Crane Equipment Erection",
   "Quay Crane Load Test",
   "Reefer Power Distribution Board Installation",
   "Container Yard Lighting Installation",
   "Cable Tray Installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r2-FP19",
  "intent": "FP",
  "rule": "R6 out_of_sequence",
  "activities": [
   "Chilled Water Line A Hydrotest",
   "Chilled Water Line A Insulation",
   "Chilled Water Riser Access Milestone",
   "Chilled Water Line B Hydrotest",
   "Chilled Water Pump Installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r2-FP20",
  "intent": "FP",
  "rule": "R6",
  "activities": [
   "Chilled water riser 1 hydrotest",
   "Chilled water riser 1 pipe insulation",
   "Chilled water riser 2 hydrotest"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": "out_of_sequence",
  "fires_now": false
 },
 {
  "id": "r2-FP21",
  "intent": "FP",
  "rule": "R5",
  "activities": [
   "Reinforced concrete works to booster pump base",
   "Booster pump installation"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": "missing_interface",
  "fires_now": false
 },
 {
  "id": "r2-FP22",
  "intent": "FP",
  "rule": "R7",
  "activities": [
   "Install automatic sliding doors at main entrance",
   "Functional test of automatic sliding doors"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": "sequence_gap",
  "fires_now": false
 },
 {
  "id": "r2-FN1",
  "intent": "FN",
  "rule": "R1",
  "activities": [
   "Compressor foundation",
   "Compressor installation and alignment",
   "Nitrogen system charging",
   "Compressor commissioning",
   "MDB switchgear installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN2",
  "intent": "FN",
  "rule": "R1",
  "activities": [
   "Substation energization",
   "AHU-1 commissioning",
   "AHU-2 installation",
   "AHU-2 commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN3",
  "intent": "FN",
  "rule": "R4",
  "activities": [
   "Pressure test of erected process piping",
   "Process pipe spool erection"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN4",
  "intent": "FN",
  "rule": "R4",
  "activities": [
   "Witness test of process pipe spool line 10",
   "Process pipe spool erection line 10"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN5",
  "intent": "FN",
  "rule": "R5",
  "activities": [
   "Cable trench excavation for power cables",
   "Pump installation and alignment",
   "Reactor foundation",
   "Reactor installation",
   "MV switchgear installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN6",
  "intent": "FN",
  "rule": "R5",
  "activities": [
   "Crane hardstand pad for heavy lift",
   "Compressor installation"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN7",
  "intent": "FN",
  "rule": "R7 sequence_gap (integration/performance",
  "activities": [
   "Chiller installation",
   "CHW pipework insulation",
   "Plant performance test"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN8",
  "intent": "FN",
  "rule": "R4/R2 out_of_sequence (later phase drive",
  "activities": [
   "Boiler feed pump erection",
   "Commissioning of installed pumps"
  ],
  "rels": [
   [
    1,
    0
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN9",
  "intent": "FN",
  "rule": "R3 out_of_sequence (cross-system enabler",
  "activities": [
   "Pump foundation concrete",
   "Pump erection and alignment",
   "Transformer energization",
   "Pump commissioning",
   "Pump trial run and start-up",
   "Instrument installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    3
   ],
   [
    2,
    3
   ],
   [
    3,
    4
   ],
   [
    4,
    5
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN10",
  "intent": "FN",
  "rule": "R5 missing_interface (equipment set with",
  "activities": [
   "Coal stockpile formation and grading",
   "Boiler feed pump installation"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": null,
  "fires_now": false
 },
 {
  "id": "r2-FN11",
  "intent": "FN",
  "rule": "R1 missing_interface (a system's commiss",
  "activities": [
   "Common site enabling milestone",
   "Fire pump energization",
   "Chiller installation",
   "Chiller commissioning",
   "Transformer delivery to site"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    0,
    2
   ],
   [
    1,
    3
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN12",
  "intent": "FN",
  "rule": "R5 (missing_interface, rotating_equipmen",
  "activities": [
   "Sheet Pile Cofferdam to Wet Well",
   "Wet Well Bulk Excavation",
   "Submersible Pump Installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": false
 },
 {
  "id": "r2-FN13",
  "intent": "FN",
  "rule": "R4/R2 (out_of_sequence, rotating_equipme",
  "activities": [
   "Chemical Dosing Pump Commissioning",
   "Chemical Dosing Pump Performance Test Post-Installation",
   "Chemical Dosing Pump Alignment",
   "Chemical Dosing Pump Foundation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    3,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN14",
  "intent": "FN",
  "rule": "R1",
  "activities": [
   "Temporary construction power energization",
   "Chiller unit installation",
   "Chilled water system flushing",
   "Chiller plant commissioning",
   "MV switchgear installation",
   "Data hall busway installation",
   "AHU installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    2,
    3
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN15",
  "intent": "FN",
  "rule": "R1",
  "activities": [
   "AHU energization",
   "Diesel fire pump installation",
   "Fire pump commissioning",
   "MV switchgear installation",
   "Sprinkler system installation",
   "AHU installation",
   "Chilled water piping installation"
  ],
  "rels": [
   [
    1,
    2
   ],
   [
    0,
    2
   ],
   [
    4,
    1
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN16",
  "intent": "FN",
  "rule": "R4",
  "activities": [
   "MV switchgear energization",
   "Post-installation commissioning of chillers",
   "Chiller unit installation",
   "AHU installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN17",
  "intent": "FN",
  "rule": "R4 / R2 out_of_sequence (testing precede",
  "activities": [
   "Traction Switchgear Installation",
   "Testing of Installed Traction Switchgear",
   "MV Switchgear Installation",
   "MV Switchgear Insulation Resistance Test",
   "Cable Tray Installation",
   "Earthing Installation"
  ],
  "rels": [
   [
    1,
    0
   ],
   [
    3,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN18",
  "intent": "FN",
  "rule": "R3 out_of_sequence (cross-system enabler",
  "activities": [
   "Cable Tray Installation",
   "Commissioning of Installed Platform Lighting",
   "Luminaire Installation",
   "Cable Pulling Works"
  ],
  "rels": [
   [
    1,
    0
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN19",
  "intent": "FN",
  "rule": "R5 missing_interface (equipment set with",
  "activities": [
   "Container Yard Apron Pad Casting",
   "Quay Crane Equipment Erection",
   "Quay Crane Load Test",
   "Reefer Power Distribution Board Installation",
   "Container Yard Lighting Installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN20",
  "intent": "FN",
  "rule": "R1 missing_interface (MEP testing/commis",
  "activities": [
   "Traction Power Substation Energization",
   "Station Fit-Out Completion Milestone",
   "Fire Pump Commissioning",
   "Fire Sprinkler Installation"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    1,
    2
   ],
   [
    3,
    2
   ]
  ],
  "wrong_kind": null,
  "fires_now": false
 },
 {
  "id": "r2-FN21",
  "intent": "FN",
  "rule": "R5",
  "activities": [
   "Booster pump installation",
   "Floor tile grouting to lobby"
  ],
  "rels": [
   [
    1,
    0
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN22",
  "intent": "FN",
  "rule": "R1",
  "activities": [
   "Main switchgear energization",
   "Chiller installation",
   "Chiller commissioning",
   "Cooling tower installation",
   "Cooling tower commissioning"
  ],
  "rels": [
   [
    0,
    2
   ],
   [
    1,
    2
   ],
   [
    3,
    4
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN23",
  "intent": "FN",
  "rule": "R1",
  "activities": [
   "Fire pump energization",
   "Fire pump commissioning",
   "Main LV switchgear installation",
   "Chiller installation",
   "Chiller commissioning"
  ],
  "rels": [
   [
    0,
    1
   ],
   [
    3,
    4
   ],
   [
    0,
    4
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 },
 {
  "id": "r2-FN24",
  "intent": "FN",
  "rule": "R7",
  "activities": [
   "Chilled water pipe insulation",
   "Central plant start-up and trial run"
  ],
  "rels": [
   [
    0,
    1
   ]
  ],
  "wrong_kind": null,
  "fires_now": true
 }
]
""")

_FP = [c for c in CASES if c["intent"] == "FP"]
_FN_FIRE = [c for c in CASES if c["intent"] == "FN" and c["fires_now"]]
_FN_SILENT = [c for c in CASES if c["intent"] == "FN" and not c["fires_now"]]


@pytest.mark.parametrize("case", _FP, ids=[c["id"] for c in _FP])
def test_no_false_positive(case):
    """A legitimate schedule must not fire the wrong finding it was built to provoke."""
    kinds = {f["kind"] for f in _run(case)}
    assert case["wrong_kind"] not in kinds, (
        f"{case['id']} ({case['rule']}): false positive - engine fired "
        f"{case['wrong_kind']} on a legitimate, buildable schedule")


@pytest.mark.parametrize("case", _FN_FIRE, ids=[c["id"] for c in _FN_FIRE])
def test_real_defect_still_caught(case):
    """A real constructability defect the engine catches must keep firing."""
    assert _run(case), (
        f"{case['id']} ({case['rule']}): regression - a real defect the engine used to "
        f"catch now fires nothing")


@pytest.mark.parametrize("case", _FN_SILENT, ids=[c["id"] for c in _FN_SILENT])
@pytest.mark.xfail(reason="conservative miss - acceptable per binding insufficient-evidence rule", strict=False)
def test_conservative_miss_documented(case):
    assert _run(case)


def test_battery_scale():
    assert len(_FP) == 50 and len(_FN_FIRE) + len(_FN_SILENT) == 41
