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


def test_resolve_takes_higher_of_check_and_category():
    # check base Medium, category Construction (High) -> High
    assert resolve_severity('Medium', 'Construction', False, CONFIG) == 'High'
    # check base High, category Design Phase I (Low) -> High
    assert resolve_severity('High', 'Design Phase I', False, CONFIG) == 'High'


def test_resolve_unknown_category_uses_default():
    assert resolve_severity('Low', 'Procurement', False, CONFIG) == 'Medium'


def test_resolve_critical_path_forces_critical():
    assert resolve_severity('Low', 'Design Phase I', True, CONFIG) == 'Critical'
