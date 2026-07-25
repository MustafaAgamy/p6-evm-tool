"""Tests for p6_evm/report.py — pure HTML/logic functions (no Chrome needed)."""
from datetime import datetime

import pytest

from p6_evm.report import find_finish_milestone, render_html


def make_result():
    return {
        'records': [
            {
                'activity': {
                    'id': 'A1', 'name': 'Foundation',
                    'planned_finish': datetime(2024, 6, 30),
                },
                'total_float': 2,
            },
            {
                'activity': {
                    'id': 'A2', 'name': 'Superstructure',
                    'planned_finish': datetime(2024, 12, 31),
                },
                'total_float': -1,
            },
        ],
        'data_date': datetime(2024, 7, 1),
        'categories': {
            'Construction': {
                'weight': 1.0, 'planned_pct': 0.5, 'actual_pct': 0.4,
                'bac': 5000, 'ac': 3000, 'activity_count': 2, 'overridden': False,
            }
        },
        'overall_planned_pct': 0.5,
        'overall_actual_pct': 0.4,
        'pv': 5000.0, 'ev': 4000.0, 'ac': 3000.0,
        'spi': 0.8, 'cpi': 1.33,
        'variance': -1000.0,
        'delay_days': 3,
    }


# ── find_finish_milestone ──────────────────────────────────────────────────

def test_milestone_returns_latest_planned_finish():
    result = make_result()
    m = find_finish_milestone(result)
    assert m['activity']['id'] == 'A2'   # Dec 31 > Jun 30

def test_milestone_empty_records_returns_none():
    result = make_result()
    result['records'] = []
    assert find_finish_milestone(result) is None

def test_milestone_all_no_planned_finish_returns_none():
    result = make_result()
    for r in result['records']:
        r['activity']['planned_finish'] = None
    assert find_finish_milestone(result) is None

def test_milestone_partial_none_ignored():
    result = make_result()
    result['records'][0]['activity']['planned_finish'] = None  # A1 has no finish
    m = find_finish_milestone(result)
    assert m['activity']['id'] == 'A2'   # only A2 is eligible


# ── render_html ────────────────────────────────────────────────────────────

def make_meta():
    return {'project_name': 'Test Project', 'project_id': 'PRJ001', 'source_file': 'test.xml'}


def test_render_html_returns_string():
    out = render_html(make_result(), make_meta())
    assert isinstance(out, str)
    assert len(out) > 100

def test_render_html_contains_project_name():
    out = render_html(make_result(), make_meta())
    assert 'Test Project' in out

def test_render_html_contains_data_date():
    out = render_html(make_result(), make_meta())
    assert '01-Jul-2024' in out

def test_render_html_contains_spi():
    out = render_html(make_result(), make_meta())
    assert '0.8000' in out   # formatted as .4f

def test_render_html_escapes_category_name():
    result = make_result()
    result['categories'] = {
        '<script>alert(1)</script>': {
            'weight': 1.0, 'planned_pct': 0.5, 'actual_pct': 0.4,
            'bac': 5000, 'ac': 3000, 'activity_count': 1, 'overridden': False,
        }
    }
    out = render_html(result, make_meta())
    assert '<script>' not in out
    assert '&lt;script&gt;' in out

def test_render_html_escapes_project_name():
    meta = {'project_name': '<b>Injected</b>', 'project_id': 'PRJ001', 'source_file': 'test.xml'}
    out = render_html(make_result(), meta)
    assert '<b>Injected</b>' not in out
    assert '&lt;b&gt;Injected&lt;/b&gt;' in out
