"""Tests for the Special Report registry (auto-discovery + catalog + render)."""
import db
from p6_special import registry
from p6_special.registry import Item
from p6_special.context import SpecialContext


def _seed(fixture):
    pid = db.upsert_project('P1', 'Grain')
    sid = db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    db.insert_metrics(sid, {
        'pv': 1e6, 'ev': 6e5, 'ac': 7e5, 'spi': 0.6, 'cpi': 0.857, 'delay_days': 5,
        'overall_planned_pct': 0.614, 'overall_actual_pct': 0.404, 'variance': -0.21,
    })
    db.insert_category_metrics(sid, {
        'Construction': {'weight': 0.855, 'planned_pct': 0.58, 'actual_pct': 0.38,
                         'bac': 1e6, 'ac': 7e5, 'activity_count': 50, 'overridden': False},
    })
    return pid


def test_catalog_groups_by_feature(temp_db, xml_path):
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))
    groups = registry.catalog(ctx)
    evm = next(g for g in groups if g['feature'] == 'evm')
    assert evm['feature_title'] == 'EVM Report'
    ids = [i['id'] for i in evm['items']]
    assert 'evm:planned_pct' in ids
    assert 'evm:category_table' in ids
    assert all('availability' in i for i in evm['items'])


def test_render_selected_in_order(temp_db, xml_path):
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))
    out = registry.render(ctx, ['evm:actual_pct', 'evm:planned_pct'])
    assert [o['id'] for o in out] == ['evm:actual_pct', 'evm:planned_pct']
    assert out[0]['payload']['kind'] == 'kpi_group'
    assert out[0]['feature_title'] == 'EVM Report'


def test_unknown_id_skipped(temp_db, xml_path):
    registry.clear_providers()
    ctx = SpecialContext(_seed(xml_path))
    out = registry.render(ctx, ['evm:planned_pct', 'nope:xxx'])
    assert len(out) == 1


def test_producer_error_becomes_no_data(temp_db, xml_path):
    registry.clear_providers()

    def boom(ctx):
        return [Item('x:boom', 'x', 'X', 'Boom', 'text',
                     lambda c: (_ for _ in ()).throw(ValueError('nope')))]
    registry.register_provider(boom)
    ctx = SpecialContext(_seed(xml_path))
    out = registry.render(ctx, ['x:boom'])
    assert out[0]['payload']['kind'] == 'no_data'


def test_custom_provider_auto_appears(temp_db, xml_path):
    registry.clear_providers()

    def prov(ctx):
        return [Item('x:one', 'x', 'X Feature', 'One', 'text',
                     lambda c: {'kind': 'text', 'paragraphs': ['hi']})]
    registry.register_provider(prov)
    ctx = SpecialContext(_seed(xml_path))
    groups = registry.catalog(ctx)
    assert any(g['feature'] == 'x' for g in groups)
