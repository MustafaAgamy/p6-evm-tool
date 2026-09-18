"""p6_period.trend — milestone finish trend assembly + IO orchestration.

assemble_trend is pure; milestone_trend is tested with injected fake db + parser so it
never touches the real database."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_period.trend import extract_milestones, assemble_trend, milestone_trend


def test_extract_milestones_only_milestone_types_with_iso_finish():
    d = ScheduleData()
    d.activities = {
        '1': {'id': 'M900', 'name': 'Handover', 'task_type': 'FinishMilestone',
              'planned_finish': datetime(2027, 2, 9)},
        '2': {'id': 'A1', 'name': 'Work', 'task_type': 'Task',
              'planned_finish': datetime(2026, 8, 1)},
    }
    ms = extract_milestones(d)
    assert ms == [{'activity_id': 'M900', 'name': 'Handover',
                   'task_type': 'FinishMilestone', 'finish_date': '2027-02-09'}]


def test_assemble_trend_series_track_finish_over_periods():
    snaps = [{'data_date': '2026-06-30 00:00:00'}, {'data_date': '2026-07-31 00:00:00'}]
    per = [
        [{'activity_id': 'M900', 'name': 'Handover', 'task_type': 'FinishMilestone', 'finish_date': '2027-02-09'},
         {'activity_id': 'M100', 'name': 'Mech done', 'task_type': 'FinishMilestone', 'finish_date': '2026-12-20'}],
        [{'activity_id': 'M900', 'name': 'Handover', 'task_type': 'FinishMilestone', 'finish_date': '2027-03-26'},
         {'activity_id': 'M100', 'name': 'Mech done', 'task_type': 'FinishMilestone', 'finish_date': '2026-12-20'}],
    ]
    t = assemble_trend(snaps, per)
    assert t['periods'] == ['2026-06-30', '2026-07-31']
    by = {s['code']: s for s in t['series']}
    assert by['M900']['finishes'] == ['2027-02-09', '2027-03-26']    # slipping
    assert by['M100']['finishes'] == ['2026-12-20', '2026-12-20']    # holding
    # latest (later) finish milestone ranks first
    assert t['series'][0]['code'] == 'M900'


def test_assemble_trend_aligns_missing_milestone_as_none():
    snaps = [{'data_date': '2026-06-30'}, {'data_date': '2026-07-31'}]
    per = [[], [{'activity_id': 'M1', 'name': 'New', 'task_type': 'FinishMilestone', 'finish_date': '2027-01-01'}]]
    t = assemble_trend(snaps, per)
    assert t['series'][0]['finishes'] == [None, '2027-01-01']


class _FakeDB:
    """Minimal db stand-in: two snapshots, milestones cached only for the second."""
    def __init__(self):
        self.cached = {}
    def snapshot_project_id(self, sid):
        return 7
    def get_project_snapshot_files(self, pid):
        return [{'id': 1, 'data_date': '2026-06-30', 'original_path': None, 'cached_path': 'c1.xml'},
                {'id': 2, 'data_date': '2026-07-31', 'original_path': None, 'cached_path': 'c2.xml'}]
    def get_snapshot_milestones(self, sid):
        if sid in self.cached:
            return True, self.cached[sid]
        return False, []
    def resolve_xml_path(self, orig, cached):
        return cached
    def cache_snapshot_milestones(self, sid, ms):
        self.cached[sid] = ms


def test_milestone_trend_parses_uncached_and_caches(monkeypatch=None):
    fake = _FakeDB()
    parsed = {'c1.xml': [{'activity_id': 'M1', 'name': 'Finish', 'task_type': 'FinishMilestone', 'finish_date': '2027-01-05'}],
              'c2.xml': [{'activity_id': 'M1', 'name': 'Finish', 'task_type': 'FinishMilestone', 'finish_date': '2027-01-20'}]}
    calls = []

    def fake_parse(path):
        calls.append(path)
        d = ScheduleData()
        # emulate one finish milestone with the finish per file
        fin = {'c1.xml': datetime(2027, 1, 5), 'c2.xml': datetime(2027, 1, 20)}[path]
        d.activities = {'o': {'id': 'M1', 'name': 'Finish', 'task_type': 'FinishMilestone', 'planned_finish': fin}}
        return d

    t = milestone_trend(1, db_module=fake, parse=fake_parse)
    assert t['periods'] == ['2026-06-30', '2026-07-31']
    assert t['series'][0]['finishes'] == ['2027-01-05', '2027-01-20']
    assert calls == ['c1.xml', 'c2.xml']            # both parsed once
    # second call hits the cache — no further parsing
    calls.clear()
    milestone_trend(1, db_module=fake, parse=fake_parse)
    assert calls == []
