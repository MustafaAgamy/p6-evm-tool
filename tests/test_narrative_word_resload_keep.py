"""Baseline Narrative Word §13 Resource Loading — the chart group closes on its 'Peak …'
caption; the totals table below is its own block (NARRFIX).

The 13.1 sub-heading, basis note, chart label, chart and 'Peak …' caption were chained to the
totals table (the shared pass read the short Peak caption as the table's lead). Group + table
(~640 pt on SG_BASELINE_XER) did not fit under the §13 intro, so Word pushed all of it and
left page 22 85 % blank (checker: large_blank_then_continuation). The writer now marks the
Peak caption 'keep with next = off' — the shared pass reads an explicit off as "this closes
the block above" — so the group starts under the intro and the table follows or moves alone.

XML tests need python-docx only; the Word proof is skipped without Microsoft Word.
"""
import pytest
from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Pt

from p6_export import docx_pagination as DP
from p6_export import pagination_check as pc
from p6_narrative import docx_template as T
from p6_narrative import docx_writer as W

_P, _TBL = qn('w:p'), qn('w:tbl')
MONTHS = ['Jan-25', 'Feb-25', 'Mar-25', 'Apr-25', 'May-25', 'Jun-25', 'Jul-25', 'Aug-25']
PAYLOAD = {'available': True,
           'intro': 'The manpower and equipment loading read from the baseline resource assignments.',
           'groups': [{'title': 'Manpower',
                       'basis_note': 'Read from the Labour resource assignments.',
                       'total_label': '124,142', 'total_unit': 'man-hours',
                       'window': 'January 2025 – August 2025',
                       'row_headers': ['Resource', 'Total man-hours'],
                       'rows': [['Trade %d' % i, '{:,}'.format(40000 - 3000 * i)] for i in range(11)],
                       'charts': [{'chart_title': 'Manpower — man-hours per month', 'color': '1F4E79',
                                   'span': MONTHS,
                                   'values': [4151, 22487, 20504, 21023, 33727, 8265, 9594, 4390],
                                   'peak_val': 33727, 'peak_label': 'May 2025',
                                   'peak_unit': 'man-hours'}]}]}


def _kn(p):
    ppr = p.find(qn('w:pPr'))
    return ppr.find(qn('w:keepNext')) if ppr is not None else None


def _on(p):
    k = _kn(p)
    return k is not None and k.get(qn('w:val'), 'true') not in ('0', 'false', 'off')


def _doc(fill_pt, old=False):
    """A §13 heading + filler of ``fill_pt`` then the real §13 renderer; ``old`` drops the
    Peak caption's explicit keep-off (the pre-fix writer) before the shared pass."""
    d = Document()
    T.apply_base_styles(d)
    T.apply_page_geometry(d.sections[0])
    T.heading(d, '13)', 'Resource Loading')
    p = d.add_paragraph()
    n = int(fill_pt // 12)
    for i in range(n):
        r = p.add_run('Earlier text of the section, line %d.' % (i + 1))
        if i + 1 < n:
            r.add_break()
    f = p.paragraph_format
    f.line_spacing_rule, f.line_spacing = WD_LINE_SPACING.EXACTLY, Pt(12)
    f.space_before = f.space_after = Pt(0)
    W._render_resload(d, PAYLOAD, 13, None)
    if old:
        for q in d.element.body.iter(_P):
            if ''.join(t.text or '' for t in q.iter(qn('w:t'))).startswith('Peak '):
                q.find(qn('w:pPr')).remove(_kn(q))
        for tbl in d.element.body.iter(_TBL):         # … and the pre-fix table had no title row
            tr = tbl.find(qn('w:tr'))
            if ''.join(t.text or '' for t in tr.iter(qn('w:t'))).endswith('totals by resource'):
                tbl.remove(tr)
    DP.paginate_docx(d)
    return d


def _peak_and_neighbours(d):
    items = [el for el in d.element.body if el.tag in (_P, _TBL)]
    k = next(i for i, el in enumerate(items)
             if el.tag == _P and ''.join(t.text or '' for t in el.iter(qn('w:t'))).startswith('Peak '))
    return items[k - 1], items[k], items[k + 1]


def test_the_peak_caption_closes_the_chart_group():
    chart, peak, table = _peak_and_neighbours(_doc(0))
    assert chart.find('.//' + qn('w:drawing')) is not None and _on(chart)   # chart keeps with Peak
    assert not _on(peak)                                                      # Peak does not chain
    assert table.tag == _TBL                                                  # … to the table


def test_the_shared_pass_still_chains_an_unmarked_short_lead():
    _, peak, _ = _peak_and_neighbours(_doc(0, old=True))
    assert _on(peak)                  # the pre-fix: the pass chained the Peak caption to the table


def test_an_explicit_keep_off_is_not_overridden_by_the_shared_pass():
    d = _doc(0)
    DP.paginate_docx(d)               # idempotent
    _, peak, _ = _peak_and_neighbours(d)
    assert not _on(peak)


@pytest.mark.parametrize('fill_pt', [180, 260])
def test_word_the_chart_group_starts_under_the_intro(tmp_path, fill_pt):
    """Word proof: with ~half a page left under the section's earlier text, the pre-fix chain
    (group + table) is pushed whole and leaves a large blank (flagged); the fixed group
    starts on the same page and the page is not left blank."""
    if not pc.word_available():
        pytest.skip('Microsoft Word (COM) is not available')
    old = str(tmp_path / 'old.docx')
    _doc(fill_pt, old=True).save(old)
    flags, _, _ = pc.analyze_word_layout(pc.word_layout(old))
    assert 'large_blank_then_continuation' in {f['type'] for f in flags}, flags
    new = str(tmp_path / 'new.docx')
    _doc(fill_pt).save(new)
    lay = pc.word_layout(new)
    flags, _, _ = pc.analyze_word_layout(lay)
    assert flags == [], flags
    sub = next(it for it in lay['items'] if (it.get('t') or '').startswith('13.1'))
    assert sub['page'] == 1                                   # the group starts under the intro
