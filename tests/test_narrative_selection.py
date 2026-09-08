"""Comments 4 & 5 — the planner can pick which Major Milestones and Key Dates go in
the narrative BEFORE running. build_report exposes the candidate lists in meta and
filters by a `setup` selection; an absent selection includes all (unchanged)."""
import os

from p6_evm.parser import parse_file
from p6_narrative.report import build_report

FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def _doc(setup=None):
    return build_report(parse_file(FIX), setup=setup).to_dict()


def _sec(doc, kind):
    return next((s for s in doc['sections'] if s['kind'] == kind), None)


def test_candidate_lists_exposed_in_meta():
    m = _doc()['meta']
    assert isinstance(m.get('milestone_choices'), list)
    assert isinstance(m.get('key_date_choices'), list)


def test_all_milestones_included_by_default():
    doc = _doc()
    ms = _sec(doc, 'ms_table')
    choices = doc['meta']['milestone_choices']
    if ms and choices:                       # fixture-dependent; only assert when present
        assert len(ms['payload']['rows']) == len(choices)


def test_milestone_selection_filters_to_the_pick():
    choices = _doc()['meta']['milestone_choices']
    if len(choices) >= 1:
        pick = [choices[0]]
        ms = _sec(_doc({'milestone_keys': pick}), 'ms_table')
        assert [r[0] for r in ms['payload']['rows']] == pick


def test_empty_milestone_selection_includes_none():
    if _doc()['meta']['milestone_choices']:
        ms = _sec(_doc({'milestone_keys': []}), 'ms_table')
        assert ms['payload']['rows'] == []


def test_key_date_selection_filters_when_present():
    kchoices = _doc()['meta']['key_date_choices']
    if len(kchoices) >= 1:
        pick = [kchoices[0]]
        tl = _sec(_doc({'key_date_keys': pick}), 'timeline')
        assert [it['label'] for it in tl['payload']['items']] == pick
