"""Baseline Narrative Word §10 Activity Codes — code tables side by side (finding NARR-WORD-3).

The two code tables of a row were ONE 5-column Word table (title + 'Code Value | Description'
rows repeated). Beside a LONG table that runs onto the next page a SHORT one broke with it:
on the GBT baseline '8 · Procurement SUB WBS' (4 rows) went 3 + 1 across the break next to
the 24-row '7 · Silos Area Name', and '10 · EV - FW Movement' repeated its title + header over
NO rows on the page where '9 · Type of Civil Work' continued. Now an unequal pair whose long
half continues is two tables: the long one breaks like any long table, the short one rides
in a borderless text box on a 1 pt line that keeps with the long one — always beside its
first rows, never split, never repeated. The page checker reads a side-by-side part of a
Word table (empty_repeated_header, table_split_few_rows) so the old layout is flagged.

XML tests need python-docx only; the Word proofs are skipped when Microsoft Word is absent.
"""
import pytest
from docx import Document
from docx.oxml.ns import qn

from p6_export import docx_pagination as DP
from p6_export import pagination_check as pc
from p6_narrative import docx_template as T
from p6_narrative import docx_writer as W

_P, _TBL, _TR, _TC = qn('w:p'), qn('w:tbl'), qn('w:tr'), qn('w:tc')


def _table(dim, n, prefix):
    return {'dimension': dim, 'rows': [{'code': f'{prefix}{i}', 'description': f'{dim} item {i}'}
                                       for i in range(1, n + 1)]}


# a GBT-shaped §10: a long table with a short one beside it (twice), a short one LEFT of a
# long one, a small pair, and two long halves of unequal length
CODES = {'tables': [_table('Silos Area Name', 24, 'S'), _table('Procurement SUB WBS', 4, 'P'),
                    _table('Type of Civil Work', 22, 'C'), _table('EV - FW Movement', 3, 'EV'),
                    _table('EXC - EXC Movement', 1, 'X'), _table('EX.MOV. - Silo Name', 16, 'M'),
                    _table('Main WBS', 10, 'W'), _table('Design Cycle', 3, 'D'),
                    _table('Long A', 30, 'LA'), _table('Long B', 16, 'LB')]}


def _doc(tables=None, filler=0):
    d = Document()
    T.apply_base_styles(d)
    T.apply_page_geometry(d.sections[0])
    for i in range(filler):
        d.add_paragraph(f'Filler line {i + 1} of the page above the activity codes.')
    W._render_codes(d, tables or CODES, 10, None)
    DP.paginate_docx(d)
    W._dedupe_drawing_ids(d)
    return d


def _text(el):
    return ''.join(t.text or '' for t in el.iter(qn('w:t')))


def _kwn(p):
    ppr = p.find(qn('w:pPr'))
    k = ppr.find(qn('w:keepNext')) if ppr is not None else None
    return k is not None and k.get(qn('w:val'), 'true') not in ('0', 'false')


def _row_kwn(tr):
    return all(_kwn(p) for tc in tr.findall(_TC) for p in tc.findall(_P))


def _body(d):
    return [el for el in d.element.body if el.tag in (_P, _TBL)]


def _body_table(d, title):
    return next(el for el in _body(d) if el.tag == _TBL and _text(el).startswith(title))


def _box_before(d, tbl):
    items = _body(d)
    prev = items[items.index(tbl) - 1]
    box = prev.find('.//' + qn('w:txbxContent'))
    return prev, (box.find(_TBL) if box is not None else None)


def _box_x(p):
    return int(p.find('.//' + qn('wp:positionH')).find(qn('wp:posOffset')).text)


# ── the writer ─────────────────────────────────────────────────────────────────
def test_a_short_table_beside_a_long_one_rides_in_a_box_that_keeps_with_it():
    d = _doc()
    for long_title, short_title, n_short in (('1 · Silos Area Name', '2 · Procurement SUB WBS', 4),
                                             ('3 · Type of Civil Work', '4 · EV - FW Movement', 3)):
        lt = _body_table(d, long_title)
        assert short_title not in _text(lt)               # no longer one table for both
        anchor, st = _box_before(d, lt)
        assert st is not None and _text(st).startswith(short_title)
        assert len(st.findall(_TR)) == 2 + n_short        # title, header, every code row
        assert _kwn(anchor)                               # the box's line keeps with the long table
        assert _box_x(anchor) > 0                         # … and sits in the RIGHT half
        rows = lt.findall(_TR)
        # the long table keeps its title, header and as many rows as the short one together …
        assert all(_row_kwn(tr) for tr in rows[:2 + max(n_short, 3) - 1])
        # … repeats both header rows, and never strands its last rows
        assert all(tr.find(qn('w:trPr')).find(qn('w:tblHeader')) is not None for tr in rows[:2])
        assert all(_row_kwn(tr) for tr in rows[-3:-1])
    # no short code table is a body-level table of its own
    assert not any(el.tag == _TBL and _text(el).startswith(('2 · ', '4 · ', '5 · ')) for el in _body(d))


def test_a_short_table_left_of_a_long_one_sits_in_the_left_half():
    d = _doc()
    lt = _body_table(d, '6 · EX.MOV. - Silo Name')
    anchor, st = _box_before(d, lt)
    assert st is not None and _text(st).startswith('5 · EXC - EXC Movement')
    assert _box_x(anchor) <= 0                            # left margin
    jc = lt.find(qn('w:tblPr')).find(qn('w:jc'))
    assert jc is not None and jc.get(qn('w:val')) in ('right', 'end')


def test_small_pairs_stay_one_table_and_two_long_halves_are_stacked():
    d = _doc()
    small = _body_table(d, '7 · Main WBS')
    assert '8 · Design Cycle' in _text(small)            # one 5-column table, kept whole
    assert len(small.findall(_TR)[1].findall(_TC)) == 5
    a, b = _body_table(d, '9 · Long A'), _body_table(d, '10 · Long B')
    assert '10 · Long B' not in _text(a)
    items = _body(d)
    assert items.index(a) < items.index(b)                # reading order kept
    assert d.element.body.find('.//' + qn('w:txbxContent')) is not None
    assert all(el.find('.//' + qn('w:txbxContent')) is None for el in items[items.index(a) - 1:])


def test_equal_halves_stay_one_table():
    d = _doc({'tables': [_table('Left', 20, 'L'), _table('Right', 20, 'R')]})
    t = _body_table(d, '1 · Left')
    assert '2 · Right' in _text(t)
    assert d.element.body.find('.//' + qn('w:txbxContent')) is None


def test_the_box_line_and_its_long_table_are_not_split_by_the_shared_pass():
    """Running the shared Word pass again (idempotent) keeps the box line's keep flag."""
    d = _doc()
    DP.paginate_docx(d)
    anchor, _ = _box_before(d, _body_table(d, '1 · Silos Area Name'))
    assert _kwn(anchor)


# ── the checker reads a side-by-side part of a Word table ───────────────────────
def _row(page, y, cells, hdr=False):
    return {'page': page, 'y': y, 'hdr': hdr, 'n': len(cells), 'bold': hdr, 't': 'x', 'cells': cells}


def _layout(rows):
    return {'page': {'h': 842.0, 'w': 595.0, 'top': 61.0, 'bottom': 48.0}, 'pages': 2,
            'items': [{'k': 'table', 'rows': rows, 'page': rows[0]['page'], 'page_end': rows[-1]['page'],
                       'y': rows[0]['y'], 't': '7 · Silos Area Name |  | 8 · Procurement', 'ncols': 5}]}


def _pair_rows(left, right, first_page_rows):
    """A 5-column pair (title + header rows repeated) whose break falls after
    ``first_page_rows`` body rows."""
    head = [_row(1, 500, [True, False, True], hdr=True), _row(1, 522, [True, True, False, True, True], hdr=True)]
    rows, y, page = list(head), 540, 1
    for i in range(max(left, right)):
        if i == first_page_rows:
            page, y = 2, 97
        rows.append(_row(page, y, [i < left, i < left, False, i < right, i < right]))
        y += 18
    return rows


def test_checker_flags_a_side_part_repeating_its_header_over_no_rows():
    fl, _, _ = pc.analyze_word_layout(_layout(_pair_rows(22, 3, 8)))
    assert [f['type'] for f in fl] == ['empty_repeated_header'] and fl[0]['page'] == 2


def test_checker_flags_a_side_part_split_leaving_one_row():
    fl, _, _ = pc.analyze_word_layout(_layout(_pair_rows(24, 4, 3)))
    assert [f['type'] for f in fl] == ['table_split_few_rows']
    assert 'columns 4-5' in fl[0]['detail'] and 'p2: 1 row' in fl[0]['detail']


def test_checker_leaves_a_wide_table_without_a_gap_column_and_a_balanced_pair_alone():
    wide = [_row(1, 500, [True] * 5, hdr=True)] + [_row(1 if i < 8 else 2, 520 + 18 * i, [True] * 5)
                                                   for i in range(20)]
    assert pc.analyze_word_layout(_layout(wide))[0] == []
    assert pc.analyze_word_layout(_layout(_pair_rows(20, 20, 8)))[0] == []


# ── Word's own pagination ───────────────────────────────────────────────────────
def _need_word():
    if not pc.word_available():
        pytest.skip('Microsoft Word (COM) is not available')


GBT_LIKE = {'tables': CODES['tables'][:4]}


def _old_layout_doc(filler):
    keep = W._code_pair
    W._code_pair = W._code_pair_table                     # the pre-fix: one 5-column table
    try:
        return _doc(GBT_LIKE, filler)
    finally:
        W._code_pair = keep


@pytest.mark.parametrize('filler', [0, 20, 45])
def test_word_one_table_pair_is_flagged_and_the_boxed_layout_is_clean(tmp_path, filler):
    """Word lays both layouts out with the pair at three page positions: the one-table pair
    repeats the short table's header over no rows (flagged); the boxed layout has zero flags
    and the short table's box stands on the page where its long partner starts."""
    _need_word()
    old = str(tmp_path / 'old.docx')
    _old_layout_doc(filler).save(old)
    flags, _, _ = pc.analyze_word_layout(pc.word_layout(old))
    assert {f['type'] for f in flags} & {'empty_repeated_header', 'table_split_few_rows'}, flags
    new = str(tmp_path / 'new.docx')
    _doc(GBT_LIKE, filler).save(new)
    lay = pc.word_layout(new)
    flags, _, _ = pc.analyze_word_layout(lay)
    assert flags == []
    items = lay['items']
    for j, it in enumerate(items[:-1]):
        if (it.get('shape_h') or 0) > 0:                  # a code box's line …
            nxt = items[j + 1]
            assert nxt['k'] == 'table' and nxt['page'] == it['page']      # … beside its partner
            assert it['shape_h'] <= 22 + 18 + 18 * 4 + 8                   # the box is the table's height
