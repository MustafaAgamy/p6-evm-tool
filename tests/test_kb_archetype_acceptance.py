"""Archetype acceptance — the KB is an OPERATIONAL, project-aware, archetype-specific
intelligence layer, not a static rule library (Ibrahim's binding acceptance criterion).

Runs the WHOLE pipeline (tag → resolve archetype → applicable KB knowledge → rules →
findings) across the full KB coverage and proves:

  1. the uploaded schedule is the source of truth — every finding is evidenced by an
     activity/system that is actually in THAT schedule (no generalization across types);
  2. the applicable knowledge is archetype-specific — the resolution exposes the systems,
     commissioning focus and relevant patterns for the type it identified;
  3. the analysis genuinely CHANGES by project type — a civil-led type and an MEP-heavy
     type get different applicable systems and different findings, not one-size rules;
  4. uncertain input is handled conservatively — an unclassifiable schedule resolves with
     low confidence / ambiguous and the engine invents no findings.

The R1–R7 validation gate (test_kb_findings*.py) is unchanged; this is an ADDITIONAL
acceptance layer over the same engine.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(__file__))   # so the resolver-battery schedules import

from p6_kb.findings import generate_findings
from p6_kb.resolve import resolve
from p6_kb.tagging import tag_view
from test_kb_resolve_validation import CASES


def _view(names, rels=()):
    oid = [{'object_id': f'O{i}', 'id': f'A{i:03d}', 'name': n, 'wbs_path': '',
            'activity_codes': {}, 'task_type': 'Task'} for i, n in enumerate(names)]
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


def _tagged_systems(view):
    return {(a.get('identity') or {}).get('system') for a in view['activities_oid']} - {None}


# ── 1. every finding is evidenced by the uploaded schedule (no cross-type leak) ──

def test_every_finding_system_belongs_to_its_own_schedule():
    """Across the full KB coverage, a finding never references a system that is not in
    the schedule it was produced from — the XER is the source of truth."""
    leaks = []
    for label, _accept, names in CASES:
        view = _view(names)
        tagged = _tagged_systems(view)
        for f in generate_findings(view, resolve(view)):
            s = f.get('system')
            if s is not None and s not in tagged:
                leaks.append((label, s, tagged))
    assert not leaks, f"finding referenced a system outside its own schedule: {leaks[:3]}"


# ── 2. applicable knowledge is archetype-specific ──

def test_resolution_exposes_archetype_specific_knowledge():
    """A confidently resolved schedule carries the archetype's own applicable knowledge:
    its focus systems, the relevant System Patterns present, and its commissioning focus —
    the intelligence the engine will apply, drawn from the identified type."""
    checked = 0
    for label, _accept, names in CASES:
        r = resolve(_view(names))
        if not r or r.get('confidence') == 'low':
            continue
        checked += 1
        assert r.get('primary_systems'), f"{label}: resolved type carries no focus systems"
        assert r.get('present_systems'), f"{label}: no systems detected in the schedule"
        # the relevant patterns the engine will reason over are the archetype's, and at
        # least one is actually present in this schedule
        assert any(p['present'] for p in r.get('relevant_patterns', [])), \
            f"{label}: none of the archetype's systems are present"
    assert checked >= 15, "expected most of the coverage to resolve confidently"


# ── 3. the analysis changes by project type (not a static library) ──

_PROCESS = ['Pipe Rack Steel Erection', 'Process Piping Spool Fabrication', 'Pressure Vessel Installation',
            'Centrifugal Pump Installation', 'Hydrotest of Piping Systems', 'DCS Cabinet Installation',
            'Pre-Commissioning of Process Units', 'Start-Up and Performance Test']
_ROADS = ['Site Clearance and Earthworks', 'Subgrade Preparation', 'Subbase and Roadbase Layers',
          'Asphalt Binder Course', 'Asphalt Wearing Course', 'Kerbs and Footpath',
          'Stormwater Drainage Network', 'Road Marking and Signage', 'Road Opening to Traffic']
_INDUSTRIAL_ONLY = {'piping', 'rotating_equipment', 'process_equipment', 'tanks_vessels', 'instrumentation'}


def test_applicable_systems_differ_between_civil_led_and_mep_heavy():
    """A roads project and a process plant resolve to different types AND expose different
    applicable systems — the intelligence layer is project-aware, not one-size."""
    proc = resolve(_view(_PROCESS))
    road = resolve(_view(_ROADS))
    assert proc and road
    assert proc['archetype'] != road['archetype']
    proc_sys, road_sys = set(proc['present_systems']), set(road['present_systems'])
    # the process plant carries the industrial MEP systems; the road does not
    assert proc_sys & _INDUSTRIAL_ONLY, 'process plant should detect industrial systems'
    assert not (road_sys & _INDUSTRIAL_ONLY), 'a road must not pull in industrial-plant systems'


def test_findings_do_not_generalize_across_unrelated_types():
    """A civil-led road schedule (with logic links) must not receive process-plant
    findings — no piping-hydrotest / equipment-foundation / commissioning findings for a
    project that has none of those systems."""
    view = _view(_ROADS, rels=[(i, i + 1) for i in range(len(_ROADS) - 1)])
    systems = {f.get('system') for f in generate_findings(view, resolve(view))}
    assert not (systems & _INDUSTRIAL_ONLY), \
        f"road schedule received findings for industrial systems it does not contain: {systems}"


# ── 4. conservative on the unknown ──

def test_unclassifiable_schedule_is_conservative():
    """A schedule of generic management activities carries no project-type signal — the
    engine must resolve nothing confident and invent no findings rather than guess."""
    view = _view(['General Administration', 'Weekly Progress Meeting', 'Monthly Report',
                  'Document Control', 'Site Mobilisation'])
    r = resolve(view)
    if r is not None:
        assert r.get('confidence') == 'low' or r.get('ambiguous'), \
            'a no-signal schedule must not be presented as a confident classification'
    assert generate_findings(view, r) == [], 'no findings may be invented on a no-signal schedule'
