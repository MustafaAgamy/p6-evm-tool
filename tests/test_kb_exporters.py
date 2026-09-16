"""Constructability exporters — the PDF HTML and the Excel flattener."""
import os
import sys
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import report_theme
from p6_kb.kb import load_kb
from p6_kb.starter import write_starter_xml
from p6_evm.parser import parse_file
from p6_kb.review import run_review
from p6_kb.exporters import render_html, findings_excel, findings_excel_sections
from p6_evm.xlsx_writer import write_sections_xlsx

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


def _sheet(sheets, name):
    return next((s for s in sheets if s['name'] == name), None)


def test_findings_excel_sections_mirrors_review_and_writes(tmp_path):
    rep = _report_with_findings(tmp_path)
    sheets = findings_excel_sections(rep)
    names = [s['name'] for s in sheets]

    # neutral headline sheet is always first
    assert names[0] == 'Summary'
    summary = _sheet(sheets, 'Summary')
    titles = [b['title'] for b in summary['blocks']]
    assert 'Review Summary' in titles and 'Findings by Type' in titles

    # reference-first: the /100 score, its band label and the verdict title must NOT leak
    # into the workbook (a plain-English "not a pass/fail score" disclaimer is fine).
    blob = str(sheets)
    assert '/100' not in blob and 'out of 100' not in blob.lower()
    assert 'Constructability Score' not in blob and 'Risk Score' not in blob
    vtitle = (rep.get('verdict') or {}).get('title')
    if vtitle:
        assert vtitle not in blob, f"verdict title leaked: {vtitle!r}"
    band = (rep.get('score') or {}).get('band_label')
    if band:
        assert band not in blob, f"score band leaked: {band!r}"

    # counts-per-type block mirrors the report exactly
    fbt = next(b for b in summary['blocks'] if b['title'] == 'Findings by Type')
    counts = {r[0]: r[1] for r in fbt['rows']}
    assert counts['Illogical relationships'] == len(rep['illogical'])
    assert counts['Missing activities (vs standard)'] == len(rep['missing'])
    assert counts['Missing WBS branches (vs standard)'] == len(rep['missing_wbs'])

    # one clearly-titled sheet per finding type that has data (all three here)
    assert _sheet(sheets, 'Illogical Relationships') and _sheet(sheets, 'Missing Activities') \
        and _sheet(sheets, 'Missing WBS Branches')

    # illogical sheet colours a severity column with the standard vocabulary + a legend
    illo = _sheet(sheets, 'Illogical Relationships')
    blk = illo['blocks'][0]
    sev_col = blk['severity_col']
    sev_values = {row[sev_col] for row in blk['rows']}
    assert sev_values and sev_values <= {'Critical', 'High', 'Medium', 'Low'}
    assert illo['legend'] and {lbl for lbl, _ in illo['legend']} == sev_values
    assert len(blk['rows']) == len(rep['illogical'])

    # writes a valid multi-sheet workbook through the shared writer
    out = tmp_path / 'construct.xlsx'
    write_sections_xlsx(str(out), sheets)
    assert out.exists() and out.stat().st_size > 0
    with zipfile.ZipFile(str(out)) as z:
        assert z.testzip() is None
        assert sum(n.startswith('xl/worksheets/sheet') for n in z.namelist()) == len(sheets)


def test_findings_excel_sections_clean_has_only_summary(tmp_path):
    # A starter reviewed as itself has no gaps — only the neutral headline sheet remains.
    xml = tmp_path / 'ok.xml'
    write_starter_xml(_BY['Steel Structures'], str(xml))
    rep = run_review(parse_file(str(xml)))
    sheets = findings_excel_sections(rep)
    assert [s['name'] for s in sheets] == ['Summary']
    fbt = next(b for b in sheets[0]['blocks'] if b['title'] == 'Findings by Type')
    assert all(r[1] == 0 for r in fbt['rows'])
    out = tmp_path / 'clean.xlsx'
    write_sections_xlsx(str(out), sheets)          # must still write a valid workbook
    with zipfile.ZipFile(str(out)) as z:
        assert z.testzip() is None
    # the flat exporter stays intact alongside the new one
    headers, rows = findings_excel(rep)
    assert headers[0] == 'Type' and rows == []


def test_render_html_clean_when_no_findings(tmp_path):
    # A starter reviewed as itself has no gaps — exporter must still render.
    xml = tmp_path / 'ok.xml'
    write_starter_xml(_BY['Steel Structures'], str(xml))
    rep = run_review(parse_file(str(xml)))
    html = render_html(rep)
    assert 'Ready' in html
    headers, rows = findings_excel(rep)
    assert rows == []


def test_render_html_theme_dark(tmp_path):
    rep = _report_with_findings(tmp_path)
    html = render_html(rep, theme='dark')
    assert 'data-rpt-theme="dark"' in html
    assert report_theme.THEMES['dark']['rpt-accent'] == '#5b9bff'
    assert '#5b9bff' in html


def test_render_html_theme_default_is_light_full_doc(tmp_path):
    rep = _report_with_findings(tmp_path)
    html = render_html(rep)
    assert html.startswith('<!doctype html>')
    assert html.rstrip().endswith('</html>')
    assert 'data-rpt-theme="light"' in html
