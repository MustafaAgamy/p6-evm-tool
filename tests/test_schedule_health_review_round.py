"""Schedule Health review round (build 578 comments 1-9) - notes that say what each check covers,
no loop through a Level of Effort activity, and one critical count in every sub-feature."""
import os

from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.checks.circular import check_circular
from p6_audit.modules.circular import run_circular
from p6_audit.modules.cpli import run_cpli
from p6_audit.modules.float_management import float_management
from p6_audit.modules.negative_float import run_negative_float
from p6_audit.presentation import build_presentation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = {'audit': {}}


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _g(acts, rels):
    d = ScheduleData(); d.activities = acts; d.relationships = rels
    return ScheduleGraph(d)


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task',
         'is_critical': False, 'wbs_path': 'P > W', 'category': None}
    b.update(kw); return b


def _rel(p, s, t='FS'):
    return {'pred_id': p, 'succ_id': s, 'type': t, 'lag_days': 0}


# ── comment 3: a chain that returns through a Level of Effort is not a loop in P6 ──────────
def test_chain_through_level_of_effort_is_not_a_loop():
    # Alstom: task -SS-> LOE -FF-> task -FS-> ... -FS-> the first task. P6 schedules it.
    for span in ('LOE', 'WBSSummary'):
        g = _g({'a': _act('a'), 'loe': _act('loe', task_type=span), 'b': _act('b'), 'c': _act('c')},
               [_rel('a', 'loe', 'SS'), _rel('loe', 'b', 'FF'), _rel('b', 'c'), _rel('c', 'a')])
        r = run_circular(g, CONFIG)
        assert r['kpis']['loops'] == 0 and r['blocking'] is False and r['findings'] == []
        assert check_circular(g, CONFIG) == []


def test_real_loop_beside_a_level_of_effort_is_still_reported():
    g = _g({'a': _act('a'), 'b': _act('b'), 'c': _act('c'), 'loe': _act('loe', task_type='LOE')},
           [_rel('a', 'b'), _rel('b', 'c'), _rel('c', 'a'), _rel('a', 'loe', 'SS'), _rel('loe', 'c', 'FF')])
    r = run_circular(g, CONFIG)
    assert r['kpis']['loops'] == 1 and r['kpis']['activities_in_loops'] == 3
    assert len(check_circular(g, CONFIG)) == 1


# ── comments 1, 2, 9: the highlighted notes ─────────────────────────────────────────────────
def test_dangling_says_what_it_covers():
    d = build_presentation({'module': 'dangling', 'kpis': {}, 'findings': []})['highlight']
    assert 'Task Dependent and Resource Dependent' in d and 'Milestones' in d


def test_negative_float_note_when_most_are_a_fraction_of_a_day():
    acts = {f'a{i}': _act(f'a{i}', total_float_days=-0.1 * (i + 1)) for i in range(4)}   # -0.1 .. -0.4
    acts['big'] = _act('big', total_float_days=-12)
    r = run_negative_float(_g(acts, []), CONFIG)
    assert r['kpis']['negative_count'] == 5 and r['kpis']['fraction_count'] == 4
    assert r['kpis']['most_negative'] == -12
    note = build_presentation(r)['highlight']
    assert note.startswith('4 of the 5 negative-float activities') and '0.5 day' in note


def test_negative_float_note_absent_for_real_negative_float():
    acts = {'a': _act('a', total_float_days=-8), 'b': _act('b', total_float_days=-3),
            'c': _act('c', total_float_days=-0.2), 'd': _act('d', total_float_days=5)}
    r = run_negative_float(_g(acts, []), CONFIG)
    assert r['kpis']['fraction_count'] == 1
    assert build_presentation(r)['highlight'] is None
    clean = run_negative_float(_g({'a': _act('a', total_float_days=0)}, []), CONFIG)
    assert build_presentation(clean)['highlight'] is None


def test_highlight_reaches_screen_report_and_excel():
    assert 'p.highlight' in _read('ui/modules/audit.js')
    assert '.kpi-highlight' in _read('ui/style.css')
    assert 'class="hnote"' in _read('p6_audit/report.py')
    assert "p.get('highlight')" in _read('p6_audit/excel_sheets.py')


# ── comments 5, 7, 8: one critical / negative count, whichever sub-feature shows it ────────
def test_critical_count_is_one_number_everywhere():
    acts = {
        'c1': _act('c1', total_float_days=0, is_critical=True, status='Not Started'),
        'c2': _act('c2', total_float_days=-0.2, is_critical=True, status='In Progress'),
        'ms': _act('ms', total_float_days=0, is_critical=True, task_type='FinishMilestone', status='Not Started'),
        'n1': _act('n1', total_float_days=0.5, status='Not Started'),      # near-critical: above 0
        'n2': _act('n2', total_float_days=10, status='Not Started'),       # near-critical: up to 10
        'f1': _act('f1', total_float_days=10.5, status='Not Started'),
        'dn': _act('dn', total_float_days=None, status='Completed', actual_finish='x'),
    }
    g = _g(acts, [])
    cpli = run_cpli(g, CONFIG)
    stats = float_management(g, CONFIG)['stats']
    assert cpli['kpis']['critical_count'] == len(cpli['findings']) == stats['critical'] == 3
    assert stats['near_critical'] == 2
    assert run_negative_float(g, CONFIG)['kpis']['negative_count'] == 1


# ── comments 4, 6: Dangling table wording and the Apply-all button position ─────────────────
def test_dangling_table_headers_and_apply_all_above_the_table():
    js = _read('ui/modules/audit.js')
    assert 'Start side (predecessor)' not in js and 'Finish side (successor)' not in js
    assert '<th class="dng-gcol">Predecessor</th><th>Successor</th>' in js
    table = js[js.index('function _dngTable('):js.index('function _dngTable(') + 3200]
    assert table.index('${applyAllBar}') < table.index('<table class="audit-table dng-logx">')


# ── High Duration: Construction only by default, the planner picks the WBS (review decision) ──
class _Cal:
    def __init__(self, name, day_hours):
        self.name, self.day_hours = name, day_hours


def _hd_graph():
    def act(oid, wbs, days, cal='C8', **kw):
        return _act(oid, wbs_path=f'Proj > {wbs} > Area', calendar_id=cal,
                    planned_duration=days * (24 if cal == 'C24' else 8), **kw)
    acts = {
        'c1': act('c1', 'Construction Works', 50), 'c2': act('c2', 'Construction Works', 10),
        'c3': act('c3', 'Construction Works', 20), 'c4': act('c4', 'Construction Works', 45, cal='C24'),
        'p1': act('p1', 'Procurement', 120), 'p2': act('p2', 'Procurement', 90), 'p3': act('p3', 'Procurement', 5),
        'e1': act('e1', 'Engineering', 30),
        'loe': act('loe', 'Construction Works', 300, task_type='LOE'),
        'ms': act('ms', 'Construction Works', 0, task_type='FinishMilestone'),
    }
    d = ScheduleData(); d.activities = acts; d.relationships = []
    d.calendars = {'C8': _Cal('Site 8h', 8.0), 'C24': _Cal('Site 24h', 24.0)}
    return ScheduleGraph(d)


def test_high_duration_evaluates_construction_only():
    from p6_audit.modules.high_duration import run_high_duration
    r = run_high_duration(_hd_graph(), {'audit': {'duration_threshold_days': 44}})
    k = r['kpis']
    assert k['scope_label'] == 'Construction only' and k['view_default'] is True
    assert k['scope_wbs'] == k['view_wbs'] == ['Construction Works']
    # Task Dependent only (no LOE / milestone); each on its OWN calendar: c4 = 45 days of 24 h
    assert (k['total_activities'], k['over_threshold'], k['high_pct']) == (4, 2, 50.0)
    assert (k['all_activities'], k['all_task_activities'], k['all_over_threshold']) == (10, 8, 4)
    assert sorted(f['activity_id'] for f in r['findings']) == ['c1', 'c4']
    assert sorted(f['activity_id'] for f in r['mgmt']['not_counted']) == ['p1', 'p2']
    assert r['score'] == 50.0
    rows = {x['wbs']: x for x in r['mgmt']['wbs']}
    assert rows['Procurement'] == {'wbs': 'Procurement', 'activities': 3, 'over': 2, 'pct': 66.7,
                                   'is_construction': False, 'evaluated': False, 'counted': False,
                                   'p6_activities': 3, 'p6_over': 2}
    assert rows['Construction Works']['evaluated'] is True


def test_high_duration_reads_task_dependent_only():
    from p6_audit.modules.high_duration import run_high_duration
    acts = {'t': _act('t', wbs_path='P > Construction', planned_duration=400),
            'r': _act('r', wbs_path='P > Construction', planned_duration=400, task_type='ResourceDependent')}
    r = run_high_duration(_g(acts, []), {'audit': {}})
    assert r['kpis']['all_task_activities'] == 1 and [f['activity_id'] for f in r['findings']] == ['t']
    assert 'Resource Dependent activities are not counted' in build_presentation(r)['highlight']


def test_picking_a_wbs_shows_it_but_never_moves_the_evaluation():
    from p6_audit.modules.high_duration import run_high_duration, rescope
    base = run_high_duration(_hd_graph(), {'audit': {'duration_threshold_days': 44}})
    pick = rescope(base, ['Procurement', 'Engineering'])
    k = pick['kpis']
    # the evaluation is still the Construction WBS
    assert (pick['score'], pick['grade'], pick['pct']) == (base['score'], base['grade'], base['pct'])
    assert (k['scope_label'], k['total_activities'], k['over_threshold'], k['high_pct']) == ('Construction only', 4, 2, 50.0)
    # the pick is shown beside it
    assert k['view_label'] == 'Procurement, Engineering' and k['view_default'] is False
    assert (k['view_activities'], k['view_over'], k['view_pct']) == (4, 2, 50.0)
    assert sorted(f['activity_id'] for f in pick['findings']) == ['p1', 'p2']
    assert sorted(f['activity_id'] for f in pick['mgmt']['not_counted']) == ['c1', 'c4']
    everything = rescope(pick, ['Construction Works', 'Procurement', 'Engineering'])
    assert everything['kpis']['view_label'] == 'All WBS' and everything['kpis']['view_over'] == 4
    assert everything['score'] == 50.0 and everything['mgmt']['not_counted'] == []
    # an unknown / empty pick = the evaluated WBS again, from the stored result alone
    again = rescope(everything, [])
    assert again['kpis'] == base['kpis'] and again['findings'] == base['findings']
    assert rescope(everything, ['No such WBS'])['kpis']['view_label'] == 'Construction only'
    assert base['kpis']['view_label'] == 'Construction only'          # rescope never edits its input


def test_high_duration_without_a_construction_wbs_counts_every_wbs():
    from p6_audit.modules.high_duration import run_high_duration, rescope
    acts = {'a': _act('a', wbs_path='P > Zone A', planned_duration=400), 'b': _act('b', wbs_path='P > Zone B', planned_duration=8)}
    r = run_high_duration(_g(acts, []), {'audit': {}})
    assert r['kpis']['scope_fallback'] is True and r['kpis']['scope_label'] == 'All WBS'
    assert r['kpis']['total_activities'] == 2 and r['kpis']['over_threshold'] == 1
    assert 'No WBS of this schedule is named Construction' in build_presentation(r)['highlight']
    # a result stored before the WBS scope existed is left exactly as it is
    old = {'module': 'high_duration', 'kpis': {'total_activities': 9, 'over_threshold': 3}, 'findings': [{'x': 1}], 'score': 66.7}
    assert rescope(old, ['Zone A']) == old


def test_high_duration_presentation_explains_every_figure():
    from p6_audit.modules.high_duration import run_high_duration, rescope
    r = run_high_duration(_hd_graph(), {'audit': {'duration_threshold_days': 44}})
    p = build_presentation(r)
    tiles = {t['label']: t['value'] for t in p['tiles']}
    assert tiles['WBS Evaluated'] == 'Construction only' and tiles['Task Dependent Activities Evaluated'] == '4'
    assert tiles['Task Dependent Activities (all WBS)'] == '8' and tiles['Over Threshold (evaluated)'] == '2'
    assert 'Also Shown (picked WBS)' not in tiles
    assert 'Task Dependent activities only' in p['highlight']
    assert 'considers the Construction WBS only, by default - Construction Works, 4 of the 8 task activities' in p['highlight']
    assert 'additional option' in p['highlight'] and 'does not change the evaluation' in p['highlight']
    # every figure worked out with the schedule's own numbers
    note = p['tiles_note']
    assert 'Task Dependent Activities (all WBS) 8 = 10 total - 2 milestones' in note
    assert 'High-Duration % 50% = 2 / 4. Score 50 = 100 - 50.' in note
    assert p['p6_filter'].startswith('Check it in P6: filter Activity Type equals Task Dependent and Original Duration')
    assert 'WBS is under Construction Works - P6 lists 2 activities' in p['p6_filter']
    assert [x['wbs'] for x in p['wbs_scope'] if x['evaluated']] == ['Construction Works']
    # each activity on its own assigned calendar - said in the report
    assert any('calendar assigned to each activity' in t and '24 h/day: 1 activities' in t for t in p['highlights'])
    picked = build_presentation(rescope(r, ['Procurement']))
    ptiles = {t['label']: t['value'] for t in picked['tiles']}
    assert ptiles['WBS Evaluated'] == 'Construction only' and ptiles['Over Threshold (evaluated)'] == '2'
    assert ptiles['Also Shown (picked WBS)'] == 'Procurement' and ptiles['Over Threshold (picked WBS)'] == '2 of 3 - 66.7%'
    assert 'Shown as picked: Procurement - 2 of 3 task activities over the limit (66.7%).' in picked['highlight']
    assert 'WBS is under Procurement - P6 lists 2 activities' in picked['p6_filter']
    from p6_audit.report import render_module_report
    html = render_module_report({**r, 'presentation': p}, {'project_name': 'x'})
    assert 'WBS scope' in html and '<th>Evaluated</th><th>Listed</th>' in html and 'Check it in P6' in html


def test_picked_wbs_is_applied_when_the_result_is_read_back(tmp_path, monkeypatch):
    import db
    from p6_audit.modules.high_duration import run_high_duration
    monkeypatch.setattr(db, '_db_path', lambda: str(tmp_path / 't.db'))
    db.init_db()
    r = run_high_duration(_hd_graph(), {'audit': {'duration_threshold_days': 44}})
    pid = db.upsert_project('P1', 'Proj')
    sid = db.insert_snapshot(pid, None, 'x.xer', 'x.xer', 'h', 10, 2)
    db.insert_audit_modules(sid, {'module_order': ['high_duration'], 'modules': {'high_duration': r}})
    got = db.get_audit_modules_for_snapshot(sid)['modules']['high_duration']
    assert got['kpis']['view_label'] == 'Construction only' and got['kpis']['over_threshold'] == 2
    db.save_snapshot_ui_state(sid, db.HIGH_DURATION_WBS_KEY, ['Procurement'])
    got = db.get_audit_modules_for_snapshot(sid)['modules']['high_duration']
    assert got['kpis']['view_label'] == 'Procurement' and got['score'] == 50.0      # score: Construction
    assert sorted(f['activity_id'] for f in got['findings']) == ['p1', 'p2']
    db.save_snapshot_ui_state(sid, db.HIGH_DURATION_WBS_KEY, None)
    assert db.get_audit_modules_for_snapshot(sid)['modules']['high_duration']['kpis']['view_default'] is True


def test_wbs_scope_is_wired_on_the_screen_and_the_server():
    js, srv = _read('ui/modules/audit.js'), _read('server.py')
    assert '${hdScopeHtml(m)}' in js and 'hdScopeWire(m);' in js
    assert "'/api/health/high-duration-scope'" in srv and '/api/health/high-duration-scope' in js
    assert '.hds-row' in _read('ui/style.css')


_SCOPE_XER = (
    "ERMHDR\t19.12\n"
    "%T\tPROJECT\n%F\tproj_id\tproj_short_name\tlast_recalc_date\n%R\t1\tP1\t2026-02-09 00:00\n"
    "%T\tCALENDAR\n%F\tclndr_id\tclndr_name\tday_hr_cnt\n%R\t10\t8hr\t8\n"
    "%T\tPROJWBS\n%F\twbs_id\twbs_name\tparent_wbs_id\tproj_node_flag\n"
    "%R\t100\tProj\t\tY\n%R\t101\tConstruction\t100\tN\n%R\t102\tProcurement\t100\tN\n"
    "%T\tTASK\n%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_type\ttask_code\ttask_name"
    "\ttarget_drtn_hr_cnt\tremain_drtn_hr_cnt\trestart_date\treend_date\n"
    "%R\t1\t1\t101\t10\tTT_Task\tC10\tPour slab\t80\t80\t2026-03-01 08:00\t2026-03-10 17:00\n"
    "%R\t2\t1\t101\t10\tTT_Task\tC20\tErect steel\t400\t400\t2026-03-11 08:00\t2026-05-10 17:00\n"
    "%R\t3\t1\t102\t10\tTT_Task\tP10\tDeliver chillers\t800\t800\t2026-03-01 08:00\t2026-07-10 17:00\n"
    "%R\t4\t1\t102\t10\tTT_Task\tP20\tDeliver pumps\t720\t720\t2026-03-01 08:00\t2026-06-30 17:00\n"
    "%T\tTASKPRED\n%F\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt\n%R\t2\t1\tPR_FS\t0\n"
    "%E\n"
)


def test_wbs_scope_round_trip_through_the_server(test_server, tmp_path):
    """Import -> Construction only; pick Procurement -> the check, the re-opened result and the
    Excel export all list Procurement while the score stays on Construction; an empty pick ->
    Construction listed again."""
    import http.client
    import json

    def post(path, payload):
        conn = http.client.HTTPConnection('127.0.0.1', test_server, timeout=30)
        conn.request('POST', path, body=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        return json.loads(conn.getresponse().read())

    p = tmp_path / 'scope.xer'
    p.write_text(_SCOPE_XER, encoding='utf-8')
    parsed = post('/api/parse', {'path': str(p)})
    sid = parsed['snapshot_id']
    hd = parsed['result']['audit_modules']['modules']['high_duration']
    assert hd['kpis']['scope_label'] == 'Construction only'
    assert (hd['kpis']['total_activities'], hd['kpis']['over_threshold'], hd['score']) == (2, 1, 50.0)
    assert [f['activity_id'] for f in hd['findings']] == ['C20']

    r = post('/api/health/high-duration-scope', {'snapshot_id': sid, 'wbs': ['Procurement']})
    assert r['ok'] and r['module']['kpis']['view_label'] == 'Procurement'
    assert r['module']['kpis']['view_over'] == 2 and r['module']['score'] == 50.0   # score stays Construction
    assert sorted(f['activity_id'] for f in r['module']['findings']) == ['P10', 'P20']
    assert [x['wbs'] for x in r['module']['presentation']['wbs_scope'] if x['counted']] == ['Procurement']

    out = str(tmp_path / 'hd.xlsx')
    assert post('/api/export/excel', {'snapshot_id': sid, 'module': 'high_duration', 'output_path': out})['ok']
    import zipfile
    with zipfile.ZipFile(out) as z:
        text = ' '.join(z.read(n).decode('utf-8', 'ignore') for n in z.namelist() if n.endswith('.xml'))
    assert 'P10' in text and 'P20' in text

    back = post('/api/health/high-duration-scope', {'snapshot_id': sid, 'wbs': []})
    assert back['module']['kpis']['view_label'] == 'Construction only' and back['module']['score'] == 50.0
    assert post('/api/health/high-duration-scope', {'wbs': ['Procurement']})['ok'] is False


# ── every check counts the activities under each major WBS the way P6 does ──────────────────
def test_each_check_shows_p6s_activity_count_per_major_wbs():
    from p6_audit.modules.high_duration import run_high_duration
    g = _hd_graph()
    g.activities['c1']['is_critical'] = True
    g.activities['ms']['is_critical'] = True
    g.activities['p3']['status'] = 'Completed'
    g.activities['p3']['is_critical'] = True            # completed: never in P6's Critical filter
    for oid, tf in (('c1', 0), ('c2', 60), ('p1', 50), ('p3', 90), ('e1', -2), ('loe', 100)):
        g.activities[oid]['total_float_days'] = tf
    cp = run_cpli(g, CONFIG)
    rows = {r['wbs']: r for r in cp['wbs_summary']}
    # Construction Works: 4 tasks + the LOE + the milestone = 6 activities in P6's WBS band
    assert rows['Construction Works'] == {'wbs': 'Construction Works', 'activities': 6, 'remaining': 6, 'critical': 2}
    assert rows['Procurement'] == {'wbs': 'Procurement', 'activities': 3, 'remaining': 2, 'critical': 0}
    assert sum(r['critical'] for r in cp['wbs_summary']) == cp['kpis']['critical_count'] == len(cp['findings']) == 2
    assert (cp['kpis']['critical_task'], cp['kpis']['critical_milestone']) == (1, 1)
    p = build_presentation(cp)
    assert p['tiles_note'].startswith('Critical Activities 2 = 1 Task Dependent + 1 milestones.')
    assert p['wbs_table']['total'] == ['Whole schedule', '10', '9', '2']

    fw = {r['wbs']: r for r in float_management(g, {'audit': {'float_threshold_days': 44}})['p6_wbs']}
    assert (fw['Construction Works']['activities'], fw['Construction Works']['over']) == (6, 2)    # c2 + the LOE
    assert (fw['Procurement']['over'], fw['Engineering']['negative']) == (1, 1)                  # p3 is completed

    hd = run_high_duration(g, {'audit': {'duration_threshold_days': 44}})
    hw = {r['wbs']: r for r in hd['mgmt']['wbs']}
    # P6's 'Original Duration > 44d' lists the LOE too: 3 in Construction Works, 2 of them Task Dependent
    assert (hw['Construction Works']['p6_activities'], hw['Construction Works']['p6_over'], hw['Construction Works']['over']) == (6, 3, 2)
    assert (hd['kpis']['p6_over_threshold'], hd['kpis']['all_over_threshold']) == (5, 4)
    hp = build_presentation(hd)
    tiles = {t['label']: t['value'] for t in hp['tiles']}
    assert tiles['Over Threshold - whole schedule (P6 filter)'] == '5' and tiles['of which Task Dependent'] == '4'
    assert "lists 5 activities in the whole schedule = 4 Task Dependent + 1 of other types" in hp['tiles_note']
    assert hp['wbs_table']['total'] == ['Whole schedule', '10', '5', '8', '4']
    js = _read('ui/modules/audit.js')
    assert js.count('p6WbsTableHtml(') >= 4 and "p.get('wbs_table')" in _read('p6_audit/excel_sheets.py')


def test_spreadsheet_check_proves_every_figure_against_the_p6_file(tmp_path):
    """tests/p6_spreadsheet_check.py reads the P6 file itself (one row per activity) and compares
    every Schedule Health figure with it - the check run on real schedules before a build is sent."""
    from tests.p6_spreadsheet_check import check
    p = tmp_path / 'scope.xer'
    p.write_text(_SCOPE_XER, encoding='utf-8')
    res, book = check(str(p), str(tmp_path / 'out'))
    assert len(res) >= 40 and [r[0] for r in res if not r[3]] == []
    assert os.path.isfile(book)
