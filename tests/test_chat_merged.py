"""The 15 merged chat questions: catalog, router, builders, service, network analysis and the engine fixes.

Uses synthetic facts and the repo fixture only — never the user's app database."""
import copy
import importlib
import json
import os
import re

import pytest

from p6_chat import merged, router
from p6_chat.merged import _kit2 as K2

IDS = [f'q{i:02d}' for i in range(1, 16)]
FIXTURE = os.path.join(os.path.dirname(__file__), 'fixtures', 'minimal.xml')


def _facts(**over):
    F = {
        'ok': True, 'snapshot_id': 1, 'project_name': 'Test Terminal', 'data_date': '31-Mar-2025',
        'activity_count': 900, 'calendar_count': 3, 'baseline_finish': '01-Jun-2026', 'forecast_finish': '15-Sep-2026',
        'delay_days': 30, 'delay_weeks': 6, 'behind': True, 'ahead': False, 'on_track': False,
        'spi': 0.5, 'cpi': 1.0, 'pv': 1000.0, 'ev': 500.0, 'ac': 500.0, 'variance': -500.0, 'cost_derived': True,
        'pace_pct': 50, 'planned_pct': 55, 'actual_pct': 40,
        'disciplines': [{'name': 'Civil Works', 'weight': 0.80, 'planned': 55, 'actual': 38, 'gap': 17},
                        {'name': 'Design', 'weight': 0.05, 'planned': 90, 'actual': 20, 'gap': 70},
                        {'name': 'Engineering', 'weight': 0.15, 'planned': 100, 'actual': 100, 'gap': 0}],
        'worst_discipline': {'name': 'Civil Works', 'weight': 0.80, 'planned': 55, 'actual': 38, 'gap': 17},
        'widest_gap': {'name': 'Design', 'weight': 0.05, 'planned': 90, 'actual': 20, 'gap': 70},
        'top_gaps': [], 'trend': None, 'history': [], 'has_history': False, 'has_audit': True, 'audit': {},
        'float_grade': 'Needs Attention', 'float_above': 120, 'float_pct': 13.0, 'float_threshold': 44, 'max_float': 88,
        'avg_float': 7.0, 'neg_float_count': 60, 'neg_float_pct': 6.7, 'neg_float_grade': 'Needs Attention',
        'oos_count': 9, 'oos_pct': 1.0, 'critical_oos': 1, 'oos_grade': 'Good', 'cpli_critical_count': 300,
        'cpli_critical_pct': 33.0, 'driving_path_count': 310, 'cpli_grade': 'Needs Attention',
        'cpli_density_grade': 'Moderate', 'dangling_count': 5, 'dangling_pct': 0.6, 'dangling_grade': 'Excellent',
        'open_ends': 2, 'open_ends_grade': 'Good', 'hard_constraints_computable': False,
        'value_gap': None, 'submittals': None,
    }
    F.update(over)
    return F


AHEAD = dict(delay_days=-12, delay_weeks=2, behind=False, ahead=True, spi=1.06, pace_pct=106, cpi=0.93,
             cost_derived=False, planned_pct=50, actual_pct=53, forecast_finish='14-May-2026')
NO_FILE = {'ok': False, 'error': 'file not found'}
ROOTS_WORDS = re.compile(r'Silo|INP\.EMP|Layout Approval|CONS\.|KD\.CE|CM\.1020|Roots|02-May-2027', re.I)
FORBIDDEN = re.compile(r'\b(jetty|fender|berth|pile[- ]driving|marine terminal)\b|\$\d|\bdollars?\b', re.I)


# ── catalog ─────────────────────────────────────────────────────────────────────
def test_catalog_has_15_questions_covering_all_182_originals_once():
    cat = merged.catalog()
    assert [q['id'] for q in cat['questions']] == IDS
    originals = [o['id'] for q in cat['questions'] for o in q['originals']]
    assert len(originals) == len(set(originals)) == 182
    lib = json.load(open(os.path.join(os.path.dirname(merged.__file__), '..', 'data', 'questions.json'), encoding='utf-8'))
    assert set(originals) == {q['id'] for t in lib['catalog'] for q in t['questions']}
    assert sum(len(q['covers']) for q in cat['questions']) == 35
    assert all(q['group'] in cat['groups'] for q in cat['questions'])


def test_catalog_is_currency_neutral():
    assert not re.search(r'\$\d|\bdollars?\b', json.dumps(merged.catalog()), re.I)


# ── router ──────────────────────────────────────────────────────────────────────
ROUTES = [('are we behind schedule?', 'q01'), ('how are we doing', 'q01'), ('is our progress on plan', 'q01'),
          ('when will the project finish', 'q02'), ('will we hit the handover date', 'q02'),
          ('which milestones are late', 'q02'), ('why are we late', 'q03'),
          ('is the delay genuine or did someone fiddle the logic', 'q03'), ('what is on the critical path', 'q04'),
          ('how much float do we have', 'q04'), ('how do I catch up the lost time', 'q05'), ('run a what-if', 'q05'),
          ('does the schedule pass DCMA', 'q06'), ('what changed in the new baseline revision', 'q07'),
          ('are we over budget', 'q08'), ('is manpower enough', 'q09'), ('which long lead items are critical', 'q10'),
          ('which subcontractor is behind', 'q11'), ('is commissioning in the schedule', 'q11'),
          ('are any activities missing', 'q12'), ('can we claim an extension of time', 'q13'),
          ('is the client causing delay', 'q13'), ('how many weather days did we lose', 'q14'),
          ('give me a board summary', 'q15'), ('what should I tell the client this month', 'q15')]


@pytest.mark.parametrize('text,want', ROUTES)
def test_router_routes_everyday_phrasing(text, want):
    assert router.route(text)['qid'] == want


@pytest.mark.parametrize('text,want,kind', [('why?', 'q03', 'cause'), ('how do I fix it?', 'q05', 'topic'),
                                            ('more detail', 'q01', 'expand'), ('can we claim?', 'q13', 'topic')])
def test_router_keeps_the_thread(text, want, kind):
    r = router.route(text, last_qid='q01')
    assert (r['qid'], r['followup']) == (want, kind)


def test_router_says_so_when_it_does_not_understand():
    r = router.route('hello')
    assert not r['matched'] and r['qid'] is None


def test_router_focuses_the_exact_original_sub_question():
    r = router.route('how many weather days did we lose this month and what did it do to the finish')
    assert r['qid'] == 'q14' and r['focus'] and r['focus'].startswith('t15')


# ── builders ────────────────────────────────────────────────────────────────────
def _built():
    return [q for q in IDS if os.path.exists(os.path.join(os.path.dirname(merged.__file__), q + '.py'))]


def test_all_15_builders_present_and_importable():
    assert _built() == IDS
    assert merged.load_errors() == {}


@pytest.mark.parametrize('qid', IDS)
@pytest.mark.parametrize('case', ['behind', 'ahead', 'nofile'])
def test_builder_contract(qid, case):
    mod = importlib.import_module(f'p6_chat.merged.{qid}')
    F = _facts(**AHEAD) if case == 'ahead' else _facts()
    a = mod.build(F, NO_FILE, 'planning')
    assert a['verdict'] and len(a['sections']) >= 2
    for s in a['sections']:
        t = s.get('table')
        if t:
            assert all(len(r) == len(t['cols']) for r in t['rows']), s['label']
    for d in a.get('drilldowns', []):
        assert d['to'] in IDS and d['to'] != qid
    blob = json.dumps(a, ensure_ascii=False)
    assert not ROOTS_WORDS.search(blob), ROOTS_WORDS.findall(blob)
    assert not FORBIDDEN.search(blob), FORBIDDEN.findall(blob)
    if case == 'ahead':
        assert not re.search(r'\b\d+ working days? (late|behind)\b', blob)
    if F.get('cost_derived'):
        assert not re.search(r"\b(is|are|we're|running) on budget\b", blob, re.I)


def test_merged_build_without_project_asks_for_the_file():
    a = merged.build('q01', {'ok': False}, NO_FILE)
    assert 'P6 schedule' in a['verdict']


# ── service ─────────────────────────────────────────────────────────────────────
def test_answer_merged_attaches_every_original_and_thinking(monkeypatch):
    from p6_chat import qa_service, facts, analysis, copilot
    monkeypatch.setattr(facts, 'build_facts', lambda sid: _facts())
    monkeypatch.setattr(analysis, 'network', lambda sid=None, xml_path=None: NO_FILE)
    monkeypatch.setattr(copilot, 'project_brain', lambda sid: {'project_name': 'Test', 'delay_days': 30, 'behind': True,
                                                               'disciplines': [], 'worst_discipline': None})
    out = qa_service.answer_merged(1, 'q13')
    a = out['answer']
    assert out['ok'] and out['v'] == 2
    assert len(a['specific']) == len(merged.entry('q13')['originals'])
    assert all(s['headline'] for s in a['specific'])
    assert a['thinking'] and a['covers'] and a['question'] == merged.entry('q13')['q']
    assert any(s.get('tool') == 'tia' for s in a['specific'])


def test_ask_text_routes_and_focuses(monkeypatch):
    from p6_chat import qa_service, facts, analysis, copilot
    monkeypatch.setattr(facts, 'build_facts', lambda sid: _facts())
    monkeypatch.setattr(analysis, 'network', lambda sid=None, xml_path=None: NO_FILE)
    monkeypatch.setattr(copilot, 'project_brain', lambda sid: {})
    out = qa_service.ask_text(1, 'will we hit the handover date?')
    assert out['matched'] and out['answer']['id'] == 'q02'
    miss = qa_service.ask_text(1, 'hello')
    assert not miss['matched'] and miss['suggest']


def test_library15_payload():
    from p6_chat import qa_service
    lib = qa_service.library15()
    assert lib['ok'] and len(lib['questions']) == 15 and lib['counts']['originals'] == 182


# ── network analysis ────────────────────────────────────────────────────────────
def test_network_on_fixture_is_ok_and_plain():
    from p6_chat.analysis import network
    N = network(xml_path=FIXTURE)
    assert N['ok'] and N['activity_count'] > 0
    json.dumps(N)                                   # JSON-ready
    assert network(xml_path='does-not-exist.xml')['ok'] is False


# ── chat answer-engine fixes ────────────────────────────────────────────────────
def test_cost_derived_is_never_called_on_budget():
    from p6_chat import qa
    blob = json.dumps([qa.answer(q, _facts(), 'planning') for q in ('t00q00', 't00q01', 't00q08', 't16q00', 't16q01')])
    assert not re.search(r'essentially on budget|cost is holding|holding close to budget|cost is stable', blob, re.I)


NONE_LEAK = re.compile(r'(~|\*\*|of |at |about |to |vs |the |finish |date )None\b|None (baseline|finish|forecast)|\bnan\b')
MARINE = re.compile(r'\b(jetty|fenders?|berth\w*|bollards?|marine piling|silo steel)\b|\bmarine, piling\b', re.I)


def _library_ids():
    return [o['id'] for q in merged.catalog()['questions'] for o in q['originals'] if not o.get('cap')]


def test_no_answer_prints_none_when_the_finish_dates_are_unknown():
    from p6_chat import qa
    F = _facts(baseline_finish=None, forecast_finish=None)
    blob = json.dumps([qa.answer(i, F, 'planning') for i in _library_ids()] +
                      [merged.build(q, F, NO_FILE) for q in IDS], ensure_ascii=False)
    assert not NONE_LEAK.search(blob), NONE_LEAK.findall(blob)[:5]


def test_library_answers_carry_no_marine_nouns_on_a_generic_project():
    from p6_chat import qa
    blob = json.dumps([qa.answer(i, _facts(), 'planning') for i in _library_ids()], ensure_ascii=False)
    assert not MARINE.search(blob), MARINE.findall(blob)[:5]


def test_missing_finish_dates_are_filled_from_the_p6_finish_milestone():
    from p6_chat.qa_service import _backfill_finish
    F = _facts(baseline_finish=None, forecast_finish=None)
    _backfill_finish(F, {'ok': True, 'finish_milestone': {'baseline_finish': '09-Feb-2027', 'finish': '02-May-2027'}})
    assert (F['baseline_finish'], F['forecast_finish']) == ('09-Feb-2027', '02-May-2027')
    kept = _facts()
    _backfill_finish(kept, {'ok': True, 'finish_milestone': {'baseline_finish': 'x', 'finish': 'y'}})
    assert (kept['baseline_finish'], kept['forecast_finish']) == ('01-Jun-2026', '15-Sep-2026')
    _backfill_finish(F, NO_FILE)                    # no file → nothing invented


def test_completed_discipline_is_not_offered_as_spare_effort():
    from p6_chat import qa
    a = qa.answer('t09q01', _facts(), 'planning')
    assert '**Engineering** are on or ahead of plan' not in ' '.join(a['body'])
