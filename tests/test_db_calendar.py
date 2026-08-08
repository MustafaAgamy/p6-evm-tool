"""Task 3 — DB persistence for the Calendar Audit: snapshot-level calendar_audit
JSON, and per-project settings (location, shutdown reasons, manual shutdowns)."""
import db


def test_calendar_audit_roundtrip(temp_db):
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, None, 'a.xml', None, 'h1', 5, 2)
    db.save_calendar_audit(sid, {'dashboard': {'total_working_days': 42}, 'usage': []})
    got = db.get_calendar_audit(sid)
    assert got['dashboard']['total_working_days'] == 42
    assert db.get_calendar_audit(9999) is None


def test_project_settings_merge_roundtrip(temp_db):
    pid = db.upsert_project('P2', 'Proj2')
    assert db.get_project_settings(pid) == {}
    db.save_project_settings(pid, {'location': {'lat': 24.7, 'lon': 46.6, 'name': 'Riyadh'}})
    db.save_project_settings(pid, {'manual_shutdowns': [
        {'start': '2025-01-01', 'end': '2025-01-05', 'reason': 'Turnaround'}]})
    s = db.get_project_settings(pid)
    assert s['location']['lat'] == 24.7            # first save preserved
    assert s['manual_shutdowns'][0]['reason'] == 'Turnaround'  # second merged in


def test_delete_project_removes_calendar_and_settings(temp_db):
    pid = db.upsert_project('P3', 'P3')
    sid = db.insert_snapshot(pid, None, 'a.xml', None, 'h3', 1, 1)
    db.save_calendar_audit(sid, {'x': 1})
    db.save_project_settings(pid, {'location': {'lat': 1}})
    db.delete_project(pid)
    assert db.get_calendar_audit(sid) is None
    assert db.get_project_settings(pid) == {}
