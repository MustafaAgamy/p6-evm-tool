"""Consultant Review exporters — logic_excel (flattened change table) and render_html
(landscape consultant PDF page, with or without the before/after impact)."""
import report_theme
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


def test_render_html_includes_dashboard_charts():
    r = _report()
    r['dashboard']['delay_working_days'] = 13
    r['change_summary']['items'] = [
        {'kind': 'lag', 'label': 'driving lag changed', 'count': 2, 'group': 'logic'},
        {'kind': 'extended', 'label': 'duration extended', 'count': 1, 'group': 'duration'},
    ]
    h = render_html(r)
    assert 'How the logic was changed' in h        # change-type bar chart
    assert 'driving lag changed' in h              # the logic bar label
    assert 'cbf' in h                              # a bar fill was drawn
    assert 'Delay vs baseline' in h                # delay (date-based) card
    assert '+13' in h                              # delay headline (13 working days behind)
    assert 'working days behind' in h              # #04 date-based delay wording
    assert 'Changed activities' in h               # donut card
    assert 'no float' in h                         # impact-on-finish legend explains the blanks
    assert '<svg' in h                             # delay + donut are SVG


def test_render_html_caps_tables_for_manager_report():
    from p6_compare.exporters import _PDF_ROW_CAP
    r = _report()
    n = _PDF_ROW_CAP + 20
    r['logic']['rows'] = [dict(r['logic']['rows'][0], activity_id=f'A{i}') for i in range(n)]
    r['durations']['rows'] = [dict(r['durations']['rows'][0], activity_id=f'D{i}') for i in range(n)]
    h = render_html(r)
    assert f'first {_PDF_ROW_CAP} of {n} logic' in h        # logic table capped, points to Excel
    assert f'{_PDF_ROW_CAP} largest of {n} duration' in h   # duration table capped
    assert 'Excel export' in h


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


def test_render_html_dark_theme_injects_palette():
    h = render_html(_report(), theme='dark')
    assert 'data-rpt-theme="dark"' in h
    assert report_theme.THEMES['dark']['rpt-accent'] in h   # '#5b9bff'


def test_render_html_default_theme_is_light_full_document():
    h = render_html(_report())
    assert h.startswith('<!doctype html>') and h.rstrip().endswith('</html>')
    assert 'data-rpt-theme="light"' in h


# ── Report-Contents section picker (sections=None → everything, unchanged) ─────────────

def test_render_html_sections_default_none_includes_everything():
    h = render_html(_report(), _impact())
    assert 'Reported delay (as submitted)' in h          # dashboard tiles
    assert 'How the logic was changed' in h              # charts
    assert 'Driving logic &amp; lag changes vs baseline' in h
    assert 'Duration &amp; remaining changes vs baseline' in h
    assert 'Impact — reported vs but-for delay' in h     # impact (only rendered when impact given)


def test_render_html_sections_subset_omits_unselected_keeps_chosen():
    h = render_html(_report(), _impact(), sections=['logic'])
    # Chosen section's content is present, in full.
    assert 'Driving logic &amp; lag changes vs baseline' in h
    assert 'A1120' in h and 'Excavate zone B' in h and 'FS+10' in h
    # Every other section is omitted.
    assert 'Reported delay (as submitted)' not in h
    assert 'How the logic was changed' not in h
    assert 'Duration &amp; remaining changes vs baseline' not in h
    assert 'Rebar' not in h                              # duration table content gone
    assert 'Impact — reported vs but-for delay' not in h
    assert 'Consultant recommendation' not in h


def test_render_html_sections_content_of_kept_section_unchanged():
    r, impact = _report(), _impact()
    h_full = render_html(r, impact)
    h_subset = render_html(r, impact, sections=['duration'])
    # The duration table's numbers/content are identical whether or not siblings render.
    assert 'A1250' in h_full and 'A1250' in h_subset
    assert '18 d' in h_full and '18 d' in h_subset       # update_orig_days, unchanged
    assert '3 d' in h_full and '3 d' in h_subset          # remaining_minus_baseline_days, unchanged


def test_render_html_sections_empty_list_still_self_contained_document():
    h = render_html(_report(), sections=[])
    assert h.startswith('<!doctype html>') and h.rstrip().endswith('</html>')
    assert 'Driving logic' not in h and 'Duration &amp; remaining' not in h


def test_render_html_sections_omits_dashboard_and_charts_independently():
    h = render_html(_report(), _impact(), sections=['dashboard'])
    assert '>Reported delay<' in h                         # dashboard summary tile kept
    assert 'How the logic was changed' not in h            # charts omitted
    assert 'Driving logic &amp; lag changes vs baseline' not in h
    assert 'Impact — reported vs but-for delay' not in h   # the separate impact section omitted
