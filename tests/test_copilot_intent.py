"""Typed-question intent-matching (V2 Slice 6). A freely-typed question is mapped to the
nearest repertoire question by keyword; planning-only intents aren't offered in Management
mode, and gibberish falls through to the graceful deferral."""
from p6_copilot.intent import match_intent


def test_claim_words_map_to_eot():
    for q in ['can we claim?', 'is an EOT likely', 'time extension', 'entitlement to more time']:
        qid, matched = match_intent(q, 'management')
        assert qid == 'eot_likely' and matched, q


def test_recovery_and_risk_words_map():
    assert match_intent('how do we catch up?', 'management')[0] == 'recovery'
    assert match_intent('what are the biggest risks', 'management')[0] == 'risks'


def test_why_is_the_broad_catch_for_lateness():
    assert match_intent('why are we behind schedule', 'management')[0] == 'why_delayed'


def test_planning_only_intents_only_offered_in_planning():
    qid, _ = match_intent('which delay-analysis method should I use', 'management')
    assert qid != 'delay_method'                       # not offered to a manager
    qid, matched = match_intent('which delay-analysis method should I use', 'planning')
    assert qid == 'delay_method' and matched


def test_gibberish_and_empty_do_not_match():
    assert match_intent('', 'management') == (None, False)
    assert match_intent('xq', 'management') == (None, False)
    assert match_intent('zzz qwerty foobar', 'management') == (None, False)
