"""Gantt in Word: the bar column is drawn, as in the PDF (final sweep, comment 3).

The printed Gantt table has a time-line column — the bar from Start to Finish with its
% complete fill, the milestone diamond and the data-date line on a page-wide month scale.
It was marked screen-only, so Word got the table without its bars.  Now Word draws each
bar as native, editable Word shapes in that column; Excel leaves the column out (the dates
are in the other columns).
"""
import os
import re
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _gantt_css():
    css = open(os.path.join(ROOT, 'ui', 'style.css'), encoding='utf-8').read()
    keep = [ln for ln in css.splitlines() if ln.lstrip().startswith('.gp-')]
    assert keep, 'the printed Gantt styles are in ui/style.css'
    return (':root{--accent:#1F6FEB;--accent-soft:#D6E4FB;--danger:#D1242F;--danger-bg:#EF4444;'
            '--bg:#EEF1F5;--text:#1B2330;--muted:#6B7686;--border:#C9D1DC;--hair:#E1E6EE}\n' + '\n'.join(keep))


def _html():
    head = ('<thead><tr><th>Activity ID</th><th>Activity name</th><th>Start</th><th>Finish</th><th class="gp-n">%</th>'
            '<th class="gp-n">Float</th><th class="gp-tl" data-export="bar"><div class="gp-scale">'
            '<span style="left:10.00%">Jan 25</span><span style="left:50.00%">Jul 25</span></div></th></tr></thead>')
    dd = '<u style="left:40.00%"></u>'
    rows = (
        '<tr><td class="gp-id">A1000</td><td>Excavation</td><td class="gp-d">01 Jan 25</td><td class="gp-d">01 Mar 25</td>'
        '<td class="gp-n">50</td><td class="gp-n">12</td><td class="gp-tl" data-export="bar"><div class="gp-track">'
        f'{dd}<b class="gp-bar" style="left:10.00%;width:30.00%"><s style="width:50%"></s></b></div></td></tr>'
        '<tr class="gp-crit"><td class="gp-id">A1010</td><td>Foundations</td><td class="gp-d">01 Mar 25</td><td class="gp-d">01 Jun 25</td>'
        '<td class="gp-n">0</td><td class="gp-n">0</td><td class="gp-tl" data-export="bar"><div class="gp-track">'
        f'{dd}<b class="gp-bar crit" style="left:40.00%;width:30.00%"><s style="width:0%"></s></b></div></td></tr>'
        '<tr><td class="gp-id">M100 ◆</td><td>Handover</td><td class="gp-d">01 Sep 25</td><td class="gp-d">01 Sep 25</td>'
        '<td class="gp-n">0</td><td class="gp-n">5</td><td class="gp-tl" data-export="bar"><div class="gp-track">'
        f'{dd}<b class="gp-ms" style="left:90.00%"></b></div></td></tr>')
    return (f'<html><head><style>{_gantt_css()}</style></head><body><div data-sec="gantt"><h2>Gantt chart</h2>'
            f'<table class="gp-table">{head}<tbody>{rows}</tbody></table></div></body></html>')


def test_the_model_reads_the_bars_and_the_scale():
    from p6_export import html_model as HM
    rep = HM.parse_report(_html())
    t = [b for b in rep.all_blocks() if b.kind == 'table'][0]
    scale = t.rows[0][6].bar['scale']
    assert [(round(p), lbl) for p, lbl, _ in scale] == [(10, 'Jan 25'), (50, 'Jul 25')]
    b1, b2, ms = (r[6].bar for r in t.rows[1:])
    assert b1['bar'][:2] == (10.0, 30.0) and b1['fill'][0] == 50.0 and b1['dd'][0] == 40.0
    assert b1['bar'][2] == 'D6E4FB' and b1['fill'][1] == '1F6FEB'
    assert b2['bar'][2] == 'EF4444'                              # critical = red, as in the PDF
    assert ms['ms'][0] == 90.0 and ms['ms'][1] == '1B2330' and 'bar' not in ms
    assert t.col_weights[6] > 0.2, 'the time-line column keeps its room'


def test_word_draws_each_bar_as_native_shapes(tmp_path):
    import docx
    from p6_export import to_docx
    out = tmp_path / 'g.docx'
    to_docx.html_to_docx(_html(), str(out), app_name='Controlyx', feature='Gantt', use_chrome=False)
    xml = zipfile.ZipFile(out).read('word/document.xml').decode('utf-8')
    assert xml.count('name="Gantt bar') == 4                     # the scale + three rows
    assert '<pic:pic' not in xml and 'D6E4FB' in xml and 'EF4444' in xml and '1F6FEB' in xml
    assert 'Jan 25' in xml and 'Jul 25' in xml
    t = docx.Document(str(out)).tables[0]
    assert len(t.columns) == 7 and t.rows[1].cells[0].text == 'A1000'


def test_excel_leaves_the_time_line_column_out():
    from p6_export import html_model as HM, to_xlsx
    rep = HM.parse_report(_html())
    t = [b for b in rep.all_blocks() if b.kind == 'table'][0]
    blk = to_xlsx._table_block(t, 'Gantt')
    assert blk['headers'] == ['Activity ID', 'Activity name', 'Start', 'Finish', '%', 'Float']
    assert all(len(r) == 6 for r in blk['rows'])


def test_the_printed_gantt_marks_its_bar_column_for_the_exports():
    g = open(os.path.join(ROOT, 'ui', 'modules', 'gantt.js'), encoding='utf-8').read()
    assert len(re.findall(r'class="gp-tl" data-export="bar"', g)) == 3      # header, activity row, WBS band row
    assert 'class="gp-tl" data-export="skip"' not in g


def _months_html():
    mons = ['Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    w = 100.0 / len(mons)
    spans = ('<span class="yr" data-r="0" style="left:0%;width:7.69%"></span>'
             '<span class="yr" data-r="0" style="left:7.69%;width:92.31%">2025</span>'
             + ''.join(f'<span class="mo" data-r="1" style="left:{i * w:.2f}%;width:{w:.2f}%">{m}</span>' for i, m in enumerate(mons)))
    head = ('<thead><tr><th>WBS</th><th>Baseline Start</th><th>Baseline Finish</th><th>Expected Start</th><th>Expected Finish</th>'
            '<th>Planned %</th><th>Actual %</th><th>Delay</th>'
            f'<th class="gp-tl" data-export="bar"><div class="gp-scale">{spans}</div></th></tr></thead>')
    row = ('<tr><td>Engineering</td><td>19-Dec.2024</td><td>15-May.2025</td><td>19-Dec.2024 A</td><td>15-Sep.2025</td>'
           '<td>100.0%</td><td>45.3%</td><td>-123 d</td><td class="gp-tl" data-export="bar"><div class="gp-track">'
           '<b class="gp-bar" style="left:10.00%;width:30.00%"><s style="width:50%"></s></b></div></td></tr>')
    return (f'<html><head><style>{_gantt_css()}</style></head><body><div data-sec="wbs"><h2>WBS</h2>'
            f'<table class="gp-table">{head}<tbody>{row}</tbody></table></div></body></html>')


def test_word_month_names_never_run_into_each_other(tmp_path):
    """Owner: 'when exporting to word the Gantt chart ... the scale seems to be unreadable'. The PDF
    fits 13 month names on one line; Word's column is narrower, so there they take more lines."""
    from p6_export import to_docx
    out = tmp_path / 'm.docx'
    to_docx.html_to_docx(_months_html(), str(out), app_name='X', feature='WBS', project='P', chrome=None)
    x = zipfile.ZipFile(out).read('word/document.xml').decode('utf8')
    lines = [p for p in re.findall(r'<w:p>.*?</w:p>', x, flags=re.S)
             if 'Consolas' in p and re.search(r'>(Jan|Feb|Dec)<', p)]
    assert len(lines) >= 2, 'the month names are spread over more than one line'
    for p in lines:                                   # on a line, each name has the room of its width
        stops = [int(v) for v in re.findall(r'<w:tab w:val="left" w:pos="(\d+)"', p)]
        assert all(b - a >= 3 * 7.4 * 0.6 * 20 for a, b in zip(stops, stops[1:])), stops
    names = re.findall(r'>(Dec|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov)<', ''.join(lines))
    assert len(names) == 13, 'every month is still written'
