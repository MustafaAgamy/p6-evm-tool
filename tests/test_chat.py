"""Unit tests for the Offline AI Chat backend (p6_chat).

Covers the read-path pieces that must be correct regardless of whether a local
brain is installed: the question library, grounding text, the prompt assembly,
and the service's brain / fallback branches (brain calls are stubbed so tests
never touch a network or a model).
"""
import p6_chat
from p6_chat import library, grounding, knowledge, service, llm


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
    assert total == 168
    assert len(lib['themes']) == 16
    assert len(lib['roles']) == 8
    assert lib['counts']['total'] == 168
    assert lib['counts']['today'] + lib['counts']['in_progress'] + lib['counts']['gap'] == 168


def test_library_roles_have_counts_and_no_answers_leak():
    lib = library.library()
    keys = {r['key'] for r in lib['roles']}
    assert {'pm', 'plmgr', 'planner', 'pd', 'tom', 'contracts', 'cm', 'commercial'} <= keys
    assert all(r['count'] > 0 for r in lib['roles'])
    # bundled sample answers must NOT be shipped to the browser
    for t in lib['themes']:
        for q in t['questions']:
            assert 'answer_full' not in q and 'answer_sketch' not in q
            assert set(q) == {'q', 'grounds', 'status', 'role_keys'}


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
    assert 'SENIOR PLANNING MANAGER' in sp
    assert 'Baseline Revision Comparison' in sp        # feature knowledge present
    assert 'indicators' in sp.lower()                  # claims rule


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
    assert out['ok'] and 'Import a P6 schedule' in out['answer']


def test_ask_empty_question():
    out = service.ask('   ', SAMPLE)
    assert out['ok'] is False


# ── llm status is offline-safe (no server in test env) ─────────────────────────
def test_llm_status_offline_safe():
    st = llm.status()
    assert st['ready'] is False and 'base_url' in st       # must not raise


def test_public_api_surface():
    assert callable(p6_chat.get_library) and callable(p6_chat.ask)
    assert callable(p6_chat.brain_status) and callable(p6_chat.brain_setup)
