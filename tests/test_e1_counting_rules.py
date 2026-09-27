"""summarize_e1 counting rules added with the format-agnostic engineering-log reader.

The owner's rules are unchanged (a drawing counts once; once approved at any revision it stays
approved; % Submitted = (Submitted − Rejected) ÷ Req; % Approved = Approved ÷ Req). New:
  * a row may carry its own distinct-drawing key ('drawing_key', e.g. from a Drawing No.
    column) — otherwise the key stays (building, description) exactly as before;
  * a row may carry a pre-classified 'verdict' (from the log's own code legend);
  * a row SUBMITTED with no reply and no code yet counts as Under Review (approved rule §2).
"""
from datetime import datetime

from p6_evm.e1_log import summarize_e1


def _r(key, action='', submitted=datetime(2025, 1, 1), **kw):
    row = {'trade': 'Civil', 'submittal_type': 'SD', 'building': 'B', 'description': 'same title',
           'submitted': submitted, 'planned': None, 'action_code': action, 'drawing_key': key}
    row.update(kw)
    return row


def test_drawing_key_separates_drawings_that_share_a_title():
    # two different drawing numbers with the same (building, description) are TWO drawings
    g = summarize_e1([_r('DWG-001', 'A'), _r('DWG-002', 'C')])[('Civil', 'SD')]
    assert g['req'] == 2 and g['approved_rows'] == 1 and g['not_approved_rows'] == 1


def test_revisions_c_then_b_is_approved_once():
    g = summarize_e1([_r('DWG-001', 'C'), _r('DWG-001', 'B')])[('Civil', 'SD')]
    assert (g['req'], g['approved_rows'], g['not_approved_rows'], g['approved_pct']) == (1, 1, 0, 100.0)


def test_revisions_b_then_c_stays_approved():
    # once approved at any revision it stays approved (a later C re-issue doesn't undo it)
    g = summarize_e1([_r('DWG-001', 'B'), _r('DWG-001', 'C')])[('Civil', 'SD')]
    assert (g['req'], g['approved_rows'], g['not_approved_rows']) == (1, 1, 0)
    assert g['submitted_pct'] == 100.0


def test_submitted_without_reply_is_under_review():
    rows = [_r('D1', ''), _r('D2', '', submitted=None)]
    g = summarize_e1(rows)[('Civil', 'SD')]
    assert g['req'] == 2
    assert g['submitted_rows'] == 1
    assert g['under_review_rows'] == 1          # D1: sent, no reply yet
    assert g['approved_rows'] == 0 and g['not_approved_rows'] == 0


def test_submitted_with_reply_date_but_no_code_is_not_under_review():
    # a reply came back but the code cell is blank → unknown, not "awaiting reply"
    g = summarize_e1([_r('D1', '', returned=datetime(2025, 1, 9))])[('Civil', 'SD')]
    assert g['under_review_rows'] == 0


def test_rejected_then_resubmitted_without_reply_stays_rejected():
    # existing rule: Not Approved while not yet approved (rejected wins over under review)
    g = summarize_e1([_r('D1', 'C'), _r('D1', '')])[('Civil', 'SD')]
    assert g['not_approved_rows'] == 1 and g['under_review_rows'] == 0


def test_row_verdict_overrides_default_classification():
    # the log's legend said C = approved with comments → the reader pre-classifies it
    g = summarize_e1([_r('D1', 'C', verdict='approved')])[('Civil', 'SD')]
    assert g['approved_rows'] == 1 and g['not_approved_rows'] == 0
    # a code the planner chose to Ignore is not counted as anything (and is a code, so not
    # "awaiting reply" either)
    g = summarize_e1([_r('D1', 'N', verdict=None)])[('Civil', 'SD')]
    assert (g['approved_rows'], g['not_approved_rows'], g['under_review_rows']) == (0, 0, 0)


def test_no_drawing_key_keeps_the_old_building_description_key():
    rows = [
        {'trade': 'Civil', 'submittal_type': 'SD', 'building': 'Silo', 'description': 'D1',
         'submitted': datetime(2025, 1, 1), 'planned': None, 'action_code': 'C'},
        {'trade': 'Civil', 'submittal_type': 'SD', 'building': 'Silo ', 'description': 'D1',
         'submitted': datetime(2025, 2, 1), 'planned': None, 'action_code': 'B'},
    ]
    g = summarize_e1(rows)[('Civil', 'SD')]
    assert g['req'] == 1 and g['approved_rows'] == 1
