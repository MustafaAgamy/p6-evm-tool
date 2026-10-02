"""Owner comment 1 — "Every feature split into sub-features, with a picker to print any sub-feature
or any single part of it."

The Report Contents picker has two levels: SECTIONS (``data-sec``) and the PARTS inside them
(``data-part``).  Only Earned Value and Calendar Audit had both.  Now:

  * every report renderer wraps its sections in ``data-sec`` (Schedule Health checks, the Float
    report, the Health summary, Consultant Review joined the ones that already did);
  * ``p6_export.auto_parts.annotate`` finds the parts of any section that has none marked by hand
    (each table, chart, tile group, sub-headed block), and every preview route runs it;
  * Update Analysis, Update vs Update and Critical Path name their parts by hand and open the
    shared preview instead of their own older overlay.
"""
import re

from p6_export.auto_parts import AUTO_ATTR, annotate, wrap_part, wrap_section
from tests.test_server import _LAG_XML, _post_json


def _parts(html):
    return re.findall(r'data-part="([^"]+)"\s+data-part-label="([^"]*)"', html)


def _secs(html):
    return re.findall(r'data-sec="([^"]+)"', html)


TABLE = '<table><thead><tr><th>Activity ID</th><th>Name</th><th>Float</th><th>WBS</th></tr></thead><tbody><tr><td>A1</td><td>x</td><td>3</td><td>w</td></tr></tbody></table>'
CHART = '<svg viewBox="0 0 10 10"><rect width="5" height="5"/></svg>'


# ── the automatic part finder ─────────────────────────────────────────────────────

def test_blocks_of_a_section_become_parts_with_readable_labels():
    html = ('<html><body><div data-sec="findings"><h2 class="sec">Findings</h2>'
            '<p class="note">These are the flagged activities.</p>'
            f'{TABLE}<div class="chartcard"><div class="chartt">Lags by type</div>{CHART}</div>'
            '</div></body></html>')
    out = annotate(html)
    assert _parts(out) == [('findings.a1', 'Table — Activity ID · Name · Float'), ('findings.a2', 'Lags by type')]
    assert out.count(AUTO_ATTR) == 2
    # only attributes were added: stripping them gives the original document back
    assert re.sub(r' data-part="[^"]*" data-part-label="[^"]*" %s="1"' % AUTO_ATTR, '', out) == html
    # the intro note is not a part — it stays with the section
    assert 'data-part' not in out[out.index('<p class="note"'):out.index('<table')]


def test_a_sub_heading_takes_what_follows_it_as_one_part():
    html = ('<section data-sec="cost"><h2>Cost</h2>'
            f'<h3>Where the money moved</h3><p>by phase</p>{TABLE}'
            f'<h3>Cost reconciliation</h3>{CHART}<p class="note">note</p></section>')
    out = annotate(html)
    assert [lab for _id, lab in _parts(out)] == ['Where the money moved', 'Cost reconciliation']
    # a heading + its blocks are wrapped without changing the layout, and the wrappers do not overlap
    assert out.count('style="display:contents"') == 2
    first = out.index('data-part="cost.a1"')
    assert out.index('</div><div data-part="cost.a2"') > first
    assert out.count('<div') - html.count('<div') == out.count('</div>') - html.count('</div>') == 2


def test_a_second_h2_inside_one_section_opens_a_part():
    html = (f'<div data-sec="findings"><h2 class="sec">WBS Summary</h2>{TABLE}'
            f'<h2 class="sec">Detailed Findings</h2>{TABLE}</div>')
    labels = [lab for _id, lab in _parts(annotate(html))]
    # the first h2 is the section's own title; the second one names the second part
    assert labels[-1] == 'Detailed Findings' and len(labels) == 2


def test_tiles_are_named_key_figures_not_by_their_values():
    html = ('<div data-sec="dash"><h2>Dashboard</h2>'
            '<div class="kpis"><div class="kpi"><div class="v">0.74</div><div class="k">CPLI</div></div>'
            '<div class="kpi"><div class="v">62%</div><div class="k">Critical</div></div></div>'
            f'{TABLE}</div>')
    labels = [lab for _id, lab in _parts(annotate(html))]
    assert labels[0] == 'Key figures' and labels[1].startswith('Table')


def test_rows_of_a_list_are_one_part_but_big_look_alike_blocks_stay_separate():
    rows = ''.join(f'<div class="wrow"><span>Item {i}</span><span>{i}0%</span></div>' for i in range(1, 9))
    html = f'<div data-sec="scope"><h2>Scope</h2>{rows}{TABLE}</div>'
    labels = [lab for _id, lab in _parts(annotate(html))]
    assert len(labels) == 2 and labels[0] in ('List', 'Chart', 'Key figures')
    blocks = ''.join(f'<div class="mpblock"><div class="mphdr">Path to milestone {i}</div>{CHART}</div>' for i in range(1, 5))
    html = f'<div data-sec="paths"><h2>Paths</h2><div class="wrap">{blocks}</div></div>'
    assert [lab for _id, lab in _parts(annotate(html))] == ['Path to milestone %d' % i for i in range(1, 5)]


def test_same_labels_are_numbered():
    html = f'<div data-sec="s"><h2>S</h2>{CHART}{CHART}{CHART}</div>'
    assert [lab for _id, lab in _parts(annotate(html))] == ['Chart', 'Chart (2)', 'Chart (3)']


def test_sections_left_alone_when_marked_by_hand_single_or_absent():
    hand = (f'<div data-sec="a"><h2>A</h2><div data-part="a.t" data-part-label="Mine">{TABLE}</div>{CHART}</div>')
    assert annotate(hand) == hand                                   # the renderer's own marks win
    single = f'<div data-sec="a"><h2>A</h2>{TABLE}</div>'
    assert annotate(single) == single                               # one block = the section itself
    plain = f'<div><h2>A</h2>{TABLE}{CHART}</div>'
    assert annotate(plain) == plain                                 # no data-sec → nothing to do
    out = annotate(f'<div data-sec="a"><h2>A</h2>{TABLE}{CHART}</div>')
    assert annotate(out) == out                                     # running it twice changes nothing


def test_it_never_raises_and_returns_the_input_when_unsure():
    for junk in (None, '', 123, '<div data-sec="x"><h2>', '<div data-sec="x"><table><tr><td>unclosed',
                 '<div data-sec="x"><!-- <table> --><p>a</p><p>b</p></div>', '<<<>>> data-sec'):
        out = annotate(junk)
        assert out == junk or isinstance(out, str)
    # a section key with characters that need escaping stays a valid attribute
    out = annotate(f'<div data-sec="a&amp;b"><h2>A</h2>{TABLE}{CHART}</div>')
    assert 'data-part="a&amp;b.a1"' in out


def test_wrap_helpers():
    assert wrap_section('x', '') == '' and wrap_part('x.y', 'L', '') == ''
    assert wrap_section('wbs', '<p>a</p>') == '<div data-sec="wbs"><p>a</p></div>'
    assert wrap_section('wbs', '<p>a</p>', tag='section').startswith('<section data-sec="wbs">')
    assert wrap_part('x.y', 'A "b" & c', '<p>a</p>') == \
        '<div data-part="x.y" data-part-label="A &quot;b&quot; &amp; c"><p>a</p></div>'


# ── every renderer marks its sections; the hand-named parts ───────────────────────

def test_update_analysis_names_its_parts():
    from tests.test_update_analysis import _parse_and_compute, _xml, build_report_from_data
    from p6_update.exporters import render_html
    wbs = [(100, 'Proj', ''), (200, 'Silo 1', 100), (301, 'Soil Replacement', 200)]
    acts = [(20, 'S1', 'Soil a', 0.5, '2025-03-02', '2025-06-01', 320, 301, {'Discipline': 'Civil'}),
            (21, 'S2', 'Soil b', 0.3, '2025-03-02', '2025-06-01', 320, 301, {'Discipline': 'Civil'})]
    data, metrics = _parse_and_compute(_xml('2025-04-01', acts, [(20, 999)], wbs,
                                            [(999, 'MS', 'Project completion', '2025-06-01', 200)]))
    report = build_report_from_data(data, metrics)
    html = render_html(report)
    assert _secs(html) == ['conclusion', 'time', 'bycode', 'driving', 'counts', 'scope']
    ids = [pid for pid, _lab in _parts(html)]
    assert {'time.status', 'time.values', 'bycode.c1', 'scope.bars'} <= set(ids)
    labels = dict(_parts(html))
    assert labels['time.values'] == 'Planned Value / Earned Value / Variance'
    assert labels['bycode.c1'].startswith('Planned vs Actual — ')
    assert labels['scope.bars'].startswith('Scope weight by ')


def test_update_vs_update_names_its_parts():
    from tests.test_period_exporters import _report
    from p6_period.exporters import render_html
    html = render_html(_report(), trend=None)
    labels = dict(_parts(html))
    for pid in ('dashboard.exec', 'dashboard.recovery', 'dashboard.facts', 'dashboard.defs',
                'whatmoved.chart', 'whatmoved.defs', 'milestones.table', 'milestones.chart'):
        assert pid in labels, pid
    assert labels['dashboard.recovery'] == 'Recovery outlook'
    # every part sits inside the section its id names
    for pid in labels:
        sec = pid.split('.')[0]
        a = html.index('data-sec="%s"' % sec)
        b = html.find('<section data-sec', a + 10)
        assert a < html.index('data-part="%s"' % pid) < (b if b > 0 else len(html)), pid


def test_critical_path_names_its_charts_and_each_milestone_path():
    from tests.test_critpath_exporters import _report
    from p6_critpath.exporters import render_html
    rep = _report()
    html = render_html(rep)
    labels = dict(_parts(html))
    assert labels['dashboard.health'].startswith('Critical path health')
    paths = [lab for pid, lab in labels.items() if pid.startswith('driving_path.m')]
    assert paths and all(p.startswith('Path to ') for p in paths)
    assert len(paths) == len([b for b in rep.get('milestone_paths', [])])
    assert {'recommendation.effect', 'recommendation.list'} <= set(labels)


def test_schedule_health_reports_mark_their_sections(test_server, tmp_path):
    xml = tmp_path / 'lag.xml'
    xml.write_text(_LAG_XML, encoding='utf-8')
    _, parsed = _post_json(test_server, '/api/parse', {'path': str(xml)})
    sid = parsed['snapshot_id']
    meta = {'project_name': 'P'}

    def preview(module, **extra):
        _, d = _post_json(test_server, '/api/report/module',
                          dict({'snapshot_id': sid, 'module': module, 'preview': True, 'meta': meta}, **extra))
        assert d['ok'], d
        return d['html']

    lag = preview('lag_lead')
    assert _secs(lag) == ['summary', 'charts', 'findings']
    assert [lab for pid, lab in _parts(lag) if pid.startswith('charts.')], 'each lag chart is its own part'
    assert _secs(preview('lag_lead', sections=['findings'])) == ['findings']      # the filter still works
    assert _secs(preview('dangling'))[:1] == ['executive'] and 'findings' in _secs(preview('dangling'))
    flt = preview('float')
    if _secs(flt):             # (a schedule with no float data prints a notice instead of the report)
        assert _secs(flt) == ['executive', 'statistics', 'indicators', 'wbs', 'conclusion']
        assert {'executive.gauge', 'executive.method'} <= {pid for pid, _l in _parts(flt)}
    oos = preview('out_of_sequence')
    assert set(_secs(oos)) <= {'executive', 'wbs', 'findings', 'cpi', 'conclusion'} and 'executive' in _secs(oos)
    summary = preview('__summary__')
    assert _secs(summary) == ['overview', 'checks', 'headline', 'composition', 'problems', 'fixes', 'conclusion']
    assert _secs(preview('__summary__', sections=['overview', 'conclusion'])) == ['overview', 'conclusion']


def test_consultant_review_marks_its_sections():
    from p6_compare.exporters import COMPARE_SECTIONS, render_html
    report = {'project_name': 'P', 'dashboard': {'changed_activities': 1, 'logic_changed': 1, 'duration_only': 0},
              'change_summary': {'items': [{'label': 'lag changed', 'count': 1}]},
              'logic': {'rows': []}, 'durations': {'rows': []}}
    secs = _secs(render_html(report))
    assert secs and set(secs) <= set(COMPARE_SECTIONS) and 'logic' in secs
    assert _secs(render_html(report, sections=['logic'])) == ['logic']


def test_the_annotate_route_serves_screen_views(test_server):
    html = f'<html><body><section class="pr-sec" data-sec="kpis"><h2 class="pr-h">Key indicators</h2>{TABLE}{CHART}</section></body></html>'
    _, d = _post_json(test_server, '/api/report/annotate', {'html': html})
    assert d['ok'] and [pid for pid, _l in _parts(d['html'])] == ['kpis.a1', 'kpis.a2']
    _, d = _post_json(test_server, '/api/report/annotate', {})
    assert d['ok'] and d['html'] == ''


def test_float_report_marks_sections_and_the_two_parts_of_its_dashboard():
    from p6_audit.float_report import render_float_report
    mgmt = {'float_health': 98.4, 'fh_color': 'green',
            'high': {'pct': 1.6, 'penalty': 1.6, 'count': 12, 'base': 743, 'dcma_max_pct': 5.0, 'dcma_within_pct': 95.0},
            'neg': {'pct': 61.1, 'penalty': 61.1, 'count': 712, 'context': True},
            'stats': {'total': 1165, 'total_label': 'Remaining Total Activities', 'is_update': True, 'critical': 722,
                      'critical_pct': 62.0, 'near_critical': 6, 'near_critical_pct': 0.5, 'near_band': 10},
            'indicators': {'threshold': 44, 'constr_total': 743, 'constr_over': 12, 'constr_over_pct': 1.6,
                           'top_wbs': 'Phase II Design', 'top_wbs_pct': 100.0, 'highest_float': 148.8,
                           'highest_float_wbs': 'Phase I Construction Works'},
            'wbs': [{'wbs': 'Phase I Construction Works', 'short': 'Phase I Construction Works', 'activities': 743,
                     'avg_float': -28.1, 'max_float': 148.8, 'over_44': 12, 'pct': 1.6, 'is_construction': True}],
            'conclusion': 'The construction logic needs a planning review.'}
    m = {'module': 'float', 'name': 'Float Analysis', 'score': 98.4, 'grade': 'Excellent', 'mgmt': mgmt,
         'kpis': {'threshold': 44}, 'findings': []}
    html = render_float_report(m, {'project_name': 'P'})
    assert _secs(html) == ['executive', 'statistics', 'indicators', 'wbs', 'conclusion']
    assert dict(_parts(html)) == {'executive.gauge': 'Float health score',
                                  'executive.method': 'How the float health score is calculated'}
    assert _secs(render_float_report(m, {'project_name': 'P'}, sections=['wbs'])) == ['wbs']


def test_a_wrapper_around_the_section_title_is_not_a_part():
    head = '<div class="secmark"><span class="secn">3</span><h2>Critical Path &amp; Float</h2><span>driving chain</span></div>'
    html = f'<div data-sec="critical">{head}{TABLE}{CHART}</div>'
    labels = [lab for _id, lab in _parts(annotate(html))]
    assert len(labels) == 2 and labels[0].startswith('Table') and labels[1] == 'Chart'


def test_a_section_can_say_it_is_one_block():
    html = wrap_section('overview', f'<div class="card">{TABLE}{CHART}</div>{CHART}', whole=True)
    assert 'data-parts="none"' in html and annotate(html) == html
