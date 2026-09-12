"""Tests for the Reporting Studio Excel (.xlsx) export.

``build_excel`` mirrors the Document / Dashboard as DATA: a leading Contents sheet
listing the picked sections in order, then one sheet per result holding that result's
numbers (table rows, KPI values, bar series, findings, ...). A reused feature-report
section (kind 'html') becomes an honest one-row "see the PDF/Word report" sheet — we
never parse the opaque feature markup back into a table.

The workbook is written by the shared pure-Python OOXML writer (no openpyxl), so the
assertions here just open it as a zip and read the raw part XML.
"""
import re
import zipfile

from p6_special import payloads as P
from p6_special.excel_export import build_excel


def _rendered():
    """A fake selection shaped like ``registry.render`` output — covers a payload
    ``table`` (with a coloured ``[text, tone]`` cell), a ``kpi_group``, ``bars``,
    ``findings`` and a reused feature ``html`` section, plus a ``no_data`` result and
    an unknown-kind result (both should be listed in Contents but emit no sheet)."""
    return [
        {'id': 'evm:cat', 'title': 'EVM Table', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'table',
         'payload': P.table(['Category', 'Planned %', 'Actual %'],
                            [['Piling', 100, ('95', 'good')],
                             ['Concrete', ('80', 'warn'), 72]])},
        {'id': 'evm:kpi', 'title': 'Key Metrics', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'kpi',
         'payload': P.kpi_group([P.kpi('SPI', '0.87', sub='behind plan', tone='warn'),
                                 P.kpi('CPI', '1.02', tone='good')])},
        {'id': 'evm:bars', 'title': 'Planned vs Actual', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'chart',
         'payload': P.bars(rows=[{'label': 'Piling', 'values': [100, 95]},
                                 {'label': 'Concrete', 'values': [80, 72]}],
                           series=[{'label': 'Planned', 'tone': 'neutral'},
                                   {'label': 'Actual', 'tone': 'good'}])},
        {'id': 'audit:find', 'title': 'Open Findings', 'feature': 'audit',
         'feature_title': 'Schedule Audit', 'ctype': 'findings',
         'payload': P.findings([{'severity': 'high', 'title': 'Negative float',
                                 'detail': '12 activities below zero'}])},
        {'id': 'audit:reuse', 'title': 'Detailed Section', 'feature': 'audit',
         'feature_title': 'Schedule Audit', 'ctype': 'html',
         'payload': {'kind': 'html', 'html': '<div>opaque report markup</div>',
                     'css': '.x{color:red}'}},
        {'id': 'x:empty', 'title': 'Empty Result', 'feature': 'x',
         'feature_title': 'Nothing', 'ctype': 'text', 'payload': P.NO_DATA},
        {'id': 'x:weird', 'title': 'Mystery', 'feature': 'x',
         'feature_title': 'Nothing', 'ctype': 'text', 'payload': {'kind': 'zzz'}},
    ]


def _sheet_names(z):
    """Sheet names in workbook order (also the sheet1..N.xml order)."""
    xml = z.read('xl/workbook.xml').decode('utf-8')
    return re.findall(r'<sheet name="([^"]+)"', xml)


def _sheet_xml(z, name):
    """Raw worksheet XML for a sheet by name (workbook order == sheetN.xml order)."""
    idx = _sheet_names(z).index(name)
    return z.read(f'xl/worksheets/sheet{idx + 1}.xml').decode('utf-8')


def test_build_excel_writes_valid_workbook(tmp_path):
    out = tmp_path / 'out.xlsx'
    rendered = _rendered()
    build_excel(out, 'Weekly', {'project_name': 'Grain', 'data_date': '2026-07-19'}, rendered)

    assert out.exists()
    assert zipfile.is_zipfile(out)

    with zipfile.ZipFile(out) as z:
        names_in_zip = z.namelist()
        assert 'xl/workbook.xml' in names_in_zip
        names = _sheet_names(z)

        # Contents + one sheet per data-bearing result (no_data / unknown skipped).
        assert names[0] == 'Contents'
        for title in ('EVM Table', 'Key Metrics', 'Planned vs Actual',
                      'Open Findings', 'Detailed Section'):
            assert title in names
        assert 'Empty Result' not in names        # no_data -> no sheet
        assert 'Mystery' not in names             # unknown kind -> no sheet
        assert len(names) == 6                     # Contents + 5

        # Contents still lists every picked section, including the skipped ones.
        contents = _sheet_xml(z, 'Contents')
        assert 'Grain' in contents
        for title in ('EVM Table', 'Key Metrics', 'Empty Result', 'Mystery'):
            assert title in contents

        # Data values land in the right sheets.
        assert '0.87' in _sheet_xml(z, 'Key Metrics')          # a KPI value
        assert 'Piling' in _sheet_xml(z, 'EVM Table')          # a table category
        assert '95' in _sheet_xml(z, 'EVM Table')              # the unwrapped [text,tone] cell
        assert 'Piling' in _sheet_xml(z, 'Planned vs Actual')  # a bar row label
        assert 'Negative float' in _sheet_xml(z, 'Open Findings')
        assert 'see the PDF / Word report' in _sheet_xml(z, 'Detailed Section')


def test_build_excel_empty_selection(tmp_path):
    """With no results it still writes a valid workbook — just the Contents sheet."""
    out = tmp_path / 'empty.xlsx'
    build_excel(out, 'Weekly', {'project_name': 'Grain', 'data_date': '2026-07-19'}, [])

    assert out.exists()
    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out) as z:
        assert 'xl/workbook.xml' in z.namelist()
        assert _sheet_names(z) == ['Contents']


def test_build_excel_group_and_malformed(tmp_path):
    """A ``group`` stacks its blocks onto one sheet; a malformed item never crashes."""
    rendered = [
        {'id': 'g', 'title': 'Grouped', 'feature': 'f', 'feature_title': 'Feature',
         'ctype': 'group',
         'payload': P.group([P.keyvals([('Data date', '2026-07-19')]),
                             P.table(['A', 'B'], [['alpha', 1], ['beta', 2]])])},
        {'id': 'bad', 'title': 'Broken', 'feature': 'f', 'feature_title': 'Feature',
         'ctype': 'text', 'payload': None},          # malformed -> skipped, no crash
    ]
    out = tmp_path / 'group.xlsx'
    build_excel(out, 'Weekly', {}, rendered)

    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out) as z:
        names = _sheet_names(z)
        assert names == ['Contents', 'Grouped']       # 'Broken' skipped
        grouped = _sheet_xml(z, 'Grouped')
        assert 'alpha' in grouped and 'beta' in grouped
