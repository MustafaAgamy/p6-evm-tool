"""Cost + branch grouping adapts to a single-root WBS — the Saint-Gobain fix
(a project built under one top node must still get a real breakdown)."""
from p6_narrative.costflow import branch_stats, cost_by_wbs
from p6_narrative.util import wbs_grouping

# one top root, two branches, each with a sub-package
WBS = {
    'root': {'name': 'Project', 'parent_object_id': None},
    'civ':  {'name': 'Civil', 'parent_object_id': 'root'},
    'mec':  {'name': 'Mechanical', 'parent_object_id': 'root'},
    'pile': {'name': 'Pile', 'parent_object_id': 'civ'},
    'conv': {'name': 'Conveyor', 'parent_object_id': 'mec'},
}
ACTS = [{'object_id': 'a', 'wbs_id': 'pile'},
        {'object_id': 'b', 'wbs_id': 'pile'},
        {'object_id': 'c', 'wbs_id': 'conv'}]
BAC = {'a': 800.0, 'b': 100.0, 'c': 100.0}


def test_cost_groups_below_single_root():
    res = cost_by_wbs(ACTS, BAC, WBS)
    assert {r['name'] for r in res['rows']} == {'Civil', 'Mechanical'}   # not one 'Project' bar
    assert res['total'] == 1000.0
    assert next(r for r in res['rows'] if r['name'] == 'Civil')['pct'] == 90.0


def test_branch_stats_counts_and_cost():
    by = {s['name']: s for s in branch_stats(ACTS, BAC, WBS)}
    assert by['Civil']['count'] == 2 and by['Civil']['pct'] == 90.0
    assert by['Mechanical']['count'] == 1


def test_multiple_roots_group_by_roots():
    wbs = {'civ': {'name': 'Civil', 'parent_object_id': None},
           'mec': {'name': 'Mechanical', 'parent_object_id': None}}
    _, branches = wbs_grouping(wbs)
    assert set(branches) == {'civ', 'mec'}
