"""Tests for p6_evm/report.py — pure HTML/logic functions (no Chrome needed)."""
from datetime import datetime

import pytest

import report_theme
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


# ── Audit section (Plan 2) ──────────────────────────────────────────────────

def _audit():
    return {
        'findings': [{
            'finding_id': 'abc123', 'check_name': 'Open Ends', 'severity': 'High',
            'activity_id': 'A2', 'activity_name': 'Roof', 'wbs_path': 'T > Struct',
            'summary': 'Missing successor', 'recommendation': 'Link it', 'basis': 'succ=0',
        }],
        'scores': {'overall': {'score': 57, 'grade': 'Fair',
                               'categories_evaluated': 2, 'categories_total': 2}},
        'counts': {'total': 1, 'by_severity': {'High': 1}},
        'total_review_areas': 5,
    }


def test_render_html_without_audit_has_no_health_section():
    html = render_html(make_result(), make_meta())
    assert 'Schedule Health' not in html


def test_render_html_with_audit_includes_section_and_finding():
    html = render_html(make_result(), make_meta(), audit=_audit())
    assert 'Schedule Health' in html
    assert '57' in html
    assert 'Fair' in html
    assert '2 of 5' in html
    assert 'A2' in html            # activity id shown
    assert 'Missing successor' in html


def test_render_html_with_audit_escapes_findings():
    a = _audit()
    a['findings'][0]['activity_name'] = '<script>x</script>'
    html = render_html(make_result(), make_meta(), audit=a)
    assert '<script>x</script>' not in html
    assert '&lt;script&gt;' in html


# ── Theme support ────────────────────────────────────────────────────────────

def test_render_html_default_theme_is_light():
    out = render_html(make_result(), make_meta())
    assert out.strip().startswith('<html>')
    assert out.strip().endswith('</html>')
    assert 'data-rpt-theme="light"' in out

def test_render_html_dark_theme():
    out = render_html(make_result(), make_meta(), theme='dark')
    assert 'data-rpt-theme="dark"' in out
    assert report_theme.THEMES['dark']['rpt-accent'] in out  # '#5b9bff'
