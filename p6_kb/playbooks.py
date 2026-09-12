"""Project Type Playbooks — assemble the KB into a project-type-first reference.

Each archetype in ``knowledge_base/archetypes.json`` becomes a **Playbook**:
an overview, a step-by-step construction sequence composed from its system
patterns, a suggested WBS (from the legacy curated standard where one exists,
which is also what the downloadable baseline file is generated from), a
baseline-file availability flag, cross-discipline hold points, a commissioning
ladder, and evidence/provenance.

Project-type-first and reference-only: no score, no verdict, no percent meter.
Deterministic, offline, stdlib-only. Honest coverage using the 5-state status
vocabulary from :mod:`p6_kb.reference`; a thin/absent area reads as
``not_assessed``/``insufficient_evidence``, never as approval.
"""
import re

from . import kb, reference
from .patterns import load_archetypes, load_system_patterns

# ── sector taxonomy: fold the inconsistent raw categories into ~8 sectors ──
SECTORS = [
    ('oil_gas_process', 'Oil, Gas & Process'),
    ('power_energy', 'Power & Energy'),
    ('water', 'Water'),
    ('industrial', 'Industrial & Manufacturing'),
    ('buildings', 'Buildings'),
    ('residential', 'Residential'),
    ('transport_marine', 'Transport & Marine'),
    ('critical', 'Critical Facilities'),
]
SECTOR_LABEL = dict(SECTORS)

_SECTOR_BY_ID = {
    'process_oil_gas': 'oil_gas_process', 'chemical_petrochemical': 'oil_gas_process',
    'lng_terminal': 'oil_gas_process', 'tank_farm': 'oil_gas_process',
    'offshore_platform': 'oil_gas_process', 'pipeline': 'oil_gas_process',
    'power_utility_plant': 'power_energy', 'solar_pv_plant': 'power_energy',
    'wind_farm': 'power_energy', 'substation_switchyard': 'power_energy',
    'district_cooling_plant': 'power_energy', 'waste_to_energy': 'power_energy',
    'utilities_network': 'power_energy',
    'water_wastewater': 'water', 'desalination_plant': 'water',
    'pumping_station': 'water', 'dam_hydraulic': 'water',
    'data_center': 'critical', 'hospital_healthcare': 'critical',
    'commercial_highrise': 'buildings', 'mall_retail': 'buildings',
    'hotel_hospitality': 'buildings', 'school_education': 'buildings',
    'university_campus': 'buildings', 'mosque_religious': 'buildings',
    'sports_stadium_arena': 'buildings', 'warehouse_logistics': 'buildings',
    'parking_structure': 'buildings',
    'residential_building': 'residential', 'apartment_building': 'residential',
    'lowrise_residential': 'residential', 'midrise_residential': 'residential',
    'highrise_residential': 'residential', 'residential_compound': 'residential',
    'townhouse': 'residential', 'villa': 'residential',
    'standalone_house': 'residential', 'mixed_use_residential': 'residential',
    'rail_metro': 'transport_marine', 'metro_station': 'transport_marine',
    'railway_track_systems': 'transport_marine', 'roads_highways': 'transport_marine',
    'bridges': 'transport_marine', 'tunnels': 'transport_marine',
    'airport_terminal': 'transport_marine', 'airport_airside': 'transport_marine',
    'seaport_container_terminal': 'transport_marine',
    'seaport_bulk_terminal': 'transport_marine', 'marine_jetty_quay': 'transport_marine',
    'infrastructure': 'transport_marine',
    'industrial_factory': 'industrial', 'manufacturing_plant': 'industrial',
    'silo_grain_terminal': 'industrial', 'cold_storage': 'industrial',
    'cement_plant': 'industrial', 'steel_plant': 'industrial',
    'mining_processing': 'industrial', 'pharmaceutical_plant': 'industrial',
    'food_beverage_plant': 'industrial', 'pulp_paper': 'industrial',
    'glass_plant': 'industrial',
}
_SECTOR_BY_CATEGORY = {
    'industrial_process': 'oil_gas_process', 'industrial_energy': 'power_energy',
    'industrial_utility': 'water', 'industrial_manufacturing': 'industrial',
    'industrial_bulk_handling': 'industrial', 'industrial': 'industrial',
    'infrastructure_transit': 'transport_marine', 'transport_infrastructure': 'transport_marine',
    'marine_ports': 'transport_marine', 'aviation': 'transport_marine',
    'infrastructure_civil': 'transport_marine', 'water_infrastructure': 'water',
    'water': 'water', 'utility_infrastructure': 'power_energy',
    'critical_facility': 'critical', 'building_vertical': 'buildings',
    'buildings': 'buildings', 'energy': 'power_energy', 'residential': 'residential',
}


def _sector_of(a):
    return (_SECTOR_BY_ID.get(a.get('archetype'))
            or _SECTOR_BY_CATEGORY.get((a.get('category') or '').lower())
            or _SECTOR_BY_CATEGORY.get(a.get('category'))
            or 'buildings')


# ── construction macro-phases (a typical EPC spine; labelled typical) ──
PHASES = [
    {'key': 'eng', 'name': 'Engineering & Procurement',
     'desc': 'Complete detailed design and place the long-lead equipment and material orders that set the pace of the programme.'},
    {'key': 'enabling', 'name': 'Site Enabling & Civil',
     'desc': 'Site clearance, earthworks, temporary works, underground services and duct banks.'},
    {'key': 'foundations', 'name': 'Foundations & Substructure',
     'desc': 'Foundations, equipment bases and plinths, containment/bunds and below-ground structure.'},
    {'key': 'structure', 'name': 'Superstructure & Structure',
     'desc': 'Erect the structural frame / steel and the building superstructure.'},
    {'key': 'envelope', 'name': 'Envelope & Architecture',
     'desc': 'Cladding, roofing, blockwork and the architectural build (where applicable).'},
    {'key': 'equipment', 'name': 'Equipment Setting',
     'desc': 'Set the major mechanical, electrical and process equipment on their prepared bases.'},
    {'key': 'mep', 'name': 'Bulk MEP & Systems',
     'desc': 'Install piping, ducting, cabling, containment and the discipline systems, then rough-in and fit-out.'},
    {'key': 'testing', 'name': 'Testing & Pre-commissioning',
     'desc': 'Flushing, pressure and leak testing, point-to-point checks, loop checks and pre-functional tests.'},
    {'key': 'commissioning', 'name': 'Commissioning & Handover',
     'desc': 'Functional and integrated commissioning, performance / reliability testing and handover.'},
]
_PHASE_ORDER = [p['key'] for p in PHASES]

# each known system pattern -> its primary construction phase
_SYSTEM_PHASE = {
    'local_fabrication': 'eng', 'pipe_spool_fabrication': 'eng',
    'civil_interface': 'foundations', 'earthing': 'foundations',
    'structural_steel': 'structure', 'pipe_racks': 'structure',
    'waterproofing': 'envelope', 'architectural_finishing': 'envelope',
    'floor_tiling_stone': 'envelope', 'joinery_fitout': 'envelope',
    'sanitary_fixtures': 'envelope',
    'mechanical_equipment': 'equipment', 'rotating_equipment': 'equipment',
    'process_equipment': 'equipment', 'tanks_vessels': 'equipment',
    'skids_packaged': 'equipment', 'conveying': 'equipment',
    'process_piping': 'mep', 'utility_piping': 'mep', 'plumbing': 'mep',
    'chilled_water': 'mep', 'hvac': 'mep', 'utilities': 'mep',
    'insulation_coating': 'mep', 'electrical_power': 'mep', 'lighting': 'mep',
    'containment_cabling': 'mep', 'instrumentation': 'mep', 'bms': 'mep',
    'fire_alarm': 'mep', 'fire_fighting': 'mep',
    'commissioning': 'commissioning',
}
_DISC_PHASE = {
    'CIVIL': 'foundations', 'STRUCT': 'structure', 'FINISHES': 'envelope',
    'MECH': 'mep', 'ELEC': 'mep', 'ELV': 'mep', 'PIPING': 'mep', 'INSTR': 'mep',
    'PLUMB': 'mep', 'FIRE': 'mep', 'PROCESS': 'equipment', 'UTIL': 'mep',
}
# generic hold-point notes, universal enough to be honest across project types
_PHASE_GATE = {
    'foundations': 'Equipment anchor bolts set and surveyed to tolerance before the steel or equipment they carry.',
    'structure': 'Foundations cured and released before structural erection.',
    'mep': 'Earthing / bonding proven before energizing electrical systems.',
    'testing': 'Systems mechanically complete before pressure / functional testing.',
    'commissioning': 'Pre-commissioning and point-to-point complete before functional and integrated commissioning.',
}


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '_', (text or '').lower()).strip('_')


def _first_sentence(text, limit=150):
    t = ' '.join(str(text or '').split())
    if not t:
        return ''
    m = re.search(r'[.;]', t)
    s = t[:m.start()] if m else t
    if len(s) > limit:
        s = s[:limit].rstrip() + '…'
    return s


def _legacy_by_slug(kb_entries=None):
    """Map slug(type) -> legacy curated entry (the WBS + baseline source)."""
    if kb_entries is None:
        kb_entries = kb.load_kb()
    vals = kb_entries.values() if isinstance(kb_entries, dict) else kb_entries
    out = {}
    for entry in vals:
        out[_slug(entry.get('type'))] = entry
    return out


def _entry_for(a, legacy):
    return legacy.get(_slug(a.get('archetype'))) or legacy.get(_slug(a.get('name')))


def _coverage(prim, sec, entry):
    n = len(prim) + len(sec)
    seq = 'knowledge_available' if n >= 3 else ('potentially_relevant' if n else 'not_assessed')
    if entry:
        wbs = 'knowledge_available'
    elif n:
        wbs = 'potentially_relevant'
    else:
        wbs = 'not_assessed'
    return [
        {'area': 'Sequence', 'status': seq},
        {'area': 'WBS', 'status': wbs},
        {'area': 'Baseline file', 'status': 'knowledge_available' if entry else 'not_assessed'},
        {'area': 'Learned', 'status': 'not_assessed'},
    ]


def library(patterns=None, archetypes=None, kb_entries=None):
    """The shelf: every project type as a card, grouped into sectors."""
    if archetypes is None:
        archetypes = load_archetypes()
    if patterns is None:
        patterns = load_system_patterns()
    legacy = _legacy_by_slug(kb_entries)

    cards = []
    for a in archetypes.values():
        prim = [s for s in (a.get('primary_systems') or []) if s in patterns]
        sec = [s for s in (a.get('secondary_systems') or []) if s in patterns]
        entry = _entry_for(a, legacy)
        sector = _sector_of(a)
        cards.append({
            'archetype': a.get('archetype'),
            'name': a.get('name'),
            'sector': sector,
            'sector_label': SECTOR_LABEL.get(sector),
            'driver': _first_sentence(a.get('notes')),
            'system_count': len(prim) + len(sec),
            'primary_count': len(prim),
            'wbs_count': len(entry.get('wbs') or []) if entry else 0,
            'baseline_available': bool(entry),
            'coverage': _coverage(prim, sec, entry),
        })

    sectors = []
    for key, label in SECTORS:
        items = sorted([c for c in cards if c['sector'] == key], key=lambda c: c['name'])
        if items:
            sectors.append({'key': key, 'label': label, 'count': len(items), 'types': items})
    return {'sectors': sectors,
            'counts': {'types': len(cards), 'sectors': len(sectors)}}


def _sysinfo(sid, patterns, is_primary):
    p = patterns[sid]
    disc = p.get('discipline')
    return {'system': sid, 'name': p.get('name') or sid, 'discipline': disc,
            'discipline_label': reference.discipline_label(disc), 'primary': is_primary}


def _phase_of(system):
    return (_SYSTEM_PHASE.get(system['system'])
            or _DISC_PHASE.get((system['discipline'] or '').upper()) or 'mep')


def _sequence_steps(systems):
    """Compose the archetype's systems into an ordered, step-by-step spine.

    Each macro-phase that has active systems becomes a step, listing the
    disciplines/systems active and any generic gate. Engineering & Procurement
    and Commissioning are always shown (they bookend every project)."""
    by_phase = {k: [] for k in _PHASE_ORDER}
    for s in systems:
        by_phase[_phase_of(s)].append(s)
    # seed Engineering & Procurement with the primary systems (long-lead)
    if not by_phase['eng']:
        by_phase['eng'] = [s for s in systems if s['primary']] or systems[:4]

    steps = []
    for p in PHASES:
        active = by_phase[p['key']]
        if not active and p['key'] not in ('eng', 'commissioning'):
            continue
        steps.append({
            'name': p['name'], 'key': p['key'], 'desc': p['desc'],
            'disciplines': sorted({s['discipline_label'] for s in active}),
            'systems': [s['name'] for s in active],
            'gate': _PHASE_GATE.get(p['key'], ''),
        })
    for i, s in enumerate(steps, start=1):
        s['n'] = i
    return steps


def _hold_points(systems, archetype, patterns, limit=14):
    """Cross-discipline gates from the systems' relationships + interfaces, plus
    the archetype's civil interfaces. Reference only — never a finding."""
    out, seen = [], set()

    def add(before, after, reason, typ, phase, strength):
        key = (before, after)
        if not before or not after or key in seen:
            return
        seen.add(key)
        out.append({'before': before, 'after': after, 'reason': reason or '',
                    'type': typ or '', 'phase': phase or '',
                    'strength': strength or '', 'grade': reference.evidence_grade(strength)})

    for s in systems:
        det = reference.pattern_detail(s['system'], patterns) or {}
        for r in det.get('relationships', []):
            if (r.get('strength') or '').lower() == 'strong':
                add(r.get('before'), r.get('after'), r.get('reason'), 'sequence',
                    s['discipline_label'], r.get('strength'))
        for it in det.get('interfaces', []):
            if (it.get('strength') or '').lower() in ('strong', 'moderate'):
                add(it.get('with_name'), s['name'], it.get('requirement'),
                    it.get('type'), it.get('phase'), it.get('strength'))
    for civ in (archetype.get('civil_interfaces') or []):
        add('Civil / structural provision', civ, 'Civil interface that must be in place first',
            'enabler', 'Foundations', 'strong')

    out.sort(key=lambda h: 0 if (h['strength'] or '').lower() == 'strong' else 1)
    return out[:limit]


def _commissioning(systems, archetype, patterns):
    """The commissioning ladder: the archetype's commissioning focus as ordered
    rungs, plus a pooled list of the systems' testing requirements."""
    rungs = [{'title': f, 'gates': []} for f in (archetype.get('commissioning_focus') or [])]
    tests, seen = [], set()
    for s in systems:
        det = reference.pattern_detail(s['system'], patterns) or {}
        for t in det.get('testing_requirements', []):
            k = t.strip().lower()
            if k and k not in seen:
                seen.add(k)
                tests.append(t)
    return {'rungs': rungs, 'testing_requirements': tests[:24]}


def _wbs(entry, systems):
    """The suggested WBS. Prefer the legacy curated ``wbs[]`` (which is exactly
    what the downloadable baseline file is generated from — screen == file);
    otherwise compose a branch per discipline from the systems."""
    if entry and entry.get('wbs'):
        branches = [{'code': f'WBS{i:02d}', 'name': w.get('name'),
                     'keywords': list(w.get('keywords') or [])}
                    for i, w in enumerate(entry['wbs'], start=1)]
        return {'source': 'curated', 'source_label': 'Curated standard',
                'note': 'This is the WBS inside the downloadable baseline file — what you see is what you get.',
                'branches': branches}
    seen, branches, i = set(), [], 0
    for s in systems:
        d = s['discipline_label']
        if d in seen:
            continue
        seen.add(d)
        i += 1
        branches.append({'code': f'WBS{i:02d}', 'name': d, 'keywords': []})
    return {'source': 'composed', 'source_label': 'Composed from systems',
            'note': 'Composed from the disciplines present — adapt to your own P6 standard.',
            'branches': branches}


def playbook(archetype_id, patterns=None, archetypes=None, kb_entries=None):
    """The full dossier for one project type, or ``None`` for an unknown id."""
    if archetypes is None:
        archetypes = load_archetypes()
    if patterns is None:
        patterns = load_system_patterns()
    a = archetypes.get(archetype_id)
    if not a:
        return None
    legacy = _legacy_by_slug(kb_entries)
    entry = _entry_for(a, legacy)

    prim = [s for s in (a.get('primary_systems') or []) if s in patterns]
    sec = [s for s in (a.get('secondary_systems') or []) if s in patterns]
    systems = ([_sysinfo(s, patterns, True) for s in prim]
               + [_sysinfo(s, patterns, False) for s in sec])

    mix = {}
    for s in systems:
        mix[s['discipline_label']] = mix.get(s['discipline_label'], 0) + (2 if s['primary'] else 1)
    disc_mix = sorted(({'label': k, 'weight': v} for k, v in mix.items()),
                      key=lambda x: (-x['weight'], x['label']))

    detail = []
    for s in systems:
        det = reference.pattern_detail(s['system'], patterns) or {}
        detail.append({'system': s['system'], 'name': s['name'],
                       'discipline_label': s['discipline_label'], 'primary': s['primary'],
                       'stages': [st.get('stage') for st in det.get('sequence', [])]})

    sector = _sector_of(a)
    return {
        'archetype': archetype_id,
        'name': a.get('name'),
        'sector': sector,
        'sector_label': SECTOR_LABEL.get(sector),
        'overview': {
            'notes': a.get('notes') or '',
            'driver': _first_sentence(a.get('notes')),
            'civil_interfaces': list(a.get('civil_interfaces') or []),
            'commissioning_focus': list(a.get('commissioning_focus') or []),
            'primary_systems': [s for s in systems if s['primary']],
            'secondary_systems': [s for s in systems if not s['primary']],
            'discipline_mix': disc_mix,
        },
        'sequence': {'phases': PHASES, 'steps': _sequence_steps(systems), 'detail': detail},
        'wbs': _wbs(entry, systems),
        'baseline': {
            'available': bool(entry),
            'type': entry.get('type') if entry else None,
            'wbs_count': len(entry.get('wbs') or []) if entry else 0,
            'activity_count': len(entry.get('activities') or []) if entry else 0,
            'milestones': list(entry.get('milestones') or []) if entry else [],
        },
        'hold_points': _hold_points(systems, a, patterns),
        'commissioning': _commissioning(systems, a, patterns),
        'evidence': {
            'patterns': [{'system': s['system'], 'name': s['name'],
                          'status': 'curated', 'source': 'system_pattern'} for s in systems],
            'status_vocab': reference.STATUS_VOCAB,
        },
        'coverage': _coverage(prim, sec, entry),
    }
