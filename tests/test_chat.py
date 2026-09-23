"""Unit tests for the Offline AI Chat backend (p6_chat).

Covers the read-path pieces that must be correct regardless of whether a local
brain is installed: the question library, grounding text, the prompt assembly,
and the service's brain / fallback branches (brain calls are stubbed so tests
never touch a network or a model).
"""
import p6_chat
from p6_chat import library, grounding, knowledge, service, llm, charts


SAMPLE = {
    'project_name': 'Grain Bulk Terminal',
    'data_date': '2026-07-19',
    'activity_count': 1503,
    'spi': 0.658, 'cpi': 0.94,
    'overall_planned_pct': 61.4, 'overall_actual_pct': 40.4,
    'pv': 61400000, 'ev': 40430000, 'ac': 43010000, 'variance': -20970000,
    'delay_days': 47,
    'categories': {
        'Marine & Jetty Works': {'weight': 40, 'planned_pct': 70, 'actual_pct': 45},
        'Silo Structure': {'weight': 30, 'planned_pct': 55, 'actual_pct': 40},
    },
}


# ── library ──────────────────────────────────────────────────────────────────
def test_library_loads_full_catalogue():
    lib = library.library()
    total = sum(len(t['questions']) for t in lib['themes'])
    assert total == 182
    assert len(lib['themes']) == 17
    assert len(lib['roles']) == 8
    assert lib['counts']['total'] == 182
    assert lib['counts']['today'] + lib['counts']['in_progress'] + lib['counts']['gap'] == 182


def test_library_roles_have_counts_and_no_answers_leak():
    lib = library.library()
    keys = {r['key'] for r in lib['roles']}
    assert {'pm', 'plmgr', 'planner', 'pd', 'tom', 'contracts', 'cm', 'commercial'} <= keys
    assert all(r['count'] > 0 for r in lib['roles'])
    # bundled sample answers must NOT be shipped to the browser
    for t in lib['themes']:
        for q in t['questions']:
            assert 'answer_full' not in q and 'answer_sketch' not in q
            # safe payload only: the question, its grounding hint, status, roles, and the
            # optional Copilot capability tags (cap/qid/mode) — never a bundled answer.
            assert set(q) == {'q', 'grounds', 'status', 'role_keys', 'cap', 'qid', 'mode'}


def test_library_find_exact_returns_bundled_answer():
    lib = library.library()
    q = lib['themes'][0]['questions'][0]['q']
    entry = library.find(q)
    assert entry and entry.get('answer_full')


# ── grounding ─────────────────────────────────────────────────────────────────
def test_grounding_includes_real_numbers():
    g = grounding.build(SAMPLE)
    assert grounding.available(SAMPLE)
    for token in ('Grain Bulk Terminal', 'SPI 0.66', 'CPI 0.94', '47 working days',
                  'Marine & Jetty Works'):
        assert token in g, token


def test_grounding_empty_result():
    assert grounding.build({}) == ''
    assert grounding.build(None) == ''
    assert not grounding.available({})


# ── knowledge / prompt ────────────────────────────────────────────────────────
def test_system_prompt_has_persona_and_tool_knowledge():
    sp = knowledge.system_prompt()
    assert 'PROJECT-CONTROLS MANAGER' in sp             # expert persona
    assert 'DETAILED' in sp                             # max-detail rule
    assert 'Baseline Revision Comparison' in sp         # feature knowledge present
    assert 'indicators' in sp.lower()                   # claims rule


def test_build_prompt_contains_grounding_role_and_question():
    p = knowledge.build_prompt('Why are we late?', grounding.build(SAMPLE), 'Project Director')
    assert 'Why are we late?' in p
    assert 'Project Director' in p
    assert 'SPI 0.66' in p


# ── service (brain stubbed) ────────────────────────────────────────────────────
def test_ask_uses_brain_when_ready(monkeypatch):
    monkeypatch.setattr(llm, 'status', lambda: {'ready': True, 'engine': True, 'model': True})
    monkeypatch.setattr(llm, 'generate', lambda system, user, **k: 'DETAILED GROUNDED ANSWER')
    out = service.ask('Why is the project delayed?', SAMPLE, role='pm')
    assert out['ok'] and out['source'] == 'brain'
    assert out['answer'] == 'DETAILED GROUNDED ANSWER'
    assert out['grounded'] is True


def test_ask_fallback_when_brain_not_ready(monkeypatch):
    monkeypatch.setattr(llm, 'status', lambda: {'ready': False, 'engine': False, 'model': False,
                                                'detail': 'no runtime'})
    out = service.ask('What are my best recovery options?', SAMPLE, role='plmgr')
    assert out['ok'] and out['source'] == 'setup' and out['needs_setup'] is True
    # honest fallback shows the real snapshot, not a canned answer
    assert 'SPI' in out['answer'] and '47 working days' in out['answer']


def test_ask_no_project(monkeypatch):
    monkeypatch.setattr(llm, 'status', lambda: {'ready': False, 'engine': False, 'model': False})
    out = service.ask('Why are we delayed?', {}, role=None)
    assert out['ok'] and 'Send me your P6 schedule' in out['answer']


def test_ask_empty_question():
    out = service.ask('   ', SAMPLE)
    assert out['ok'] is False


# ── llm status is offline-safe (engine not installed in the test env) ──────────
def test_llm_status_offline_safe():
    st = llm.status()
    assert st['ready'] is False                                        # must not raise
    for k in ('engine', 'model', 'model_key', 'options'):
        assert k in st
    assert isinstance(st['options'], list) and len(st['options']) >= 2


def test_model_choice_default_and_switch():
    assert llm.get_model_key() in llm.MODELS
    prev = llm.get_model_key()
    try:
        llm.set_model_key('fast')
        assert llm.get_model_key() == 'fast' and llm.status()['model_key'] == 'fast'
        llm.set_model_key('detailed')
        assert llm.status()['model_key'] == 'detailed'
    finally:
        llm.set_model_key(prev)


def test_answer_stream_fallback(monkeypatch):
    monkeypatch.setattr(llm, 'status', lambda: {'ready': False, 'engine': False, 'model': False})
    meta, gen = service.answer_stream('Why is the project delayed?', SAMPLE, role='pm')
    assert meta['ok'] and meta['source'] == 'setup' and 'charts' in meta
    text = ''.join(gen)
    assert 'SPI' in text or 'brain' in text.lower()


def test_answer_stream_uses_brain(monkeypatch):
    monkeypatch.setattr(llm, 'status', lambda: {'ready': True, 'engine': True, 'model': True, 'model_name': 'X'})
    monkeypatch.setattr(llm, 'generate_stream', lambda system, user, **k: iter(['Detailed ', 'grounded ', 'answer.']))
    meta, gen = service.answer_stream('How are we performing?', SAMPLE, role='pd')
    assert meta['source'] == 'brain' and any(c['type'] == 'kpi' for c in meta['charts'])
    assert ''.join(gen) == 'Detailed grounded answer.'


def test_public_api_surface():
    assert callable(p6_chat.get_library) and callable(p6_chat.ask)
    assert callable(p6_chat.brain_status) and callable(p6_chat.brain_setup)


# ── charts (grounded, deterministic) ───────────────────────────────────────────
def test_charts_kpi_for_status_question():
    cs = charts.charts_for('How are we performing on SPI and CPI?', SAMPLE)
    kpi = next((c for c in cs if c['type'] == 'kpi'), None)
    assert kpi is not None
    labels = [i['label'] for i in kpi['items']]
    assert {'SPI', 'CPI', 'Progress', 'Delay'} <= set(labels)
    delay = next(i for i in kpi['items'] if i['label'] == 'Delay')
    assert delay['value'] == '+47 wd' and delay['tone'] == 'bad'


def test_charts_bars_for_discipline_question():
    cs = charts.charts_for('show me progress by discipline breakdown', SAMPLE)
    bars = next((c for c in cs if c['type'] == 'bars'), None)
    assert bars is not None
    names = [r['name'] for r in bars['items']]
    assert 'Marine & Jetty Works' in names
    mj = next(r for r in bars['items'] if r['name'] == 'Marine & Jetty Works')
    assert mj['planned'] == 70 and mj['actual'] == 45


def test_charts_empty_without_result():
    assert charts.charts_for('anything', {}) == []
    assert charts.charts_for('what is the weather', SAMPLE) == []   # no matching intent


def test_service_ask_attaches_grounded_charts(monkeypatch):
    monkeypatch.setattr(llm, 'status', lambda: {'ready': False, 'engine': False, 'model': False})
    out = service.ask('How are we performing (SPI/CPI)?', SAMPLE, role='pm')
    assert 'charts' in out and any(c['type'] == 'kpi' for c in out['charts'])
