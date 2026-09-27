"""The owner-approved REVIEW-CODE RULE (Tool-Wide Enhancement scope, Decisions §2):

  Approved      = A, B, Code 1, Code 2, "approved", "approved as noted", "approved with
                  comments", "no objection", "reviewed – no exceptions (taken)"
  Not approved  = C, D, Code 3, Code 4, "revise and resubmit", "rejected", "not approved"
  Under review  = W, P, "pending", "under review", "in review" (and a row submitted with no
                  reply yet — that part lives in summarize_e1)
  Not sent yet  = "under preparation", "in progress", "pending / awaiting submission",
                  "not yet submitted", "to be submitted" → None (not a review status at all)

A code legend found in the log itself overrides these defaults (classify_action_code_with_legend).
"""
import pytest

from p6_evm.classify import classify_action_code, classify_action_code_with_legend


@pytest.mark.parametrize('raw', [
    'A', 'B', 'a', ' b ', 'Code 1', 'Code 2', 'code-1', '1', '2', 1, 2, 1.0,
    'Approved', 'APPROVED', 'Approved as Noted', 'Approved with comments', 'Approved With\nComments',
    'No objection', 'No Objection', 'Reviewed - no exceptions taken', 'Reviewed – No Exceptions Taken',
    'Reviewed, no exceptions', 'Approved (Code B)', 'Approved \n( A )', 'AAN', 'Accepted',
    'STATUS: B (approved with comments).',
])
def test_approved(raw):
    assert classify_action_code(raw) == 'approved', raw


@pytest.mark.parametrize('raw', [
    'C', 'D', 'c', 'Code 3', 'Code 4', '3', '4', 3, 4.0,
    'Revise and Resubmit', 'Revise & Resubmit', 'Revise & Resubmit\n  ( C )', 'Rejected',
    'Rejected \n( D )', 'Not Approved', 'not approved', 'RNS', 'Rejected to Resubmittal',
])
def test_not_approved(raw):
    assert classify_action_code(raw) == 'not_approved', raw


@pytest.mark.parametrize('raw', [
    'W', 'P', 'w', 'Pending', 'Pending\n( W )', 'Pending (W)', 'Under Review', 'In Review',
    'U.A', 'UA', 'Under approval', 'Awaiting reply', 'Awaiting approval', 'Awaiting review',
    'Pending review', 'Pending approval', 'Pending with consultant',
])
def test_under_review(raw):
    assert classify_action_code(raw) == 'under_review', raw


@pytest.mark.parametrize('raw', [None, '', '   ', 'B/C', '…', 'S', 'L', 'IN', 'OUT', 'TBD',
                                 'Kindly find a copy of the drawings attached for your review and approval'])
def test_unknown_or_ambiguous(raw):
    # 'B/C' is two codes at once; 'S'/'L' are superseded/latest flags, not review codes;
    # a long free-text comment must not be read as a code just because it contains 'a'.
    assert classify_action_code(raw) is None, raw


@pytest.mark.parametrize('raw', [
    'Under preparation', 'Under Preparation by subcontractor', 'In preparation', 'In progress',
    'Work in progress', 'Pending submission', 'Awaiting submission', 'Pending Submittal',
    'Not yet submitted', 'Not yet', 'To be submitted', 'Yet to submit', 'Not submitted',
])
def test_not_sent_yet_is_not_a_review_status(raw):
    # ELOG-1: these mean the drawing has NOT gone to the consultant — they are not
    # "under review" (the old bare 'under' / 'progress' / 'pend' matches read them so, and
    # the reader then counted those drawings as submitted). None = shown as "not recognised".
    assert classify_action_code(raw) is None, raw


def test_status_says_sent_only_for_explicit_reviewer_side_wording():
    from p6_evm.classify import status_says_sent
    for raw in ('Under Review', 'In review', 'Under approval', 'U.A', 'Awaiting reply',
                'Awaiting approval', 'Pending review', 'Submitted for approval'):
        assert status_says_sent(raw), raw
    # a bare code / 'Pending' does not prove the drawing went out; nor does "not sent" wording
    for raw in ('W', 'P', 'Pending', 'Pending (W)', None, '', 'Pending submission',
                'Under preparation', 'Not yet submitted', 'In progress'):
        assert not status_says_sent(raw), raw


def test_reviewed_no_exceptions_is_not_under_review():
    # the false positive this scope fixes: 'review' used to win → under review
    assert classify_action_code('Reviewed – no exceptions taken') == 'approved'


def test_legend_overrides_defaults():
    # a consultant scheme where C means "approved with comments" (not the default)
    legend = {'A': 'approved', 'B': 'approved', 'C': 'approved', 'R': 'not_approved', 'H': 'under_review'}
    assert classify_action_code_with_legend('C', legend) == 'approved'
    assert classify_action_code_with_legend('(C)', legend) == 'approved'
    assert classify_action_code_with_legend('Code C', legend) == 'approved'
    assert classify_action_code_with_legend('R', legend) == 'not_approved'
    assert classify_action_code_with_legend('H', legend) == 'under_review'
    # a code the legend doesn't list falls back to the default rule
    assert classify_action_code_with_legend('D', legend) == 'not_approved'
    assert classify_action_code_with_legend('Pending', legend) == 'under_review'


def test_legend_ignore_verdict_means_not_counted():
    legend = {'N': 'ignore', 'A': 'approved'}
    assert classify_action_code_with_legend('N', legend) is None
    assert classify_action_code_with_legend('A', legend) == 'approved'


def test_legend_code_inside_words():
    legend = {'B': 'approved', 'W': 'under_review'}
    assert classify_action_code_with_legend('Approved (Code B)', legend) == 'approved'
    assert classify_action_code_with_legend('Pending (W)', legend) == 'under_review'


def test_legend_empty_or_none_is_default_rule():
    assert classify_action_code_with_legend('B', None) == 'approved'
    assert classify_action_code_with_legend('3', {}) == 'not_approved'
    assert classify_action_code_with_legend(None, {'A': 'approved'}) is None
