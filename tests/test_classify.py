"""Construction-meaning classification shared by WBS + E1. Guards the auto-setup:
different projects name things differently, so matching is by meaning not spelling."""
from p6_evm.classify import (classify_wbs_name, classify_branch_names, default_weights,
                             is_design_drawing, match_e1_field)


def test_wbs_category_by_meaning():
    assert classify_wbs_name('Phase I Construction Works') == 'Construction'
    assert classify_wbs_name('Phase I Engineering') == 'Engineering'
    assert classify_wbs_name('Phase I Design') == 'Design'
    assert classify_wbs_name('Phase II Design') == 'Design'
    assert classify_wbs_name('Procurement & Delivery') == 'Procurement'
    # a project that calls Engineering "Shop Drawings" still lands as Engineering
    assert classify_wbs_name('Shop Drawings') == 'Engineering'
    # civil/structural/MEP works are construction
    assert classify_wbs_name('Silos Area — Civil') == 'Construction'
    assert classify_wbs_name('MEP Installation') == 'Construction'


def test_branch_fallback_is_construction():
    assert classify_branch_names(['General Requirements', 'Site']) == 'Construction'
    assert classify_branch_names(['Nothing', 'Detailed Design']) == 'Design'


def test_top_phase_wins_over_leaf_word():
    # leaf 'Rebar Shop Drawing Approval' under a Construction phase → Construction,
    # not Engineering (names are leaf → root, phase is last)
    names = ['Rebar Shop Drawing Approval', 'Foundations', 'Phase I Construction Works', 'GBT']
    assert classify_branch_names(names) == 'Construction'
    # 'Delivery Bins' is a construction area, not Procurement
    assert classify_wbs_name('Delivery Bins Mechanical Installation Works') == 'Construction'


def test_project_root_name_does_not_swallow_categories():
    # regression: a project named "... Detailed Schedule" must NOT match Design and
    # make every activity Design (this happened on the real XER baseline).
    assert classify_wbs_name('Grain Bulk Terminal - Phase I Scope Detailed Schedule') is None
    names = ['Rebar', 'Foundations', 'Phase I Construction Works', 'GBT Detailed Schedule']
    assert classify_branch_names(names) == 'Construction'
    # but a real "Detailed Design" branch is still Design (via 'design')
    assert classify_wbs_name('Civil Detailed Design') == 'Design'


def test_default_weights_construction_95_rest_share_5():
    w = default_weights({'Construction', 'Engineering', 'Design', 'Procurement'})
    assert w['Construction'] == 0.95
    assert round(sum(w.values()), 6) == 1.0
    # three others share 5% evenly
    assert round(w['Engineering'], 6) == round(0.05 / 3, 6)


def test_default_weights_no_construction_splits_even():
    w = default_weights({'Engineering', 'Design'})
    assert round(w['Engineering'], 6) == 0.5 and round(w['Design'], 6) == 0.5


def test_is_design_drawing():
    for t in ['Detailed Design', 'Schematic Design', 'IFC', 'Concept Design']:
        assert is_design_drawing(t), t
    for t in ['Shop Drawing', 'As-Built', 'Coordination', 'Vendor Drawing', '']:
        assert not is_design_drawing(t), t


def test_e1_field_matching_by_meaning():
    assert match_e1_field('Descipline') == 'trade'
    assert match_e1_field('Discipline') == 'trade'
    assert match_e1_field('Trade') == 'trade'
    assert match_e1_field('Division') == 'trade'
    assert match_e1_field('Type of Submittal') == 'submittal_type'
    assert match_e1_field('Drawing Type') == 'submittal_type'
    assert match_e1_field('Planned Submission') == 'planned'
    assert match_e1_field('Submitted') == 'submitted'
    assert match_e1_field('Action') == 'action_code'
    assert match_e1_field('Review Status') in ('action_code',)
    assert match_e1_field('Totally Unrelated') is None


def test_type_of_submittal_beats_generic_type():
    # longest-match wins so the specific phrase isn't stolen by the generic 'type'
    assert match_e1_field('Type of Submittal') == 'submittal_type'
