"""Regression tests for the Reporting Studio renderers added with the merge:

* the document renderer (render_html) for the NEW payload kinds a picked
  trend / exec-header / discipline-gap item produces — they must render real
  content (not a blank "no data" section) across appearance modes;
* the dashboard PDF wrapper (dash_render) — it must theme the board by the
  chosen appearance mode so the PDF matches the screen.

These fail if a renderer regresses to no_data or the PDF wrapper drops the mode
or the stylesheet.
"""
import pytest

from p6_special import payloads as P
from p6_special import render_html as R
from p6_special import dash_render


LINE = P.line(
    [{'label': 'SPI', 'tone': 'accent', 'points': [0.95, 0.9, 0.87]},
     {'label': 'CPI', 'tone': 'good', 'points': [1.0, 1.01, 1.02]}],
    x=['w1', 'w2', 'w3'], ref={'value': 1.0, 'label': '1.00 target'}, note='weekly')

STATUS = P.status_header(
    [{'domain': 'EVM', 'tone': 'neutral', 'headline': 'SPI 0.87'},
     {'domain': 'Schedule quality', 'tone': 'warn', 'headline': '72/100'},
     {'domain': 'Buildability', 'tone': 'neutral', 'headline': 'Not run'}],
    verdict=None)

VARIANCE = P.bars(
    rows=[{'label': 'Construction', 'values': [45], 'display': ['45%'],
           'target': 70, 'target_display': '70%', 'tone': 'bad'}],
    series=[{'label': 'Actual', 'tone': 'accent'}], style='variance', note='gap')


@pytest.mark.parametrize('mode', ['light', 'dark', 'blueprint'])
def test_document_renders_new_kinds_not_no_data(mode):
    C = R._Colors(mode)
    for name, pl in (('line', LINE), ('status_header', STATUS), ('variance', VARIANCE)):
        html = R.render_payload(pl, C)
        assert html and '<' in html, f'{name} produced nothing in {mode}'
        assert 'No data available' not in html, f'{name} fell through to no_data in {mode}'


def test_document_line_shows_values_and_reference():
    html = R.render_payload(LINE, R._Colors('light'))
    assert 'SPI' in html and 'CPI' in html
    assert '0.87' in html and '1.02' in html        # the trend values
    assert '1.00 target' in html                    # the reference caption


def test_document_status_header_is_honest_without_verdict():
    html = R.render_payload(STATUS, R._Colors('light'))
    assert 'Status by area' in html                 # no fabricated single verdict
    assert 'Schedule quality' in html and '72/100' in html
    assert 'Not run' in html                         # a not-run domain shown honestly


def test_document_variance_shows_actual_and_plan_target():
    html = R.render_payload(VARIANCE, R._Colors('light'))
    assert 'Construction' in html and '45%' in html
    assert 'plan 70%' in html                        # the planned target is shown alongside


def test_line_with_one_point_is_no_data():
    html = R.render_payload(P.line([{'label': 'x', 'tone': 'accent', 'points': [1]}]), R._Colors('light'))
    assert 'No data available' in html               # a single point is not a trend


@pytest.mark.parametrize('mode', ['light', 'dark', 'midnight', 'sepia', 'contrast', 'blueprint'])
def test_dash_pdf_wrapper_themes_by_mode(mode):
    board = '<div class="studio-dash-wrap"><div class="pd-sheet">BOARD_CONTENT</div></div>'
    html = dash_render.build_dashboard_html(board, mode=mode, title='T')
    assert f'data-appearance="{mode}"' in html        # the mode is applied (screen == PDF)
    assert 'BOARD_CONTENT' in html                     # the client's board is embedded verbatim
    assert '.pd-sheet' in html                         # the app stylesheet (with .pd-* rules) is inlined
    assert 'overflow:visible' in html                  # the SPA overflow:hidden is overridden for print


def test_dash_pdf_wrapper_tolerates_empty_board():
    html = dash_render.build_dashboard_html('', mode='light')
    assert '<body>' in html and 'data-appearance="light"' in html
