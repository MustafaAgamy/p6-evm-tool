from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.checks.dangling import check_dangling

CONFIG = {'audit': {'default_severity': 'Medium', 'category_severity': {}}}


def _g(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': oid, 'task_type': 'Task',
         'is_critical': False, 'wbs_path': '', 'category': None}; b.update(kw); return b


def test_ff_only_predecessor_flags_dangling_start():
    # b is preceded only by FF from a — FF ties a's finish to b's finish, not b's start
    # so b's start is uncontrolled (no FS or SS incoming) → dangling-start finding expected
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FF', 'lag_days': 0},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'FS', 'lag_days': 0}])
    b = [f for f in check_dangling(g, CONFIG) if f.activity_id == 'b']
    assert len(b) == 1
    assert 'start' in b[0].basis.lower()
    assert b[0].check_id == 'LOGIC-002'


def test_fs_predecessor_start_is_controlled():
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'FS', 'lag_days': 0}])
    b = [f for f in check_dangling(g, CONFIG) if f.activity_id == 'b']
    assert b == []


def test_ss_only_successor_flags_dangling_finish():
    # b's finish is not controlled: it only has an SS successor
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c')},
           [{'pred_id': 'a', 'succ_id': 'b', 'type': 'FS', 'lag_days': 0},
            {'pred_id': 'b', 'succ_id': 'c', 'type': 'SS', 'lag_days': 0}])
    b = [f for f in check_dangling(g, CONFIG) if f.activity_id == 'b']
    assert len(b) == 1
    assert 'finish' in b[0].basis.lower()
