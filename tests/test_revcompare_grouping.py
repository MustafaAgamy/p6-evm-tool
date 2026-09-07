"""One-row-per-activity grouping of the change register (presentation only)."""
from p6_revcompare.grouping import group_register
from p6_revcompare import build_report_from_data
from tests.test_revcompare_engine import _pair, _act, _sched, D


def _row(activity_id, change_type, rev0, rev1, change, impact, severity,
         activity_name=None, orig_id=None, **extra):
    r = {'activity_id': activity_id, 'orig_id': orig_id,
         'activity_name': activity_name or activity_id,
         'change_type': change_type, 'type_label': change_type.title(),
         'rev0': rev0, 'rev1': rev1, 'change': change,
         'impact': impact, 'severity': severity, 'status': 'open', 'detail': None}
    r.update(extra)
    return r


# ── one row per activity ──────────────────────────────────────────────────────

def test_two_changes_on_one_activity_collapse_to_one_row():
    reg = [
        _row('A2075', 'logic', 'A2050 FS', 'A2050 SS', 'Type changed', 'material', 'crit',
             activity_name='Steel Erection', activity_key='A2075'),
        _row('A2075', 'criticality', 'TF 12 d', 'TF 0 d', 'Became critical', 'material', 'crit',
             activity_name='Steel Erection', activity_key='A2075'),
    ]
    g = group_register(reg)
    assert len(g) == 1, 'Steel Erection must appear once, not twice'
    e = g[0]
    assert e['activity_name'] == 'Steel Erection'
    assert set(e['change_types']) == {'logic', 'criticality'}
    assert len(e['changes']) == 2
    assert e['impact'] == 'material' and e['severity'] == 'crit'


def test_removed_and_added_resource_pair_on_one_line():
    reg = [
        _row('RES:A1300:Crawler Crane 50T', 'resource', '2 u', '—', 'Resource removed',
             'minor', 'med', activity_name='Raft · Crawler Crane 50T',
             activity_key='A1300', resource_name='Crawler Crane 50T', res_kind='removed', act_name='Raft'),
        _row('RES:A1300:Tower Crane TC-7', 'resource', '—', '1 u', 'Resource added',
             'minor', 'med', activity_name='Raft · Tower Crane TC-7',
             activity_key='A1300', resource_name='Tower Crane TC-7', res_kind='added', act_name='Raft'),
    ]
    g = group_register(reg)
    assert len(g) == 1
    e = g[0]
    assert e['activity_name'] == 'Raft', 'group name is the activity, not "name · resource"'
    # one combined resource line carrying BOTH the removed and the added resource
    res_lines = [c for c in e['changes'] if c['change_type'] == 'resource']
    assert len(res_lines) == 1, 'removed + added must be one line, not two'
    assert res_lines[0]['removed'] == 'Crawler Crane 50T'
    assert res_lines[0]['added'] == 'Tower Crane TC-7'


def test_scope_summary_rows_are_dropped():
    reg = [
        _row('SCOPE:removed', 'removed', 'Present in Rev.00', '—', 'Removed activities',
             'minor', 'low', activity_name='1 activities', activity_key=None),
        _row('A4400', 'added', '—', 'Present in Rev.01', 'New critical activity',
             'material', 'crit', activity_name='MEP Risers', activity_key='A4400'),
    ]
    g = group_register(reg)
    keys = [e['activity_name'] for e in g]
    assert '1 activities' not in keys
    assert 'MEP Risers' in keys


def test_milestone_row_is_its_own_kind():
    reg = [_row('MS:Practical Completion', 'milestone', '19 Dec 2026', '04 Feb 2027',
                '+47 d (delayed)', 'material', 'crit', activity_name='Practical Completion',
                activity_key='MS:Practical Completion')]
    g = group_register(reg)
    assert g[0]['kind'] == 'milestone'
    assert g[0]['activity_id'] is None


def test_order_preserved_and_display_id_cleaned():
    # the real register arrives pre-sorted by rank (worst first); grouping preserves it
    reg = [
        _row('A2', 'criticality', 'x', 'y', 'c', 'material', 'crit', activity_name='Crit one', activity_key='A2'),
        _row('A1', 'logic', 'x', 'y', 'c', 'minor', 'low', activity_name='Low one', activity_key='A1'),
    ]
    g = group_register(reg)
    assert [e['activity_name'] for e in g] == ['Crit one', 'Low one']
    # a MS:/SCOPE: prefix never leaks into the displayed id
    reg2 = [_row('A2', 'idchange', 'A2', 'A2-new', 'A2 → A2-new', 'minor', 'low',
                 activity_name='Renamed', orig_id='A2-new', activity_key='A2')]
    assert group_register(reg2)[0]['activity_id'] == 'A2-new'


# ── integration: the real engine attaches register_grouped ───────────────────

def test_engine_attaches_register_grouped_no_activity_twice():
    r = build_report_from_data(*_pair(), config={})
    assert 'register_grouped' in r
    g = r['register_grouped']
    # every real-activity entry appears once
    names = [e['activity_name'] for e in g if e['kind'] == 'activity']
    assert len(names) == len(set(names)), f'an activity is repeated: {names}'
    # Steel Erection had a logic AND a criticality change -> one entry, two badges
    steel = [e for e in g if e['activity_name'] == 'Steel Erection']
    assert len(steel) == 1
    assert set(steel[0]['change_types']) >= {'logic', 'criticality'}


def test_grouped_is_empty_when_no_changes():
    rev0, _ = _pair()
    r = build_report_from_data(rev0, rev0, config={})
    assert r['register_grouped'] == []


# ── review fixes ──────────────────────────────────────────────────────────────

def test_resource_only_group_shows_clean_code_not_synthetic_token():
    # a resource-only change: the register row carries the synthetic RES:<code>:<res> id,
    # but the displayed activity_id must be the bare code (not the internal token).
    reg = [_row('RES:A1020:Crawler Crane 50T', 'resource', '2 u', '—', 'Resource removed',
                'minor', 'med', activity_name='Raft · Crawler Crane 50T',
                activity_key='A1020', resource_name='Crawler Crane 50T', res_kind='removed', act_name='Raft')]
    g = group_register(reg)
    assert len(g) == 1
    assert g[0]['activity_id'] == 'A1020'          # NOT 'RES:A1020:Crawler Crane 50T'
    assert g[0]['activity_name'] == 'Raft'         # the activity, not "name · resource"


def test_scope_only_revision_itemizes_added_and_removed():
    # A revision whose ONLY changes are a (non-critical) added and removed activity must NOT
    # yield an empty register — each is itemised as its own one-per-activity entry.
    rev0 = _sched([
        _act('A1', 'Excavation', tf=0, ps=D(2025, 3, 1), pf=D(2025, 3, 20)),
        _act('A2', 'Old Temporary Fence', tf=40, wbs='WBS 1.9 Enabling',
             ps=D(2025, 4, 1), pf=D(2025, 4, 10)),
    ], [('A1', 'A2', 'FS', 0)], D(2025, 3, 1))
    rev1 = _sched([
        _act('A1', 'Excavation', tf=0, ps=D(2025, 3, 1), pf=D(2025, 3, 20)),
        _act('A3', 'New Landscaping Works', tf=40, wbs='WBS 1.5 MEP',
             ps=D(2025, 6, 1), pf=D(2025, 6, 12)),
    ], [('A1', 'A3', 'FS', 0)], D(2025, 3, 1))
    r = build_report_from_data(rev0, rev1, config={})
    g = r['register_grouped']
    assert g, 'scope-only revision must not produce an empty change register'
    names = [e['activity_name'] for e in g]
    assert 'New Landscaping Works' in names        # added activity itemised
    assert 'Old Temporary Fence' in names          # removed activity itemised
    # no synthetic "N activities" summary entry survives
    assert not any((e['activity_name'] or '').endswith('activities') for e in g)
