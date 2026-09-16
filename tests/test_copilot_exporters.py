"""p6_evm.copilot_exporters.copilot_excel — the AI Copilot · TIA Excel mirror.

The exporter turns the copilot report dict (build_copilot's output: tia + insights)
into the `sheets` structure for write_sections_xlsx, mirroring the screen's two
deterministic sections. These tests assert the produced .xlsx is a valid zip with
the expected sheet and that every on-screen section + its data lands in it, and
that empty/missing data degrades to a "No data" row without crashing.
"""
import zipfile
import xml.etree.ElementTree as ET

from p6_evm.copilot import build_copilot
from p6_evm.copilot_exporters import (copilot_excel, _fdate,
                                      _FORECAST_HEADERS, _DRIVER_HEADERS, _INSIGHT_HEADERS)
from p6_evm.xlsx_writer import write_sections_xlsx


def _result(**kw):
    """A representative computed result — behind schedule, over the baseline finish,
    with a lagging category — so the TIA and insights are all populated."""
    base = {'project_name': 'Harbor Expansion', 'data_date': '2026-08-31',
            'expected_finish': '2027-08-31', 'baseline_finish': '2027-06-30',
            'spi': 0.66, 'cpi': 0.92,
            'categories': {'Engineering': {'planned_pct': 0.38, 'actual_pct': 0.61},
                           'Construction': {'planned_pct': 0.55, 'actual_pct': 0.30}}}
    base.update(kw)
    return base


def _write(report, tmp_path):
    sheets = copilot_excel(report)
    out = tmp_path / 'copilot.xlsx'
    write_sections_xlsx(str(out), sheets)
    return out, sheets


def _sheet1_xml(path):
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        assert '[Content_Types].xml' in names
        assert 'xl/workbook.xml' in names
        assert 'xl/worksheets/sheet1.xml' in names
        wb = z.read('xl/workbook.xml').decode('utf-8')
        xml = z.read('xl/worksheets/sheet1.xml').decode('utf-8')
    ET.fromstring(xml)                                   # sheet parses as valid XML
    return wb, xml


def test_valid_xlsx_with_one_named_sheet(tmp_path):
    report = build_copilot(_result(), weather={'weather_adjusted_finish': '2027-10-20'})
    out, sheets = _write(report, tmp_path)
    assert out.exists()
    assert len(sheets) == 1
    wb, _ = _sheet1_xml(out)
    assert 'AI Copilot' in wb                             # the sheet is named after the feature


def test_mirrors_every_on_screen_section(tmp_path):
    report = build_copilot(_result(), weather={'weather_adjusted_finish': '2027-10-20'})
    out, _ = _write(report, tmp_path)
    _, xml = _sheet1_xml(out)
    for title in ['Time-Impact Analysis', "What's driving the slip", 'Copilot insights']:
        assert title in xml, title
    for header in _FORECAST_HEADERS + _DRIVER_HEADERS + _INSIGHT_HEADERS:
        assert header in xml, header


def test_carries_forecast_dates_components_and_insights(tmp_path):
    report = build_copilot(_result(), weather={'weather_adjusted_finish': '2027-10-20'})
    tia = report['tia']
    out, _ = _write(report, tmp_path)
    _, xml = _sheet1_xml(out)
    # the finish-forecast summary shows the (formatted) baseline finish
    assert _fdate(tia['baseline_finish']) in xml
    # the TIA decomposition names its components and keeps the slip days numeric
    labels = {c['label'] for c in tia['components']}
    assert 'Slippage to date' in labels
    for lab in labels:
        assert lab in xml
    to_date_days = next(c['days'] for c in tia['components'] if c['key'] == 'to_date')
    assert f'<v>{to_date_days}</v>' in xml               # numeric cell, not a string
    # a high-severity insight (SPI 0.66 → significantly behind) is present with its label
    assert 'Significantly behind schedule' in xml and 'High' in xml


def test_no_weather_component_when_none(tmp_path):
    report = build_copilot(_result())                    # no weather passed
    out, _ = _write(report, tmp_path)
    _, xml = _sheet1_xml(out)
    assert 'Slippage to date' in xml                     # to-date component still there
    assert 'Weather' not in [c['label'] for c in report['tia']['components']]


def test_empty_report_degrades_to_no_data_row(tmp_path):
    report = build_copilot({})                            # no metrics at all
    out, _ = _write(report, tmp_path)
    assert out.exists()
    _, xml = _sheet1_xml(out)
    assert 'No finish forecast' in xml                    # driver table "No data" row
    # all three section titles still render even with no data
    for title in ['Time-Impact Analysis', "What's driving the slip", 'Copilot insights']:
        assert title in xml, title


def test_none_report_does_not_crash(tmp_path):
    out, sheets = _write(None, tmp_path)                  # exporter tolerates None
    assert out.exists() and len(sheets) == 1
