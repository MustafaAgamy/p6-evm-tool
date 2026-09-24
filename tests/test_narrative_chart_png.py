"""The Word S-curve chart helper builds a valid SVG and no-ops without Chrome."""
from p6_narrative.chart_png import cashflow_svg, render_svg_png


def test_cashflow_svg_builds_scurve():
    pts = [{'date': f'2026-{(i % 9) + 1:02d}-01', 'pct': i * 10} for i in range(11)]
    svg = cashflow_svg(pts)
    assert svg and svg.startswith('<svg') and 'polyline' in svg and 'S-curve' in svg


def test_cashflow_svg_empty_is_none():
    assert cashflow_svg([]) is None


def test_render_svg_png_without_chrome_returns_none():
    assert render_svg_png('<svg xmlns="http://www.w3.org/2000/svg"/>', 100, 100, chrome=None) is None
