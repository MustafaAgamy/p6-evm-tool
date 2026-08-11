"""Manager Report V2 additions: the progress S-curve, the recovery line with a real number,
and the named critical drivers folded into 'where it's coming from'."""
from datetime import datetime

from p6_copilot.context import build_context
from p6_copilot.report import build_scurve, render_scurve_svg, build_manager_report, render_manager_report_html

RESULT = {
    'project_name': 'Grain Bulk Terminal',
    'data_date': '2026-05-18T00:00:00',
    'baseline_finish': '2027-08-15T00:00:00',
    'expected_finish': '2027-11-14T00:00:00',
    'delay_days': 62, 'spi': 0.78,
    'overall_planned_pct': 0.55, 'overall_actual_pct': 0.40,
    'categories': {'Civil': {'weight': 0.6, 'planned_pct': 0.61, 'actual_pct': 0.34},
                   'MEP':   {'weight': 0.4, 'planned_pct': 0.50, 'actual_pct': 0.45}},
}
HISTORY = [
    {'date': '2026-01-10', 'planned': 0.30, 'actual': 0.26},
    {'date': '2026-03-15', 'planned': 0.42, 'actual': 0.33},
    {'date': '2026-05-18', 'planned': 0.55, 'actual': 0.40},
]


def test_build_scurve_scales_and_anchors_to_the_finishes():
    sc = build_scurve(HISTORY, RESULT['baseline_finish'], RESULT['expected_finish'])
    assert sc is not None
    assert sc['planned'][-1][1] == 100.0          # planned reaches 100% at the promised finish
    assert sc['forecast'][-1][1] == 100.0          # forecast reaches 100% at the forecast finish
    assert sc['actual'][0][1] == 26.0              # 0-1 fraction -> 0-100 percent


def test_build_scurve_none_without_history_or_finish():
    assert build_scurve([], RESULT['baseline_finish'], RESULT['expected_finish']) is None
    assert build_scurve(HISTORY, RESULT['baseline_finish'], None) is None


def test_scurve_svg_is_self_contained():
    svg = render_scurve_svg(build_scurve(HISTORY, RESULT['baseline_finish'], RESULT['expected_finish']))
    assert svg.startswith('<svg') and 'polyline' in svg and 'Forecast' in svg and 'http' not in svg.replace('xmlns="http', '')


def test_report_html_includes_chart_recovery_and_drivers():
    ctx = build_context(RESULT)
    ctx['history'] = HISTORY
    ctx['drivers'] = [{'id': 'STEEL', 'name': 'Structural Steel Erection', 'late': 18, 'driving': True},
                      {'id': 'CIVIL', 'name': 'Civil Works', 'late': 12}]
    ctx['recovery'] = {'activity': 'Structural Steel Erection', 'recovered': 10, 'new_finish': datetime(2027, 10, 31)}
    html = render_manager_report_html(build_manager_report(ctx), {})
    assert '<svg' in html and 'Progress —' in html
    assert 'Recovery opportunity' in html and '10 working days' in html
    assert 'Structural Steel Erection' in html and '18 wd late' in html
    assert '31-Oct-2027' in html                   # new finish date, formatted


def test_report_still_renders_cleanly_without_the_new_parts():
    html = render_manager_report_html(build_manager_report(build_context(RESULT)), {})
    assert 'Manager Report' in html
    assert 'Recovery opportunity' not in html and '<svg' not in html   # nothing fabricated when data absent
