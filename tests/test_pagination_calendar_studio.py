"""Owner point 14 — pagination findings CAL-PDF-1, STUDIO-PDF-2, STUDIO-PDF-3, STUDIO-DOC-1.

The page checker must not mistake two things the audit's real reports print on purpose for
page-composition defects, while still flagging the real ones:

* a row of month calendars (Calendar Audit "Each month's calendar", the Studio's
  "Working-day timeline") — every month grid is kept WHOLE, the next row of months starts
  the next page with its own month titles + weekday header: that is a NEW titled grid, not a
  table "continuing" with 1 row (CAL-PDF-1 / STUDIO-PDF-3);
* a KPI card's big value ("0 days" under the label "DELAY") — card content, not a heading
  orphaned at the page bottom (STUDIO-PDF-2).
"""
import pytest

from p6_export import pagination_check as pc

pymupdf = pytest.importorskip('pymupdf')

A4 = (595, 842)


def _pdf(path, pages):
    """pages: op lists — ('t', x, y, text, size, bold) text at baseline y;
    ('r', x0, y0, x1, y1) a filled box; ('b', x0, y0, x1, y1) a card (tinted, outlined)."""
    doc = pymupdf.open()
    for ops in pages:
        pg = doc.new_page(width=A4[0], height=A4[1])
        for op in ops:
            if op[0] == 't':
                _, x, y, text, size, bold = op
                pg.insert_text((x, y), text, fontsize=size, fontname='hebo' if bold else 'helv')
            elif op[0] == 'r':
                pg.draw_rect(pymupdf.Rect(*op[1:]), color=None, fill=(0.85, 0.9, 0.95))
            else:
                pg.draw_rect(pymupdf.Rect(*op[1:]), color=(0.8, 0.84, 0.9), fill=(0.96, 0.97, 0.98))
    doc.save(path)
    doc.close()
    return path


def _running(no, n):
    return [('t', 40, 30, 'PROJECT REPORT  Grain Bulk Terminal', 8, False),
            ('t', 280, 825, f'Page {no} of {n}', 8, False)]


def _para(y0, y1, tag):
    return [('t', 40, y, f'{tag} line {y} of the narrative text of this section, plain words.', 10, False)
            for y in range(int(y0), int(y1), 14)]


MONTHS = ('Dec 2025', 'Jan 2026', 'Feb 2026', 'Mar 2026', 'Apr 2026', 'May 2026')
DAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


def _month_row(y, left, right, weeks=5, first=1):
    """Two month grids side by side (the renderers' .mgrids): each a bold month title, a bold
    weekday header and `weeks` rows of bold day numbers (the calendar cells)."""
    ops = []
    for x0, title in ((40, left), (310, right)):
        ops.append(('t', x0, y, title, 8, True))
        for k, d in enumerate(DAYS):
            ops.append(('t', x0 + 34 * k, y + 14, d, 6, True))
        day = first
        for w in range(weeks):
            for k in range(7):
                ops.append(('t', x0 + 34 * k, y + 32 + 20 * w, str(day), 7, True))
                day += 1
    return ops


def test_next_row_of_whole_month_grids_is_a_new_grid_not_a_split_table(tmp_path):
    n = 3
    pages = [
        _running(1, n) + [('t', 40, 70, 'Each month calendar', 14, True)] + _para(95, 640, 'A')
        + _month_row(660, MONTHS[0], MONTHS[1], weeks=4),            # a whole row of months ends p1
        _running(2, n) + _month_row(60, MONTHS[2], MONTHS[3])         # the next row starts p2
        + _month_row(200, MONTHS[4], MONTHS[5]) + _para(340, 790, 'B'),
        _running(3, n) + [('t', 40, 70, 'Notes', 14, True)] + _para(95, 790, 'C'),
    ]
    res = pc.check_pdf(_pdf(str(tmp_path / 'months.pdf'), pages))
    assert res['flags'] == [], res['flags']


def test_a_month_grid_cut_across_the_break_is_still_flagged(tmp_path):
    """Control: a grid whose weeks run on to the next page (no month title there) is a split."""
    n = 3
    cut = _month_row(700, MONTHS[0], MONTHS[1], weeks=5)
    top = [op for op in cut if op[2] > 780]                       # weeks 4-5 fall off p1 …
    moved = [(o[0], o[1], o[2] - 700, *o[3:]) for o in top]      # … and start p2
    pages = [
        _running(1, n) + [('t', 40, 70, 'Each month calendar', 14, True)] + _para(95, 680, 'A')
        + [op for op in cut if op[2] <= 780],
        _running(2, n) + moved + _para(160, 790, 'B'),
        _running(3, n) + [('t', 40, 70, 'Notes', 14, True)] + _para(95, 790, 'C'),
    ]
    res = pc.check_pdf(_pdf(str(tmp_path / 'cut.pdf'), pages))
    assert ('table_split_few_rows', 1) in {(f['type'], f['page']) for f in res['flags']}, res['flags']


def test_kpi_card_value_is_card_content_not_an_orphaned_heading(tmp_path):
    n = 4
    pages = [
        # p1 ends with a KPI card: small label + big bold value inside one outlined box
        _running(1, n) + [('t', 40, 70, 'Delay in working days', 14, True)] + _para(95, 690, 'A')
        + [('b', 40, 705, 555, 790), ('t', 52, 725, 'DELAY', 8, False), ('t', 52, 770, '0 days', 22, True)],
        _running(2, n) + [('t', 40, 70, 'Planned Value vs Earned Value', 14, True)] + _para(95, 790, 'B'),
        # control: a real heading alone at the bottom of p3 is still an orphan
        _running(3, n) + _para(60, 770, 'C') + [('t', 40, 800, 'Resource summary', 13, True)],
        _running(4, n) + _para(60, 790, 'D'),
    ]
    res = pc.check_pdf(_pdf(str(tmp_path / 'kpi.pdf'), pages))
    assert [(f['type'], f['page']) for f in res['flags']] == [('orphaned_heading', 3)], res['flags']
    assert 'Resource summary' in res['flags'][0]['detail']
