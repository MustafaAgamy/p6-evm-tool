"""DB helpers backing Update vs Update: previous-snapshot lookup, per-project snapshot
files, and the milestone-finish cache (with the scanned sentinel)."""
from datetime import datetime
import db


def _snap(pid, dd, tag):
    return db.insert_snapshot(project_id=pid, data_date=dd, original_path=f'{tag}.xml',
                              cached_path=f'cache/{tag}.xml', file_hash=tag,
                              activity_count=1, calendar_count=1)


def test_prev_snapshot_and_project_files(temp_db):
    pid = db.upsert_project('P1', 'Grain Terminal')
    s1 = _snap(pid, datetime(2026, 6, 30), 'jun')
    s2 = _snap(pid, datetime(2026, 7, 31), 'jul')

    prev = db.get_prev_snapshot(s2)
    assert prev and prev['id'] == s1 and prev['cached_path'] == 'cache/jun.xml'
    assert db.get_prev_snapshot(s1) is None                 # nothing before the first

    assert db.snapshot_project_id(s2) == pid
    files = db.get_project_snapshot_files(pid)
    assert [f['id'] for f in files] == [s1, s2]             # oldest first


def test_milestone_cache_roundtrip_and_sentinel(temp_db):
    pid = db.upsert_project('P2', 'Factory')
    sid = _snap(pid, datetime(2026, 7, 31), 'jul2')

    scanned, rows = db.get_snapshot_milestones(sid)
    assert scanned is False and rows == []                  # not scanned yet

    db.cache_snapshot_milestones(sid, [
        {'activity_id': 'M900', 'name': 'Handover', 'task_type': 'FinishMilestone', 'finish_date': '2027-03-26'}])
    scanned, rows = db.get_snapshot_milestones(sid)
    assert scanned is True and len(rows) == 1 and rows[0]['activity_id'] == 'M900'

    # empty extraction still marks the snapshot scanned (sentinel), never re-parsed
    sid2 = _snap(pid, datetime(2026, 8, 31), 'aug2')
    db.cache_snapshot_milestones(sid2, [])
    scanned, rows = db.get_snapshot_milestones(sid2)
    assert scanned is True and rows == []
