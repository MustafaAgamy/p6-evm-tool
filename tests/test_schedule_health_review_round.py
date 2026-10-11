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
def test_dangling_and_high_duration_say_what_they_cover():
    d = build_presentation({'module': 'dangling', 'kpis': {}, 'findings': []})['highlight']
    assert 'Task Dependent and Resource Dependent' in d and 'Milestones' in d
    h = build_presentation({'module': 'high_duration', 'kpis': {'threshold': 44}, 'findings': []})['highlight']
    assert '44-working-day' in h and 'construction / execution-of-works' in h


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


# ── tip 4: High Duration reconciles with P6's 'Original Duration > limit' filter ─────────────
def test_high_duration_note_reconciles_with_the_p6_filter():
    from p6_audit.modules.high_duration import run_high_duration
    acts = {'t': _act('t', planned_duration=50 * 8), 's': _act('s', planned_duration=10 * 8),
            'loe': _act('loe', task_type='LOE', planned_duration=200 * 8)}
    r = run_high_duration(_g(acts, []), {'audit': {'duration_threshold_days': 44}})
    assert r['kpis']['over_threshold'] == 1 and r['kpis']['span_over_threshold'] == 1
    note = build_presentation(r)['highlight']
    assert 'lists 2 activities: the 1 counted here + 1 Level of Effort / WBS Summary activity' in note
