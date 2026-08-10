"""p6_period.report.build_report_from_data — assembles the Update-vs-Update report
dict from two updates and their metrics.compute() results (pure; no re-parse)."""
from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_period.report import build_report_from_data


def _act(code, name, pct, s, f, ts='Task'):
    return {'id': code, 'name': name, 'percent_complete': pct, 'task_type': ts,
            'planned_start': s, 'planned_finish': f, 'remaining_early_start': s,
            'remaining_early_finish': f, 'planned_duration': 8.0}


def _sched(acts, dd):
    d = ScheduleData()
    d.activities = {f'o{i}': a for i, a in enumerate(acts)}
    d.project = {'name': 'Grain Terminal', 'data_date': dd}
    return d


def test_build_report_assembles_all_slice1_sections():
    s, f = datetime(2026, 1, 1), datetime(2026, 12, 1)
    prev = _sched([_act('A1', 'Dredging', 0.55, s, f), _act('A2', 'Quay', 0.10, s, f)],
                  datetime(2026, 6, 30))
    curr = _sched([_act('A1', 'Dredging', 0.68, s, f), _act('A2', 'Quay', 0.22, s, f)],
                  datetime(2026, 7, 31))
    pm = {'overall_actual_pct': 0.34, 'delay_days': 22}
    cm = {'overall_actual_pct': 0.41, 'delay_days': 30}
    r = build_report_from_data(prev, curr, pm, cm)

    assert r['project_name'] == 'Grain Terminal'
    assert r['matched_activities'] == 2 and r['update_activity_count'] == 2
    assert r['summary']['actual_prev'] == 34.0 and r['summary']['actual_now'] == 41.0
    assert r['summary']['delay_change'] == 8
    # progress rows for both activities (both moved), biggest first (A1 +13 > A2 +12)
    assert [row['activity_id'] for row in r['progress']['rows']] == ['A1', 'A2']
    assert r['progress']['rows'][0]['variance'] == 13.0
    # scurve present with aligned arrays
    assert len(r['scurve']['periods']) == len(r['scurve']['forecast']) > 0
    # Slice 2 sections present
    assert 'rows' in r['critical_movement'] and 'new_critical' in r['critical_movement']
    assert set(r['buckets']['counts']) == {'finished', 'started', 'slipped', 'stalled', 're_sequenced'}
    assert isinstance(r['conclusion'], str) and 'this period' in r['conclusion'].lower()
    # project conclusion (overall) + slicer code types present
    assert isinstance(r['project_conclusion'], str) and 'overall' in r['project_conclusion'].lower()
    assert 'code_types' in r and isinstance(r['code_types'], list)


def test_build_report_flags_no_match():
    prev = _sched([_act('X1', 'a', 0.1, datetime(2026, 1, 1), datetime(2026, 6, 1))],
                  datetime(2026, 6, 30))
    curr = _sched([_act('Y1', 'b', 0.2, datetime(2026, 1, 1), datetime(2026, 6, 1))],
                  datetime(2026, 7, 31))
    r = build_report_from_data(prev, curr, {'overall_actual_pct': 0.2, 'delay_days': 0},
                               {'overall_actual_pct': 0.2, 'delay_days': 0})
    assert r['matched_activities'] == 0
