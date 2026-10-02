"""The Manager's briefing carries the AI Chat answer charts (comment 33, the part left open:
"charts are not yet in the Manager's briefing export").

The screen draws the answer charts from p6_chat/merged/_charts.py with the app's colour tokens;
the briefing (and the PDF printed from it) now carries the same charts as print-safe HTML:
progress by discipline, then the milestones running late (or the client items overdue).
"""
from p6_chat import copilot
from p6_chat.merged import _charts as QC

from tests.test_chat_copilot import snap  # noqa: F401  (fixture)


def test_chart_html_draws_each_kind_with_its_rows():
    bars = {'type': 'bars', 'title': 'Progress by discipline', 'legend': 'solid = done · light = planned (%)',
            'items': [{'name': 'Marine & Jetty', 'planned': 70, 'actual': 45}]}
    h = QC.chart_html(bars)
    assert 'Progress by discipline' in h and 'Marine &amp; Jetty' in h
    assert 'width:70.0%' in h and 'width:45.0%' in h and '45% <small>of 70%</small>' in h
    hb = QC.chart_html({'type': 'hbar', 'title': 'Milestones — working days late', 'unit': 'wd',
                        'items': [{'name': 'Handover (M100)', 'value': 20, 'label': '20 wd', 'tone': 'bad'},
                                  {'name': 'Jetty ready (M050)', 'value': 5, 'label': '5 wd', 'tone': 'warn'}]})
    assert 'width:100.0%' in hb and 'width:25.0%' in hb and '#dc2626' in hb and '20 wd' in hb
    pairs = QC.chart_html({'type': 'pairs', 'title': 'Value', 'legend': ['planned', 'done'], 'unit': 'M',
                           'items': [{'name': 'Civil', 'a': 10, 'b': 5, 'la': '10M', 'lb': '5M'}]})
    assert 'upper bar = planned · lower bar = done · in M' in pairs and 'width:50.0%' in pairs
    kpi = QC.chart_html({'type': 'kpi', 'title': 'Where', 'items': [{'label': 'SPI', 'value': '0.60', 'tone': 'bad'}]})
    assert 'SPI' in kpi and '0.60' in kpi
    assert QC.chart_html({'type': 'bars', 'items': []}) == '' and QC.chart_html({'type': 'x', 'items': [{}]}) == ''


def test_the_briefing_shows_progress_by_discipline(snap):  # noqa: F811
    out = copilot.manager_report(snap, xml_path=None, preview=True)
    assert out['ok'] is True
    kinds = [c['type'] for c in out['report']['charts']]
    assert kinds and kinds[0] == 'bars'
    html = out['html']
    assert 'data-chart="bars"' in html and 'Marine &amp; Jetty Works' in html
    assert '.qc{' in html                                   # its print styles travel with it
    assert html.index('data-chart="bars"') < html.index('Every figure is from your P6 update')


def test_a_briefing_without_facts_has_no_charts():
    assert QC.for_briefing({'ok': False}, {'ok': False}) == []
