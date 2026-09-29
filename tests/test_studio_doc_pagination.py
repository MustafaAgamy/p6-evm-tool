"""Owner point 14 — the Reporting Studio's own Word button (Office-HTML ``.doc``,
``p6_special.word_export``), finding STUDIO-DOC-1.

Word's HTML engine has no flex / grid: every ``<div>`` of a screen row prints as its own line.
So a score row ("Float Analysis | bar | 95.8% | 15 | 16.9"), a bar row or a KPI card could be
cut between its name and its values, a card title ("Lags by WBS area") could end a page, and
the Calendar's month calendars printed as a column of ~40 one-word lines that a break cut
anywhere ("Mon … Sun" ending a page, the days on the next). The shared Word pass
(``p6_export.doc_pagination``) now keeps a screen row's lines together and a container's title
with its first block; ``word_export`` re-lays each month calendar as a small 7-column table
(two months a row, rows never split). Unit tests on the rewrite + a PROOF laid out by Word
itself (COM): the same Studio document is flagged without these rules and clean with them.
"""
import calendar as _cal
import datetime as _dt
import os
import re

import pytest

from p6_export import doc_pagination as DP
from p6_export import pagination_check as pc
from p6_special import word_export as WE

KWN = 'page-break-after:avoid'


def _kwn_texts(html):
    """Texts of the elements that carry keep-with-next."""
    return [re.sub(r'<[^>]+>', '', m.group(2)).strip()
            for m in re.finditer(r'<(div|p)\b[^>]*' + KWN + r'[^>]*>(.*?)</\1>', html, re.S)]


# ── unit: the Word rewrite ───────────────────────────────────────────────────────────────
def test_screen_row_lines_are_kept_together_last_line_free():
    row = ('<div class="crow"><div class="nm"><span class="dot"></span>Float Analysis</div>'
           '<div class="bar"><i style="width:96%"></i></div><div class="sc">95.8%</div>'
           '<div class="wt">15</div><div class="pt">16.9</div></div>')
    out = DP.paginate_word_html(row * 2)
    assert _kwn_texts(out) == ['Float Analysis', '', '95.8%', '15'] * 2, out
    assert re.sub(r' style="page-break-after:avoid"', '', out) == row * 2      # nothing else changed


def test_kpi_card_label_keeps_with_its_value():
    out = DP.paginate_word_html('<div class="kpi"><div class="k">Delay</div><div class="v">0 days</div></div>')
    assert _kwn_texts(out) == ['Delay'], out


def test_card_title_keeps_with_its_first_row():
    html = ('<div class="lcard"><div class="lch">Lags by WBS area</div>'
            '<div class="lbarS"><div class="lblS">Silos Civil Works</div><div class="lineS">'
            '<span class="trk"><i style="width:100%"></i></span><span class="lval">153</span></div></div>'
            '<div class="lbarS"><div class="lblS">Detailed</div><div class="lineS">'
            '<span class="lval">89</span></div></div></div>')
    out = DP.paginate_word_html(html)
    assert _kwn_texts(out) == ['Lags by WBS area', 'Silos Civil Works', 'Detailed'], out


def test_body_text_and_long_groups_are_left_free():
    para = 'A body paragraph of the narrative that runs on for well over a line of text, ' * 3
    html = (f'<div class="notes"><div>{para}</div><div>{para}</div></div>'        # long: not a row
            '<div class="box"><div>Short</div><table><tr><td>x</td></tr><tr><td>y</td></tr></table>'
            '<div>after</div></div>')                                            # holds a table
    out = DP.paginate_word_html(html)
    assert KWN not in out.split('<div class="box">')[0], out
    # only the existing rules there: the label before the table, the small table's rows
    assert _kwn_texts(out) == ['Short', 'x'], out


def test_heading_table_and_data_tables_keep_rules():
    head = ('<table class="sr-sec-h"><tr><td><span class="sr-num">7</span></td>'
            '<td>Delay in working days</td></tr></table>')
    small = '<table><tr><th>A</th><th>B</th></tr>' + '<tr><td>1</td><td>2</td></tr>' * 4 + '</table>'
    long_ = '<table><tr><th>A</th><th>B</th></tr>' + ''.join(
        f'<tr><td>r{i}</td><td>v</td></tr>' for i in range(30)) + '</table>'
    out = DP.paginate_word_html(head + small + long_)
    h, s, l_ = out.split('<table')[1:]
    assert h.count(KWN) == 2                                    # both heading cells keep with next
    assert '<thead>' in s and '<thead>' in l_                    # header rows repeat on every page
    assert s.count(KWN) == 2 * (1 + 3)                           # header + all body rows but the last
    kept = [m for m in re.findall(r'<tr><td>(?:<p[^>]*>)?(r\d+)', l_)]
    assert [r for r in kept] == [f'r{i}' for i in range(30)]
    kw = re.findall(r'<td><p style="margin:0;page-break-after:avoid">(r\d+)</p>', l_)
    assert kw == ['r0', 'r1', 'r27', 'r28'], kw                  # never 1-2 rows stranded


# ── unit: month calendars as Word tables ─────────────────────────────────────────────────
def _months(n):
    out = []
    for i in range(n):
        yy, mm = 2026 + i // 12, i % 12 + 1
        first, nd = _dt.date(yy, mm, 1), _cal.monthrange(yy, mm)[1]
        days = []
        for d in range(1, nd + 1):
            st = 'weekend' if _dt.date(yy, mm, d).weekday() >= 5 else 'work'
            day = {'d': d, 'status': st}
            if d == 15 and st == 'work':
                day.update(status='holiday', name='Public holiday')
            days.append(day)
        wd = sum(1 for x in days if x['status'] == 'work')
        out.append({'label': first.strftime('%b %Y'), 'working_days': wd, 'nonworking_days': nd - wd,
                    'working_hours': wd * 8, 'first_weekday': first.weekday(), 'days': days})
    return out


def _calendar_body(n):
    from p6_calendar.report import render_calendar_report
    res = {'dashboard': {'data_date': '2025-12-11'}, 'project': {}, 'primary_calendar_id': 1,
           'by_calendar': {1: {'monthly_stats': _months(n), 'hours_profiles': [],
                               'exceptions': {'holidays': [], 'special': [], 'shutdowns': []}}},
           'assigned_calendars': [{'object_id': 1, 'name': 'Standard 5-day'}]}
    html = render_calendar_report(res, {'project_name': 'Synthetic'}, sections=['timeline'])
    return html[html.index('<div class="mgrids">'):]


def test_month_calendars_become_week_tables_two_a_row():
    src = _calendar_body(3)
    out = WE._month_grids_as_tables(src)
    assert 'class="mgrid"' not in out and 'class="mgrids"' not in out
    assert out.count('class="mgrid-tbl"') == 3 and out.count('class="mgrids-tbl"') == 1
    assert out.count('<tr style="page-break-inside:avoid">') == 2          # months two a row
    for label, days in (('Jan 2026', 31), ('Feb 2026', 28), ('Mar 2026', 31)):
        part = out.split(f'<div class="mgrid-t">{label}</div>')[1].split('</table>')[0]
        assert re.findall(r'>(Mon|Tue|Wed|Thu|Fri|Sat|Sun)</th>', part) == ['Mon', 'Tue', 'Wed', 'Thu',
                                                                           'Fri', 'Sat', 'Sun']
        nums = [int(x) for x in re.findall(r'<span class="dn">(\d+)</span>', part)]
        assert nums == list(range(1, days + 1))                            # every day, in order
        rows = part.split('<tbody>')[1].count('<tr>')
        assert all(r.count('<td') == 7 for r in part.split('<tbody>')[1].split('<tr>')[1:])
        assert 4 <= rows <= 6
    assert 'Public holiday' in out                                         # cell names kept
    # every day-number and holiday name of the source survives, in the same order
    assert re.findall(r'>(\d+|Public holiday)<', out) == re.findall(
        r'>(\d+|Public holiday)<', src.replace('</div>', '</div>'))


def test_month_rows_carry_no_keep_rules_inside_only_the_legend_keeps_with_them():
    """Word keeps a table row whose paragraphs keep-with-next with the NEXT row: keep rules
    inside the (never-splitting) rows of months would chain them all into one pushed block."""
    src = ('<div class="sub2">Each month calendar</div><div class="legend"><span>Working</span>'
           '<span>Holiday</span></div>' + _calendar_body(6))
    out = DP.paginate_word_html(WE._month_grids_as_tables(src))
    lay = out[out.index('class="mgrids-tbl"'):]
    assert KWN not in lay, lay[:400]
    assert lay.count('<tr style="page-break-inside:avoid">') == 3
    assert lay.count('<thead>') == 6                                 # each month's weekday header
    assert _kwn_texts(out[:out.index('class="mgrids-tbl"')]) == ['WorkingHoliday']   # legend + months


def test_studio_word_document_carries_month_tables_and_row_rules():
    html = WE.build_word_document('Synthetic', {'project_name': 'Synthetic'}, _rendered(months=2, rows=3))
    assert 'class="mgrid-tbl"' in html and 'class="mgrid"' not in html
    assert '<div class="nm" style="page-break-after:avoid">' in html


# ── PROOF: Word's own pagination of a synthetic Studio .doc ─────────────────────────────
_P = ('<p>This paragraph stands for a long passage of an earlier Studio section: it describes '
      'the scope, the methodology and the phasing in enough words to be a real body paragraph.</p>')


def _score_rows(n):
    return ''.join(
        f'<div class="crow"><div class="nm"><span class="dot" style="background:#15803d"></span>'
        f'Check number {i:02d}</div><div class="bar"><i style="width:{50 + i % 40}%;background:#15803d"></i>'
        f'</div><div class="sc">{90 + i % 10}.5%</div><div class="wt">{i % 20}</div>'
        f'<div class="pt">{i % 17}.4</div></div>' for i in range(n))


def _rendered(months=24, rows=70):
    from p6_calendar.report import render_calendar_report
    from p6_special import feature_reports as FR, reuse
    res = {'dashboard': {'data_date': '2025-12-11'}, 'project': {}, 'primary_calendar_id': 1,
           'by_calendar': {1: {'monthly_stats': _months(months), 'hours_profiles': [],
                               'exceptions': {'holidays': [], 'special': [], 'shutdowns': []}}},
           'assigned_calendars': [{'object_id': 1, 'name': 'Standard 5-day'}]}
    cal = render_calendar_report(res, {'project_name': 'Synthetic'}, sections=['timeline'])
    cal_payload = FR._payload('calendar', reuse.extract_styles(cal), FR._strip_trailing_foot(FR._body_after_head(cal)))
    css = ('.crow{display:flex;gap:8px;font-size:10px}.crow .nm{font-weight:700;width:40%}'
           '.lcard{border:1px solid #d9dee6}.lch{font-weight:700;text-transform:uppercase;font-size:9px}')
    score = {'kind': 'html', 'feature': 'audit', 'css': css,
             'html': '<div class="srf-audit">' + _P * 3 + '<div class="lcard"><div class="lch">'
                     'Score by check</div>' + _score_rows(rows) + '</div></div>'}

    def item(iid, title, p):
        return {'id': iid, 'title': title, 'feature': iid.split(':')[0], 'feature_title': 'F',
                'ctype': 'section', 'payload': p}
    return [item('audit:health_score', 'Schedule Health - score', score),
            item('calendar:timeline', 'Working-day timeline', cal_payload)]


def test_word_lays_out_the_studio_doc_with_rows_and_months_whole(tmp_path, monkeypatch):
    if not pc.word_available():
        pytest.skip('Microsoft Word (COM) is not available')
    rendered = _rendered()
    after = str(tmp_path / 'after.doc')
    WE.save_word_document(WE.build_word_document('Synthetic Studio', {'project_name': 'Synthetic'},
                                                 rendered), after)
    # the same document as the Studio wrote it before this fix
    monkeypatch.setattr(WE, '_month_grids_as_tables', lambda h: h)
    monkeypatch.setattr(DP, '_line_groups', lambda toks: [])
    before = str(tmp_path / 'before.doc')
    WE.save_word_document(WE.build_word_document('Synthetic Studio', {'project_name': 'Synthetic'},
                                                 rendered), before)
    rb = pc.check_docx(before, engine='word', timeout=900)
    ra = pc.check_docx(after, engine='word', timeout=900)
    assert rb['status'] == 'ok' and ra['status'] == 'ok', (rb['message'], ra['message'])
    assert any(f['type'] == 'orphaned_heading' for f in rb['flags']), rb['flags']
    assert ra['flags'] == [], ra['flags']
    assert ra['pages'] < rb['pages'], (ra['pages'], rb['pages'])    # months two a row, not 40 lines
