"""The redesigned Float Analysis PDF (management dashboard).

Renders from the module result's `mgmt` block; the detailed activity table and
the score/grade badge are gone.
"""
from p6_audit.float_report import render_float_report

META = {'project_name': 'Alstom', 'data_date': '12-Oct-2025',
        'report_date': '07-Aug-2026', 'source_file': 'x.xml'}


def _m():
    return {
        'module': 'float', 'name': 'Float Analysis',
        'mgmt': {
            'float_health': 30, 'fh_color': 'red',
            'high': {'pct': 21.6, 'penalty': 60, 'count': 412, 'base': 1910, 'target': 5, 'max_pct': 20},
            'neg': {'pct': 1.2, 'penalty': 10, 'count': 30, 'target': 0, 'max_pct': 5},
            'stats': {'total': 2502, 'critical': 187, 'critical_pct': 7.5,
                      'near_critical': 143, 'near_critical_pct': 5.7, 'near_band': 10},
            'indicators': {'threshold': 44, 'constr_total': 1910, 'constr_over': 412,
                           'constr_over_pct': 21.6, 'top_wbs': 'Steel Structure > Structural Steel',
                           'top_wbs_pct': 55.0, 'highest_float': 210.0,
                           'highest_float_wbs': 'Steel Structure > Structural Steel'},
            'wbs': [
                {'wbs': 'Steel Structure > Structural Steel', 'short': 'Steel Structure > Structural Steel',
                 'activities': 240, 'avg_float': 88.0, 'max_float': 210.0, 'over_44': 132,
                 'pct': 55.0, 'is_construction': True},
                {'wbs': 'Root > Procurement > Long Lead', 'short': 'Procurement > Long Lead',
                 'activities': 95, 'avg_float': 120.0, 'max_float': 260.0, 'over_44': 60,
                 'pct': 63.2, 'is_construction': False},
            ],
            'conclusion': 'Activities with total float greater than 44 working days are '
                          'concentrated mainly in the Structural Steel construction package.',
        },
    }


def test_renders_all_management_sections():
    h = render_float_report(_m(), META)
    for s in ['Float Health', 'Schedule Statistics', 'Float Indicators',
              'Float Distribution by WBS', 'Executive Conclusion', 'DCMA']:
        assert s in h


def test_shows_score_and_colour_class():
    h = render_float_report(_m(), META)
    assert '30' in h
    assert 'red' in h            # colour drives the gauge, no word-grade


def test_removes_detailed_table_and_grade_badge():
    h = render_float_report(_m(), META)
    assert 'Detailed Findings' not in h
    assert 'grade-badge' not in h
    assert 'Module Score' not in h


def test_highest_float_names_its_wbs():
    h = render_float_report(_m(), META)
    assert 'Structural Steel' in h


def test_wbs_rows_tagged_construction_and_excluded():
    h = render_float_report(_m(), META)
    assert 'Constr' in h         # construction row tag
    assert 'Excl' in h           # excluded (non-construction) row tag


def test_legend_shows_dcma_criteria():
    h = render_float_report(_m(), META)
    assert 'How the Float Health score is calculated' in h
    assert '44' in h and '5%' in h   # threshold + DCMA high-float target


def test_conclusion_text_present():
    h = render_float_report(_m(), META)
    assert 'concentrated mainly' in h


def test_missing_mgmt_shows_reimport_notice_not_zeros():
    # A project imported before this feature has no mgmt — never show a zeroed dashboard.
    h = render_float_report({'module': 'float', 'name': 'Float Analysis'}, META)
    assert isinstance(h, str) and 'Float Analysis' in h
    assert 're-import' in h.lower()
    assert 'Float Health' not in h        # no misleading gauge


def test_empty_float_data_shows_no_data_notice():
    h = render_float_report({'module': 'float', 'name': 'Float Analysis', 'mgmt': {'stats': {'total': 0}}}, META)
    assert 'assessable total float' in h.lower()
    assert 'Float Health' not in h
