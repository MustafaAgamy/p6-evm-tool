"""Owner comment 35 — the Reporting Studio no longer offers the Overview group.

"Remove from the Reporting Studio the Overview / WBS, so the user chooses": the catalog lists
the real analysis features only. The Overview group (Project snapshot, Key indicators,
Progress by category) is gone. A report saved BEFORE the removal may still list those ids:
it opens without them (no error, no raw id on screen), says how many were left out, and is
stored clean the next time it is saved. The Overview SCREEN keeps its own Print.
"""
import db
from p6_special import registry, templates
from p6_special.context import SpecialContext

OLD_IDS = ['overview:snapshot', 'overview:kpis', 'overview:categories']


def _seed(fixture):
    pid = db.upsert_project('NOOV', 'No Overview Fixture')
    sid = db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    db.insert_metrics(sid, {
        'pv': 1e6, 'ev': 6e5, 'ac': 7e5, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 5,
        'overall_planned_pct': 0.61, 'overall_actual_pct': 0.40, 'variance': -0.21,
    })
    db.insert_category_metrics(sid, {
        'Construction': {'weight': 1.0, 'planned_pct': 0.58, 'actual_pct': 0.38,
                         'bac': 1e6, 'ac': 7e5, 'activity_count': 50, 'overridden': False},
    })
    return pid, sid


def test_catalog_has_no_overview_group(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    groups = registry.catalog(SpecialContext(pid, snapshot_id=sid))
    feats = [g['feature'] for g in groups]
    assert 'overview' not in feats
    assert 'evm' in feats and 'audit' in feats            # the analysis features are still offered
    ids = [i['id'] for g in groups for i in g['items']]
    assert not [i for i in ids if i.startswith('overview:')]
    titles = [i['title'] for g in groups for i in g['items']]
    for gone in ('Project snapshot', 'Key indicators', 'Progress by category'):
        assert gone not in titles


def test_no_overview_provider_ships():
    import importlib
    import pytest
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module('p6_special.providers.overview')


def test_split_retired_keeps_order_and_only_drops_the_overview_ids():
    kept, retired = registry.split_retired(['evm:spi', 'overview:kpis', 'audit:health_score', 'overview:snapshot'])
    assert kept == ['evm:spi', 'audit:health_score']
    assert retired == ['overview:kpis', 'overview:snapshot']
    assert registry.split_retired(None) == ([], [])
    assert registry.split_retired(['narrative:overview']) == (['narrative:overview'], [])   # a Narrative section, not the group


def test_a_report_saved_before_the_removal_renders_without_those_results(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    ctx = SpecialContext(pid, snapshot_id=sid)
    rendered = registry.render(ctx, OLD_IDS + ['evm:spi'])
    assert [r['id'] for r in rendered] == ['evm:spi']       # skipped, never an error


def test_saved_reports_open_clean_and_say_what_was_left_out(temp_db):
    pid = db.upsert_project('NOOV2', 'Templates')
    # as stored by an older version: the Overview ids are still in the record
    db.save_project_settings(pid, {templates.KEY: [
        {'id': 'sr1', 'name': 'Monthly', 'item_ids': ['overview:kpis', 'evm:spi', 'overview:categories'],
         'letterhead': {}, 'mode': 'light'},
        {'id': 'sr2', 'name': 'Health', 'item_ids': ['audit:health_score'], 'letterhead': {}, 'mode': 'light'}]})
    lst = {t['id']: t for t in templates.list_templates(pid)}
    assert lst['sr1']['item_ids'] == ['evm:spi'] and lst['sr1']['retired'] == 2
    assert lst['sr2']['item_ids'] == ['audit:health_score'] and 'retired' not in lst['sr2']
    assert templates.get_template(pid, 'sr1')['item_ids'] == ['evm:spi']
    # saving it again stores it clean; the other report is untouched
    templates.save_template(pid, {'id': 'sr1', 'name': 'Monthly', 'item_ids': ['overview:kpis', 'evm:spi']})
    stored = {t['id']: t for t in db.get_project_settings(pid)[templates.KEY]}
    assert stored['sr1']['item_ids'] == ['evm:spi']
    assert stored['sr2']['item_ids'] == ['audit:health_score']
    assert 'retired' not in templates.list_templates(pid)[0]
    # deleting works on the stored list
    assert [t['id'] for t in templates.delete_template(pid, 'sr1')] == ['sr2']


def test_the_screen_tells_the_planner_and_never_shows_a_raw_item_code():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, 'ui', 'modules', 'special.js'), encoding='utf-8').read()
    assert 'S.retired = t.retired || 0' in js
    assert 'no longer part of the Reporting Studio' in js and 'sr-retired' in js
    assert 'alert(' not in js and 'confirm(' not in js          # WebView2: in-page note only
    css = open(os.path.join(root, 'ui', 'style.css'), encoding='utf-8').read()
    assert '.sr-retired {' in css
