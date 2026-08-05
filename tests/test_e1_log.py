from datetime import datetime
from p6_evm.e1_log import summarize_e1


def _row(trade, typ, bldg, desc, submitted=None, planned=None, action=''):
    return {'trade': trade, 'submittal_type': typ, 'building': bldg, 'description': desc,
            'submitted': submitted, 'planned': planned, 'action_code': action}


def test_counts_and_distinct_percentages():
    # Civil Schematic: 1 drawing (D1) submitted twice — rev0 rejected (C), rev1 approved (B)
    rows = [
        _row('Civil', 'Schematic', 'Silo', 'D1', submitted=datetime(2025, 2, 1), action='C'),
        _row('Civil', 'Schematic', 'Silo', 'D1', submitted=datetime(2025, 4, 1), action='B'),
        _row('Civil', 'Schematic', 'Silo', 'D2', submitted=datetime(2025, 5, 1), action='A'),
    ]
    g = summarize_e1(rows)[('Civil', 'Schematic')]
    assert g['req'] == 2                 # two distinct drawings D1, D2
    assert g['submitted_rows'] == 2      # two distinct drawings submitted (not 3 rows)
    assert g['approved_rows'] == 2       # both drawings ultimately approved
    assert g['not_approved_rows'] == 0   # D1 is approved, so its earlier C doesn't count
    assert g['submitted_pct'] == 100.0
    assert g['approved_pct'] == 100.0


def test_approved_drawing_resubmitted_after_client_change_counts_once():
    # Client change / variation order: D1 approved at rev0 (A), then resubmitted (rev1) and
    # approved again (B). It is ONE drawing, approved — must not count twice or exceed 100%.
    rows = [
        _row('Civil', 'Shop', 'Silo', 'D1', submitted=datetime(2025, 1, 1), action='A'),
        _row('Civil', 'Shop', 'Silo', 'D1', submitted=datetime(2025, 6, 1), action='B'),  # after VO
    ]
    g = summarize_e1(rows)[('Civil', 'Shop')]
    assert g['req'] == 1 and g['approved_rows'] == 1 and g['approved_pct'] == 100.0


def test_pending_and_unsubmitted():
    rows = [
        _row('MEP', 'Detailed', 'B1', 'M1'),                                   # not submitted
        _row('MEP', 'Detailed', 'B1', 'M2', submitted=datetime(2025, 3, 1), action='P'),
    ]
    g = summarize_e1(rows)[('MEP', 'Detailed')]
    assert g['req'] == 2
    assert g['submitted_rows'] == 1
    assert g['under_review_rows'] == 1
    assert g['approved_rows'] == 0
    assert g['submitted_pct'] == 50.0    # only 1 of 2 drawings submitted
    assert g['approved_pct'] == 0.0


def test_net_submitted_formula():
    # req=3; D1 rejected then approved (2 rows), D2 rejected only, D3 not submitted
    rows = [
        _row('Civil', 'Shop', 'B', 'D1', submitted=datetime(2025, 1, 1), action='C'),
        _row('Civil', 'Shop', 'B', 'D1', submitted=datetime(2025, 2, 1), action='B'),
        _row('Civil', 'Shop', 'B', 'D2', submitted=datetime(2025, 1, 1), action='C'),
        _row('Civil', 'Shop', 'B', 'D3'),
    ]
    g = summarize_e1(rows)[('Civil', 'Shop')]
    assert g['req'] == 3
    assert g['submitted_rows'] == 2      # D1, D2 submitted (distinct); D3 not
    assert g['not_approved_rows'] == 1   # only D2 (D1 ended approved, so not rejected)
    assert g['approved_rows'] == 1       # D1
    # % Submitted = (submitted 2 - not approved 1) / req 3 = 33.3
    assert g['submitted_pct'] == 33.3
    # % Approved = approved 1 / req 3 = 33.3
    assert g['approved_pct'] == 33.3


def test_planned_by_cutoff():
    rows = [
        _row('Civil', 'IFC', 'B', 'X1', planned=datetime(2026, 1, 1)),   # planned before cutoff
        _row('Civil', 'IFC', 'B', 'X2', planned=datetime(2026, 12, 1)),  # planned after cutoff
    ]
    g = summarize_e1(rows, cutoff=datetime(2026, 5, 10))[('Civil', 'IFC')]
    assert g['req'] == 2
    assert g['planned'] == 1             # only X1 planned by the cutoff
    assert g['planned_pct'] == 50.0
