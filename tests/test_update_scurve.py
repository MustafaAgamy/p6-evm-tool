"""Update Analysis · Progress S-curve (section 6) and the summary band (section 1).

Rules (Ibrahim, 2026-11-23):
- Planned  = the Time Status Planned % rule at every month end + the data date.
- Earned   = rebuilt from actual start/finish x % complete; an earlier imported update of the
             same project puts its own Earned % at its data date.
- Forecast = remaining work spread over P6's remaining early dates.
At the data date the curve equals Time Status exactly.
"""
from tests.test_update_analysis import _xml, _parse_and_compute
from p6_update.analysis import time_status, build_report_from_data
from p6_update.scurve import progress_scurve, merge_earlier, earned_pct


def _with_actuals(xml, actuals):
    """actuals: {code: (actual_start, actual_finish_or_None)} → adds P6 actual dates."""
    for code, (s, f) in actuals.items():
        tag = f'<Id>{code}</Id>'
        extra = f'<ActualStartDate>{s}T00:00:00</ActualStartDate>'
        if f:
            extra += f'<ActualFinishDate>{f}T00:00:00</ActualFinishDate>'
        xml = xml.replace(tag, tag + extra, 1)
    return xml


def _sample():
    # Baseline 01 Jan → 31 Dec 2025, data date 02 Jul 2025. A1 done (Jan–Jun),
    # A2 half done (started 01 Jun), A3 not started (remaining Sep–Dec).
    xml = _xml('2025-07-02', [
        (10, 'A1', 'Act 1', 1.0, '2025-01-01', '2025-06-30', 80, 100, {}),
        (11, 'A2', 'Act 2', 0.5, '2025-05-01', '2025-08-31', 80, 100, {}),
        (12, 'A3', 'Act 3', 0.0, '2025-09-01', '2025-12-31', 80, 100, {}),
    ])
    xml = _with_actuals(xml, {'A1': ('2025-01-01', '2025-06-30'), 'A2': ('2025-06-01', None)})
    return _parse_and_compute(xml)


def _dd_point(sc):
    pts = [p for p in sc['points'] if p['kind'] == 'data_date']
    assert len(pts) == 1
    return pts[0]


def test_curve_meets_time_status_exactly_at_the_data_date():
    data, metrics = _sample()
    ts = time_status(data, metrics)
    sc = progress_scurve(data, metrics)
    p = _dd_point(sc)
    assert p['date'] == '2025-07-02'
    assert p['planned'] == ts['planned_pct']
    assert p['earned'] == ts['actual_pct']
    assert p['forecast'] == ts['actual_pct']
    assert p['earned_source'] == 'this update'


def test_month_ends_in_order_and_curves_reach_100():
    data, metrics = _sample()
    sc = progress_scurve(data, metrics)
    dates = [p['date'] for p in sc['points']]
    assert dates == sorted(dates)
    months = [p for p in sc['points'] if p['kind'] == 'month']
    assert months[0]['date'] == '2025-01-31' and months[-1]['date'] == '2025-12-31'
    planned = [p['planned'] for p in sc['points']]
    assert planned == sorted(planned) and planned[-1] == 100.0
    fc = [p['forecast'] for p in sc['points'] if p['forecast'] is not None]
    assert fc == sorted(fc) and fc[-1] == 100.0
    # earned only up to the data date, forecast only from it
    for p in sc['points']:
        if p['date'] < '2025-07-02':
            assert p['earned'] is not None and p['forecast'] is None
        if p['date'] > '2025-07-02':
            assert p['earned'] is None and p['forecast'] is not None


def test_earned_is_rebuilt_from_actual_dates():
    data, metrics = _sample()
    sc = progress_scurve(data, metrics)
    by = {p['date']: p for p in sc['points']}
    # nothing started before 01 Jan; A1 (1/3 of the budget) is half way by end of March
    assert by['2025-01-31']['earned'] < by['2025-03-31']['earned'] < by['2025-05-31']['earned']
    assert 10 < by['2025-03-31']['earned'] < 23
    assert by['2025-03-31']['earned_source'] == 'rebuilt'


def test_earlier_update_point_replaces_the_rebuilt_value_at_its_date():
    data, metrics = _sample()
    sc = progress_scurve(data, metrics)
    merged = merge_earlier(sc, [
        {'snapshot_id': 7, 'label': 'Update May', 'data_date': '2025-05-15', 'earned': 30.0, 'on': True},
        {'snapshot_id': 8, 'label': 'Update Apr', 'data_date': '2025-04-30', 'earned': 20.0, 'on': False},
        {'snapshot_id': 9, 'label': 'Later', 'data_date': '2025-08-01', 'earned': 60.0, 'on': True},
    ])
    upd = [p for p in merged['points'] if p['kind'] == 'update']
    assert [(p['date'], p['earned'], p['earned_source']) for p in upd] == [('2025-05-15', 30.0, 'update')]
    dates = [p['date'] for p in merged['points']]
    assert dates == sorted(dates)
    # the data-date point is untouched, the rebuilt base is kept for re-merging
    assert _dd_point(merged)['earned'] == _dd_point(sc)['earned']
    assert merged['base_points'] == sc['points']
    # merging again from the merged result does not double the point
    again = merge_earlier(merged, merged['earlier'])
    assert len([p for p in again['points'] if p['kind'] == 'update']) == 1


def test_earned_pct_matches_time_status():
    data, metrics = _sample()
    assert earned_pct(metrics) == time_status(data, metrics)['actual_pct']


def test_report_carries_scurve_and_summary():
    data, metrics = _sample()
    rep = build_report_from_data(data, metrics)
    assert _dd_point(rep['scurve'])['planned'] == rep['time_status']['planned_pct']
    s = rep['summary']
    keys = [k['key'] for k in s['kpis']]
    assert keys == ['elapsed', 'planned', 'earned', 'spi', 'finish', 'delay']
    assert s['status'] in ('behind', 'on_track', 'baseline')
    assert s['headline']


def test_summary_behind_with_a_late_completion_milestone():
    xml = _xml('2025-07-02', [
        (10, 'A1', 'Act 1', 0.2, '2025-01-01', '2025-06-30', 80, 100, {}),
    ], milestones=[(50, 'M1', 'Completion', '2025-06-30', 100)], rels=[(10, 50)])
    # push the update's remaining dates later than the baseline → the milestone slips
    xml = xml.replace('<RemainingEarlyFinishDate>2025-06-30T00:00:00</RemainingEarlyFinishDate>',
                      '<RemainingEarlyFinishDate>2025-08-29T00:00:00</RemainingEarlyFinishDate>')
    data, metrics = _parse_and_compute(xml)
    rep = build_report_from_data(data, metrics)
    s = rep['summary']
    assert s['status'] == 'behind'
    kp = {k['key']: k for k in s['kpis']}
    assert kp['earned']['value'] == f"{rep['time_status']['actual_pct']:.2f}%"
    assert kp['planned']['value'] == f"{rep['time_status']['planned_pct']:.2f}%"


def test_no_data_date_gives_an_empty_curve():
    data, metrics = _sample()
    data.project['data_date'] = None
    sc = progress_scurve(data, metrics)
    assert sc['points'] == []
