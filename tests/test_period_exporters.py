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
             'variance': 18.0, 'finished': True, 'started': False, 'reversal': False, 'status': 'Completed'},
            {'activity_id': 'A2', 'activity_name': 'Apron', 'prev_pct': 40.0, 'curr_pct': 35.0,
             'variance': -5.0, 'finished': False, 'started': False, 'reversal': True, 'status': 'In Progress'}]},
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
        'critical_path': {
            'previous': [
                {'id': 'A', 'name': 'Excavate', 'wbs_path': 'Plant > Foundations > Excavation', 'codes': {'Discipline': 'Civil'}, 'start': '2026-08-01', 'finish': '2026-09-30'},
                {'id': 'B', 'name': 'Steel erection', 'wbs_path': 'Plant > Steel > Erection', 'codes': {'Discipline': 'Structural'}, 'start': '2026-10-01', 'finish': '2026-12-15'},
                {'id': 'C', 'name': 'Cladding', 'wbs_path': 'Plant > Cladding > Panels', 'codes': {'Discipline': 'Arch'}, 'start': '2026-12-16', 'finish': '2027-02-01'},
                {'id': 'D', 'name': 'Roofing', 'wbs_path': 'Plant > Roof > Sheeting', 'codes': {'Discipline': 'Arch'}, 'start': '2027-02-02', 'finish': '2027-03-12'},
            ],
            'current': [
                {'id': 'A', 'name': 'Excavate', 'wbs_path': 'Plant > Foundations > Excavation', 'codes': {'Discipline': 'Civil'}, 'start': '2026-08-01', 'finish': '2026-09-30'},
                {'id': 'B', 'name': 'Steel erection', 'wbs_path': 'Plant > Steel > Erection', 'codes': {'Discipline': 'Structural'}, 'start': '2026-10-01', 'finish': '2026-12-15'},
                {'id': 'E', 'name': 'Furnace', 'wbs_path': 'Plant > Furnace > Melter', 'codes': {'Discipline': 'Mech'}, 'start': '2026-12-16', 'finish': '2027-02-20'},
                {'id': 'F', 'name': 'Commissioning', 'wbs_path': 'Plant > Commissioning > Cold end', 'codes': {'Discipline': 'Mech'}, 'start': '2027-02-21', 'finish': '2027-03-26'},
            ],
        },
    }


def test_verdict_flags_off_track_when_recovery_infeasible():
    level, head, detail = _verdict(_report())
    assert level == 'bad' and 'off track' in head.lower()


def test_progress_excel_headers_and_rows():
    headers, rows = progress_excel(_report())
    assert headers[0] == 'Activity ID' and 'Variance' in headers
    assert rows[0] == ['A1', 'Dredging', 'Completed', '82.0%', '100.0%', '▲ +18.0%']
    assert rows[1][2] == 'In Progress (reversed)'


def test_report_excel_mirrors_every_section():
    headers, rows = report_excel(_report())
    assert headers[0].startswith('Update vs Update') and 'Grain Terminal' in headers
    flat = [str(c) for row in rows for c in row]
    for section in ['Execution Dashboard', 'Recovery outlook', 'Progress by activity — % complete this period',
                    'Critical-path movement in this window', 'Next-period watch list', 'What moved this period',
                    'Milestones — baseline vs previous vs current forecast', 'Project conclusion & outlook']:
        assert section in flat, section
    assert _PROGRESS in rows and _CRITICAL in rows and _WATCH in rows
    assert ['A1', 'Dredging', 'Completed', '82.0%', '100.0%', '▲ +18.0%'] in rows
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


# ── #02 — Critical-path comparison as a timeline (Option A) ──────────────────

def test_critical_route_data_shared_prefix_divergence_and_conclusion():
    from p6_period.exporters import _cp_timeline_data
    d = _cp_timeline_data(_report(), 'leaf-parent')
    assert [s['key'] for s in d['prev']] == ['Foundations', 'Steel', 'Cladding', 'Roof']
    assert [s['key'] for s in d['curr']] == ['Foundations', 'Steel', 'Furnace', 'Commissioning']
    assert d['divergence'] == 2 and d['changed'] is True   # shared through Steel, then the route splits
    assert d['slip_days'] == 14
    assert d['prev'][0]['start'] == '2026-08-01' and d['curr'][-1]['finish'] == '2027-03-26'
    # the plain conclusion names where it rerouted, the new route, and the P6 finish
    assert 'rerouted at Steel' in d['conclusion'] and 'Furnace' in d['conclusion'] and '26-Mar-2027' in d['conclusion']


def test_critical_compare_two_rows_new_route_and_slip_when_changed():
    from p6_period.exporters import _critical_compare_html
    html = _critical_compare_html(_report())
    assert 'cpchain' in html                            # connected-chain layout (not boxes, not an SVG)
    assert 'Was — last update' in html and 'Now — this update' in html   # both rows on a reroute
    assert 'cpblk gone' in html                         # the dropped old route (greyed)
    assert 'cpblk new' in html                          # the new route (red)
    assert 'rerouted at Steel' in html
    assert 'Furnace' in html and 'Commissioning' in html
    assert '12-Mar-2027' in html and '26-Mar-2027' in html   # both finish flags
    assert 'moved +14 working days' in html             # the slip note (total, not per-segment)


def test_critical_compare_one_row_when_route_unchanged():
    from p6_period.exporters import _critical_compare_html, _cp_timeline_data
    rep = _report()
    rep['critical_path'] = {'previous': rep['critical_path']['previous'],
                            'current': rep['critical_path']['previous']}   # same route both updates
    d = _cp_timeline_data(rep, 'leaf-parent')
    assert d['divergence'] == len(d['curr']) and d['changed'] is False     # no divergence
    assert 'Same critical path as last period' in d['conclusion']
    html = _critical_compare_html(rep)
    assert "This period's critical path" in html         # single-row heading
    assert 'Was — last update' not in html               # no second row when unchanged
    assert 'cpblk gone' not in html and 'cpblk new' not in html   # one blue chain, no red/grey


def test_render_html_uses_connected_chain_not_boxes():
    html = render_html(_report(), trend=None)
    assert 'cpchain' in html and 'cpblk shared' in html  # the connected-chain critical path (default style)
    assert 'rerouted at Steel' in html                   # plain conclusion in the section
    assert 'the finish-driving route' in html.lower()    # section heading


def test_critical_compare_timeline_style_draws_svg_gantt():
    from p6_period.exporters import _critical_compare_html
    html = _critical_compare_html(_report(), style='timeline')
    assert '<svg' in html and 'Critical path timeline' in html    # date-axis Gantt, not the block chain
    assert 'cpchain' not in html and 'cptable' not in html
    assert 'WAS · 30-Jun-2026' in html and 'NOW · 31-Jul-2026' in html   # the two data dates label the rows
    assert 'rerouted here' in html and '#f87171' in html          # divergence marker + new route drawn red
    assert 'finish 12-Mar-2027' in html and 'finish 26-Mar-2027' in html
    assert '+14 wd' in html                                        # the total-slip bracket
    assert 'rerouted at Steel' in html                            # the shared plain conclusion is still there


def test_critical_compare_table_style_lists_routes_with_red_new_tail():
    from p6_period.exporters import _critical_compare_html
    html = _critical_compare_html(_report(), style='table')
    assert 'cptable' in html and '<svg' not in html and 'cpchain' not in html
    assert 'Driving route' in html and 'Forecast finish' in html and 'Rerouted at' in html
    assert 'Foundations → Steel → Cladding → Roof' in html         # the Was route in full (plain)
    assert 'cpt-red' in html and '(+14 wd)' in html                # new tail + slip shown in red
    assert '12-Mar-2027' in html and '26-Mar-2027' in html
    assert 'rerouted at Steel' in html                            # the shared plain conclusion


def test_critical_compare_table_unchanged_says_so():
    from p6_period.exporters import _critical_compare_html
    rep = _report()
    rep['critical_path'] = {'previous': rep['critical_path']['previous'],
                            'current': rep['critical_path']['previous']}
    rep['summary'] = dict(rep['summary'], finish_slip_days=0,               # same route AND no slip
                          forecast_finish_now=rep['summary']['forecast_finish_prev'])
    html = _critical_compare_html(rep, style='table')
    assert 'cptable' in html and 'unchanged this period' in html   # the Rerouted-at row reads unchanged
    assert 'cpt-red' not in html                                   # nothing red when the route held and no slip


def test_render_html_critical_style_carries_into_pdf():
    # check for the rendered markup (class="cpchain"), not the CSS block which always defines .cpchain
    assert 'class="cpchain"' in render_html(_report(), trend=None)               # default = chain
    tl = render_html(_report(), trend=None, critical_style='timeline')
    assert 'Critical path timeline' in tl and 'class="cpchain"' not in tl        # timeline replaces the chain in the PDF
    tb = render_html(_report(), trend=None, critical_style='table')
    assert 'class="cptable"' in tb and 'class="cpchain"' not in tb               # table replaces the chain in the PDF


# ── #01 — the exported PDF must respect the on-screen activity-code filter ────

def _coded_report():
    """A report whose activity tables carry two different Discipline codes, so a code
    filter can be shown to keep one and drop the other."""
    rep = _report()
    rep['code_types'] = ['Discipline']
    rep['progress'] = {'rows': [
        {'activity_id': 'CIV1', 'activity_name': 'Dredging', 'prev_pct': 82.0, 'curr_pct': 100.0,
         'variance': 18.0, 'status': 'Completed', 'reversal': False, 'codes': {'Discipline': 'Civil'}},
        {'activity_id': 'MEC1', 'activity_name': 'Ductwork', 'prev_pct': 10.0, 'curr_pct': 25.0,
         'variance': 15.0, 'status': 'In Progress', 'reversal': False, 'codes': {'Discipline': 'Mechanical'}}]}
    rep['critical_movement'] = {'rows': [
        {'activity_id': 'CIV1', 'activity_name': 'Dredging', 'wbs': 'Berth', 'prev_finish': 'x', 'curr_finish': 'y',
         'slip_days': 3, 'float_days': 0, 'driver': 'd', 'critical_status': 'stayed', 'codes': {'Discipline': 'Civil'}},
        {'activity_id': 'MEC1', 'activity_name': 'Ductwork', 'wbs': 'Plant', 'prev_finish': 'x', 'curr_finish': 'y',
         'slip_days': 2, 'float_days': 1, 'driver': 'd', 'critical_status': 'stayed', 'codes': {'Discipline': 'Mechanical'}}],
        'new_critical': 0}
    rep['watch_list'] = {'rows': [
        {'activity_id': 'CIV1', 'activity_name': 'Dredging', 'float_days': 0, 'due_to_start': 'z', 'reason': 'r', 'codes': {'Discipline': 'Civil'}},
        {'activity_id': 'MEC1', 'activity_name': 'Ductwork', 'float_days': 1, 'due_to_start': 'z', 'reason': 'r', 'codes': {'Discipline': 'Mechanical'}}]}
    return rep


def test_render_html_code_filter_limits_activity_tables_to_selected_code():
    rep = _coded_report()
    full = render_html(rep, trend=None)
    assert 'CIV1' in full and 'MEC1' in full            # unfiltered shows both disciplines
    filtered = render_html(rep, trend=None, code_filter={'type': 'Discipline', 'value': 'Civil'})
    assert 'CIV1' in filtered                           # the Civil activity is kept
    assert 'MEC1' not in filtered                       # the Mechanical activity is filtered out of every table
    assert 'Filtered:' in filtered and 'Discipline' in filtered and 'Civil' in filtered
