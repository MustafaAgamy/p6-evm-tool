"""Tests for the Reporting Studio native Word (.docx) generator.

Unlike the Office-HTML ``.doc`` wrapper (:mod:`p6_special.word_export`), this exporter
writes a genuine ``.docx`` package via python-docx: a double navy page border on every
page (``w:pgBorders``), a 3-logo header part, a page-number footer, a navy cover, navy
tables, and — importantly — ``bars`` drawn as real proportional bars (not a value
table). These tests hand-build a ``rendered`` selection (as ``registry.render`` returns)
covering table, kpi_group, bars, findings and a reused-feature ``html`` section, write a
``.docx``, then open it back with python-docx / zipfile and assert the structure.
"""
import zipfile

import docx

from p6_special import payloads as P
from p6_special.docx_report import build_docx


def _meta():
    return {'project_name': 'Grain Bulk Terminal', 'data_date': '2026-07-19'}


def _rendered():
    """A small report: a data table, a KPI group, a bars result, a findings register,
    and a REUSED feature-report ``html`` section (its inner ``<td>`` must be
    reconstructed into a real docx table)."""
    return [
        {'id': 'evm:cat', 'title': 'By category', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'table',
         'payload': P.table(['Category', 'Planned %', 'Actual %'],
                            [['Piling', 100, ('95', 'good')],
                             ['Concrete', ('80', 'warn'), 72]])},
        {'id': 'evm:kpi', 'title': 'Key metrics', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'kpi',
         'payload': P.kpi_group([P.kpi('SPI', '0.87', sub='behind plan', tone='warn'),
                                 P.kpi('CPI', '1.02', tone='good')])},
        {'id': 'evm:bars', 'title': 'Planned vs Actual', 'feature': 'evm',
         'feature_title': 'EVM Report', 'ctype': 'chart',
         'payload': P.bars(rows=[{'label': 'Piling', 'values': [100, 95],
                                  'display': ['100%', '95%']},
                                 {'label': 'Concrete', 'values': [80, 72],
                                  'display': ['80%', '72%']}],
                           series=[{'label': 'Planned', 'tone': 'neutral'},
                                   {'label': 'Actual', 'tone': 'good'}],
                           axis_max=100, note='Weighted by BAC')},
        {'id': 'audit:find', 'title': 'Open findings', 'feature': 'audit',
         'feature_title': 'Schedule Audit', 'ctype': 'findings',
         'payload': P.findings([{'severity': 'high', 'title': 'Negative float',
                                 'detail': '12 activities below zero'},
                                {'severity': 'low', 'title': 'Long duration',
                                 'detail': '3 activities over 60d'}])},
        {'id': 'audit:reuse', 'title': 'Detailed section', 'feature': 'audit',
         'feature_title': 'Schedule Audit', 'ctype': 'html',
         'payload': {'kind': 'html',
                     'css': '.x{color:red}',
                     'html': '<div><h3>Cat</h3>'
                             '<table><tr><th>A</th></tr><tr><td>1</td></tr></table></div>'}},
    ]


def _letterhead():
    return {'kicker': 'Project Progress Report', 'company': 'Acme Marine JV',
            'prepared_by': 'Planning Dept',
            'logos': {'owner': None, 'consultant': None, 'contractor': None}}


def _all_table_cell_texts(document):
    out = []
    for t in document.tables:
        for row in t.rows:
            for cell in row.cells:
                out.append(cell.text)
                # nested tables inside a cell, if any
                for nt in cell.tables:
                    for r in nt.rows:
                        for c in r.cells:
                            out.append(c.text)
    return out


def _all_paragraph_texts(document):
    return [p.text for p in document.paragraphs]


def test_build_docx_writes_valid_docx(tmp_path):
    out = tmp_path / 'out.docx'
    ret = build_docx(out, 'Weekly', _meta(), _rendered(), letterhead=_letterhead())

    # written + a real zip (docx is a zip package)
    assert out.exists()
    assert str(ret) == str(out)
    assert zipfile.is_zipfile(out)

    document = docx.Document(str(out))
    paras = _all_paragraph_texts(document)
    cell_texts = _all_table_cell_texts(document)

    # cover carries the report name
    assert any('Weekly' in p for p in paras)
    # a Contents heading is present
    assert any(p.strip() == 'Contents' for p in paras)
    # the numbered section headings (pick order)
    assert any(p.strip() == '1 By category' for p in paras)
    assert any(p.strip() == '3 Planned vs Actual' for p in paras)
    assert any(p.strip() == '5 Detailed section' for p in paras)

    # >= 1 real table with the expected header cell(s)
    assert 'Category' in cell_texts and 'Planned %' in cell_texts
    assert 'Metric' in cell_texts and 'Value' in cell_texts     # kpi_group table
    assert 'Severity' in cell_texts and 'Finding' in cell_texts  # findings table
    # findings severity values are title-cased
    assert 'High' in cell_texts and 'Low' in cell_texts

    # the html section's inner <td> '1' appears in a reconstructed table
    assert '1' in cell_texts
    # and its <h3> became a subheading paragraph
    assert any(p.strip() == 'Cat' for p in paras)


def test_docx_has_navy_page_border_and_header_part(tmp_path):
    out = tmp_path / 'framed.docx'
    build_docx(out, 'Weekly', _meta(), _rendered(), letterhead=_letterhead())

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        # a page border is declared on the section
        document_xml = z.read('word/document.xml').decode('utf-8')
        assert 'w:pgBorders' in document_xml
        # navy frame colour
        assert '1F4E79' in document_xml.upper()
        # a header part exists (the 3-logo running header)
        assert 'word/header1.xml' in names
        # a footer part exists (the page-number footer)
        assert any(n.startswith('word/footer') for n in names)
        # a live PAGE field in the footer
        footer = next(n for n in names if n.startswith('word/footer'))
        assert 'PAGE' in z.read(footer).decode('utf-8')


def test_bars_drawn_as_shaded_bars_not_a_table(tmp_path):
    """A bars payload draws proportional shaded cells (a series colour + a grey track),
    NOT a numeric value table — so the document XML carries the fill colours."""
    out = tmp_path / 'bars.docx'
    build_docx(out, 'Weekly', _meta(),
               [{'id': 'b', 'title': 'Bars only', 'feature': 'f', 'feature_title': 'Feat',
                 'ctype': 'chart',
                 'payload': P.bars(rows=[{'label': 'A', 'values': [100, 50]}],
                                   series=[{'label': 'Planned', 'tone': 'neutral'},
                                           {'label': 'Actual', 'tone': 'good'}],
                                   axis_max=100)}],
               letterhead=_letterhead())

    with zipfile.ZipFile(out) as z:
        document_xml = z.read('word/document.xml').decode('utf-8').upper()
    # the navy first-series fill, the green second-series fill and the grey track
    assert '1F4E79' in document_xml            # navy (series 0 + chrome)
    assert '2E7D32' in document_xml            # green (series 1)
    assert 'E9EDF2' in document_xml            # grey bar track


def test_build_docx_empty_selection_still_valid(tmp_path):
    out = tmp_path / 'empty.docx'
    build_docx(out, 'Weekly', _meta(), [], letterhead=_letterhead())
    assert out.exists()
    assert zipfile.is_zipfile(out)
    document = docx.Document(str(out))
    paras = _all_paragraph_texts(document)
    assert any('Weekly' in p for p in paras)                 # cover still written
    assert any(p.strip() == 'Contents' for p in paras)


def test_build_docx_never_raises_on_malformed_items(tmp_path):
    """A None payload, an unknown kind and a no_data item are skipped, never fatal."""
    rendered = [
        {'id': 'ok', 'title': 'Good table', 'feature': 'f', 'feature_title': 'Feat',
         'ctype': 'table', 'payload': P.table(['A', 'B'], [['x', 'y']])},
        {'id': 'none', 'title': 'Broken', 'feature': 'f', 'feature_title': 'Feat',
         'ctype': 'text', 'payload': None},
        {'id': 'weird', 'title': 'Mystery', 'feature': 'f', 'feature_title': 'Feat',
         'ctype': 'text', 'payload': {'kind': 'zzz'}},
        {'id': 'nd', 'title': 'Nothing', 'feature': 'f', 'feature_title': 'Feat',
         'ctype': 'text', 'payload': P.NO_DATA},
    ]
    out = tmp_path / 'malformed.docx'
    build_docx(out, 'Weekly', _meta(), rendered, letterhead=_letterhead())
    assert zipfile.is_zipfile(out)
    document = docx.Document(str(out))
    paras = _all_paragraph_texts(document)
    # every picked item still gets its numbered heading (even the empty ones)
    for n, title in ((1, 'Good table'), (2, 'Broken'), (3, 'Mystery'), (4, 'Nothing')):
        assert any(p.strip() == ('%d %s' % (n, title)) for p in paras)


def test_group_and_segbar_and_line_and_status(tmp_path):
    """A group recurses its blocks; segbar/line/status_header each render without error."""
    rendered = [
        {'id': 'g', 'title': 'Grouped', 'feature': 'f', 'feature_title': 'Feat',
         'ctype': 'group',
         'payload': P.group([P.keyvals([('Data date', '2026-07-19')]),
                             P.segbar([{'label': 'Steel', 'value': 60, 'tone': 'accent'},
                                       {'label': 'Concrete', 'value': 40, 'tone': 'good'}])])},
        {'id': 'l', 'title': 'SPI trend', 'feature': 'f', 'feature_title': 'Feat',
         'ctype': 'chart',
         'payload': P.line([{'label': 'SPI', 'tone': 'accent', 'points': [0.9, 0.92, 0.87]}],
                           x=['W1', 'W2', 'W3'], ref={'value': 1.0, 'label': 'target'})},
        {'id': 's', 'title': 'Status', 'feature': 'f', 'feature_title': 'Feat',
         'ctype': 'summary',
         'payload': P.status_header([{'domain': 'Schedule', 'tone': 'warn',
                                      'headline': 'Slipping'}])},
    ]
    out = tmp_path / 'mixed.docx'
    build_docx(out, 'Weekly', _meta(), rendered, letterhead=_letterhead())
    assert zipfile.is_zipfile(out)
    document = docx.Document(str(out))
    cell_texts = _all_table_cell_texts(document)
    # keyvals from inside the group
    assert 'Data date' in cell_texts
    # line trend point table + status header table
    assert 'Point' in cell_texts and 'SPI' in cell_texts
    assert 'Area' in cell_texts and 'Schedule' in cell_texts
