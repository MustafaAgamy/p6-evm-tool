"""Cost + branch grouping adapts to a single-root WBS — the Saint-Gobain fix
(a project built under one top node must still get a real breakdown)."""
from p6_narrative.costflow import branch_stats, cost_by_wbs
from p6_narrative.report import build_report
from p6_narrative.util import wbs_grouping
from tests import intel_fixtures as F

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


# ── WBS section: overview org-chart + per-branch breakdown to level 4 ──────────
def _deep_epc():
    """A single-root EPC schedule with one branch (Engineering) six WBS tiers deep and
    one shallow branch (Construction) — enough to exercise the overview chart, the
    per-branch depth-4 cap, and the '+N more' breadth marker."""
    d = F._blank()
    d.project = {'name': 'Deep EPC', 'data_date': None}
    d.wbs['PRJ'] = {'name': 'Deep EPC', 'parent_object_id': None}
    d.wbs['ENG'] = {'name': 'Engineering', 'parent_object_id': 'PRJ'}
    d.wbs['CON'] = {'name': 'Construction', 'parent_object_id': 'PRJ'}
    # Engineering broken down six tiers deep (branch root ENG is tier 0):
    #   Engineering → Phase I → Shop Drawing → Submittal → Approval → Detailing
    d.wbs['PH1'] = {'name': 'Phase I Engineering', 'parent_object_id': 'ENG'}
    d.wbs['SHOP'] = {'name': 'Shop Drawing', 'parent_object_id': 'PH1'}
    d.wbs['SUB'] = {'name': 'Submittal', 'parent_object_id': 'SHOP'}
    d.wbs['APP'] = {'name': 'Approval', 'parent_object_id': 'SUB'}
    d.wbs['DET'] = {'name': 'Detailing', 'parent_object_id': 'APP'}   # tier 5 → beyond the cap
    d.activities['e1'] = F._act('e1', 'Approve Drawings', 'APP', act_id='EN-01')
    d.activities['e2'] = F._act('e2', 'Produce Details', 'DET', act_id='EN-02')
    d.activities['c1'] = F._act('c1', 'Excavate', 'CON', act_id='CO-01')
    d.activities['c2'] = F._act('c2', 'Foundation', 'CON', act_id='CO-02')
    F._chain(d, ['e1', 'e2', 'c1', 'c2'])
    return d


def _max_depth(node, depth=0):
    kids = [k for k in (node.get('children') or []) if not k.get('more')]
    return max([_max_depth(k, depth + 1) for k in kids], default=depth)


def _wbs_payload(data):
    doc = build_report(data).to_dict()
    return next(s for s in doc['sections'] if s['kind'] == 'wbs_tree')['payload']


def test_wbs_carries_overview_and_per_branch_breakdown():
    p = _wbs_payload(_deep_epc())
    # (a) a single overview org-chart: project → major branches, shallow
    ov = p['overview']
    assert ov['name'] == 'Deep EPC'
    branch_names = {c['name'] for c in ov['children']}
    assert {'Engineering', 'Construction'} <= branch_names
    assert _max_depth(ov) == 1                        # project + major branches only
    # (b) one breakdown chart per major branch
    branches = {b['name']: b for b in p['branches']}
    assert {'Engineering', 'Construction'} <= set(branches)
    for b in p['branches']:
        assert 'root' in b and b['layout'] in ('tree', 'columns')
    # 'worlds' kept for back-compat / fallback rendering
    assert p['worlds']


def test_per_branch_breakdown_reaches_level_four_and_caps_there():
    branches = {b['name']: b for b in _wbs_payload(_deep_epc())['branches']}
    eng = branches['Engineering']['root']
    assert eng['name'] == 'Engineering'
    # the six-tier Engineering branch is expanded to — and capped at — depth 4
    assert _max_depth(eng) == 4
    # the deepest kept name is Approval; Detailing (tier 5) is dropped by the cap
    names = []

    def _walk(n):
        names.append(n['name'])
        for k in n.get('children') or []:
            _walk(k)
    _walk(eng)
    assert 'Approval' in names and 'Detailing' not in names
