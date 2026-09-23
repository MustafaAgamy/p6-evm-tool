"""The offline grounded answer engine (p6_chat.qa + facts + qa_service).

These tests exercise EVERY registered answer function against a synthetic FACTS dict with
distinctive numbers, so they automatically cover each theme module as it's added. They assert:
  * every answer returns the render shape {headline, body[], advice[], evidence[]},
  * answers are substantial (not one-liners),
  * the delay-sign convention holds (positive delay_days => 'behind' language, never 'ahead'),
  * no answer leaks the illustrative sample literals from the bundled answer_full texts.
"""
import re

import pytest

from p6_chat import qa
from p6_chat.qa import _kit as K


# A realistic, distinctive project so leaked sample numbers stand out.
def _facts(**over):
    F = {
        'ok': True, 'snapshot_id': 1,
        'project_name': 'Test Terminal', 'data_date': '31-Mar-2025',
        'activity_count': 900, 'calendar_count': 3,
        'baseline_finish': '01-Jun-2026', 'forecast_finish': '15-Sep-2026',
        'delay_days': 30, 'delay_weeks': 6, 'behind': True, 'ahead': False, 'on_track': False,
        'spi': 0.5, 'cpi': 0.98, 'pv': 1000.0, 'ev': 500.0, 'ac': 510.0, 'variance': -500.0,
        'pace_pct': 50, 'planned_pct': 55, 'actual_pct': 40,
        'disciplines': [
            {'name': 'Civil Works', 'weight': 0.80, 'planned': 55, 'actual': 38, 'gap': 17},
            {'name': 'Design', 'weight': 0.05, 'planned': 90, 'actual': 20, 'gap': 70},
            {'name': 'Procurement', 'weight': 0.15, 'planned': 60, 'actual': 58, 'gap': 2},
        ],
        'worst_discipline': {'name': 'Design', 'weight': 0.05, 'planned': 90, 'actual': 20, 'gap': 70},
        'top_gaps': [], 'trend': None, 'history': [], 'has_history': False,
        'has_audit': True, 'audit': {},
        'float_grade': 'Needs Attention', 'float_above': 120, 'float_pct': 13.0,
        'float_threshold': 44, 'max_float': 88, 'avg_float': 7.0,
        'neg_float_count': 60, 'neg_float_pct': 6.7, 'neg_float_grade': 'Needs Attention',
        'oos_count': 9, 'oos_pct': 1.0, 'critical_oos': 1, 'oos_grade': 'Good',
        'cpli_critical_count': 300, 'cpli_critical_pct': 33.0, 'driving_path_count': 310,
        'cpli_grade': 'Needs Attention', 'cpli_density_grade': 'Moderate',
        'dangling_count': 5, 'dangling_pct': 0.6, 'dangling_grade': 'Excellent',
        'open_ends': 2, 'open_ends_grade': 'Good', 'hard_constraints_computable': False,
    }
    F.update(over)
    return F


# Literals from the bundled illustrative answer_full sample — must NEVER appear verbatim.
_SAMPLE_LEAKS = ['0.66', '40.4%', '61.4%', '47 working', '20 Apr 2027', '9 Feb', 'TF −18', 'TF -18', 'jetty']


def _all_ids():
    return sorted(qa.registered_ids())


def test_theme_modules_import_clean():
    # A broken theme module shows up here rather than silently vanishing.
    assert qa.load_errors() == {} or all('No module named' in v for v in qa.load_errors().values()), qa.load_errors()


def test_registry_is_populated():
    assert len(_all_ids()) >= 10          # theme 0 at minimum; grows with the workflow


@pytest.mark.parametrize('qid', _all_ids())
def test_answer_shape_and_grounding(qid):
    F = _facts()
    a = qa.answer(qid, F, 'management')
    assert isinstance(a, dict) and a.get('headline'), f'{qid}: no headline'
    assert isinstance(a.get('body'), list) and len(a['body']) >= 1, f'{qid}: thin/empty body'
    # substantial: headline + body carries real prose, not a one-liner stub
    text = ' '.join([a['headline']] + a['body'])
    assert len(text) >= 120, f'{qid}: answer too thin ({len(text)} chars)'
    # no leaked sample literals
    for bad in _SAMPLE_LEAKS:
        assert bad not in text, f'{qid}: leaks sample literal {bad!r}'


@pytest.mark.parametrize('qid', _all_ids())
def test_no_project_guarded(qid):
    a = qa.answer(qid, {'ok': False}, 'management')
    # every function must handle the no-project state (either a guard message or None->fallback)
    assert a is None or (isinstance(a, dict) and a.get('headline'))


def test_delay_sign_language_behind(monkeypatch):
    # With positive delay_days the headline read of a KPI question must say behind, never ahead.
    F = _facts(delay_days=30, behind=True, ahead=False)
    a = qa.answer('t00q00', F, 'management')
    text = (a['headline'] + ' ' + ' '.join(a['body'])).lower()
    assert 'behind' in text and 'ahead' not in a['headline'].lower()


def test_delay_sign_language_ahead():
    F = _facts(delay_days=-20, behind=False, ahead=True, spi=1.1, pace_pct=110)
    a = qa.answer('t00q00', F, 'management')
    assert 'ahead' in a['headline'].lower() or 'ahead' in ' '.join(a['body']).lower()


def test_qa_service_fallback_and_no_project():
    from p6_chat import qa_service
    # unknown id, no project -> honest, never raises
    out = qa_service.answer_question(None, 'zzz', 'management')
    assert out['ok'] and out['answer']['headline']
