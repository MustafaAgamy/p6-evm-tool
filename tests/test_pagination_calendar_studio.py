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


# ── PROOF with Chrome: the REAL Calendar Audit renderer's month calendars ────────────────
import calendar as _cal
import datetime as _dt
import os
import re
import tempfile


def _calendar_result(n=24):
    months = []
    for i in range(n):
        yy, mm = 2026 + i // 12, i % 12 + 1
        first, nd = _dt.date(yy, mm, 1), _cal.monthrange(yy, mm)[1]
        days = []
        for d in range(1, nd + 1):
            st = 'weekend' if _dt.date(yy, mm, d).weekday() >= 5 else 'work'
            day = {'d': d, 'status': st}
            if d == 15 and mm % 3 == 0 and st == 'work':
                day.update(status='holiday', name='Public holiday')
            days.append(day)
        wd = sum(1 for x in days if x['status'] == 'work')
        months.append({'label': first.strftime('%b %Y'), 'working_days': wd, 'nonworking_days': nd - wd,
                       'working_hours': wd * 8, 'first_weekday': first.weekday(), 'days': days})
    return {'dashboard': {'data_date': '2025-12-11'}, 'project': {}, 'primary_calendar_id': 1,
            'by_calendar': {1: {'monthly_stats': months, 'hours_profiles': [],
                                'exceptions': {'holidays': [], 'special': [], 'shutdowns': []}}},
            'assigned_calendars': [{'object_id': 1, 'name': 'Standard 5-day'}]}


def _calendar_html():
    from p6_calendar.report import render_calendar_report
    return render_calendar_report(_calendar_result(), {'project_name': 'Synthetic'},
                                  sections=['dashboard', 'timeline'])


def _studio_calendar_html():
    """The Studio's 'Working-day timeline' item, reused exactly as its calendar provider does
    (feature_reports.calendar_section), inside the Studio's page shell."""
    from p6_calendar.report import render_calendar_report
    from p6_special import feature_reports as FR, render_html, reuse
    html = render_calendar_report(_calendar_result(), {'project_name': 'Synthetic'}, sections=['timeline'])
    payload = FR._payload('calendar', reuse.extract_styles(html), FR._strip_trailing_foot(FR._body_after_head(html)))
    filler = {'kind': 'html', 'feature': 'x', 'css': '',
              'html': '<div>' + '<p>A body paragraph of an earlier Studio section, long enough to fill '
                                'part of the page realistically before the calendar starts.</p>' * 6 + '</div>'}

    def item(iid, title, p):
        return {'id': iid, 'title': title, 'feature': iid.split(':')[0], 'feature_title': 'F',
                'ctype': 'section', 'payload': p}
    return render_html.build_document('Synthetic Studio', {'project_name': 'Synthetic'},
                                      [item('x:a', 'Executive read', filler),
                                       item('calendar:timeline', 'Working-day timeline', payload)], 'light')


_LAYER_RE = re.compile(r'<style id="rpt-pagination">.*?</style><script id="rpt-pagination-js">.*?</script>', re.S)


def _without_layer(html):
    """The report as the audit printed it: no shared pagination layer (Chrome's defaults)."""
    out = _LAYER_RE.sub('', html)
    assert 'rpt-pagination' not in out
    return out


def _chrome():
    from p6_export.pdf import chrome_candidates
    found = chrome_candidates(None)
    if not found:
        pytest.skip('no Chromium installed')
    return found[0]


def _print_raw(html, chrome, folder, name):
    from p6_export.pdf import run_chrome
    src = os.path.join(folder, name + '.html')
    with open(src, 'w', encoding='utf-8') as fh:
        fh.write(html)
    out = os.path.join(folder, name + '.pdf')
    run_chrome(chrome, [f'--print-to-pdf={out}', '--no-pdf-header-footer',
                        'file:///' + src.replace(os.sep, '/')], timeout=120)
    return out


def _month_days(pdf):
    """{month title: (page of the title, day numbers printed under it on THAT page)} — a month
    kept whole shows all its days under its title; a cut month loses its last weeks."""
    import pymupdf
    got = {}
    with pymupdf.open(pdf) as d:
        for pg in d:
            words = pg.get_text('words')
            titles = []
            for t in words:
                if not re.fullmatch(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', t[4]):
                    continue
                yr = [w for w in words if abs(w[1] - t[1]) < 2 and 0 < w[0] - t[2] < 12
                      and re.fullmatch(r'20\d\d', w[4])]
                below = [w for w in words if w[4] == 'Mon' and abs(w[0] - t[0]) < 8 and 0 < w[1] - t[3] < 14]
                if yr and below:                          # a month title over its weekday header
                    titles.append((t, t[4] + ' ' + yr[0][4]))
            for t, label in titles:
                nxt = min([u[1] for u, _ in titles if abs(u[0] - t[0]) < 4 and u[1] > t[1]], default=1e9)
                days = [w for w in words if t[0] - 2 <= w[0] <= t[0] + 175 and t[3] < w[1] < min(nxt, t[3] + 170)
                        and re.fullmatch(r'\d{1,2}', w[4])]
                got[label] = (pg.number + 1, len(days))
    return got


def _days_in(label):
    m = _dt.datetime.strptime(label, '%b %Y')
    return _cal.monthrange(m.year, m.month)[1]


def test_chrome_calendar_audit_month_grids_are_cut_without_the_layer_and_whole_with_it():
    """CAL-PDF-1: the real Calendar Audit renderer, 24 months. Without the shared layer (as the
    audit printed it) a page break runs through a row of month grids; with it (the production
    /api/export/pdf path) every month is printed whole under its title, zero checker flags."""
    from p6_export.pdf import html_to_pdf
    chrome = _chrome()
    html = _calendar_html()
    with tempfile.TemporaryDirectory() as folder:
        before = _print_raw(_without_layer(html), chrome, folder, 'before')
        after = os.path.join(folder, 'after.pdf')
        html_to_pdf(html, after, chrome=chrome)
        rb, ra = pc.check_pdf(before), pc.check_pdf(after)
        mb, ma = _month_days(before), _month_days(after)
    cut = {k: v for k, v in mb.items() if v[1] < _days_in(k)}
    assert cut, mb                                         # the test is meaningful …
    # (where the raw break falls decides whether the generic checker also flags it — the cut
    # months above are the proof the un-layered print is broken)
    assert len(ma) == 24, sorted(ma)
    assert {k: v for k, v in ma.items() if v[1] != _days_in(k)} == {}, ma
    assert ra['flags'] == [], ra['flags']


def test_chrome_studio_working_day_timeline_prints_every_month_whole():
    """STUDIO-PDF-3: the same calendars reused in the Studio document (inside its page shell):
    every month whole under its title, zero checker flags."""
    from p6_export.pdf import html_to_pdf
    chrome = _chrome()
    with tempfile.TemporaryDirectory() as folder:
        after = os.path.join(folder, 'studio.pdf')
        html_to_pdf(_studio_calendar_html(), after, chrome=chrome)
        ra, ma = pc.check_pdf(after), _month_days(after)
    assert len(ma) == 24, sorted(ma)
    assert {k: v for k, v in ma.items() if v[1] != _days_in(k)} == {}, ma
    assert ra['flags'] == [], ra['flags']


def test_table_header_repeated_at_the_very_top_of_every_page_is_not_a_running_header(tmp_path):
    """A long register in a report with no running header (Schedule Health lag / lead): its header
    row repeated at the top of every page sits in the sheet's header band — it is the table's
    repeated header, not page furniture, so the table is NOT 'continued without its header'."""
    def rows(y, n, first):
        ops = [('t', 40, y, 'Activity ID', 9, True), ('t', 200, y, 'Activity name', 9, True),
               ('t', 400, y, 'Relationship', 9, True)]
        for i in range(n):
            ops += [('t', 40, y + 18 * (i + 1), f'A-{first + i}', 9, False),
                    ('t', 200, y + 18 * (i + 1), f'Activity {first + i}', 9, False),
                    ('t', 400, y + 18 * (i + 1), 'FS', 9, False)]
        return ops
    pages = [[('t', 40, 50, 'Lag and lead register', 14, True)] + rows(80, 40, 1)]
    for k in range(1, 4):
        pages.append(rows(45, 42, 1 + 40 + 42 * (k - 1)))
    res = pc.check_pdf(_pdf(str(tmp_path / 'register.pdf'), pages))
    assert res['flags'] == [], res['flags']
