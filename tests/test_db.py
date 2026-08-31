"""Tests for db.py — all CRUD, file helpers, cascade delete, migration."""
import json
import os
import sqlite3

import pytest

import db


# ── Schema ─────────────────────────────────────────────────────────────────

def test_init_db_creates_tables(temp_db):
    conn = sqlite3.connect(temp_db / 'controlyx.db')
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert {'projects', 'snapshots', 'metrics', 'category_metrics'}.issubset(tables)

def test_init_db_idempotent(temp_db):
    # Calling init_db again on an existing DB must not raise
    db.init_db()


# ── upsert_project ─────────────────────────────────────────────────────────

def test_upsert_project_creates_new(temp_db):
    pid = db.upsert_project('P001', 'Test Project')
    assert isinstance(pid, int)

def test_upsert_project_by_p6_id_returns_existing(temp_db):
    pid1 = db.upsert_project('P001', 'Test Project')
    pid2 = db.upsert_project('P001', 'Different Name')  # same p6_id
    assert pid1 == pid2

def test_upsert_project_empty_p6_id_matches_by_name(temp_db):
    pid1 = db.upsert_project('', 'Test Project')
    pid2 = db.upsert_project('', 'Test Project')
    assert pid1 == pid2

def test_upsert_project_different_names_create_separate_rows(temp_db):
    pid1 = db.upsert_project('', 'Project A')
    pid2 = db.upsert_project('', 'Project B')
    assert pid1 != pid2


# ── insert_snapshot ────────────────────────────────────────────────────────

def test_insert_snapshot_returns_int(temp_db):
    pid = db.upsert_project('P001', 'Test')
    sid = db.insert_snapshot(pid, '2024-07-01', '/path.xml', '/cache.xml', 'abc123', 10, 2)
    assert isinstance(sid, int)

def test_insert_snapshot_data_persisted(temp_db):
    pid = db.upsert_project('P001', 'Test')
    sid = db.insert_snapshot(pid, '2024-07-01', '/path.xml', '/cache.xml', 'hash1', 5, 1)
    snaps = db.get_project_snapshots(pid)
    assert len(snaps) == 1
    assert snaps[0]['data_date'] == '2024-07-01'


# ── insert_metrics ─────────────────────────────────────────────────────────

def test_insert_metrics_partial_keys_ok(temp_db):
    pid = db.upsert_project('P001', 'Test')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h', 5, 1)
    # Partial dict — missing keys become NULL, must not raise
    db.insert_metrics(sid, {'spi': 0.5, 'delay_days': 3})
    rows = db.get_recent_projects()
    assert rows[0]['spi'] == pytest.approx(0.5)
    assert rows[0]['delay'] == 3

def test_insert_metrics_full_dict(temp_db):
    pid = db.upsert_project('P001', 'Test')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h2', 5, 1)
    metrics = {
        'pv': 1000, 'ev': 500, 'ac': 800,
        'spi': 0.5, 'cpi': 0.625,
        'delay_days': 4,
        'overall_planned_pct': 0.33, 'overall_actual_pct': 0.17,
        'variance': -500,
    }
    db.insert_metrics(sid, metrics)
    rows = db.get_recent_projects()
    assert rows[0]['spi'] == pytest.approx(0.5)


# ── insert_category_metrics ────────────────────────────────────────────────

def test_insert_category_metrics(temp_db):
    pid = db.upsert_project('P001', 'Test')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h3', 5, 1)
    db.insert_category_metrics(sid, {
        'Construction': {
            'weight': 0.95, 'planned_pct': 0.5, 'actual_pct': 0.4,
            'bac': 1000, 'ac': 800, 'activity_count': 2, 'overridden': False,
        }
    })
    conn = sqlite3.connect(temp_db / 'controlyx.db')
    count = conn.execute('SELECT COUNT(*) FROM category_metrics').fetchone()[0]
    conn.close()
    assert count == 1

def test_insert_category_metrics_empty_categories(temp_db):
    pid = db.upsert_project('P001', 'Test')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h4', 5, 1)
    db.insert_category_metrics(sid, {})   # must not raise
    db.insert_category_metrics(sid, None)  # also must not raise


# ── get_recent_projects ────────────────────────────────────────────────────

def test_get_recent_projects_empty_db(temp_db):
    assert db.get_recent_projects() == []

def test_get_recent_projects_one_row_per_project(temp_db):
    pid = db.upsert_project('P001', 'Test')
    sid1 = db.insert_snapshot(pid, '2024-06-01', '/a.xml', '/ca.xml', 'h1', 5, 1)
    db.insert_metrics(sid1, {'spi': 0.8})
    sid2 = db.insert_snapshot(pid, '2024-07-01', '/b.xml', '/cb.xml', 'h2', 5, 1)
    db.insert_metrics(sid2, {'spi': 0.6})
    rows = db.get_recent_projects()
    assert len(rows) == 1
    assert rows[0]['spi'] == pytest.approx(0.6)   # most recent snapshot

def test_get_recent_projects_construction_pct(temp_db):
    pid = db.upsert_project('P001', 'Test')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h', 5, 1)
    db.insert_metrics(sid, {'spi': 0.9})
    db.insert_category_metrics(sid, {
        'Construction': {
            'weight': 1.0, 'planned_pct': 0.5, 'actual_pct': 0.4,
            'bac': 3000, 'ac': 800, 'activity_count': 2, 'overridden': False,
        }
    })
    rows = db.get_recent_projects()
    assert rows[0]['construction_pct'] == pytest.approx(0.4)


# ── get_project_snapshots ──────────────────────────────────────────────────

def test_get_project_snapshots_ordered_by_date(temp_db):
    pid = db.upsert_project('P001', 'Test')
    for d in ('2024-06-01', '2024-07-01', '2024-05-01'):
        db.insert_snapshot(pid, d, f'/x.xml', f'/c.xml', d, 5, 1)
    snaps = db.get_project_snapshots(pid)
    dates = [s['data_date'] for s in snaps]
    assert dates == sorted(dates)


# ── delete_project ─────────────────────────────────────────────────────────

def test_delete_project_removes_project_row(temp_db):
    pid = db.upsert_project('P001', 'Test')
    db.delete_project(pid)
    assert db.get_recent_projects() == []

def test_delete_project_cascades_to_all_child_tables(temp_db):
    pid = db.upsert_project('P001', 'Test')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h', 5, 1)
    db.insert_metrics(sid, {'spi': 0.5, 'delay_days': 3})
    db.insert_category_metrics(sid, {
        'Construction': {'weight': 0.95, 'planned_pct': 0.5, 'actual_pct': 0.4,
                         'bac': 1000, 'ac': 800, 'activity_count': 2, 'overridden': False}
    })
    db.delete_project(pid)
    conn = sqlite3.connect(temp_db / 'controlyx.db')
    assert conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM metrics').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM category_metrics').fetchone()[0] == 0
    conn.close()

def test_delete_project_only_affects_target(temp_db):
    pid1 = db.upsert_project('P001', 'Project 1')
    pid2 = db.upsert_project('P002', 'Project 2')
    sid1 = db.insert_snapshot(pid1, '2024-07-01', '/a.xml', '/ca.xml', 'h1', 5, 1)
    db.insert_metrics(sid1, {'spi': 0.5})
    sid2 = db.insert_snapshot(pid2, '2024-07-01', '/b.xml', '/cb.xml', 'h2', 5, 1)
    db.insert_metrics(sid2, {'spi': 0.8})
    db.delete_project(pid1)
    rows = db.get_recent_projects()
    assert len(rows) == 1
    assert rows[0]['spi'] == pytest.approx(0.8)


# ── hash_file ──────────────────────────────────────────────────────────────

def test_hash_file_consistent(tmp_path):
    f = tmp_path / 'test.xml'
    f.write_bytes(b'<project/>')
    h1 = db.hash_file(str(f))
    h2 = db.hash_file(str(f))
    assert h1 == h2

def test_hash_file_is_sha256_length(tmp_path):
    f = tmp_path / 'test.xml'
    f.write_bytes(b'<project/>')
    assert len(db.hash_file(str(f))) == 64

def test_hash_file_differs_for_different_content(tmp_path):
    f1 = tmp_path / 'a.xml'
    f2 = tmp_path / 'b.xml'
    f1.write_bytes(b'<a/>')
    f2.write_bytes(b'<b/>')
    assert db.hash_file(str(f1)) != db.hash_file(str(f2))


# ── resolve_xml_path ───────────────────────────────────────────────────────

def test_resolve_prefers_original(tmp_path):
    orig   = tmp_path / 'orig.xml'
    cached = tmp_path / 'cached.xml'
    orig.write_bytes(b'<x/>')
    cached.write_bytes(b'<x/>')
    assert db.resolve_xml_path(str(orig), str(cached)) == str(orig)

def test_resolve_falls_back_to_cached(tmp_path):
    cached = tmp_path / 'cached.xml'
    cached.write_bytes(b'<x/>')
    result = db.resolve_xml_path('/nonexistent/path.xml', str(cached))
    assert result == str(cached)

def test_resolve_returns_none_when_both_missing():
    assert db.resolve_xml_path('/missing.xml', '/also_missing.xml') is None

def test_resolve_handles_none_cached(tmp_path):
    orig = tmp_path / 'orig.xml'
    orig.write_bytes(b'<x/>')
    assert db.resolve_xml_path(str(orig), None) == str(orig)


# ── cache_xml ──────────────────────────────────────────────────────────────

def test_cache_xml_copies_file(temp_db, tmp_path):
    xml = tmp_path / 'test.xml'
    xml.write_bytes(b'<project/>')
    file_hash = db.hash_file(str(xml))
    cached = db.cache_xml(str(xml), file_hash)
    assert os.path.exists(cached)
    assert open(cached, 'rb').read() == b'<project/>'

def test_xml_eviction_removes_oldest(temp_db):
    """Beyond 20 cached XMLs, _cleanup_old_xml_files drops the oldest by mtime."""
    sdir = temp_db / 'schedules'
    # Create 21 files with distinct, ordered mtimes (i seconds from epoch)
    for i in range(21):
        f = sdir / f'file_{i:02d}.xml'
        f.write_bytes(b'<project/>')
        os.utime(f, (i, i))

    db._cleanup_old_xml_files()

    remaining = list(sdir.glob('*.xml'))
    assert len(remaining) == 20
    assert not (sdir / 'file_00.xml').exists()  # oldest evicted
    assert (sdir / 'file_20.xml').exists()       # newest kept


def test_cache_xml_dedup_same_hash(temp_db, tmp_path):
    xml = tmp_path / 'test.xml'
    xml.write_bytes(b'<project/>')
    file_hash = db.hash_file(str(xml))
    # Cache once: file is copied
    cached1 = db.cache_xml(str(xml), file_hash)
    # The snapshot row with cached_path must exist for dedup to fire
    pid = db.upsert_project('', 'Test')
    db.insert_snapshot(pid, '2024-07-01', str(xml), cached1, file_hash, 1, 1)
    # Cache again: same hash → reuse existing path
    cached2 = db.cache_xml(str(xml), file_hash)
    assert cached1 == cached2


# ── migrate_history_json ───────────────────────────────────────────────────

def test_migrate_history_json(temp_db, tmp_path):
    history = [
        {
            'filename': 'project.xml',
            'path': '/path/to/project.xml',
            'data_date': '2024-06-01',
            'spi': 0.9,
            'delay': -2,
            'construction_pct': 0.7,
        }
    ]
    hist_file = tmp_path / 'history.json'
    hist_file.write_text(json.dumps(history), encoding='utf-8')
    db.migrate_history_json(str(hist_file))
    rows = db.get_recent_projects()
    assert len(rows) == 1
    # File renamed to .migrated
    assert (tmp_path / 'history.json.migrated').exists()
    assert not hist_file.exists()

def test_migrate_history_json_missing_file(temp_db, tmp_path):
    # Should not raise even if file doesn't exist
    db.migrate_history_json(str(tmp_path / 'nonexistent.json'))

def test_migrate_history_json_bad_json(temp_db, tmp_path):
    bad = tmp_path / 'history.json'
    bad.write_text('NOT JSON', encoding='utf-8')
    db.migrate_history_json(str(bad))   # must not raise


# ── audit persistence ──────────────────────────────────────────────────────

def _audit_result():
    return {
        'findings': [
            {'finding_id': 'aaa', 'check_id': 'LOGIC-003', 'check_name': 'Circular Logic',
             'category': 'Construction', 'severity': 'Critical', 'activity_id': 'A1',
             'activity_name': 'Loop', 'wbs_path': 'T > S', 'related_activity_id': None,
             'related_activity_name': None, 'summary': 'loop', 'basis': 'cycle: A1 -> A1',
             'recommendation': 'break it', 'confidence': None},
            {'finding_id': 'bbb', 'check_id': 'LOGIC-001', 'check_name': 'Open Ends',
             'category': None, 'severity': 'High', 'activity_id': 'A2', 'activity_name': 'End',
             'wbs_path': 'T', 'related_activity_id': None, 'related_activity_name': None,
             'summary': 'no succ', 'basis': 'successor_count = 0', 'recommendation': 'link it',
             'confidence': None},
        ],
        'scores': {
            'categories': {'Schedule Logic': {'score': 40, 'finding_count': 2, 'weight': 0.5},
                           'Float Analysis': {'score': 100, 'finding_count': 0, 'weight': 0.5}},
            'overall': {'score': 70, 'categories_evaluated': 2, 'categories_total': 2, 'grade': 'Good'},
        },
        'counts': {'total': 2, 'by_severity': {'Critical': 1, 'High': 1}},
    }


def test_insert_and_get_audit_roundtrip(temp_db):
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h', 5, 1)
    db.insert_audit(sid, _audit_result(), total_review_areas=5)
    got = db.get_audit_for_snapshot(sid)
    assert got is not None
    assert got['total_review_areas'] == 5
    assert got['scores']['overall']['grade'] == 'Good'
    assert got['scores']['categories']['Schedule Logic']['score'] == 40
    assert got['counts']['total'] == 2
    assert got['counts']['by_severity']['Critical'] == 1
    # order preserved: Critical finding first
    assert got['findings'][0]['finding_id'] == 'aaa'
    assert got['findings'][0]['wbs_path'] == 'T > S'


def test_get_audit_none_when_absent(temp_db):
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h', 5, 1)
    assert db.get_audit_for_snapshot(sid) is None


def test_delete_project_clears_audit_tables(temp_db):
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h', 5, 1)
    db.insert_audit(sid, _audit_result(), total_review_areas=5)
    db.delete_project(pid)
    conn = sqlite3.connect(temp_db / 'controlyx.db')
    assert conn.execute('SELECT COUNT(*) FROM audit_findings').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM audit_scores').fetchone()[0] == 0
    conn.close()


def test_get_latest_snapshot_id(temp_db):
    pid = db.upsert_project('P1', 'Proj')
    s1 = db.insert_snapshot(pid, '2024-06-01', '/a.xml', '/c.xml', 'h1', 5, 1)
    s2 = db.insert_snapshot(pid, '2024-07-01', '/b.xml', '/c.xml', 'h2', 5, 1)
    assert db.get_latest_snapshot_id(pid) == s2


def test_get_project_result_includes_snapshot_id(temp_db):
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h', 5, 1)
    db.insert_metrics(sid, {'spi': 0.9})
    res = db.get_project_result(pid)
    assert res['_snapshot_id'] == sid


# ── V2 isolated module persistence ──────────────────────────────────────────

def _modules_result():
    return {
        'module_order': ['dangling', 'float'],
        'modules': {
            'dangling': {
                'module': 'dangling', 'name': 'Dangling Activities',
                'score': 94, 'grade': 'Excellent', 'pct': 1.2,
                'kpis': {'total_activities': 1466, 'total_dangling': 18},
                'wbs_summary': [],
                'findings': [{'finding_id': 'd1', 'activity_id': 'A1',
                              'logic_issue': 'Dangling Start + Finish', 'severity': 'High'}],
            },
            'float': {
                'module': 'float', 'name': 'Float Analysis',
                'score': 0, 'grade': 'Critical', 'pct': 40.3,
                'kpis': {'total_activities': 1466, 'above_threshold': 591},
                'wbs_summary': [{'wbs': 'Civil', 'high': 6, 'activities': 7, 'pct': 85.7}],
                'findings': [{'finding_id': 'f1', 'activity_id': 'A2', 'impact': 5.6,
                              'severity': 'High', 'status': 'Excessive Float'}],
            },
        },
    }


def test_insert_and_get_audit_modules_roundtrip(temp_db):
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h', 5, 1)
    db.insert_audit_modules(sid, _modules_result())
    got = db.get_audit_modules_for_snapshot(sid)
    assert got is not None
    assert got['module_order'] == ['dangling', 'float']
    fm = got['modules']['float']
    assert fm['score'] == 0 and fm['grade'] == 'Critical' and fm['pct'] == 40.3
    assert fm['kpis']['above_threshold'] == 591
    assert fm['wbs_summary'][0]['wbs'] == 'Civil'
    assert fm['findings'][0]['impact'] == 5.6
    assert got['modules']['dangling']['findings'][0]['logic_issue'] == 'Dangling Start + Finish'


def test_get_audit_modules_none_when_absent(temp_db):
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h', 5, 1)
    assert db.get_audit_modules_for_snapshot(sid) is None


def test_delete_project_clears_audit_modules(temp_db):
    import sqlite3
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, '2024-07-01', '/p.xml', '/c.xml', 'h', 5, 1)
    db.insert_audit_modules(sid, _modules_result())
    db.delete_project(pid)
    conn = sqlite3.connect(temp_db / 'controlyx.db')
    assert conn.execute('SELECT COUNT(*) FROM audit_modules').fetchone()[0] == 0
    conn.close()
