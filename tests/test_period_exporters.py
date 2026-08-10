"""p6_period.exporters — progress Excel flattening and the PDF HTML layout."""
from p6_period.exporters import progress_excel, render_html, _trend_svg


def _report():
    return {
        'project_name': 'Grain Terminal', 'prev_file': 'jun.xml', 'update_file': 'jul.xml',
        'data_date_prev': '30-Jun-2026', 'data_date_now': '31-Jul-2026',
        'summary': {'actual_prev': 34.0, 'actual_now': 41.0, 'period_earned': 7.0,
                    'forecast_at_now': 43.0, 'forecast_achievement': 0.78,
                    'forecast_finish_now': '26-Mar-2027', 'finish_slip_days': 14,
                    'delay_now': 30, 'delay_change': 8},
        'progress': {'rows': [
            {'activity_id': 'A1', 'activity_name': 'Dredging', 'prev_pct': 82.0, 'curr_pct': 100.0,
             'variance': 18.0, 'finished': True, 'started': False, 'reversal': False},
            {'activity_id': 'A2', 'activity_name': 'Apron', 'prev_pct': 40.0, 'curr_pct': 35.0,
             'variance': -5.0, 'finished': False, 'started': False, 'reversal': True}]},
        'critical_movement': {'rows': [
            {'activity_id': 'CV1', 'activity_name': 'Quay', 'prev_finish': '18-Aug', 'curr_finish': '01-Sep',
             'slip_days': 10, 'float_days': 0, 'driver': 'progress shortfall', 'critical_status': 'stayed'}],
            'new_critical': 1},
        'buckets': {'counts': {'finished': 1, 'started': 0, 'slipped': 3, 'stalled': 2, 're_sequenced': 1}},
        'conclusion': 'This period the project earned +7% against +9% forecast.',
    }


def test_progress_excel_headers_and_rows():
    headers, rows = progress_excel(_report())
    assert headers[0] == 'Activity ID' and 'Variance' in headers
    assert rows[0] == ['A1', 'Dredging', 82.0, 100.0, 18.0, 'finished']
    assert rows[1][5] == 'progress reversed'          # reversal noted


def test_render_html_contains_every_section():
    html = render_html(_report(), trend=None)
    for heading in ['Update vs Update', 'Executive dashboard', 'Progress by activity',
                    'Critical-path movement', 'What moved this period', 'Executive conclusion']:
        assert heading in html
    assert 'Grain Terminal' in html and 'jun.xml' in html
    assert '+7.0%' in html                            # signed variance rendering
    assert 'This period the project earned' in html


def test_render_html_includes_trend_when_present():
    trend = {'periods': ['2026-06-30', '2026-07-31'],
             'series': [{'code': 'M900', 'name': 'Handover', 'task_type': 'FinishMilestone',
                         'finishes': ['2027-02-09', '2027-03-26']}]}
    html = render_html(_report(), trend=trend)
    assert 'Milestone finish trend' in html and '<svg' in html and 'Handover' in html
    # no trend block when there is nothing to plot
    assert 'Milestone finish trend' not in render_html(_report(), trend={'periods': [], 'series': []})


def test_trend_svg_empty_when_insufficient():
    assert _trend_svg({'periods': ['2026-06-30'], 'series': []}) == ''
