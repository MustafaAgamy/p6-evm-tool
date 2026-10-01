"""Owner comment 16 — professional page composition in every report (Reporting Studio first).

What went wrong on a real Reporting Studio document (GBT update with Critical Path Analyzer,
Consultant Review and Update vs Update) and is pinned here:

* Chrome prints the WHOLE document at 67 % when any element is wider than the page - body text
  came out near 5 pt and a 16-column table at 2.7 pt. The checker now flags unreadable text,
  the Consultant Review logic table has a portrait layout, the Update vs Update critical-path
  chain wraps and its milestone drift chart is drawn for a portrait page.
* Critical Path Analyzer: a lane title ended a page alone; day counts printed unrounded.
* Baseline Revision: the before / after rows of a finding had no layout in the report (stacked
  boxes, half a page per finding); a bold label on a card's last line forbade the break after
  every card (the print composer marked it keep-with-next) and Chrome cut cards in two.
"""
import pytest

import report_theme as rt
from p6_export import pagination_check as pc

pymupdf = pytest.importorskip('pymupdf')
A4 = (595, 842)


def _pdf(path, pages):
    doc = pymupdf.open()
    for ops in pages:
        pg = doc.new_page(width=A4[0], height=A4[1])
        for x, y, text, size, bold in ops:
            pg.insert_text((x, y), text, fontsize=size, fontname='hebo' if bold else 'helv')
    doc.save(path)
    doc.close()
    return str(path)


def _page(no, size):
    ops = [(40, 30, 'PROJECT REPORT  A real project', 8, False), (280, 825, f'Page {no} of 3', 8, False)]
    ops += [(40, y, f'Body line {y} of the report text on page {no}, plain planning words here.', size, False)
            for y in range(70, 760, 14)]
    return ops


# ── the page checker ─────────────────────────────────────────────────────────
def test_checker_flags_pages_of_unreadable_text(tmp_path):
    shrunk = pc.check_pdf(_pdf(tmp_path / 'shrunk.pdf', [_page(1, 9), _page(2, 4), _page(3, 4)]))
    small = [f for f in shrunk['flags'] if f['type'] == 'text_too_small']
    assert len(small) == 1 and small[0]['page'] == 2
    assert '2 page(s)' in small[0]['detail'] and '4.0 pt' in small[0]['detail']
    assert 'text_too_small' in pc.DEFECT_TYPES


def test_checker_accepts_readable_text(tmp_path):
    ok = pc.check_pdf(_pdf(tmp_path / 'ok.pdf', [_page(1, 9), _page(2, 8), _page(3, 6)]))
    assert not [f for f in ok['flags'] if f['type'] == 'text_too_small']


@pytest.mark.parametrize('text,is_value', [
    ('0 d / 0 wd', True), ('+42 d / -42.7 wd', True), ('55.6 %', True), ('1,250', True),
    ('Driving chain', False), ('Rev.01 driving chain', False), ('Phase 1 Works', False),
])
def test_checker_knows_a_card_value_from_a_title(text, is_value):
    assert bool(pc._VALUE_RE.match(text)) is is_value


# ── the print composer ───────────────────────────────────────────────────────
def test_composer_leaves_titles_inside_a_renderers_own_keep_whole_card_alone():
    js = rt.pagination_script()
    kept = js[js.index('function inKept'):js.index('function headings')]
    assert 'getComputedStyle(a).breakInside' in kept and "bi==='avoid'" in kept
    assert 'hOf(a)>fit' in kept            # only a SMALL card; a tall block still pairs its titles


# ── Consultant Review: the logic table on a portrait page ────────────────────
_LOGIC = {'logic': {'rows': [{
    'activity_id': 'A1000', 'activity_name': 'Pile Works', 'change_label': 'Type changed',
    'baseline_preds': [{'code': 'A0900', 'name': 'Excavation', 'type': 'FS', 'lag_days': 0}],
    'baseline_succs': [], 'update_succs': [],
    'update_preds': [{'code': 'A0900', 'name': 'Excavation', 'type': 'SS', 'lag_days': 5}]}]},
    'change_summary': {'items': []}, 'dashboard': {}}


def test_consultant_review_logic_table_has_a_portrait_layout_with_the_same_data():
    from p6_compare.exporters import render_html
    wide = render_html(_LOGIC, sections=['logic'])
    tall = render_html(_LOGIC, sections=['logic'], layout='portrait')
    assert '<th colspan="6" class="grp">Baseline — driving links</th>' in wide      # 16 columns
    assert 'class="data stk"' not in wide.split('</style>')[-1]
    body = tall.split('</style>')[-1]
    assert 'class="data stk"' in body and '<th colspan="2" class="grp">Baseline — driving links</th>' in body
    assert '<th>Predecessors</th><th>Successors</th><th>Predecessors</th><th>Successors</th>' in body
    for bit in ('A1000', 'Pile Works', 'Type changed', 'A0900', 'Excavation', 'FS', 'SS+5'):
        assert bit in body                                   # same rows, same data
    assert 'table.data.stk { table-layout: fixed; }' in tall


def test_reporting_studio_asks_for_the_portrait_layout():
    import inspect
    from p6_special import feature_reports
    from p6_special.providers import twofile
    assert "layout='portrait'" in inspect.getsource(feature_reports.compare_full_report)
    assert inspect.getsource(twofile).count("layout='portrait'") == 2


# ── Update vs Update ─────────────────────────────────────────────────────────
def test_critical_path_chain_wraps_and_never_cuts_a_name():
    from p6_period import exporters as px
    long_name = 'Above Silos From S6 Till S10 -CC7-CC8A-CC8B-CC9'
    seg = lambda k: {'key': k, 'start': '2026-04-01', 'finish': '2026-04-20'}
    curr = [seg('Silo 9'), seg(long_name)]
    wprev, wcurr = px._cp_widths(curr, curr, 2)
    assert wcurr[0] >= 58 and wcurr[1] >= 150               # room for the long name on ~2 lines
    css = px.render_html.__globals__  # noqa: F841 (module loaded)
    import inspect
    src = inspect.getsource(px.render_html)
    assert 'flex-wrap: wrap' in src and 'overflow-wrap: anywhere' in src and 'min-height: 44px' in src


def test_milestone_drift_chart_is_drawn_for_a_portrait_page():
    from p6_period.exporters import _milestone_drift_svg
    rows = [{'name': 'Phase C Civil Works Completion Milestone', 'baseline_iso': '2026-07-01',
             'prev_iso': '2026-08-01', 'curr_iso': '2026-09-01'}]
    svg = _milestone_drift_svg({'milestones': {'rows': rows}})
    assert 'viewBox="0 0 700 ' in svg and 'font-size="10"' in svg
    assert 'Phase C Civil Works Completion Mile' in svg       # 35 characters before the ellipsis


# ── Critical Path Analyzer ───────────────────────────────────────────────────
@pytest.mark.parametrize('v,out', [(-42.666666666666664, '-42.7 wd'), (0.6666666666, '+0.7 wd'),
                                   (0.0, '0 wd'), (12, '+12 wd'), (None, '—')])
def test_day_counts_read_as_p6_shows_them(v, out):
    from p6_critpath.exporters import _sd
    assert _sd(v, ' wd') == out


def test_critical_path_titles_reserve_a_row_of_cards_and_the_pill_sits_inside_the_card():
    import inspect
    from p6_critpath import exporters as cx
    src = inspect.getsource(cx)
    assert '<div class="lanekeep"><div class="lanehdr">' in src and '<div class="mpkeep"><div class="mphdr">' in src
    assert '.lanekeep::after' in src and 'margin-bottom: -150px' in src
    pill = src[src.index('.bflag {{'):].split('}}')[0]
    assert 'position: absolute' not in pill and 'display: table' in pill


# ── Baseline Revision ────────────────────────────────────────────────────────
def test_baseline_revision_report_lays_a_finding_on_one_row_as_on_screen():
    import inspect
    from p6_revcompare import exporters as rx
    src = inspect.getsource(rx)
    assert '.chain2 { display: flex; align-items: stretch; flex-wrap: nowrap; }' in src
    assert '.clink2 {' in src and '.rev2lab {' in src
    assert '.chain2 .cnode { flex: 1 1 0;' in src


def test_driving_chain_total_float_is_rounded():
    from p6_revcompare.exporters import _cp_chain
    html = _cp_chain([{'name': 'Pile Works', 'tf': 0.6666666666666666}, {'name': 'Columns', 'tf': 0.0}])
    assert 'TF 0.7<' in html and 'TF 0<' in html and '0.6666' not in html
