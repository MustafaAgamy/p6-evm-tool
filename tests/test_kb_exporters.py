"""Constructability exporters — the PDF HTML and the Excel flattener."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from p6_kb.kb import load_kb
from p6_kb.starter import write_starter_xml
from p6_evm.parser import parse_file
from p6_kb.review import run_review
from p6_kb.exporters import render_html, findings_excel

_BY = {e['type']: e for e in load_kb()}


def _report_with_findings(tmp_path):
    # An MDF starter reviewed against the Oil & Gas standard => plenty of findings.
    xml = tmp_path / 's.xml'
    write_starter_xml(_BY['MDF / Wood Panel Factory'], str(xml))
    return run_review(parse_file(str(xml)), forced_type='Oil & Gas / Petrochemical')


def test_render_html_has_dashboard_and_tables(tmp_path):
    rep = _report_with_findings(tmp_path)
    html = render_html(rep)
    assert html.startswith('<!doctype html>')
    for needle in ('Execution Readiness', 'Constructability Score', 'Issues by WBS phase',
                   'Illogical relationships', 'Missing activities', rep['verdict']['title']):
        assert needle in html, f"missing {needle!r} in PDF html"
    assert 'Priority fixes' not in html  # removed per Ibrahim's request
    # the band legend and score both present
    assert str(rep['score']['overall']) in html


def test_findings_excel_flattens_every_finding(tmp_path):
    rep = _report_with_findings(tmp_path)
    headers, rows = findings_excel(rep)
    assert headers[0] == 'Type' and len(headers) == 8
    expected = len(rep['illogical']) + len(rep['missing']) + len(rep['missing_wbs'])
    assert len(rows) == expected
    assert all(len(r) == len(headers) for r in rows)
    kinds = {r[0] for r in rows}
    assert 'Missing activity' in kinds  # the forced mismatch guarantees missing activities


def test_render_html_clean_when_no_findings(tmp_path):
    # A starter reviewed as itself has no gaps — exporter must still render.
    xml = tmp_path / 'ok.xml'
    write_starter_xml(_BY['Steel Structures'], str(xml))
    rep = run_review(parse_file(str(xml)))
    html = render_html(rep)
    assert 'Ready' in html
    headers, rows = findings_excel(rep)
    assert rows == []
