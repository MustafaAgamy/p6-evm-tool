"""Tests for db.get_dashboard — the read-model behind the Professional Dashboard.

The dashboard reads entirely from the DB: `portfolio` is one row per project (its
most recent snapshot); `active` is the full snapshot trend for the project owning a
given snapshot. No XML parse, no metric recomputation — the architecture's read path.
"""
import db


def _snap(project_id, data_date, spi, cpi, delay, planned, actual):
    sid = db.insert_snapshot(project_id, data_date, 'p.xml', 'p.xml',
                             f'h{project_id}{data_date}', 7, 1)
    db.insert_metrics(sid, {'pv': 100, 'ev': 90, 'ac': 90, 'spi': spi, 'cpi': cpi,
                            'delay_days': delay, 'overall_planned_pct': planned,
                            'overall_actual_pct': actual, 'variance': 0})
    return sid


def test_portfolio_one_row_per_project_latest_snapshot(temp_db):
    a = db.upsert_project('P-A', 'Harbor')
    b = db.upsert_project('P-B', 'Metro')
    _snap(a, '2026-06-01', 0.50, 1.0, None, 0.20, 0.10)
    late = _snap(a, '2026-08-24', 0.68, 1.0, None, 0.56, 0.38)   # newer Harbor update
    _snap(b, '2026-08-10', 0.74, 1.0, None, 0.52, 0.38)

    port = {r['name']: r for r in db.get_dashboard()['portfolio']}
    assert set(port) == {'Harbor', 'Metro'}
    # Harbor's row is its LATEST snapshot, and it rolls both updates into one card
    assert port['Harbor']['snapshot_id'] == late
    assert port['Harbor']['spi'] == 0.68
    assert port['Harbor']['snapshot_count'] == 2
    assert port['Metro']['snapshot_count'] == 1


def test_active_trend_is_full_series_data_date_ascending(temp_db):
    a = db.upsert_project('P-A', 'Harbor')
    _snap(a, '2026-06-01', 0.50, 1.0, None, 0.20, 0.10)
    _snap(a, '2026-07-27', 0.60, 1.0, None, 0.40, 0.24)
    s3 = _snap(a, '2026-08-24', 0.68, 1.0, None, 0.56, 0.38)

    active = db.get_dashboard(active_snapshot_id=s3)['active']
    assert active is not None and active['name'] == 'Harbor'
    assert [t['data_date'][:10] for t in active['trend']] == \
        ['2026-06-01', '2026-07-27', '2026-08-24']
    assert [round(t['spi'], 2) for t in active['trend']] == [0.50, 0.60, 0.68]


def test_no_active_when_no_snapshot_id(temp_db):
    a = db.upsert_project('P-A', 'Harbor')
    _snap(a, '2026-08-24', 0.68, 1.0, None, 0.56, 0.38)
    dash = db.get_dashboard()
    assert dash['active'] is None
    assert len(dash['portfolio']) == 1


def test_empty_db_yields_empty_portfolio(temp_db):
    dash = db.get_dashboard()
    assert dash['portfolio'] == []
    assert dash['active'] is None
