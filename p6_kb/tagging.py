"""Multi-signal identity tagger for the MEP-first constructability engine.

Assigns every activity a ``(discipline, system, phase, zone)`` with a
**confidence**, combining *all* available signals — activity-code values, name
keywords, and WBS path — so it works even when a schedule has no clean discipline
code (real P6 files vary: one codes "Type of Works", another "Trade", another a
clean "HVAC Works Category"). The lexicons are **generalized construction/MEP/
industrial terminology**, never project-specific names, so the same tagger works
on structurally different projects. Deterministic and offline.

Design (per the binding redesign spec):
  * discipline is recovered from code *values* (any dimension) first — the most
    reliable signal across P6 conventions — then corroborated / refined by name;
  * system is the finer MEP/industrial classification, mostly name-driven;
  * civil/structural work is tagged only coarsely and only matters where it forms
    an MEP interface;
  * confidence reflects how many independent signals agree, and ambiguous cases
    are flagged rather than forced.
"""
import re

# ── canonical construction phase model (shared vocabulary, ranked) ──────────
PHASES = [
    'DESIGN', 'PROCUREMENT', 'FABRICATION', 'DELIVERY', 'CIVIL_INTERFACE',
    'ROUGH_IN', 'ERECTION_INSTALL', 'MECHANICAL_COMPLETION', 'INSULATION',
    'POWER_AVAILABLE', 'PRE_COMMISSIONING', 'TESTING', 'COMMISSIONING',
    'INTEGRATED_TESTING', 'PERFORMANCE', 'STARTUP', 'HANDOVER',
]
PHASE_RANK = {p: i for i, p in enumerate(PHASES)}

# most-specific / latest phase first — the tagger takes the highest-rank match
_PHASE_KW = [
    ('HANDOVER', ['handing over', 'hand over', 'handover', 'taking over', 'de-snag', 'de snag', 'close out', 'closeout', 'snagging']),
    ('STARTUP', ['start-up', 'start up', 'startup', 'first fire', 'light-up', 'light up', 'first product', 'first batch', 'trial run', 'trial production']),
    ('PERFORMANCE', ['performance test', 'reliability test', 'reliability run', 'guarantee test', 'capacity test']),
    ('INTEGRATED_TESTING', ['integrated test', 'integration test', 'site acceptance', ' sat ', 'end-to-end', 'end to end', 'functional test', 'functional check']),
    ('PRE_COMMISSIONING', ['pre-commission', 'precommission', 'pre commission', 'cold commission', 'flushing', 'air blowing', 'loop test', 'loop check']),
    ('COMMISSIONING', ['commissioning', 'commission']),
    ('POWER_AVAILABLE', ['energization', 'energisation', 'energize', 'energise', 'charging', 'power on', 'first power', 'permanent power']),
    ('TESTING', ['hydrotest', 'hydro test', 'pressure test', 'leak test', 'pneumatic test', ' ndt', 'radiograph', 'megger', 'insulation resistance', 'ir test', 'hi-pot', 'continuity test', 'test and balance', 'testing & balancing', ' tab ', 'factory acceptance', ' fat', 'testing', ' test']),
    ('INSULATION', ['insulation', 'lagging']),
    ('MECHANICAL_COMPLETION', ['mechanical completion', ' mc ', 'punch list', 'punch']),
    ('ERECTION_INSTALL', ['erection', 'installation', 'install', 'fixing', 'laying', 'cable pulling', 'termination', 'glanding', 'alignment', 'grouting', 'mounting', 'assembly', 'erect']),
    ('ROUGH_IN', ['first fix', 'rough-in', 'rough in', 'embedded', 'sleeve', 'conduit', 'builders work', 'builder work', 'opening', 'second fix']),
    ('CIVIL_INTERFACE', ['foundation', 'plinth', 'pedestal', 'housekeeping pad', 'trench', 'duct bank']),
    ('DELIVERY', ['delivery', 'deliver', 'received', 'receive', 'shipment', 'on site', 'transport']),
    ('FABRICATION', ['fabrication', 'fabricate', 'spool', 'prefab', 'pre-assembly', 'preassembly', 'workshop', 'shop fabrication']),
    ('PROCUREMENT', ['procurement', 'procure', 'purchase order', 'purchase', 'long lead', 'manufacturing', 'manufacture', 'p.o', 'material supply']),
    ('DESIGN', ['submittal', 'submital', 'approval', 'shop drawing', ' ifc', 'detailing', 'design', 'method statement', 'material approval']),
]

# ── discipline recovered from CODE VALUES (any dimension) — the strong signal ─
# generalized value fragments → discipline. Matched as substrings on code values.
_DISCIPLINE_VALUE = [
    ('PIPING', ['piping', 'pipe work', 'pipe erection', 'spool']),
    ('MECH', ['hvac', 'ventilation', 'mechanical vent', 'air condition']),   # HVAC is a MECH system
    ('PLUMB', ['plumbing', 'drainage', 'sanitary', 'water works']),
    ('FIRE', ['fire fighting', 'firefighting', 'fire &', 'fire and gas', 'fire alarm']),
    ('INSTR', ['instrument', 'instrumentation', ' i&c', 'control &']),
    ('ELEC', ['electrical', 'cable erection', 'cable work', 'power work', 'lv work', 'mv work']),
    ('MECH', ['mechanical', 'equipment work', 'equipment install', 'rotating', 'static equipment']),
    ('STRUCT', ['steel', 'structur']),
    ('FINISHES', ['finish', 'architect', 'arc.', 'arch ', 'painting', 'plaster', 'masonry', 'blockwork']),
    ('CIVIL', ['civil', 'concrete', 'infrastructure', 'excavation', 'earthwork', 'foundation']),
]

# ── system lexicon: (system, discipline, keywords, excludes) ─────────────────
# keywords match on activity name (and WBS). Order = more specific first.
_SYSTEMS = [
    # ── specific MEP systems first (their keywords beat the generic equipment ones) ──
    ('chilled_water', 'MECH', ['chiller', 'chilled water', ' chw', 'cooling tower', 'condenser water'], []),
    ('hvac', 'MECH', ['hvac', ' ahu', 'air handling', ' fcu', 'fan coil', 'ventilation', 'ductwork', 'duct work', 'exhaust fan', 'refrigerant', 'air coil', 'metal duct', 'vrf', 'split unit', 'fresh air'], ['production', 'conductor', 'viaduct', 'aqueduct']),
    ('plumbing', 'PLUMB', ['plumbing', 'drainage', 'sewage', 'sanitary', 'domestic water', 'soil pipe', 'waste pipe', 'storm water', 'potable water', 'water supply network'], []),
    ('fire_fighting', 'FIRE', ['fire fighting', 'firefighting', 'fire pump', 'sprinkler', 'fire hydrant', 'wet riser', 'dry riser', 'fm200', 'fm-200', 'deluge', 'foam system', 'hose reel', 'gas suppression'], []),
    ('fire_alarm', 'FIRE', ['fire alarm', 'smoke detector', 'fire detection', 'fire & gas', 'fire and gas', 'gas detection', 'manual call point', 'f&g'], []),
    ('containment_cabling', 'ELEC', ['cable tray', 'cable ladder', 'cable containment', 'cable trunking', 'cable pulling', 'cable laying', 'cable termination', 'cable erection', 'glanding', 'wiring'], []),
    ('earthing', 'ELEC', ['earthing', 'earth pit', 'grounding', 'lightning protection', ' lps', 'earth mat', 'bonding'], ['stray current']),
    ('lighting', 'ELEC', ['lighting', 'luminaire', 'light fixture', 'light fitting', 'emergency light', 'street light', 'flood light'], ['lightweight', 'light weight', 'lightning']),
    ('electrical_power', 'ELEC', ['transformer', 'substation', 'switchgear', ' mdb', ' smdb', 'distribution board', 'power panel', 'busbar', 'busway', 'busduct', 'low voltage', 'medium voltage', ' lv ', ' mv ', 'power cable', 'generator', 'genset', ' ups', 'electrical installation', 'electrical works', 'panel board'], ['stray current']),
    ('instrumentation', 'INSTR', ['instrument', 'instrumentation', 'instrument cable', 'tubing', 'transmitter', 'calibration', 'control valve', 'field instrument', 'analyzer', 'flow meter'], []),
    ('bms', 'ELV', ['bms', 'building management', ' dcs', ' scada', ' plc', 'control system', 'automation system', 'graphics'], []),
    ('elv_security', 'ELV', ['cctv', 'access control', 'security system', 'intercom', 'ip camera', 'surveillance', 'public address', ' pa system'], []),
    ('data_telecom', 'ELV', ['structured cabling', 'fiber optic', 'fibre optic', 'telecom', 'telephone', 'pabx', 'data cabling', 'server room'], ['road network', 'pipe network', 'water network']),
    ('conveying', 'MECH', ['conveyor', 'bucket elevator', 'chain conveyor', 'belt conveyor', 'screw conveyor', 'material handling', 'apron feeder', 'diverter', 'shuttle'], []),
    ('piping', 'PIPING', ['pipe rack', 'pipe erection', 'pipe installation', 'process pipe', 'pipe spool', 'spool fabrication', 'pipe fabrication', 'pipeline', 'welding', 'piping works', 'pipe fitting', 'process piping'], []),
    ('utilities', 'UTIL', ['compressed air', 'instrument air', 'plant air', 'process water', 'cooling water', 'raw water', 'demin water', ' steam ', 'fuel system', 'nitrogen', 'utility connection', 'utilities'], []),
    # ── generic equipment last (only fire after a specific system fails to match) ──
    ('process_equipment', 'PROCESS', ['crusher', 'ball mill', 'grinding mill', ' kiln', 'furnace', 'dust collection', 'bag filter', 'baghouse', 'cyclone', 'separator', 'classifier', 'dryer', 'batch mixer', 'reactor', 'centrifuge'], []),
    ('tanks_vessels', 'MECH', ['pressure vessel', 'storage tank', 'hopper', 'heat exchanger', 'boiler install', 'process tank', 'day tank', 'tank erection', 'tank installation'], []),
    ('rotating_equipment', 'MECH', ['pump ', ' pump', 'compressor', 'blower', 'turbine', 'fan install', 'motor install'], ['pumping station']),
    ('mechanical_equipment', 'MECH', ['mechanical installation', 'mechanical equipment', 'equipment installation', 'equipment erection', 'equipment works', 'skid ', 'package unit', 'mechanical works', 'equipment setting', 'equipment alignment'], []),
    ('structural_steel', 'STRUCT', ['structural steel', 'steel structure', 'steel erection', 'steel fabrication', 'steel works', 'pipe rack steel', 'platform', 'catwalk', 'purlin', 'girder', 'truss', 'decking', 'cladding', 'grating'], ['stainless']),
    ('civil_interface', 'CIVIL', ['equipment foundation', 'housekeeping pad', 'inertia base', 'plinth', 'pedestal', 'sleeve', 'opening', 'embedded', 'cable trench', 'duct bank', 'underground utilit', 'manhole', 'plant room', 'equipment room', 'shaft', 'anchor bolt'], []),
]

_ZONE_DIM_HINTS = ('area', 'zone', 'building', 'level', 'floor', 'silo', 'unit',
                   'block', 'tower', 'location', 'sector', 'phase name', 'grid')
_ZONE_RX = re.compile(r'\b(?:silo|building|block|tower|zone|level|area|unit|sector|grid|axis)\s*[-#]?\s*[a-z0-9]{1,4}\b', re.I)


def _norm(s):
    return ' ' + re.sub(r'\s+', ' ', (s or '').lower().strip()) + ' '


def _phase_of(text):
    """The most-ADVANCED construction phase whose keywords appear (highest
    PHASE_RANK wins, deterministically), with a guard so 'pre-/cold commissioning'
    is not swallowed by the 'commission' substring into COMMISSIONING."""
    best = None
    for phase, kws in _PHASE_KW:
        if any(k in text for k in kws):
            if best is None or PHASE_RANK[phase] > PHASE_RANK[best]:
                best = phase
    if best == 'COMMISSIONING' and any(p in text for p in ('pre-comm', 'pre comm', 'precomm', 'cold comm')):
        best = 'PRE_COMMISSIONING'
    # 'insulation' as a MODIFIER — "pipes above insulation installation", "copper pipes &
    # insulation - delivery" — must NOT promote a delivery/install activity to the late
    # INSULATION phase; that manufactured false 'later-drives-earlier' inversions on real
    # schedules. INSULATION wins only when insulating/lagging is the actual action (no
    # delivery/erection/install verb present). R6 still catches insulation-before-hydrotest
    # via activity-name keywords, so this loses no genuine coverage.
    if best == 'INSULATION' and any(k in text for k in (
            'install', 'erect', 'delivery', 'deliver', 'fabricat', 'laying', 'fixing',
            'mounting', 'supply', 'procure', 'purchase', 'order', 'p.o', 'submittal',
            'approval', 'shop drawing', 'manufactur')):
        best = None
        for phase, kws in _PHASE_KW:
            if phase == 'INSULATION':
                continue
            if any(k in text for k in kws) and (best is None or PHASE_RANK[phase] > PHASE_RANK[best]):
                best = phase
    return best


def _discipline_from_codes(codes):
    # disciplines-first so a real MEP/trade code value beats an incidental civil
    # word in a *zone/area* value (e.g. "Concrete Podium") — MEP disciplines are
    # listed before STRUCT/CIVIL in _DISCIPLINE_VALUE, so they win across all codes.
    vals = [((val or '').lower(), val) for val in (codes or {}).values()]
    for disc, frags in _DISCIPLINE_VALUE:
        for v, orig in vals:
            if any(f in v for f in frags):
                return disc, orig
    return None, None


# Generic discipline / trade words that legitimately match a system keyword on the
# ACTIVITY NAME (specific enough there) but are UNSAFE on a WBS branch or a discipline
# code value — a "Mechanical Works" WBS branch groups silo sheets, steel and civil under
# it, so tagging every child 'mechanical_equipment' mis-classifies structural/civil work
# as MEP and produces false findings. WBS/code inference must use SPECIFIC system terms.
_WBS_UNSAFE_KW = {
    'mechanical works', 'mechanical installation', 'mechanical equipment', 'mechanical work',
    'equipment installation', 'equipment erection', 'equipment works', 'equipment setting',
    'equipment alignment', 'electrical installation', 'electrical works', 'electrical work',
    'power work', 'power works', 'mechanical vent',
}


def _system_from_text(text, safe_only=False):
    """Match a system by keyword. With safe_only, GENERIC discipline words (see
    _WBS_UNSAFE_KW) are ignored so WBS/code inference tags only on specific system terms."""
    for system, disc, kws, excl in _SYSTEMS:
        use = [k for k in kws if not (safe_only and k.strip() in _WBS_UNSAFE_KW)]
        if any(k in text for k in use) and not any(e in text for e in excl):
            return system, disc
    return None, None


def _zone_of(activity):
    for dim, val in (activity.get('activity_codes') or {}).items():
        dl = dim.lower()
        if any(h in dl for h in _ZONE_DIM_HINTS) and val:
            return str(val).strip()
    m = _ZONE_RX.search(activity.get('name') or '') or _ZONE_RX.search(activity.get('wbs_path') or '')
    return m.group(0).strip() if m else None


# broad discipline for the leftover civil/finishes bulk (so nothing is 'unknown'
# just because it isn't MEP) — keeps MEP the focus while still classifying.
_CIVIL_KW = ['concrete', 'rft', 'reinforc', 'formwork', 'shutter', 'excavat', 'backfill',
             ' raft', ' slab', ' column', ' beam', 'footing', ' pile', 'blockwork', 'masonry',
             'plaster', 'painting', 'screed', 'waterproof', 'block work', 'brick', 'render',
             'tiling', 'ceiling', 'partition', 'facade', ' door ', 'window', 'finishing',
             # civil interfaces for equipment — demote "pump foundation" etc. to civil:
             'foundation', 'plinth', 'pedestal', 'anchor bolt', 'grouting', 'housekeeping pad']


_CIVIL_DISC = {'CIVIL', 'STRUCT', 'FINISHES'}
_MEP_DISC = {'MECH', 'ELEC', 'ELV', 'PIPING', 'INSTR', 'PLUMB', 'FIRE', 'PROCESS', 'UTIL'}


def tag_activity(activity):
    """Return an identity dict for one activity (from schedule_view's oid rows).

    Signal priority: a discipline recovered from code *values* is authoritative
    for civil/steel/finishes (so a system word in the zone/WBS can't promote a
    concrete activity to MEP); otherwise a system found in the *activity name*
    (name-only — the WBS/zone often just names the area) drives the tag, with the
    code discipline corroborating for confidence."""
    ntext = _norm(activity.get('name'))            # NAME only for system matching
    codes = activity.get('activity_codes') or {}

    code_disc, _code_val = _discipline_from_codes(codes)
    sys_name, sys_disc = _system_from_text(ntext)
    name_civil = any(k in ntext for k in _CIVIL_KW)

    if code_disc in _CIVIL_DISC:
        # code is explicit civil/steel/finishes → authoritative discipline; accept a
        # name system only if it agrees (e.g. structural_steel for STRUCT). Never MEP.
        discipline = code_disc
        system = sys_name if sys_disc == code_disc else None
        confidence, source = ('high' if system else 'medium'), 'code'
    elif sys_name and not (name_civil and sys_disc in _MEP_DISC):
        # a genuine MEP/industrial system named in the activity (and the name isn't
        # itself clearly a civil task like "concrete pouring for <equipment>")
        system, discipline = sys_name, sys_disc
        confidence = 'high' if code_disc == sys_disc else 'medium'
        source = 'code+name' if code_disc == sys_disc else 'name'
    elif code_disc:
        discipline, system, confidence, source = code_disc, None, 'medium', 'code'
    elif name_civil:
        discipline, system, confidence, source = 'CIVIL', None, 'low', 'name-civil'
    else:
        discipline, system, confidence, source = 'UNKNOWN', None, 'none', 'none'

    # ── recall: real schedules put the discipline/system in the WBS branch or an
    # activity code, not always the activity name. If the name gave no system — and the
    # activity is not itself a civil task and not civil-coded — fall back to the WBS path,
    # then the code values, using the SAME specific system lexicon (so an area name only
    # tags when it genuinely names a system). This never overrides a name/code system or
    # a civil discipline; it only fills in the large 'unknown' remainder. ──
    if system is None and not name_civil and code_disc not in _CIVIL_DISC:
        for src_text, tag in ((activity.get('wbs_path'), 'wbs'),
                              (' '.join(str(v) for v in codes.values()), 'codeval')):
            fsys, fdisc = _system_from_text(_norm(src_text), safe_only=True)
            if fsys:
                system = fsys
                discipline = discipline if discipline in _MEP_DISC else fdisc
                source = f'{source}+{tag}'
                confidence = 'medium' if confidence in ('low', 'none') else confidence
                break

    phase = _phase_of(ntext)   # name only — WBS summary branches (e.g. "Handing Over") pollute phase
    ambiguous = confidence in ('low', 'none') or bool(name_civil and system and sys_disc in _MEP_DISC)
    signals = [s for s, ok in (('code', code_disc), ('name', sys_name)) if ok]
    return {
        'discipline': discipline, 'system': system,
        'phase': phase, 'phase_rank': PHASE_RANK.get(phase),
        'zone': _zone_of(activity),
        'confidence': confidence, 'source': source,
        'signals': signals, 'ambiguous': bool(ambiguous),
    }


def tag_view(view):
    """Tag every activity on the ObjectId graph in place; return the same view."""
    for a in view.get('activities_oid', []):
        a['identity'] = tag_activity(a)
    return view


_MEP_DISCIPLINES = {'MECH', 'ELEC', 'ELV', 'PIPING', 'INSTR', 'PLUMB', 'FIRE', 'PROCESS', 'UTIL'}


def detect_systems(view):
    """Roll up which systems / disciplines are present, with confidence — the
    'which MEP systems actually exist' answer the old engine couldn't give."""
    if 'activities_oid' not in view or not view['activities_oid'] or 'identity' not in view['activities_oid'][0]:
        tag_view(view)
    acts = view['activities_oid']
    by_system, by_discipline = {}, {}
    for a in acts:
        idn = a['identity']
        d, s = idn['discipline'], idn['system']
        if d:
            bd = by_discipline.setdefault(d, {'count': 0, 'high': 0})
            bd['count'] += 1
            bd['high'] += (idn['confidence'] == 'high')
        if s:
            bs = by_system.setdefault(s, {'system': s, 'discipline': d, 'count': 0, 'high': 0, 'zones': set()})
            bs['count'] += 1
            bs['high'] += (idn['confidence'] == 'high')
            if idn['zone']:
                bs['zones'].add(idn['zone'])
    systems = sorted(({**v, 'zones': len(v['zones'])} for v in by_system.values()),
                     key=lambda x: -x['count'])
    total = len(acts)
    mep = sum(v['count'] for k, v in by_discipline.items() if k in _MEP_DISCIPLINES)
    tagged = total - by_discipline.get('UNKNOWN', {}).get('count', 0)
    ambiguous = sum(1 for a in acts if a['identity']['ambiguous'])
    return {
        'systems_present': systems,
        'by_discipline': by_discipline,
        'total_activities': total,
        'tagged_activities': tagged,
        'tagged_pct': round(100.0 * tagged / max(total, 1), 1),
        'mep_activities': mep,
        'mep_pct': round(100.0 * mep / max(total, 1), 1),
        'ambiguous_activities': ambiguous,
        'ambiguous_pct': round(100.0 * ambiguous / max(total, 1), 1),
    }
