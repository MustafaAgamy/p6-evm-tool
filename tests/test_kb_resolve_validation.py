"""Archetype-resolver VALIDATION BATTERY.

The resolver must identify the project type from activity names alone, across the
whole range a planning engineer sees — industrial, buildings, residential, civil
infrastructure, marine, transit, energy — without any project-specific hardcoding.

Each case is a synthetic but realistic P6-style activity list and the set of
archetypes that would be a CORRECT answer. The set is plural on purpose: several
archetypes legitimately overlap (a metro station is also rail; a cement plant is
also a heavy industrial factory), and forcing a single id would be testing the KB's
labelling rather than the resolver's judgement. Where a type is genuinely distinct
(roads, bridges, tunnels, solar, mall, data center) the set is a single id.

These schedules are written from generic construction vocabulary — none of them is
a real project, and the resolver must not be tuned to any single one of them.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.patterns import load_archetypes, load_system_patterns
from p6_kb.resolve import resolve

PATTERNS = load_system_patterns()
ARCHETYPES = load_archetypes()

# (label, accepted archetype ids, activity names)
CASES = [
    ('grain silo terminal', {'silo_grain_terminal'}, [
        'Silo Slipform Concrete', 'Grain Silo Cell Construction', 'Belt Conveyor Erection',
        'Bucket Elevator Installation', 'Chain Conveyor Alignment', 'Screw Conveyor Installation',
        'Ship Unloader Erection', 'Dust Collection Baghouse Installation', 'Weighbridge Installation',
        'Bulk Material Handling Equipment Setting', 'Grain Intake Pit Works', 'Dryer Installation',
        'Electrical Cable Tray and Cabling', 'Instrument Loop Check', 'Conveying System Commissioning']),

    ('oil and gas process plant', {'process_oil_gas', 'chemical_petrochemical', 'tank_farm', 'lng_terminal'}, [
        'Pipe Rack Steel Erection', 'Process Piping Spool Fabrication', 'Spool Erection - Unit 100',
        'Pressure Vessel Installation', 'Heat Exchanger Setting', 'Centrifugal Pump Installation',
        'Compressor Skid Installation', 'Welding and NDT of Process Piping', 'Hydrotest of Piping Systems',
        'Line Flushing and Reinstatement', 'Piping Insulation and Painting', 'Instrument Tubing and Hook-Up',
        'DCS Cabinet Installation', 'Fire and Gas Detection System', 'Pre-Commissioning of Process Units',
        'Nitrogen Purging', 'Start-Up and Performance Test']),

    ('power plant', {'power_utility_plant', 'waste_to_energy', 'substation_switchyard'}, [
        'Boiler Steel Structure Erection', 'Steam Turbine Generator Installation', 'Condenser Installation',
        'HRSG Erection', 'Steam Piping Erection and Welding', 'Feedwater Pump Installation',
        'Transformer Installation', 'Switchgear Installation', 'HV Cable Termination',
        'Cooling Water System Piping', 'Chemical Dosing System', 'Stack Erection',
        'Plant DCS Configuration', 'Steam Blowing', 'Unit Commissioning and Trial Run']),

    ('water treatment plant', {'water_wastewater', 'desalination_plant', 'pumping_station'}, [
        'Sedimentation Tank Concrete Works', 'Clarifier Mechanism Installation', 'Filter Media Installation',
        'Raw Water Pump Station Equipment', 'Blower Installation', 'Aeration Diffuser Installation',
        'Chlorination Dosing System', 'Process Pipework Installation', 'Valve Chamber Works',
        'Sludge Handling Equipment', 'SCADA and Instrumentation', 'Watertightness Testing',
        'Plant Wet Commissioning']),

    ('data center', {'data_center'}, [
        'White Space Raised Floor Installation', 'UPS Installation and Testing',
        'Standby Generator Installation', 'Diesel Rotary UPS Commissioning', 'CRAC Unit Installation',
        'Chilled Water Piping to CRAH Units', 'Busway Installation to Racks', 'Server Rack Installation',
        'Structured Data Cabling', 'VESDA Aspirating Smoke Detection', 'FM200 Clean Agent System',
        'Level 4 Integrated Systems Test', 'Black Building Test', 'Data Hall Handover']),

    ('hospital', {'hospital_healthcare'}, [
        'Operating Theatre Fit-Out', 'Medical Gas Pipeline Installation', 'Medical Gas Manifold Room',
        'HEPA Filtration and Cleanroom Ceiling', 'Isolation Room Pressurisation Testing',
        'Nurse Call System Installation', 'Patient Room Finishes', 'Radiology Lead Lining',
        'Imaging Equipment Installation', 'Chilled Water and AHU Installation',
        'Medical Gas Testing and Certification', 'Emergency Power Changeover Test', 'Ward Handover']),

    ('villa / residential finishing', {'villa', 'standalone_house', 'townhouse', 'lowrise_residential',
                                       'residential_building', 'residential_compound'}, [
        'Villa Foundation and Ground Slab', 'Villa Blockwork to External Walls', 'Internal Wall Plaster',
        'MEP First Fix - Conduits and Pipes', 'Floor Screed', 'Bathroom Waterproofing and Flood Test',
        'Floor and Wall Tiling', 'Marble to Staircase', 'Gypsum Board Ceiling',
        'Wall Painting - Two Coats', 'Internal Doors and Ironmongery', 'Kitchen Joinery Installation',
        'Sanitary Ware and Fixtures', 'Wiring Devices and Light Fittings', 'Snagging and Handover']),

    ('high-rise residential tower', {'highrise_residential', 'midrise_residential', 'apartment_building',
                                     'residential_building', 'mixed_use_residential', 'commercial_highrise'}, [
        'Tower Core Slipform', 'Post-Tensioned Slab - Typical Floor', 'Curtain Wall Installation',
        'Apartment Blockwork and Plaster', 'Riser Pipework Installation', 'Booster Pump Set Installation',
        'Fire Fighting Sprinkler to Apartments', 'Passenger Lift Installation and Testing',
        'Apartment Unit Finishes', 'Balcony Waterproofing and Tiling', 'Common Corridor Finishes',
        'Electrical Busbar Risers', 'Apartment Handover Snagging']),

    ('roads and highways', {'roads_highways'}, [
        'Site Clearance and Earthworks', 'Subgrade Preparation', 'Subbase and Roadbase Layers',
        'Asphalt Binder Course', 'Asphalt Wearing Course', 'Kerbs and Footpath',
        'Box Culvert Construction', 'Stormwater Drainage Network', 'Street Lighting Column Erection',
        'Road Marking and Signage', 'Traffic Signal Installation', 'Road Opening to Traffic']),

    ('bridge / viaduct', {'bridges'}, [
        'Bored Pile Installation - Pier P1', 'Pile Cap Construction', 'Pier Column Construction',
        'Pier Head Casting', 'Precast Girder Fabrication', 'Girder Erection by Crane',
        'Deck Slab Casting', 'Post-Tensioning and Grouting', 'Bridge Bearing Installation',
        'Expansion Joint Installation', 'Parapet and Crash Barrier', 'Bridge Load Testing']),

    ('tunnel', {'tunnels'}, [
        'TBM Assembly and Launch', 'Tunnel Boring - Drive 1', 'Segmental Lining Erection',
        'Cross Passage Excavation', 'Tunnel Invert Concrete', 'Shaft Excavation and Lining',
        'Tunnel Ventilation Fan Installation', 'Jet Fan Installation', 'Tunnel Lighting Installation',
        'Fire Main and Hydrant in Tunnel', 'Tunnel Drainage Pumping Station',
        'Tunnel Systems Commissioning']),

    ('airport terminal', {'airport_terminal'}, [
        'Terminal Building Structural Steel', 'Terminal Roof Cladding', 'Check-In Hall Finishes',
        'Baggage Handling System Installation', 'Baggage Screening Equipment',
        'Passenger Boarding Bridge Installation', 'Escalator and Travelator Installation',
        'Flight Information Display System', 'Terminal HVAC AHU Installation',
        'Security Screening Fit-Out', 'Departure Lounge Fit-Out',
        'Terminal Systems Integrated Testing']),

    ('airport airside', {'airport_airside'}, [
        'Runway Subgrade and Subbase', 'Runway Rigid Pavement Concrete', 'Taxiway Asphalt Paving',
        'Apron Stand Construction', 'Airfield Ground Lighting Ducts', 'Runway Edge Lighting Installation',
        'PAPI Installation', 'Airfield Marking and Signage', 'Apron Drainage Works',
        'Fuel Hydrant Pit Installation', 'Runway Friction Testing', 'Airside Handover']),

    ('container terminal', {'seaport_container_terminal', 'marine_jetty_quay', 'seaport_bulk_terminal'}, [
        'Quay Wall Diaphragm Wall', 'Dredging and Reclamation', 'Quay Deck Construction',
        'Crane Rail Beam and Rail Installation', 'Ship-to-Shore Gantry Crane Erection',
        'RTG Crane Assembly', 'Container Yard Paving', 'Reefer Rack Installation',
        'Terminal High Mast Lighting', 'Gate Complex Construction',
        'Crane Power Supply and Cable Reel', 'Terminal Operating System Integration']),

    ('metro station', {'metro_station', 'rail_metro', 'railway_track_systems'}, [
        'Station Box Diaphragm Wall', 'Station Excavation and Strutting', 'Concourse Slab Construction',
        'Platform Slab and Platform Screen Doors', 'Station Architectural Finishes',
        'Escalator Installation', 'Tunnel Ventilation System', 'Environmental Control System Installation',
        'Signalling Equipment Room Fit-Out', 'Traction Power Substation', 'Third Rail Installation',
        'Station Systems Integrated Testing']),

    ('cement plant', {'cement_plant', 'mining_processing', 'industrial_factory'}, [
        'Raw Mill Foundation', 'Rotary Kiln Erection', 'Kiln Refractory Lining',
        'Preheater Tower Steel Erection', 'Cement Mill Installation', 'Clinker Silo Construction',
        'Belt Conveyor Erection', 'Bag Filter Installation', 'ID Fan Installation',
        'Packing Plant Equipment', 'Electrical MCC Installation', 'Kiln No-Load Test',
        'Hot Commissioning']),

    ('steel plant', {'steel_plant', 'industrial_factory', 'mining_processing'}, [
        'Electric Arc Furnace Foundation', 'EAF Shell Erection', 'Ladle Furnace Installation',
        'Continuous Casting Machine Erection', 'Rolling Mill Stand Installation',
        'Overhead Crane Runway and Crane Erection', 'Water Cooling System Piping',
        'Oxygen and Gas Piping Installation', 'Fume Extraction Duct Erection',
        'Transformer and Substation Installation', 'Hydraulic Power Pack Installation',
        'Hot Trial Rolling']),

    ('pharmaceutical plant', {'pharmaceutical_plant', 'food_beverage_plant', 'industrial_factory'}, [
        'Cleanroom Wall and Ceiling Panel Installation', 'HEPA Filter Installation and Integrity Test',
        'HVAC AHU for Cleanroom', 'Purified Water Generation Skid', 'WFI Distribution Loop Installation',
        'Orbital Welding of Stainless Piping', 'Passivation and Cleaning of Loops',
        'Process Vessel Installation', 'Clean Steam Generator Installation', 'BMS and EMS Installation',
        'IQ OQ Qualification', 'Process Validation and Handover']),

    ('solar PV plant', {'solar_pv_plant'}, [
        'Site Grading and Access Roads', 'Pile Driving for Module Structures',
        'Mounting Structure Installation', 'PV Module Installation', 'DC String Cabling',
        'Inverter Station Installation', 'Step-Up Transformer Installation',
        'MV Cable Laying and Termination', 'Earthing and Lightning Protection',
        'SCADA and Monitoring System', 'String IV Testing', 'Grid Connection and Energization']),

    ('electrical substation', {'substation_switchyard', 'power_utility_plant'}, [
        'Switchyard Civil Foundations', 'Gantry Structure Erection', 'Power Transformer Installation',
        'GIS Switchgear Installation', 'Busbar and Conductor Stringing', 'Circuit Breaker Installation',
        'Protection and Control Panel Installation', 'Battery and Charger Installation',
        'Earthing Grid Installation', 'Cable Trench and Cable Laying', 'Primary Injection Testing',
        'Substation Energization']),

    ('district cooling plant', {'district_cooling_plant', 'power_utility_plant'}, [
        'Plant Room Civil Works', 'Chiller Installation and Alignment', 'Cooling Tower Erection',
        'Primary Chilled Water Pump Installation', 'Chilled Water Piping Header Fabrication',
        'Thermal Energy Storage Tank Erection', 'District Cooling Network Pipe Laying',
        'Pipe Insulation Works', 'Electrical Switchgear and VFD Installation', 'BMS Integration',
        'Chilled Water Flushing and Water Treatment', 'Plant Performance Test']),

    ('warehouse / logistics', {'warehouse_logistics', 'cold_storage', 'parking_structure'}, [
        'Warehouse Pad Foundation', 'Pre-Engineered Steel Frame Erection', 'Roof and Wall Cladding',
        'Warehouse Floor Power Float Slab', 'Loading Dock Levellers Installation',
        'Racking System Installation', 'High Bay Lighting Installation', 'ESFR Sprinkler System',
        'Ventilation Fan Installation', 'Office Block Fit-Out', 'Fire Alarm Installation',
        'Warehouse Handover']),

    ('shopping mall', {'mall_retail'}, [
        'Retail Podium Substructure and Raft', 'Superstructure Concrete Frame',
        'Atrium Structural Steel and Skylight', 'Retail Unit Shell and Core Completion',
        'Anchor Tenant Handover', 'Tenant Fit-Out Coordination', 'Shopfront Installation',
        'Food Court Fit-Out', 'Escalator Installation and Testing', 'Travelator Installation',
        'Car Park Deck and Ramps', 'Common Area Marble Flooring',
        'Gypsum Ceiling to Retail Corridor', 'Chilled Water Piping to AHUs',
        'Ductwork to Retail Units', 'Fire Fighting Sprinkler Network', 'Electrical Busbar Risers',
        'BMS Integration and Testing']),

    ('rail depot', {'rail_metro', 'railway_track_systems', 'metro_station'}, [
        'Depot Site Preparation and Earthworks', 'Stabling Yard Formation and Ballast',
        'Ballasted Track Laying - Stabling Roads', 'Turnout and Switch Installation',
        'Maintenance Workshop Building Structure', 'Inspection Pit Road Construction',
        'Bogie Drop Equipment Installation', 'Lifting Jacks Installation and Commissioning',
        'Wheel Lathe Installation', 'Train Wash Plant Installation', 'Sanding Plant Installation',
        'Overhead Catenary System Erection', 'Third Rail Conductor Installation',
        'Traction Power Substation Equipment', 'Depot Control Centre and Server Room Fit-Out',
        'Signalling and Telecom Depot Works', 'Depot Data Cabling and Network Racks',
        'Compressed Air System to Workshop', 'Workshop Overhead Crane Installation',
        'Depot Testing and Commissioning', 'Rolling Stock Trial Running']),

    ('hotel', {'hotel_hospitality', 'mixed_use_residential', 'commercial_highrise'}, [
        'Hotel Tower Structure', 'Guest Room Blockwork and Plaster',
        'Guest Room Bathroom Pod Installation', 'Guest Room FF and E Installation',
        'Corridor Carpet and Wall Covering', 'Ballroom Fit-Out', 'Kitchen Equipment Installation',
        'Laundry Equipment Installation', 'Swimming Pool Plant Room',
        'FCU and Ductwork to Guest Rooms', 'Fire Alarm and Sprinkler Installation',
        'Guest Room Mock-Up Approval', 'Hotel Systems Commissioning']),

    ('stadium', {'sports_stadium_arena'}, [
        'Stadium Bowl Substructure', 'Precast Terrace Unit Erection', 'Roof Truss Erection and Lift',
        'PTFE Roof Membrane Installation', 'Pitch Drainage and Irrigation', 'Natural Turf Installation',
        'Sports Floodlighting Installation', 'Giant Screen and Scoreboard Installation',
        'Public Address and Voice Alarm', 'Turnstile and Access Control Installation',
        'Hospitality Suite Fit-Out', 'Stadium Systems Testing']),

    ('school', {'school_education', 'university_campus'}, [
        'School Block Foundations', 'Classroom Block Superstructure', 'Classroom Blockwork and Plaster',
        'Classroom Finishes and Painting', 'Science Laboratory Fit-Out', 'Library Fit-Out',
        'Sports Hall Steel Structure', 'Split AC Unit Installation', 'Electrical Wiring and Devices',
        'Fire Alarm and PA System', 'Playground and Landscaping', 'School Handover']),
]


def _view(names):
    return {'activities_oid': [{'name': n} for n in names]}


@pytest.mark.parametrize('label,accept,names', CASES, ids=[c[0] for c in CASES])
def test_resolver_identifies_project_type(label, accept, names):
    r = resolve(_view(names), PATTERNS, ARCHETYPES)
    assert r is not None, f'{label}: resolver returned nothing'
    assert r['archetype'] in accept, \
        f"{label}: got {r['archetype']} ({r['confidence']}), expected one of {sorted(accept)}"


def test_battery_covers_the_project_range():
    """The battery itself must stay broad — not shrink to the easy cases."""
    cats = {c for _l, acc, _n in CASES for c in acc}
    assert len(CASES) >= 25 and len(cats) >= 30
