"""Change classification & severity rules (p6_revcompare.severity)."""
from p6_revcompare import severity as SEV


def test_band():
    assert SEV.band(None) is None
    assert SEV.band(0) == 'crit'
    assert SEV.band(-2) == 'crit'
    assert SEV.band(5) == 'near'
    assert SEV.band(20) == 'safe'


def test_sequence_always_material():
    imp, sev = SEV.classify('sequence', tf0=0, tf1=0)
    assert imp == 'material' and sev == 'crit'
    imp, sev = SEV.classify('sequence', tf0=30, tf1=30)   # off the path
    assert imp == 'material' and sev == 'hi'


def test_milestone_severity_scales_with_slip():
    assert SEV.classify('milestone', magnitude=46)[1] == 'crit'
    assert SEV.classify('milestone', magnitude=5)[1] == 'hi'
    assert SEV.classify('milestone', magnitude=0)[1] == 'med'


def test_logic_material_only_on_or_near_path():
    assert SEV.classify('logic', tf0=0, tf1=0) == ('material', 'crit')
    assert SEV.classify('logic', tf0=5, tf1=5) == ('material', 'hi')
    assert SEV.classify('logic', tf0=30, tf1=30) == ('minor', 'low')


def test_time_change_material_when_large_or_on_path():
    assert SEV.classify('time', tf0=30, tf1=30, magnitude=2)[0] == 'minor'
    assert SEV.classify('time', tf0=30, tf1=30, magnitude=15)[0] == 'material'
    assert SEV.classify('time', tf0=0, tf1=0, magnitude=1)[0] == 'material'


def test_added_removed_material_on_cp():
    assert SEV.classify('added', on_cp=True)[0] == 'material'
    assert SEV.classify('added', tf0=None, tf1=30)[0] == 'minor'


def test_identity_changes_are_minor():
    assert SEV.classify('idchange', tf0=0, tf1=0)[0] == 'minor'
    assert SEV.classify('renamed')[0] == 'minor'


def test_rank_key_orders_material_and_severity_first():
    rows = [
        {'impact': 'minor', 'severity': 'low', 'activity_name': 'z'},
        {'impact': 'material', 'severity': 'hi', 'activity_name': 'b'},
        {'impact': 'material', 'severity': 'crit', 'activity_name': 'a'},
    ]
    rows.sort(key=SEV.rank_key)
    assert [r['severity'] for r in rows] == ['crit', 'hi', 'low']
