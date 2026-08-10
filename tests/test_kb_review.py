"""The rule-based constructability engine: detect the sub-type, flag a bad link
against a KB rule, list missing activities/WBS, and score — all offline."""
from p6_evm.parser import ScheduleData
from p6_kb.kb import load_kb
from p6_kb.review import run_review


def _rail_schedule():
    d = ScheduleData()
    d.wbs = {'w1': {'name': 'Civil & Earthworks', 'parent_object_id': None},
             'w2': {'name': 'Installation', 'parent_object_id': None}}

    def act(oid, code, name, wbs_id, path):
        return {'object_id': oid, 'id': code, 'name': name, 'wbs_id': wbs_id, 'wbs_path': path,
                'task_type': 'Task', 'planned_duration': 40, 'calendar_id': None}
    d.activities = {
        'o1': act('o1', 'A1200', 'Install Traction Equipment', 'w2', 'Installation'),
        'o2': act('o2', 'A1220', 'Commissioning of Substation', 'w2', 'Installation'),
        'o3': act('o3', 'A1000', 'Track Laying', 'w1', 'Civil & Earthworks'),
        'o4': act('o4', 'A1300', 'OCS Wiring', 'w1', 'Civil & Earthworks'),
    }
    # Commissioning tied Start-to-Start to installation → violates the KB rule
    d.relationships = [{'pred_id': 'o1', 'succ_id': 'o2', 'type': 'SS', 'lag_days': 0.0}]
    d.calendars = {}
    return d


ENTRIES = load_kb(overlay='')  # bundled Rail + Factory


def test_detects_rail():
    rep = run_review(_rail_schedule(), entries=ENTRIES)
    assert rep['detected']['type'] == 'Rail'
    assert 'Rail' in rep['project_type']


def test_flags_commissioning_before_installation():
    rep = run_review(_rail_schedule(), entries=ENTRIES)
    hit = next((f for f in rep['illogical'] if f['activity_id'] == 'A1220'), None)
    assert hit is not None
    # current link is SS from A1200; suggestion is FS from A1200 (change)
    assert any(p['rel'] == 'SS' and p['id'] == 'A1200' for p in hit['current_preds'])
    assert any(p['rel'] == 'FS' and p['kind'] == 'change' for p in hit['suggested_preds'])
    assert hit['impact'] == 'Critical'
    assert 'Rail' in hit['source']


def test_lists_missing_sat_and_testing_wbs():
    rep = run_review(_rail_schedule(), entries=ENTRIES)
    assert any('SAT' in m['name'] or 'Site Acceptance' in m['name'] for m in rep['missing'])
    assert any(w['name'] == 'Testing & Commissioning' for w in rep['missing_wbs'])
    # a suggested id must not clash with an existing activity id
    assert all(m['suggested_id'] not in {'A1200', 'A1220', 'A1000', 'A1300'} for m in rep['missing'])


def test_dashboard_counts_and_score():
    rep = run_review(_rail_schedule(), entries=ENTRIES)
    d = rep['dashboard']
    assert d['illogical_count'] == len(rep['illogical'])
    assert d['missing_count'] == len(rep['missing'])
    assert d['critical_affected'] is True
    assert 'overall' in rep['score'] and 'band_label' in rep['score']


def test_forced_type_overrides_detection():
    rep = run_review(_rail_schedule(), entries=ENTRIES, forced_type='Factory')
    assert 'Factory' in rep['project_type']


def test_unknown_schedule_returns_prompt():
    d = ScheduleData()
    d.wbs = {'w1': {'name': 'Miscellaneous', 'parent_object_id': None}}
    d.activities = {'o1': {'object_id': 'o1', 'id': 'X1', 'name': 'Do the thing', 'wbs_id': 'w1',
                           'wbs_path': 'Miscellaneous', 'task_type': 'Task', 'planned_duration': 1, 'calendar_id': None}}
    d.relationships = []
    d.calendars = {}
    rep = run_review(d, entries=ENTRIES)
    assert rep['detected'] is None
    assert rep['project_type'] == 'Unrecognised'
    assert rep['available_types']  # offers the sub-types to pick from
