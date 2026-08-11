"""Consultant Review exporters — logic_excel (flattened change table) and render_html
(landscape consultant PDF page, with or without the before/after impact)."""
from p6_compare.exporters import render_html, logic_excel


def _report():
    return {
        'project_name': 'Riyadh Metro', 'data_date': '09-Feb-2026',
        'baseline_file': 'baseline.xer', 'update_file': 'update.xml',
        'baseline_finish': '09-Feb-2027', 'update_finish': '22-Feb-2027',
        'dashboard': {'changed_activities': 3, 'logic_changed': 2, 'duration_only': 1},
        'change_summary': {'items': [{'kind': 'lag', 'label': 'driving lag changed', 'count': 2}]},
        'logic': {'rows': [{
            'activity_id': 'A1120', 'activity_name': 'Excavate zone B', 'change_label': 'Lag ↑',
            'baseline_preds': [{'code': 'A1050', 'name': 'Clearance', 'type': 'FS', 'lag_days': 0, 'status': 'same'}],
            'baseline_succs': [], 'update_succs': [],
            'update_preds': [{'code': 'A1050', 'name': 'Clearance', 'type': 'FS', 'lag_days': 10, 'status': 'changed'}],
        }]},
        'durations': {'rows': [{'activity_id': 'A1250', 'activity_name': 'Rebar', 'baseline_orig_days': 12,
                                'update_orig_days': 18, 'remaining_days': 15,
                                'remaining_minus_baseline_days': 3, 'status': 'extended'}]},
    }


def _impact():
    return {
        'delay_after': 18, 'delay_before': 4, 'manufactured_days': 14,
        'forecast': {'baseline': '09-Feb-2027', 'before': '15-Feb-2027', 'after': '22-Feb-2027'},
        'milestones': [{'activity_id': 'M900', 'name': 'Handover', 'baseline_finish': '09-Feb-2027',
                        'before_finish': '15-Feb-2027', 'after_finish': '22-Feb-2027'}],
        'scurve': {'periods': ['Jan 26', 'Feb 26', 'Mar 26'], 'baseline': [0, 50, 100],
                   'before': [0, 60, 100], 'after': [0, 40, 90]},
        'recommendation': 'The reported delay is 18 working days; with the changes reverted it is 4.',
    }


def test_logic_excel_headers_and_flattened_links():
    headers, rows = logic_excel(_report())
    # Leading serial "#" column, then the 15 relationship columns (16 total).
    assert len(headers) == 16 and headers[0] == '#' and headers[1] == 'Activity ID'
    assert rows[0][0] == 1 and rows[0][1] == 'A1120' and rows[0][3] == 'Lag ↑'
    assert 'FS+10' in rows[0][11]   # update pred rel column carries the +10 lag


def test_logic_excel_serials_number_every_row():
    report = _report()
    report['logic']['rows'] = report['logic']['rows'] * 3   # three identical rows
    _, rows = logic_excel(report)
    assert [r[0] for r in rows] == [1, 2, 3]


def test_render_html_dashboard_reconciles_changed_counts():
    h = render_html(_report())
    assert '>#<' in h                 # serial column header in the logic table
    assert '2 logic/lag' in h         # dashboard breakdown of the 3 changed activities
    assert '1 duration' in h


def test_render_html_without_impact_is_self_contained_landscape():
    h = render_html(_report())
    assert h.startswith('<!doctype html>')
    assert 'landscape' in h
    assert 'A1120' in h and 'Excavate zone B' in h
    assert 'Duration' in h
    assert 'S-curve' not in h and 'Consultant recommendation' not in h   # no impact yet


def test_render_html_with_impact_adds_scurve_and_recommendation():
    h = render_html(_report(), _impact())
    assert 'Impact — reported vs but-for delay' in h
    assert '<polyline' in h                    # three-way S-curve drawn
    assert 'Consultant recommendation' in h
    assert 'Overall completion' in h           # overall completion only (no per-milestone table)
    assert '14 d' in h                          # manufactured tile
