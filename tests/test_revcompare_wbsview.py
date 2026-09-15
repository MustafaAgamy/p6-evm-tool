"""Unit tests for p6_revcompare.wbsview — WBS structure view + sequence roll-up.

Pure-function tests over tiny synthetic ScheduleData / hand-built diff dicts;
no file parsing. Run only this file (fast):

  python -m pytest tests/test_revcompare_wbsview.py -q
"""
from p6_evm.parser import ScheduleData
from p6_revcompare.wbsview import build_wbs_view, build_sequence_rollup


# ── helpers ──────────────────────────────────────────────────────────────────

def _wbs_sched(wbs):
    """A ScheduleData carrying only a WBS map {oid: {name, parent_object_id}}."""
    d = ScheduleData()
    d.wbs = wbs
    d.activities = {}
    d.project = {'data_date': None, 'name': 'Test'}
    return d


# Two-tower WBS trees:
#   rev0: …Substructure > Dewatering (removed), …Superstructure > Blockwork (moved from)
#   rev1: …Envelope (added) > Blockwork (moved to), …Building B > MEP Risers (added)
_REV0_WBS = {
    'r': {'name': 'Project', 'parent_object_id': None},
    'a': {'name': 'Building A', 'parent_object_id': 'r'},
    'sub': {'name': 'Substructure', 'parent_object_id': 'a'},
    'dew': {'name': 'Dewatering', 'parent_object_id': 'sub'},
    'sup': {'name': 'Superstructure', 'parent_object_id': 'a'},
    'blk': {'name': 'Blockwork', 'parent_object_id': 'sup'},
    'b': {'name': 'Building B', 'parent_object_id': 'r'},
}
_REV1_WBS = {
    'r': {'name': 'Project', 'parent_object_id': None},
    'a': {'name': 'Building A', 'parent_object_id': 'r'},
    'sub': {'name': 'Substructure', 'parent_object_id': 'a'},
    'sup': {'name': 'Superstructure', 'parent_object_id': 'a'},
    'env': {'name': 'Envelope', 'parent_object_id': 'a'},
    'blk': {'name': 'Blockwork', 'parent_object_id': 'env'},
    'b': {'name': 'Building B', 'parent_object_id': 'r'},
    'mep': {'name': 'MEP Risers', 'parent_object_id': 'b'},
}

# What structure.diff_wbs would report for the trees above (Blockwork appears in both
# added and removed because its parent changed — wbsview folds it into 'moved').
_WBS_CHANGES = {
    'added': [
        {'path': 'Project > Building A > Envelope'},
        {'path': 'Project > Building A > Envelope > Blockwork'},
        {'path': 'Project > Building B > MEP Risers'},
    ],
    'removed': [
        {'path': 'Project > Building A > Substructure > Dewatering'},
        {'path': 'Project > Building A > Superstructure > Blockwork'},
    ],
    'renamed': [],
    'moved_activities': 18,
}


class _Matched:
    def __init__(self, by0=None, by1=None):
        self.baseline_by_code = by0 or {}
        self.update_by_code = by1 or {}


# ── build_wbs_view ─────────────────────────────────────────────────────────────

def test_wbs_view_shape_and_keys():
    v = build_wbs_view(_wbs_sched(_REV0_WBS), _wbs_sched(_REV1_WBS), _WBS_CHANGES)
    assert set(v) == {'rev0', 'rev1', 'summary'}
    assert set(v['summary']) == {'added', 'removed', 'moved', 'reparented'}
    for side in ('rev0', 'rev1'):
        for row in v[side]:
            assert set(row) == {'level', 'name', 'state'}
            assert isinstance(row['level'], int)


def test_wbs_view_preorder_and_levels():
    v = build_wbs_view(_wbs_sched(_REV0_WBS), _wbs_sched(_REV1_WBS), _WBS_CHANGES)
    # Root first, depth 0; pre-order keeps a child directly under its parent.
    assert v['rev0'][0] == {'level': 0, 'name': 'Project', 'state': 'unchanged'}
    names0 = [(r['level'], r['name']) for r in v['rev0']]
    assert (1, 'Building A') in names0 and (2, 'Substructure') in names0
    assert (3, 'Dewatering') in names0            # leaf at depth 3


def test_wbs_view_removed_added_moved_states():
    v = build_wbs_view(_wbs_sched(_REV0_WBS), _wbs_sched(_REV1_WBS), _WBS_CHANGES)
    st0 = {r['name']: r['state'] for r in v['rev0']}
    st1 = {r['name']: r['state'] for r in v['rev1']}
    assert st0['Dewatering'] == 'removed'         # gone in rev1
    assert st1['Envelope'] == 'added'             # new branch
    assert st1['MEP Risers'] == 'added'
    # Blockwork re-parented Superstructure → Envelope: 'moved' on BOTH sides,
    # never double-counted as remove+add.
    assert st0['Blockwork'] == 'moved' and st1['Blockwork'] == 'moved'


def test_wbs_view_summary_counts_match_mockup():
    v = build_wbs_view(_wbs_sched(_REV0_WBS), _wbs_sched(_REV1_WBS), _WBS_CHANGES)
    s = v['summary']
    assert s['added'] == 2                         # Envelope + MEP Risers (Blockwork excluded)
    assert s['removed'] == 1                        # Dewatering (Blockwork excluded)
    assert s['moved'] == 1                          # Blockwork re-parented
    assert s['reparented'] == 18                    # activities moved (from diff_wbs)


def test_wbs_view_identical_trees_all_unchanged():
    v = build_wbs_view(_wbs_sched(_REV0_WBS), _wbs_sched(_REV0_WBS),
                       {'added': [], 'removed': [], 'renamed': [], 'moved_activities': 0})
    assert all(r['state'] == 'unchanged' for r in v['rev0'])
    assert all(r['state'] == 'unchanged' for r in v['rev1'])
    assert v['summary'] == {'added': 0, 'removed': 0, 'moved': 0, 'reparented': 0}


def test_wbs_view_empty_or_missing_wbs_is_safe():
    empty = _wbs_sched({})
    v = build_wbs_view(empty, empty, None)
    assert v['rev0'] == [] and v['rev1'] == []
    assert v['summary'] == {'added': 0, 'removed': 0, 'moved': 0, 'reparented': 0}

    class _Bare:
        pass
    v2 = build_wbs_view(_Bare(), _Bare(), {})     # no .wbs attribute at all
    assert v2['rev0'] == [] and v2['rev1'] == []


def test_wbs_view_cyclic_parent_does_not_hang():
    # A rootless cycle (x↔y) has no entry node → safely yields [] rather than hanging.
    cyc = {'x': {'name': 'X', 'parent_object_id': 'y'},
           'y': {'name': 'Y', 'parent_object_id': 'x'}}
    v = build_wbs_view(_wbs_sched(cyc), _wbs_sched(cyc), {})
    assert isinstance(v['rev0'], list) and v['rev0'] == []


# ── build_sequence_rollup ───────────────────────────────────────────────────────

def _seq(a, b, chain0, chain1, wbs=None):
    return {'a': a, 'b': b, 'a_name': a, 'b_name': b,
            'chain0': chain0, 'chain1': chain1, 'shared_wbs': wbs}


def test_sequence_rollup_groups_by_branch_and_counts():
    seqs = [
        _seq('C1', 'S1', ['Slab S1', 'Col S1', 'Slab S2', 'Col S2'],
             ['Slab S1', 'Slab S2', 'Col S1', 'Col S2'],
             wbs='Building A > Superstructure > Level 3'),
        _seq('C3', 'S3', ['Col S3', 'Slab S3'], ['Slab S3', 'Col S3'],
             wbs='Building A > Superstructure > Level 4'),
        _seq('W1', 'R1', ['Waterproof', 'Raft'], ['Raft', 'Waterproof'],
             wbs='Building B > Substructure'),
    ]
    roll = build_sequence_rollup(seqs, None)
    groups = {g['group']: g for g in roll}
    # First two share the top branch 'Building A > Superstructure'.
    assert 'Building A > Superstructure' in groups
    assert groups['Building A > Superstructure']['count'] == 2
    assert len(groups['Building A > Superstructure']['items']) == 2
    assert 'Building B > Substructure' in groups
    # Most-populated group first.
    assert roll[0]['count'] == 2


def test_sequence_rollup_direction_tags():
    seqs = [
        # same 4 activities, re-ordered (not a pure reverse) → de-interleaved
        _seq('C1', 'S1', ['Slab S1', 'Col S1', 'Slab S2', 'Col S2'],
             ['Slab S1', 'Slab S2', 'Col S1', 'Col S2'], wbs='A > Sup'),
        # pure reversal of the same list → zone order reversed
        _seq('C2', 'S2', ['Blockwork', 'MEP'], ['MEP', 'Blockwork'], wbs='A > Sup'),
        # re-linked to a different neighbour set → trades overlapped
        _seq('C3', 'S3', ['Core walls', 'MEP risers'],
             ['MEP risers', 'Fit-out'], wbs='A > Sup'),
    ]
    roll = build_sequence_rollup(seqs, None)
    dirs = {it['a_name']: it['direction']
            for g in roll for it in g['items']}
    assert dirs['C1'] == 'de-interleaved'
    assert dirs['C2'] == 'zone order reversed'
    assert dirs['C3'] == 'trades overlapped'
    allowed = {'de-interleaved', 'trades overlapped', 'zone order reversed'}
    assert all(d in allowed for d in dirs.values())


def test_sequence_rollup_fallback_branch_via_matched():
    # shared_wbs is None → group falls back to activity a's WBS branch via matched.
    seqs = [_seq('A1', 'B1', ['A1', 'B1'], ['B1', 'A1'], wbs=None)]
    matched = _Matched(by1={'A1': {'wbs_path': 'Tower 1 > Fit-out > L5'}})
    roll = build_sequence_rollup(seqs, matched)
    assert roll[0]['group'] == 'Tower 1 > Fit-out'


def test_sequence_rollup_no_wbs_no_matched_is_cross_wbs():
    seqs = [_seq('A1', 'B1', ['A1', 'B1'], ['B1', 'A1'], wbs=None)]
    roll = build_sequence_rollup(seqs, None)
    assert roll[0]['group'] == 'Cross-WBS'


def test_sequence_rollup_empty_is_safe():
    assert build_sequence_rollup([], None) == []
    assert build_sequence_rollup(None, None) == []


def test_sequence_rollup_item_shape():
    seqs = [_seq('A1', 'B1', ['A1', 'B1'], ['B1', 'A1'], wbs='X > Y')]
    roll = build_sequence_rollup(seqs, None)
    item = roll[0]['items'][0]
    assert set(item) == {'a_name', 'b_name', 'direction', 'chain0', 'chain1'}
    assert item['chain0'] == ['A1', 'B1'] and item['chain1'] == ['B1', 'A1']
