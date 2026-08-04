from datetime import datetime
from p6_evm.parser import ScheduleData
from p6_evm.engineering_p6 import engineering_from_p6


def _act(oid, aid, trade, cycle, sub_wbs, pct):
    return {'object_id': oid, 'id': aid, 'name': aid, 'percent_complete': pct,
            'activity_codes': {'Trade Design': trade, 'Design Cycle': cycle,
                               'Design SUB WBS': sub_wbs}}


def _data(acts, baselines=None, data_date=datetime(2026, 5, 10)):
    d = ScheduleData()
    d.project = {'data_date': data_date}
    d.activities = {a['object_id']: a for a in acts}
    d.baseline_by_id = baselines or {}
    return d


def test_submittal_approval_pair_counts():
    acts = [
        _act('1', 'DD.SUB.PL.1010', 'Civil', 'Detailed Design', 'Detailed Design Submittal', 1.0),
        _act('2', 'DD.APP.PL.1010', 'Civil', 'Detailed Design', 'Detailed Design Approval', 0.0),
        _act('3', 'DD.SUB.PL.1020', 'Civil', 'Detailed Design', 'Detailed Design Submittal', 0.0),
    ]
    r = engineering_from_p6(_data(acts))
    g = r[('Civil', 'Detailed Design')]
    assert g['req'] == 2               # two submittal activities = two drawings
    assert g['actual_sub'] == 1        # one submittal complete
    assert g['actual_appr'] == 0       # approval not complete
    assert g['actual_sub_pct'] == 50.0


def test_planned_by_baseline_vs_data_date():
    acts = [
        _act('1', 'DD.SUB.A.1', 'MEP', 'Detailed Design', 'Detailed Design Submittal', 0.0),
        _act('2', 'DD.SUB.A.2', 'MEP', 'Detailed Design', 'Detailed Design Submittal', 0.0),
    ]
    baselines = {
        'DD.SUB.A.1': {'planned_finish': datetime(2026, 1, 1)},   # before data date → planned
        'DD.SUB.A.2': {'planned_finish': datetime(2026, 12, 1)},  # after → not planned
    }
    g = engineering_from_p6(_data(acts, baselines))[('MEP', 'Detailed Design')]
    assert g['req'] == 2
    assert g['planned_sub'] == 1
    assert g['planned_sub_pct'] == 50.0


def test_non_engineering_ignored():
    acts = [{'object_id': '1', 'id': 'CONS.1', 'name': 'Pour', 'percent_complete': 0.5,
             'activity_codes': {'Type of Works': 'Civil Works'}}]
    assert engineering_from_p6(_data(acts)) == {}
