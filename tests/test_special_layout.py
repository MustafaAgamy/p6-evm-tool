"""The Studio dashboard layout (order/sizes/titles/letterhead) persists per
project — the storage behind /api/special/layout/save + /load. It lives in
project_settings['studio_layout'] (no schema change) and round-trips intact."""
import db


def _seed(fixture):
    pid = db.upsert_project('P1', 'Grain')
    db.insert_snapshot(pid, '2026-01-01', str(fixture), str(fixture), 'h', 10, 2)
    return pid


LAYOUT = {
    'order': ['evm:kpis', 'audit:find', 'evm:cat'],
    'sizes': {'evm:cat': {'w': 2, 'h': 1}},
    'titles': {'audit:find': 'This week’s risks'},
    'header': {
        'title': 'ACME — Grain Terminal', 'subtitle': 'Weekly pack',
        'title_size': 'l', 'sub_size': 'm', 'title_bold': True, 'sub_bold': False,
        'logos_left': [{'src': 'data:image/png;base64,AAAA', 'size': 'm'}],
        'logos_right': [],
    },
}


def test_layout_round_trips_per_project(temp_db, xml_path):
    pid = _seed(xml_path)
    # nothing saved yet
    assert db.get_project_settings(pid).get('studio_layout') is None

    db.save_project_settings(pid, {'studio_layout': LAYOUT})
    got = db.get_project_settings(pid).get('studio_layout')
    assert got == LAYOUT
    assert got['sizes']['evm:cat'] == {'w': 2, 'h': 1}
    assert got['header']['logos_left'][0]['src'].startswith('data:image')


def test_layout_is_isolated_per_project(temp_db, xml_path):
    pid_a = _seed(xml_path)
    pid_b = db.upsert_project('P2', 'Other')
    db.save_project_settings(pid_a, {'studio_layout': LAYOUT})
    assert db.get_project_settings(pid_b).get('studio_layout') is None
    assert db.get_project_settings(pid_a).get('studio_layout') == LAYOUT


def test_layout_save_preserves_other_settings(temp_db, xml_path):
    pid = _seed(xml_path)
    db.save_project_settings(pid, {'location': {'lat': 31.2, 'lon': 32.3}})
    db.save_project_settings(pid, {'studio_layout': LAYOUT})   # shallow-merge, must not clobber
    s = db.get_project_settings(pid)
    assert s.get('location') == {'lat': 31.2, 'lon': 32.3}
    assert s.get('studio_layout') == LAYOUT
