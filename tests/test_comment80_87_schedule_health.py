"""Comments 80–87 — Schedule Health figures as P6 holds them, and a new import that starts clean."""
import os

import pytest

from p6_audit.presentation import float_days_text, TASKS_CHECKED_LABEL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


@pytest.mark.parametrize('value, text', [
    (-0.05, '-0.05 d'), (-0.4545, '-0.45 d'), (-3.0, '-3 d'), (0, '0 d'),
    (-0.0045, '-0.0045 d'),          # too small for two decimals: never shown as 0
    (None, '—'), (12.5, '12.5 d'),
])
def test_total_float_keeps_its_decimals(value, text):
    assert float_days_text(value) == text


def test_tasks_checked_tile_is_named_and_explained():
    from p6_audit.presentation import TASKS_CHECKED_NOTE
    assert TASKS_CHECKED_LABEL == 'Task Activities Checked'
    assert 'Milestones' in TASKS_CHECKED_NOTE and 'Task Dependent' in TASKS_CHECKED_NOTE
    assert 'tiles_note' in _read('ui/modules/audit.js')
    assert 'tiles_note' in _read('p6_audit/report.py')


def test_relationship_types_workbook_drops_non_fs_and_remaining():
    from p6_audit.excel_sheets import _SKIP_FOR
    assert {'non_fs', 'remaining_activities'} <= _SKIP_FOR['relationship_types']


def test_fresh_import_resets_what_was_typed_but_keeps_report_templates(temp_db):
    import db
    pid = db.upsert_project('P-86', 'Project 86')
    db.save_project_settings(pid, {
        'contract_milestones': [{'name': 'Completion', 'date': '2026-01-01'}],
        'lag_justifications': {'A|B': 'curing'}, 'location': {'lat': 30, 'lon': 31},
        'last_weather': {'x': 1}, 'evm_setup': {'w': 1}, 'special_reports': [{'name': 'Monthly'}]})
    removed = db.reset_project_inputs(pid)
    assert 'contract_milestones' in removed and 'special_reports' not in removed
    assert db.get_project_settings(pid) == {'special_reports': [{'name': 'Monthly'}]}
    assert db.get_contract_milestones(pid) == []
    assert db.reset_project_inputs(pid) == []          # nothing left to drop


def test_browse_import_asks_for_a_fresh_start_and_clears_session_work():
    api = _read('ui/modules/api.js')
    assert 'fresh_start: true' in api and 'controlyx:new-schedule' in api
    for mod in ('period', 'critpath', 'update', 'compare'):
        assert 'controlyx:new-schedule' in _read(f'ui/modules/{mod}.js'), mod
    server = _read('server.py')
    assert "body.get('fresh_start')" in server and 'reset_project_inputs' in server


def test_schedule_health_narrative_and_lag_are_xer_only():
    app = _read('ui/app.js')
    assert "XER_ONLY = new Set(['audit', 'narrative', 'lag'])" in app
    assert 'accepts XER files only' in app
