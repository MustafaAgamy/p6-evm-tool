"""E1 rollup: Design vs Engineering(Shop) split, category overrides, and the
two gap sets. Numbers mirror Ibrahim's E1 screenshot so a regression is visible."""
from p6_evm.e1_rollup import overall_split, category_actuals, engineering_gaps, is_shop


def _rows():
    # (trade, type, req, planned, submitted, approved, not_appr)
    raw = [
        ('Civil', 'Detailed Design', 26, 26, 12, 7, 5),
        ('Civil', 'IFC', 7, 7, 8, 7, 1),
        ('MEP', 'Schematic Design', 19, 19, 19, 19, 0),
        ('MEP', 'Detailed Design', 106, 106, 0, 0, 0),
        ('Arch', 'Detailed Design', 19, 19, 1, 0, 1),
        ('Arch', 'Schematic Design', 20, 20, 30, 0, 30),
        ('Civil', 'Schematic Design', 25, 25, 8, 5, 3),
        ('Infra', 'Detailed Design', 7, 7, 4, 0, 4),
        ('Infra', 'Schematic Design', 7, 7, 14, 0, 14),
        ('Steel', 'Detailed Design', 1, 1, 3, 0, 3),
        ('Civil', 'Shop Drawing', 45, 45, 56, 43, 13),
    ]
    return [{'trade': t, 'submittal_type': ty, 'req': rq, 'planned': pl,
             'submitted_rows': su, 'approved_rows': ap, 'not_approved_rows': na,
             'under_review_rows': 0} for (t, ty, rq, pl, su, ap, na) in raw]


def test_is_shop():
    assert is_shop('Shop Drawing') and is_shop('shop drawings')
    assert not is_shop('Detailed Design') and not is_shop('IFC')


def test_explicit_bucket_overrides_type():
    # Two-file case: a Shop Drawing Log tags all its rows 'engineering' even if a row's
    # type doesn't say "shop"; a Design Log tags all 'design'.
    rows = [
        {'trade': 'Civil', 'submittal_type': 'GA Drawing', 'req': 8, 'planned': 8,
         'submitted_rows': 6, 'approved_rows': 5, 'not_approved_rows': 1, 'under_review_rows': 0,
         'bucket': 'engineering'},                                   # from the Shop log
        {'trade': 'Civil', 'submittal_type': 'Layout', 'req': 10, 'planned': 10,
         'submitted_rows': 4, 'approved_rows': 3, 'not_approved_rows': 1, 'under_review_rows': 0,
         'bucket': 'design'},                                        # from the Design log
    ]
    o = overall_split(rows)
    assert o['design']['req'] == 10 and o['design']['approved_rows'] == 3
    assert o['engineering']['req'] == 8 and o['engineering']['approved_rows'] == 5


def test_e1_file_bucket_from_name():
    from p6_evm.classify import e1_file_bucket
    assert e1_file_bucket('Shop Drawing Log.xlsx') == 'engineering'
    assert e1_file_bucket('Design Log.xlsx') == 'design'
    assert e1_file_bucket('E1 Log.xlsx') is None            # combined → split by type


def test_other_drawings_count_into_engineering():
    # As-built / coordination are neither design nor shop → Engineering bucket (Ibrahim's rule)
    rows = [
        {'trade': 'Civil', 'submittal_type': 'Detailed Design', 'req': 10, 'planned': 10,
         'submitted_rows': 5, 'approved_rows': 4, 'not_approved_rows': 1, 'under_review_rows': 0},
        {'trade': 'Civil', 'submittal_type': 'As-Built', 'req': 4, 'planned': 4,
         'submitted_rows': 2, 'approved_rows': 2, 'not_approved_rows': 0, 'under_review_rows': 0},
        {'trade': 'Civil', 'submittal_type': 'Shop Drawing', 'req': 6, 'planned': 6,
         'submitted_rows': 6, 'approved_rows': 6, 'not_approved_rows': 0, 'under_review_rows': 0},
    ]
    o = overall_split(rows)
    assert o['design']['req'] == 10                       # only the design drawing
    assert o['engineering']['req'] == 10                  # As-Built (4) + Shop (6)
    assert o['engineering']['approved_rows'] == 8         # 2 + 6


def test_overall_split_design_vs_shop():
    o = overall_split(_rows())
    # Design = every non-Shop row: Req 237, Approved 38 -> 16.0%
    assert o['design']['req'] == 237
    assert o['design']['approved_rows'] == 38
    assert o['design']['approved_pct'] == 16.0
    # Engineering = Shop only: Req 45, Approved 43 -> 95.6%
    assert o['engineering']['req'] == 45
    assert o['engineering']['approved_pct'] == 95.6


def test_category_actuals_mapping():
    cats = ['Design Phase I', 'Engineering Phase I', 'Phase II Design', 'Construction']
    a = category_actuals(_rows(), cats)
    assert round(a['Design Phase I'] * 100, 1) == 16.0
    assert round(a['Phase II Design'] * 100, 1) == 16.0
    assert round(a['Engineering Phase I'] * 100, 1) == 95.6
    assert 'Construction' not in a          # untouched


def test_shop_only_log_does_not_zero_design():
    # Uploading ONLY a Shop log must not override (zero) the Design categories.
    rows = [{'trade': 'Civil', 'submittal_type': 'Shop Drawing', 'req': 10, 'planned': 10,
             'submitted_rows': 8, 'approved_rows': 6, 'not_approved_rows': 2, 'under_review_rows': 0}]
    a = category_actuals(rows, ['Design Phase I', 'Engineering Phase I', 'Construction'])
    assert 'Design Phase I' not in a                    # left alone (keeps its schedule value)
    assert round(a['Engineering Phase I'] * 100, 1) == 60.0
    assert 'Construction' not in a


def test_engineering_gaps_separate_design_and_shop():
    g = engineering_gaps(_rows())
    # Design gap by trade: planned - approved; sorted by gap desc, shares sum to 100
    design = g['design']
    assert design                                  # non-empty
    top = design[0]
    assert set(top) >= {'trade', 'planned', 'approved', 'gap', 'pct_of_gap'}
    assert top['gap'] == top['planned'] - top['approved']
    assert round(sum(x['pct_of_gap'] for x in design)) == 100
    # Engineering (Shop) gap is separate: only Civil shop rows
    eng = g['engineering']
    assert [x['trade'] for x in eng] == ['Civil']
    assert eng[0]['gap'] == 45 - 43
