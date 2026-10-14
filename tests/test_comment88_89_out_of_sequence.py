"""Comments 88-89 - Out of Sequence as Primavera P6's schedule log lists it, corrections that leave
the schedule clean in P6, and a dashboard that follows the applied corrections.

Checked against a real P6 log (MAFI, 12-Oct-2026): P6 lists 1 out-of-sequence activity where the
tool listed 59; 1 activity without predecessor and 2 without successor (milestones included).
"""
import os
from datetime import datetime

from p6_evm.parser import ScheduleData
from p6_audit.graph import ScheduleGraph
from p6_audit.modules import oos_resolve as R
from p6_audit.modules.out_of_sequence import run_out_of_sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = {'audit': {}}


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def dt(s):
    return datetime.strptime(s, '%Y-%m-%d')


def _act(oid, **kw):
    b = {'object_id': oid, 'id': oid, 'name': f'Act {oid}', 'task_type': 'Task', 'is_critical': False,
         'wbs_path': 'P > Construction', 'category': None, 'calendar_id': None,
         'actual_start': None, 'actual_finish': None, 'status': 'Not Started'}
    b.update(kw)
    return b


def _data(acts, rels):
    d = ScheduleData()
    d.activities = acts
    d.relationships = [{'pred_id': p, 'succ_id': s, 'type': t, 'lag_days': 0.0} for p, s, t in rels]
    d.calendars = {}
    d.project = {'data_date': dt('2026-03-01')}
    return d


def _ops(findings):
    out = []
    for f in findings:
        r = f.get('pred_resolution') or {}
        if r.get('action') in ('change', 'remove', 'replace'):
            out.append({'finding_id': f['finding_id'], 'pred_id': f['pred_id'], 'succ_id': f['activity_id'],
                        'action': r['action'], 'new_type': r.get('new_type'), 'new_lag_days': r.get('new_lag_days'),
                        'new_pred_id': r.get('new_pred_id') if r['action'] == 'replace' else ''})
    return out


def _oos(data):
    return run_out_of_sequence(ScheduleGraph(data), CONFIG)


# ── the P6 log's rule ───────────────────────────────────────────────────────────────────────
def test_only_a_relationship_still_unsatisfied_at_the_data_date_is_out_of_sequence():
    started = dict(actual_start=dt('2026-01-05'), status='In Progress')
    acts = {
        # Start-to-Start, the predecessor started AFTER its successor but HAS started: satisfied
        'p1': _act('p1', actual_start=dt('2026-02-01'), status='In Progress'), 's1': _act('s1', **started),
        # Start-to-Start, the predecessor has not started: out of sequence
        'p2': _act('p2'), 's2': _act('s2', **started),
        # Finish-to-Start, the predecessor finished after its successor started: finished work, satisfied
        'p3': _act('p3', actual_start=dt('2026-01-01'), actual_finish=dt('2026-02-10'), status='Completed'),
        's3': _act('s3', **started),
        # Finish-to-Start, the predecessor is still running: out of sequence
        'p4': _act('p4', actual_start=dt('2026-01-01'), status='In Progress'), 's4': _act('s4', **started),
        # no progress on the successor: never out of sequence
        'p5': _act('p5'), 's5': _act('s5'),
    }
    d = _data(acts, [('p1', 's1', 'SS'), ('p2', 's2', 'SS'), ('p3', 's3', 'FS'), ('p4', 's4', 'FS'), ('p5', 's5', 'FS')])
    r = _oos(d)
    assert sorted(f['activity_id'] for f in r['findings']) == ['s2', 's4']
    assert r['kpis']['oos_count'] == 2


# ── one Apply corrects every out-of-sequence tie of the activity ────────────────────────────
def _many_ties():
    acts = {'x': _act('x', actual_start=dt('2026-01-10'), status='In Progress')}
    rels = []
    for i in range(4):                               # x started ahead of four unfinished predecessors
        acts[f'p{i}'] = _act(f'p{i}')
        rels.append((f'p{i}', 'x', 'FS'))
    acts['done'] = _act('done', actual_start=dt('2025-12-01'), actual_finish=dt('2025-12-20'), status='Completed')
    rels.append(('done', 'x', 'FS'))
    return _data(acts, rels)


def test_a_finding_shows_one_tie_but_apply_corrects_them_all():
    d = _many_ties()
    findings = _oos(d)['findings']
    assert len(findings) == 1                       # one row per activity
    accepted = _ops(findings)
    assert len(accepted) == 1
    full = R.complete_ops(d, CONFIG, accepted)
    assert sorted(o['pred_id'] for o in full) == ['p0', 'p1', 'p2', 'p3']
    assert sum(1 for o in full if o.get('auto') == 'tie') == 3
    out = R.revalidate(d, CONFIG, accepted)
    assert out['findings'] == [] and out['resolved'] == [findings[0]['finding_id']]
    assert out['auto'] == {'ties': 3, 'closed': 0}
    # the untouched tie to the finished predecessor is left exactly as it was
    rels = R.apply_ops_to_relationships(d, full)
    assert [r['type'] for r in rels if r['pred_id'] == 'done'] == ['FS']


def test_an_activity_the_planner_did_not_accept_is_left_alone():
    d = _many_ties()
    d.activities['y'] = _act('y', actual_start=dt('2026-01-10'), status='In Progress')
    d.activities['q'] = _act('q')
    d.relationships.append({'pred_id': 'q', 'succ_id': 'y', 'type': 'FS', 'lag_days': 0.0})
    accepted = [o for o in _ops(_oos(d)['findings']) if o['succ_id'] == 'x']
    out = R.revalidate(d, CONFIG, accepted)
    assert [f['activity_id'] for f in out['findings']] == ['y']


# ── no correction leaves an open end ────────────────────────────────────────────────────────
def test_a_removed_tie_never_leaves_an_activity_without_predecessor_or_successor():
    acts = {
        'ntp': _act('ntp', task_type='StartMilestone', name='Project Commencement', actual_start=dt('2025-11-01'),
                    status='Completed'),
        'end': _act('end', task_type='FinishMilestone', name='Project Completion', planned_finish=dt('2026-12-01')),
        'a': _act('a'),                                              # not started; only successor is x
        'x': _act('x', actual_start=dt('2026-01-01'), actual_finish=dt('2026-01-20'), status='Completed'),
        'z': _act('z'),
    }
    d = _data(acts, [('ntp', 'a', 'FS'), ('a', 'x', 'FS'), ('x', 'z', 'FS'), ('z', 'end', 'FS')])
    accepted = [{'finding_id': _oos(d)['findings'][0]['finding_id'], 'pred_id': 'a', 'succ_id': 'x',
                 'action': 'remove', 'new_type': None, 'new_lag_days': None, 'new_pred_id': ''}]
    full = R.complete_ops(d, CONFIG, accepted)
    closing = [(o['pred_id'], o['succ_id'], o['action']) for o in full if o.get('auto') == 'close']
    assert sorted(closing) == [('a', 'end', 'add'), ('ntp', 'x', 'add')]
    rels = R.apply_ops_to_relationships(d, full)
    assert {r['succ_id'] for r in rels} >= {'a', 'x', 'z', 'end'} and {r['pred_id'] for r in rels} >= {'ntp', 'a', 'x', 'z'}
    out = R.revalidate(d, CONFIG, accepted)
    assert out['findings'] == [] and out['auto']['closed'] == 2
    # the ops reach the corrected file through the same vocabulary
    kinds = [o['kind'] for o in R.to_file_ops(full, d)]
    assert kinds.count('remove_rel') == 1 and kinds.count('add_rel') == 2


# ── comment 89: the dashboard follows the corrections ───────────────────────────────────────
def test_revalidation_returns_the_whole_check_as_corrected():
    d = _many_ties()
    before = _oos(d)
    out = R.revalidate(d, CONFIG, _ops(before['findings']))
    assert set(out['module']) == {'score', 'grade', 'pct', 'kpis', 'wbs_summary'}
    assert before['kpis']['oos_count'] == 1 and out['module']['kpis']['oos_count'] == 0
    assert out['module']['score'] >= before['score'] and out['module']['pct'] == 0.0
    js = _read('ui/modules/audit.js')
    assert '_oos.live = out.module' in js and 'Object.assign({}, base, _oos.live)' in js
    assert js.count('_oosTakeValidated(out)') >= 3            # Apply, Apply all and Re-open
    assert '_oosInit(base);' in js                            # the applied list survives the redraw


# ── the schedule-log check itself ───────────────────────────────────────────────────────────
def test_schedule_log_reader(tmp_path):
    from tests.p6_schedlog_check import read_log
    log = tmp_path / 'SCHEDLOG.TXT'
    log.write_text(
        "Warnings:\n---------\n"
        "\tActivities without predecessors..................................1\n"
        "\t\tProject:\tP1\tActivity:\tA-1000\tProject Commencement Date\n\n"
        "\tActivities without successors....................................2\n"
        "\t\tProject:\tP1\tActivity:\tA-1010\tProject Finish Date\n"
        "\t\tProject:\tP1\tActivity:\tA-5713\tInstallation of skirting\n( wrapped name )\n\n"
        "\tOut-of-sequence activities.......................................1\n"
        "\t\tProject:\tP1\tActivity:\tA-3311\tPouring of S.O.G\n\n"
        "\tActivities with Actual Dates > Data Date.........................0\n\n"
        "Exceptions:\n-----------\n"
        "\tCritical Activities..............................................2\n"
        "\t\tProject:\tP1\tActivity:\tA-11030\tBMS\n"
        "\t\tProject:\tP1\tActivity:\tA-11040\tBMS fixtures\n\n"
        "\tActivities with unsatisfied constraints..........................0\n", encoding='latin-1')
    got = read_log(str(log))
    assert got['no_predecessor'] == (1, ['A-1000'])
    assert got['no_successor'] == (2, ['A-1010', 'A-5713'])
    assert got['out_of_sequence'] == (1, ['A-3311'])
    assert got['critical'] == (2, ['A-11030', 'A-11040'])


# ── follow-up round (12-Oct): XML adds, exports follow the screen, changed ties highlighted ──
def test_an_added_relationship_is_written_where_p6_reads_it(tmp_path):
    """P6 reads a project's elements in the schema's order; a <Relationship> appended after
    <ScheduleOptions> was skipped on import, so a replaced predecessor reached P6 without its
    replacement. New ties now sit right after the last relationship."""
    import xml.etree.ElementTree as ET
    from p6_compare.revert import write_corrected_xml
    ns = 'http://xmlns.oracle.com/Primavera/P6/V19.12/API/BusinessObjects'
    src = tmp_path / 'u.xml'
    src.write_text(
        f'<?xml version="1.0"?><APIBusinessObjects xmlns="{ns}"><Project><ObjectId>1</ObjectId>'
        '<Activity><Id>A</Id><ObjectId>11</ObjectId></Activity><Activity><Id>B</Id><ObjectId>12</ObjectId></Activity>'
        '<Activity><Id>C</Id><ObjectId>13</ObjectId></Activity>'
        '<Relationship><Lag>0</Lag><ObjectId>100</ObjectId><PredecessorActivityObjectId>11</PredecessorActivityObjectId>'
        '<PredecessorProjectObjectId>1</PredecessorProjectObjectId><SuccessorActivityObjectId>12</SuccessorActivityObjectId>'
        '<SuccessorProjectObjectId>1</SuccessorProjectObjectId><Type>Finish to Start</Type></Relationship>'
        '<ScheduleOptions><ObjectId>5</ObjectId></ScheduleOptions></Project></APIBusinessObjects>', encoding='utf-8')
    out = tmp_path / 'c.xml'
    write_corrected_xml(str(src), [{'kind': 'remove_rel', 'pred_code': 'A', 'succ_code': 'B'},
                                   {'kind': 'add_rel', 'pred_code': 'C', 'succ_code': 'B', 'type': 'FS', 'lag_hours': 0}], str(out))
    proj = ET.parse(out).getroot().find(f'{{{ns}}}Project')
    tags = [c.tag.split('}')[1] for c in proj]
    assert tags[-2:] == ['Relationship', 'ScheduleOptions']
    rel = proj.find(f'{{{ns}}}Relationship')
    assert rel.find(f'{{{ns}}}PredecessorActivityObjectId').text == '13'
    assert rel.find(f'{{{ns}}}SuccessorActivityObjectId').text == '12'


def test_every_changed_tie_is_listed_for_both_activities():
    d = _many_ties()
    out = R.revalidate(d, CONFIG, _ops(_oos(d)['findings']))
    ch = out['changes']
    assert sorted(c['other'] for c in ch['x'] if c['side'] == 'pred') == ['p0', 'p1', 'p2', 'p3']
    assert all(c['before'] == 'FS' and c['after'].startswith('FF') for c in ch['x'])
    assert [c['side'] for c in ch['p0']] == ['succ']                 # the predecessor sees it too
    assert sum(1 for c in ch['x'] if c['auto'] == 'tie') == 3


def test_the_report_and_workbook_print_the_check_as_on_screen():
    """The default for every feature: after fixes, the PDF and Excel print the screen."""
    import server
    from p6_audit.report import render_module_report
    from p6_audit.exporters import excel_columns
    d = _many_ties()
    stored = _oos(d)
    out = R.revalidate(d, CONFIG, _ops(stored['findings']))
    live = dict(out['module'], applied=1,
                findings=[dict(f, status='Resolved', changes=out['changes'].get(f['activity_id'], []))
                          for f in stored['findings']])
    m = server.Handler._live_as_on_screen(dict(stored, module='out_of_sequence'), {'live_module': live})
    assert m['kpis']['oos_count'] == 0 and m['score'] == out['module']['score']
    assert 'After 1 applied correction' in m['presentation']['verdict']
    assert '0% of activities progressed out of logical sequence. After 1 applied correction' in render_module_report(m, {'project_name': 'x'})
    html = render_module_report(m, {'project_name': 'x'})
    assert '<th rowspan="2">Status</th>' in html and 'Resolved' in html
    assert html.count('p0</span> FS → <b>FF') == 1 and 'p3</span> FS → <b>FF' in html
    headers, rows = excel_columns(m)
    assert headers[-1] == 'Status' and rows[0][-1] == 'Resolved'
    runs = rows[0][headers.index('After Predecessor Tie')].runs
    assert len(runs) == 4 and all(r['b'] and r['color'] == 'FF92400E' for r in runs)
    # nothing applied: the stored check prints unchanged
    assert server.Handler._live_as_on_screen(stored, {}) is stored
    js, api = _read('ui/modules/audit.js'), _read('ui/modules/api.js')
    assert 'export const LIVE_EXPORTS = { out_of_sequence: oosLiveModule }' in js
    assert api.count('LIVE_EXPORTS[') >= 3 and 'live_module = live' in api


def test_apply_all_sits_above_the_table_and_changed_ties_are_highlighted():
    js = _read('ui/modules/audit.js')
    tbl = js[js.index('function _oosLogTable('):]
    assert tbl.index('${applyAllBar}') < tbl.index('<table class="audit-table oos-logx">')
    assert "_oosChangedCell(f, 'pred')" in js and "_oosChangedCell(f, 'succ')" in js
    assert '.oos-relrow.oos-chg' in _read('ui/style.css')


def test_every_driving_tie_is_marked_and_every_relationship_listed():
    """15-Oct: a predecessor changed by the fix was missing from the current relationships (a
    milestone tie was left out of the list) and only the first of several driving ties was marked."""
    acts = {'x': _act('x', actual_start=dt('2026-01-10'), status='In Progress'),
            'p0': _act('p0'), 'p1': _act('p1'),
            'ms': _act('ms', task_type='FinishMilestone'),                 # a milestone not reached
            'ok': _act('ok', actual_start=dt('2025-12-01'), actual_finish=dt('2025-12-20'), status='Completed')}
    d = _data(acts, [('p0', 'x', 'FS'), ('p1', 'x', 'FS'), ('ms', 'x', 'FS'), ('ok', 'x', 'FS')])
    f = _oos(d)['findings'][0]
    listed = {p['id']: p['affected'] for p in f['all_predecessors']}
    assert listed == {'p0': True, 'p1': True, 'ms': True, 'ok': False}
    assert [p['id'] for p in f['all_predecessors']][-1] == 'ok'               # driving ties listed first
    ch = R.revalidate(d, CONFIG, _ops([f]))['changes']['x']
    assert {c['other'] for c in ch if c['side'] == 'pred'} == {'p0', 'p1', 'ms'}
    assert all(listed[c['other']] for c in ch if c['side'] == 'pred')
    from p6_audit.exporters import excel_columns
    headers, rows = excel_columns({'module': 'out_of_sequence', 'kpis': {}, 'findings': [f]})
    bold = [r['t'].strip() for r in rows[0][headers.index('Baseline Predecessors')].runs if r['b']]
    assert len(bold) == 3 and all('[Driving]' in t for t in bold)
