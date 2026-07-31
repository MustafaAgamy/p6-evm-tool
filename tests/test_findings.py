from p6_audit.findings import Finding, resolve_severity, SEVERITY_ORDER

CONFIG = {'audit': {
    'default_severity': 'Medium',
    'category_severity': {'Construction': 'High', 'Design Phase I': 'Low'},
}}


def test_finding_as_dict_has_standard_keys():
    f = Finding(check_id='LOGIC-001', check_name='Open Ends', category='Construction',
                severity='High', activity_id='A230', activity_name='Roof Steel',
                wbs_path='T33 > Structure', summary='Missing successor', basis='succ=0')
    d = f.as_dict()
    assert d['activity_id'] == 'A230'
    assert d['confidence'] is None
    assert d['check_id'] == 'LOGIC-001'


def test_finding_id_is_populated_and_leads_the_dict():
    f = Finding(check_id='LOGIC-001', check_name='Open Ends', category='Construction',
                severity='High', activity_id='A230', activity_name='Roof Steel',
                wbs_path='T33 > Structure', summary='Missing successor', basis='succ=0')
    d = f.as_dict()
    assert d['finding_id']                        # non-empty
    assert list(d.keys())[0] == 'finding_id'      # standard order: id first


def test_finding_id_is_deterministic_across_reimports():
    # Same schedule imported twice -> identical finding_id (enables "still open" tracking)
    kw = dict(check_id='LOGIC-001', check_name='Open Ends', category='Construction',
              severity='High', activity_id='A230', activity_name='Roof Steel',
              wbs_path='T33 > Structure', basis='succ=0')
    assert Finding(**kw).finding_id == Finding(**kw).finding_id


def test_two_dangling_findings_on_same_activity_do_not_collide():
    # LOGIC-002 emits dangling-start AND dangling-finish on one activity, same
    # check_id + activity_id + related; only `basis` differs. Ids must stay distinct.
    common = dict(check_id='LOGIC-002', check_name='Dangling Logic', category=None,
                  severity='High', activity_id='A240', activity_name='Roof Cladding',
                  wbs_path='T33 > Structure')
    start = Finding(**common, basis='activity start has no FS/SS predecessor tie')
    finish = Finding(**common, basis='activity finish has no FS/FF successor tie')
    assert start.finding_id != finish.finding_id


def test_explicit_finding_id_is_respected():
    # An id supplied by the caller (e.g. AI layer or DB rehydration) is not overwritten
    f = Finding(check_id='LOGIC-001', check_name='Open Ends', category=None,
                severity='High', activity_id='A230', activity_name='Roof Steel',
                wbs_path='', finding_id='fixed-id-123')
    assert f.finding_id == 'fixed-id-123'


def test_resolve_takes_higher_of_check_and_category():
    # check base Medium, category Construction (High) -> High
    assert resolve_severity('Medium', 'Construction', False, CONFIG) == 'High'
    # check base High, category Design Phase I (Low) -> High
    assert resolve_severity('High', 'Design Phase I', False, CONFIG) == 'High'


def test_resolve_unknown_category_uses_default():
    assert resolve_severity('Low', 'Procurement', False, CONFIG) == 'Medium'


def test_resolve_critical_path_forces_critical():
    assert resolve_severity('Low', 'Design Phase I', True, CONFIG) == 'Critical'
