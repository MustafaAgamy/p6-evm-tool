"""AI Chat Professional Dashboard → Excel (final sweep, comments 2 / 29).

The dashboard had Download PDF only, while the cost answer tells the planner to "export the
one-pager to Excel".  Download Excel now saves the figures the page is showing: headline and
KPI tiles, SPI / CPI, time status, progress by discipline, the EV vs PV gap by code and the
monthly S-curve values.
"""
import os

import openpyxl

from p6_chat import dashboard_excel
from tests.test_chat_dashboard import data_metrics, dash  # noqa: F401  (fixtures)
from tests.test_server import _post_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _values(path, sheet):
    ws = openpyxl.load_workbook(path)[sheet]
    return [[c for c in r if c not in (None, '')] for r in ws.iter_rows(values_only=True)]


def test_the_workbook_carries_every_part_of_the_dashboard(dash, tmp_path):  # noqa: F811
    from p6_evm.xlsx_writer import write_sections_xlsx
    sh = dashboard_excel.sheets(dash)
    assert [s['name'] for s in sh][:2] == ['Dashboard', 'Progress']
    p = tmp_path / 'd.xlsx'
    write_sections_xlsx(str(p), sh)
    flat = [str(x) for r in _values(p, 'Dashboard') for x in r]
    for k in dash['kpis']:                                    # every KPI tile, with the screen's value
        assert k['k'] in flat and k['v'] in flat
    assert 'Performance indices — 1.00 is on plan' in flat and 'Time status' in flat
    prog = _values(p, 'Progress')
    names = [r[0] for r in prog if r]
    for d in dash['disciplines']:
        assert d['name'] in names
    row = next(r for r in prog if r and r[0] == dash['disciplines'][0]['name'])
    assert row[1] == round(dash['disciplines'][0]['planned'], 1) and row[2] == round(dash['disciplines'][0]['actual'], 1)
    if dash['gap_by_code']['rows']:
        assert 'Total schedule variance (PV − EV)' in names
    if dash['scurve']['months']:
        sc = _values(p, 'S-Curve')
        assert len([r for r in sc if r and r[0] in dash['scurve']['months']]) == len(dash['scurve']['months'])
        assert any('data date' in r for r in sc)


def test_an_empty_dashboard_still_writes_a_headline_and_never_invents():
    sh = dashboard_excel.sheets({'ok': True, 'meta': {'project': 'P'}})
    assert [s['name'] for s in sh] == ['Dashboard']
    assert all(b['rows'] for b in sh[0]['blocks'])


def test_the_route_saves_the_page_payload(test_server, dash, tmp_path):  # noqa: F811
    out = tmp_path / 'dash.xlsx'
    _, d = _post_json(test_server, '/api/chat/dashboard/excel', {'dashboard': dash, 'output_path': str(out)})
    assert d['ok'] is True and out.exists()
    _, d = _post_json(test_server, '/api/chat/dashboard/excel', {'dashboard': {'ok': False}, 'output_path': str(out)})
    assert d['ok'] is False and 'dashboard first' in d['error']


def test_the_dashboard_has_the_excel_button():
    js = open(os.path.join(ROOT, 'ui', 'modules', 'chat.js'), encoding='utf-8').read()
    assert 'data-dxlsx="1"' in js and "'/api/chat/dashboard/excel'" in js
    assert 'downloadDashboardExcel(dash, p)' in js
