"""EVM results in the Studio ship their DATA as payloads (table / bars / kpi), so
ONE selection feeds both views: the narrative Document renders the data in its
house style, and the Dashboard turns the same data into a chart. The whole EVM
report stays available as a detailed reused section (``evm:full_report``)."""
import db
from p6_special import registry
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
    return pid, sid


def _render_one(pid, sid, item_id):
    ctx = SpecialContext(pid, snapshot_id=sid)
    out = registry.render(ctx, [item_id])
    assert out, f'{item_id} produced nothing'
    return out[0], ctx


def test_composites_are_chartable_data_payloads(temp_db, xml_path):
    """category -> table, planned-vs-actual + PV/EV/AC -> bars. Structured data (not
    opaque html), so the Dashboard can turn each into a chart and the Document can
    render it in the narrative house style."""
    pid, sid = _seed(xml_path)
    expected = {'evm:category_table': 'table',
                'evm:planned_vs_actual': 'bars',
                'evm:pv_ev_ac': 'bars'}
    for item_id, kind in expected.items():
        item, _ = _render_one(pid, sid, item_id)
        pl = item['payload']
        assert pl.get('kind') == kind, f'{item_id}: expected {kind}, got {pl.get("kind")}'
        assert pl.get('rows'), f'{item_id} has no rows'   # real, non-empty structured data


def test_full_report_stays_a_reused_section(temp_db, xml_path):
    """The whole EVM report remains available verbatim as a detailed section."""
    pid, sid = _seed(xml_path)
    item, ctx = _render_one(pid, sid, 'evm:full_report')
    assert item['ctype'] == 'section'
    pl = item['payload']
    assert pl.get('kind') == 'html'
    assert 'Category Weights' in pl.get('html', '')   # the report's own section content
