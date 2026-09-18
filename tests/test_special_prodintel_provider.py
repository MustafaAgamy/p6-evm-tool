"""Tests for the Productivity & Resource Intelligence Special Report provider.

prodintel is a project-independent knowledge feature, so its results are 'ready'
whenever the bundled KB loads — even with no imported project. Each item's
produce(ctx) must return a real payload dict (never a silent-empty 'ready').
"""
import db
from p6_special.providers import prodintel
from p6_special.context import SpecialContext


def _seed(fixture):
    """A minimal project snapshot, matching the EVM provider test's seed — prodintel
    does not use it, but it proves the KB items are project-independent."""
    pid = db.upsert_project('P1', 'Grain')
    db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    return pid


def _items(ctx):
    return {i.id: i for i in prodintel.provide(ctx)}


def test_all_items_available_ready(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    for it in prodintel.provide(ctx):
        assert it.availability(ctx) == 'ready', it.id


def test_ready_without_a_project(temp_db):
    # KB is bundled and project-independent: ready even with no imported file.
    ctx = SpecialContext(9999)
    for it in prodintel.provide(ctx):
        assert it.availability(ctx) == 'ready', it.id


def test_every_item_produces_a_payload_without_raising(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    for it in prodintel.provide(ctx):
        pl = it.produce(ctx)
        assert isinstance(pl, dict) and pl.get('kind') and pl['kind'] != 'no_data', it.id


def test_coverage_kpis(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    pl = _items(ctx)['prodintel:coverage'].produce(ctx)
    assert pl['kind'] == 'kpi_group'
    labels = {k['label'] for k in pl['items']}
    assert {'Disciplines', 'Systems', 'Work items', 'Component norms'} <= labels
    # Counts tie out to the KB loaded through the feature's own functions.
    from p6_prodintel import load_items, build_tree, item_result
    items = load_items()
    tree = build_tree(items)
    by = {k['label']: k['value'] for k in pl['items']}
    assert by['Work items'] == f'{len(items):,}'
    assert by['Disciplines'] == f'{len(tree):,}'
    n_comps = sum(len(item_result(it).get('components', [])) for it in items)
    assert by['Component norms'] == f'{n_comps:,}'


def test_norm_library_is_a_table_one_row_per_item(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    t = _items(ctx)['prodintel:norm_library'].produce(ctx)
    assert t['kind'] == 'table' and t['columns'][0] == 'Discipline'
    from p6_prodintel import load_items
    assert len(t['rows']) == len(load_items())


def test_component_norms_table_rows_and_rate_format(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    t = _items(ctx)['prodintel:component_norms'].produce(ctx)
    assert t['kind'] == 'table'
    from p6_prodintel import load_items, item_result
    n_comps = sum(len(item_result(it).get('components', [])) for it in load_items())
    assert len(t['rows']) == n_comps
    # Rate cells are screen-faithful strings (MH/unit or output/day), never blank.
    for row in t['rows']:
        rate_cell = row[3]
        assert isinstance(rate_cell, str) and rate_cell


def test_evidence_mix_is_a_segbar_with_real_counts(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    pl = _items(ctx)['prodintel:evidence_mix'].produce(ctx)
    assert pl['kind'] == 'segbar'
    labels = {s['label'] for s in pl['segments']}
    # Bucketed by the SAME evidence word the component table + screen chips use, so the
    # chart and the table never disagree (was the raw state — Validated/Draft/No reference).
    assert labels and labels <= {'Validated', 'High', 'Moderate', 'Draft',
                                 'Insufficient', 'No reference'}
    from p6_prodintel import load_items, item_result
    n_comps = sum(len(item_result(it).get('components', [])) for it in load_items())
    assert sum(s['value'] for s in pl['segments']) == n_comps


def test_discipline_table_has_total_row(temp_db, xml_path):
    ctx = SpecialContext(_seed(xml_path))
    t = _items(ctx)['prodintel:discipline_table'].produce(ctx)
    assert t['kind'] == 'table'
    assert t['rows'][-1][0] == 'All disciplines'
