from datetime import datetime
from p6_evm.evm_report import render_evm_report, spi_status


def _result():
    return {
        'pv': 412.6e6, 'ev': 388.9e6, 'ac': 388.9e6,
        'spi': 0.94, 'cpi': 1.11, 'delay_days': 18,
        'overall_planned_pct': 0.362, 'overall_actual_pct': 0.341,
        'data_date': datetime(2025, 12, 11),
        'categories': {
            'Construction': {'weight': 0.95, 'planned_pct': 0.345, 'actual_pct': 0.324},
            'Design — Phase I': {'weight': 0.015, 'planned_pct': 0.80, 'actual_pct': 0.72},
        },
    }


META = {'project_name': 'GBT', 'data_date': '11-Dec-2025', 'report_date': '04-Aug-2026',
        'source_file': 'gbt.xer', 'baseline_finish': datetime(2027, 2, 28),
        'expected_finish': datetime(2027, 3, 18), 'actual_cost': 350e6}


def test_spi_status_bands():
    assert spi_status(1.02)[0].startswith('Ahead')
    assert spi_status(0.97)[0] == 'Slightly Behind'
    assert spi_status(0.80)[0] == 'Behind Schedule'


def test_report_has_dashboard_as_percentages_and_no_actual_cost_in_bar():
    html = render_evm_report(_result(), META)
    assert 'EVM Results' in html
    assert '94%' in html          # SPI as %
    assert '111%' in html         # CPI as %
    assert 'Behind Schedule' in html
    # PV-vs-EV bar present, Actual Cost NOT a bar row
    assert 'Planned Value (PV)' in html and 'Earned Value (EV)' in html
    assert 'Actual Cost (AC)' not in html
    # editable AC reflected (entered value 350M)
    assert '350.0M' in html
    # baseline / expected finish + delay
    assert '28-Feb-27' in html and '18-Mar-27' in html and '18 days' in html


def test_report_category_planned_weight_columns():
    html = render_evm_report(_result(), META)
    assert 'Planned Weight %' in html and 'Weighted Actual %' in html


def test_engineering_section_and_order():
    eng = {'mode': 'E1', 'rows': [
        {'trade': 'Civil', 'submittal_type': 'Shop Drawing', 'req': 45, 'planned': 45,
         'submitted_rows': 56, 'approved_rows': 43, 'not_approved_rows': 13,
         'under_review_rows': 0, 'planned_pct': 100.0, 'submitted_pct': 95.6, 'approved_pct': 95.6}],
        'gap': [{'trade': 'Mechanical', 'planned_appr': 27, 'actual_appr': 20, 'gap': 7, 'pct_of_gap': 37}]}
    gap = {'dimension': 'Type of Works', 'total_gap': 1e6,
           'groups': [{'code': 'Piles Works', 'pv': 4e6, 'ev': 3e6, 'gap': 1e6, 'pct_of_gap': 100}]}
    html = render_evm_report(_result(), META, gap=gap, engineering=eng)
    assert 'Engineering Progress — Drawings by Trade' in html
    assert 'Engineering Gap Analysis' in html
    assert 'Shop Drawing' in html and '95.6%' in html
    # order: engineering appears before the PV-EV gap section
    assert html.index('Engineering Progress') < html.index('PV vs EV Gap Analysis')


def test_report_gap_section_optional():
    gap = {'dimension': 'Type of Works', 'total_gap': 23.7e6,
           'groups': [{'code': 'Piles Works', 'pv': 42e6, 'ev': 30.1e6, 'gap': 11.9e6, 'pct_of_gap': 50.2}]}
    html = render_evm_report(_result(), META, gap=gap)
    assert 'PV vs EV Gap Analysis' in html
    assert 'Piles Works' in html
    # without gap → no section
    assert 'PV vs EV Gap Analysis' not in render_evm_report(_result(), META)
