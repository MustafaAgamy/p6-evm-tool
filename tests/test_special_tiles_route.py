"""Integration test for p6_special.assemble.tiles() — the /api/special/tiles
route's underlying orchestration. Seeds a project via a real EVM snapshot
(same pattern as test_special_evm_provider.py) and checks the returned tiles
+ meta shape."""
import db
from p6_special import assemble

_ALLOWED_KINDS = ('kpis', 'table', 'bars', 'segbar', 'findings', 'keyvals',
                  'text', 'note', 'group', 'no_data')


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
    return pid, sid


def _first_ready_item_id(pid, sid):
    groups = assemble.catalog(pid, snapshot_id=sid)
    for g in groups:
        for it in g['items']:
            if it['availability'] == 'ready':
                return it['id']
    return None


def test_tiles_returns_mapped_tiles_and_meta(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    item_id = _first_ready_item_id(pid, sid)
    assert item_id, 'expected at least one ready catalog item to test tiles() against'

    res = assemble.tiles(project_id=pid, item_ids=[item_id], snapshot_id=sid)

    assert isinstance(res, dict)
    assert 'tiles' in res and 'meta' in res
    tiles = res['tiles']
    assert isinstance(tiles, list)
    assert len(tiles) == 1

    tile = tiles[0]
    assert tile['id'] == item_id
    assert tile['kind'] in _ALLOWED_KINDS
    assert 'shape' in tile and set(tile['shape'].keys()) == {'w', 'h'}
    assert 'data' in tile

    meta = res['meta']
    assert meta['project_name'] == 'Grain'


def test_tiles_with_no_item_ids_returns_empty_list(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    res = assemble.tiles(project_id=pid, item_ids=[], snapshot_id=sid)
    assert res['tiles'] == []
    assert res['meta']['project_name'] == 'Grain'


def test_tiles_unknown_item_id_skipped(temp_db, xml_path):
    pid, sid = _seed(xml_path)
    res = assemble.tiles(project_id=pid, item_ids=['nonexistent:item'], snapshot_id=sid)
    assert res['tiles'] == []
