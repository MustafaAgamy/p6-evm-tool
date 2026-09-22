from p6_claims import methods


def test_tia_is_executable_and_named():
    m = methods.get_method('tia')
    assert m['name'] == 'Time impact analysis'
    assert m['executable'] is True
    assert m['aace_mip'] == 'MIP 3.7'


def test_other_methods_are_known_but_not_executable_yet():
    for key in ('iap', 'windows', 'but_for'):
        m = methods.get_method(key)
        assert m is not None, key
        assert m['executable'] is False, key
        assert m['name'] and m['needs'] and m['description']


def test_only_tia_is_executable_now():
    assert [m['key'] for m in methods.executable_methods()] == ['tia']


def test_list_methods_orders_tia_first():
    assert [m['key'] for m in methods.list_methods()][0] == 'tia'


def test_unknown_method_returns_none():
    assert methods.get_method('nope') is None
    assert methods.is_executable('nope') is False
