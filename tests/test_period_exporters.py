"""p6_period.exporters — Excel mirror + the two-page management PDF layout."""
from p6_period.exporters import (progress_excel, report_excel, render_html, _verdict,
                                 _PROGRESS_HEADERS as _PROGRESS, _CRITICAL_HEADERS as _CRITICAL,
                                 _WATCH_HEADERS as _WATCH)


def _report():
    return {
        'project_name': 'Grain Terminal',
        'data_date_prev': '30-Jun-2026', 'data_date_now': '31-Jul-2026',
        'project_conclusion': 'Overall the project stands at 41% complete, 30 wd behind baseline.',
        'summary': {'actual_prev': 34.0, 'actual_now': 41.0, 'period_earned': 7.0,
                    'forecast_at_now': 43.0, 'forecast_achievement': 0.78, 'shortfall_pct': 2.0,
                    'forecast_finish_prev': '12-Mar-2027', 'forecast_finish_now': '26-Mar-2027', 'finish_slip_days': 14,
                    'delay_prev': 22, 'delay_now': 30, 'delay_change': 8,
                    'prev_spi': 0.85, 'curr_spi': 0.81, 'spi_variance': -0.04},
        'schedule_adherence': {'planned': 18, 'hit': 13, 'pct': 72.2},
        'recovery': {'work_remaining': 59.0, 'current_rate': 7.0, 'projected_finish': '10-Apr-2027',
                     'baseline_finish': '09-Feb-2027', 'required_rate': 9.8, 'required_achievement': 1.4,
                     'feasible': False, 'note': ''},
        'watch_list': {'rows': [{'activity_id': 'ME2', 'activity_name': 'Belt install', 'float_days': 1.0,
                                 'due_to_start': '02-Sep-2026', 'reason': 'Near-critical (1.0 wd float)'}]},
        'scurve': {'periods': ['Jan 26', 'Feb 26', 'Mar 26'], 'forecast': [10, 50, 90],
                   'actual': [8, 40, None], 'dd_prev_idx': 1, 'dd_now_idx': 2},
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
        'milestones': {'rows': [
            {'activity_id': 'M9', 'name': 'Handover', 'baseline_finish': '09-Feb-2027',
             'prev_forecast': '20-Feb-2027', 'curr_forecast': '01-Mar-2027',
             'slip_period_days': 9, 'slip_baseline_days': 20,
             'baseline_iso': '2027-02-09', 'prev_iso': '2027-02-20', 'curr_iso': '2027-03-01'}],
            'overall': {'activity_id': 'M9', 'name': 'Handover', 'baseline_finish': '09-Feb-2027',
             'prev_forecast': '20-Feb-2027', 'curr_forecast': '01-Mar-2027',
             'slip_period_days': 9, 'slip_baseline_days': 20,
             'baseline_iso': '2027-02-09', 'prev_iso': '2027-02-20', 'curr_iso': '2027-03-01'}},
        'conclusion': 'This period the project earned +7% against +9% forecast.',
    }


def test_verdict_flags_off_track_when_recovery_infeasible():
    level, head, detail = _verdict(_report())
    assert level == 'bad' and 'off track' in head.lower()


def test_progress_excel_headers_and_rows():
    headers, rows = progress_excel(_report())
    assert headers[0] == 'Activity ID' and 'Variance' in headers
    assert rows[0] == ['A1', 'Dredging', '82.0%', '100.0%', '▲ +18.0%', 'finished']
    assert rows[1][5] == 'progress reversed'


def test_report_excel_mirrors_every_section():
    headers, rows = report_excel(_report())
    assert headers[0].startswith('Update vs Update') and 'Grain Terminal' in headers
    flat = [str(c) for row in rows for c in row]
    for section in ['Execution Dashboard', 'Recovery outlook', 'Progress by activity — % complete this period',
                    'Critical-path movement in this window', 'Next-period watch list', 'What moved this period',
                    'Milestones — baseline vs previous vs current forecast', 'Project conclusion & outlook']:
        assert section in flat, section
    assert _PROGRESS in rows and _CRITICAL in rows and _WATCH in rows
    assert ['A1', 'Dredging', '82.0%', '100.0%', '▲ +18.0%', 'finished'] in rows
    assert any(r and r[0] == 'CV1' for r in rows)        # critical-movement data row
    assert any(r and r[0] == 'ME2' for r in rows)        # watch-list data row
    assert any('Handover' in str(r) for r in rows)       # milestone row
    assert '85%' in flat                                  # SPI shown as whole %


def test_report_excel_appends_activity_code_columns():
    rep = {
        'project_name': 'P', 'data_date_prev': 'a', 'data_date_now': 'b',
        'code_types': ['Discipline', 'Area'], 'summary': {},
        'progress': {'rows': [{'activity_id': 'A1', 'activity_name': 'Dredge', 'prev_pct': 10, 'curr_pct': 20,
                               'variance': 10, 'codes': {'Discipline': 'Civil', 'Area': 'Berth 1'}}]},
        'critical_movement': {'rows': [{'activity_id': 'A1', 'activity_name': 'Dredge', 'prev_finish': 'x',
                                        'curr_finish': 'y', 'slip_days': 3, 'float_days': 0, 'driver': 'd',
                                        'critical_status': 'stayed', 'codes': {'Discipline': 'Civil', 'Area': 'Berth 1'}}]},
        'watch_list': {'rows': [{'activity_id': 'A2', 'activity_name': 'Pour', 'float_days': 1,
                                 'due_to_start': 'z', 'reason': 'r', 'codes': {'Discipline': 'Civil'}}]},
    }
    ph, prows = progress_excel(rep)
    assert ph[-2:] == ['Discipline', 'Area']                 # code columns appended to the header
    assert prows[0][-2:] == ['Civil', 'Berth 1']             # and the values to each row
    _, rows = report_excel(rep)
    assert (_PROGRESS + ['Discipline', 'Area']) in rows and (_CRITICAL + ['Discipline', 'Area']) in rows
    assert ['A2', 'Pour', 1, 'z', 'r', 'Civil', ''] in rows  # watch row, missing Area → blank


def test_render_html_two_page_management_report():
    html = render_html(_report(), trend=None)
    for heading in ['Update vs Update — Period Report', 'Execution Dashboard', 'Recovery outlook',
                    'Progress by activity', 'Critical-path movement', 'Next-period watch list',
                    'What moved this period', 'Executive conclusion — this period',
                    'Progress — where you are', 'Milestones — project completion',
                    'What these numbers mean']:
        assert heading in html, heading
    assert 'Grain Terminal' in html
    assert 'Off track' in html                           # status banner verdict
    assert '12-Mar-2027' in html and '26-Mar-2027' in html   # both forecast finishes
    assert '09-Feb-2027' in html                         # recovery baseline finish
    assert 'Near-critical' in html                       # watch list content
    assert '85%' in html and '81%' in html               # SPI as whole %
    assert 'of the whole project' in html                # progress-bar 3-point explanation
    assert 'Activities completed' in html and 'Activities in progress' in html  # new counts
    assert 'Overall the project stands' in html          # project conclusion in the management box
    assert html.count('data-sec=') >= 10                 # section-tagged blocks (for the print picker)


def test_render_html_milestone_table_and_drift_chart():
    html = render_html(_report(), trend=None)
    # the milestone TABLE shows baseline/prev/current dates for each milestone
    assert 'Handover' in html and '09-Feb-2027' in html and '20-Feb-2027' in html
    # the drift chart is an SVG (dots per milestone), not the old trend line
    assert '<svg' in html and 'Previous forecast' in html and 'Current forecast' in html


def test_milestone_drift_svg_empty_when_no_milestones():
    from p6_period.exporters import _milestone_drift_svg
    assert _milestone_drift_svg({'milestones': {'rows': []}}) == ''
