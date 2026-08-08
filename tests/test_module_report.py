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


def _oos():
    return {
        'module': 'out_of_sequence', 'name': 'Out of Sequence',
        'score': 83, 'grade': 'Acceptable', 'pct': 3.4,
        'kpis': {
            'total_activities': 1847, 'oos_count': 63, 'oos_pct': 3.4,
            'critical_oos': 5, 'critical_oos_pct': 0.3,
            'near_critical_oos': 11, 'near_critical_oos_pct': 0.6,
            'near_critical_days': 10, 'affected_wbs': 2, 'data_date': '19-Jul-2026',
            'critical_path_impact': 'Yes', 'completion_date_impact': 'Direct Impact',
            'executive_conclusion': 'Out-of-sequence conditions are concentrated in the Design package.',
        },
        'wbs_summary': [
            {'wbs': 'Design', 'activities': 516, 'oos': 20,
             'pct': 3.9, 'critical_oos': 4, 'near_critical_oos': 5, 'grade': 'Acceptable'},
            {'wbs': 'Construction', 'activities': 823, 'oos': 4,
             'pct': 0.5, 'critical_oos': 1, 'near_critical_oos': 0, 'grade': 'Excellent'},
        ],
        'findings': [{
            'finding_id': 'o1', 'activity_id': 'SS-1420', 'activity_name': 'Erect Steel Columns – Grid C',
            'wbs_path': 'Project > Structural Works > Structural Steel', 'category': 'Construction',
            'current_pred_rel': 'FS', 'current_pred_activity': 'SS-1410 · Fabricate Steel',
            'current_succ_rel': 'FS', 'current_succ_activity': 'SS-1430 · Install Beams',
            'suggested_predecessor': 'SS(2) - SS-1410 · Fabricate Steel', 'suggested_predecessor_kind': 'change',
            'suggested_successor': 'No Change', 'suggested_successor_kind': 'same',
            'root_cause': 'Activity started before predecessor completion.',
            'planning_review_comment': 'Review construction sequence.', 'criticality': 'Critical',
        }],
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


def test_oos_report_has_five_sections_in_order():
    html = render_module_report(_oos(), META)
    assert 'Out of Sequence' in html
    assert 'Acceptable' in html and '83' in html
    order = ['Executive Dashboard', 'Distribution by WBS', 'Out-of-Sequence Review Log',
             'Critical Path Impact Assessment', 'Executive Conclusion']
    positions = [html.find(s) for s in order]
    assert all(p != -1 for p in positions)
    assert positions == sorted(positions)
    # review-log content: split pred/succ rel + activity, single suggested cols, # + cutoff
    assert 'SS-1420' in html and 'SS(2)' in html
    assert '<th>#</th>' in html and '<th>Cutoff Date</th>' in html
    assert '19-Jul-2026' in html
    assert 'Current Pred. Rel.' in html and 'Current Predecessor Activity' in html
    assert 'Current Successor Activity' in html
    assert '<th>Suggested Predecessor</th>' in html and '<th>Suggested Successor</th>' in html
    assert 'Fix 2' not in html                     # Fix 2 columns removed
    assert 'Distribution by WBS Category' in html and 'Design' in html
    assert 'Review construction sequence.' in html
    assert 'DCMA 14-Point Schedule Assessment' in html
    assert 'Direct Impact' in html


def test_oos_review_log_empty_when_clean():
    m = _oos()
    m['findings'] = []
    m['kpis']['oos_count'] = 0
    m['kpis']['executive_conclusion'] = 'No out-of-sequence conditions were detected.'
    html = render_module_report(m, META)
    assert 'schedule progress is consistent' in html
    assert 'No out-of-sequence conditions were detected.' in html


def test_excel_columns_out_of_sequence():
    headers, rows = excel_columns(_oos())
    assert 'Current Pred. Rel.' in headers and 'Current Predecessor Activity' in headers
    assert 'Cutoff Date' in headers
    assert 'Suggested Predecessor' in headers and 'Suggested Successor' in headers
    assert 'Fix 2' not in ' '.join(headers)
    assert 'Root Cause' in headers and 'Criticality' in headers
    assert rows[0][1] == 'SS-1420'
    assert '19-Jul-2026' in rows[0]                # cutoff on the row


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
