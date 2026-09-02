"""Every screen view must print from the menu bar (File ▸ Print / Export to PDF) with
the Printing Selection picker. These assert the wiring that guarantees it:
  - the generic Chrome-PDF route exists,
  - the shared printView helper exists,
  - every screen view is registered in PRINT_VIEW with a print-sections provider.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'ui' / 'app.js').read_text(encoding='utf-8')
SERVER = (ROOT / 'server.py').read_text(encoding='utf-8')


def test_generic_pdf_route_exists():
    assert "'/api/report/html'" in SERVER
    assert 'def _handle_report_html' in SERVER
    assert '--print-to-pdf' in SERVER


def test_shared_printview_helper_exists():
    pv = ROOT / 'ui' / 'modules' / 'printview.js'
    assert pv.exists(), 'printview.js missing'
    text = pv.read_text(encoding='utf-8')
    assert 'export async function printView' in text
    assert 'showReportPreview' in text          # goes through the shared preview + picker
    assert 'api/report/html' in text


def test_every_screen_view_is_registered_for_print():
    assert 'const PRINT_VIEW = {' in APP
    for view in ('overview', 'wbs', 'dash', 'forecast', 'narrative', 'copilot'):
        assert f'{view}:' in APP, f'{view} not registered in PRINT_VIEW'
    # each provider is imported from its module
    for fn in ('overviewPrint', 'wbsPrint', 'dashboardPrint',
               'forecastPrint', 'narrativePrint', 'copilotPrint'):
        assert fn in APP, f'{fn} not imported/used in app.js'


def test_runreport_falls_through_to_printview():
    # File ▸ Print dispatches to printView for views without a per-module report button
    assert 'printView({' in APP
    assert 'PRINT_VIEW[state.currentView]' in APP
