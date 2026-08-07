from p6_audit.report import render_module_report, short_wbs
from p6_audit.exporters import excel_columns


def _dangling():
    return {
        'module': 'dangling', 'name': 'Dangling Activities',
        'score': 94, 'grade': 'Excellent', 'pct': 1.2,
        'kpis': {'total_activities': 1466, 'total_dangling': 18,
                 'start_dangling': 5, 'finish_dangling': 1, 'both_dangling': 12, 'dangling_pct': 1.2},
        'wbs_summary': [],
        'findings': [{
            'finding_id': 'd1', 'activity_id': 'A240', 'activity_name': 'Cast Column C3',
            'wbs_path': 'Project > Civil > Silo 8 > Columns', 'severity': 'High',
            'logic_issue': 'Dangling Start', 'predecessors': 'No Predecessor',
            'successors': 'A260 - Slab (FS)', 'suggested_fix': 'Add an FS predecessor.',
            'suggested_fix_2': 'Predecessor: add a Start-to-Start tie',
        }],
    }


def _float():
    return {
        'module': 'float', 'name': 'Float Analysis',
        'score': 0, 'grade': 'Critical', 'pct': 40.3,
        'kpis': {'total_activities': 1466, 'above_threshold': 591, 'float_pct': 40.3,
                 'threshold': 44, 'max_float': 247.0, 'avg_float': 64.3},
        'wbs_summary': [{'wbs': 'Project > Civil > External', 'activities': 7, 'high': 6, 'pct': 85.7, 'grade': 'Critical'}],
        'findings': [{
            'finding_id': 'f1', 'activity_id': 'A1420', 'activity_name': 'Duct Riser',
            'wbs_path': 'Project > MEP > Level 12 > Zone C', 'total_float_days': 247.0,
            'threshold': 44, 'impact': 5.6, 'severity': 'High', 'status': 'Excessive Float',
            'reason': 'Severely excessive float (5.6× threshold)', 'recommendation': 'Review missing successor logic.',
        }],
        'mgmt': {
            'float_health': 0, 'fh_color': 'red',
            'high': {'pct': 40.3, 'penalty': 60, 'count': 591, 'base': 1400, 'target': 5, 'max_pct': 20, 'max_penalty': 60},
            'neg': {'pct': 0, 'penalty': 0, 'count': 0, 'target': 0, 'max_pct': 5, 'max_penalty': 40},
            'stats': {'total': 1466, 'critical': 100, 'critical_pct': 6.8,
                      'near_critical': 50, 'near_critical_pct': 3.4, 'near_band': 10},
            'indicators': {'threshold': 44, 'constr_total': 1400, 'constr_over': 591, 'constr_over_pct': 40.3,
                           'top_wbs': 'Civil > External', 'top_wbs_pct': 85.7,
                           'highest_float': 247.0, 'highest_float_wbs': 'MEP > Level 12 > Zone C'},
            'wbs': [{'wbs': 'Project > Civil > External', 'short': 'Civil > External', 'activities': 7,
                     'avg_float': 64.3, 'max_float': 247.0, 'over_44': 6, 'pct': 85.7, 'is_construction': True}],
            'conclusion': 'Float concentrates in the Civil construction work packages.',
        },
    }


META = {'project_name': 'Grain Bulk Terminal', 'data_date': '11-Dec-2025',
        'source_file': 'gbt.xer', 'report_date': '01-Aug-2026'}


def test_short_wbs_keeps_last_three():
    assert short_wbs('A > B > C > D > E') == 'C > D > E'
    assert short_wbs('Only > Two') == 'Only > Two'


def test_dangling_report_has_sections_and_no_float_content():
    html = render_module_report(_dangling(), META)
    assert 'Dangling Activities' in html
    assert 'Excellent' in html and '94' in html
    assert 'A240' in html and 'Dangling Start' in html
    assert 'Add an FS predecessor.' in html      # suggested fix rendered
    assert 'Summary Statistics' in html          # Output 2
    assert '<th>Suggested Logic Fix</th>' in html
    assert '<th>Suggested Logic Fix 2</th>' in html  # alternative-types column
    assert '<th>Recommendation</th>' not in html  # Recommendation column removed from Dangling
    assert 'Dangling Start + Dangling Finish' in html  # relabelled KPI tile
    assert 'Task-Dependent' in html                    # scope note
    # isolation: no float wording
    assert 'Float Analysis' not in html
    # repeated header support
    assert 'table-header-group' in html


def test_float_module_report_uses_management_dashboard():
    # V2 redesign: render_module_report delegates float to the management dashboard.
    html = render_module_report(_float(), META)
    assert 'Float Analysis' in html
    # new management layout
    assert 'Float Health' in html
    assert 'Float Distribution by WBS' in html
    assert 'Executive Conclusion' in html
    assert '247' in html                    # highest float surfaced
    # old technical layout is gone
    assert 'WBS Summary' not in html
    assert 'Detailed Findings' not in html
    assert 'Excessive Float' not in html    # per-activity status column removed
    assert 'Dangling' not in html           # isolation


def test_excel_columns_dangling():
    headers, rows = excel_columns(_dangling())
    assert headers[0] == '#'
    assert 'Suggested Logic Fix' in headers
    assert rows[0][0] == 1          # row number
    assert 'A240' in rows[0]


def test_excel_columns_float_has_impact():
    headers, rows = excel_columns(_float())
    assert 'Impact' in headers
    assert any('5.6' in str(c) for c in rows[0])
