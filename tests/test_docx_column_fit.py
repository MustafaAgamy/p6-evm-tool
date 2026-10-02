"""Word tables: a column is never narrower than its longest single word.

Found while checking comment 2 in the built exe: the Lag Report register in Word wrapped the row
number "10" onto two lines ("1" / "0") and every Activity ID after its last digit, because the
column widths followed the report's weights only.
"""
from p6_export.to_docx import _fit_widths


def test_narrow_columns_grow_to_their_longest_word_and_the_total_is_kept():
    widths = [10, 56, 113, 35, 113, 35, 113, 37]
    mins = [21, 101, 73, 57, 63, 57, 56, 61]
    out = _fit_widths(widths, mins)
    assert sum(out) == sum(widths)
    assert all(o >= m for o, m in zip(out, mins))
    assert out[0] == 21 and out[1] == 101                       # '#' and Activity ID fit on one line


def test_columns_that_already_fit_are_left_alone():
    assert _fit_widths([100, 200, 300], [50, 60, 70]) == [100, 200, 300]
    assert _fit_widths([], []) == []


def test_when_the_needs_do_not_fit_the_shortage_is_shared():
    out = _fit_widths([10, 290], [200, 200])                     # 400 needed, 300 there
    assert sum(out) == 300 and out[0] >= 140 and out[1] >= 140


def test_the_register_ids_stay_on_one_line_in_word(tmp_path):
    import docx
    from p6_export import to_docx
    rows = ''.join(f'<tr><td>{i}</td><td style="font-family:Consolas,monospace">CONS.BTC3.MECH.{1000 + i}</td>'
                   f'<td>Preassembly of the machine tower sections number {i}</td><td>FS+{i}</td></tr>' for i in range(8, 13))
    html = ('<html><body><div data-sec="reg"><h2>Register</h2><table><colgroup><col style="width:3%"><col style="width:12%">'
            '<col style="width:70%"><col style="width:15%"></colgroup><thead><tr><th>#</th><th>Activity ID</th>'
            f'<th>Activity Name</th><th>Pred. Relationship</th></tr></thead><tbody>{rows}</tbody></table></div></body></html>')
    out = tmp_path / 'r.docx'
    to_docx.html_to_docx(html, str(out), app_name='Controlyx', feature='T')
    t = docx.Document(str(out)).tables[0]
    w = [c.width for c in t.rows[1].cells]
    assert w[0] >= 12700 * 15, 'the # column holds two digits'
    assert w[1] >= 12700 * 90, 'the Activity ID column holds the longest ID'
    assert abs(sum(w) - sum(c.width for c in t.rows[0].cells)) < 5
