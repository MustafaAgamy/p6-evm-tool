"""Planning-mode answers (V2 Slice 4) + the offline knowledge base. Planning answers carry
full technical depth and cite the right method/clause; the knowledge base is authoritative
(AACE 29R-03, FIDIC, SCL, DCMA) and the project-type read degrades gracefully.
"""
from p6_copilot.context import build_context
from p6_copilot.answers import answer
from p6_copilot import knowledge as kb

RESULT = {
    'project_name': 'Metro L3',
    'data_date': '2025-03-03T00:00:00',
    'baseline_finish': '2027-01-15T00:00:00',
    'expected_finish': '2027-03-12T00:00:00',
    'delay_days': 40,
    'spi': 0.85,
    'overall_planned_pct': 0.34,
    'overall_actual_pct': 0.29,
    'categories': {
        'MEP':        {'weight': 0.4, 'planned_pct': 0.34, 'actual_pct': 0.12},
        'Civil':      {'weight': 0.5, 'planned_pct': 0.60, 'actual_pct': 0.58},
        'Milestones': {'weight': 0.0, 'planned_pct': 0.0,  'actual_pct': 0.0},
    },
}
AUDIT = {'modules': {'out_of_sequence': {'kpis': {'oos_count': 3}}, 'float': {'grade': 'Critical'}}}


def _text(a):
    return ' '.join([a['headline'], *a['body'], *a['advice']])


# ── knowledge base ──────────────────────────────────────────────────────────

def test_recommend_method_picks_tia_when_behind_and_cites_aace():
    rec = kb.recommend_method(build_context(RESULT))
    assert rec['method']['key'] == 'tia'
    assert 'MIP 3.7' in rec['method']['aace']
    assert 'Time Impact Analysis' in rec['method']['name']


def test_contract_clauses_are_correct_per_edition():
    assert kb.contract('fidic_2017')['eot_clause'] == 'Sub-Clause 8.5'
    assert kb.contract('fidic_2017')['notice_clause'] == 'Sub-Clause 20.2'
    assert kb.contract('fidic_1999')['eot_clause'] == 'Sub-Clause 8.4'
    assert kb.contract('fidic_1999')['notice_clause'] == 'Sub-Clause 20.1'
    assert kb.contract('anything-unknown')['key'] == 'fidic_2017'   # sensible default


def test_all_four_delay_methods_present():
    for key in ('tia', 'windows', 'iap', 'as_built'):
        m = kb.method(key)
        assert m and m['name'] and m['aace'] and m['plain']


def test_detect_project_type_matches_a_seed_and_degrades_gracefully():
    hit = kb.detect_project_type(build_context({**RESULT, 'project_name': 'Acme Factory'}))
    assert hit and hit['type'] == 'Factory'          # 'factory' signature matches the seed KB
    miss = kb.detect_project_type(build_context({**RESULT, 'project_name': 'Zeta One'}))
    assert miss is None                               # no signal -> None, never an exception


# ── planning answers ────────────────────────────────────────────────────────

def test_planning_mode_answers_are_not_the_generic_deferral():
    ctx = build_context(RESULT, audit=AUDIT)
    for qid in ('why_delayed', 'critical_driver', 'recovery', 'risks', 'delay_method', 'project_needs'):
        a = answer(qid, ctx, 'planning')
        assert "can't answer that one yet" not in a['headline'].lower(), qid
        assert a['headline'] and a['body']


def test_why_delayed_planning_is_technical_and_names_the_driver():
    t = _text(answer('why_delayed', build_context(RESULT, audit=AUDIT), 'planning'))
    assert 'MEP' in t and 'SPI' in t
    assert 'critical path' in t.lower()


def test_recovery_planning_lists_the_levers():
    t = _text(answer('recovery', build_context(RESULT), 'planning')).lower()
    assert 'crash' in t and ('re-sequence' in t or 'fast-track' in t)


def test_delay_method_answer_cites_method_and_fidic_clause():
    t = _text(answer('delay_method', build_context(RESULT), 'planning'))
    assert 'Time Impact Analysis' in t and 'Sub-Clause 8.5' in t
    assert 'SCL' in t                                   # standard cited


def test_eot_planning_answer_cites_method_and_stays_careful():
    t = _text(answer('eot_likely', build_context(RESULT, audit=AUDIT), 'planning'))
    assert 'Time Impact Analysis' in t and 'FIDIC' in t and 'Entitlement' in t
    assert 'entitled' not in t.lower()                  # never asserts entitlement


def test_project_needs_answer_names_the_type_or_defers_cleanly():
    hit = answer('project_needs', build_context({**RESULT, 'project_name': 'Acme Factory'}), 'planning')
    assert 'Factory' in _text(hit)
    miss = answer('project_needs', build_context({**RESULT, 'project_name': 'Zeta One'}), 'planning')
    assert 'Constructability' in _text(miss)             # graceful pointer, not an error
